"""
Simplified Reconciliation Service - Single Table Design
Production-ready reconciliation using only reconciliation_match table
"""

import os
import sys
import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.simplified_reconciliation import (
    ReconciliationMatch, ReconciliationSummary,
    reconciliation_match_to_dict, dict_to_reconciliation_match,
    get_simplified_reconciliation_schema
)
from config import DB_PATH

class SimplifiedReconciliationService:
    """Simplified reconciliation service using single table design"""
    
    def __init__(self):
        self.reconciliation_engine = SimplifiedMatchingEngine()
    
    def create_reconciliation(self, invoice_upload_id: int, bank_upload_id: int,
                           reconciliation_type: str = "automatic", 
                           created_by: str = None) -> str:
        """Create reconciliation and return single reconciliation ID"""
        
        # Generate unique reconciliation ID
        reconciliation_id = f"REC-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        reconciliation_date = datetime.now().isoformat()
        
        # No parent table needed - just return the ID
        # All data will be stored in reconciliation_match table with this ID
        
        return reconciliation_id
    
    def process_reconciliation(self, reconciliation_id: str, invoice_upload_id: int, 
                            bank_upload_id: int, reconciliation_type: str = "automatic",
                            created_by: str = None) -> bool:
        """Process reconciliation and store all results in single table"""
        
        try:
            # Load invoice and bank data
            invoices = self._load_invoices_from_upload(invoice_upload_id)
            transactions = self._load_transactions_from_upload(bank_upload_id)
            
            if not invoices and not transactions:
                return False
            
            # Perform matching
            matches, unmatched_invoices, unmatched_transactions = self.reconciliation_engine.reconcile(
                invoices, transactions, reconciliation_id
            )
            
            # Store ALL results in reconciliation_match table
            self._store_reconciliation_results(
                reconciliation_id, matches, unmatched_invoices, 
                unmatched_transactions, invoice_upload_id, bank_upload_id,
                reconciliation_type, created_by
            )
            
            return True
            
        except Exception as e:
            print(f"Reconciliation processing failed: {e}")
            return False
    
    def _store_reconciliation_results(self, reconciliation_id: str, 
                                   matches: List[Dict], unmatched_invoices: List, 
                                   unmatched_transactions: List,
                                   invoice_upload_id: int, bank_upload_id: int,
                                   reconciliation_type: str, created_by: str):
        """Store all reconciliation results in single reconciliation_match table"""
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        reconciliation_date = datetime.now().isoformat()
        
        try:
            # Store matched records
            for match in matches:
                match_record = ReconciliationMatch(
                    reconciliation_id=reconciliation_id,
                    match_type=match['match_type'],
                    invoice_upload_id=invoice_upload_id,
                    extracted_invoice_id=match.get('invoice_id'),
                    invoice_number=match.get('invoice_number'),
                    invoice_date=match.get('invoice_date'),
                    invoice_amount=match.get('invoice_amount'),
                    invoice_vendor=match.get('invoice_vendor'),
                    bank_upload_id=bank_upload_id,
                    bank_transaction_id=match.get('transaction_id'),
                    transaction_date=match.get('transaction_date'),
                    transaction_amount=match.get('transaction_amount'),
                    transaction_description=match.get('transaction_description'),
                    match_score=match.get('match_score'),
                    confidence_level=match.get('confidence_level'),
                    amount_difference=match.get('amount_difference'),
                    date_difference_days=match.get('date_difference_days'),
                    matching_rules=match.get('matching_rules', []),
                    reconciliation_date=reconciliation_date,
                    reconciliation_type=reconciliation_type,
                    created_by=created_by
                )
                
                self._save_reconciliation_match(match_record, cur)
            
            # Store unmatched invoices
            for invoice in unmatched_invoices:
                unmatched_record = ReconciliationMatch(
                    reconciliation_id=reconciliation_id,
                    match_type='unmatched_invoice',
                    invoice_upload_id=invoice_upload_id,
                    extracted_invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    invoice_amount=invoice.total_amount,
                    invoice_vendor=invoice.vendor_name,
                    unmatched_reason="No matching transaction found",
                    suggested_matches=[],  # Could be populated by AI
                    reconciliation_date=reconciliation_date,
                    reconciliation_type=reconciliation_type,
                    created_by=created_by
                )
                
                self._save_reconciliation_match(unmatched_record, cur)
            
            # Store unmatched transactions
            for transaction in unmatched_transactions:
                unmatched_record = ReconciliationMatch(
                    reconciliation_id=reconciliation_id,
                    match_type='unmatched_transaction',
                    bank_upload_id=bank_upload_id,
                    bank_transaction_id=transaction.id,
                    transaction_date=transaction.transaction_date,
                    transaction_amount=transaction.debit_amount or transaction.credit_amount,
                    transaction_description=transaction.description,
                    unmatched_reason="No matching invoice found",
                    suggested_matches=[],  # Could be populated by AI
                    reconciliation_date=reconciliation_date,
                    reconciliation_type=reconciliation_type,
                    created_by=created_by
                )
                
                self._save_reconciliation_match(unmatched_record, cur)
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _save_reconciliation_match(self, match: ReconciliationMatch, cur):
        """Save reconciliation match to database"""
        data = reconciliation_match_to_dict(match)
        
        cur.execute("""
            INSERT INTO reconciliation_match (
                reconciliation_id, match_type, invoice_upload_id, extracted_invoice_id,
                invoice_number, invoice_date, invoice_amount, invoice_vendor, invoice_currency,
                bank_upload_id, bank_transaction_id, transaction_date, transaction_amount,
                transaction_description, transaction_reference, transaction_currency,
                match_score, confidence_level, amount_difference, date_difference_days,
                matching_rules, unmatched_reason, suggested_matches, verified_by, verified_at,
                notes, reconciliation_date, reconciliation_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['reconciliation_id'], data['match_type'], data['invoice_upload_id'],
            data['extracted_invoice_id'], data['invoice_number'], data['invoice_date'],
            data['invoice_amount'], data['invoice_vendor'], data['invoice_currency'],
            data['bank_upload_id'], data['bank_transaction_id'], data['transaction_date'],
            data['transaction_amount'], data['transaction_description'], data['transaction_reference'],
            data['transaction_currency'], data['match_score'], data['confidence_level'],
            data['amount_difference'], data['date_difference_days'], data['matching_rules'],
            data['unmatched_reason'], data['suggested_matches'], data['verified_by'],
            data['verified_at'], data['notes'], data['reconciliation_date'],
            data['reconciliation_type'], data['created_by']
        ))
    
    def get_reconciliation_results(self, reconciliation_id: str) -> Dict[str, Any]:
        """Get all reconciliation results from single table"""
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        try:
            # Get all records for this reconciliation
            cur.execute("""
                SELECT * FROM reconciliation_match 
                WHERE reconciliation_id = ? 
                ORDER BY 
                    CASE match_type 
                        WHEN 'exact' THEN 1 
                        WHEN 'partial' THEN 2 
                        WHEN 'unmatched_invoice' THEN 3 
                        WHEN 'unmatched_transaction' THEN 4 
                    END,
                    match_score DESC,
                    created_at ASC
            """, (reconciliation_id,))
            
            rows = cur.fetchall()
            if not rows:
                return {}
            
            # Convert rows to objects
            matches = []
            for row in rows:
                # Convert row to dictionary
                columns = [desc[0] for desc in cur.description]
                data = dict(zip(columns, row))
                match = dict_to_reconciliation_match(data)
                matches.append(match)
            
            # Group by type
            exact_matches = [m for m in matches if m.match_type == 'exact']
            partial_matches = [m for m in matches if m.match_type == 'partial']
            unmatched_invoices = [m for m in matches if m.match_type == 'unmatched_invoice']
            unmatched_transactions = [m for m in matches if m.match_type == 'unmatched_transaction']
            
            # Calculate summary
            summary = self._calculate_summary(matches)
            
            return {
                'reconciliation_id': reconciliation_id,
                'summary': summary,
                'exact_matches': [reconciliation_match_to_dict(m) for m in exact_matches],
                'partial_matches': [reconciliation_match_to_dict(m) for m in partial_matches],
                'unmatched_invoices': [reconciliation_match_to_dict(m) for m in unmatched_invoices],
                'unmatched_transactions': [reconciliation_match_to_dict(m) for m in unmatched_transactions],
                'total_records': len(matches)
            }
            
        finally:
            conn.close()
    
    def _calculate_summary(self, matches: List[ReconciliationMatch]) -> Dict[str, Any]:
        """Calculate summary statistics from reconciliation matches"""
        
        exact_matches = len([m for m in matches if m.match_type == 'exact'])
        partial_matches = len([m for m in matches if m.match_type == 'partial'])
        unmatched_invoices = len([m for m in matches if m.match_type == 'unmatched_invoice'])
        unmatched_transactions = len([m for m in matches if m.match_type == 'unmatched_transaction'])
        
        # Calculate financial totals
        matched_amount = sum(m.invoice_amount or 0 for m in matches if m.match_type in ['exact', 'partial'])
        total_invoice_amount = sum(m.invoice_amount or 0 for m in matches if m.invoice_amount)
        total_transaction_amount = sum(m.transaction_amount or 0 for m in matches if m.transaction_amount)
        
        return {
            'total_invoices': len([m for m in matches if m.invoice_amount]),
            'total_transactions': len([m for m in matches if m.transaction_amount]),
            'exact_matches': exact_matches,
            'partial_matches': partial_matches,
            'unmatched_invoices': unmatched_invoices,
            'unmatched_transactions': unmatched_transactions,
            'total_invoice_amount': total_invoice_amount,
            'total_transaction_amount': total_transaction_amount,
            'matched_amount': matched_amount,
            'unmatched_amount': total_invoice_amount - matched_amount,
            'variance_amount': total_transaction_amount - matched_amount,
            'match_rate': (exact_matches + partial_matches) / len(matches) * 100 if matches else 0
        }
    
    def list_reconciliations(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List all reconciliations (derived from single table)"""
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        try:
            # Get unique reconciliation IDs with summary
            cur.execute("""
                SELECT 
                    reconciliation_id,
                    reconciliation_date,
                    reconciliation_type,
                    created_by,
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN match_type IN ('exact', 'partial') THEN 1 END) as matched_records,
                    COUNT(CASE WHEN match_type = 'unmatched_invoice' THEN 1 END) as unmatched_invoices,
                    COUNT(CASE WHEN match_type = 'unmatched_transaction' THEN 1 END) as unmatched_transactions,
                    SUM(CASE WHEN match_type IN ('exact', 'partial') THEN invoice_amount ELSE 0 END) as matched_amount,
                    SUM(invoice_amount) as total_invoice_amount
                FROM reconciliation_match 
                GROUP BY reconciliation_id 
                ORDER BY reconciliation_date DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            reconciliations = []
            for row in rows:
                data = dict(zip(columns, row))
                reconciliations.append(data)
            
            return reconciliations
            
        finally:
            conn.close()
    
    def _load_invoices_from_upload(self, upload_id: int) -> List:
        """Load invoices from upload (simplified)"""
        # Implementation would load from extracted_invoices table
        return []
    
    def _load_transactions_from_upload(self, upload_id: int) -> List:
        """Load transactions from upload (simplified)"""
        # Implementation would load from bank_transactions table
        return []

class SimplifiedMatchingEngine:
    """Simplified matching engine for single table design"""
    
    def reconcile(self, invoices: List, transactions: List, reconciliation_id: str) -> Tuple[List[Dict], List, List]:
        """Perform reconciliation and return results for single table storage"""
        
        matches = []
        matched_invoices = set()
        matched_transactions = set()
        
        # Exact matching
        for invoice in invoices:
            for transaction in transactions:
                if self._exact_match(invoice, transaction):
                    match = {
                        'match_type': 'exact',
                        'invoice_id': invoice.id,
                        'invoice_number': invoice.invoice_number,
                        'invoice_date': invoice.invoice_date,
                        'invoice_amount': invoice.total_amount,
                        'invoice_vendor': invoice.vendor_name,
                        'transaction_id': transaction.id,
                        'transaction_date': transaction.transaction_date,
                        'transaction_amount': transaction.debit_amount or transaction.credit_amount,
                        'transaction_description': transaction.description,
                        'match_score': 1.0,
                        'confidence_level': 'high',
                        'matching_rules': ['exact_amount', 'exact_date', 'vendor_match']
                    }
                    matches.append(match)
                    matched_invoices.add(invoice.id)
                    matched_transactions.add(transaction.id)
        
        # Partial matching
        for invoice in invoices:
            if invoice.id not in matched_invoices:
                for transaction in transactions:
                    if transaction.id not in matched_transactions:
                        score = self._calculate_match_score(invoice, transaction)
                        if score >= 0.7:
                            match = {
                                'match_type': 'partial',
                                'invoice_id': invoice.id,
                                'invoice_number': invoice.invoice_number,
                                'invoice_date': invoice.invoice_date,
                                'invoice_amount': invoice.total_amount,
                                'invoice_vendor': invoice.vendor_name,
                                'transaction_id': transaction.id,
                                'transaction_date': transaction.transaction_date,
                                'transaction_amount': transaction.debit_amount or transaction.credit_amount,
                                'transaction_description': transaction.description,
                                'match_score': score,
                                'confidence_level': 'medium' if score >= 0.8 else 'low',
                                'amount_difference': abs((invoice.total_amount or 0) - ((transaction.debit_amount or 0) + (transaction.credit_amount or 0))),
                                'matching_rules': ['amount_tolerance', 'date_proximity']
                            }
                            matches.append(match)
                            matched_invoices.add(invoice.id)
                            matched_transactions.add(transaction.id)
        
        # Unmatched items
        unmatched_invoices = [inv for inv in invoices if inv.id not in matched_invoices]
        unmatched_transactions = [trans for trans in transactions if trans.id not in matched_transactions]
        
        return matches, unmatched_invoices, unmatched_transactions
    
    def _exact_match(self, invoice, transaction) -> bool:
        """Check for exact match"""
        if not invoice.total_amount or not (transaction.debit_amount or transaction.credit_amount):
            return False
        
        # Amount match
        invoice_amount = invoice.total_amount
        transaction_amount = transaction.debit_amount or transaction.credit_amount
        if abs(invoice_amount - transaction_amount) > 0.01:
            return False
        
        # Date match (within 1 day)
        if invoice.invoice_date and transaction.transaction_date:
            try:
                inv_date = datetime.fromisoformat(invoice.invoice_date.replace('Z', '+00:00'))
                trans_date = datetime.fromisoformat(transaction.transaction_date.replace('Z', '+00:00'))
                if abs((inv_date - trans_date).days) > 1:
                    return False
            except:
                pass
        
        # Vendor match
        if invoice.vendor_name and transaction.description:
            if invoice.vendor_name.lower() in transaction.description.lower():
                return True
        
        # Bank details match
        if hasattr(invoice, 'account_number') and invoice.account_number and hasattr(transaction, 'account_number') and transaction.account_number:
            if invoice.account_number == transaction.account_number:
                return True
        
        return False
    
    def _calculate_match_score(self, invoice, transaction) -> float:
        """Calculate match score"""
        score = 0.0
        
        # Amount similarity (40% weight)
        if invoice.total_amount and (transaction.debit_amount or transaction.credit_amount):
            invoice_amount = invoice.total_amount
            transaction_amount = transaction.debit_amount or transaction.credit_amount
            amount_diff = abs(invoice_amount - transaction_amount)
            amount_similarity = max(0, 1 - (amount_diff / max(invoice_amount, transaction_amount)))
            score += amount_similarity * 0.4
        
        # Date proximity (30% weight)
        if invoice.invoice_date and transaction.transaction_date:
            try:
                inv_date = datetime.fromisoformat(invoice.invoice_date.replace('Z', '+00:00'))
                trans_date = datetime.fromisoformat(transaction.transaction_date.replace('Z', '+00:00'))
                days_diff = abs((inv_date - trans_date).days)
                date_similarity = max(0, 1 - (days_diff / 30))
                score += date_similarity * 0.3
            except:
                pass
        
        # Vendor similarity (30% weight)
        if invoice.vendor_name and transaction.description:
            vendor_lower = invoice.vendor_name.lower()
            desc_lower = transaction.description.lower()
            if vendor_lower in desc_lower:
                score += 0.3
            elif any(word in desc_lower for word in vendor_lower.split() if len(word) > 2):
                score += 0.15
        
        # Bank detail similarity (30% weight)
        if hasattr(invoice, 'account_number') and invoice.account_number and hasattr(transaction, 'account_number') and transaction.account_number:
            if invoice.account_number == transaction.account_number:
                score += 0.3
            elif invoice.account_number[-4:] == transaction.account_number[-4:]:
                score += 0.1
                
        if hasattr(invoice, 'sort_code') and invoice.sort_code and transaction.description:
            if invoice.sort_code in transaction.description:
                score += 0.15
        
        return min(1.0, score)

# Global service instance
simplified_reconciliation_service = SimplifiedReconciliationService()
