"""
MySQL Migration Script for Reconciliation Database
Creates all necessary tables for the reconciliation system
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

# MySQL-compatible table creation statements
TABLES = {
    "file_uploads": """
        CREATE TABLE IF NOT EXISTS file_uploads (
            id INT PRIMARY KEY AUTO_INCREMENT,
            file_name VARCHAR(500) NOT NULL,
            file_type ENUM('invoice', 'bank_statement') NOT NULL,
            file_size BIGINT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processing_status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending',
            error_message TEXT,
            file_path VARCHAR(1000),
            metadata JSON
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "invoices": """
        CREATE TABLE IF NOT EXISTS invoices (
            id INT PRIMARY KEY AUTO_INCREMENT,
            file_upload_id INT NULL,
            invoice_number VARCHAR(200),
            invoice_date DATE,
            reference VARCHAR(255) NULL,
            vendor_name VARCHAR(500),
            vat_number VARCHAR(100) NULL,
            total_amount DECIMAL(15,2),
            tax_amount DECIMAL(15,2),
            total_vat_rate DECIMAL(6,3) NULL,
            total_zero_rated DECIMAL(15,2) NULL,
            total_gbp DECIMAL(15,2) NULL,
            net_amount DECIMAL(15,2),
            due_date DATE,
            status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending',
            invoice_file_path VARCHAR(1000),
            invoice_file_hash VARCHAR(64),
            description TEXT,
            line_items JSON,
            extracted_data JSON,
            confidence_score DECIMAL(5,4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_upload_id) REFERENCES file_uploads(id) ON DELETE SET NULL,
            INDEX idx_invoice_number (invoice_number),
            INDEX idx_vendor_name (vendor_name),
            INDEX idx_invoice_date (invoice_date),
            INDEX idx_total_amount (total_amount),
            UNIQUE KEY unique_invoice_file_hash (invoice_file_hash)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    "invoice_extractions": """
        CREATE TABLE IF NOT EXISTS invoice_extractions (
            id INT PRIMARY KEY AUTO_INCREMENT,
            parent_invoice_id INT NOT NULL,
            sequence_no INT NOT NULL,
            page_no INT,
            section_no INT,
            original_filename VARCHAR(500),
            json_file_path VARCHAR(1000),
            extracted_data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            UNIQUE KEY unique_parent_sequence (parent_invoice_id, sequence_no),
            INDEX idx_parent_invoice_id (parent_invoice_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "bank_transactions": """
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id INT PRIMARY KEY AUTO_INCREMENT,
            file_upload_id INT NOT NULL,
            transaction_date DATE NOT NULL,
            description TEXT NOT NULL,
            amount DECIMAL(15,2) NOT NULL,
            balance DECIMAL(15,2),
            transaction_type ENUM('credit', 'debit') NOT NULL,
            reference_number VARCHAR(200),
            account_number VARCHAR(100),
            category VARCHAR(200),
            raw_data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_upload_id) REFERENCES file_uploads(id) ON DELETE CASCADE,
            INDEX idx_transaction_date (transaction_date),
            INDEX idx_amount (amount),
            INDEX idx_description (description(255)),
            INDEX idx_transaction_type (transaction_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "reconciliations": """
        CREATE TABLE IF NOT EXISTS reconciliations (
            id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(500) NOT NULL,
            description TEXT,
            reconciliation_date DATE NOT NULL,
            status ENUM('pending', 'in_progress', 'completed', 'failed') DEFAULT 'pending',
            total_invoices INT DEFAULT 0,
            total_transactions INT DEFAULT 0,
            total_matches INT DEFAULT 0,
            total_amount_matched DECIMAL(15,2) DEFAULT 0,
            -- Bank statement fields (from UI screenshots)
            date_started_utc TIMESTAMP NULL DEFAULT NULL,
            date_ended_utc TIMESTAMP NULL DEFAULT NULL,
            date_utc DATETIME NULL DEFAULT NULL,
            external_id VARCHAR(255) NULL,
            type VARCHAR(100) NULL,
            bank_description TEXT NULL,
            reference VARCHAR(255) NULL,
            reference_2 VARCHAR(255) NULL,
            reference_name VARCHAR(255) NULL,
            payer VARCHAR(255) NULL,
            card_number VARCHAR(64) NULL,
            orig_currency VARCHAR(10) NULL,
            orig_amount DECIMAL(15,2) NULL,
            amount DECIMAL(15,2) NULL,
            fee DECIMAL(15,2) NULL,
            balance DECIMAL(15,2) NULL,
            paid_in DECIMAL(15,2) NULL,
            paid_out DECIMAL(15,2) NULL,
            account VARCHAR(255) NULL,
            beneficiary VARCHAR(255) NULL,
            bic VARCHAR(32) NULL,
            raw_json LONGTEXT NULL,
            source_file_name VARCHAR(500) NULL,
            source_file_hash VARCHAR(128) NULL,
            bank_account_number VARCHAR(64) NULL,
            bank_sort_code VARCHAR(32) NULL,
            statement_period_start DATE NULL,
            statement_period_end DATE NULL,
            opening_balance DECIMAL(15,2) NULL,
            closing_balance DECIMAL(15,2) NULL,
            statement_total_paid_in DECIMAL(15,2) NULL,
            statement_total_paid_out DECIMAL(15,2) NULL,
            business_owner VARCHAR(255) NULL,
            business_address TEXT NULL,
            created_by VARCHAR(200),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_reconciliation_date (reconciliation_date),
            INDEX idx_status (status),
            INDEX idx_created_at (created_at),
            INDEX idx_date_utc (date_utc),
            INDEX idx_reference (reference),
            INDEX idx_account (account)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "reconciliation_matches": """
        CREATE TABLE IF NOT EXISTS reconciliation_matches (
            id INT PRIMARY KEY AUTO_INCREMENT,
            reconciliation_id INT NOT NULL,
            invoice_id INT NOT NULL,
            transaction_id INT NOT NULL,
            match_score DECIMAL(5,4) NOT NULL,
            match_type ENUM('auto', 'manual', 'suggested') NOT NULL,
            status ENUM('pending', 'confirmed', 'rejected') DEFAULT 'pending',
            amount_difference DECIMAL(15,2),
            date_difference INT,
            confidence_score DECIMAL(5,4),
            matching_rules JSON,
            notes TEXT,
            created_by VARCHAR(200),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES bank_transactions(id) ON DELETE CASCADE,
            INDEX idx_reconciliation_id (reconciliation_id),
            INDEX idx_invoice_id (invoice_id),
            INDEX idx_transaction_id (transaction_id),
            INDEX idx_match_score (match_score),
            INDEX idx_status (status),
            UNIQUE KEY unique_invoice_transaction_match (reconciliation_id, invoice_id, transaction_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "unmatched_invoices": """
        CREATE TABLE IF NOT EXISTS unmatched_invoices (
            id INT PRIMARY KEY AUTO_INCREMENT,
            reconciliation_id INT NOT NULL,
            invoice_id INT NOT NULL,
            reason VARCHAR(500),
            suggested_matches JSON,
            auto_match_attempted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            INDEX idx_reconciliation_id (reconciliation_id),
            INDEX idx_invoice_id (invoice_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "unmatched_transactions": """
        CREATE TABLE IF NOT EXISTS unmatched_transactions (
            id INT PRIMARY KEY AUTO_INCREMENT,
            reconciliation_id INT NOT NULL,
            transaction_id INT NOT NULL,
            reason VARCHAR(500),
            suggested_matches JSON,
            auto_match_attempted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES bank_transactions(id) ON DELETE CASCADE,
            INDEX idx_reconciliation_id (reconciliation_id),
            INDEX idx_transaction_id (transaction_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "ml_models": """
        CREATE TABLE IF NOT EXISTS ml_models (
            id INT PRIMARY KEY AUTO_INCREMENT,
            model_name VARCHAR(200) NOT NULL UNIQUE,
            model_type ENUM('classification', 'regression', 'clustering') NOT NULL,
            model_version VARCHAR(50) NOT NULL,
            model_path VARCHAR(1000),
            accuracy_score DECIMAL(5,4),
            training_data_count INT,
            last_trained_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_model_name (model_name),
            INDEX idx_is_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    "training_data": """
        CREATE TABLE IF NOT EXISTS training_data (
            id INT PRIMARY KEY AUTO_INCREMENT,
            invoice_id INT NOT NULL,
            transaction_id INT NOT NULL,
            is_match BOOLEAN NOT NULL,
            match_score DECIMAL(5,4),
            features JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES bank_transactions(id) ON DELETE CASCADE,
            INDEX idx_is_match (is_match),
            INDEX idx_match_score (match_score)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    
    
}

def add_column_if_not_exists(table, column, definition):
    """Adds a column to a table if it doesn't already exist"""
    try:
        # Check if column exists
        query = f"SHOW COLUMNS FROM `{table}` LIKE '{column}'"
        result = db_manager.execute_query(query)
        
        if not result:
            logger.info(f"Adding column '{column}' to table '{table}'")
            db_manager.execute_update(f"ALTER TABLE `{table}` ADD COLUMN {column} {definition}")
            logger.info(f"✅ Column '{column}' added successfully")
        else:
            logger.debug(f"Column '{column}' already exists in table '{table}'")
    except Exception as e:
        logger.error(f"Error adding column '{column}' to '{table}': {e}")


def create_tables():
    """Create all tables in the database"""
    logger.info("Starting MySQL database migration...")
    
    try:
        # Create database if it doesn't exist
        db_manager.create_database_if_not_exists()
        
        # Create each table
        for table_name, table_sql in TABLES.items():
            logger.info(f"Creating table: {table_name}")
            db_manager.execute_update(table_sql)
            logger.info(f"✅ Table '{table_name}' created successfully")

        # Ensure invoices schema supports invoice-as-business-record
        db_manager.execute_update("ALTER TABLE invoices MODIFY COLUMN file_upload_id INT NULL")

        add_column_if_not_exists("invoices", "status", "ENUM('pending','processing','completed','failed') DEFAULT 'pending'")
        add_column_if_not_exists("invoices", "invoice_file_path", "VARCHAR(1000)")
        add_column_if_not_exists("invoices", "invoice_file_hash", "VARCHAR(64)")
        add_column_if_not_exists("invoices", "reference", "VARCHAR(255) NULL")
        add_column_if_not_exists("invoices", "vat_number", "VARCHAR(100) NULL")
        add_column_if_not_exists("invoices", "total_vat_rate", "DECIMAL(6,3) NULL")
        add_column_if_not_exists("invoices", "total_zero_rated", "DECIMAL(15,2) NULL")
        add_column_if_not_exists("invoices", "total_gbp", "DECIMAL(15,2) NULL")

        # Ensure reconciliations has required bank-statement fields
        reconciliation_cols = [
            ("date_started_utc", "TIMESTAMP NULL DEFAULT NULL"),
            ("date_ended_utc", "TIMESTAMP NULL DEFAULT NULL"),
            ("date_utc", "DATETIME NULL DEFAULT NULL"),
            ("external_id", "VARCHAR(255) NULL"),
            ("type", "VARCHAR(100) NULL"),
            ("bank_description", "TEXT NULL"),
            ("reference", "VARCHAR(255) NULL"),
            ("reference_2", "VARCHAR(255) NULL"),
            ("reference_name", "VARCHAR(255) NULL"),
            ("payer", "VARCHAR(255) NULL"),
            ("card_number", "VARCHAR(64) NULL"),
            ("orig_currency", "VARCHAR(10) NULL"),
            ("orig_amount", "DECIMAL(15,2) NULL"),
            ("amount", "DECIMAL(15,2) NULL"),
            ("fee", "DECIMAL(15,2) NULL"),
            ("balance", "DECIMAL(15,2) NULL"),
            ("paid_in", "DECIMAL(15,2) NULL"),
            ("paid_out", "DECIMAL(15,2) NULL"),
            ("account", "VARCHAR(255) NULL"),
            ("beneficiary", "VARCHAR(255) NULL"),
            ("bic", "VARCHAR(32) NULL"),
            ("raw_json", "LONGTEXT NULL"),
            ("source_file_name", "VARCHAR(500) NULL"),
            ("source_file_hash", "VARCHAR(128) NULL"),
            ("bank_account_number", "VARCHAR(64) NULL"),
            ("bank_sort_code", "VARCHAR(32) NULL"),
            ("statement_period_start", "DATE NULL"),
            ("statement_period_end", "DATE NULL"),
            ("opening_balance", "DECIMAL(15,2) NULL"),
            ("closing_balance", "DECIMAL(15,2) NULL"),
            ("statement_total_paid_in", "DECIMAL(15,2) NULL"),
            ("statement_total_paid_out", "DECIMAL(15,2) NULL"),
            ("business_owner", "VARCHAR(255) NULL"),
            ("business_address", "TEXT NULL"),
        ]
        for col, defn in reconciliation_cols:
            add_column_if_not_exists("reconciliations", col, defn)

        # Best-effort cleanup: drop legacy bank_statements tables if present.
        for stmt in [
            "DROP TABLE IF EXISTS bank_statement_extractions",
            "DROP TABLE IF EXISTS bank_statements",
        ]:
            try:
                db_manager.execute_update(stmt)
            except Exception:
                pass

        try:
            db_manager.execute_update("ALTER TABLE invoices ADD UNIQUE KEY unique_invoice_file_hash (invoice_file_hash)")
        except Exception:
            pass
        
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
    print("MySQL Migration for Reconciltion Database")
    print("=" * 50)
    
    if db_manager.db_type != "mysql":
        logger.error("This script is for MySQL migration only. Set DB_TYPE=mysql in config.")
        sys.exit(1)
    
    success = create_tables()
    
    if success:
        print("\nMigration completed successfully!")
        print("Your 'reconciltion' database is ready for use.")
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
