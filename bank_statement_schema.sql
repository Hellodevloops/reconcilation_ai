-- Enhanced Bank Statement Table Schema
-- Contains all fields from your image as NOT NULL columns (except optional fields)

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

-- Sample INSERT statement
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
