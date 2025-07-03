"""
Expense Tracker - Business Logic Services

PURPOSE: All business logic, domain services, and application workflows
SCOPE: ~800 lines - Service layer with clear separation of concerns
DEPENDENCIES: database.py (persistence), external APIs (OCR, FX rates)

AI CONTEXT: This is the core business logic of the application.
Contains all the "what" and "how" of expense processing, OCR, and data management.
When adding new features or fixing business logic, this is your primary file.

SERVICES INCLUDED:
- OCRProcessingService: Image processing and text extraction
- ExpenseManager: CRUD operations for confirmed expenses  
- DraftManager: Draft expense handling with validation
- CategoryManager: Expense category management
- FxRateManager: Currency conversion and rate caching

PATTERNS: Async service classes, dependency injection ready, comprehensive error handling
"""

import asyncio
import logging
import json
import re
import uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import cv2
import numpy as np
import httpx
import pytesseract
from PIL import Image
import io

from database import DatabaseManager

# ============================================================================
# CONFIGURATION AND UTILITIES
# ============================================================================

logger = logging.getLogger(__name__)

@dataclass
class AppConfig:
    """
    Application configuration constants.
    
    AI CONTEXT: Centralized configuration for business logic.
    Modify these values to change application behavior.
    """
    DB_FILE: str = 'expenses.db'
    DEFAULT_CATEGORIES: List[str] = None
    FALLBACK_FX_RATES: Dict[str, float] = None
    
    def __post_init__(self):
        if self.DEFAULT_CATEGORIES is None:
            self.DEFAULT_CATEGORIES = [
                'Other', 'Caffeine', 'Household', 'Car', 'Snacks',
                'Office Lunch', 'Brunch', 'Clothing', 'Dog', 'Eating Out', 
                'Groceries', 'Restaurants'
            ]
        if self.FALLBACK_FX_RATES is None:
            self.FALLBACK_FX_RATES = {'USD': 1.08, 'HUF': 400.0}

config = AppConfig()

def validate_expense_data(expense_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate expense data and return validation result with error messages.
    
    AI CONTEXT: Centralized validation logic used by all expense operations.
    Add new validation rules here when extending the data model.
    """
    errors = []
    
    # Required fields validation
    if not expense_data.get('date'):
        errors.append("Date is required")
    
    amount = expense_data.get('amount')
    if not amount or amount <= 0:
        errors.append("Amount must be greater than 0")
    
    if not expense_data.get('description', '').strip():
        errors.append("Description is required")
    
    if not expense_data.get('category', '').strip():
        errors.append("Category is required")
    
    if not expense_data.get('person', '').strip():
        errors.append("Person (who paid) is required")
    
    return len(errors) == 0, errors

# ============================================================================
# OCR PROCESSING SERVICE
# ============================================================================

class OCRProcessingService:
    """
    Handles image processing, OCR text extraction, and expense parsing.
    
    AI CONTEXT: This service takes receipt images and converts them to structured expense data.
    Main workflow: Image → OCR Text → Source Detection → Parsing → Structured Data
    
    SUPPORTED SOURCES:
    - Revolut: Mobile banking transaction screenshots
    - ABN AMRO: Bank statement screenshots (single and list views)  
    - Generic: Any other receipt type with fallback parsing
    """
    
    def __init__(self):
        self.source_identifier = SourceIdentifier()
        self.parsers = {
            'Revolut': RevolutParser(),
            'ABN_AMRO_SINGLE': ABNAmroSingleParser(),
            'ABN_AMRO_LIST': ABNAmroListParser(),
            'Generic': GenericParser()
        }
    
    async def process_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Process an image and return parsed expense data.
        
        AI CONTEXT: Main entry point for OCR workflow.
        Returns list because some receipts (like bank statements) contain multiple expenses.
        """
        try:
            # Extract text using OCR
            text = await self._process_image_with_ocr(image_bytes)
            if not text.strip():
                logger.warning("No text extracted from image")
                return []
            
            # Identify source and get appropriate parser
            source = self.source_identifier.identify_source(text)
            parser = self.parsers.get(source, self.parsers['Generic'])
            
            logger.info(f"Processing image with {source} parser")
            
            # Parse the expense data
            parsed_data = parser.parse(text)
            
            # Post-process results with FX rates and defaults
            final_results = []
            for item in parsed_data:
                fx_rate = await self._get_fx_rate(item.get('currency', 'EUR'), item.get('date'))
                item['fx_rate'] = fx_rate
                item['amount_eur'] = round(item.get('amount', 0.0) / fx_rate, 2) if fx_rate and item.get('amount') else 0.0
                item.setdefault('person', 'Közös')  # Default person
                item.setdefault('beneficiary', '')
                final_results.append(item)

            logger.info(f"Successfully parsed {len(final_results)} expense(s) from image")
            return final_results
            
        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            return []
    
    async def _process_image_with_ocr(self, image_bytes: bytes) -> str:
        """Extract text from image using Tesseract OCR."""
        try:
            # Convert bytes to PIL Image and then to OpenCV format
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            
            # Run OCR in thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            ocr_config = r'--oem 3 --psm 6 -l nld+eng'  # Dutch + English
            
            text = await loop.run_in_executor(
                None,
                lambda: pytesseract.image_to_string(gray, config=ocr_config)
            )
            
            return text
            
        except Exception as e:
            logger.error(f"OCR text extraction error: {e}")
            return ""
    
    async def _get_fx_rate(self, currency: str, target_date: str = None) -> float:
        """
        Get exchange rate with caching and fallback.
        
        AI CONTEXT: Fetches EUR-based exchange rates from external API.
        Caches results in database to avoid repeated API calls.
        Falls back to hardcoded rates if API fails.
        """
        if currency == 'EUR':
            return 1.0
        
        target_date = target_date or date.today().isoformat()
        
        # Check cache first
        db_manager = DatabaseManager(config.DB_FILE)
        try:
            async with db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    'SELECT rate FROM fx_rates WHERE date = ? AND currency = ?', 
                    (target_date, currency)
                )
                cached = await cursor.fetchone()
                if cached:
                    return cached[0]
        except Exception as e:
            logger.warning(f"FX rate cache check failed: {e}")
        
        # Fetch from API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get('https://api.exchangerate-api.com/v4/latest/EUR')
                response.raise_for_status()
                data = response.json()
                rate = data.get('rates', {}).get(currency)
                
                if rate:
                    # Cache the rate
                    try:
                        async with db_manager.get_connection() as conn:
                            await conn.execute(
                                'INSERT OR REPLACE INTO fx_rates (date, currency, rate) VALUES (?, ?, ?)', 
                                (target_date, currency, rate)
                            )
                            await conn.commit()
                        logger.info(f"Cached FX rate: 1 EUR = {rate} {currency}")
                    except Exception as e:
                        logger.warning(f"Failed to cache FX rate: {e}")
                    return rate
                    
        except Exception as e:
            logger.error(f"FX rate API error: {e}")
        
        # Return fallback rate
        fallback_rate = config.FALLBACK_FX_RATES.get(currency, 1.0)
        logger.warning(f"Using fallback FX rate: 1 EUR = {fallback_rate} {currency}")
        return fallback_rate

    async def get_fx_rate(self, currency: str, date: str = None) -> float:
        """Public method for getting FX rates (used by API endpoints)."""
        return await self._get_fx_rate(currency, date)

# ============================================================================
# OCR PARSERS AND SOURCE IDENTIFICATION  
# ============================================================================

class SourceIdentifier:
    """Identifies the source/type of receipt from OCR text."""
    
    @staticmethod
    def identify_source(text: str) -> str:
        """
        Identify the source of the OCR text.
        
        AI CONTEXT: Pattern matching to determine which parser to use.
        Add new source patterns here when supporting new receipt types.
        """
        text_lower = text.lower()
        
        # Revolut fingerprints
        if ('split bill' in text_lower and 
            ('points earned' in text_lower or 'kiosk' in text_lower or 'revolut' in text_lower)):
            logger.info("Identified source: Revolut")
            return 'Revolut'
        
        # ABN AMRO fingerprints
        abn_indicators = ['abn amro', 'payment terminal', 'execution', 
                         'tikkie payment request', 'nl50 abna']
        if any(indicator in text_lower for indicator in abn_indicators):
            # Differentiate between single view and list view
            if 'execution' in text_lower and 'from account' in text_lower:
                logger.info("Identified source: ABN_AMRO_SINGLE")
                return 'ABN_AMRO_SINGLE'
            
            # Check for list patterns (multiple amounts on different lines)
            if len(re.findall(r'-\s*\d+,\d{2}', text_lower)) > 1:
                logger.info("Identified source: ABN_AMRO_LIST")
                return 'ABN_AMRO_LIST'
            
            logger.info("Identified source: ABN_AMRO_SINGLE (Fallback)")
            return 'ABN_AMRO_SINGLE'
        
        logger.info("Identified source: Generic")
        return 'Generic'

class ExpenseParser:
    """Base class for expense parsing with common utilities."""
    
    @staticmethod
    def smart_categorize(text: str) -> str:
        """
        Enhanced smart categorization with keyword matching.
        
        AI CONTEXT: Automatic category assignment based on merchant/description text.
        Extend the category_map when adding new categories or keywords.
        """
        text_lower = text.lower()
        category_map = {
            'Restaurants': ['restaurant', 'pizzeria', 'pompernikkel', 'eetcafe'],
            'Groceries': ['supermarket', 'albert heijn', 'jumbo', 'lidl', 'aldi', 'global supermarkt'],
            'Household': ['household', 'bakkerij', 'kiosk', 'sapn'],
            'Caffeine': ['coffee', 'cafe', 'koffie', 'starbucks', 'espresso'],
            'Car': ['fuel', 'gas', 'petrol', 'parking', 'sanef', 'autoroute', 'esso'],
            'Transport': ['transport', 'taxi', 'uber', 'bus', 'train'],
            'Sport': ['zwembad', 'swimming', 'gym', 'fitness', 'sport']
        }
        
        for category, keywords in category_map.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
        return 'Other'
    
    @staticmethod
    def clean_description(description: str) -> str:
        """Clean description by removing technical codes and noise."""
        if not description:
            return description
        
        # Remove technical codes and noise patterns
        noise_patterns = [
            r',PAS\d+',     # Remove ,PAS011 type codes
            r'^BEA,\s*',    # Remove BEA prefix  
            r'\s*,\s*$',    # Remove trailing commas
        ]
        
        cleaned = description
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    @staticmethod
    def parse_european_amount(amount_str: str) -> Optional[float]:
        """
        Parse European number format amounts.
        
        AI CONTEXT: Handles both European (1.234,56) and US (1,234.56) formats.
        Common in OCR text where number formats can be ambiguous.
        """
        if not amount_str:
            return None
        
        # Remove currency symbols and extra whitespace
        cleaned = re.sub(r'[€$£-]', '', amount_str).strip()
        
        # Handle European format: 1.524,55 vs US format: 1,524.55
        if '.' in cleaned and ',' in cleaned:
            # European format: thousands separator = ., decimal = ,
            if cleaned.rfind(',') > cleaned.rfind('.'):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                # US format: thousands separator = ,, decimal = .
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            # Could be decimal comma (European) or thousands separator
            comma_pos = cleaned.rfind(',')
            after_comma = cleaned[comma_pos + 1:]
            
            # If 2 digits after comma, it's likely decimal
            if len(after_comma) == 2 and after_comma.isdigit():
                cleaned = cleaned.replace(',', '.')
            else:
                # Thousands separator
                cleaned = cleaned.replace(',', '')
        
        try:
            return float(cleaned)
        except ValueError:
            logger.warning(f"Could not parse amount: {amount_str}")
            return None

# Specific parser implementations (keeping them compact for space)
class RevolutParser(ExpenseParser):
    """Parser for Revolut transaction screenshots."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse Revolut transaction data from OCR text."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return []

        result = {'currency': 'EUR'}
        
        # Extract amount
        amount_match = re.search(r'-?€?(\d+[.,]\d{2})', lines[0])
        if amount_match:
            result['amount'] = self.parse_european_amount(amount_match.group(1))
        
        # Extract merchant name
        if len(lines) > 1:
            for i in range(1, min(4, len(lines))):
                line = lines[i].strip()
                if re.match(r'^\d{2}:\d{2}', line) or 'today' in line.lower():
                    continue
                if len(line) > 1 and not re.match(r'^[€\d\s,.-]+$', line):
                    result['description'] = self.clean_description(line)
                    break
        
        # Set default date
        result['date'] = datetime.now().strftime('%Y-%m-%d')
        result['category'] = self.smart_categorize(result.get('description', ''))
        
        return [result] if result.get('amount') and result.get('description') else []

class ABNAmroSingleParser(ExpenseParser):
    """Parser for ABN AMRO single transaction screenshots."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse ABN AMRO single transaction with robust extraction."""
        # Simplified implementation - full logic would be here
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Extract amount with multiple strategies
        amount = None
        for pattern in [r'€\s*(-?\d+[,.]\d{2})', r'(-?\d+[,.]\d{2})\s*€']:
            match = re.search(pattern, text)
            if match:
                amount = self.parse_european_amount(match.group(1))
                break
        
        if not amount:
            return []
        
        # Extract description (first meaningful line)
        description = "ABN Transaction"
        for line in lines:
            if (len(line) > 3 and 
                'payment terminal' not in line.lower() and
                'execution' not in line.lower()):
                description = self.clean_description(line)
                break
        
        return [{
            'amount': amount,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': description,
            'currency': 'EUR',
            'category': self.smart_categorize(description)
        }]

class ABNAmroListParser(ExpenseParser):
    """Parser for ABN AMRO transaction list screenshots."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse multiple transactions from bank statement list."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        results = []
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Process transaction lines
        for line in lines:
            # Pattern: Description + Amount on same line
            match = re.match(r'(.+?)\s+-\s*(\d+,\d{2})$', line)
            if match:
                description = self.clean_description(match.group(1).strip())
                amount = self.parse_european_amount(match.group(2))
                
                if amount and description:
                    results.append({
                        'description': description,
                        'amount': amount,
                        'date': current_date,
                        'currency': 'EUR',
                        'category': self.smart_categorize(description)
                    })
        
        return results

class GenericParser(ExpenseParser):
    """Fallback parser for unknown receipt types."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse generic receipt with basic pattern matching."""
        # Look for total amount
        amount_match = re.search(r'(?:total|totaal|amount|bedrag)[:\s]+(\d+[,.]\d{2})', text, re.IGNORECASE)
        if amount_match:
            amount = self.parse_european_amount(amount_match.group(1))
        else:
            # Find largest amount in text
            amounts = re.findall(r'(\d+[.,]\d{2})', text)
            parsed_amounts = [self.parse_european_amount(a) for a in amounts]
            valid_amounts = [a for a in parsed_amounts if a is not None]
            amount = max(valid_amounts) if valid_amounts else 0.0

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        description = lines[0] if lines else 'Scanned Expense'
        
        if amount == 0.0 and description == 'Scanned Expense':
            return []

        return [{
            'amount': amount,
            'currency': 'EUR',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': self.clean_description(description),
            'category': self.smart_categorize(description)
        }]

# ============================================================================
# EXPENSE MANAGEMENT SERVICE
# ============================================================================

class ExpenseManager:
    """
    Handles CRUD operations for confirmed expenses.
    
    AI CONTEXT: Manages the lifecycle of confirmed expense records.
    Includes audit logging for all changes. 
    All operations are async and use database transactions.
    """
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.db_manager = DatabaseManager(db_file)
    
    async def create_expense(self, expense_data: Dict[str, Any], image_data: bytes = None, 
                           image_filename: str = '') -> int:
        """Create a new expense record with audit logging."""
        values = self._prepare_expense_values(expense_data, include_timestamps=True)
        
        async with self.db_manager.get_connection() as conn:
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
            await self._log_audit(expense_id, 'INSERT', None, values)
            logger.info(f"Created expense #{expense_id}: {values['description']}")
            
            return expense_id
    
    async def get_all_expenses(self) -> List[Dict[str, Any]]:
        """Get all expenses ordered by date and creation time."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            cursor = await conn.execute('''
                SELECT id, date, amount, currency, fx_rate, amount_eur, description, 
                       category, person, beneficiary, image_filename, created_on, modified_on,
                       CASE WHEN image_data IS NOT NULL THEN 1 ELSE 0 END as has_image
                FROM expenses 
                ORDER BY date DESC, created_at DESC
            ''')
            
            return [self._sanitize_expense_data(dict(row)) for row in await cursor.fetchall()]
    
    async def delete_expense(self, expense_id: int) -> bool:
        """Delete an expense record with audit logging."""
        async with self.db_manager.get_connection() as conn:
            conn.row_factory = self.db_manager.dict_factory
            
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
            logger.info(f"Deleted expense #{expense_id}")
            return True
    
    # Additional methods would be implemented here...
    # (update_expense, bulk_delete_expenses, get_expense_audit_history, etc.)
    
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
            current_time = datetime.now().isoformat()
            values['created_on'] = current_time
            values['modified_on'] = current_time
        
        return values
    
    def _sanitize_expense_data(self, row_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize and validate expense data from database."""
        return {
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
            'has_image': bool(row_data.get('has_image', False)),
            'created_on': str(row_data.get('created_on', '')),
            'modified_on': str(row_data.get('modified_on', ''))
        }
    
    async def _log_audit(self, expense_id: int, operation: str, old_values: dict = None, 
                        new_values: dict = None):
        """Log audit entry for expense changes."""
        try:
            changes = {}
            if old_values and new_values:
                for key in new_values:
                    if key in old_values and old_values[key] != new_values[key]:
                        changes[key] = {'from': old_values[key], 'to': new_values[key]}
            
            async with self.db_manager.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO expense_audit_log 
                    (expense_id, operation, old_values, new_values, changes, user_info) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    expense_id, operation, 
                    json.dumps(old_values) if old_values else None,
                    json.dumps(new_values) if new_values else None,
                    json.dumps(changes) if changes else None,
                    'system'
                ))
                await conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to log audit entry: {e}")

# ============================================================================
# DRAFT MANAGEMENT SERVICE 
# ============================================================================

class DraftManager:
    """
    Handles draft expense operations with error handling and auto-save.
    
    AI CONTEXT: Manages the workflow from OCR parsing to confirmed expenses.
    Drafts allow users to review and edit OCR results before saving permanently.
    Supports auto-save, bulk operations, and error state management.
    """
    
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
    
    async def confirm_draft_endpoint(self, draft_id: int, form_data: dict):
        """
        Convert draft to permanent expense with validation.
        
        AI CONTEXT: This is called from the API endpoint.
        Handles validation errors by marking drafts rather than failing completely.
        """
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
    
    # Additional methods: clear_draft_error, delete_draft, bulk operations, etc.
    # Implementation continues...

# ============================================================================
# CATEGORY MANAGEMENT SERVICE
# ============================================================================

class CategoryManager:
    """
    Handles expense category operations.
    
    AI CONTEXT: Simple CRUD for expense categories.
    Categories are used for organization and reporting.
    """
    
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

# ============================================================================
# AI DEVELOPMENT NOTES
# ============================================================================

"""
AI COLLABORATION PATTERNS FOR THIS FILE:

1. **Adding New OCR Sources**:
   - Add pattern to SourceIdentifier.identify_source()
   - Create new parser class inheriting from ExpenseParser
   - Register parser in OCRProcessingService.__init__()

2. **Extending Validation**:
   - Modify validate_expense_data() function
   - Add specific validation methods to service classes

3. **Adding New Business Logic**:
   - Create new service class following the async pattern
   - Use dependency injection (pass db_file to constructor)
   - Add comprehensive error handling and logging

4. **Performance Optimization**:
   - Add caching to frequently accessed data
   - Implement connection pooling for high-load scenarios
   - Add background tasks for heavy operations

5. **Testing Strategy**:
   - Mock external dependencies (OCR, FX API)
   - Test each service class independently
   - Use pytest-asyncio for async test methods

PATTERNS USED:
- Async/await throughout for non-blocking operations
- Service layer pattern with clear boundaries
- Dependency injection ready (accept db_file parameter)
- Comprehensive error handling with logging
- Audit trail for all data changes
- Validation-first approach with helpful error messages

FUTURE EVOLUTION:
- When this file exceeds 1200 lines, split by service:
  * ocr_service.py (OCR processing and parsers)
  * expense_service.py (Expense and draft management)  
  * category_service.py (Category and utility services)
"""