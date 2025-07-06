"""
Expense Tracker - Main FastAPI Application

PURPOSE: FastAPI routes, endpoints, and application setup
SCOPE: HTTP API layer and request/response handling
DEPENDENCIES: FastAPI, all backend modules
"""

import uuid
import logging
import aiofiles
from datetime import datetime
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import config
from .database import DatabaseManager
from .ocr_processor import OCRProcessingService
from .managers import ExpenseManager, DraftManager, CategoryManager
from .validators import validate_expense_data, sanitize_form_data

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Expense Tracker")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Initialize service instances
db_manager = DatabaseManager(config.DB_FILE)
expense_manager = ExpenseManager(config.DB_FILE)
draft_manager = DraftManager(config.DB_FILE)
category_manager = CategoryManager(config.DB_FILE)
ocr_service = OCRProcessingService()


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    await db_manager.initialize_database()
    logger.info("Database initialized successfully.")


# ============================================================================
# FRONTEND ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main HTML interface."""
    try:
        async with aiofiles.open('frontend/index.html', mode='r', encoding='utf-8') as f:
            content = await f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Expense Tracker</h1><p>Frontend file not found.</p>", 
            status_code=404
        )


# ============================================================================
# OCR AND IMAGE UPLOAD ENDPOINTS
# ============================================================================

@app.post("/upload-images")
async def upload_images(files: List[UploadFile] = File(...)):
    """Upload images, process with OCR, and save as drafts."""
    upload_group_id = str(uuid.uuid4())
    draft_ids = []
    
    for file in files:
        if not file.content_type.startswith('image/'):
            continue
        
        try:
            image_bytes = await file.read()
            parsed_results = await ocr_service.process_image(image_bytes)
            
            if not parsed_results:
                logger.warning(f"Could not extract any data from {file.filename}")
                continue

            for data in parsed_results:
                draft_id = await draft_manager.save_draft(
                    upload_group_id, data, image_bytes, file.filename
                )
                draft_ids.append(draft_id)
                
        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")

    return {"upload_group_id": upload_group_id, "drafts_created": len(draft_ids)}


# ============================================================================
# DRAFT MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/drafts")
async def get_drafts():
    """Get all pending drafts."""
    return await draft_manager.get_all_drafts()


@app.get("/drafts/{draft_id}")
async def get_draft(draft_id: int):
    """Get full details for a single draft."""
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
    """Update a draft with new data (for auto-saving)."""
    draft_data = sanitize_form_data({
        'date': date,
        'amount': amount,
        'currency': currency,
        'fx_rate': fx_rate,
        'amount_eur': amount_eur,
        'description': description,
        'category': category,
        'person': person,
        'beneficiary': beneficiary
    })
    
    success = await draft_manager.update_draft(draft_id, draft_data)
    if not success:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    return {"success": True, "id": draft_id}


@app.post("/drafts/{draft_id}/confirm")
async def confirm_draft(
    draft_id: int, 
    date: str = Form(...), 
    amount: float = Form(...), 
    currency: str = Form(...), 
    fx_rate: float = Form(...), 
    amount_eur: float = Form(...), 
    description: str = Form(...), 
    category: str = Form(...), 
    person: str = Form(...), 
    beneficiary: str = Form('')
):
    """Convert a draft to a permanent expense record with error handling."""
    try:
        # Prepare expense data
        expense_data = sanitize_form_data({
            'date': date, 'amount': amount, 'currency': currency, 'fx_rate': fx_rate,
            'amount_eur': amount_eur, 'description': description, 'category': category,
            'person': person, 'beneficiary': beneficiary
        })
        
        # Validate the data
        is_valid, validation_errors = validate_expense_data(expense_data)
        
        if not is_valid:
            # Mark draft with error instead of failing
            error_message = "; ".join(validation_errors)
            await draft_manager.mark_draft_error(draft_id, error_message)
            return {
                "success": False, 
                "error": "Validation failed", 
                "details": validation_errors,
                "draft_marked_error": True
            }
        
        # Clear any previous error state
        await draft_manager.clear_draft_error(draft_id)
        
        # Get image data from draft
        img_data, img_fname = await draft_manager.get_draft_image(draft_id)
        
        # Create the permanent expense
        expense_id = await expense_manager.create_expense(expense_data, img_data, img_fname or '')
        
        # Clean up the draft only if successful
        await draft_manager.delete_draft(draft_id)
        
        return {"success": True, "id": expense_id}
        
    except Exception as e:
        logger.error(f"Error confirming draft {draft_id}: {e}")
        # Mark draft with error instead of losing it
        await draft_manager.mark_draft_error(draft_id, f"System error: {str(e)}")
        return {
            "success": False, 
            "error": "System error occurred", 
            "details": [str(e)],
            "draft_marked_error": True
        }


@app.post("/drafts/bulk-confirm")
async def bulk_confirm_drafts(draft_ids: List[int] = Form(...)):
    """Bulk confirm multiple drafts with partial success handling."""
    if not draft_ids:
        raise HTTPException(status_code=400, detail="No draft IDs provided")
    
    results = {
        "success_count": 0,
        "error_count": 0,
        "errors": [],
        "success_ids": [],
        "error_ids": []
    }
    
    for draft_id in draft_ids:
        try:
            # Get draft data
            draft_data = await draft_manager.get_draft(draft_id)
            if not draft_data:
                results["error_count"] += 1
                results["errors"].append(f"Draft {draft_id} not found")
                results["error_ids"].append(draft_id)
                continue
            
            # Validate the data
            expense_data = {
                'date': draft_data.get('date', ''),
                'amount': draft_data.get('amount', 0),
                'currency': draft_data.get('currency', 'EUR'),
                'fx_rate': draft_data.get('fx_rate', 1.0),
                'amount_eur': draft_data.get('amount_eur', 0),
                'description': draft_data.get('description', ''),
                'category': draft_data.get('category', 'Other'),
                'person': draft_data.get('person', ''),
                'beneficiary': draft_data.get('beneficiary', '')
            }
            
            is_valid, validation_errors = validate_expense_data(expense_data)
            
            if not is_valid:
                # Mark draft with error instead of failing
                error_message = "; ".join(validation_errors)
                await draft_manager.mark_draft_error(draft_id, error_message)
                results["error_count"] += 1
                results["errors"].append(f"Draft {draft_id}: {error_message}")
                results["error_ids"].append(draft_id)
                continue
            
            # Clear any previous error state
            await draft_manager.clear_draft_error(draft_id)
            
            # Get image data from draft
            img_data, img_fname = await draft_manager.get_draft_image(draft_id)
            
            # Create the permanent expense
            expense_id = await expense_manager.create_expense(expense_data, img_data, img_fname or '')
            
            # Clean up the draft only if successful
            await draft_manager.delete_draft(draft_id)
            
            results["success_count"] += 1
            results["success_ids"].append(draft_id)
            
        except Exception as e:
            logger.error(f"Error confirming draft {draft_id}: {e}")
            # Mark draft with error instead of losing it
            await draft_manager.mark_draft_error(draft_id, f"System error: {str(e)}")
            results["error_count"] += 1
            results["errors"].append(f"Draft {draft_id}: System error - {str(e)}")
            results["error_ids"].append(draft_id)
    
    return results


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
        raise HTTPException(status_code=404, detail=f"Draft with ID {draft_id} not found.")
    return {"success": True, "detail": f"Draft with ID {draft_id} has been deleted."}


@app.get("/drafts/{draft_id}/image")
async def get_draft_image(draft_id: int):
    """Get the image associated with a draft."""
    image_data, filename = await draft_manager.get_draft_image(draft_id)
    if not image_data:
        raise HTTPException(status_code=404, detail="Image not found for this draft")
    
    # Fix: Complete the truncated line
    ext = (filename.lower().split('.')[-1] if filename and '.' in filename else 'jpeg')
    return Response(content=image_data, media_type=f'image/{ext}')


# ============================================================================
# EXPENSE MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/expenses")
async def get_expenses():
    """Get all expenses."""
    return await expense_manager.get_all_expenses()


@app.get("/expense/{expense_id}")
async def get_expense(expense_id: int):
    """Get a specific expense by ID."""
    expense = await expense_manager.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@app.put("/expense/{expense_id}")
async def update_expense(
    expense_id: int, 
    date: str = Form(...), 
    amount: float = Form(...), 
    currency: str = Form(...), 
    fx_rate: float = Form(...), 
    amount_eur: float = Form(...), 
    description: str = Form(...), 
    category: str = Form(...), 
    person: str = Form(...), 
    beneficiary: str = Form('')
):
    """Update an existing expense."""
    expense_data = sanitize_form_data({
        'date': date, 'amount': amount, 'currency': currency, 'fx_rate': fx_rate,
        'amount_eur': amount_eur, 'description': description, 'category': category,
        'person': person, 'beneficiary': beneficiary
    })
    
    # Validate the data
    is_valid, validation_errors = validate_expense_data(expense_data)
    if not is_valid:
        raise HTTPException(status_code=400, detail={"errors": validation_errors})
    
    success = await expense_manager.update_expense(expense_id, expense_data)
    if not success:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    return {"success": True, "id": expense_id}


@app.delete("/expense/{expense_id}")
async def delete_expense(expense_id: int):
    """Delete a specific expense."""
    success = await expense_manager.delete_expense(expense_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Expense with ID {expense_id} not found.")
    
    return {"success": True, "detail": f"Expense with ID {expense_id} has been deleted."}


@app.delete("/expenses/bulk")
async def bulk_delete_expenses(expense_ids: List[int] = Form(...)):
    """Delete multiple expenses at once."""
    if not expense_ids:
        raise HTTPException(status_code=400, detail="No expense IDs provided")
    
    deleted_count = await expense_manager.bulk_delete_expenses(expense_ids)
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="No expenses found with the provided IDs")
    
    return {"success": True, "deleted_count": deleted_count}


@app.get("/expense/{expense_id}/audit")
async def get_expense_audit_history_endpoint(expense_id: int):
    """Get audit history for a specific expense."""
    audit_history = await expense_manager.get_expense_audit_history(expense_id)
    return {"success": True, "expense_id": expense_id, "audit_history": audit_history}


@app.get("/expense/{expense_id}/image")
async def get_expense_image(expense_id: int):
    """Get the image associated with an expense."""
    image_data, filename = await expense_manager.get_expense_image(expense_id)
    if not image_data:
        raise HTTPException(status_code=404, detail="Image not found")
    
    ext = (filename.lower().split('.')[-1] if filename and '.' in filename else 'jpeg')
    return Response(content=image_data, media_type=f'image/{ext}')


# ============================================================================
# CATEGORY MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/categories")
async def get_categories():
    """Get all available expense categories."""
    return await category_manager.get_all_categories()


@app.post("/add-category")
async def add_category(name: str = Form(...)):
    """Add a new expense category."""
    success = await category_manager.add_category(name.strip())
    if success:
        return {"success": True}
    else:
        return {"success": False, "detail": "Category already exists."}


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/fx-rate/{currency}")
async def get_fx_rate_endpoint(currency: str, date: str = Query(None)):
    """Get exchange rate for a currency on a specific date."""
    rate = await ocr_service._get_fx_rate(currency, date)
    return {
        "currency": currency, 
        "rate": rate, 
        "date": date or datetime.now().strftime('%Y-%m-%d')
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)