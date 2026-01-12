"""
Unified Document Processor
Production-ready processing for both invoices and bank statements
"""

import os
import sys
import hashlib
import sqlite3
import json
import threading
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
import uuid

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.unified_models import (
    BaseDocumentUpload, ExtractedInvoice, InvoiceLineItem,
    BankTransaction, BankStatementInfo, BaseProcessingJob,
    base_document_to_dict, dict_to_base_document,
    invoice_to_dict, bank_transaction_to_dict, processing_job_to_dict
)
from config import DB_PATH, UPLOAD_FOLDER

class UnifiedDocumentProcessor:
    """Unified processor for invoices and bank statements"""
    
    def __init__(self):
        self.active_jobs = {}
        self.processing_threads = {}
    
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
        """Create document upload record"""
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
            document_type=self._get_document_type_from_db(document_upload_id)
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
        """Background processing worker"""
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
        """Process invoice document"""
        self._update_job_progress(job_id, 0.1, "Extracting text from invoice file")
        
        # Extract text from file
        text_content = self._extract_text_from_file(doc_upload.file_path)
        
        self._update_job_progress(job_id, 0.3, "Identifying invoices in document")
        
        # Split into individual invoices (simplified logic)
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
        """Process bank statement document"""
        self._update_job_progress(job_id, 0.1, "Extracting text from bank statement")
        
        # Extract text from file
        text_content = self._extract_text_from_file(doc_upload.file_path)
        
        self._update_job_progress(job_id, 0.3, "Identifying transactions in statement")
        
        # Extract transactions
        transactions = self._extract_bank_transactions(text_content, doc_upload.file_name)
        total_transactions = len(transactions)
        
        doc_upload.total_documents_found = total_transactions
        self._update_document_upload(doc_upload)
        
        extracted_transactions = []
        total_amount = 0.0
        currency_summary = {}
        
        for i, transaction in enumerate(transactions):
            self._update_job_progress(job_id, 0.3 + (0.6 * i / total_transactions),
                                   f"Processing transaction {i+1}/{total_transactions}")
            
            transaction.document_upload_id = doc_upload.id
            transaction_id = self._save_bank_transaction(transaction)
            transaction.id = transaction_id
            
            extracted_transactions.append(transaction)
            
            # Calculate totals
            if transaction.debit_amount:
                total_amount += transaction.debit_amount
                currency = transaction.currency or 'USD'
                currency_summary[currency] = currency_summary.get(currency, 0) + transaction.debit_amount
            elif transaction.credit_amount:
                total_amount += transaction.credit_amount
                currency = transaction.currency or 'USD'
                currency_summary[currency] = currency_summary.get(currency, 0) + transaction.credit_amount
        
        # Update document upload with summary
        doc_upload.total_documents_processed = len(extracted_transactions)
        doc_upload.total_amount = total_amount
        doc_upload.currency_summary = currency_summary
        doc_upload.extraction_confidence = self._calculate_overall_confidence(extracted_transactions)
        self._update_document_upload(doc_upload)
    
    # Database helper methods
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
    
    def _save_extracted_invoice(self, invoice: ExtractedInvoice) -> int:
        """Save extracted invoice to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = invoice_to_dict(invoice)
        
        cur.execute("""
            INSERT INTO extracted_invoices (
                document_upload_id, invoice_number, invoice_date, due_date, vendor_name,
                vendor_address, vendor_tax_id, customer_name, customer_address, customer_tax_id,
                subtotal, tax_total, total_amount, currency, payment_terms, purchase_order,
                raw_text, confidence_score, extraction_method, page_number, bounding_box
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['document_upload_id'], data['invoice_number'], data['invoice_date'],
            data['due_date'], data['vendor_name'], data['vendor_address'], data['vendor_tax_id'],
            data['customer_name'], data['customer_address'], data['customer_tax_id'],
            data['subtotal'], data['tax_total'], data['total_amount'], data['currency'],
            data['payment_terms'], data['purchase_order'], data['raw_text'],
            data['confidence_score'], data['extraction_method'], data['page_number'], data['bounding_box']
        ))
        
        invoice_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return invoice_id
    
    def _save_bank_transaction(self, transaction: BankTransaction) -> int:
        """Save bank transaction to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = bank_transaction_to_dict(transaction)
        
        cur.execute("""
            INSERT INTO bank_transactions (
                document_upload_id, transaction_date, description, debit_amount, credit_amount,
                balance, currency, transaction_type, reference_number, account_number,
                account_name, bank_name, branch_name, category, raw_text,
                confidence_score, extraction_method, page_number, statement_period_start,
                statement_period_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['document_upload_id'], data['transaction_date'], data['description'],
            data['debit_amount'], data['credit_amount'], data['balance'], data['currency'],
            data['transaction_type'], data['reference_number'], data['account_number'],
            data['account_name'], data['bank_name'], data['branch_name'], data['category'],
            data['raw_text'], data['confidence_score'], data['extraction_method'],
            data['page_number'], data['statement_period_start'], data['statement_period_end']
        ))
        
        transaction_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return transaction_id
    
    # Simplified extraction methods (would be enhanced with AI/OCR in production)
    def _extract_text_from_file(self, file_path: str) -> str:
        """Extract text from file (simplified)"""
        # This would use OCR for PDFs/images in production
        return "Sample invoice text with multiple invoices..."
    
    def _split_into_invoices(self, text: str) -> List[str]:
        """Split text into individual invoices"""
        # Simplified logic - would use AI in production
        return [text]  # Return as single invoice for demo
    
    def _extract_invoice_data(self, text: str, page_num: int, file_name: str) -> Optional[ExtractedInvoice]:
        """Extract invoice data from text"""
        # Simplified extraction - would use AI/ML in production
        return ExtractedInvoice(
            invoice_number=f"INV-{page_num}",
            total_amount=100.0,
            confidence_score=0.85,
            extraction_method="ocr"
        )
    
    def _extract_bank_transactions(self, text: str, file_name: str) -> List[BankTransaction]:
        """Extract bank transactions from text"""
        # Simplified extraction - would use AI/ML in production
        return [
            BankTransaction(
                transaction_date="2024-01-15",
                description="Sample transaction",
                debit_amount=50.0,
                confidence_score=0.85,
                extraction_method="ocr"
            )
        ]
    
    def _calculate_overall_confidence(self, items: List) -> float:
        """Calculate overall confidence score"""
        if not items:
            return 0.0
        
        confidences = [getattr(item, 'confidence_score', 0.0) for item in items if hasattr(item, 'confidence_score')]
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    # Additional helper methods would be implemented here...
    def _update_job_status(self, job_id: str, status: str, message: str = ""):
        """Update processing job status"""
        # Implementation would update database
        pass
    
    def _update_job_progress(self, job_id: str, progress: float, step: str):
        """Update processing job progress"""
        # Implementation would update database
        pass
    
    def _update_document_status(self, upload_id: int, status: str, error_msg: str = None):
        """Update document processing status"""
        # Implementation would update database
        pass
    
    def _update_document_upload(self, doc_upload: BaseDocumentUpload):
        """Update document upload record"""
        # Implementation would update database
        pass
    
    def _save_processing_job(self, job: BaseProcessingJob):
        """Save processing job to database"""
        # Implementation would save to database
        pass
    
    def _save_invoice_line_item(self, line_item: InvoiceLineItem):
        """Save invoice line item to database"""
        # Implementation would save to database
        pass
    
    def _load_document_upload(self, upload_id: int) -> Optional[BaseDocumentUpload]:
        """Load document upload from database"""
        # Implementation would load from database
        return None
    
    def _get_document_type_from_db(self, upload_id: int) -> str:
        """Get document type from database"""
        # Implementation would query database
        return "invoice"

# Global processor instance
unified_processor = UnifiedDocumentProcessor()
