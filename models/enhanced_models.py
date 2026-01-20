"""
Enhanced Data Models for Multi-Invoice File Processing
Provides parent-child relationship for file uploads and extracted invoices
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


@dataclass
class InvoiceLineItem:
    """Individual line item within an invoice"""
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_amount: Optional[float] = None
    item_code: Optional[str] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None


@dataclass
class ExtractedInvoice:
    """Individual invoice extracted from a multi-invoice file"""
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    reference: Optional[str] = None
    due_date: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_tax_id: Optional[str] = None
    vat_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    customer_tax_id: Optional[str] = None
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_address: Optional[str] = None
    subtotal: Optional[float] = None
    tax_total: Optional[float] = None
    total_vat_rate: Optional[float] = None
    total_zero_rated: Optional[float] = None
    total_gbp: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    payment_terms: Optional[str] = None
    purchase_order: Optional[str] = None
    line_items: List[InvoiceLineItem] = None
    raw_text: Optional[str] = None
    confidence_score: Optional[float] = None
    extraction_method: Optional[str] = None  # "ocr", "structured", "hybrid"
    page_number: Optional[int] = None
    bounding_box: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.line_items is None:
            self.line_items = []


@dataclass
class FileUpload:
    """Parent record for uploaded files containing multiple invoices"""
    id: Optional[int] = None
    file_name: str = ""
    file_path: str = ""
    file_hash: str = ""
    file_size: int = 0
    file_type: str = ""  # "pdf", "excel", "image"
    mime_type: str = ""
    upload_timestamp: str = ""
    processing_status: str = "pending"  # "pending", "processing", "completed", "failed"
    processing_start_time: Optional[str] = None
    processing_end_time: Optional[str] = None
    total_invoices_found: int = 0
    total_invoices_processed: int = 0
    total_amount: Optional[float] = None
    currency_summary: Dict[str, float] = None
    extraction_confidence: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.currency_summary is None:
            self.currency_summary = {}
        if self.metadata is None:
            self.metadata = {}
        if not self.upload_timestamp:
            self.upload_timestamp = datetime.now().isoformat()


@dataclass
class ProcessingJob:
    """Background processing job for file uploads"""
    job_id: str
    file_upload_id: int
    status: str = "queued"  # "queued", "processing", "completed", "failed", "cancelled"
    progress: float = 0.0
    current_step: str = ""
    estimated_time_remaining: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    result_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.result_data is None:
            self.result_data = {}


# Database schema definitions
CREATE_FILE_UPLOADS_TABLE = """
CREATE TABLE IF NOT EXISTS file_uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    file_size INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    upload_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    processing_start_time TEXT,
    processing_end_time TEXT,
    total_invoices_found INTEGER DEFAULT 0,
    total_invoices_processed INTEGER DEFAULT 0,
    total_amount REAL,
    currency_summary TEXT,  -- JSON string
    extraction_confidence REAL,
    error_message TEXT,
    metadata TEXT,  -- JSON string
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_EXTRACTED_INVOICES_TABLE = """
CREATE TABLE IF NOT EXISTS extracted_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_upload_id INTEGER NOT NULL,
    invoice_number TEXT,
    invoice_date TEXT,
    reference TEXT,
    due_date TEXT,
    vendor_name TEXT,
    vendor_address TEXT,
    vendor_tax_id TEXT,
    vat_number TEXT,
    customer_name TEXT,
    customer_address TEXT,
    customer_tax_id TEXT,
    subtotal REAL,
    tax_total REAL,
    total_vat_rate REAL,
    total_zero_rated REAL,
    total_gbp REAL,
    total_amount REAL,
    currency TEXT,
    payment_terms TEXT,
    purchase_order TEXT,
    raw_text TEXT,
    confidence_score REAL,
    extraction_method TEXT,
    page_number INTEGER,
    bounding_box TEXT,  -- JSON string
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_upload_id) REFERENCES file_uploads (id) ON DELETE CASCADE
)
"""

CREATE_INVOICE_LINE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extracted_invoice_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity REAL,
    unit_price REAL,
    total_amount REAL,
    item_code TEXT,
    tax_rate REAL,
    tax_amount REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (extracted_invoice_id) REFERENCES extracted_invoices (id) ON DELETE CASCADE
)
"""

CREATE_PROCESSING_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    file_upload_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0.0,
    current_step TEXT,
    estimated_time_remaining INTEGER,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    result_data TEXT,  -- JSON string
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_upload_id) REFERENCES file_uploads (id) ON DELETE CASCADE
)
"""

# Indexes for performance optimization
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_file_uploads_hash ON file_uploads(file_hash)",
    "CREATE INDEX IF NOT EXISTS idx_file_uploads_status ON file_uploads(processing_status)",
    "CREATE INDEX IF NOT EXISTS idx_file_uploads_upload_date ON file_uploads(upload_timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_file_upload ON extracted_invoices(file_upload_id)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_number ON extracted_invoices(invoice_number)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_date ON extracted_invoices(invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_vendor ON extracted_invoices(vendor_name)",
    "CREATE INDEX IF NOT EXISTS idx_line_items_invoice ON invoice_line_items(extracted_invoice_id)",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_file_upload ON processing_jobs(file_upload_id)"
]

# Migration statements for existing transactions table
MIGRATE_EXISTING_TRANSACTIONS = """
-- Add file_upload_id column to existing transactions table for backward compatibility
ALTER TABLE transactions ADD COLUMN file_upload_id INTEGER;

-- Create foreign key relationship (SQLite doesn't enforce FK constraints but this helps with data integrity)
-- Note: This is for documentation purposes as SQLite has limited FK support
"""

def get_all_schema_statements():
    """Return all SQL statements needed to create the enhanced schema"""
    statements = [
        CREATE_FILE_UPLOADS_TABLE,
        CREATE_EXTRACTED_INVOICES_TABLE,
        CREATE_INVOICE_LINE_ITEMS_TABLE,
        CREATE_PROCESSING_JOBS_TABLE
    ]
    statements.extend(CREATE_INDEXES)
    return statements


# Utility functions for data conversion
def file_upload_to_dict(file_upload: FileUpload) -> Dict[str, Any]:
    """Convert FileUpload to dictionary for JSON serialization"""
    data = asdict(file_upload)
    # Convert complex objects to JSON strings
    if data['currency_summary']:
        data['currency_summary'] = json.dumps(data['currency_summary'])
    if data['metadata']:
        data['metadata'] = json.dumps(data['metadata'])
    return data


def dict_to_file_upload(data: Dict[str, Any]) -> FileUpload:
    """Convert dictionary to FileUpload object"""
    # Parse JSON strings back to objects
    if data.get('currency_summary') and isinstance(data['currency_summary'], str):
        data['currency_summary'] = json.loads(data['currency_summary'])
    if data.get('metadata') and isinstance(data['metadata'], str):
        data['metadata'] = json.loads(data['metadata'])
    return FileUpload(**data)


def extracted_invoice_to_dict(invoice: ExtractedInvoice) -> Dict[str, Any]:
    """Convert ExtractedInvoice to dictionary for database storage"""
    data = asdict(invoice)
    # Convert complex objects to JSON strings
    if data['bounding_box']:
        data['bounding_box'] = json.dumps(data['bounding_box'])
    return data


def dict_to_extracted_invoice(data: Dict[str, Any]) -> ExtractedInvoice:
    """Convert dictionary to ExtractedInvoice object"""
    # Parse JSON strings back to objects
    if data.get('bounding_box') and isinstance(data['bounding_box'], str):
        data['bounding_box'] = json.loads(data['bounding_box'])
    return ExtractedInvoice(**data)
