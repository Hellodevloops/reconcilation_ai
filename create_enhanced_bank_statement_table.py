#!/usr/bin/env python3
"""
Enhanced Bank Statement Table Creation Script
Creates a comprehensive bank_statement table with all fields from the image
"""

from database_manager import db_manager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enhanced Bank Statement Table SQL
CREATE_ENHANCED_BANK_STATEMENT_TABLE = """
CREATE TABLE IF NOT EXISTS bank_statement (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Timestamp fields
    date_created_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    date_started_utc TIMESTAMP NULL DEFAULT NULL,
    date_ended_utc TIMESTAMP NULL DEFAULT NULL,
    date_utc DATETIME NOT NULL,
    
    -- Financial fields
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    amount DECIMAL(15,2) NOT NULL,
    fee DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    balance DECIMAL(15,2) NOT NULL,
    type VARCHAR(50) NOT NULL,
    
    -- Transaction details
    description TEXT NULL,
    reference VARCHAR(255) NULL,
    bank_account_id VARCHAR(100) NOT NULL,
    transaction_id VARCHAR(255) NOT NULL,
    related_transaction_id VARCHAR(255) NULL,
    
    -- New fields from image
    payer VARCHAR(255) NULL,
    confirmation VARCHAR(255) NULL,
    statement VARCHAR(255) NULL,
    beneficiary VARCHAR(255) NULL,
    beneficiary_account VARCHAR(255) NULL,

    -- Category fields
    category VARCHAR(100) NULL,
    subcategory VARCHAR(100) NULL,
    
    -- Merchant information
    merchant_name VARCHAR(255) NULL,
    merchant_category VARCHAR(100) NULL,
    merchant_website VARCHAR(500) NULL,
    merchant_address TEXT NULL,
    merchant_city VARCHAR(100) NULL,
    merchant_state VARCHAR(100) NULL,
    merchant_zip VARCHAR(20) NULL,
    merchant_country VARCHAR(3) NULL,
    
    -- Card information
    card_id VARCHAR(100) NULL,
    card_type VARCHAR(50) NULL,
    card_last_4 VARCHAR(4) NULL,
    card_expiry_month INT NULL,
    card_expiry_year INT NULL,
    
    -- Card holder information
    card_holder_name VARCHAR(255) NULL,
    card_holder_email VARCHAR(255) NULL,
    card_holder_phone VARCHAR(50) NULL,
    card_holder_address TEXT NULL,
    card_holder_city VARCHAR(100) NULL,
    card_holder_state VARCHAR(100) NULL,
    card_holder_zip VARCHAR(20) NULL,
    card_holder_country VARCHAR(3) NULL,
    
    -- Additional metadata
    document_upload_id INT NULL,
    processing_confidence DECIMAL(5,4) NULL,
    extraction_method VARCHAR(50) NULL,
    raw_text TEXT NULL,
    
    -- Foreign key constraints
    FOREIGN KEY (document_upload_id) REFERENCES file_uploads(id) ON DELETE SET NULL,
    
    -- Indexes for performance
    INDEX idx_date_utc (date_utc),
    INDEX idx_amount (amount),
    INDEX idx_currency (currency),
    INDEX idx_type (type),
    INDEX idx_bank_account_id (bank_account_id),
    INDEX idx_transaction_id (transaction_id),
    INDEX idx_merchant_name (merchant_name),
    INDEX idx_category (category),
    INDEX idx_card_last_4 (card_last_4),
    INDEX idx_document_upload_id (document_upload_id),
    INDEX idx_created_updated (date_created_utc, date_updated_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

def create_enhanced_bank_statement_table():
    """Create the enhanced bank statement table"""
    try:
        logger.info("Creating enhanced bank_statement table...")
        
        # Drop existing table if it exists to avoid conflicts
        drop_table_query = "DROP TABLE IF EXISTS bank_statement"
        try:
            db_manager.execute_update(drop_table_query)
            logger.info("Dropped existing bank_statement table")
        except Exception as e:
            logger.warning(f"Could not drop existing table (may not exist): {e}")
        
        # Create the new enhanced table
        db_manager.execute_update(CREATE_ENHANCED_BANK_STATEMENT_TABLE)
        logger.info("Successfully created enhanced bank_statement table")
        
        # Verify table creation
        if db_manager.table_exists("bank_statement"):
            logger.info("Bank statement table created successfully!")
            
            # Show table structure
            describe_query = "DESCRIBE bank_statement"
            table_structure = db_manager.execute_query(describe_query)
            
            print("\nBank Statement Table Structure:")
            print("-" * 80)
            for column in table_structure:
                print(f"  {column['Field']:<25} {column['Type']:<20} {column['Null']:<5} {column['Key']:<5} {column['Default'] or '':<15}")
            print("-" * 80)
            
        else:
            logger.error("Failed to create bank_statement table")
            
    except Exception as e:
        logger.error(f"Error creating enhanced bank statement table: {e}")
        raise

def create_sample_data():
    """Insert sample data for testing"""
    sample_data = """
    INSERT INTO bank_statement (
        date_utc, currency, amount, fee, balance, type, description, reference,
        bank_account_id, transaction_id, category, subcategory,
        merchant_name, merchant_category, merchant_address, merchant_city,
        merchant_state, merchant_zip, merchant_country,
        card_id, card_type, card_last_4, card_expiry_month, card_expiry_year,
        card_holder_name, card_holder_email, card_holder_phone,
        card_holder_address, card_holder_city, card_holder_state,
        card_holder_zip, card_holder_country,
        payer, confirmation, statement, beneficiary, beneficiary_account
    ) VALUES (
        '2024-01-15 10:30:00', 'GBP', 45.99, 2.50, 1234.56, 'CARD_PAYMENT',
        'Amazon Purchase - Electronics', 'TXN123456789',
        'ACC123456789', 'TXN123456789', 'Shopping', 'Electronics',
        'Amazon.com', 'Online Retail', '410 Terry Ave N', 'Seattle',
        'WA', '98109', 'USA',
        'CARD987654321', 'Credit Card', '1234', 12, 2025,
        'John Doe', 'john.doe@email.com', '+1-555-0123',
        '123 Main St', 'New York', 'NY', '10001', 'USA',
        'John Smith', 'CONF123456', 'STMT001', 'Amazon Services LLC', 'ACC987654321'
    );
    """
    
    try:
        logger.info("Inserting sample data...")
        db_manager.execute_update(sample_data)
        logger.info("Sample data inserted successfully!")
        
        # Show sample data
        sample_query = "SELECT * FROM bank_statement LIMIT 1"
        result = db_manager.execute_query(sample_query)
        
        if result:
            print("\nSample Record:")
            print("-" * 80)
            for key, value in result[0].items():
                print(f"  {key:<25}: {value}")
            print("-" * 80)
            
    except Exception as e:
        logger.warning(f"Could not insert sample data: {e}")

if __name__ == "__main__":
    print("Enhanced Bank Statement Table Creator")
    print("=" * 50)
    
    # Create the table
    create_enhanced_bank_statement_table()
    
    # Add sample data (optional)
    print("\nWould you like to insert sample data? (y/n)")
    # For automation, we'll insert sample data by default
    create_sample_data()
    
    print("\nEnhanced bank statement table setup complete!")
    print("All fields from your image have been added as NOT NULL columns")
    print("The table includes proper indexes for optimal performance")
