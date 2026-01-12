# Separate Upload & Reconciliation Implementation Guide

## Overview

This implementation meets the requirement for **separate invoice and bank statement uploads with clear reconciliation traceability**. The design ensures accountants can clearly identify which invoice data is reconciled with which bank statement data.

## Core Design Principles

### 1. Separate Upload Tables
- **Invoice Uploads**: Stored in `invoice_uploads` table with unique `invoice_upload_id`
- **Bank Statement Uploads**: Stored in `bank_statement_uploads` table with unique `bank_upload_id`
- **Complete Separation**: Each upload type has its own table with dedicated metadata

### 2. Linked Reconciliation Records
- **Reconciliation Table**: `reconciliation_records` stores both `invoice_upload_id` and `bank_upload_id`
- **Clear Traceability**: Accountants can see exactly which documents were reconciled together
- **Single JSON Storage**: All reconciliation results stored as JSON under one `reconciliation_id`

### 3. Data Integrity & Scalability
- **Foreign Key Constraints**: Ensures referential integrity between uploads and reconciliations
- **Unique Constraints**: Prevents duplicate uploads and duplicate reconciliations
- **Performance Indexes**: Optimized for accountant queries and reporting

## Database Schema

### Invoice Uploads Table
```sql
CREATE TABLE invoice_uploads (
    invoice_upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,  -- Prevents duplicate uploads
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    
    -- Processing metadata
    upload_timestamp TEXT NOT NULL,
    processing_start TEXT,
    processing_end TEXT,
    processing_duration_seconds INTEGER,
    ocr_engine TEXT DEFAULT 'tesseract',
    confidence_score REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    
    -- JSON column containing ALL invoice data (single row per file)
    invoice_data_json TEXT,  -- Full JSON structure with all invoices
    
    -- Summary fields for quick queries (indexed)
    total_invoices_found INTEGER DEFAULT 0,
    total_invoices_processed INTEGER DEFAULT 0,
    total_amount REAL,
    currency_summary TEXT,  -- JSON: {"USD": 85000.00, "EUR": 40000.50}
    vendor_summary TEXT,     -- JSON: {"Acme Corp": 25, "Global Tech": 15}
    date_range_start TEXT,
    date_range_end TEXT,
    
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Bank Statement Uploads Table
```sql
CREATE TABLE bank_statement_uploads (
    bank_upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,  -- Prevents duplicate uploads
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    
    -- Processing metadata
    upload_timestamp TEXT NOT NULL,
    processing_start TEXT,
    processing_end TEXT,
    processing_duration_seconds INTEGER,
    ocr_engine TEXT DEFAULT 'tesseract',
    confidence_score REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    
    -- JSON column containing ALL transaction data (single row per file)
    bank_data_json TEXT,  -- Full JSON structure with all transactions
    
    -- Statement summary fields (indexed)
    account_number TEXT,
    account_name TEXT,
    bank_name TEXT,
    statement_period_start TEXT,
    statement_period_end TEXT,
    opening_balance REAL,
    closing_balance REAL,
    total_debits REAL,
    total_credits REAL,
    currency TEXT DEFAULT 'USD',
    statement_type TEXT,
    
    -- Transaction summary fields (indexed)
    total_transactions_found INTEGER DEFAULT 0,
    total_transactions_processed INTEGER DEFAULT 0,
    transaction_type_summary TEXT,  -- JSON: {"card_transaction": 180, "transfer": 85}
    
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Reconciliation Records Table
```sql
CREATE TABLE reconciliation_records (
    reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Source document references - CORE REQUIREMENT
    invoice_upload_id INTEGER NOT NULL,
    bank_upload_id INTEGER NOT NULL,
    invoice_file_name TEXT,
    bank_file_name TEXT,
    
    -- Reconciliation metadata
    reconciliation_timestamp TEXT NOT NULL,
    reconciliation_duration_seconds INTEGER,
    matching_algorithm TEXT DEFAULT 'hybrid_ml_rule_based',
    confidence_threshold REAL DEFAULT 0.75,
    status TEXT NOT NULL DEFAULT 'pending',
    
    -- JSON column containing ALL reconciliation results (single row per reconciliation)
    reconciliation_results_json TEXT,  -- Full JSON structure with all match results
    
    -- Summary fields for quick queries (indexed)
    total_invoices_processed INTEGER DEFAULT 0,
    total_transactions_processed INTEGER DEFAULT 0,
    total_matches_found INTEGER DEFAULT 0,
    partial_matches INTEGER DEFAULT 0,
    unmatched_invoices INTEGER DEFAULT 0,
    unmatched_transactions INTEGER DEFAULT 0,
    total_amount_matched REAL,
    match_rate_percentage REAL,
    
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraints for data integrity
    FOREIGN KEY (invoice_upload_id) REFERENCES invoice_uploads(invoice_upload_id) ON DELETE CASCADE,
    FOREIGN KEY (bank_upload_id) REFERENCES bank_statement_uploads(bank_upload_id) ON DELETE CASCADE,
    
    -- Unique constraint to prevent duplicate reconciliations between same uploads
    UNIQUE(invoice_upload_id, bank_upload_id)
);
```

## JSON Structure Examples

### Invoice Data JSON (stored in `invoice_uploads.invoice_data_json`)
```json
{
    "upload_info": {
        "invoice_upload_id": 5,
        "file_name": "invoices_batch_2024.pdf",
        "file_path": "/uploads/invoices/invoices_batch_2024.pdf",
        "file_hash": "sha256:abc123...",
        "file_size": 2048576,
        "pages_total": 28,
        "mime_type": "application/pdf"
    },
    "processing_info": {
        "upload_timestamp": "2024-01-15T10:30:00Z",
        "processing_start": "2024-01-15T10:30:05Z",
        "processing_end": "2024-01-15T10:32:15Z",
        "processing_duration_seconds": 130,
        "ocr_engine": "tesseract",
        "confidence_score": 0.92,
        "status": "completed"
    },
    "extraction_summary": {
        "total_invoices_found": 100,
        "total_invoices_processed": 100,
        "total_amount": 125000.50,
        "currency_summary": {"USD": 85000.00, "EUR": 40000.50},
        "vendor_summary": {"Acme Corp": 25, "Global Tech": 15, "Local Supplies": 60},
        "date_range": {
            "earliest_invoice_date": "2024-01-01",
            "latest_invoice_date": "2024-01-31"
        }
    },
    "invoices": [
        {
            "invoice_id": "inv_001",
            "invoice_number": "INV-2024-001",
            "invoice_date": "2024-01-05",
            "due_date": "2024-02-04",
            "vendor_name": "Acme Corp",
            "total_amount": 1080.00,
            "currency": "USD",
            "line_items": [...]
        }
        // ... 99 more invoice objects
    ]
}
```

### Bank Data JSON (stored in `bank_statement_uploads.bank_data_json`)
```json
{
    "upload_info": {
        "bank_upload_id": 7,
        "file_name": "bank_statement_jan2024.pdf",
        "file_path": "/uploads/bank/bank_statement_jan2024.pdf",
        "file_hash": "sha256:def456...",
        "file_size": 1536000,
        "pages_total": 15,
        "mime_type": "application/pdf"
    },
    "processing_info": {
        "upload_timestamp": "2024-02-01T09:15:00Z",
        "processing_start": "2024-02-01T09:15:05Z",
        "processing_end": "2024-02-01T09:16:45Z",
        "processing_duration_seconds": 100,
        "ocr_engine": "tesseract",
        "confidence_score": 0.89,
        "status": "completed"
    },
    "statement_info": {
        "account_number": "****1234",
        "account_name": "Business Checking Account",
        "bank_name": "National Bank",
        "statement_period_start": "2024-01-01",
        "statement_period_end": "2024-01-31",
        "opening_balance": 50000.00,
        "closing_balance": 75000.00,
        "total_debits": 150000.00,
        "total_credits": 175000.00,
        "currency": "USD",
        "statement_type": "checking"
    },
    "extraction_summary": {
        "total_transactions_found": 342,
        "total_transactions_processed": 342,
        "total_debits": 150000.00,
        "total_credits": 175000.00,
        "transaction_types": {
            "card_transaction": 180,
            "domestic_transfer": 85,
            "direct_debit": 45,
            "internal_book_transfer": 32
        }
    },
    "transactions": [
        {
            "transaction_id": "txn_001",
            "transaction_date": "2024-01-02",
            "description": "Card Transaction: Amazon Web Services",
            "debit_amount": 250.00,
            "credit_amount": null,
            "balance": 49750.00,
            "currency": "USD",
            "transaction_type": "card_transaction",
            "reference_number": "REF-001",
            "category": "Software/Cloud Services",
            "page_number": 1,
            "confidence_score": 0.94
        }
        // ... 341 more transaction objects
    ]
}
```

### Reconciliation Results JSON (stored in `reconciliation_records.reconciliation_results_json`)
```json
{
    "reconciliation_info": {
        "reconciliation_id": 3,
        "reconciliation_timestamp": "2024-02-05T14:30:00Z",
        "reconciliation_duration_seconds": 45,
        "matching_algorithm": "hybrid_ml_rule_based",
        "confidence_threshold": 0.75,
        "status": "completed"
    },
    "source_documents": {
        "invoice_upload_id": 5,
        "invoice_file_name": "invoices_batch_2024.pdf",
        "bank_upload_id": 7,
        "bank_file_name": "bank_statement_jan2024.pdf"
    },
    "reconciliation_summary": {
        "total_invoices_processed": 100,
        "total_transactions_processed": 342,
        "total_matches_found": 85,
        "partial_matches": 12,
        "unmatched_invoices": 15,
        "unmatched_transactions": 257,
        "total_amount_matched": 98750.25,
        "match_rate_percentage": 85.0
    },
    "matched": [
        {
            "match_id": "match_001",
            "match_score": 0.95,
            "match_type": "exact",
            "invoice": {
                "invoice_id": "inv_001",
                "invoice_number": "INV-2024-001",
                "invoice_date": "2024-01-05",
                "vendor_name": "Acme Corp",
                "total_amount": 1080.00,
                "currency": "USD"
            },
            "bank_transaction": {
                "transaction_id": "txn_045",
                "transaction_date": "2024-01-05",
                "description": "Direct Debit: Acme Corp",
                "debit_amount": 1080.00,
                "currency": "USD",
                "reference_number": "REF-045"
            },
            "matching_criteria": {
                "amount_match": true,
                "date_match": true,
                "vendor_match": true,
                "reference_match": true
            }
        }
        // ... 84 more matched objects
    ],
    "partial": [
        // ... partial matches with discrepancies
    ],
    "unmatched": {
        "invoices": [
            // ... unmatched invoices with reasons
        ],
        "bank_transactions": [
            // ... unmatched transactions with reasons
        ]
    }
}
```

## Key Features for Accountants

### 1. Clear Document Traceability
```sql
-- Find all reconciliations for a specific invoice upload
SELECT 
    rr.reconciliation_id,
    rr.reconciliation_timestamp,
    rr.total_matches_found,
    rr.match_rate_percentage,
    bu.file_name as bank_file_name,
    bu.upload_timestamp as bank_upload_timestamp,
    bu.account_number,
    bu.bank_name
FROM reconciliation_records rr
JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
WHERE rr.invoice_upload_id = 5
ORDER BY rr.reconciliation_timestamp DESC;
```

### 2. Complete Audit Trail
```sql
-- Get complete reconciliation details with source documents
SELECT 
    rr.*,
    iu.file_name as invoice_file_name,
    iu.upload_timestamp as invoice_upload_timestamp,
    bu.file_name as bank_file_name,
    bu.upload_timestamp as bank_upload_timestamp,
    bu.account_number,
    bu.bank_name,
    bu.statement_period_start,
    bu.statement_period_end
FROM reconciliation_records rr
LEFT JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
LEFT JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
WHERE rr.reconciliation_id = 3;
```

### 3. Performance & Reporting Indexes
- `idx_reconciliation_invoice_upload`: Fast lookup by invoice upload
- `idx_reconciliation_bank_upload`: Fast lookup by bank upload  
- `idx_reconciliation_timestamp`: Chronological reporting
- `idx_reconciliation_match_rate`: Performance analysis
- `idx_invoice_uploads_hash`: Duplicate detection
- `idx_bank_uploads_account`: Account-based reporting

## Data Access Layer

### Core Functions
```python
from models.separate_upload_reconciliation_models import SeparateUploadDataAccess

# Initialize data access
data_access = SeparateUploadDataAccess("reconciliation.db")

# Insert invoice upload
invoice_upload_id = data_access.insert_invoice_upload(invoice_upload)

# Insert bank upload  
bank_upload_id = data_access.insert_bank_upload(bank_upload)

# Insert reconciliation record linking both uploads
reconciliation_id = data_access.insert_reconciliation_record(reconciliation_record)

# Get traceability report
traceability_data = data_access.get_reconciliation_traceability_report(
    invoice_upload_id=5  # or bank_upload_id=7
)
```

### Validation Functions
```python
# Validate JSON structure before storage
is_valid, error_msg = validate_separate_upload_json_structure(
    json_string, "invoice"  # or "bank", "reconciliation"
)
```

## Migration Process

### Automated Migration
```bash
python migrations/migrate_to_separate_upload_schema.py
```

The migration script:
1. **Creates backup** of existing database
2. **Initializes new schema** with separate tables
3. **Migrates existing data** from unified or production schemas
4. **Validates data integrity** and foreign key constraints
5. **Generates migration log** for audit purposes

### Migration Safety Features
- **Automatic backup** before any changes
- **Rollback capability** by restoring from backup
- **Data validation** at each step
- **Comprehensive logging** for audit trail
- **Foreign key validation** to ensure referential integrity

## Production Benefits

### 1. Accountant-Friendly
- **Clear separation** of invoice and bank statement uploads
- **Explicit linking** in reconciliation records
- **Complete traceability** from upload to reconciliation
- **Audit-ready** structure with timestamps and file references

### 2. Scalable Performance
- **Single-row storage** for all results (JSON)
- **Optimized indexes** for common accountant queries
- **Efficient foreign key constraints** for data integrity
- **Unique constraints** to prevent duplicates

### 3. Data Integrity
- **Foreign key constraints** ensure reconciliation records always point to valid uploads
- **Unique constraints** prevent duplicate uploads and reconciliations
- **JSON validation** ensures data structure consistency
- **Referential integrity** with CASCADE delete for clean data management

### 4. Maintenance & Operations
- **Clear separation** makes debugging and maintenance easier
- **Modular design** allows independent evolution of upload types
- **Standardized JSON structures** for consistent API responses
- **Comprehensive validation** prevents data corruption

## Usage Examples

### Upload Flow
```python
# 1. Upload invoice file
invoice_upload = InvoiceUpload(
    file_name="january_invoices.pdf",
    file_path="/uploads/invoices/january_invoices.pdf",
    file_hash=calculate_file_hash("/uploads/invoices/january_invoices.pdf"),
    file_size=2048576,
    mime_type="application/pdf",
    invoice_data_json=extracted_invoice_data_json
)
invoice_upload_id = data_access.insert_invoice_upload(invoice_upload)

# 2. Upload bank statement
bank_upload = BankStatementUpload(
    file_name="january_bank_statement.pdf", 
    file_path="/uploads/bank/january_bank_statement.pdf",
    file_hash=calculate_file_hash("/uploads/bank/january_bank_statement.pdf"),
    file_size=1536000,
    mime_type="application/pdf",
    bank_data_json=extracted_bank_data_json
)
bank_upload_id = data_access.insert_bank_upload(bank_upload)

# 3. Reconcile
reconciliation_record = ReconciliationRecord(
    invoice_upload_id=invoice_upload_id,
    bank_upload_id=bank_upload_id,
    invoice_file_name="january_invoices.pdf",
    bank_file_name="january_bank_statement.pdf",
    reconciliation_results_json=reconciliation_results_json,
    total_matches_found=85,
    match_rate_percentage=85.0
)
reconciliation_id = data_access.insert_reconciliation_record(reconciliation_record)
```

### Accountant Query Examples
```python
# Find all reconciliations for January 2024 invoices
january_reconciliations = data_access.get_reconciliation_traceability_report(
    invoice_upload_id=january_invoice_upload_id
)

# Get complete reconciliation details
reconciliation_details = data_access.get_reconciliation_with_sources(
    reconciliation_id=3
)
```

## Summary

This implementation provides:

✅ **Separate upload tables** with unique IDs for invoices and bank statements  
✅ **Clear reconciliation linking** storing both upload IDs together  
✅ **Single JSON storage** for all reconciliation results under one reconciliation_id  
✅ **Complete traceability** for accountants to identify document relationships  
✅ **Production-ready scalability** with proper indexing and constraints  
✅ **Data integrity** through foreign keys and validation  
✅ **Automated migration** from existing schemas  
✅ **Accountant-friendly queries** and reporting capabilities  

The design meets the ultra-short requirement: *"Store invoice and bank statement uploads separately, but during reconciliation save both IDs together in the reconciliation table, with all results stored as JSON under one reconciliation ID."*
