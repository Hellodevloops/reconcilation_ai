"""
Production-Ready Separate Upload & Reconciliation Models
Implements the requirement for separate invoice/bank statement uploads with linked reconciliation

Core Design:
- Invoice uploads stored in separate table with unique invoice_upload_id
- Bank statement uploads stored in separate table with unique bank_upload_id  
- Reconciliation table stores both IDs together for clear traceability
- All reconciliation results stored as JSON under one reconciliation_id
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import hashlib
import uuid


# === Upload Models - Separate Tables ===

@dataclass
class InvoiceUpload:
    """Invoice file upload record - separate table with unique invoice_upload_id"""
    invoice_upload_id: Optional[int] = None  # Primary unique identifier
    file_name: str = ""
    file_path: str = ""
    file_hash: str = ""
    file_size: int = 0
    mime_type: str = ""
    
    # Processing metadata
    upload_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    processing_start: Optional[str] = None
    processing_end: Optional[str] = None
    processing_duration_seconds: Optional[int] = None
    ocr_engine: str = "tesseract"
    confidence_score: Optional[float] = None
    status: str = "pending"  # pending, processing, completed, failed
    
    # JSON column containing ALL invoice data (single row per file)
    invoice_data_json: Optional[str] = None  # Full JSON structure with all invoices from this file
    
    # Summary fields for quick queries (indexed)
    total_invoices_found: int = 0
    total_invoices_processed: int = 0
    total_amount: Optional[float] = None
    currency_summary: Optional[str] = None  # JSON string: {"USD": 85000.00, "EUR": 40000.50}
    vendor_summary: Optional[str] = None  # JSON string: {"Acme Corp": 25, "Global Tech": 15}
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BankStatementUpload:
    """Bank statement file upload record - separate table with unique bank_upload_id"""
    bank_upload_id: Optional[int] = None  # Primary unique identifier
    file_name: str = ""
    file_path: str = ""
    file_hash: str = ""
    file_size: int = 0
    mime_type: str = ""
    
    # Processing metadata
    upload_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    processing_start: Optional[str] = None
    processing_end: Optional[str] = None
    processing_duration_seconds: Optional[int] = None
    ocr_engine: str = "tesseract"
    confidence_score: Optional[float] = None
    status: str = "pending"  # pending, processing, completed, failed
    
    # JSON column containing ALL transaction data (single row per file)
    bank_data_json: Optional[str] = None  # Full JSON structure with all transactions from this file
    
    # Statement summary fields (indexed)
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    statement_period_start: Optional[str] = None
    statement_period_end: Optional[str] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    total_debits: Optional[float] = None
    total_credits: Optional[float] = None
    currency: str = "USD"
    statement_type: Optional[str] = None
    
    # Transaction summary fields (indexed)
    total_transactions_found: int = 0
    total_transactions_processed: int = 0
    transaction_type_summary: Optional[str] = None  # JSON string: {"card_transaction": 180, "transfer": 85}
    
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ReconciliationRecord:
    """Reconciliation record - stores both upload IDs with all results in JSON"""
    reconciliation_id: Optional[int] = None  # Primary unique identifier
    
    # Source document references - CORE REQUIREMENT
    invoice_upload_id: Optional[int] = None  # Links to invoice_uploads.invoice_upload_id
    bank_upload_id: Optional[int] = None     # Links to bank_statement_uploads.bank_upload_id
    
    # File names for accountant reference
    invoice_file_name: Optional[str] = None
    bank_file_name: Optional[str] = None
    
    # Reconciliation metadata
    reconciliation_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reconciliation_duration_seconds: Optional[int] = None
    matching_algorithm: str = "hybrid_ml_rule_based"
    confidence_threshold: float = 0.75
    status: str = "pending"  # pending, processing, completed, failed
    
    # JSON column containing ALL reconciliation results (single row per reconciliation)
    reconciliation_results_json: Optional[str] = None  # Full JSON structure with all matches
    
    # Summary fields for quick queries (indexed)
    total_invoices_processed: int = 0
    total_transactions_processed: int = 0
    total_matches_found: int = 0
    partial_matches: int = 0
    unmatched_invoices: int = 0
    unmatched_transactions: int = 0
    total_amount_matched: Optional[float] = None
    match_rate_percentage: Optional[float] = None
    
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# === Database Schema Definitions ===

# Invoice uploads table - separate from bank statements
CREATE_INVOICE_UPLOADS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_uploads (
    invoice_upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    
    -- Processing metadata
    upload_timestamp TEXT NOT NULL,
    processing_start TEXT,
    processing_end TEXT,
    processing_duration_seconds INTEGER,
    ocr_engine TEXT DEFAULT 'tesseract',
    confidence_score REAL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    
    -- JSON column containing ALL invoice data (core requirement)
    invoice_data_json TEXT,  -- Full JSON structure with all invoices from this file
    
    -- Summary fields for quick queries (indexed)
    total_invoices_found INTEGER DEFAULT 0,
    total_invoices_processed INTEGER DEFAULT 0,
    total_amount REAL,
    currency_summary TEXT,  -- JSON string: {"USD": 85000.00, "EUR": 40000.50}
    vendor_summary TEXT,     -- JSON string: {"Acme Corp": 25, "Global Tech": 15}
    date_range_start TEXT,
    date_range_end TEXT,
    
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique constraint on file hash to prevent duplicates
    UNIQUE(file_hash)
);
"""

# Bank statement uploads table - separate from invoices
CREATE_BANK_STATEMENT_UPLOADS_TABLE = """
CREATE TABLE IF NOT EXISTS bank_statement_uploads (
    bank_upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    
    -- Processing metadata
    upload_timestamp TEXT NOT NULL,
    processing_start TEXT,
    processing_end TEXT,
    processing_duration_seconds INTEGER,
    ocr_engine TEXT DEFAULT 'tesseract',
    confidence_score REAL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    
    -- JSON column containing ALL transaction data (core requirement)
    bank_data_json TEXT,  -- Full JSON structure with all transactions from this file
    
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
    transaction_type_summary TEXT,  -- JSON string: {"card_transaction": 180, "transfer": 85}
    
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique constraint on file hash to prevent duplicates
    UNIQUE(file_hash)
);
"""

# Reconciliation table - links both upload IDs together
CREATE_RECONCILIATION_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS reconciliation_records (
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
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    
    -- JSON column containing ALL reconciliation results (core requirement)
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
"""

# Production indexes for performance
CREATE_SEPARATE_UPLOAD_INDEXES = [
    # Invoice uploads indexes
    "CREATE INDEX IF NOT EXISTS idx_invoice_uploads_hash ON invoice_uploads(file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_invoice_uploads_status ON invoice_uploads(status);",
    "CREATE INDEX IF NOT EXISTS idx_invoice_uploads_timestamp ON invoice_uploads(upload_timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_invoice_uploads_total_amount ON invoice_uploads(total_amount);",
    "CREATE INDEX IF NOT EXISTS idx_invoice_uploads_date_range ON invoice_uploads(date_range_start, date_range_end);",
    
    # Bank statement uploads indexes
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_hash ON bank_statement_uploads(file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_status ON bank_statement_uploads(status);",
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_timestamp ON bank_statement_uploads(upload_timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_account ON bank_statement_uploads(account_number);",
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_period ON bank_statement_uploads(statement_period_start, statement_period_end);",
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_total_debits ON bank_statement_uploads(total_debits);",
    "CREATE INDEX IF NOT EXISTS idx_bank_uploads_total_credits ON bank_statement_uploads(total_credits);",
    
    # Reconciliation records indexes
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_invoice_upload ON reconciliation_records(invoice_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_bank_upload ON reconciliation_records(bank_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_timestamp ON reconciliation_records(reconciliation_timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_status ON reconciliation_records(status);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_match_rate ON reconciliation_records(match_rate_percentage);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_total_matched ON reconciliation_records(total_amount_matched);"
]


# === JSON Structure Examples ===

# Example Invoice Data JSON (stored in invoice_uploads.invoice_data_json)
INVOICE_DATA_JSON_EXAMPLE = {
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
            "vendor_address": "123 Business St, City, State",
            "customer_name": "Global Company Inc",
            "subtotal": 1000.00,
            "tax_total": 80.00,
            "total_amount": 1080.00,
            "currency": "USD",
            "payment_terms": "Net 30",
            "purchase_order": "PO-2024-001",
            "page_number": 1,
            "confidence_score": 0.95,
            "line_items": [
                {
                    "item_code": "PROD-001",
                    "description": "Professional Services",
                    "quantity": 10,
                    "unit_price": 100.00,
                    "total_amount": 1000.00,
                    "tax_rate": 0.08,
                    "tax_amount": 80.00
                }
            ]
        }
        # ... 99 more invoice objects
    ]
}

# Example Bank Data JSON (stored in bank_statement_uploads.bank_data_json)
BANK_DATA_JSON_EXAMPLE = {
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
        "branch_name": "Downtown Branch",
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
            "credit_amount": None,
            "balance": 49750.00,
            "currency": "USD",
            "transaction_type": "card_transaction",
            "reference_number": "REF-001",
            "category": "Software/Cloud Services",
            "page_number": 1,
            "confidence_score": 0.94
        }
        # ... 341 more transaction objects
    ]
}

# Example Reconciliation Results JSON (stored in reconciliation_records.reconciliation_results_json)
RECONCILIATION_RESULTS_JSON_EXAMPLE = {
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
                "amount_match": True,
                "date_match": True,
                "vendor_match": True,
                "reference_match": True
            }
        }
        # ... 84 more matched objects
    ],
    "partial": [
        {
            "match_id": "partial_001",
            "match_score": 0.65,
            "match_type": "partial",
            "invoice": {
                "invoice_id": "inv_023",
                "invoice_number": "INV-2024-023",
                "invoice_date": "2024-01-12",
                "vendor_name": "Partial Match Corp",
                "total_amount": 500.00,
                "currency": "USD"
            },
            "bank_transaction": {
                "transaction_id": "txn_127",
                "transaction_date": "2024-01-13",
                "description": "Card Transaction: Partial Match",
                "debit_amount": 450.00,
                "currency": "USD"
            },
            "matching_criteria": {
                "amount_match": False,  # $500 vs $450
                "date_match": True,
                "vendor_match": True,
                "reference_match": False
            },
            "discrepancy": {
                "amount_difference": 50.00,
                "date_difference_days": 1,
                "issues": ["Amount mismatch ($50 difference)", "Date difference (1 day)"]
            }
        }
        # ... 11 more partial matches
    ],
    "unmatched": {
        "invoices": [
            {
                "invoice_id": "inv_045",
                "invoice_number": "INV-2024-045",
                "invoice_date": "2024-01-20",
                "vendor_name": "Unmatched Vendor",
                "total_amount": 750.00,
                "currency": "USD",
                "unmatched_reason": "No corresponding bank transaction found"
            }
            # ... 14 more unmatched invoices
        ],
        "bank_transactions": [
            {
                "transaction_id": "txn_201",
                "transaction_date": "2024-01-25",
                "description": "Card Transaction: Unknown Vendor",
                "debit_amount": 125.00,
                "currency": "USD",
                "unmatched_reason": "No corresponding invoice found"
            }
            # ... 256 more unmatched transactions
        ]
    }
}


# === Utility Functions ===

def generate_unique_upload_id() -> int:
    """Generate unique upload ID for both invoice and bank uploads"""
    return int(uuid.uuid4().hex[:8], 16)

def generate_unique_reconciliation_id() -> int:
    """Generate unique reconciliation ID"""
    return int(uuid.uuid4().hex[:8], 16)

def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of file"""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return f"sha256:{hash_sha256.hexdigest()}"

def validate_separate_upload_json_structure(json_string: str, expected_type: str) -> tuple[bool, str]:
    """
    Validate JSON structure for separate upload model
    Returns (is_valid, error_message)
    """
    if not json_string:
        return False, "JSON string is empty"
    
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}"
    
    # Validate based on expected type
    if expected_type == "invoice":
        required_keys = ["upload_info", "processing_info", "extraction_summary", "invoices"]
        if not all(key in data for key in required_keys):
            missing = [key for key in required_keys if key not in data]
            return False, f"Missing required keys: {missing}"
        
        if not isinstance(data["invoices"], list):
            return False, "invoices must be an array"
            
    elif expected_type == "bank":
        required_keys = ["upload_info", "processing_info", "statement_info", "extraction_summary", "transactions"]
        if not all(key in data for key in required_keys):
            missing = [key for key in required_keys if key not in data]
            return False, f"Missing required keys: {missing}"
        
        if not isinstance(data["transactions"], list):
            return False, "transactions must be an array"
            
    elif expected_type == "reconciliation":
        required_keys = ["reconciliation_info", "source_documents", "reconciliation_summary", "matched", "partial", "unmatched"]
        if not all(key in data for key in required_keys):
            missing = [key for key in required_keys if key not in data]
            return False, f"Missing required keys: {missing}"
        
        if not isinstance(data["matched"], list):
            return False, "matched must be an array"
        if not isinstance(data["partial"], list):
            return False, "partial must be an array"
        if not isinstance(data["unmatched"], dict):
            return False, "unmatched must be an object"
    
    return True, "JSON structure is valid"

def get_separate_upload_schema_statements():
    """Get all schema statements for separate upload model"""
    statements = [
        CREATE_INVOICE_UPLOADS_TABLE,
        CREATE_BANK_STATEMENT_UPLOADS_TABLE,
        CREATE_RECONCILIATION_RECORDS_TABLE
    ]
    statements.extend(CREATE_SEPARATE_UPLOAD_INDEXES)
    return statements


# === Data Access Layer ===

class SeparateUploadDataAccess:
    """Data access layer for separate upload model with clear traceability"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def init_separate_upload_tables(self):
        """Initialize separate upload tables with proper constraints"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        
        statements = get_separate_upload_schema_statements()
        for statement in statements:
            try:
                conn.execute(statement)
            except sqlite3.Error as e:
                print(f"Error executing statement: {e}")
                print(f"Statement: {statement}")
        
        conn.commit()
        conn.close()
        print("✓ Separate upload reconciliation tables initialized")
    
    def insert_invoice_upload(self, upload: InvoiceUpload) -> int:
        """Insert invoice upload with validation"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        # Validate JSON before insertion
        if upload.invoice_data_json:
            is_valid, error_msg = validate_separate_upload_json_structure(upload.invoice_data_json, "invoice")
            if not is_valid:
                raise ValueError(f"Invalid invoice JSON structure: {error_msg}")
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO invoice_uploads (
                    file_name, file_path, file_hash, file_size, mime_type,
                    upload_timestamp, processing_start, processing_end, processing_duration_seconds,
                    ocr_engine, confidence_score, status, invoice_data_json,
                    total_invoices_found, total_invoices_processed, total_amount,
                    currency_summary, vendor_summary, date_range_start, date_range_end,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                upload.file_name, upload.file_path, upload.file_hash, upload.file_size, upload.mime_type,
                upload.upload_timestamp, upload.processing_start, upload.processing_end,
                upload.processing_duration_seconds, upload.ocr_engine, upload.confidence_score,
                upload.status, upload.invoice_data_json,
                upload.total_invoices_found, upload.total_invoices_processed, upload.total_amount,
                upload.currency_summary, upload.vendor_summary, upload.date_range_start, upload.date_range_end,
                upload.error_message, upload.created_at, upload.updated_at
            ))
            
            invoice_upload_id = cursor.lastrowid
            conn.commit()
            return invoice_upload_id
            
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def insert_bank_upload(self, upload: BankStatementUpload) -> int:
        """Insert bank upload with validation"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        # Validate JSON before insertion
        if upload.bank_data_json:
            is_valid, error_msg = validate_separate_upload_json_structure(upload.bank_data_json, "bank")
            if not is_valid:
                raise ValueError(f"Invalid bank JSON structure: {error_msg}")
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bank_statement_uploads (
                    file_name, file_path, file_hash, file_size, mime_type,
                    upload_timestamp, processing_start, processing_end, processing_duration_seconds,
                    ocr_engine, confidence_score, status, bank_data_json,
                    account_number, account_name, bank_name, statement_period_start, statement_period_end,
                    opening_balance, closing_balance, total_debits, total_credits, currency, statement_type,
                    total_transactions_found, total_transactions_processed, transaction_type_summary,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                upload.file_name, upload.file_path, upload.file_hash, upload.file_size, upload.mime_type,
                upload.upload_timestamp, upload.processing_start, upload.processing_end,
                upload.processing_duration_seconds, upload.ocr_engine, upload.confidence_score,
                upload.status, upload.bank_data_json,
                upload.account_number, upload.account_name, upload.bank_name,
                upload.statement_period_start, upload.statement_period_end,
                upload.opening_balance, upload.closing_balance, upload.total_debits, upload.total_credits,
                upload.currency, upload.statement_type,
                upload.total_transactions_found, upload.total_transactions_processed,
                upload.transaction_type_summary,
                upload.error_message, upload.created_at, upload.updated_at
            ))
            
            bank_upload_id = cursor.lastrowid
            conn.commit()
            return bank_upload_id
            
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def insert_reconciliation_record(self, record: ReconciliationRecord) -> int:
        """Insert reconciliation record with both upload IDs and validation"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        # Validate JSON before insertion
        if record.reconciliation_results_json:
            is_valid, error_msg = validate_separate_upload_json_structure(record.reconciliation_results_json, "reconciliation")
            if not is_valid:
                raise ValueError(f"Invalid reconciliation JSON structure: {error_msg}")
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reconciliation_records (
                    invoice_upload_id, bank_upload_id, invoice_file_name, bank_file_name,
                    reconciliation_timestamp, reconciliation_duration_seconds, matching_algorithm,
                    confidence_threshold, status, reconciliation_results_json,
                    total_invoices_processed, total_transactions_processed, total_matches_found,
                    partial_matches, unmatched_invoices, unmatched_transactions, total_amount_matched,
                    match_rate_percentage, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.invoice_upload_id, record.bank_upload_id, record.invoice_file_name, record.bank_file_name,
                record.reconciliation_timestamp, record.reconciliation_duration_seconds,
                record.matching_algorithm, record.confidence_threshold, record.status,
                record.reconciliation_results_json,
                record.total_invoices_processed, record.total_transactions_processed,
                record.total_matches_found, record.partial_matches, record.unmatched_invoices,
                record.unmatched_transactions, record.total_amount_matched, record.match_rate_percentage,
                record.error_message, record.created_at, record.updated_at
            ))
            
            reconciliation_id = cursor.lastrowid
            conn.commit()
            return reconciliation_id
            
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_reconciliation_with_sources(self, reconciliation_id: int) -> Dict[str, Any]:
        """Get reconciliation record with full source document information"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    rr.*,
                    iu.file_name as invoice_file_name_full,
                    iu.upload_timestamp as invoice_upload_timestamp,
                    bu.file_name as bank_file_name_full,
                    bu.upload_timestamp as bank_upload_timestamp
                FROM reconciliation_records rr
                LEFT JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
                LEFT JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
                WHERE rr.reconciliation_id = ?
            """, (reconciliation_id,))
            
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
            
        except sqlite3.Error as e:
            raise e
        finally:
            conn.close()
    
    def get_reconciliation_traceability_report(self, invoice_upload_id: Optional[int] = None, 
                                            bank_upload_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get traceability report for accountant - shows which documents were reconciled together"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        try:
            cursor = conn.cursor()
            
            if invoice_upload_id:
                cursor.execute("""
                    SELECT 
                        rr.reconciliation_id,
                        rr.reconciliation_timestamp,
                        rr.total_matches_found,
                        rr.match_rate_percentage,
                        rr.status,
                        iu.file_name as invoice_file_name,
                        iu.upload_timestamp as invoice_upload_timestamp,
                        bu.file_name as bank_file_name,
                        bu.upload_timestamp as bank_upload_timestamp,
                        bu.account_number,
                        bu.bank_name
                    FROM reconciliation_records rr
                    JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
                    JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
                    WHERE rr.invoice_upload_id = ?
                    ORDER BY rr.reconciliation_timestamp DESC
                """, (invoice_upload_id,))
            elif bank_upload_id:
                cursor.execute("""
                    SELECT 
                        rr.reconciliation_id,
                        rr.reconciliation_timestamp,
                        rr.total_matches_found,
                        rr.match_rate_percentage,
                        rr.status,
                        iu.file_name as invoice_file_name,
                        iu.upload_timestamp as invoice_upload_timestamp,
                        bu.file_name as bank_file_name,
                        bu.upload_timestamp as bank_upload_timestamp,
                        bu.account_number,
                        bu.bank_name
                    FROM reconciliation_records rr
                    JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
                    JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
                    WHERE rr.bank_upload_id = ?
                    ORDER BY rr.reconciliation_timestamp DESC
                """, (bank_upload_id,))
            else:
                cursor.execute("""
                    SELECT 
                        rr.reconciliation_id,
                        rr.reconciliation_timestamp,
                        rr.total_matches_found,
                        rr.match_rate_percentage,
                        rr.status,
                        iu.file_name as invoice_file_name,
                        iu.upload_timestamp as invoice_upload_timestamp,
                        bu.file_name as bank_file_name,
                        bu.upload_timestamp as bank_upload_timestamp,
                        bu.account_number,
                        bu.bank_name
                    FROM reconciliation_records rr
                    JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
                    JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
                    ORDER BY rr.reconciliation_timestamp DESC
                    LIMIT 100
                """)
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
            
        except sqlite3.Error as e:
            raise e
        finally:
            conn.close()
