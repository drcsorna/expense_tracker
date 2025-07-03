"""
Expense Tracker - FastAPI Application Entry Point

PURPOSE: HTTP routing, request handling, and FastAPI server configuration
SCOPE: ~200 lines - Controller layer only, delegates business logic to services
DEPENDENCIES: services.py (business logic), database.py (persistence)

AI CONTEXT: This is the main FastAPI application that handles HTTP requests.
All business logic is in services.py, database operations in database.py.
When working on API endpoints, this is your primary file.

DEPLOYMENT: Works in both development (remote VS Code) and Docker containers
DEVELOPMENT: Auto-reload enabled, CORS configured for local development
PRODUCTION: Static file serving, proper error handling, health checks
"""

import logging
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import aiofiles

# Import our business logic services
from services import (
    OCRProcessingService, 
    ExpenseManager, 
    DraftManager, 
    CategoryManager
)
from database import DatabaseManager

# ============================================================================
# APPLICATION CONFIGURATION & SETUP
# ============================================================================

# Configure logging for development and production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="Expense Tracker API",
    description="Personal expense tracking with OCR receipt processing",
    version="1.0.0",
    docs_url="/docs",  # Swagger documentation
    redoc_url="/redoc"  # ReDoc documentation
)

# CORS configuration for development (remote VS Code) and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on deployment environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database and service initialization
db_manager = DatabaseManager('expenses.db')
expense_manager = ExpenseManager('expenses.db')
draft_manager = DraftManager('expenses.db')
category_manager = CategoryManager('expenses.db')
ocr_service = OCRProcessingService()

# ============================================================================
# APPLICATION LIFECYCLE EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Initialize application on startup.
    
    AI CONTEXT: This runs once when the server starts.
    Initializes database schema and prepares services.
    """
    try:
        await db_manager.initialize_database()
        logger.info("✅ Database initialized successfully")
        logger.info("🚀 Expense Tracker API started")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of application resources."""
    logger.info("🛑 Expense Tracker API shutting down")

# ============================================================================
# FRONTEND SERVING (Development & Production)
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """
    Serve the main HTML interface.
    
    AI CONTEXT: Serves index.html from frontend/ directory.
    In production, this might be handled by Nginx/reverse proxy.
    """
    try:
        async with aiofiles.open('frontend/index.html', mode='r', encoding='utf-8') as f:
            content = await f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        logger.error("Frontend index.html not found")
        return HTMLResponse(
            content="<h1>Expense Tracker</h1><p>Frontend file not found.</p>", 
            status_code=404
        )

# Mount static files (CSS, JS, images)
try:
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
    logger.info("📁 Static files mounted from frontend/ directory")
except Exception as e:
    logger.warning(f"⚠️ Could not mount static files: {e}")

# ============================================================================
# IMAGE UPLOAD & OCR PROCESSING ENDPOINTS
# ============================================================================

@app.post("/upload-images")
async def upload_images(files: List[UploadFile] = File(...)):
    """
    Upload receipt images, process with OCR, and create drafts.
    
    AI CONTEXT: Main entry point for receipt processing workflow.
    1. Accepts multiple image files
    2. Processes each with OCR (services.py)
    3. Creates draft expenses for user review
    
    RETURNS: Upload group ID and count of drafts created
    """
    import uuid
    
    upload_group_id = str(uuid.uuid4())
    draft_ids = []
    
    for file in files:
        if not file.content_type.startswith('image/'):
            logger.warning(f"Skipping non-image file: {file.filename}")
            continue
        
        try:
            # Read image data
            image_bytes = await file.read()
            
            # Process with OCR service
            parsed_results = await ocr_service.process_image(image_bytes)
            
            if not parsed_results:
                logger.warning(f"No data extracted from {file.filename}")
                continue

            # Create draft for each parsed expense
            for data in parsed_results:
                draft_id = await draft_manager.save_draft(
                    upload_group_id, data, image_bytes, file.filename
                )
                draft_ids.append(draft_id)
                
        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")

    logger.info(f"Upload complete: {len(draft_ids)} drafts created")
    return {"upload_group_id": upload_group_id, "drafts_created": len(draft_ids)}

# ============================================================================
# DRAFT MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/drafts")
async def get_drafts():
    """Get all pending draft expenses."""
    return await draft_manager.get_all_drafts()

@app.get("/drafts/{draft_id}")
async def get_draft(draft_id: int):
    """Get specific draft by ID for editing/review."""
    draft = await draft_manager.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@app.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: int,
    date: str = Form(''),
    amount: float = Form(0),
    currency: str = Form('EUR'),
    fx_rate: float = Form(1.0),
    amount_eur: float = Form(0),
    description: str = Form(''),
    category: str = Form('Other'),
    person: str = Form(''),
    beneficiary: str = Form('')
):
    """
    Update draft with new data (auto-save functionality).
    
    AI CONTEXT: Called automatically as user edits draft forms.
    Does not validate - just saves current state for later confirmation.
    """
    draft_data = {
        'date': date, 'amount': amount, 'currency': currency, 'fx_rate': fx_rate,
        'amount_eur': amount_eur, 'description': description, 'category': category,
        'person': person, 'beneficiary': beneficiary
    }
    
    success = await draft_manager.update_draft(draft_id, draft_data)
    if not success:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    return {"success": True, "id": draft_id}

@app.post("/drafts/{draft_id}/confirm")
async def confirm_draft(draft_id: int, **form_data):
    """
    Convert draft to permanent expense with validation.
    
    AI CONTEXT: Final step in draft workflow. Validates data and creates expense.
    If validation fails, marks draft with error for user to fix.
    """
    # This endpoint accepts all form fields as the original did
    # Business logic and validation handled in services.py
    return await draft_manager.confirm_draft_endpoint(draft_id, form_data)

@app.post("/drafts/bulk-confirm")
async def bulk_confirm_drafts(draft_ids: List[int] = Form(...)):
    """Confirm multiple drafts at once with partial success handling."""
    return await draft_manager.bulk_confirm_drafts(draft_ids)

@app.post("/drafts/{draft_id}/clear-error")
async def clear_draft_error(draft_id: int):
    """Clear error state from a draft."""
    success = await draft_manager.clear_draft_error(draft_id)
    if not success:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"success": True, "message": "Error state cleared"}

@app.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: int):
    """Delete (dismiss) a draft."""
    success = await draft_manager.delete_draft(draft_id)
    if not success:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"success": True, "message": "Draft deleted"}

@app.get("/drafts/{draft_id}/image")
async def get_draft_image(draft_id: int):
    """Get image associated with a draft."""
    image_data, filename = await draft_manager.get_draft_image(draft_id)
    if not image_data:
        raise HTTPException(status_code=404, detail="Image not found")
    
    ext = (filename.lower().split('.')[-1] if filename and '.' in filename else 'jpeg')
    return Response(content=image_data, media_type=f'image/{ext}')

# ============================================================================
# EXPENSE MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/expenses")
async def get_expenses():
    """Get all confirmed expenses."""
    return await expense_manager.get_all_expenses()

@app.get("/expense/{expense_id}")
async def get_expense(expense_id: int):
    """Get specific expense by ID."""
    expense = await expense_manager.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense

@app.put("/expense/{expense_id}")
async def update_expense(expense_id: int, **form_data):
    """Update existing expense with validation."""
    # Business logic handled in services.py
    return await expense_manager.update_expense_endpoint(expense_id, form_data)

@app.delete("/expense/{expense_id}")
async def delete_expense(expense_id: int):
    """Delete specific expense."""
    success = await expense_manager.delete_expense(expense_id)
    if not success:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"success": True, "message": "Expense deleted"}

@app.delete("/expenses/bulk")
async def bulk_delete_expenses(expense_ids: List[int] = Form(...)):
    """Delete multiple expenses at once."""
    if not expense_ids:
        raise HTTPException(status_code=400, detail="No expense IDs provided")
    
    deleted_count = await expense_manager.bulk_delete_expenses(expense_ids)
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="No expenses found")
    
    return {"success": True, "deleted_count": deleted_count}

@app.get("/expense/{expense_id}/image")
async def get_expense_image(expense_id: int):
    """Get image associated with an expense."""
    image_data, filename = await expense_manager.get_expense_image(expense_id)
    if not image_data:
        raise HTTPException(status_code=404, detail="Image not found")
    
    ext = (filename.lower().split('.')[-1] if filename and '.' in filename else 'jpeg')
    return Response(content=image_data, media_type=f'image/{ext}')

@app.get("/expense/{expense_id}/audit")
async def get_expense_audit_history(expense_id: int):
    """Get audit trail for specific expense."""
    audit_history = await expense_manager.get_expense_audit_history(expense_id)
    return {"success": True, "expense_id": expense_id, "audit_history": audit_history}

# ============================================================================
# CATEGORY MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/categories")
async def get_categories():
    """Get all available expense categories."""
    return await category_manager.get_all_categories()

@app.post("/add-category")
async def add_category(name: str = Form(...)):
    """Add new expense category."""
    success = await category_manager.add_category(name)
    if success:
        return {"success": True}
    else:
        return {"success": False, "detail": "Category already exists"}

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/fx-rate/{currency}")
async def get_fx_rate(currency: str, date: str = Query(None)):
    """Get exchange rate for currency on specific date."""
    rate = await ocr_service.get_fx_rate(currency, date)
    return {
        "currency": currency, 
        "rate": rate, 
        "date": date or "today"
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and deployment.
    
    AI CONTEXT: Used by Docker health checks and load balancers.
    Returns application status and database connectivity.
    """
    try:
        # Basic database connectivity check
        categories = await category_manager.get_all_categories()
        return {
            "status": "healthy",
            "database": "connected",
            "categories_count": len(categories),
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

# ============================================================================
# ERROR HANDLING
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for production error logging.
    
    AI CONTEXT: Catches unhandled exceptions and logs them properly.
    In development, shows full stack trace. In production, returns generic error.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return Response(
        content="Internal server error", 
        status_code=500,
        media_type="text/plain"
    )

# ============================================================================
# DEVELOPMENT HELPERS
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    # AI CONTEXT: Only runs when file is executed directly
    # In production, use gunicorn or similar WSGI server
    uvicorn.run(
        "app:app",
        host="0.0.0.0",  # Allow external connections (remote VS Code)
        port=8000,
        reload=True,     # Auto-reload on file changes
        log_level="info"
    )