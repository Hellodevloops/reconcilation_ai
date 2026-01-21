-- Manual Invoice Entries Table
CREATE TABLE IF NOT EXISTS manual_invoice_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    date TEXT NOT NULL,
    invoice_number TEXT,
    vendor_name TEXT,
    currency TEXT DEFAULT 'GBP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE
);

-- Manual Bank Entries Table
CREATE TABLE IF NOT EXISTS manual_bank_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    date TEXT NOT NULL,
    reference_id TEXT,
    currency TEXT DEFAULT 'GBP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE
);

-- MySQL versions (if using MySQL)
-- CREATE TABLE IF NOT EXISTS manual_invoice_entries (
--     id INT AUTO_INCREMENT PRIMARY KEY,
--     reconciliation_id INT NOT NULL,
--     description TEXT NOT NULL,
--     amount DECIMAL(15,2) NOT NULL,
--     date VARCHAR(20) NOT NULL,
--     invoice_number VARCHAR(100),
--     vendor_name VARCHAR(200),
--     currency VARCHAR(3) DEFAULT 'GBP',
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE
-- );

-- CREATE TABLE IF NOT EXISTS manual_bank_entries (
--     id INT AUTO_INCREMENT PRIMARY KEY,
--     reconciliation_id INT NOT NULL,
--     description TEXT NOT NULL,
--     amount DECIMAL(15,2) NOT NULL,
--     date VARCHAR(20) NOT NULL,
--     reference_id VARCHAR(100),
--     currency VARCHAR(3) DEFAULT 'GBP',
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(id) ON DELETE CASCADE
-- );
