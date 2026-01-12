"""
Simplified Reconciliation Model - Single Table Design
Centralized reconciliation_match table for all reconciliation data
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

@dataclass
class ReconciliationMatch:
    """Centralized reconciliation match table - stores ALL reconciliation data"""
    id: Optional[int] = None
    reconciliation_id: str = ""  # Single parent ID for entire reconciliation operation
    match_type: str = ""  # 'exact', 'partial', 'unmatched_invoice', 'unmatched_transaction'
    
    # Invoice reference
    invoice_upload_id: Optional[int] = None
    extracted_invoice_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    invoice_amount: Optional[float] = None
    invoice_vendor: Optional[str] = None
    invoice_currency: str = "USD"
    
    # Bank transaction reference
    bank_upload_id: Optional[int] = None
    bank_transaction_id: Optional[int] = None
    transaction_date: Optional[str] = None
    transaction_amount: Optional[float] = None
    transaction_description: Optional[str] = None
    transaction_reference: Optional[str] = None
    transaction_currency: str = "USD"
    
    # Match analysis (for matched/partial records)
    match_score: Optional[float] = None  # 0.0 to 1.0
    confidence_level: Optional[str] = None  # 'high', 'medium', 'low'
    amount_difference: Optional[float] = None
    date_difference_days: Optional[int] = None
    matching_rules: List[str] = field(default_factory=list)
    
    # Unmatched analysis (for unmatched records)
    unmatched_reason: Optional[str] = None
    suggested_matches: List[Dict[str, Any]] = field(default_factory=list)
    
    # Audit trail
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Reconciliation metadata (same for all records with same reconciliation_id)
    reconciliation_date: str = field(default_factory=lambda: datetime.now().isoformat())
    reconciliation_type: str = "automatic"  # automatic, manual, hybrid
    created_by: Optional[str] = None

@dataclass
class ReconciliationSummary:
    """Summary data for reconciliation operations (optional, can be derived)"""
    reconciliation_id: str = ""
    invoice_upload_id: Optional[int] = None
    bank_upload_id: Optional[int] = None
    reconciliation_date: str = ""
    status: str = "completed"  # pending, processing, completed, failed
    
    # Summary statistics
    total_invoices: int = 0
    total_transactions: int = 0
    exact_matches: int = 0
    partial_matches: int = 0
    unmatched_invoices: int = 0
    unmatched_transactions: int = 0
    
    # Financial summary
    total_invoice_amount: Optional[float] = None
    total_transaction_amount: Optional[float] = None
    matched_amount: Optional[float] = None
    unmatched_amount: Optional[float] = None
    variance_amount: Optional[float] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

# === Database Schema for Single Table Design ===

CREATE_RECONCILIATION_MATCH_TABLE = """
CREATE TABLE IF NOT EXISTS reconciliation_match (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Parent grouping (single reconciliation ID for entire operation)
    reconciliation_id TEXT NOT NULL,
    
    -- Match type classification
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'partial', 'unmatched_invoice', 'unmatched_transaction')),
    
    -- Invoice reference
    invoice_upload_id INTEGER,
    extracted_invoice_id INTEGER,
    invoice_number TEXT,
    invoice_date TEXT,
    invoice_amount REAL,
    invoice_vendor TEXT,
    invoice_currency TEXT DEFAULT 'USD',
    
    -- Bank transaction reference
    bank_upload_id INTEGER,
    bank_transaction_id INTEGER,
    transaction_date TEXT,
    transaction_amount REAL,
    transaction_description TEXT,
    transaction_reference TEXT,
    transaction_currency TEXT DEFAULT 'USD',
    
    -- Match analysis (for matched/partial records)
    match_score REAL,
    confidence_level TEXT CHECK (confidence_level IN ('high', 'medium', 'low')),
    amount_difference REAL,
    date_difference_days INTEGER,
    matching_rules TEXT,  -- JSON array
    
    -- Unmatched analysis (for unmatched records)
    unmatched_reason TEXT,
    suggested_matches TEXT,  -- JSON array
    
    -- Audit trail
    verified_by TEXT,
    verified_at TEXT,
    notes TEXT,
    
    -- Reconciliation metadata (same for all records with same reconciliation_id)
    reconciliation_date TEXT NOT NULL,
    reconciliation_type TEXT DEFAULT 'automatic' CHECK (reconciliation_type IN ('automatic', 'manual', 'hybrid')),
    created_by TEXT,
    
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraints
    FOREIGN KEY (invoice_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL,
    FOREIGN KEY (bank_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL,
    FOREIGN KEY (extracted_invoice_id) REFERENCES extracted_invoices(id) ON DELETE SET NULL,
    FOREIGN KEY (bank_transaction_id) REFERENCES bank_transactions(id) ON DELETE SET NULL
);
"""

# Indexes for optimal performance
CREATE_RECONCILIATION_MATCH_INDEXES = [
    # Primary grouping index
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_match_id ON reconciliation_match(reconciliation_id);",
    
    # Match type filtering
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_match_type ON reconciliation_match(match_type);",
    
    # Invoice references
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_invoice_upload ON reconciliation_match(invoice_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_invoice_id ON reconciliation_match(extracted_invoice_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_invoice_number ON reconciliation_match(invoice_number);",
    
    # Bank transaction references
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_bank_upload ON reconciliation_match(bank_upload_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_transaction_id ON reconciliation_match(bank_transaction_id);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_transaction_ref ON reconciliation_match(transaction_reference);",
    
    # Date and amount queries
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_invoice_date ON reconciliation_match(invoice_date);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_transaction_date ON reconciliation_match(transaction_date);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_amount ON reconciliation_match(invoice_amount, transaction_amount);",
    
    # Performance indexes
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_match_score ON reconciliation_match(match_score);",
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_created_at ON reconciliation_match(created_at);"
]

# Utility functions
def reconciliation_match_to_dict(match: ReconciliationMatch) -> Dict[str, Any]:
    """Convert reconciliation match to dictionary for database storage"""
    return {
        'id': match.id,
        'reconciliation_id': match.reconciliation_id,
        'match_type': match.match_type,
        'invoice_upload_id': match.invoice_upload_id,
        'extracted_invoice_id': match.extracted_invoice_id,
        'invoice_number': match.invoice_number,
        'invoice_date': match.invoice_date,
        'invoice_amount': match.invoice_amount,
        'invoice_vendor': match.invoice_vendor,
        'invoice_currency': match.invoice_currency,
        'bank_upload_id': match.bank_upload_id,
        'bank_transaction_id': match.bank_transaction_id,
        'transaction_date': match.transaction_date,
        'transaction_amount': match.transaction_amount,
        'transaction_description': match.transaction_description,
        'transaction_reference': match.transaction_reference,
        'transaction_currency': match.transaction_currency,
        'match_score': match.match_score,
        'confidence_level': match.confidence_level,
        'amount_difference': match.amount_difference,
        'date_difference_days': match.date_difference_days,
        'matching_rules': json.dumps(match.matching_rules),
        'unmatched_reason': match.unmatched_reason,
        'suggested_matches': json.dumps(match.suggested_matches),
        'verified_by': match.verified_by,
        'verified_at': match.verified_at,
        'notes': match.notes,
        'reconciliation_date': match.reconciliation_date,
        'reconciliation_type': match.reconciliation_type,
        'created_by': match.created_by,
        'created_at': match.created_at,
        'updated_at': match.updated_at
    }

def dict_to_reconciliation_match(data: Dict[str, Any]) -> ReconciliationMatch:
    """Convert dictionary to reconciliation match object"""
    return ReconciliationMatch(
        id=data.get('id'),
        reconciliation_id=data.get('reconciliation_id', ''),
        match_type=data.get('match_type', ''),
        invoice_upload_id=data.get('invoice_upload_id'),
        extracted_invoice_id=data.get('extracted_invoice_id'),
        invoice_number=data.get('invoice_number'),
        invoice_date=data.get('invoice_date'),
        invoice_amount=data.get('invoice_amount'),
        invoice_vendor=data.get('invoice_vendor'),
        invoice_currency=data.get('invoice_currency', 'USD'),
        bank_upload_id=data.get('bank_upload_id'),
        bank_transaction_id=data.get('bank_transaction_id'),
        transaction_date=data.get('transaction_date'),
        transaction_amount=data.get('transaction_amount'),
        transaction_description=data.get('transaction_description'),
        transaction_reference=data.get('transaction_reference'),
        transaction_currency=data.get('transaction_currency', 'USD'),
        match_score=data.get('match_score'),
        confidence_level=data.get('confidence_level'),
        amount_difference=data.get('amount_difference'),
        date_difference_days=data.get('date_difference_days'),
        matching_rules=json.loads(data.get('matching_rules', '[]')),
        unmatched_reason=data.get('unmatched_reason'),
        suggested_matches=json.loads(data.get('suggested_matches', '[]')),
        verified_by=data.get('verified_by'),
        verified_at=data.get('verified_at'),
        notes=data.get('notes'),
        reconciliation_date=data.get('reconciliation_date'),
        reconciliation_type=data.get('reconciliation_type', 'automatic'),
        created_by=data.get('created_by'),
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at')
    )

def get_simplified_reconciliation_schema():
    """Get schema statements for simplified single-table design"""
    return [CREATE_RECONCILIATION_MATCH_TABLE] + CREATE_RECONCILIATION_MATCH_INDEXES
