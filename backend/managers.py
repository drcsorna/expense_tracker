"""
Expense Tracker - Data Managers

PURPOSE: Data access layer for expenses, drafts, and categories
SCOPE: CRUD operations, data validation, and business logic
DEPENDENCIES: aiosqlite, json, datetime
"""

import json
import sqlite3
import aiosqlite
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from .config import config

logger = logging.getLogger(__name__)


class ExpenseManager:
    """Handles expense CRUD operations and data management."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
    
    async def create_expense(self, expense_data: Dict[str, Any], image_data: bytes = None, 
                           image_filename: str = '') -> int:
        """Create a new expense record."""
        async with aiosqlite.connect(self.db_file) as conn:
            values = self._prepare_expense_values(expense_data, include_timestamps=True)
            
            cursor = await conn.execute('''
                INSERT INTO expenses (date, amount, currency, fx_rate, amount_eur, description, 
                                    category, person, beneficiary, image_data, image_filename, 
                                    created_on, modified_on)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                values['date'], values['amount'], values['currency'], values['fx_rate'],
                values['amount_eur'], values['description'], values['category'], 
                values['person'], values['beneficiary'], image_data, image_filename or '',
                values['created_on'], values['modified_on']
            ))
            
            expense_id = cursor.lastrowid
            await conn.commit()
            
            # Log audit entry
            audit_values = values.copy()
            audit_values.update({'image_filename': image_filename or '', 'has_image': bool(image_data)})
            await self._log_audit(expense_id, 'INSERT', None, audit_values)
            
            return expense_id
    
    async def update_expense(self, expense_id: int, expense_data: Dict[str, Any]) -> bool:
        """Update an existing expense record."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Get old values for audit
            cursor = await conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,))
            old_row = await cursor.fetchone()
            if not old_row:
                return False
            
            old_values = self._sanitize_expense_data(dict(old_row))
            new_values = self._prepare_expense_values(expense_data)
            new_values['modified_on'] = self._get_current_timestamp()

            # Update the record
            await conn.execute('''
                UPDATE expenses SET date=?, amount=?, currency=?, fx_rate=?, amount_eur=?, 
                                  description=?, category=?, person=?, beneficiary=?, modified_on=? 
                WHERE id=?
            ''', (
                new_values['date'], new_values['amount'], new_values['currency'], 
                new_values['fx_rate'], new_values['amount_eur'], new_values['description'], 
                new_values['category'], new_values['person'], new_values['beneficiary'], 
                new_values['modified_on'], expense_id
            ))
            
            await conn.commit()
            
            # Log audit entry
            await self._log_audit(expense_id, 'UPDATE', old_values, new_values)
            return True
    
    async def delete_expense(self, expense_id: int) -> bool:
        """Delete an expense record."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Get expense data for audit
            cursor = await conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,))
            expense_row = await cursor.fetchone()
            if not expense_row:
                return False
            
            deleted_values = self._sanitize_expense_data(dict(expense_row))
            
            # Delete the record
            await conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            await conn.commit()
            
            # Log audit entry
            await self._log_audit(expense_id, 'DELETE', deleted_values, None)
            return True
    
    async def bulk_delete_expenses(self, expense_ids: List[int]) -> int:
        """Delete multiple expense records."""
        if not expense_ids:
            return 0
        
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Get expenses for audit
            placeholders = ','.join('?' * len(expense_ids))
            cursor = await conn.execute(f"SELECT * FROM expenses WHERE id IN ({placeholders})", expense_ids)
            expenses_to_delete = [dict(row) for row in await cursor.fetchall()]
            
            if not expenses_to_delete:
                return 0
            
            # Delete the records
            query = f"DELETE FROM expenses WHERE id IN ({placeholders})"
            cursor = await conn.execute(query, expense_ids)
            deleted_count = cursor.rowcount
            await conn.commit()
            
            # Log audit entries
            for expense_data in expenses_to_delete:
                expense_id = expense_data['id']
                deleted_values = self._sanitize_expense_data(expense_data)
                await self._log_audit(expense_id, 'DELETE', deleted_values, None)
            
            return deleted_count
    
    async def get_expense(self, expense_id: int) -> Optional[Dict[str, Any]]:
        """Get a single expense by ID."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute('''
                SELECT id, date, amount, currency, fx_rate, amount_eur, description, 
                       category, person, beneficiary, image_filename, created_on, modified_on,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image_data 
                FROM expenses WHERE id = ?
            ''', (expense_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            expense_data = dict(row)
            sanitized = self._sanitize_expense_data(expense_data)
            sanitized['has_image'] = bool(expense_data.get('has_image_data', 0))
            return sanitized
    
    async def get_all_expenses(self) -> List[Dict[str, Any]]:
        """Get all expenses ordered by date and creation time."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute('''
                SELECT id, date, amount, currency, fx_rate, amount_eur, description, 
                       category, person, beneficiary, image_filename, created_on, modified_on,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image
                FROM expenses 
                ORDER BY date DESC, created_at DESC
            ''')
            
            return [self._sanitize_expense_data(dict(row)) for row in await cursor.fetchall()]
    
    async def get_expense_image(self, expense_id: int) -> Tuple[Optional[bytes], Optional[str]]:
        """Get expense image data and filename."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('SELECT image_data, image_filename FROM expenses WHERE id = ?', (expense_id,))
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)
    
    async def get_expense_audit_history(self, expense_id: int) -> List[Dict[str, Any]]:
        """Get audit history for a specific expense."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute('''
                SELECT id, expense_id, operation, old_values, new_values, changes, 
                       audit_timestamp, user_info
                FROM expense_audit_log 
                WHERE expense_id = ? 
                ORDER BY audit_timestamp DESC
            ''', (expense_id,))
            
            audit_entries = []
            for row in await cursor.fetchall():
                entry = {
                    'id': row['id'],
                    'expense_id': row['expense_id'],
                    'operation': row['operation'],
                    'audit_timestamp': row['audit_timestamp'],
                    'user_info': row['user_info']
                }
                
                # Parse JSON fields safely
                try:
                    entry['old_values'] = json.loads(row['old_values']) if row['old_values'] else None
                except (json.JSONDecodeError, TypeError):
                    entry['old_values'] = None
                
                try:
                    entry['new_values'] = json.loads(row['new_values']) if row['new_values'] else None
                except (json.JSONDecodeError, TypeError):
                    entry['new_values'] = None
                
                try:
                    entry['changes'] = json.loads(row['changes']) if row['changes'] else {}
                except (json.JSONDecodeError, TypeError):
                    entry['changes'] = {}
                
                audit_entries.append(entry)
            
            return audit_entries
    
    async def _log_audit(self, expense_id: int, operation: str, old_values: dict = None, 
                        new_values: dict = None, user_info: str = 'system'):
        """Log an audit entry for expense changes."""
        try:
            changes = {}
            if old_values and new_values:
                for key in new_values:
                    if key in old_values and old_values[key] != new_values[key]:
                        changes[key] = {'from': old_values[key], 'to': new_values[key]}
            
            async with aiosqlite.connect(self.db_file) as conn:
                await conn.execute('''
                    INSERT INTO expense_audit_log 
                    (expense_id, operation, old_values, new_values, changes, user_info) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    expense_id, operation, 
                    json.dumps(old_values) if old_values else None,
                    json.dumps(new_values) if new_values else None,
                    json.dumps(changes) if changes else None,
                    user_info
                ))
                await conn.commit()
                logger.info(f"Audit log created: expense_id={expense_id}, operation={operation}")
                
        except Exception as e:
            logger.error(f"Failed to log audit entry: {e}")
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        return datetime.now().isoformat()
    
    def _prepare_expense_values(self, form_data: dict, include_timestamps: bool = False) -> dict:
        """Prepare and validate expense values from form data."""
        values = {
            'date': form_data.get('date', ''),
            'amount': float(form_data.get('amount', 0)),
            'currency': form_data.get('currency', 'EUR'),
            'fx_rate': float(form_data.get('fx_rate', 1.0)),
            'amount_eur': float(form_data.get('amount_eur', 0)),
            'description': str(form_data.get('description', '')),
            'category': str(form_data.get('category', 'Other')),
            'person': str(form_data.get('person', '')),
            'beneficiary': str(form_data.get('beneficiary', ''))
        }
        
        if include_timestamps:
            current_time = self._get_current_timestamp()
            values['created_on'] = current_time
            values['modified_on'] = current_time
        
        return values
    
    def _sanitize_expense_data(self, row_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize and validate expense data from database."""
        sanitized = {
            'id': int(row_data.get('id', 0)),
            'date': str(row_data.get('date', '')),
            'amount': float(row_data.get('amount', 0.0)),
            'currency': str(row_data.get('currency', 'EUR')),
            'fx_rate': float(row_data.get('fx_rate', 1.0)),
            'amount_eur': float(row_data.get('amount_eur', 0.0)),
            'description': str(row_data.get('description', '')),
            'category': str(row_data.get('category', 'Other')),
            'person': str(row_data.get('person', '')),
            'beneficiary': str(row_data.get('beneficiary', '')),
            'has_image': bool(row_data.get('has_image') or row_data.get('image_filename')),
            'created_on': str(row_data.get('created_on', '')),
            'modified_on': str(row_data.get('modified_on', ''))
        }
        
        # Format timestamps for display
        for timestamp_field in ['created_on', 'modified_on']:
            if sanitized[timestamp_field]:
                try:
                    dt = datetime.fromisoformat(sanitized[timestamp_field].replace('Z', '+00:00'))
                    sanitized[timestamp_field] = dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, AttributeError):
                    pass
        
        return sanitized


class DraftManager:
    """Handles draft expense operations from OCR processing with error handling."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
    
    async def save_draft(self, upload_group_id: str, expense_data: Dict[str, Any], 
                         image_data: bytes, image_filename: str) -> int:
        """Save a new draft expense."""
        async with aiosqlite.connect(self.db_file) as conn:
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
            return draft_id

    async def update_draft(self, draft_id: int, draft_data: Dict[str, Any]) -> bool:
        """Update a draft with new data (for auto-saving functionality)."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('''
                UPDATE drafts 
                SET date=?, amount=?, currency=?, fx_rate=?, amount_eur=?, description=?, 
                    category=?, person=?, beneficiary=?
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

    async def get_all_drafts(self) -> List[Dict[str, Any]]:
        """Get all pending drafts."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
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
        """Get a single draft by ID for processing."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """SELECT id, upload_group_id, date, amount, currency, fx_rate, amount_eur, 
                          description, category, person, beneficiary, date_warning, image_filename, 
                          created_on, has_error, error_message, last_error_at,
                          CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image 
                   FROM drafts WHERE id = ?""", 
                (draft_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            
            # Convert row to a mutable dict and return (excluding binary image_data)
            return dict(row)
    
    async def mark_draft_error(self, draft_id: int, error_message: str) -> bool:
        """Mark a draft as having an error."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('''
                UPDATE drafts 
                SET has_error = 1, error_message = ?, last_error_at = ?
                WHERE id = ?
            ''', (error_message, datetime.now().isoformat(), draft_id))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def clear_draft_error(self, draft_id: int) -> bool:
        """Clear error state from a draft."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('''
                UPDATE drafts 
                SET has_error = 0, error_message = NULL, last_error_at = NULL
                WHERE id = ?
            ''', (draft_id,))
            await conn.commit()
            return cursor.rowcount > 0
            
    async def get_draft_image(self, draft_id: int) -> Tuple[Optional[bytes], Optional[str]]:
        """Get draft image data and filename."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('SELECT image_data, image_filename FROM drafts WHERE id = ?', (draft_id,))
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)
    
    async def delete_draft(self, draft_id: int) -> bool:
        """Delete a draft."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('DELETE FROM drafts WHERE id = ?', (draft_id,))
            await conn.commit()
            return cursor.rowcount > 0


class CategoryManager:
    """Handles expense category operations."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
    
    async def get_all_categories(self) -> List[str]:
        """Get all available expense categories."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute('SELECT name FROM categories ORDER BY name')
            return [row[0] for row in await cursor.fetchall()]
    
    async def add_category(self, name: str) -> bool:
        """Add a new expense category."""
        async with aiosqlite.connect(self.db_file) as conn:
            try:
                await conn.execute('INSERT INTO categories (name) VALUES (?)', (name,))
                await conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # Category already exists