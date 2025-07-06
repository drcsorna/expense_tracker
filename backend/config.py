"""
Expense Tracker - Configuration and Constants

PURPOSE: Central configuration management for the application
SCOPE: Application settings, constants, and environment variables
DEPENDENCIES: None (foundational module)
"""

import logging
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class AppConfig:
    """Application configuration constants."""
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


# Global configuration instance
config = AppConfig()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)