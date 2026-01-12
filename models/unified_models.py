"""
Unified Document Processing Models
Production-ready data models for both invoices and bank statements
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

# === Base Models ===

@dataclass
class BaseDocumentUpload:
    """Base model for all document uploads"""
    id: Optional[int] = None
    file_name: str = ""
    file_path: str = ""
    file_hash: str = ""
    file_size: int = 0
    file_type: str = ""
    mime_type: str = ""
    document_type: str = ""  # 'invoice' or 'bank_statement'
    upload_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    processing_status: str = "pending"  # pending, processing, completed, failed
    processing_start_time: Optional[str] = None
    processing_end_time: Optional[str] = None
    total_documents_found: int = 0  # invoices or statements found
    total_documents_processed: int = 0
    total_amount: Optional[float] = None
    currency_summary: Dict[str, float] = field(default_factory=dict)
    extraction_confidence: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class BaseProcessingJob:
    """Base model for processing jobs"""
    job_id: str = ""
    document_upload_id: int = 0
    document_type: str = ""  # 'invoice' or 'bank_statement'
    status: str = "queued"  # queued, processing, completed, failed, cancelled
    progress: float = 0.0  # 0.0 to 1.0
    current_step: str = ""
    estimated_time_remaining: Optional[int] = None  # seconds
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    result_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

# === Invoice Models ===

@dataclass
class InvoiceLineItem:
    """Line item within an invoice"""
    id: Optional[int] = None
    extracted_invoice_id: int = 0
    description: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_amount: Optional[float] = None
    item_code: Optional[str] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class ExtractedInvoice:
    """Individual invoice extracted from a file"""
    id: Optional[int] = None
    document_upload_id: int = 0
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_tax_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    customer_tax_id: Optional[str] = None
    subtotal: Optional[float] = None
    tax_total: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "USD"
    payment_terms: Optional[str] = None
    purchase_order: Optional[str] = None
    raw_text: Optional[str] = None
    confidence_score: Optional[float] = None
    extraction_method: Optional[str] = None  # ocr, structured, manual
    page_number: Optional[int] = None
    bounding_box: Optional[str] = None
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

# === Bank Statement Models ===

@dataclass
class BankTransaction:
    """Individual transaction extracted from bank statement"""
    id: Optional[int] = None
    document_upload_id: int = 0
    transaction_date: Optional[str] = None
    description: Optional[str] = None
    debit_amount: Optional[float] = None
    credit_amount: Optional[float] = None
    balance: Optional[float] = None
    currency: str = "USD"
    transaction_type: Optional[str] = None  # debit, credit, transfer, etc.
    reference_number: Optional[str] = None
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None
    category: Optional[str] = None
    raw_text: Optional[str] = None
    confidence_score: Optional[float] = None
    extraction_method: Optional[str] = None
    page_number: Optional[int] = None
    statement_period_start: Optional[str] = None
    statement_period_end: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class BankStatementInfo:
    """Bank statement metadata"""
    id: Optional[int] = None
    document_upload_id: int = 0
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None
    statement_period_start: Optional[str] = None
    statement_period_end: Optional[str] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    total_debits: Optional[float] = None
    total_credits: Optional[float] = None
    currency: str = "USD"
    statement_type: Optional[str] = None  # savings, current, credit_card
    bank_statement_json: Optional[str] = None
    total_transactions: int = 0
    processing_confidence: Optional[float] = None
    extraction_method: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class BankStatementExtraction:
    """Individual bank statement extraction from a file"""
    id: Optional[int] = None
    parent_bank_statement_id: int = 0
    sequence_no: int = 0
    page_no: Optional[int] = None
    section_no: Optional[int] = None
    original_filename: Optional[str] = None
    json_file_path: Optional[str] = None
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

# === Specialized Upload Models ===

@dataclass
class InvoiceFileUpload(BaseDocumentUpload):
    """Invoice file upload record"""
    document_type: str = field(default="invoice")
    total_invoices_found: int = 0
    total_invoices_processed: int = 0
    vendor_summary: Dict[str, int] = field(default_factory=dict)
    customer_summary: Dict[str, int] = field(default_factory=dict)

@dataclass
class BankStatementFileUpload(BaseDocumentUpload):
    """Bank statement file upload record"""
    document_type: str = field(default="bank_statement")
    total_statements_found: int = 0
    total_statements_processed: int = 0
    total_transactions_found: int = 0
    total_transactions_processed: int = 0
    account_summary: Dict[str, int] = field(default_factory=dict)
    bank_summary: Dict[str, int] = field(default_factory=dict)

# === Utility Functions ===

def base_document_to_dict(doc: BaseDocumentUpload) -> Dict[str, Any]:
    """Convert base document to dictionary"""
    return {
        'id': doc.id,
        'file_name': doc.file_name,
        'file_path': doc.file_path,
        'file_hash': doc.file_hash,
        'file_size': doc.file_size,
        'file_type': doc.file_type,
        'mime_type': doc.mime_type,
        'document_type': doc.document_type,
        'upload_timestamp': doc.upload_timestamp,
        'processing_status': doc.processing_status,
        'processing_start_time': doc.processing_start_time,
        'processing_end_time': doc.processing_end_time,
        'total_documents_found': doc.total_documents_found,
        'total_documents_processed': doc.total_documents_processed,
        'total_amount': doc.total_amount,
        'currency_summary': json.dumps(doc.currency_summary),
        'extraction_confidence': doc.extraction_confidence,
        'error_message': doc.error_message,
        'metadata': json.dumps(doc.metadata),
        'created_at': doc.created_at,
        'updated_at': doc.updated_at
    }

def dict_to_base_document(data: Dict[str, Any]) -> BaseDocumentUpload:
    """Convert dictionary to base document"""
    currency_summary = {}
    if data.get('currency_summary'):
        try:
            currency_summary = json.loads(data['currency_summary'])
        except:
            pass
    
    metadata = {}
    if data.get('metadata'):
        try:
            metadata = json.loads(data['metadata'])
        except:
            pass
    
    return BaseDocumentUpload(
        id=data.get('id'),
        file_name=data.get('file_name', ''),
        file_path=data.get('file_path', ''),
        file_hash=data.get('file_hash', ''),
        file_size=data.get('file_size', 0),
        file_type=data.get('file_type', ''),
        mime_type=data.get('mime_type', ''),
        document_type=data.get('document_type', ''),
        upload_timestamp=data.get('upload_timestamp', ''),
        processing_status=data.get('processing_status', 'pending'),
        processing_start_time=data.get('processing_start_time'),
        processing_end_time=data.get('processing_end_time'),
        total_documents_found=data.get('total_documents_found', 0),
        total_documents_processed=data.get('total_documents_processed', 0),
        total_amount=data.get('total_amount'),
        currency_summary=currency_summary,
        extraction_confidence=data.get('extraction_confidence'),
        error_message=data.get('error_message'),
        metadata=metadata,
        created_at=data.get('created_at', ''),
        updated_at=data.get('updated_at', '')
    )

def invoice_to_dict(invoice: ExtractedInvoice) -> Dict[str, Any]:
    """Convert invoice to dictionary"""
    return {
        'id': invoice.id,
        'document_upload_id': invoice.document_upload_id,
        'invoice_number': invoice.invoice_number,
        'invoice_date': invoice.invoice_date,
        'due_date': invoice.due_date,
        'vendor_name': invoice.vendor_name,
        'vendor_address': invoice.vendor_address,
        'vendor_tax_id': invoice.vendor_tax_id,
        'customer_name': invoice.customer_name,
        'customer_address': invoice.customer_address,
        'customer_tax_id': invoice.customer_tax_id,
        'subtotal': invoice.subtotal,
        'tax_total': invoice.tax_total,
        'total_amount': invoice.total_amount,
        'currency': invoice.currency,
        'payment_terms': invoice.payment_terms,
        'purchase_order': invoice.purchase_order,
        'raw_text': invoice.raw_text,
        'confidence_score': invoice.confidence_score,
        'extraction_method': invoice.extraction_method,
        'page_number': invoice.page_number,
        'bounding_box': invoice.bounding_box,
        'created_at': invoice.created_at,
        'updated_at': invoice.updated_at
    }

def bank_transaction_to_dict(transaction: BankTransaction) -> Dict[str, Any]:
    """Convert bank transaction to dictionary"""
    return {
        'id': transaction.id,
        'document_upload_id': transaction.document_upload_id,
        'transaction_date': transaction.transaction_date,
        'description': transaction.description,
        'debit_amount': transaction.debit_amount,
        'credit_amount': transaction.credit_amount,
        'balance': transaction.balance,
        'currency': transaction.currency,
        'transaction_type': transaction.transaction_type,
        'reference_number': transaction.reference_number,
        'account_number': transaction.account_number,
        'account_name': transaction.account_name,
        'bank_name': transaction.bank_name,
        'branch_name': transaction.branch_name,
        'category': transaction.category,
        'raw_text': transaction.raw_text,
        'confidence_score': transaction.confidence_score,
        'extraction_method': transaction.extraction_method,
        'page_number': transaction.page_number,
        'statement_period_start': transaction.statement_period_start,
        'statement_period_end': transaction.statement_period_end,
        'created_at': transaction.created_at,
        'updated_at': transaction.updated_at
    }

def processing_job_to_dict(job: BaseProcessingJob) -> Dict[str, Any]:
    """Convert processing job to dictionary"""
    return {
        'job_id': job.job_id,
        'document_upload_id': job.document_upload_id,
        'document_type': job.document_type,
        'status': job.status,
        'progress': job.progress,
        'current_step': job.current_step,
        'estimated_time_remaining': job.estimated_time_remaining,
        'started_at': job.started_at,
        'completed_at': job.completed_at,
        'error_message': job.error_message,
        'result_data': json.dumps(job.result_data),
        'created_at': job.created_at,
        'updated_at': job.updated_at
    }

# === Database Schema ===

# Unified document uploads table
CREATE_DOCUMENT_UPLOADS_TABLE = """
CREATE TABLE IF NOT EXISTS document_uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('invoice', 'bank_statement')),
    upload_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    processing_start_time TEXT,
    processing_end_time TEXT,
    total_documents_found INTEGER DEFAULT 0,
    total_documents_processed INTEGER DEFAULT 0,
    total_amount REAL,
    currency_summary TEXT,
    extraction_confidence REAL,
    error_message TEXT,
    metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# Invoice-specific tables
CREATE_EXTRACTED_INVOICES_TABLE = """
CREATE TABLE IF NOT EXISTS extracted_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_upload_id INTEGER NOT NULL,
    invoice_number TEXT,
    invoice_date TEXT,
    due_date TEXT,
    vendor_name TEXT,
    vendor_address TEXT,
    vendor_tax_id TEXT,
    customer_name TEXT,
    customer_address TEXT,
    customer_tax_id TEXT,
    subtotal REAL,
    tax_total REAL,
    total_amount REAL,
    currency TEXT DEFAULT 'USD',
    payment_terms TEXT,
    purchase_order TEXT,
    raw_text TEXT,
    confidence_score REAL,
    extraction_method TEXT,
    page_number INTEGER,
    bounding_box TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE CASCADE
);
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
    discount_amount REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (extracted_invoice_id) REFERENCES extracted_invoices(id) ON DELETE CASCADE
);
"""

# Bank statement-specific tables
CREATE_BANK_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS bank_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_upload_id INTEGER NOT NULL,
    transaction_date TEXT,
    description TEXT,
    debit_amount REAL,
    credit_amount REAL,
    balance REAL,
    currency TEXT DEFAULT 'USD',
    transaction_type TEXT,
    reference_number TEXT,
    account_number TEXT,
    account_name TEXT,
    bank_name TEXT,
    branch_name TEXT,
    category TEXT,
    raw_text TEXT,
    confidence_score REAL,
    extraction_method TEXT,
    page_number INTEGER,
    statement_period_start TEXT,
    statement_period_end TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE CASCADE
);
"""

CREATE_BANK_STATEMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS bank_statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_upload_id INTEGER NOT NULL,
    account_number TEXT,
    account_name TEXT,
    bank_name TEXT,
    branch_name TEXT,
    statement_period_start TEXT,
    statement_period_end TEXT,
    opening_balance REAL,
    closing_balance REAL,
    total_debits REAL,
    total_credits REAL,
    currency TEXT DEFAULT 'USD',
    statement_type TEXT,
    bank_statement_json TEXT,
    total_transactions INTEGER DEFAULT 0,
    processing_confidence REAL,
    extraction_method TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE CASCADE
);
"""

CREATE_BANK_STATEMENT_EXTRACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS bank_statement_extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_bank_statement_id INTEGER NOT NULL,
    sequence_no INTEGER NOT NULL,
    page_no INTEGER,
    section_no INTEGER,
    original_filename TEXT,
    json_file_path TEXT,
    extracted_data TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_bank_statement_id) REFERENCES bank_statements(id) ON DELETE CASCADE,
    UNIQUE (parent_bank_statement_id, sequence_no)
);
"""

# Unified processing jobs table
CREATE_PROCESSING_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    document_upload_id INTEGER NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('invoice', 'bank_statement')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
    progress REAL NOT NULL DEFAULT 0.0,
    current_step TEXT,
    estimated_time_remaining INTEGER,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    result_data TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE CASCADE
);
"""

# Migration tracking
CREATE_SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name TEXT NOT NULL UNIQUE,
    executed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# Indexes for performance
CREATE_INDEXES = [
    # Document uploads indexes
    "CREATE INDEX IF NOT EXISTS idx_document_uploads_hash ON document_uploads(file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_document_uploads_type ON document_uploads(document_type);",
    "CREATE INDEX IF NOT EXISTS idx_document_uploads_status ON document_uploads(processing_status);",
    "CREATE INDEX IF NOT EXISTS idx_document_uploads_timestamp ON document_uploads(upload_timestamp);",
    
    # Invoice indexes
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_upload ON extracted_invoices(document_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_number ON extracted_invoices(invoice_number);",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_vendor ON extracted_invoices(vendor_name);",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_date ON extracted_invoices(invoice_date);",
    "CREATE INDEX IF NOT EXISTS idx_extracted_invoices_amount ON extracted_invoices(total_amount);",
    
    # Invoice line items indexes
    "CREATE INDEX IF NOT EXISTS idx_invoice_line_items_invoice ON invoice_line_items(extracted_invoice_id);",
    
    # Bank transaction indexes
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_upload ON bank_transactions(document_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_date ON bank_transactions(transaction_date);",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_account ON bank_transactions(account_number);",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_amount ON bank_transactions(debit_amount);",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_credit ON bank_transactions(credit_amount);",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_description ON bank_transactions(description);",
    
    # Bank statement indexes
    "CREATE INDEX IF NOT EXISTS idx_bank_statements_upload ON bank_statements(document_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_bank_statements_account ON bank_statements(account_number);",
    "CREATE INDEX IF NOT EXISTS idx_bank_statements_period ON bank_statements(statement_period_start, statement_period_end);",
    
    # Bank statement extractions indexes
    "CREATE INDEX IF NOT EXISTS idx_bank_statement_extractions_parent ON bank_statement_extractions(parent_bank_statement_id);",
    "CREATE INDEX IF NOT EXISTS idx_bank_statement_extractions_sequence ON bank_statement_extractions(sequence_no);",
    
    # Processing jobs indexes
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_upload ON processing_jobs(document_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_type ON processing_jobs(document_type);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);"
]

def get_unified_schema_statements():
    """Get all schema statements for unified document processing"""
    statements = [
        CREATE_DOCUMENT_UPLOADS_TABLE,
        CREATE_EXTRACTED_INVOICES_TABLE,
        CREATE_INVOICE_LINE_ITEMS_TABLE,
        CREATE_BANK_TRANSACTIONS_TABLE,
        CREATE_BANK_STATEMENTS_TABLE,
        CREATE_BANK_STATEMENT_EXTRACTIONS_TABLE,
        CREATE_PROCESSING_JOBS_TABLE,
        CREATE_SCHEMA_MIGRATIONS_TABLE
    ]
    statements.extend(CREATE_INDEXES)
    return statements
