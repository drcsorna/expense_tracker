"""
Expense Tracker Backend Package

PURPOSE: Package initialization for the expense tracker backend
SCOPE: Module imports and package configuration
"""

__version__ = "1.0.0"
__author__ = "Expense Tracker Team"
__description__ = "Personal expense tracker with OCR receipt processing"

# Package imports for easier access
from .config import config
from .database import DatabaseManager
from .ocr_processor import OCRProcessingService
from .managers import ExpenseManager, DraftManager, CategoryManager
from .validators import validate_expense_data, validate_draft_data, validate_category_name

__all__ = [
    "config",
    "DatabaseManager", 
    "OCRProcessingService",
    "ExpenseManager",
    "DraftManager", 
    "CategoryManager",
    "validate_expense_data",
    "validate_draft_data",
    "validate_category_name"
]