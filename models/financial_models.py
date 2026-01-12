"""
Financial Data Processing System - Production Models
Unified parent-child architecture for invoices, bank statements, and reconciliation
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
    total_documents_found: int = 0
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
    document_type: str = ""
    job_type: str = ""  # 'upload_processing' or 'reconciliation'
    status: str = "queued"  # queued, processing, completed, failed, cancelled
    progress: float = 0.0
    current_step: str = ""
    estimated_time_remaining: Optional[int] = None
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
    extraction_method: Optional[str] = None
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
    transaction_type: Optional[str] = None
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
    statement_type: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

# === Reconciliation Models ===

@dataclass
class ReconciliationMatch:
    """Individual match within a reconciliation"""
    id: Optional[int] = None
    reconciliation_id: int = 0
    match_type: str = ""  # 'exact', 'partial', 'manual'
    match_score: Optional[float] = None
    confidence_level: Optional[str] = None  # 'high', 'medium', 'low'
    
    # Invoice reference
    invoice_upload_id: Optional[int] = None
    extracted_invoice_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_amount: Optional[float] = None
    invoice_date: Optional[str] = None
    invoice_vendor: Optional[str] = None
    
    # Bank transaction reference
    bank_upload_id: Optional[int] = None
    bank_transaction_id: Optional[int] = None
    transaction_amount: Optional[float] = None
    transaction_date: Optional[str] = None
    transaction_description: Optional[str] = None
    transaction_reference: Optional[str] = None
    
    # Match details
    amount_difference: Optional[float] = None
    date_difference_days: Optional[int] = None
    matching_rules: List[str] = field(default_factory=list)
    manual_notes: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class UnmatchedItem:
    """Unmatched invoice or transaction"""
    id: Optional[int] = None
    reconciliation_id: int = 0
    item_type: str = ""  # 'invoice' or 'transaction'
    upload_id: Optional[int] = None
    item_id: Optional[int] = None
    item_reference: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    description: Optional[str] = None
    vendor_name: Optional[str] = None
    unmatched_reason: Optional[str] = None
    suggested_matches: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class FinancialReconciliation:
    """Parent reconciliation record"""
    id: Optional[int] = None
    reconciliation_number: str = ""
    invoice_upload_id: Optional[int] = None
    bank_upload_id: Optional[int] = None
    
    # Reconciliation metadata
    reconciliation_date: str = field(default_factory=lambda: datetime.now().isoformat())
    reconciliation_type: str = "automatic"  # automatic, manual, hybrid
    status: str = "pending"  # pending, processing, completed, failed, reviewed
    
    # Processing details
    processing_job_id: Optional[str] = None
    processing_start_time: Optional[str] = None
    processing_end_time: Optional[str] = None
    processing_duration_seconds: Optional[int] = None
    
    # Summary statistics
    total_invoices: int = 0
    total_transactions: int = 0
    exact_matches: int = 0
    partial_matches: int = 0
    manual_matches: int = 0
    unmatched_invoices: int = 0
    unmatched_transactions: int = 0
    
    # Financial summary
    total_invoice_amount: Optional[float] = None
    total_transaction_amount: Optional[float] = None
    matched_amount: Optional[float] = None
    unmatched_amount: Optional[float] = None
    variance_amount: Optional[float] = None
    
    # Currency and confidence
    primary_currency: str = "USD"
    overall_confidence_score: Optional[float] = None
    
    # Configuration and rules
    matching_rules_config: Dict[str, Any] = field(default_factory=dict)
    tolerance_settings: Dict[str, Any] = field(default_factory=dict)
    
    # Review and approval
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    review_notes: Optional[str] = None
    
    # Error handling
    error_message: Optional[str] = None
    warning_messages: List[str] = field(default_factory=list)
    
    # Metadata
    created_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Child relationships
    matches: List[ReconciliationMatch] = field(default_factory=list)
    unmatched_items: List[UnmatchedItem] = field(default_factory=list)

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

def reconciliation_to_dict(reconciliation: FinancialReconciliation) -> Dict[str, Any]:
    """Convert reconciliation to dictionary"""
    return {
        'id': reconciliation.id,
        'reconciliation_number': reconciliation.reconciliation_number,
        'invoice_upload_id': reconciliation.invoice_upload_id,
        'bank_upload_id': reconciliation.bank_upload_id,
        'reconciliation_date': reconciliation.reconciliation_date,
        'reconciliation_type': reconciliation.reconciliation_type,
        'status': reconciliation.status,
        'processing_job_id': reconciliation.processing_job_id,
        'processing_start_time': reconciliation.processing_start_time,
        'processing_end_time': reconciliation.processing_end_time,
        'processing_duration_seconds': reconciliation.processing_duration_seconds,
        'total_invoices': reconciliation.total_invoices,
        'total_transactions': reconciliation.total_transactions,
        'exact_matches': reconciliation.exact_matches,
        'partial_matches': reconciliation.partial_matches,
        'manual_matches': reconciliation.manual_matches,
        'unmatched_invoices': reconciliation.unmatched_invoices,
        'unmatched_transactions': reconciliation.unmatched_transactions,
        'total_invoice_amount': reconciliation.total_invoice_amount,
        'total_transaction_amount': reconciliation.total_transaction_amount,
        'matched_amount': reconciliation.matched_amount,
        'unmatched_amount': reconciliation.unmatched_amount,
        'variance_amount': reconciliation.variance_amount,
        'primary_currency': reconciliation.primary_currency,
        'overall_confidence_score': reconciliation.overall_confidence_score,
        'matching_rules_config': json.dumps(reconciliation.matching_rules_config),
        'tolerance_settings': json.dumps(reconciliation.tolerance_settings),
        'reviewed_by': reconciliation.reviewed_by,
        'reviewed_at': reconciliation.reviewed_at,
        'approved_by': reconciliation.approved_by,
        'approved_at': reconciliation.approved_at,
        'review_notes': reconciliation.review_notes,
        'error_message': reconciliation.error_message,
        'warning_messages': json.dumps(reconciliation.warning_messages),
        'created_by': reconciliation.created_by,
        'created_at': reconciliation.created_at,
        'updated_at': reconciliation.updated_at
    }

def reconciliation_match_to_dict(match: ReconciliationMatch) -> Dict[str, Any]:
    """Convert reconciliation match to dictionary"""
    return {
        'id': match.id,
        'reconciliation_id': match.reconciliation_id,
        'match_type': match.match_type,
        'match_score': match.match_score,
        'confidence_level': match.confidence_level,
        'invoice_upload_id': match.invoice_upload_id,
        'extracted_invoice_id': match.extracted_invoice_id,
        'invoice_number': match.invoice_number,
        'invoice_amount': match.invoice_amount,
        'invoice_date': match.invoice_date,
        'invoice_vendor': match.invoice_vendor,
        'bank_upload_id': match.bank_upload_id,
        'bank_transaction_id': match.bank_transaction_id,
        'transaction_amount': match.transaction_amount,
        'transaction_date': match.transaction_date,
        'transaction_description': match.transaction_description,
        'transaction_reference': match.transaction_reference,
        'amount_difference': match.amount_difference,
        'date_difference_days': match.date_difference_days,
        'matching_rules': json.dumps(match.matching_rules),
        'manual_notes': match.manual_notes,
        'verified_by': match.verified_by,
        'verified_at': match.verified_at,
        'created_at': match.created_at,
        'updated_at': match.updated_at
    }

def unmatched_item_to_dict(item: UnmatchedItem) -> Dict[str, Any]:
    """Convert unmatched item to dictionary"""
    return {
        'id': item.id,
        'reconciliation_id': item.reconciliation_id,
        'item_type': item.item_type,
        'upload_id': item.upload_id,
        'item_id': item.item_id,
        'item_reference': item.item_reference,
        'amount': item.amount,
        'date': item.date,
        'description': item.description,
        'vendor_name': item.vendor_name,
        'unmatched_reason': item.unmatched_reason,
        'suggested_matches': json.dumps(item.suggested_matches),
        'created_at': item.created_at,
        'updated_at': item.updated_at
    }

# === Database Schema ===

# Document uploads table (unified parent for invoices and bank statements)
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE CASCADE
);
"""

# Reconciliation tables (parent-child architecture)
CREATE_FINANCIAL_RECONCILIATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS financial_reconciliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_number TEXT NOT NULL UNIQUE,
    invoice_upload_id INTEGER,
    bank_upload_id INTEGER,
    reconciliation_date TEXT NOT NULL,
    reconciliation_type TEXT NOT NULL DEFAULT 'automatic' CHECK (reconciliation_type IN ('automatic', 'manual', 'hybrid')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'reviewed')),
    processing_job_id TEXT,
    processing_start_time TEXT,
    processing_end_time TEXT,
    processing_duration_seconds INTEGER,
    total_invoices INTEGER DEFAULT 0,
    total_transactions INTEGER DEFAULT 0,
    exact_matches INTEGER DEFAULT 0,
    partial_matches INTEGER DEFAULT 0,
    manual_matches INTEGER DEFAULT 0,
    unmatched_invoices INTEGER DEFAULT 0,
    unmatched_transactions INTEGER DEFAULT 0,
    total_invoice_amount REAL,
    total_transaction_amount REAL,
    matched_amount REAL,
    unmatched_amount REAL,
    variance_amount REAL,
    primary_currency TEXT DEFAULT 'USD',
    overall_confidence_score REAL,
    matching_rules_config TEXT,
    tolerance_settings TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    approved_by TEXT,
    approved_at TEXT,
    review_notes TEXT,
    error_message TEXT,
    warning_messages TEXT,
    created_by TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL,
    FOREIGN KEY (bank_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL
);
"""

CREATE_RECONCILIATION_MATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS reconciliation_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id INTEGER NOT NULL,
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'partial', 'manual')),
    match_score REAL,
    confidence_level TEXT CHECK (confidence_level IN ('high', 'medium', 'low')),
    invoice_upload_id INTEGER,
    extracted_invoice_id INTEGER,
    invoice_number TEXT,
    invoice_amount REAL,
    invoice_date TEXT,
    invoice_vendor TEXT,
    bank_upload_id INTEGER,
    bank_transaction_id INTEGER,
    transaction_amount REAL,
    transaction_date TEXT,
    transaction_description TEXT,
    transaction_reference TEXT,
    amount_difference REAL,
    date_difference_days INTEGER,
    matching_rules TEXT,
    manual_notes TEXT,
    verified_by TEXT,
    verified_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reconciliation_id) REFERENCES financial_reconciliations(id) ON DELETE CASCADE,
    FOREIGN KEY (invoice_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL,
    FOREIGN KEY (bank_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL
);
"""

CREATE_UNMATCHED_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS unmatched_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id INTEGER NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN ('invoice', 'transaction')),
    upload_id INTEGER,
    item_id INTEGER,
    item_reference TEXT,
    amount REAL,
    date TEXT,
    description TEXT,
    vendor_name TEXT,
    unmatched_reason TEXT,
    suggested_matches TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reconciliation_id) REFERENCES financial_reconciliations(id) ON DELETE CASCADE,
    FOREIGN KEY (upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL
);
"""

# Processing jobs table (unified for uploads and reconciliation)
CREATE_PROCESSING_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    document_upload_id INTEGER,
    document_type TEXT,
    reconciliation_id INTEGER,
    job_type TEXT NOT NULL CHECK (job_type IN ('upload_processing', 'reconciliation')),
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
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL,
    FOREIGN KEY (reconciliation_id) REFERENCES financial_reconciliations(id) ON DELETE SET NULL
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
    
    # Reconciliation indexes
    "CREATE INDEX IF NOT EXISTS idx_financial_reconciliations_number ON financial_reconciliations(reconciliation_number);",
    "CREATE INDEX IF NOT EXISTS idx_financial_reconciliations_invoice_upload ON financial_reconciliations(invoice_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_financial_reconciliations_bank_upload ON financial_reconciliations(bank_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_financial_reconciliations_status ON financial_reconciliations(status);",
    "CREATE INDEX IF NOT EXISTS idx_financial_reconciliations_date ON financial_reconciliations(reconciliation_date);",
    
    # Reconciliation matches indexes
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_reconciliation ON reconciliation_matches(reconciliation_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_invoice ON reconciliation_matches(extracted_invoice_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_transaction ON reconciliation_matches(bank_transaction_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_matches_type ON reconciliation_matches(match_type);",
    
    # Unmatched items indexes
    "CREATE INDEX IF NOT EXISTS idx_unmatched_items_reconciliation ON unmatched_items(reconciliation_id);",
    "CREATE INDEX IF NOT EXISTS idx_unmatched_items_type ON unmatched_items(item_type);",
    "CREATE INDEX IF NOT EXISTS idx_unmatched_items_upload ON unmatched_items(upload_id);",
    
    # Processing jobs indexes
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_upload ON processing_jobs(document_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_reconciliation ON processing_jobs(reconciliation_id);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_type ON processing_jobs(job_type);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);"
]

def get_financial_schema_statements():
    """Get all schema statements for financial data processing"""
    statements = [
        CREATE_DOCUMENT_UPLOADS_TABLE,
        CREATE_EXTRACTED_INVOICES_TABLE,
        CREATE_INVOICE_LINE_ITEMS_TABLE,
        CREATE_BANK_TRANSACTIONS_TABLE,
        CREATE_BANK_STATEMENTS_TABLE,
        CREATE_FINANCIAL_RECONCILIATIONS_TABLE,
        CREATE_RECONCILIATION_MATCHES_TABLE,
        CREATE_UNMATCHED_ITEMS_TABLE,
        CREATE_PROCESSING_JOBS_TABLE,
        CREATE_SCHEMA_MIGRATIONS_TABLE
    ]
    statements.extend(CREATE_INDEXES)
    return statements
