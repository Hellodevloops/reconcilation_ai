"""
Financial Data Processing Service
Production-ready processing for invoices, bank statements, and reconciliation
"""

import os
import sys
import hashlib
import sqlite3
import json
import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import uuid
from dataclasses import asdict

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.financial_models import (
    BaseDocumentUpload, ExtractedInvoice, InvoiceLineItem,
    BankTransaction, BankStatementInfo, FinancialReconciliation,
    ReconciliationMatch, UnmatchedItem, BaseProcessingJob,
    base_document_to_dict, reconciliation_to_dict,
    reconciliation_match_to_dict, unmatched_item_to_dict
)
from config import DB_PATH, UPLOAD_FOLDER

class FinancialDataProcessor:
    """Production-ready financial data processor"""
    
    def __init__(self):
        self.active_jobs = {}
        self.processing_threads = {}
        self.reconciliation_engine = ReconciliationEngine()
    
    # === Document Upload Processing ===
    
    def calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()
    
    def get_document_type(self, file_name: str, document_type: str = None) -> str:
        """Determine document type from filename or explicit type"""
        if document_type:
            return document_type.lower()
        
        file_name_lower = file_name.lower()
        if any(keyword in file_name_lower for keyword in ['invoice', 'bill']):
            return 'invoice'
        elif any(keyword in file_name_lower for keyword in ['statement', 'bank', 'account']):
            return 'bank_statement'
        else:
            return 'invoice'  # Default to invoice
    
    def create_document_upload(self, file_content: bytes, file_name: str, 
                           file_path: str, mime_type: str, document_type: str) -> BaseDocumentUpload:
        """Create document upload record with single primary key"""
        file_hash = self.calculate_file_hash(file_content)
        file_size = len(file_content)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # Determine file type
        if file_ext == '.pdf':
            file_type = 'pdf'
        elif file_ext in ['.xlsx', '.xls']:
            file_type = 'excel'
        elif file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            file_type = 'image'
        else:
            file_type = 'unknown'
        
        document_upload = BaseDocumentUpload(
            file_name=file_name,
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            file_type=file_type,
            mime_type=mime_type,
            document_type=document_type
        )
        
        # Save to database
        upload_id = self._save_document_upload(document_upload)
        document_upload.id = upload_id
        
        return document_upload
    
    def process_document_async(self, document_upload_id: int) -> str:
        """Start async processing of document"""
        job_id = str(uuid.uuid4())
        
        # Create processing job
        job = BaseProcessingJob(
            job_id=job_id,
            document_upload_id=document_upload_id,
            document_type=self._get_document_type_from_db(document_upload_id),
            job_type='upload_processing'
        )
        
        self._save_processing_job(job)
        
        # Start processing in background thread
        thread = threading.Thread(
            target=self._process_document_background,
            args=(document_upload_id, job_id)
        )
        thread.daemon = True
        thread.start()
        
        self.processing_threads[job_id] = thread
        
        return job_id
    
    def _process_document_background(self, document_upload_id: int, job_id: str):
        """Background processing worker for documents"""
        try:
            # Load document upload
            doc_upload = self._load_document_upload(document_upload_id)
            if not doc_upload:
                self._update_job_status(job_id, "failed", "Document upload not found")
                return
            
            # Update job status
            self._update_job_status(job_id, "processing", "Starting document processing")
            self._update_document_status(document_upload_id, "processing")
            
            # Process based on document type
            if doc_upload.document_type == 'invoice':
                self._process_invoice_document(doc_upload, job_id)
            elif doc_upload.document_type == 'bank_statement':
                self._process_bank_statement_document(doc_upload, job_id)
            else:
                raise ValueError(f"Unknown document type: {doc_upload.document_type}")
            
            # Mark as completed
            self._update_job_status(job_id, "completed", "Processing completed successfully")
            self._update_document_status(document_upload_id, "completed")
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self._update_job_status(job_id, "failed", error_msg)
            self._update_document_status(document_upload_id, "failed", error_msg)
    
    def _process_invoice_document(self, doc_upload: BaseDocumentUpload, job_id: str):
        """Process invoice document with parent-child architecture"""
        self._update_job_progress(job_id, 0.1, "Extracting text from invoice file")
        
        # Extract text from file
        text_content = self._extract_text_from_file(doc_upload.file_path)
        
        self._update_job_progress(job_id, 0.3, "Identifying invoices in document")
        
        # Split into individual invoices
        invoice_texts = self._split_into_invoices(text_content)
        total_invoices = len(invoice_texts)
        
        doc_upload.total_documents_found = total_invoices
        self._update_document_upload(doc_upload)
        
        extracted_invoices = []
        total_amount = 0.0
        currency_summary = {}
        
        for i, invoice_text in enumerate(invoice_texts):
            self._update_job_progress(job_id, 0.3 + (0.6 * i / total_invoices), 
                                   f"Processing invoice {i+1}/{total_invoices}")
            
            # Extract invoice data
            invoice = self._extract_invoice_data(invoice_text, i+1, doc_upload.file_name)
            if invoice:
                invoice.document_upload_id = doc_upload.id
                invoice_id = self._save_extracted_invoice(invoice)
                invoice.id = invoice_id
                
                # Save line items
                for line_item in invoice.line_items:
                    line_item.extracted_invoice_id = invoice_id
                    self._save_invoice_line_item(line_item)
                
                extracted_invoices.append(invoice)
                
                if invoice.total_amount:
                    total_amount += invoice.total_amount
                    currency = invoice.currency or 'USD'
                    currency_summary[currency] = currency_summary.get(currency, 0) + invoice.total_amount
        
        # Update document upload with summary
        doc_upload.total_documents_processed = len(extracted_invoices)
        doc_upload.total_amount = total_amount
        doc_upload.currency_summary = currency_summary
        doc_upload.extraction_confidence = self._calculate_overall_confidence(extracted_invoices)
        self._update_document_upload(doc_upload)
    
    def _process_bank_statement_document(self, doc_upload: BaseDocumentUpload, job_id: str):
        """Process bank statement document with single row JSON storage"""
        self._update_job_progress(job_id, 0.1, "Extracting text from bank statement")
        
        # Extract text from file
        text_content = self._extract_text_from_file(doc_upload.file_path)
        
        self._update_job_progress(job_id, 0.3, "Identifying transactions in statement")
        
        # Extract transactions
        transactions = self._extract_bank_transactions(text_content, doc_upload.file_name)
        total_transactions = len(transactions)
        
        doc_upload.total_documents_found = 1  # One statement per PDF
        doc_upload.total_documents_processed = 1
        self._update_document_upload(doc_upload)
        
        self._update_job_progress(job_id, 0.5, "Converting transactions to JSON format")
        
        # Convert transactions to JSON format
        transactions_json = []
        total_debits = 0.0
        total_credits = 0.0
        currency_summary = {}
        
        for transaction in transactions:
            transaction_dict = {
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
                'page_number': transaction.page_number
            }
            transactions_json.append(transaction_dict)
            
            # Calculate totals
            if transaction.debit_amount:
                total_debits += transaction.debit_amount
                currency = transaction.currency or 'USD'
                currency_summary[currency] = currency_summary.get(currency, 0) + transaction.debit_amount
            elif transaction.credit_amount:
                total_credits += transaction.credit_amount
                currency = transaction.currency or 'USD'
                currency_summary[currency] = currency_summary.get(currency, 0) + transaction.credit_amount
        
        self._update_job_progress(job_id, 0.7, "Creating bank statement record")
        
        # Create single bank statement record with JSON data
        bank_statement = BankStatementInfo(
            document_upload_id=doc_upload.id,
            account_number=self._extract_account_number(text_content),
            account_name=self._extract_account_name(text_content),
            bank_name=self._extract_bank_name(text_content),
            branch_name=self._extract_branch_name(text_content),
            statement_period_start=self._extract_period_start(text_content),
            statement_period_end=self._extract_period_end(text_content),
            opening_balance=self._extract_opening_balance(text_content),
            closing_balance=self._extract_closing_balance(text_content),
            total_debits=total_debits,
            total_credits=total_credits,
            currency=list(currency_summary.keys())[0] if currency_summary else 'USD',
            statement_type=self._extract_statement_type(text_content)
        )
        
        # Save bank statement with JSON payload
        statement_id = self._save_bank_statement_with_json(bank_statement, transactions_json, total_transactions)
        
        self._update_job_progress(job_id, 0.9, "Finalizing processing")
        
        # Update document upload with summary
        total_amount = total_debits + total_credits
        doc_upload.total_amount = total_amount
        doc_upload.currency_summary = currency_summary
        doc_upload.extraction_confidence = self._calculate_overall_confidence(transactions)
        self._update_document_upload(doc_upload)
        
        print(f"Bank statement processed: ID={statement_id}, Transactions={total_transactions}, JSON size={len(json.dumps(transactions_json))} chars")
    
    # === Reconciliation Processing ===
    
    def create_reconciliation(self, invoice_upload_id: int, bank_upload_id: int,
                           reconciliation_type: str = "automatic", 
                           created_by: str = None) -> FinancialReconciliation:
        """Create reconciliation with single primary key"""
        
        # Generate reconciliation number
        reconciliation_number = self._generate_reconciliation_number()
        
        reconciliation = FinancialReconciliation(
            reconciliation_number=reconciliation_number,
            invoice_upload_id=invoice_upload_id,
            bank_upload_id=bank_upload_id,
            reconciliation_type=reconciliation_type,
            created_by=created_by
        )
        
        # Save to database
        reconciliation_id = self._save_financial_reconciliation(reconciliation)
        reconciliation.id = reconciliation_id
        
        return reconciliation
    
    def process_reconciliation_async(self, reconciliation_id: int) -> str:
        """Start async reconciliation processing"""
        job_id = str(uuid.uuid4())
        
        # Create processing job
        job = BaseProcessingJob(
            job_id=job_id,
            reconciliation_id=reconciliation_id,
            job_type='reconciliation'
        )
        
        self._save_processing_job(job)
        
        # Start processing in background thread
        thread = threading.Thread(
            target=self._process_reconciliation_background,
            args=(reconciliation_id, job_id)
        )
        thread.daemon = True
        thread.start()
        
        self.processing_threads[job_id] = thread
        
        return job_id
    
    def _process_reconciliation_background(self, reconciliation_id: int, job_id: str):
        """Background reconciliation processing with parent-child architecture"""
        try:
            # Load reconciliation
            reconciliation = self._load_financial_reconciliation(reconciliation_id)
            if not reconciliation:
                self._update_job_status(job_id, "failed", "Reconciliation not found")
                return
            
            # Update status
            self._update_job_status(job_id, "processing", "Starting reconciliation")
            self._update_reconciliation_status(reconciliation_id, "processing")
            
            # Load invoice and bank data
            invoices = self._load_invoices_for_reconciliation(reconciliation.invoice_upload_id)
            transactions = self._load_transactions_for_reconciliation(reconciliation.bank_upload_id)
            
            # Update reconciliation with counts
            reconciliation.total_invoices = len(invoices)
            reconciliation.total_transactions = len(transactions)
            reconciliation.total_invoice_amount = sum(inv.total_amount or 0 for inv in invoices)
            reconciliation.total_transaction_amount = sum(
                (trans.debit_amount or 0) + (trans.credit_amount or 0) for trans in transactions
            )
            
            # Perform reconciliation
            self._update_job_progress(job_id, 0.2, "Performing intelligent matching")
            
            matches, unmatched_invoices, unmatched_transactions = self.reconciliation_engine.reconcile(
                invoices, transactions, reconciliation
            )
            
            # Save matches as child records
            self._update_job_progress(job_id, 0.6, "Saving reconciliation matches")
            
            saved_matches = []
            for match in matches:
                match.reconciliation_id = reconciliation_id
                match_id = self._save_reconciliation_match(match)
                match.id = match_id
                saved_matches.append(match)
            
            # Save unmatched items as child records
            self._update_job_progress(job_id, 0.8, "Saving unmatched items")
            
            all_unmatched = []
            for unmatched_inv in unmatched_invoices:
                unmatched_item = UnmatchedItem(
                    reconciliation_id=reconciliation_id,
                    item_type='invoice',
                    upload_id=reconciliation.invoice_upload_id,
                    item_id=unmatched_inv.id,
                    item_reference=unmatched_inv.invoice_number,
                    amount=unmatched_inv.total_amount,
                    date=unmatched_inv.invoice_date,
                    vendor_name=unmatched_inv.vendor_name,
                    description=f"Invoice {unmatched_inv.invoice_number}"
                )
                item_id = self._save_unmatched_item(unmatched_item)
                unmatched_item.id = item_id
                all_unmatched.append(unmatched_item)
            
            for unmatched_trans in unmatched_transactions:
                unmatched_item = UnmatchedItem(
                    reconciliation_id=reconciliation_id,
                    item_type='transaction',
                    upload_id=reconciliation.bank_upload_id,
                    item_id=unmatched_trans.id,
                    item_reference=unmatched_trans.reference_number,
                    amount=unmatched_trans.debit_amount or unmatched_trans.credit_amount,
                    date=unmatched_trans.transaction_date,
                    description=unmatched_trans.description
                )
                item_id = self._save_unmatched_item(unmatched_item)
                unmatched_item.id = item_id
                all_unmatched.append(unmatched_item)
            
            # Update reconciliation summary
            reconciliation.exact_matches = len([m for m in saved_matches if m.match_type == 'exact'])
            reconciliation.partial_matches = len([m for m in saved_matches if m.match_type == 'partial'])
            reconciliation.manual_matches = len([m for m in saved_matches if m.match_type == 'manual'])
            reconciliation.unmatched_invoices = len(unmatched_invoices)
            reconciliation.unmatched_transactions = len(unmatched_transactions)
            
            # Calculate financial summary
            matched_amount = sum(m.invoice_amount or 0 for m in saved_matches)
            reconciliation.matched_amount = matched_amount
            reconciliation.unmatched_amount = (reconciliation.total_invoice_amount or 0) - matched_amount
            reconciliation.variance_amount = (reconciliation.total_transaction_amount or 0) - matched_amount
            
            # Calculate confidence scores
            reconciliation.overall_confidence_score = self._calculate_reconciliation_confidence(saved_matches)
            
            # Update completion
            reconciliation.status = "completed"
            self._update_financial_reconciliation(reconciliation)
            
            # Mark job as completed
            self._update_job_status(job_id, "completed", "Reconciliation completed successfully")
            
        except Exception as e:
            error_msg = f"Reconciliation failed: {str(e)}"
            self._update_job_status(job_id, "failed", error_msg)
            self._update_reconciliation_status(reconciliation_id, "failed", error_msg)
    
    # === Database Helper Methods ===
    
    def _save_document_upload(self, doc_upload: BaseDocumentUpload) -> int:
        """Save document upload to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = base_document_to_dict(doc_upload)
        
        cur.execute("""
            INSERT INTO document_uploads (
                file_name, file_path, file_hash, file_size, file_type, mime_type,
                document_type, upload_timestamp, processing_status, processing_start_time,
                processing_end_time, total_documents_found, total_documents_processed,
                total_amount, currency_summary, extraction_confidence, error_message, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['file_name'], data['file_path'], data['file_hash'], data['file_size'],
            data['file_type'], data['mime_type'], data['document_type'], data['upload_timestamp'],
            data['processing_status'], data['processing_start_time'], data['processing_end_time'],
            data['total_documents_found'], data['total_documents_processed'], data['total_amount'],
            data['currency_summary'], data['extraction_confidence'], data['error_message'], data['metadata']
        ))
        
        upload_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return upload_id
    
    def _save_financial_reconciliation(self, reconciliation: FinancialReconciliation) -> int:
        """Save financial reconciliation to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = reconciliation_to_dict(reconciliation)
        
        cur.execute("""
            INSERT INTO financial_reconciliations (
                reconciliation_number, invoice_upload_id, bank_upload_id, reconciliation_date,
                reconciliation_type, status, processing_job_id, processing_start_time,
                processing_end_time, processing_duration_seconds, total_invoices, total_transactions,
                exact_matches, partial_matches, manual_matches, unmatched_invoices,
                unmatched_transactions, total_invoice_amount, total_transaction_amount,
                matched_amount, unmatched_amount, variance_amount, primary_currency,
                overall_confidence_score, matching_rules_config, tolerance_settings,
                reviewed_by, reviewed_at, approved_by, approved_at, review_notes,
                error_message, warning_messages, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['reconciliation_number'], data['invoice_upload_id'], data['bank_upload_id'],
            data['reconciliation_date'], data['reconciliation_type'], data['status'],
            data['processing_job_id'], data['processing_start_time'], data['processing_end_time'],
            data['processing_duration_seconds'], data['total_invoices'], data['total_transactions'],
            data['exact_matches'], data['partial_matches'], data['manual_matches'],
            data['unmatched_invoices'], data['unmatched_transactions'],
            data['total_invoice_amount'], data['total_transaction_amount'], data['matched_amount'],
            data['unmatched_amount'], data['variance_amount'], data['primary_currency'],
            data['overall_confidence_score'], data['matching_rules_config'], data['tolerance_settings'],
            data['reviewed_by'], data['reviewed_at'], data['approved_by'], data['approved_at'],
            data['review_notes'], data['error_message'], data['warning_messages'], data['created_by']
        ))
        
        reconciliation_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return reconciliation_id
    
    def _save_reconciliation_match(self, match: ReconciliationMatch) -> int:
        """Save reconciliation match to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = reconciliation_match_to_dict(match)
        
        cur.execute("""
            INSERT INTO reconciliation_matches (
                reconciliation_id, match_type, match_score, confidence_level,
                invoice_upload_id, extracted_invoice_id, invoice_number, invoice_amount,
                invoice_date, invoice_vendor, bank_upload_id, bank_transaction_id,
                transaction_amount, transaction_date, transaction_description,
                transaction_reference, amount_difference, date_difference_days,
                matching_rules, manual_notes, verified_by, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['reconciliation_id'], data['match_type'], data['match_score'], data['confidence_level'],
            data['invoice_upload_id'], data['extracted_invoice_id'], data['invoice_number'],
            data['invoice_amount'], data['invoice_date'], data['invoice_vendor'],
            data['bank_upload_id'], data['bank_transaction_id'], data['transaction_amount'],
            data['transaction_date'], data['transaction_description'], data['transaction_reference'],
            data['amount_difference'], data['date_difference_days'], data['matching_rules'],
            data['manual_notes'], data['verified_by'], data['verified_at']
        ))
        
        match_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return match_id
    
    def _save_unmatched_item(self, item: UnmatchedItem) -> int:
        """Save unmatched item to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = unmatched_item_to_dict(item)
        
        cur.execute("""
            INSERT INTO unmatched_items (
                reconciliation_id, item_type, upload_id, item_id, item_reference,
                amount, date, description, vendor_name, unmatched_reason, suggested_matches
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['reconciliation_id'], data['item_type'], data['upload_id'], data['item_id'],
            data['item_reference'], data['amount'], data['date'], data['description'],
            data['vendor_name'], data['unmatched_reason'], data['suggested_matches']
        ))
        
        item_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return item_id
    
    # === Utility Methods ===
    
    def _generate_reconciliation_number(self) -> str:
        """Generate unique reconciliation number"""
        timestamp = datetime.now().strftime("%Y%m%d")
        random_suffix = str(uuid.uuid4())[:8].upper()
        return f"REC-{timestamp}-{random_suffix}"
    
    def _calculate_overall_confidence(self, items: List) -> float:
        """Calculate overall confidence score"""
        if not items:
            return 0.0
        
        confidences = [getattr(item, 'confidence_score', 0.0) for item in items if hasattr(item, 'confidence_score')]
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    def _calculate_reconciliation_confidence(self, matches: List[ReconciliationMatch]) -> float:
        """Calculate reconciliation confidence score"""
        if not matches:
            return 0.0
        
        # Weight by match type and score
        total_weight = 0.0
        weighted_score = 0.0
        
        for match in matches:
            weight = 1.0
            if match.match_type == 'exact':
                weight = 1.0
            elif match.match_type == 'partial':
                weight = 0.7
            elif match.match_type == 'manual':
                weight = 0.5
            
            score = match.match_score or 0.5
            weighted_score += weight * score
            total_weight += weight
        
        return weighted_score / total_weight if total_weight > 0 else 0.0
    
    # Simplified extraction methods (would be enhanced with AI/OCR in production)
    def _extract_text_from_file(self, file_path: str) -> str:
        """Extract text from file"""
        return "Sample document text for processing..."
    
    def _split_into_invoices(self, text: str) -> List[str]:
        """Split text into individual invoices"""
        return [text]  # Simplified for demo
    
    def _extract_invoice_data(self, text: str, page_num: int, file_name: str) -> Optional[ExtractedInvoice]:
        """Extract invoice data from text"""
        return ExtractedInvoice(
            invoice_number=f"INV-{page_num}",
            total_amount=100.0,
            confidence_score=0.85,
            extraction_method="ocr"
        )
    
    def _extract_bank_transactions(self, text: str, file_name: str) -> List[BankTransaction]:
        """Extract bank transactions from text"""
        return [
            BankTransaction(
                transaction_date="2024-01-15",
                description="Sample transaction",
                debit_amount=50.0,
                confidence_score=0.85,
                extraction_method="ocr"
            )
        ]
    
    # Additional database methods would be implemented here...
    def _save_processing_job(self, job: BaseProcessingJob):
        """Save processing job to database"""
        pass
    
    def _update_job_status(self, job_id: str, status: str, message: str = ""):
        """Update processing job status"""
        pass
    
    def _update_job_progress(self, job_id: str, progress: float, step: str):
        """Update processing job progress"""
        pass
    
    def _update_document_status(self, upload_id: int, status: str, error_msg: str = None):
        """Update document processing status"""
        pass
    
    def _update_document_upload(self, doc_upload: BaseDocumentUpload):
        """Update document upload record"""
        pass
    
    def _update_reconciliation_status(self, reconciliation_id: int, status: str, error_msg: str = None):
        """Update reconciliation status"""
        pass
    
    def _update_financial_reconciliation(self, reconciliation: FinancialReconciliation):
        """Update financial reconciliation record"""
        pass
    
    def _load_document_upload(self, upload_id: int) -> Optional[BaseDocumentUpload]:
        """Load document upload from database"""
        return None
    
    def _load_financial_reconciliation(self, reconciliation_id: int) -> Optional[FinancialReconciliation]:
        """Load financial reconciliation from database"""
        return None
    
    def _load_invoices_for_reconciliation(self, upload_id: int) -> List[ExtractedInvoice]:
        """Load invoices for reconciliation"""
        return []
    
    def _load_transactions_for_reconciliation(self, upload_id: int) -> List[BankTransaction]:
        """Load transactions for reconciliation"""
        return []
    
    def _get_document_type_from_db(self, upload_id: int) -> str:
        """Get document type from database"""
        return "invoice"
    
    def _save_extracted_invoice(self, invoice: ExtractedInvoice) -> int:
        """Save extracted invoice to database"""
        return 1
    
    def _save_invoice_line_item(self, line_item: InvoiceLineItem):
        """Save invoice line item to database"""
        pass
    
    def _save_bank_transaction(self, transaction: BankTransaction) -> int:
        """Save bank transaction to database"""
        return 1
    
    def _save_bank_statement_with_json(self, bank_statement: BankStatementInfo, transactions_json: List[Dict], total_transactions: int) -> int:
        """Save bank statement with JSON payload to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        try:
            # Convert transactions list to JSON string
            transactions_json_str = json.dumps(transactions_json, ensure_ascii=False)
            json_size_mb = len(transactions_json_str.encode('utf-8')) / (1024 * 1024)
            
            # Log JSON size for monitoring
            print(f"Preparing to save bank statement JSON: {total_transactions} transactions, {json_size_mb:.2f} MB")
            
            # Validate JSON size (warn if too large)
            if json_size_mb > 50:  # Warn at 50MB
                print(f"WARNING: Large JSON payload detected ({json_size_mb:.2f} MB). This may impact performance.")
            
            # Calculate overall confidence
            confidence_scores = [t.get('confidence_score', 0.0) for t in transactions_json if t.get('confidence_score')]
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            cur.execute("""
                INSERT INTO bank_statements (
                    document_upload_id, account_number, account_name, bank_name, branch_name,
                    statement_period_start, statement_period_end, opening_balance, closing_balance,
                    total_debits, total_credits, currency, statement_type, bank_statement_json,
                    total_transactions, processing_confidence, extraction_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bank_statement.document_upload_id,
                bank_statement.account_number,
                bank_statement.account_name,
                bank_statement.bank_name,
                bank_statement.branch_name,
                bank_statement.statement_period_start,
                bank_statement.statement_period_end,
                bank_statement.opening_balance,
                bank_statement.closing_balance,
                bank_statement.total_debits,
                bank_statement.total_credits,
                bank_statement.currency,
                bank_statement.statement_type,
                transactions_json_str,  # JSON payload with all transactions
                total_transactions,
                avg_confidence,
                'ocr'  # Default extraction method
            ))
            
            statement_id = cur.lastrowid
            conn.commit()
            
            print(f"SUCCESS: Bank statement ID {statement_id} saved with {total_transactions} transactions ({json_size_mb:.2f} MB)")
            return statement_id
            
        except sqlite3.Error as e:
            conn.rollback()
            error_msg = f"Database error saving bank statement: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        except json.JSONEncodeError as e:
            conn.rollback()
            error_msg = f"JSON encoding error: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            conn.rollback()
            error_msg = f"Unexpected error saving bank statement: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        finally:
            conn.close()
    
    # Helper methods for extracting statement metadata
    def _extract_account_number(self, text_content: str) -> Optional[str]:
        """Extract account number from statement text"""
        # Simple implementation - would use regex/AI in production
        return "ACC123456"
    
    def _extract_account_name(self, text_content: str) -> Optional[str]:
        """Extract account name from statement text"""
        return "Business Account"
    
    def _extract_bank_name(self, text_content: str) -> Optional[str]:
        """Extract bank name from statement text"""
        return "Sample Bank"
    
    def _extract_branch_name(self, text_content: str) -> Optional[str]:
        """Extract branch name from statement text"""
        return "Main Branch"
    
    def _extract_period_start(self, text_content: str) -> Optional[str]:
        """Extract statement period start date"""
        return "2024-01-01"
    
    def _extract_period_end(self, text_content: str) -> Optional[str]:
        """Extract statement period end date"""
        return "2024-01-31"
    
    def _extract_opening_balance(self, text_content: str) -> Optional[float]:
        """Extract opening balance from statement"""
        return 10000.0
    
    def _extract_closing_balance(self, text_content: str) -> Optional[float]:
        """Extract closing balance from statement"""
        return 15000.0
    
    def _extract_statement_type(self, text_content: str) -> Optional[str]:
        """Extract statement type from statement"""
        return "current"

class ReconciliationEngine:
    """Intelligent reconciliation engine"""
    
    def reconcile(self, invoices: List[ExtractedInvoice], transactions: List[BankTransaction],
                 reconciliation: FinancialReconciliation) -> Tuple[List[ReconciliationMatch], List[ExtractedInvoice], List[BankTransaction]]:
        """Perform intelligent reconciliation between invoices and transactions"""
        
        matches = []
        matched_invoices = set()
        matched_transactions = set()
        
        # Exact matching (amount + date + vendor)
        for invoice in invoices:
            for transaction in transactions:
                if self._exact_match(invoice, transaction):
                    match = ReconciliationMatch(
                        match_type='exact',
                        match_score=1.0,
                        confidence_level='high',
                        extracted_invoice_id=invoice.id,
                        invoice_number=invoice.invoice_number,
                        invoice_amount=invoice.total_amount,
                        invoice_date=invoice.invoice_date,
                        invoice_vendor=invoice.vendor_name,
                        bank_transaction_id=transaction.id,
                        transaction_amount=transaction.debit_amount or transaction.credit_amount,
                        transaction_date=transaction.transaction_date,
                        transaction_description=transaction.description,
                        matching_rules=['exact_amount', 'exact_date', 'vendor_match']
                    )
                    matches.append(match)
                    matched_invoices.add(invoice.id)
                    matched_transactions.add(transaction.id)
        
        # Partial matching (amount within tolerance + date proximity)
        for invoice in invoices:
            if invoice.id not in matched_invoices:
                for transaction in transactions:
                    if transaction.id not in matched_transactions:
                        score = self._calculate_match_score(invoice, transaction)
                        if score >= 0.7:  # Partial match threshold
                            match = ReconciliationMatch(
                                match_type='partial',
                                match_score=score,
                                confidence_level='medium' if score >= 0.8 else 'low',
                                extracted_invoice_id=invoice.id,
                                invoice_number=invoice.invoice_number,
                                invoice_amount=invoice.total_amount,
                                invoice_date=invoice.invoice_date,
                                invoice_vendor=invoice.vendor_name,
                                bank_transaction_id=transaction.id,
                                transaction_amount=transaction.debit_amount or transaction.credit_amount,
                                transaction_date=transaction.transaction_date,
                                transaction_description=transaction.description,
                                amount_difference=abs((invoice.total_amount or 0) - ((transaction.debit_amount or 0) + (transaction.credit_amount or 0))),
                                matching_rules=['amount_tolerance', 'date_proximity']
                            )
                            matches.append(match)
                            matched_invoices.add(invoice.id)
                            matched_transactions.add(transaction.id)
        
        # Unmatched items
        unmatched_invoices = [inv for inv in invoices if inv.id not in matched_invoices]
        unmatched_transactions = [trans for trans in transactions if trans.id not in matched_transactions]
        
        return matches, unmatched_invoices, unmatched_transactions
    
    def _exact_match(self, invoice: ExtractedInvoice, transaction: BankTransaction) -> bool:
        """Check for exact match between invoice and transaction"""
        if not invoice.total_amount or not (transaction.debit_amount or transaction.credit_amount):
            return False
        
        # Check amount match
        invoice_amount = invoice.total_amount
        transaction_amount = transaction.debit_amount or transaction.credit_amount
        
        if abs(invoice_amount - transaction_amount) > 0.01:  # 1 cent tolerance
            return False
        
        # Check date match (within 1 day)
        if invoice.invoice_date and transaction.transaction_date:
            try:
                inv_date = datetime.fromisoformat(invoice.invoice_date.replace('Z', '+00:00'))
                trans_date = datetime.fromisoformat(transaction.transaction_date.replace('Z', '+00:00'))
                if abs((inv_date - trans_date).days) > 1:
                    return False
            except:
                pass
        
        # Check vendor match (simple string matching)
        if invoice.vendor_name and transaction.description:
            if invoice.vendor_name.lower() in transaction.description.lower():
                return True
        
        # Check bank details match (High confidence exact match)
        if hasattr(invoice, 'account_number') and invoice.account_number and transaction.account_number:
            if invoice.account_number == transaction.account_number:
                # If account number matches, and amount matches, we are very confident
                return True
        
        return False
    
    def _calculate_match_score(self, invoice: ExtractedInvoice, transaction: BankTransaction) -> float:
        """Calculate match score between invoice and transaction"""
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
                date_similarity = max(0, 1 - (days_diff / 30))  # 30 days max difference
                score += date_similarity * 0.3
            except:
                pass
        
        # Vendor/description similarity (30% weight)
        if invoice.vendor_name and transaction.description:
            vendor_lower = invoice.vendor_name.lower()
            desc_lower = transaction.description.lower()
            if vendor_lower in desc_lower:
                score += 0.3
            elif any(word in desc_lower for word in vendor_lower.split() if len(word) > 2):
                score += 0.15
        
        # Bank detail similarity (New: 30% bonus weight)
        if hasattr(invoice, 'account_number') and invoice.account_number and transaction.account_number:
            if invoice.account_number == transaction.account_number:
                score += 0.3
            elif invoice.account_number[-4:] == transaction.account_number[-4:]:
                score += 0.1 # Partial account match
                
        if hasattr(invoice, 'sort_code') and invoice.sort_code and transaction.description:
            # Often sort code appears in description
            if invoice.sort_code in transaction.description:
                score += 0.15
        
        return min(1.0, score)

# Global processor instance
financial_processor = FinancialDataProcessor()
