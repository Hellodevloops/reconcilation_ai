"""
Database Migration Script for Multi-Invoice Support
Creates new tables and indexes for enhanced invoice processing
"""

import os
import sys
import sqlite3
import traceback

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.enhanced_models import get_all_schema_statements
from config import DB_PATH


def run_migration():
    """Run database migration to add multi-invoice support"""
    print("Starting database migration for multi-invoice support...")
    
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        
        # Create new tables
        statements = get_all_schema_statements()
        
        for statement in statements:
            try:
                print(f"Executing: {statement[:100]}...")
                cur.execute(statement)
                print("+ Success")
            except sqlite3.OperationalError as e:
                if "already exists" in str(e):
                    print("+ Already exists")
                else:
                    print(f"! Warning: {e}")
            except Exception as e:
                print(f"! Error: {e}")
                raise
        
        # Add migration tracking table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT NOT NULL UNIQUE,
                executed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Record this migration
        try:
            cur.execute("""
                INSERT INTO schema_migrations (migration_name) 
                VALUES ('multi_invoice_support_v1')
            """)
        except sqlite3.IntegrityError:
            print("Migration already recorded")
        
        # Add file_upload_id column to existing transactions table for backward compatibility
        try:
            cur.execute("ALTER TABLE transactions ADD COLUMN file_upload_id INTEGER")
            print("+ Added file_upload_id column to transactions table")
        except sqlite3.OperationalError:
            print("+ file_upload_id column already exists in transactions table")
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_transactions_file_upload ON transactions(file_upload_id)",
            "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_file_upload ON reconciliation_matches(invoice_file_id)",
        ]
        
        for index_sql in indexes:
            try:
                cur.execute(index_sql)
                print(f"+ Created index: {index_sql[:50]}...")
            except sqlite3.OperationalError:
                print(f"+ Index already exists: {index_sql[:50]}...")
        
        conn.commit()
        conn.close()
        
        print("+ Database migration completed successfully!")
        print("\nNew tables created:")
        print("- file_uploads: Parent records for uploaded files")
        print("- extracted_invoices: Individual invoices extracted from files")
        print("- invoice_line_items: Line items within invoices")
        print("- processing_jobs: Background job tracking")
        print("- schema_migrations: Migration tracking")
        
        return True
        
    except Exception as e:
        print(f"- Migration failed: {e}")
        print(traceback.format_exc())
        return False


def verify_migration():
    """Verify that migration was successful"""
    print("\nVerifying migration...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check if all tables exist
        tables = [
            'file_uploads',
            'extracted_invoices', 
            'invoice_line_items',
            'processing_jobs',
            'schema_migrations'
        ]
        
        for table in tables:
            cur.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table,))
            
            result = cur.fetchone()
            if result:
                print(f"+ Table {table} exists")
            else:
                print(f"- Table {table} missing")
                return False
        
        # Check indexes
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_%'
        """)
        
        indexes = cur.fetchall()
        print(f"+ Found {len(indexes)} performance indexes")
        
        # Check if migration was recorded
        cur.execute("""
            SELECT migration_name, executed_at 
            FROM schema_migrations 
            WHERE migration_name = 'multi_invoice_support_v1'
        """)
        
        migration = cur.fetchone()
        if migration:
            print(f"+ Migration recorded: {migration[0]} at {migration[1]}")
        else:
            print("! Migration not found in tracking table")
        
        conn.close()
        print("+ Migration verification completed successfully!")
        return True
        
    except Exception as e:
        print(f"- Verification failed: {e}")
        return False


def get_migration_status():
    """Get current migration status"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check if migration table exists
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='schema_migrations'
        """)
        
        if not cur.fetchone():
            return {
                "status": "not_started",
                "message": "Migration tracking table not found"
            }
        
        # Check for our migration
        cur.execute("""
            SELECT migration_name, executed_at 
            FROM schema_migrations 
            WHERE migration_name = 'multi_invoice_support_v1'
        """)
        
        migration = cur.fetchone()
        if migration:
            return {
                "status": "completed",
                "migration_name": migration[0],
                "executed_at": migration[1]
            }
        else:
            return {
                "status": "pending",
                "message": "Multi-invoice support migration not yet applied"
            }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


if __name__ == "__main__":
    print("Multi-Invoice Support Migration Script")
    print("=" * 50)
    
    # Check current status
    status = get_migration_status()
    print(f"Current status: {status['status']}")
    if 'message' in status:
        print(f"Details: {status['message']}")
    
    if status['status'] == "completed":
        print("\nMigration already completed. Verifying...")
        verify_migration()
    elif status['status'] == "not_started" or status['status'] == "pending":
        print("\nRunning migration...")
        success = run_migration()
        if success:
            verify_migration()
        else:
            print("Migration failed. Please check the error messages above.")
    else:
        print(f"Error checking status: {status['message']}")
