"""
SQLite Migration Script for Reconciliation Database
Creates all necessary tables for the reconciliation system (SQLite-compatible)
"""

import os
import sys
import logging

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database_manager import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLite-compatible table creation statements
TABLES = {
    "file_uploads": """
        CREATE TABLE IF NOT EXISTS file_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL CHECK(file_type IN ('invoice', 'bank_statement')),
            file_size INTEGER NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processing_status TEXT DEFAULT 'pending' CHECK(processing_status IN ('pending', 'processing', 'completed', 'failed')),
            error_message TEXT,
            file_path TEXT,
            metadata TEXT
        )
    """,
    
    "invoices": """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_upload_id INTEGER NULL,
            invoice_number TEXT,
            invoice_date DATE,
            reference TEXT NULL,
            vendor_name TEXT,
            vat_number TEXT NULL,
            total_amount REAL,
            tax_amount REAL,
            total_vat_rate REAL NULL,
            total_zero_rated REAL NULL,
            total_gbp REAL NULL,
            net_amount REAL,
            due_date DATE,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
            invoice_file_path TEXT,
            invoice_file_hash TEXT,
            description TEXT,
            line_items TEXT,
            extracted_data TEXT,
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_upload_id) REFERENCES file_uploads(id) ON DELETE SET NULL
        )
    """,
    
    "invoice_extractions": """
        CREATE TABLE IF NOT EXISTS invoice_extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_invoice_id INTEGER NOT NULL,
            sequence_no INTEGER NOT NULL,
            page_no INTEGER,
            raw_text TEXT,
            extracted_fields TEXT,
            confidence REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        )
    """,
    
    "bank_transactions": """
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_upload_id INTEGER NOT NULL,
            transaction_date DATE NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            balance REAL,
            transaction_type TEXT,
            reference TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_upload_id) REFERENCES file_uploads(id) ON DELETE CASCADE
        )
    """,
    
    "reconciliations": """
        CREATE TABLE IF NOT EXISTS reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            reconciliation_date DATE NOT NULL,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived')),
            total_invoices INTEGER DEFAULT 0,
            total_transactions INTEGER DEFAULT 0,
            total_matches INTEGER DEFAULT 0,
            total_amount REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    "reconciliation_matches": """
        CREATE TABLE IF NOT EXISTS reconciliation_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_id INTEGER NOT NULL,
            invoice_id INTEGER NOT NULL,
            transaction_id INTEGER NOT NULL,
            match_score REAL NOT NULL,
            match_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES bank_transactions(id) ON DELETE CASCADE
        )
    """,
    
    "unmatched_invoices": """
        CREATE TABLE IF NOT EXISTS unmatched_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_id INTEGER NOT NULL,
            invoice_id INTEGER NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        )
    """,
    
    "unmatched_transactions": """
        CREATE TABLE IF NOT EXISTS unmatched_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_id INTEGER NOT NULL,
            transaction_id INTEGER NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES bank_transactions(id) ON DELETE CASCADE
        )
    """,
    
    "ml_models": """
        CREATE TABLE IF NOT EXISTS ml_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL UNIQUE,
            model_type TEXT NOT NULL CHECK(model_type IN ('classification', 'regression', 'clustering')),
            model_version TEXT NOT NULL,
            model_path TEXT,
            accuracy REAL,
            precision REAL,
            recall REAL,
            f1_score REAL,
            training_data_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    "training_data": """
        CREATE TABLE IF NOT EXISTS training_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            transaction_id INTEGER NOT NULL,
            is_match INTEGER NOT NULL,
            features TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES bank_transactions(id) ON DELETE CASCADE
        )
    """
}

# SQLite-compatible indexes
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_vendor_name ON invoices(vendor_name)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_invoice_date ON invoices(invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_file_upload_id ON invoices(file_upload_id)",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_date ON bank_transactions(transaction_date)",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_amount ON bank_transactions(amount)",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_file_upload_id ON bank_transactions(file_upload_id)",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_reconciliation_id ON reconciliation_matches(reconciliation_id)",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_invoice_id ON reconciliation_matches(invoice_id)",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_transaction_id ON reconciliation_matches(transaction_id)",
    "CREATE INDEX IF NOT EXISTS idx_unmatched_invoices_reconciliation_id ON unmatched_invoices(reconciliation_id)",
    "CREATE INDEX IF NOT EXISTS idx_unmatched_transactions_reconciliation_id ON unmatched_transactions(reconciliation_id)",
    "CREATE INDEX IF NOT EXISTS idx_training_data_invoice_id ON training_data(invoice_id)",
    "CREATE INDEX IF NOT EXISTS idx_training_data_transaction_id ON training_data(transaction_id)"
]

def create_tables():
    """Create all tables"""
    try:
        logger.info("Starting SQLite database migration...")
        
        # Create tables
        for table_name, create_sql in TABLES.items():
            logger.info(f"Creating table: {table_name}")
            db_manager.execute_update(create_sql)
        
        # Create indexes
        logger.info("Creating indexes...")
        for index_sql in INDEXES:
            try:
                db_manager.execute_update(index_sql)
            except Exception as e:
                logger.warning(f"Failed to create index: {e}")
        
        # Verify tables were created
        logger.info("Verifying table creation...")
        for table_name in TABLES.keys():
            if db_manager.table_exists(table_name):
                logger.info(f"✅ Table '{table_name}' exists")
            else:
                logger.error(f"❌ Table '{table_name}' was not created")
                return False
        
        logger.info("Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

def main():
    """Main migration function"""
    print("SQLite Migration for Reconciliation Database")
    print("=" * 50)
    
    if db_manager.db_type != "sqlite":
        logger.error("This script is for SQLite migration only. Set DB_TYPE=sqlite in config.")
        sys.exit(1)
    
    success = create_tables()
    
    if success:
        print("\nMigration completed successfully!")
        print("Your SQLite database is ready for use.")
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above.")

if __name__ == "__main__":
    main()
