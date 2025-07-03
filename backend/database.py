"""
Expense Tracker - Database Management and Persistence Layer

PURPOSE: Database operations, schema management, and data persistence
SCOPE: ~200 lines - Clean data access layer with simple table creation
DEPENDENCIES: aiosqlite (async SQLite), logging

AI CONTEXT: Simplified database layer for fresh installations.
All tables are created directly in their final form.
"""

import logging
from typing import Any, Dict
from contextlib import asynccontextmanager
import aiosqlite

# ============================================================================
# CONFIGURATION AND LOGGING
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE MANAGER CLASS
# ============================================================================

class DatabaseManager:
    """
    Handles all database operations and connection management.
    
    AI CONTEXT: Simplified database management for fresh installations.
    Creates all tables directly without migration complexity.
    """
    
    def __init__(self, db_file: str):
        """Initialize database manager."""
        self.db_file = db_file
        logger.info(f"DatabaseManager initialized with file: {db_file}")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection with automatic cleanup."""
        conn = None
        try:
            conn = await aiosqlite.connect(self.db_file)
            conn.row_factory = aiosqlite.Row  # Enable column access by name
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            if conn:
                await conn.rollback()
            raise
        finally:
            if conn:
                await conn.close()
    
    @staticmethod
    def dict_factory(cursor, row):
        """Convert SQLite row to dictionary."""
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    
    # ============================================================================
    # DATABASE INITIALIZATION
    # ============================================================================
    
    async def initialize_database(self) -> None:
        """
        Initialize SQLite database with all tables.
        
        AI CONTEXT: Simple database setup for fresh installations.
        Creates all tables directly in their final form.
        """
        async with self.get_connection() as conn:
            # Create all tables
            await self._create_expenses_table(conn)
            await self._create_drafts_table(conn)
            await self._create_categories_table(conn)
            await self._create_fx_rates_table(conn)
            await self._create_audit_log_table(conn)
            
            # Insert default categories
            await self._insert_default_categories(conn)
            
            # Commit all changes
            await conn.commit()
            
            logger.info("✅ Database initialization completed successfully")
    
    # ============================================================================
    # TABLE CREATION
    # ============================================================================
    
    async def _create_expenses_table(self, conn: aiosqlite.Connection) -> None:
        """Create the main expenses table."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Financial Information
                date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                currency TEXT NOT NULL DEFAULT 'EUR',
                fx_rate REAL NOT NULL DEFAULT 1.0,
                amount_eur REAL NOT NULL DEFAULT 0.0,
                
                -- Descriptive Information
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Other',
                person TEXT NOT NULL DEFAULT '',
                beneficiary TEXT DEFAULT '',
                
                -- Media Attachments
                image_data BLOB,
                image_filename TEXT DEFAULT '',
                
                -- Audit Trail
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("📊 Expenses table created")
    
    async def _create_drafts_table(self, conn: aiosqlite.Connection) -> None:
        """Create drafts table for OCR processing workflow."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_group_id TEXT NOT NULL,
                
                -- Expense Data (same as expenses table)
                date TEXT,
                amount REAL,
                currency TEXT,
                fx_rate REAL,
                amount_eur REAL,
                description TEXT,
                category TEXT,
                person TEXT,
                beneficiary TEXT,
                date_warning TEXT, -- For relative date warnings
                
                -- Media
                image_data BLOB,
                image_filename TEXT,
                
                -- Error Handling
                has_error INTEGER DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                last_error_at TIMESTAMP DEFAULT NULL,
                
                -- Timestamps
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("📝 Drafts table created")
    
    async def _create_categories_table(self, conn: aiosqlite.Connection) -> None:
        """Create categories table for expense categorization."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        logger.info("📂 Categories table created")
    
    async def _create_fx_rates_table(self, conn: aiosqlite.Connection) -> None:
        """Create FX rates cache table."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fx_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                currency TEXT NOT NULL,
                rate REAL NOT NULL,
                UNIQUE(date, currency)
            )
        ''')
        logger.info("💱 FX rates table created")
    
    async def _create_audit_log_table(self, conn: aiosqlite.Connection) -> None:
        """Create audit log table for tracking expense changes."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS expense_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_id INTEGER NOT NULL,
                operation TEXT NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
                old_values TEXT, -- JSON of old values (NULL for INSERT)
                new_values TEXT, -- JSON of new values (NULL for DELETE)
                changes TEXT, -- JSON of what specifically changed
                audit_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_info TEXT DEFAULT 'system', -- For future user tracking
                FOREIGN KEY (expense_id) REFERENCES expenses(id)
            )
        ''')
        logger.info("📋 Audit log table created")
    
    async def _insert_default_categories(self, conn: aiosqlite.Connection) -> None:
        """Insert default expense categories."""
        default_categories = [
            'Other', 'Caffeine', 'Household', 'Car', 'Snacks',
            'Office Lunch', 'Brunch', 'Clothing', 'Dog', 'Eating Out', 
            'Groceries', 'Restaurants'
        ]
        
        for category in default_categories:
            await conn.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (category,))
        
        logger.info(f"📂 Default categories ready ({len(default_categories)} categories)")

# ============================================================================
# DATABASE UTILITIES
# ============================================================================

class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

async def verify_database_health(db_file: str) -> Dict[str, Any]:
    """
    Verify database health and return diagnostic information.
    """
    db_manager = DatabaseManager(db_file)
    
    try:
        async with db_manager.get_connection() as conn:
            # Get table counts
            cursor = await conn.execute("SELECT COUNT(*) FROM expenses")
            expense_count = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM drafts")
            draft_count = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM categories")
            category_count = (await cursor.fetchone())[0]
            
            return {
                "status": "healthy",
                "expense_count": expense_count,
                "draft_count": draft_count,
                "category_count": category_count,
                "database_file": db_file
            }
            
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_file": db_file
        }