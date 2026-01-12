"""
Transaction Data Models
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class Transaction:
    """
    Represents a single transaction from invoice or bank statement
    
    Attributes:
        source: "invoice" or "bank"
        description: Transaction description
        amount: Transaction amount
        date: Transaction date (optional)
        vendor_name: Vendor/client name (optional)
        invoice_number: Invoice number (optional)
        currency: Currency symbol (₹, $, £, €, etc.) (optional)
    """
    source: str  # "invoice" or "bank"
    description: str
    amount: float
    date: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    currency: Optional[str] = None

    id: Optional[int] = None
    invoice_id: Optional[int] = None
    transaction_id: Optional[int] = None
    file_name: Optional[str] = None
    reference_id: Optional[str] = None
    direction: Optional[str] = None
    balance: Optional[float] = None
    owner_name: Optional[str] = None


@dataclass
class ReconciliationResult:
    """
    Result of reconciliation process
    
    Attributes:
        matches: List of matched transactions
        only_in_invoices: Transactions only in invoices
        only_in_bank: Transactions only in bank statements
    """
    matches: List[Dict[str, Any]]
    only_in_invoices: List[Dict[str, Any]]
    only_in_bank: List[Dict[str, Any]]

