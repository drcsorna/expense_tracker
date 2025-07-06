"""
Expense Tracker - Data Validation

PURPOSE: Data validation and business rule enforcement
SCOPE: Input validation, business logic checks, and error handling
DEPENDENCIES: typing
"""

from typing import Dict, Any, List, Tuple


def validate_expense_data(expense_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate expense data and return validation result with error messages."""
    errors = []
    
    # Check required fields
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


def validate_draft_data(draft_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate draft data (less strict than expense validation)."""
    errors = []
    
    # Basic validation for drafts
    amount = draft_data.get('amount')
    if amount is not None and amount <= 0:
        errors.append("Amount must be greater than 0")
    
    return len(errors) == 0, errors


def validate_category_name(name: str) -> Tuple[bool, List[str]]:
    """Validate category name."""
    errors = []
    
    if not name or not name.strip():
        errors.append("Category name is required")
    elif len(name.strip()) > 100:
        errors.append("Category name must be 100 characters or less")
    
    return len(errors) == 0, errors


def sanitize_form_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize form data by stripping whitespace and converting types."""
    sanitized = {}
    
    for key, value in form_data.items():
        if isinstance(value, str):
            sanitized[key] = value.strip()
        else:
            sanitized[key] = value
    
    return sanitized