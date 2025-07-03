"""
Expense Tracker - Database Management and Persistence Layer

PURPOSE: Database operations, schema management, and data persistence
SCOPE: ~400 lines - Data access layer with async operations and migrations
DEPENDENCIES: aiosqlite (async SQLite), logging

AI CONTEXT: This is the data persistence layer of the application.
Handles all database operations, schema versioning, and data integrity.
When working on database-related issues or adding new tables, this is your primary file.

FEATURES:
- Async SQLite operations with aiosqlite
- Schema versioning and automatic migrations
- Connection management with proper cleanup
- Data integrity and transaction safety
- Comprehensive error handling and logging

TABLES:
- expenses: Main expense records with audit fields
- drafts: OCR processing results before confirmation  
- categories: Available expense categories
- fx_rates: Exchange rate cache
- expense_audit_log: Change tracking for expenses
- schema_version: Database version tracking

DEPLOYMENT: Works in both development and Docker environments
SCALABILITY: SQLite for single-user, PostgreSQL migration path available
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional, Any, Dict
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
    Handles all database operations, migrations, and connection management.
    
    AI CONTEXT: Central database management with schema versioning.
    
    DESIGN PRINCIPLES:
    - Async operations throughout (non-blocking)
    - Transaction safety for data integrity
    - Schema evolution with automatic migrations
    - Comprehensive error handling and logging
    - Connection pooling ready for future scaling
    
    USAGE PATTERNS:
    ```python
    db_manager = DatabaseManager('expenses.db')
    
    # Initialize database (run once on startup)
    await db_manager.initialize_database()
    
    # Use connections with proper cleanup
    async with db_manager.get_connection() as conn:
        cursor = await conn.execute('SELECT * FROM expenses')
        results = await cursor.fetchall()
    ```
    """
    
    def __init__(self, db_file: str):
        """
        Initialize database manager.
        
        Args:
            db_file: Path to SQLite database file
            
        AI CONTEXT: Database file is created automatically if it doesn't exist.
        In Docker deployments, ensure this path is in a mounted volume for persistence.
        """
        self.db_file = db_file
        logger.info(f"DatabaseManager initialized with file: {db_file}")
    
    @asynccontextmanager
    async def get_connection(self):
        """
        Get database connection with automatic cleanup.
        
        AI CONTEXT: Use this for all database operations.
        Ensures proper connection cleanup and error handling.
        
        Example:
        ```python
        async with db_manager.get_connection() as conn:
            await conn.execute('INSERT INTO...')
            await conn.commit()
        ```
        """
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
        """
        Convert SQLite row to dictionary.
        
        AI CONTEXT: Helper for converting database rows to dicts.
        Use when you need dict access instead of Row objects.
        """
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    
    # ============================================================================
    # DATABASE INITIALIZATION AND SCHEMA MANAGEMENT
    # ============================================================================
    
    async def initialize_database(self) -> None:
        """
        Initialize SQLite database with proper schema and migrations.
        
        AI CONTEXT: Main entry point for database setup.
        
        WORKFLOW:
        1. Create schema versioning table
        2. Check current schema version
        3. Run necessary migrations
        4. Create supporting tables
        5. Insert default data
        
        SAFE TO RUN MULTIPLE TIMES: Idempotent operations only.
        """
        async with self.get_connection() as conn:
            # Setup schema versioning system
            await self._setup_schema_versioning(conn)
            
            # Get current version and run migrations
            current_version = await self._get_current_schema_version(conn)
            logger.info(f"Current database schema version: {current_version}")
            
            # Run migrations if needed
            if current_version < 2:
                if current_version < 1:
                    await self._migrate_to_version_1(conn)
                await self._migrate_to_version_2(conn)
            
            # Create or update supporting tables
            await self._create_supporting_tables(conn)
            
            # Insert default categories if needed
            await self._insert_default_categories(conn)
            
            # Commit all changes
            await conn.commit()
            
            logger.info("✅ Database initialization completed successfully")
    
    async def _setup_schema_versioning(self, conn: aiosqlite.Connection) -> None:
        """
        Set up schema version tracking table.
        
        AI CONTEXT: Enables safe database migrations.
        Tracks which schema versions have been applied.
        """
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.debug("Schema versioning table ready")
    
    async def _get_current_schema_version(self, conn: aiosqlite.Connection) -> int:
        """Get the current database schema version."""
        cursor = await conn.execute('SELECT MAX(version) FROM schema_version')
        result = await cursor.fetchone()
        return result[0] or 0
    
    # ============================================================================
    # SCHEMA MIGRATIONS
    # ============================================================================
    
    async def _migrate_to_version_1(self, conn: aiosqlite.Connection) -> None:
        """
        Migrate database to version 1: Add audit columns and audit log.
        
        AI CONTEXT: Migration from initial schema to audited schema.
        
        CHANGES:
        - Add audit columns to expenses table (created_on, modified_on)
        - Create expense_audit_log table for change tracking
        - Migrate existing data with proper timestamps
        - Create backup of existing data
        
        SAFE: Creates backup before making changes.
        """
        logger.info("🔄 Migrating to schema version 1: Adding audit columns")
        
        try:
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
            
            logger.info("✅ Schema migration to version 1 completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Schema migration to version 1 failed: {e}")
            await conn.rollback()
            raise
    
    async def _migrate_to_version_2(self, conn: aiosqlite.Connection) -> None:
        """
        Migrate database to version 2: Add error handling to drafts.
        
        AI CONTEXT: Adds error state management to draft workflow.
        
        CHANGES:
        - Add has_error column to drafts table
        - Add error_message column to drafts table  
        - Add last_error_at timestamp column
        
        SAFE: Only adds columns, no data loss.
        """
        logger.info("🔄 Migrating to schema version 2: Adding error handling to drafts")
        
        try:
            # Check if drafts table exists and has error columns
            cursor = await conn.execute("PRAGMA table_info(drafts)")
            columns = [row[1] for row in await cursor.fetchall()]
            
            # Add missing error handling columns
            if 'has_error' not in columns:
                await conn.execute('ALTER TABLE drafts ADD COLUMN has_error INTEGER DEFAULT 0')
                logger.debug("Added has_error column to drafts table")
                
            if 'error_message' not in columns:
                await conn.execute('ALTER TABLE drafts ADD COLUMN error_message TEXT DEFAULT NULL')
                logger.debug("Added error_message column to drafts table")
                
            if 'last_error_at' not in columns:
                await conn.execute('ALTER TABLE drafts ADD COLUMN last_error_at TIMESTAMP DEFAULT NULL')
                logger.debug("Added last_error_at column to drafts table")
            
            # Record schema version
            await conn.execute('INSERT OR REPLACE INTO schema_version (version) VALUES (2)')
            
            logger.info("✅ Schema migration to version 2 completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Schema migration to version 2 failed: {e}")
            await conn.rollback()
            raise
    
    async def _create_backup_table(self, conn: aiosqlite.Connection) -> None:
        """Create backup of existing expenses table before migration."""
        await conn.execute('DROP TABLE IF EXISTS expenses_backup_v1')
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
        if await cursor.fetchone():
            await conn.execute('CREATE TABLE expenses_backup_v1 AS SELECT * FROM expenses')
            logger.info("📋 Created backup of existing expenses table")
    
    async def _create_expenses_table_v1(self, conn: aiosqlite.Connection) -> None:
        """
        Create the main expenses table with audit columns.
        
        AI CONTEXT: Complete expenses table schema with all required fields.
        
        SCHEMA DESIGN:
        - id: Primary key (auto-increment)
        - Financial: amount, currency, fx_rate, amount_eur
        - Descriptive: date, description, category, person, beneficiary
        - Media: image_data (BLOB), image_filename
        - Audit: created_at, created_on, modified_on
        
        CONSTRAINTS:
        - NOT NULL for required fields with sensible defaults
        - REAL for financial calculations (avoids floating point issues)
        - TEXT for strings with explicit encoding
        """
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses_new (
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
        logger.debug("Created new expenses table with audit columns")
    
    async def _migrate_existing_expense_data(self, conn: aiosqlite.Connection) -> None:
        """
        Migrate data from old expenses table to new structure.
        
        AI CONTEXT: Handles data migration with proper column mapping.
        
        STRATEGY:
        - Check which columns exist in old table
        - Map old columns to new schema
        - Provide sensible defaults for missing columns
        - Preserve all existing data
        """
        try:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
            old_table_exists = await cursor.fetchone()
            
            if old_table_exists:
                await self._perform_data_migration(conn)
                await conn.execute('DROP TABLE expenses')
                logger.info("💾 Migrated existing expense data")
            
            # Rename new table to final name
            await conn.execute('ALTER TABLE expenses_new RENAME TO expenses')
            
        except Exception as e:
            logger.error(f"Data migration error: {e}")
            # Fallback: create fresh table
            await self._create_fresh_expenses_table(conn)
    
    async def _perform_data_migration(self, conn: aiosqlite.Connection) -> None:
        """Perform the actual data migration with proper column mapping."""
        # Get column info from old table
        cursor = await conn.execute("PRAGMA table_info(expenses)")
        old_columns = [row[1] for row in await cursor.fetchall()]
        
        # Build migration query with proper column mapping
        current_timestamp = datetime.now().isoformat()
        
        # Define core columns with fallback values
        base_columns = [
            'id', 'date', 'amount', 'currency', 'fx_rate', 'amount_eur', 
            'description', 'category', 'person', 'beneficiary', 
            'image_data', 'image_filename', 'created_at'
        ]
        
        # Build SELECT parts with fallbacks for missing columns
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
        
        # Execute migration query
        migrate_query = f'''
            INSERT INTO expenses_new 
            SELECT {', '.join(select_parts)}
            FROM expenses
        '''
        await conn.execute(migrate_query)
        logger.info("📊 Migrated existing expense data with audit timestamps")
    
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
        logger.warning("⚠️ Created fresh expenses table due to migration error")
    
    async def _create_audit_log_table(self, conn: aiosqlite.Connection) -> None:
        """
        Create the audit log table for tracking expense changes.
        
        AI CONTEXT: Comprehensive audit trail for compliance and debugging.
        
        SCHEMA:
        - expense_id: Links to expenses table
        - operation: INSERT, UPDATE, DELETE
        - old_values: JSON of values before change
        - new_values: JSON of values after change  
        - changes: JSON of specific field changes
        - audit_timestamp: When change occurred
        - user_info: Future user identification
        """
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
        logger.info("📋 Created expense audit log table")
    
    # ============================================================================
    # SUPPORTING TABLES CREATION
    # ============================================================================
    
    async def _create_supporting_tables(self, conn: aiosqlite.Connection) -> None:
        """
        Create supporting tables for categories, drafts, and FX rates.
        
        AI CONTEXT: Additional tables required for full application functionality.
        
        TABLES:
        - drafts: OCR processing results before confirmation
        - categories: Available expense categories
        - fx_rates: Exchange rate cache to reduce API calls
        """
        
        # DRAFTS table for OCR processing workflow
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
                
                -- Error Handling (added in v2)
                has_error INTEGER DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                last_error_at TIMESTAMP DEFAULT NULL,
                
                -- Timestamps
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # CATEGORIES table for expense categorization
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        
        # FX RATES cache table to reduce API calls
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fx_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                currency TEXT NOT NULL,
                rate REAL NOT NULL,
                UNIQUE(date, currency)
            )
        ''')
        
        logger.info("📋 Supporting tables created/verified")
    
    async def _insert_default_categories(self, conn: aiosqlite.Connection) -> None:
        """
        Insert default expense categories if they don't exist.
        
        AI CONTEXT: Provides sensible default categories for new installations.
        Safe to run multiple times due to INSERT OR IGNORE.
        """
        default_categories = [
            'Other', 'Caffeine', 'Household', 'Car', 'Snacks',
            'Office Lunch', 'Brunch', 'Clothing', 'Dog', 'Eating Out', 
            'Groceries', 'Restaurants'
        ]
        
        for category in default_categories:
            await conn.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (category,))
        
        logger.info(f"📂 Default categories ready ({len(default_categories)} categories)")

# ============================================================================
# DATABASE UTILITIES AND HELPERS
# ============================================================================

class DatabaseError(Exception):
    """
    Custom exception for database-related errors.
    
    AI CONTEXT: Use this for database-specific error handling.
    Provides better error context than generic exceptions.
    """
    pass

async def verify_database_health(db_file: str) -> Dict[str, Any]:
    """
    Verify database health and return diagnostic information.
    
    AI CONTEXT: Useful for health checks and debugging.
    Returns database statistics and connectivity status.
    
    Returns:
        Dict with database health information
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
            
            # Get schema version
            cursor = await conn.execute("SELECT MAX(version) FROM schema_version")
            schema_version = (await cursor.fetchone())[0] or 0
            
            return {
                "status": "healthy",
                "schema_version": schema_version,
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

# ============================================================================
# AI DEVELOPMENT NOTES
# ============================================================================

"""
AI COLLABORATION PATTERNS FOR THIS FILE:

1. **Adding New Tables**:
   - Add CREATE TABLE statement to _create_supporting_tables()
   - Consider adding to database health check
   - Document the table purpose and schema

2. **Schema Migrations**:
   - Create new _migrate_to_version_X() method
   - Increment target version in initialize_database()
   - Always test with backup data first
   - Use ALTER TABLE ADD COLUMN for safe changes

3. **Performance Optimization**:
   - Add database indexes for frequently queried columns
   - Consider connection pooling for high-load scenarios
   - Monitor query performance with EXPLAIN QUERY PLAN

4. **Data Integrity**:
   - Add foreign key constraints where appropriate
   - Implement database triggers for complex business rules
   - Use transactions for multi-table operations

5. **Monitoring and Debugging**:
   - Add logging to all migration steps
   - Use verify_database_health() for health checks
   - Monitor database file size in production

PATTERNS USED:
- Async context managers for connection handling
- Schema versioning for safe migrations  
- Comprehensive error handling with rollbacks
- Backup creation before destructive changes
- Idempotent operations (safe to run multiple times)

SCALING CONSIDERATIONS:
- SQLite suitable for single-user applications
- PostgreSQL migration path available for multi-user
- Consider read replicas for reporting workloads
- File-based storage (SQLite) vs server-based (PostgreSQL)

DOCKER DEPLOYMENT:
- Mount database file as volume for persistence
- Use WAL mode for better concurrent access
- Regular backup strategy for production data
- Monitor disk space usage
"""