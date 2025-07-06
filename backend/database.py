"""
Expense Tracker - Database Management

PURPOSE: Database schema, migrations, and connection management
SCOPE: SQLite operations, schema versioning, and data persistence
DEPENDENCIES: aiosqlite, config.py
"""

import sqlite3
import aiosqlite
import logging
from datetime import datetime
from typing import List

from .config import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Handles all database operations and migrations."""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
    
    async def initialize_database(self) -> None:
        """Initialize SQLite database with proper schema and migrations."""
        async with aiosqlite.connect(self.db_file) as conn:
            await self._setup_schema_versioning(conn)
            current_version = await self._get_current_schema_version(conn)
            logger.info(f"Current database schema version: {current_version}")
            
            if current_version < 2:
                if current_version < 1:
                    await self._migrate_to_version_1(conn)
                await self._migrate_to_version_2(conn)
            
            await self._create_supporting_tables(conn)
            await self._insert_default_categories(conn)
            await conn.commit()
    
    async def _setup_schema_versioning(self, conn: aiosqlite.Connection) -> None:
        """Set up schema version tracking table."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    async def _get_current_schema_version(self, conn: aiosqlite.Connection) -> int:
        """Get the current database schema version."""
        cursor = await conn.execute('SELECT MAX(version) FROM schema_version')
        result = await cursor.fetchone()
        return result[0] or 0
    
    async def _migrate_to_version_1(self, conn: aiosqlite.Connection) -> None:
        """Migrate database to version 1 with audit columns."""
        logger.info("Migrating to schema version 1: Adding audit columns")
        
        # Create backup of existing expenses table
        await self._create_backup_table(conn)
        
        # Create new expenses table with audit columns
        await self._create_expenses_table_v1(conn)
        
        # Migrate existing data if old table exists
        await self._migrate_existing_expense_data(conn)
        
        # Create audit log table
        await self._create_audit_log_table(conn)
        
        # Record schema version
        await conn.execute('INSERT INTO schema_version (version) VALUES (1)')
        logger.info("Schema migration to version 1 completed")
    
    async def _migrate_to_version_2(self, conn: aiosqlite.Connection) -> None:
        """Migrate database to version 2 with error handling for drafts."""
        logger.info("Migrating to schema version 2: Adding error handling to drafts")
        
        # Check if drafts table exists and has error columns
        cursor = await conn.execute("PRAGMA table_info(drafts)")
        columns = [row[1] for row in await cursor.fetchall()]
        
        if 'has_error' not in columns:
            await conn.execute('ALTER TABLE drafts ADD COLUMN has_error INTEGER DEFAULT 0')
        if 'error_message' not in columns:
            await conn.execute('ALTER TABLE drafts ADD COLUMN error_message TEXT DEFAULT NULL')
        if 'last_error_at' not in columns:
            await conn.execute('ALTER TABLE drafts ADD COLUMN last_error_at TIMESTAMP DEFAULT NULL')
            
        # Record schema version
        await conn.execute('INSERT OR REPLACE INTO schema_version (version) VALUES (2)')
        logger.info("Schema migration to version 2 completed")
    
    async def _create_backup_table(self, conn: aiosqlite.Connection) -> None:
        """Create backup of existing expenses table."""
        await conn.execute('DROP TABLE IF EXISTS expenses_backup_v1')
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
        if await cursor.fetchone():
            await conn.execute('CREATE TABLE expenses_backup_v1 AS SELECT * FROM expenses')
            logger.info("Created backup of existing expenses table")
    
    async def _create_expenses_table_v1(self, conn: aiosqlite.Connection) -> None:
        """Create the main expenses table with all required columns."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                currency TEXT NOT NULL DEFAULT 'EUR',
                fx_rate REAL NOT NULL DEFAULT 1.0,
                amount_eur REAL NOT NULL DEFAULT 0.0,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Other',
                person TEXT NOT NULL DEFAULT '',
                beneficiary TEXT DEFAULT '',
                image_data BLOB,
                image_filename TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    async def _migrate_existing_expense_data(self, conn: aiosqlite.Connection) -> None:
        """Migrate data from old expenses table to new structure."""
        try:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
            old_table_exists = await cursor.fetchone()
            
            if old_table_exists:
                await self._perform_data_migration(conn)
                await conn.execute('DROP TABLE expenses')
            
            await conn.execute('ALTER TABLE expenses_new RENAME TO expenses')
            
        except Exception as e:
            logger.error(f"Error during migration: {e}")
            await self._create_fresh_expenses_table(conn)
    
    async def _perform_data_migration(self, conn: aiosqlite.Connection) -> None:
        """Perform the actual data migration with proper column mapping."""
        # Get column info from old table
        cursor = await conn.execute("PRAGMA table_info(expenses)")
        old_columns = [row[1] for row in await cursor.fetchall()]
        
        # Build migration query with proper column mapping
        current_timestamp = datetime.now().isoformat()
        base_columns = [
            'id', 'date', 'amount', 'currency', 'fx_rate', 'amount_eur', 
            'description', 'category', 'person', 'beneficiary', 'image_data', 
            'image_filename', 'created_at'
        ]
        
        select_parts = []
        for col in base_columns:
            if col in old_columns:
                select_parts.append(col)
            elif col == 'amount_eur':
                select_parts.append('COALESCE(amount_eur, amount) as amount_eur')
            elif col == 'fx_rate':
                select_parts.append('COALESCE(fx_rate, 1.0) as fx_rate')
            elif col == 'description':
                select_parts.append('COALESCE(description, "Imported Expense") as description')
            elif col == 'category':
                select_parts.append('COALESCE(category, "Other") as category')
            elif col == 'person':
                select_parts.append('COALESCE(person, "") as person')
            elif col == 'beneficiary':
                select_parts.append('COALESCE(beneficiary, "") as beneficiary')
            elif col == 'image_filename':
                select_parts.append('COALESCE(image_filename, "") as image_filename')
            elif col == 'created_at':
                if col in old_columns:
                    select_parts.append(col)
                else:
                    select_parts.append(f'"{current_timestamp}" as created_at')
        
        # Add audit columns with proper timestamps
        select_parts.extend([
            f'COALESCE(created_at, "{current_timestamp}") as created_on',
            f'COALESCE(created_at, "{current_timestamp}") as modified_on'
        ])
        
        # Execute migration
        migrate_query = f'''
            INSERT INTO expenses_new 
            SELECT {', '.join(select_parts)}
            FROM expenses
        '''
        await conn.execute(migrate_query)
        logger.info("Migrated existing expense data with audit timestamps")
    
    async def _create_fresh_expenses_table(self, conn: aiosqlite.Connection) -> None:
        """Create a fresh expenses table if migration fails."""
        await conn.execute('DROP TABLE IF EXISTS expenses_new')
        await conn.execute('''
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                currency TEXT NOT NULL DEFAULT 'EUR',
                fx_rate REAL NOT NULL DEFAULT 1.0,
                amount_eur REAL NOT NULL DEFAULT 0.0,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Other',
                person TEXT NOT NULL DEFAULT '',
                beneficiary TEXT DEFAULT '',
                image_data BLOB,
                image_filename TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.warning("Created fresh expenses table due to migration error")
    
    async def _create_audit_log_table(self, conn: aiosqlite.Connection) -> None:
        """Create the audit log table for tracking changes."""
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
        logger.info("Created expense audit log table")
    
    async def _create_supporting_tables(self, conn: aiosqlite.Connection) -> None:
        """Create supporting tables for categories, drafts, and FX rates."""
        # DRAFTS table for OCR processing with error handling
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_group_id TEXT NOT NULL,
                date TEXT,
                amount REAL,
                currency TEXT,
                fx_rate REAL,
                amount_eur REAL,
                description TEXT,
                category TEXT,
                person TEXT,
                beneficiary TEXT,
                date_warning TEXT,
                image_data BLOB,
                image_filename TEXT,
                has_error INTEGER DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                last_error_at TIMESTAMP DEFAULT NULL,
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Categories table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        
        # FX rates cache table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fx_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                currency TEXT NOT NULL,
                rate REAL NOT NULL,
                UNIQUE(date, currency)
            )
        ''')
    
    async def _insert_default_categories(self, conn: aiosqlite.Connection) -> None:
        """Insert default expense categories."""
        for category in config.DEFAULT_CATEGORIES:
            await conn.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (category,))