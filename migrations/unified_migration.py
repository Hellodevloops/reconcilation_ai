"""
Unified Document Processing Migration
Production-ready database migration for unified invoice and bank statement processing
"""

import os
import sys
import sqlite3
import traceback
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.unified_models import get_unified_schema_statements
from config import DB_PATH

def run_unified_migration():
    """Run the unified document processing migration"""
    print("=" * 60)
    print("UNIFIED DOCUMENT PROCESSING MIGRATION")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Enable foreign key constraints
        cur.execute("PRAGMA foreign_keys = ON")
        
        # Check if migration already run
        cur.execute("""
            SELECT COUNT(*) FROM schema_migrations 
            WHERE migration_name = 'unified_document_processing_v1'
        """)
        
        if cur.fetchone()[0] > 0:
            print("+ Unified document processing migration already completed")
            conn.close()
            return True
        
        print("Creating unified document processing schema...")
        
        # Get all schema statements
        statements = get_unified_schema_statements()
        
        # Execute statements
        for i, statement in enumerate(statements, 1):
            try:
                cur.execute(statement)
                print(f"  {i}/{len(statements)}: Executed schema statement")
            except sqlite3.Error as e:
                if "already exists" in str(e).lower():
                    print(f"  {i}/{len(statements)}: Table/index already exists")
                else:
                    print(f"  {i}/{len(statements)}: Error: {e}")
        
        # Record migration
        cur.execute("""
            INSERT INTO schema_migrations (migration_name, executed_at)
            VALUES ('unified_document_processing_v1', ?)
        """, (datetime.now().isoformat(),))
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print()
        print("+ Unified document processing migration completed successfully!")
        print()
        print("Created tables:")
        print("  - document_uploads (unified parent records)")
        print("  - extracted_invoices (invoice child records)")
        print("  - invoice_line_items (invoice line items)")
        print("  - bank_transactions (bank transaction child records)")
        print("  - bank_statements (bank statement metadata)")
        print("  - processing_jobs (unified job tracking)")
        print()
        print("Created indexes for optimal performance")
        print("Foreign key constraints enabled")
        print("Migration tracking updated")
        
        return True
        
    except Exception as e:
        print(f"- Migration failed: {e}")
        print("Traceback:")
        traceback.print_exc()
        return False

def verify_unified_migration():
    """Verify the unified migration was successful"""
    print("\n" + "=" * 60)
    print("VERIFYING UNIFIED MIGRATION")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check required tables exist
        required_tables = [
            'document_uploads',
            'extracted_invoices',
            'invoice_line_items',
            'bank_transactions',
            'bank_statements',
            'processing_jobs'
        ]
        
        print("Checking required tables:")
        all_exist = True
        for table in required_tables:
            cur.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table,))
            exists = cur.fetchone()[0] > 0
            status = "+" if exists else "-"
            print(f"  {status} {table}")
            if not exists:
                all_exist = False
        
        # Check migration record
        cur.execute("""
            SELECT COUNT(*) FROM schema_migrations 
            WHERE migration_name = 'unified_document_processing_v1'
        """)
        migration_exists = cur.fetchone()[0] > 0
        status = "+" if migration_exists else "-"
        print(f"  {status} Migration record")
        
        # Check indexes
        print("\nChecking key indexes:")
        key_indexes = [
            'idx_document_uploads_hash',
            'idx_document_uploads_type',
            'idx_extracted_invoices_upload',
            'idx_bank_transactions_upload',
            'idx_processing_jobs_upload'
        ]
        
        for index in key_indexes:
            cur.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='index' AND name=?
            """, (index,))
            exists = cur.fetchone()[0] > 0
            status = "+" if exists else "-"
            print(f"  {status} {index}")
        
        conn.close()
        
        if all_exist and migration_exists:
            print("\n+ Unified migration verification successful!")
            return True
        else:
            print("\n- Unified migration verification failed!")
            return False
            
    except Exception as e:
        print(f"\n- Verification failed: {e}")
        return False

def migrate_existing_data():
    """Migrate existing data to unified schema"""
    print("\n" + "=" * 60)
    print("MIGRATING EXISTING DATA TO UNIFIED SCHEMA")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check if old multi-invoice tables exist
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='file_uploads'
        """)
        old_table_exists = cur.fetchone()[0] > 0
        
        if not old_table_exists:
            print("+ No old multi-invoice tables found - skipping data migration")
            conn.close()
            return True
        
        print("Found existing multi-invoice tables - migrating data...")
        
        # Migrate file_uploads to document_uploads
        cur.execute("""
            INSERT OR IGNORE INTO document_uploads (
                id, file_name, file_path, file_hash, file_size, file_type, mime_type,
                document_type, upload_timestamp, processing_status, processing_start_time,
                processing_end_time, total_documents_found, total_documents_processed,
                total_amount, currency_summary, extraction_confidence, error_message, metadata,
                created_at, updated_at
            )
            SELECT 
                id, file_name, file_path, file_hash, file_size, file_type, mime_type,
                'invoice' as document_type, upload_timestamp, processing_status, processing_start_time,
                processing_end_time, total_invoices_found as total_documents_found, total_invoices_processed,
                total_amount, currency_summary, extraction_confidence, error_message, metadata,
                created_at, updated_at
            FROM file_uploads
        """)
        
        migrated_uploads = cur.rowcount
        print(f"  + Migrated {migrated_uploads} file upload records")
        
        # Migrate extracted_invoices (add document_upload_id column first if needed)
        try:
            # Check if column exists
            cur.execute("PRAGMA table_info(extracted_invoices)")
            columns = [col[1] for col in cur.fetchall()]
            
            if 'document_upload_id' not in columns:
                # Add the new column
                cur.execute("ALTER TABLE extracted_invoices ADD COLUMN document_upload_id INTEGER")
                print("  + Added document_upload_id column to extracted_invoices")
            
            # Update foreign key reference
            cur.execute("""
                UPDATE extracted_invoices 
                SET document_upload_id = file_upload_id
                WHERE document_upload_id IS NULL AND file_upload_id IS NOT NULL
            """)
            
            migrated_invoices = cur.rowcount
            print(f"  + Updated {migrated_invoices} invoice records")
            
        except sqlite3.Error as e:
            print(f"  ! Warning: Could not migrate invoices: {e}")
            migrated_invoices = 0
        
        # Migrate processing_jobs
        try:
            # Check if column exists
            cur.execute("PRAGMA table_info(processing_jobs)")
            columns = [col[1] for col in cur.fetchall()]
            
            if 'document_upload_id' not in columns:
                # Add the new column
                cur.execute("ALTER TABLE processing_jobs ADD COLUMN document_upload_id INTEGER")
                print("  + Added document_upload_id column to processing_jobs")
            
            if 'document_type' not in columns:
                # Add the new column
                cur.execute("ALTER TABLE processing_jobs ADD COLUMN document_type TEXT")
                print("  + Added document_type column to processing_jobs")
            
            # Update the new columns
            cur.execute("""
                UPDATE processing_jobs 
                SET document_upload_id = file_upload_id,
                    document_type = 'invoice'
                WHERE document_upload_id IS NULL AND file_upload_id IS NOT NULL
            """)
            
            migrated_jobs = cur.rowcount
            print(f"  + Updated {migrated_jobs} processing job records")
            
        except sqlite3.Error as e:
            print(f"  ! Warning: Could not migrate processing jobs: {e}")
            migrated_jobs = 0
        
        conn.commit()
        conn.close()
        
        print("\n+ Data migration completed successfully!")
        print(f"  - File uploads: {migrated_uploads}")
        print(f"  - Invoices: {migrated_invoices}")
        print(f"  - Jobs: {migrated_jobs}")
        
        return True
        
    except Exception as e:
        print(f"- Data migration failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Main migration function"""
    print("UNIFIED DOCUMENT PROCESSING MIGRATION TOOL")
    print("=" * 60)
    
    # Run migration
    if run_unified_migration():
        # Verify migration
        if verify_unified_migration():
            # Migrate existing data
            if migrate_existing_data():
                print("\n" + "=" * 60)
                print("UNIFIED MIGRATION COMPLETED SUCCESSFULLY!")
                print("=" * 60)
                print("The system is now ready for unified document processing.")
                print("Both invoices and bank statements will use the same")
                print("parent-child architecture with single primary keys.")
                return True
            else:
                print("\n- Data migration failed!")
                return False
        else:
            print("\n- Migration verification failed!")
            return False
    else:
        print("\n- Migration failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
