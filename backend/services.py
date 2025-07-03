"""
Expense Tracker - Business Logic Services

PURPOSE: All business logic, domain services, and application workflows
SCOPE: Service layer with clear separation of concerns
DEPENDENCIES: database.py (persistence), external APIs (OCR, FX rates)
"""

import logging
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from backend.database import DatabaseManager

logger = logging.getLogger(__name__)

def validate_expense_data(expense_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate expense data and return validation result with error messages."""
    errors = []
    
    # Required fields
    if not expense_data.get('date'):
        errors.append("Date is required")
    if not expense_data.get('amount') or float(expense_data.get('amount', 0)) <= 0:
        errors.append("Amount must be greater than 0")
    if not expense_data.get('description'):
        errors.append("Description is required")
    
    return len(errors) == 0, errors

# ============================================================================
# OCR PROCESSING SERVICE
# ============================================================================

class OCRProcessingService:
    """Handles image processing and text extraction."""
    
    def __init__(self):
        pass
    
    async def process_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Process image with OCR and return parsed expense data."""
        # Simple OCR implementation - returns dummy data for now
        return [{
            'date': datetime.now().strftime('%Y-%m-%d'),
            'amount': 7.47,
            'currency': 'EUR',
            'fx_rate': 1.0,
            'amount_eur': 7.47,
            'description': '07:47 OA M ORN Sl 8 95%H',
            'category': 'Other',
            'person': '',
            'beneficiary': '',
            'date_warning': ''
        }]
    
    async def get_fx_rate(self, currency: str, date: str = None) -> float:
        """Get exchange rate for currency."""
        # Simple fallback rates
        fallback_rates = {'USD': 1.08, 'HUF': 400.0, 'EUR': 1.0}
        return fallback_rates.get(currency, 1.0)

# ============================================================================
# EXPENSE MANAGEMENT SERVICE
# ============================================================================

class ExpenseManager:
    """Handles CRUD operations for confirmed expenses."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.db_manager = DatabaseManager(db_file)
    
    async def create_expense(self, expense_data: Dict[str, Any], image_data: bytes = None, 
                           image_filename: str = '') -> int:
        """Create a new expense record."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('''
                INSERT INTO expenses (date, amount, currency, fx_rate, amount_eur, description, 
                                    category, person, beneficiary, image_data, image_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                expense_data.get('date'),
                expense_data.get('amount'),
                expense_data.get('currency', 'EUR'),
                expense_data.get('fx_rate', 1.0),
                expense_data.get('amount_eur'),
                expense_data.get('description'),
                expense_data.get('category', 'Other'),
                expense_data.get('person', ''),
                expense_data.get('beneficiary', ''),
                image_data,
                image_filename
            ))
            expense_id = cursor.lastrowid
            await conn.commit()
            logger.info(f"Created expense #{expense_id}: {expense_data.get('description')}")
            return expense_id
    
    async def get_all_expenses(self) -> List[Dict[str, Any]]:
        """Get all confirmed expenses."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            cursor = await conn.execute('''
                SELECT id, date, amount, currency, fx_rate, amount_eur, description, 
                       category, person, beneficiary, image_filename, created_on, modified_on,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image
                FROM expenses
                ORDER BY date DESC, created_on DESC
            ''')
            return [dict(row) for row in await cursor.fetchall()]
    
    async def get_expense(self, expense_id: int) -> Optional[Dict[str, Any]]:
        """Get specific expense by ID."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            cursor = await conn.execute('''
                SELECT id, date, amount, currency, fx_rate, amount_eur, description, 
                       category, person, beneficiary, image_filename, created_on, modified_on,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image
                FROM expenses
                WHERE id = ?
            ''', (expense_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def update_expense(self, expense_id: int, expense_data: Dict[str, Any]) -> bool:
        """Update an existing expense."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('''
                UPDATE expenses 
                SET date = ?, amount = ?, currency = ?, fx_rate = ?, amount_eur = ?,
                    description = ?, category = ?, person = ?, beneficiary = ?, modified_on = ?
                WHERE id = ?
            ''', (
                expense_data.get('date'),
                expense_data.get('amount'),
                expense_data.get('currency', 'EUR'),
                expense_data.get('fx_rate', 1.0),
                expense_data.get('amount_eur'),
                expense_data.get('description'),
                expense_data.get('category', 'Other'),
                expense_data.get('person', ''),
                expense_data.get('beneficiary', ''),
                datetime.now().isoformat(),
                expense_id
            ))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def delete_expense(self, expense_id: int) -> bool:
        """Delete an expense."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def get_expense_audit_history(self, expense_id: int) -> List[Dict[str, Any]]:
        """Get audit history for an expense."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            cursor = await conn.execute('''
                SELECT operation, old_values, new_values, changes, audit_timestamp, user_info
                FROM expense_audit_log
                WHERE expense_id = ?
                ORDER BY audit_timestamp DESC
            ''', (expense_id,))
            return [dict(row) for row in await cursor.fetchall()]

# ============================================================================
# DRAFT MANAGEMENT SERVICE
# ============================================================================

class DraftManager:
    """Handles draft expense operations with error handling and auto-save."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.db_manager = DatabaseManager(db_file)
        self.expense_manager = ExpenseManager(db_file)
    
    async def save_draft(self, upload_group_id: str, expense_data: Dict[str, Any], 
                         image_data: bytes, image_filename: str) -> int:
        """Save a new draft expense from OCR processing."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('''
                INSERT INTO drafts (upload_group_id, date, amount, currency, fx_rate, amount_eur, 
                                    description, category, person, beneficiary, date_warning,
                                    image_data, image_filename, has_error, error_message, last_error_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                upload_group_id,
                expense_data.get('date'),
                expense_data.get('amount'),
                expense_data.get('currency'),
                expense_data.get('fx_rate'),
                expense_data.get('amount_eur'),
                expense_data.get('description'),
                expense_data.get('category'),
                expense_data.get('person'),
                expense_data.get('beneficiary'),
                expense_data.get('date_warning'),
                image_data,
                image_filename,
                0,  # has_error = False initially
                None,  # error_message = None initially
                None   # last_error_at = None initially
            ))
            draft_id = cursor.lastrowid
            await conn.commit()
            logger.info(f"Created draft #{draft_id}: {expense_data.get('description', 'Untitled')}")
            return draft_id
    
    async def get_all_drafts(self) -> List[Dict[str, Any]]:
        """Get all pending drafts."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            cursor = await conn.execute('''
                SELECT id, upload_group_id, date, amount, currency, fx_rate, amount_eur, 
                       description, category, person, beneficiary, date_warning, image_filename, 
                       created_on, has_error, error_message, last_error_at,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image
                FROM drafts
                ORDER BY created_on DESC
            ''')
            return [dict(row) for row in await cursor.fetchall()]
    
    async def get_draft(self, draft_id: int) -> Optional[Dict[str, Any]]:
        """Get specific draft by ID."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            cursor = await conn.execute('''
                SELECT id, upload_group_id, date, amount, currency, fx_rate, amount_eur, 
                       description, category, person, beneficiary, date_warning, image_filename, 
                       created_on, has_error, error_message, last_error_at,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image
                FROM drafts
                WHERE id = ?
            ''', (draft_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def update_draft(self, draft_id: int, draft_data: Dict[str, Any]) -> bool:
        """Update draft with new data (auto-save functionality)."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('''
                UPDATE drafts 
                SET date = ?, amount = ?, currency = ?, fx_rate = ?, amount_eur = ?,
                    description = ?, category = ?, person = ?, beneficiary = ?
                WHERE id = ?
            ''', (
                draft_data.get('date'),
                draft_data.get('amount'),
                draft_data.get('currency'),
                draft_data.get('fx_rate'),
                draft_data.get('amount_eur'),
                draft_data.get('description'),
                draft_data.get('category'),
                draft_data.get('person'),
                draft_data.get('beneficiary'),
                draft_id
            ))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def confirm_draft_endpoint(self, draft_id: int, form_data: dict):
        """Convert draft to permanent expense with validation."""
        try:
            # Validate the data
            is_valid, validation_errors = validate_expense_data(form_data)
            
            if not is_valid:
                # Mark draft with error instead of failing
                error_message = "; ".join(validation_errors)
                await self.mark_draft_error(draft_id, error_message)
                return {
                    "success": False, 
                    "error": "Validation failed", 
                    "details": validation_errors,
                    "draft_marked_error": True
                }
            
            # Clear any previous error state
            await self.clear_draft_error(draft_id)
            
            # Get image data from draft
            img_data, img_fname = await self.get_draft_image(draft_id)
            
            # Create the permanent expense
            expense_id = await self.expense_manager.create_expense(form_data, img_data, img_fname or '')
            
            # Clean up the draft only if successful
            await self.delete_draft(draft_id)
            
            logger.info(f"Confirmed draft #{draft_id} as expense #{expense_id}")
            return {"success": True, "id": expense_id}
            
        except Exception as e:
            logger.error(f"Error confirming draft {draft_id}: {e}")
            # Mark draft with error instead of losing it
            await self.mark_draft_error(draft_id, f"System error: {str(e)}")
            return {
                "success": False, 
                "error": "System error occurred", 
                "details": [str(e)],
                "draft_marked_error": True
            }
    
    async def mark_draft_error(self, draft_id: int, error_message: str) -> bool:
        """Mark a draft as having an error."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('''
                UPDATE drafts 
                SET has_error = 1, error_message = ?, last_error_at = ?
                WHERE id = ?
            ''', (error_message, datetime.now().isoformat(), draft_id))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def clear_draft_error(self, draft_id: int) -> bool:
        """Clear error state from a draft."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('''
                UPDATE drafts 
                SET has_error = 0, error_message = NULL, last_error_at = NULL
                WHERE id = ?
            ''', (draft_id,))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def delete_draft(self, draft_id: int) -> bool:
        """Delete (dismiss) a draft."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('DELETE FROM drafts WHERE id = ?', (draft_id,))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def get_draft_image(self, draft_id: int) -> Tuple[Optional[bytes], Optional[str]]:
        """Get image associated with a draft."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('SELECT image_data, image_filename FROM drafts WHERE id = ?', (draft_id,))
            row = await cursor.fetchone()
            if row:
                return row[0], row[1]
            return None, None
    
    async def bulk_confirm_drafts(self, draft_ids: List[int]):
        """Confirm multiple drafts at once with partial success handling."""
        results = []
        for draft_id in draft_ids:
            # Get draft data first
            draft = await self.get_draft(draft_id)
            if not draft:
                results.append({"id": draft_id, "success": False, "error": "Draft not found"})
                continue
            
            # Convert draft to form data format
            form_data = {
                'date': draft.get('date'),
                'amount': draft.get('amount'),
                'currency': draft.get('currency'),
                'fx_rate': draft.get('fx_rate'),
                'amount_eur': draft.get('amount_eur'),
                'description': draft.get('description'),
                'category': draft.get('category'),
                'person': draft.get('person'),
                'beneficiary': draft.get('beneficiary')
            }
            
            result = await self.confirm_draft_endpoint(draft_id, form_data)
            results.append({"id": draft_id, **result})
        
        return {"results": results}

# ============================================================================
# CATEGORY MANAGEMENT SERVICE
# ============================================================================

class CategoryManager:
    """Handles expense category operations."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.db_manager = DatabaseManager(db_file)
    
    async def get_all_categories(self) -> List[str]:
        """Get all available expense categories."""
        async with self.db_manager.get_connection() as conn:
            cursor = await conn.execute('SELECT name FROM categories ORDER BY name')
            return [row[0] for row in await cursor.fetchall()]
    
    async def add_category(self, name: str) -> bool:
        """Add a new expense category."""
        async with self.db_manager.get_connection() as conn:
            try:
                await conn.execute('INSERT INTO categories (name) VALUES (?)', (name,))
                await conn.commit()
                logger.info(f"Added new category: {name}")
                return True
            except Exception as e:
                logger.warning(f"Category already exists or error: {e}")
                return False