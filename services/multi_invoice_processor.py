"""
Multi-Invoice File Processing Service
Handles extraction of multiple invoices from single files with proper grouping
"""

import os
import sys
import hashlib
import time
import threading
import traceback
from typing import List, Dict, Any, Optional, Tuple, Generator
from datetime import datetime
import json
import uuid

import sqlite3
from PyPDF2 import PdfReader
import pandas as pd
from PIL import Image
import pytesseract

# Add project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.enhanced_models import (
    FileUpload, ExtractedInvoice, InvoiceLineItem, ProcessingJob,
    file_upload_to_dict, dict_to_file_upload, extracted_invoice_to_dict, dict_to_extracted_invoice
)
from config import DB_PATH, UPLOAD_FOLDER


class MultiInvoiceProcessor:
    """Service for processing files containing multiple invoices"""
    
    def __init__(self):
        self.processing_lock = threading.Lock()
        self.active_jobs: Dict[str, ProcessingJob] = {}
    
    def calculate_file_hash(self, file_bytes: bytes) -> str:
        """Calculate SHA-256 hash of file for deduplication"""
        return hashlib.sha256(file_bytes).hexdigest()
    
    def create_file_upload_record(self, file_data: bytes, file_name: str, 
                                 file_path: str, mime_type: str) -> FileUpload:
        """Create parent file upload record"""
        file_hash = self.calculate_file_hash(file_data)
        file_size = len(file_data)
        file_type = self._get_file_type(file_name)
        
        # Check for duplicate files
        existing_upload = self._get_upload_by_hash(file_hash)
        if existing_upload:
            raise ValueError(f"File with same content already uploaded: {existing_upload.file_name}")
        
        file_upload = FileUpload(
            file_name=file_name,
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            file_type=file_type,
            mime_type=mime_type,
            processing_status="pending"
        )
        
        # Save to database
        upload_id = self._save_file_upload(file_upload)
        file_upload.id = upload_id
        
        return file_upload
    
    def process_file_async(self, file_upload_id: int) -> str:
        """Start asynchronous processing of uploaded file"""
        job_id = str(uuid.uuid4())
        
        # Create processing job record
        job = ProcessingJob(
            job_id=job_id,
            file_upload_id=file_upload_id,
            status="queued"
        )
        self._save_processing_job(job)
        self.active_jobs[job_id] = job
        
        # Start background processing
        thread = threading.Thread(
            target=self._process_file_background,
            args=(file_upload_id, job_id),
            daemon=True
        )
        thread.start()
        
        return job_id
    
    def get_processing_status(self, job_id: str) -> Optional[ProcessingJob]:
        """Get status of processing job"""
        if job_id in self.active_jobs:
            return self.active_jobs[job_id]
        
        # Load from database
        job = self._load_processing_job(job_id)
        if job:
            self.active_jobs[job_id] = job
        return job
    
    def _process_file_background(self, file_upload_id: int, job_id: str):
        """Background processing thread"""
        try:
            with self.processing_lock:
                job = self.active_jobs.get(job_id)
                if not job:
                    return
                
                job.status = "processing"
                job.started_at = datetime.now().isoformat()
                job.current_step = "Loading file"
                self._update_processing_job(job)
            
            # Load file upload
            file_upload = self._load_file_upload(file_upload_id)
            if not file_upload:
                raise ValueError(f"File upload {file_upload_id} not found")
            
            # Update status to processing
            file_upload.processing_status = "processing"
            file_upload.processing_start_time = datetime.now().isoformat()
            self._update_file_upload(file_upload)
            
            # Process file based on type
            if file_upload.file_type == "pdf":
                invoices = self._process_pdf_file(file_upload, job_id)
            elif file_upload.file_type in ["excel", "xlsx", "xls"]:
                invoices = self._process_excel_file(file_upload, job_id)
            elif file_upload.file_type in ["image", "png", "jpg", "jpeg", "tiff"]:
                invoices = self._process_image_file(file_upload, job_id)
            else:
                raise ValueError(f"Unsupported file type: {file_upload.file_type}")
            
            # Save extracted invoices
            self._save_extracted_invoices(file_upload_id, invoices)
            
            # Update file upload with summary
            file_upload.processing_status = "completed"
            file_upload.processing_end_time = datetime.now().isoformat()
            file_upload.total_invoices_found = len(invoices)
            file_upload.total_invoices_processed = len(invoices)
            
            # Calculate totals and currency summary
            total_amount = 0.0
            currency_summary = {}
            confidence_scores = []
            
            for invoice in invoices:
                if invoice.total_amount:
                    total_amount += invoice.total_amount
                    currency = invoice.currency or "USD"
                    currency_summary[currency] = currency_summary.get(currency, 0) + invoice.total_amount
                
                if invoice.confidence_score:
                    confidence_scores.append(invoice.confidence_score)
            
            file_upload.total_amount = total_amount
            file_upload.currency_summary = currency_summary
            
            if confidence_scores:
                file_upload.extraction_confidence = sum(confidence_scores) / len(confidence_scores)
            
            self._update_file_upload(file_upload)
            
            # Update job status
            job.status = "completed"
            job.completed_at = datetime.now().isoformat()
            job.progress = 1.0
            job.current_step = "Completed"
            job.result_data = {
                "total_invoices": len(invoices),
                "total_amount": total_amount,
                "currency_summary": currency_summary,
                "average_confidence": file_upload.extraction_confidence
            }
            self._update_processing_job(job)
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            traceback_str = traceback.format_exc()
            
            # Update job with error
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
                job.status = "failed"
                job.error_message = error_msg
                job.completed_at = datetime.now().isoformat()
                self._update_processing_job(job)
            
            # Update file upload with error
            try:
                file_upload = self._load_file_upload(file_upload_id)
                if file_upload:
                    file_upload.processing_status = "failed"
                    file_upload.processing_end_time = datetime.now().isoformat()
                    file_upload.error_message = error_msg
                    self._update_file_upload(file_upload)
            except:
                pass
            
            print(f"Error processing file {file_upload_id}: {error_msg}")
            print(traceback_str)
    
    def _process_pdf_file(self, file_upload: FileUpload, job_id: str) -> List[ExtractedInvoice]:
        """Process PDF file containing multiple invoices"""
        invoices = []
        
        try:
            with open(file_upload.file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                self._update_job_progress(job_id, 0.1, "Processing PDF pages")
                
                for page_num, page in enumerate(pdf_reader.pages):
                    # Update progress
                    progress = 0.1 + (page_num / total_pages) * 0.7
                    self._update_job_progress(job_id, progress, f"Processing page {page_num + 1}/{total_pages}")
                    
                    # Extract text from page
                    text = page.extract_text()
                    
                    # Try to detect if this page contains an invoice
                    invoice = self._extract_invoice_from_text(
                        text, page_num + 1, file_upload.file_name
                    )
                    
                    if invoice:
                        invoice.extraction_method = "ocr"
                        invoice.page_number = page_num + 1
                        invoices.append(invoice)
                
                self._update_job_progress(job_id, 0.9, "Finalizing invoice extraction")
                
        except Exception as e:
            raise Exception(f"Failed to process PDF file: {str(e)}")
        
        return invoices
    
    def _process_excel_file(self, file_upload: FileUpload, job_id: str) -> List[ExtractedInvoice]:
        """Process Excel file containing multiple invoices"""
        invoices = []
        
        try:
            self._update_job_progress(job_id, 0.1, "Reading Excel file")
            
            # Read Excel file
            df = pd.read_excel(file_upload.file_path)
            
            self._update_job_progress(job_id, 0.3, "Analyzing Excel structure")
            
            # Try to detect invoice structure
            if self._is_structured_invoice_data(df):
                # Process as structured invoice data
                invoices = self._process_structured_excel_invoices(df, file_upload.file_name)
            else:
                # Process as tabular transaction data
                invoices = self._process_tabular_excel_invoices(df, file_upload.file_name)
            
            self._update_job_progress(job_id, 0.9, "Finalizing invoice extraction")
            
        except Exception as e:
            raise Exception(f"Failed to process Excel file: {str(e)}")
        
        return invoices
    
    def _process_image_file(self, file_upload: FileUpload, job_id: str) -> List[ExtractedInvoice]:
        """Process image file containing invoice(s)"""
        invoices = []
        
        try:
            self._update_job_progress(job_id, 0.1, "Processing image")
            
            # Open image
            image = Image.open(file_upload.file_path)
            
            # Perform OCR
            text = pytesseract.image_to_string(image)
            
            self._update_job_progress(job_id, 0.6, "Extracting invoice data")
            
            # Extract invoice from text
            invoice = self._extract_invoice_from_text(text, 1, file_upload.file_name)
            
            if invoice:
                invoice.extraction_method = "ocr"
                invoices.append(invoice)
            
            self._update_job_progress(job_id, 0.9, "Finalizing invoice extraction")
            
        except Exception as e:
            raise Exception(f"Failed to process image file: {str(e)}")
        
        return invoices
    
    def _extract_invoice_from_text(self, text: str, page_number: int, file_name: str) -> Optional[ExtractedInvoice]:
        """Extract invoice data from OCR text using pattern matching"""
        if not text or len(text.strip()) < 50:
            return None
        
        # Check if text looks like an invoice
        if not self._is_likely_invoice(text):
            return None
        
        invoice = ExtractedInvoice()
        invoice.raw_text = text
        invoice.page_number = page_number
        
        # Extract invoice number
        invoice.invoice_number = self._extract_invoice_number(text)

        # Extract reference and VAT number (common on tax invoices)
        invoice.reference = self._extract_reference(text)
        invoice.vat_number = self._extract_vat_number(text)
        
        # Extract dates
        invoice.invoice_date = self._extract_date(text, ['invoice date', 'date', 'issued'])
        invoice.due_date = self._extract_date(text, ['due date', 'payment due', 'due'])
        
        # Extract vendor/customer information
        invoice.vendor_name = self._extract_vendor_name(text)
        invoice.customer_name = self._extract_customer_name(text)
        
        # Extract amounts
        amounts = self._extract_amounts(text)
        invoice.total_amount = amounts.get('total')
        invoice.subtotal = amounts.get('subtotal')
        invoice.tax_total = amounts.get('tax')

        # Extract VAT rate / zero-rated totals / explicit total GBP when present
        invoice.total_vat_rate = self._extract_total_vat_rate(text)
        invoice.total_zero_rated = self._extract_total_zero_rated(text)
        invoice.total_gbp = self._extract_total_gbp(text) or invoice.total_amount
        
        # Extract currency
        invoice.currency = self._extract_currency(text)

        # Extract banking details
        bank_details = self._extract_bank_details(text)
        invoice.bank_name = bank_details.get('bank_name')
        invoice.account_number = bank_details.get('account_number')
        invoice.sort_code = bank_details.get('sort_code')
        invoice.iban = bank_details.get('iban')
        invoice.bic = bank_details.get('bic')
        invoice.account_name = bank_details.get('account_name')
        
        # Extract line items (simplified)
        invoice.line_items = self._extract_line_items(text)
        
        # Calculate confidence score based on extracted fields
        extracted_fields = [
            invoice.invoice_number, invoice.invoice_date, invoice.vendor_name,
            invoice.customer_name, invoice.total_amount
        ]
        filled_fields = sum(1 for field in extracted_fields if field)
        invoice.confidence_score = filled_fields / len(extracted_fields)
        
        return invoice
    
    def _is_likely_invoice(self, text: str) -> bool:
        """Check if text appears to be an invoice"""
        invoice_keywords = [
            'invoice', 'bill', 'tax invoice', 'proforma', 'statement',
            'amount due', 'total due', 'payment terms', 'due date',
            'invoice number', 'bill to', 'ship to'
        ]
        
        text_lower = text.lower()
        keyword_count = sum(1 for keyword in invoice_keywords if keyword in text_lower)
        
        # Consider it an invoice if it contains at least 2 keywords
        return keyword_count >= 2
    
    def _extract_invoice_number(self, text: str) -> Optional[str]:
        """Extract invoice number using regex patterns"""
        import re

        if not text:
            return None

        # Keep newlines (for patterns like "Invoice Number\nINV-0111"), but normalize spacing.
        t = text.replace("\r", "\n")
        t = re.sub(r"[\t\f\v]+", " ", t)
        t = re.sub(r"[ ]{2,}", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)

        # Preferred patterns: explicitly labeled invoice number/no.
        patterns = [
            # Invoice No: UA0INV20240029
            r"\binvoice\s*(?:no\.?|number|#)\b\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]{3,})",
            # Invoice Number\nINV-0111 (allow newline between label and value)
            r"\binvoice\s*(?:no\.?|number|#)\b\s*[:\-]?\s*(?:\n\s*)+([A-Z0-9][A-Z0-9\-\/]{2,})",
            # Sometimes OCR splits label: "Invoice" on one line, "No:" on next
            r"\binvoice\b\s*(?:\n\s*)*(?:no\.?|number|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]{3,})",
        ]

        for pattern in patterns:
            match = re.search(pattern, t, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = re.sub(r"\s+", "", value)  # OCR sometimes inserts spaces
                if value:
                    # Avoid junk OCR like "OICE" by requiring at least one digit
                    if len(value) >= 3 and len(value) <= 40 and re.search(r"\d", value):
                        return value

            # Pattern for:
            # Invoice Number
            # INV-0111
            # (Allows 1 or 2 newlines in between)
            r_multiline = r"\binvoice\s*(?:no\.?|number|#)\b\s*\n\s*(?:no\.?|number|#)?\s*([A-Z0-9][A-Z0-9\-\/]{2,})"
            match = re.search(r_multiline, t, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if len(value) >= 3 and re.search(r"\d", value):
                    return value

        # Fallback patterns (less specific)
        fallback_patterns = [
            r"\binvoice\b\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-\/]{3,})",
            r"\bbill\b\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-\/]{3,})",
        ]

        for pattern in fallback_patterns:
            match = re.search(pattern, t, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = re.sub(r"\s+", "", value)
                if value:
                    if len(value) >= 3 and len(value) <= 40 and re.search(r"\d", value):
                        return value

        return None

    def _extract_reference(self, text: str) -> Optional[str]:
        """Extract invoice reference (separate from invoice number when possible)"""
        import re

        patterns = [
            r'\breference\b\s*:?-?\s*([A-Z0-9\-\/]+)',
            r'\bref\.?\b\s*:?-?\s*([A-Z0-9\-\/]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
        return None

    def _extract_vat_number(self, text: str) -> Optional[str]:
        """Extract VAT number"""
        import re

        patterns = [
            r'\bVAT\s*(?:No\.?|Number)\b\s*:?-?\s*([A-Z0-9\s]+)',
            r'\bVAT\b\s*:?-?\s*([A-Z0-9\s]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = re.sub(r"\s+", "", match.group(1)).strip()
                if 6 <= len(value) <= 30:
                    return value
        return None

    def _extract_total_vat_rate(self, text: str) -> Optional[float]:
        """Extract VAT rate (e.g. 'TOTAL VAT 20%')"""
        import re

        patterns = [
            r'\btotal\s+vat\b\s*(\d{1,2}(?:\.\d+)?)\s*%',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except Exception:
                    return None
        return None

    def _extract_total_zero_rated(self, text: str) -> Optional[float]:
        """Extract zero-rated total if present (e.g. 'TOTAL ZERO RATED 0.00')"""
        import re

        patterns = [
            r'\btotal\s+zero\s+rated\b\s*[:]?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(',', ''))
                except Exception:
                    return None
        return None

    def _extract_total_gbp(self, text: str) -> Optional[float]:
        """Extract explicit total GBP amount when present (e.g. 'TOTAL GBP 3,901.20')"""
        import re

        patterns = [
            r'\btotal\s+gbp\b\s*[:]?\s*£?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'\bamount\s+gbp\b\s*[:]?\s*£?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'\bgbp\s+total\b\s*[:]?\s*£?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(',', ''))
                except Exception:
                    return None
        return None

    def _extract_bank_details(self, text: str) -> Dict[str, Optional[str]]:
        """Extract bank account and payment details"""
        import re
        details = {
            'bank_name': None,
            'account_number': None,
            'sort_code': None,
            'iban': None,
            'bic': None,
            'account_name': None
        }
        
        if not text:
            return details
            
        # Normalize text for better matching
        t = re.sub(r'\s+', ' ', text)
        
        # Account Number (generic and specific labels)
        acc_patterns = [
            r'\bAccount\s*(?:Number|No\.?|#)\b\s*[:\-]?\s*(\d{8,12})',
            r'\bAcc\s*(?:No\.?|Number)\b\s*[:\-]?\s*(\d{8,12})',
            r'\bA/C\s*(?:No\.?|Number)\b\s*[:\-]?\s*(\d{8,12})',
            # Fallback for just 8-digit numbers near "Account"
            r'Account\s+(\d{8})\b'
        ]
        for pat in acc_patterns:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                details['account_number'] = m.group(1).strip()
                break
                
        # Sort Code (XX-XX-XX or XXXXXX)
        sort_patterns = [
            r'\bSort\s+Code\b\s*[:\-]?\s*(\d{2}[-\s]\d{2}[-\s]\d{2})',
            r'\bSort\s+Code\b\s*[:\-]?\s*(\d{6})',
            r'\bSC\b\s*[:\-]?\s*(\d{2}[-\s]\d{2}[-\s]\d{2})'
        ]
        for pat in sort_patterns:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                details['sort_code'] = m.group(1).strip().replace(' ', '-')
                break
                
        # IBAN
        iban_pat = r'\bIBAN\b\s*[:\-]?\s*([A-Z]{2}\d{2}[A-Z0-9\s]{12,30})'
        m = re.search(iban_pat, t, re.IGNORECASE)
        if m:
            details['iban'] = re.sub(r'\s+', '', m.group(1)).strip()
            
        # BIC / SWIFT
        bic_pat = r'\b(?:BIC|SWIFT)\b\s*[:\-]?\s*([A-Z0-9]{8,11})'
        m = re.search(bic_pat, t, re.IGNORECASE)
        if m:
            details['bic'] = m.group(1).strip()
            
        # Bank Name
        # Look for common bank names or labels
        bank_names = ['Revolut', 'Barclays', 'HSBC', 'NatWest', 'Santander', 'Lloyds', 'Monzo', 'Starling']
        for name in bank_names:
            if re.search(rf'\b{name}\b', t, re.IGNORECASE):
                details['bank_name'] = name
                break
        
        if not details['bank_name']:
            bank_label_pat = r'\bBank\s+Name\b\s*[:\-]?\s*([A-Z][A-Za-z\s]+?)(?:\s{2,}|\n|,|$)'
            m = re.search(bank_label_pat, t, re.IGNORECASE)
            if m:
                details['bank_name'] = m.group(1).strip()
                
        # Account Name
        acc_name_pat = r'\bAccount\s+Name\b\s*[:\-]?\s*([A-Z][A-Za-z\s]+?)(?:\s{2,}|\n|,|$)'
        m = re.search(acc_name_pat, t, re.IGNORECASE)
        if m:
            details['account_name'] = m.group(1).strip()
            
        return details
    
    def _extract_date(self, text: str, labels: List[str]) -> Optional[str]:
        """Extract date using various patterns"""
        import re
        
        for label in labels:
            patterns = [
                rf'{label}\s*:?\s*(\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{2,4}})',
                rf'{label}\s*:?\s*(\d{{2,4}}[-/]\d{{1,2}}[-/]\d{{1,2}})',
                rf'{label}\s*:?\s*(\d{{1,2}}\s+\w{{3}}\s+\d{{2,4}})',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        
        return None
    
    def _extract_vendor_name(self, text: str) -> Optional[str]:
        """Extract vendor/company name"""
        import re
        
        # Look for company name patterns
        patterns = [
            r'from\s*:?\s*([A-Z][A-Za-z\s&]+?)(?:\n|$)',
            r'seller\s*:?\s*([A-Z][A-Za-z\s&]+?)(?:\n|$)',
            r'([A-Z][A-Za-z\s&]+(?:Inc|Ltd|LLC|Corp|Company))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and len(name) < 100:
                    return name
        
        return None
    
    def _extract_customer_name(self, text: str) -> Optional[str]:
        """Extract customer name"""
        import re
        
        patterns = [
            r'bill\s+to\s*:?\s*([A-Z][A-Za-z\s&]+?)(?:\n|$)',
            r'customer\s*:?\s*([A-Z][A-Za-z\s&]+?)(?:\n|$)',
            r'ship\s+to\s*:?\s*([A-Z][A-Za-z\s&]+?)(?:\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and len(name) < 100:
                    return name
        
        return None
    
    def _extract_amounts(self, text: str) -> Dict[str, Optional[float]]:
        """Extract monetary amounts"""
        import re
        
        amounts = {}
        
        # Look for total amount
        total_patterns = [
            r'total\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'amount\s+due\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'grand\s+total\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amounts['total'] = float(match.group(1).replace(',', ''))
                break
        
        # Look for subtotal
        subtotal_patterns = [
            r'subtotal\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'before\s+tax\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in subtotal_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amounts['subtotal'] = float(match.group(1).replace(',', ''))
                break
        
        # Look for tax
        tax_patterns = [
            r'tax\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'vat\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'gst\s*:?\s*[$£€]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in tax_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amounts['tax'] = float(match.group(1).replace(',', ''))
                break
        
        return amounts
    
    def _extract_currency(self, text: str) -> Optional[str]:
        """Extract currency from text"""
        if '$' in text:
            return 'USD'
        elif '£' in text:
            return 'GBP'
        elif '€' in text:
            return 'EUR'
        elif '₹' in text or 'Rs' in text or 'INR' in text:
            return 'INR'
        
        return 'USD'  # Default to USD
    
    def _extract_line_items(self, text: str) -> List[InvoiceLineItem]:
        """Extract line items from invoice text"""
        # This is a simplified implementation
        # In production, you'd use more sophisticated NLP or ML techniques
        line_items = []
        
        # Look for tabular data patterns
        import re

        # Prefer parsing table-like rows:
        #   Description  Quantity  Unit Price  VAT  Amount GBP
        # Require a decimal monetary amount on the line to avoid picking up numbers
        # from addresses/dates (e.g., "2nd Floor", "21 Mar 2024").
        header_re = re.compile(r"\bdescription\b.*\bquantity\b.*\bunit\s*price\b.*\bvat\b.*\bamount\b", re.IGNORECASE)
        footer_keywords = re.compile(r"\b(subtotal|total\s+vat|total\s+zero\s+rated|total\s+gbp|total\b)\b", re.IGNORECASE)
        
        table_row_re = re.compile(
            r"^(?P<desc>.+?)\s+"
            r"(?P<qty>\d+(?:\.\d+)?)\s+"
            r"(?P<unit>[$£€]?\s*\d+(?:\.\d{2})?)\s+"
            r"(?P<vat>(?:zero\s+rated|\d{1,2}(?:\.\d+)?%|[A-Za-z\s]+?))\s+"
            r"(?P<amount>[$£€]?\s*\d+(?:,\d{3})*(?:\.\d{2})?)\s*$",
            re.IGNORECASE,
        )

        # Split into lines and try to detect the table region.
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in (text or "").splitlines()]
        in_table = False
        for ln in lines:
            if not ln:
                continue
            if header_re.search(ln):
                in_table = True
                continue
            if footer_keywords.search(ln):
                # Stop collecting once totals section starts
                if in_table:
                    break
                continue

            # If we haven't seen the header, we still allow matching rows but with stricter filtering.
            m = table_row_re.match(ln)
            if not m:
                continue

            desc = (m.group("desc") or "").strip()
            if len(desc) < 3 or len(desc) > 200:
                continue
            # Avoid obvious non-item lines that can match accidentally.
            if re.search(r"\b(invoice|reference|vat\s*number|due\s*date|payment\s*details|iban|bic|sort\s*code)\b", desc, re.IGNORECASE):
                continue

            try:
                # Clean up extracted values
                clean_unit = re.sub(r"[^0-9\.]", "", m.group("unit").replace(",", ""))
                clean_amount = re.sub(r"[^0-9\.]", "", m.group("amount").replace(",", ""))
                
                qty = float(m.group("qty"))
                unit_price = float(clean_unit)
                total_amount = float(clean_amount)
            except Exception:
                continue

            # Hard filter: real line item amounts are typically >= 1 and include decimals.
            # Also valid items usually have Qty > 0
            if total_amount <= 0 or qty <= 0:
                continue

            line_item = InvoiceLineItem(
                description=desc,
                quantity=qty,
                unit_price=unit_price,
                total_amount=total_amount,
            )
            line_items.append(line_item)
        
        return line_items
    
    def _is_structured_invoice_data(self, df: pd.DataFrame) -> bool:
        """Check if Excel contains structured invoice data"""
        # Look for column names that suggest structured invoice data
        invoice_columns = ['invoice', 'bill', 'amount', 'total', 'date', 'vendor', 'customer']
        
        column_names = [col.lower() for col in df.columns]
        matching_columns = sum(1 for col in invoice_columns if any(col in name for name in column_names))
        
        return matching_columns >= 3
    
    def _process_structured_excel_invoices(self, df: pd.DataFrame, file_name: str) -> List[ExtractedInvoice]:
        """Process Excel file with structured invoice data"""
        invoices = []
        
        for _, row in df.iterrows():
            invoice = ExtractedInvoice()
            
            # Map columns to invoice fields
            for col in df.columns:
                col_lower = col.lower()
                if 'invoice' in col_lower and 'number' in col_lower:
                    invoice.invoice_number = str(row[col]) if pd.notna(row[col]) else None
                elif 'date' in col_lower and 'invoice' in col_lower:
                    invoice.invoice_date = str(row[col]) if pd.notna(row[col]) else None
                elif 'due' in col_lower and 'date' in col_lower:
                    invoice.due_date = str(row[col]) if pd.notna(row[col]) else None
                elif 'vendor' in col_lower or 'seller' in col_lower:
                    invoice.vendor_name = str(row[col]) if pd.notna(row[col]) else None
                elif 'customer' in col_lower or 'buyer' in col_lower:
                    invoice.customer_name = str(row[col]) if pd.notna(row[col]) else None
                elif 'total' in col_lower or 'amount' in col_lower:
                    invoice.total_amount = float(row[col]) if pd.notna(row[col]) else None
                elif 'subtotal' in col_lower:
                    invoice.subtotal = float(row[col]) if pd.notna(row[col]) else None
                elif 'tax' in col_lower:
                    invoice.tax_total = float(row[col]) if pd.notna(row[col]) else None
                elif 'currency' in col_lower:
                    invoice.currency = str(row[col]) if pd.notna(row[col]) else None
            
            invoice.extraction_method = "structured"
            invoice.confidence_score = 0.9  # High confidence for structured data
            
            if invoice.total_amount or invoice.invoice_number:
                invoices.append(invoice)
        
        return invoices
    
    def _process_tabular_excel_invoices(self, df: pd.DataFrame, file_name: str) -> List[ExtractedInvoice]:
        """Process Excel file with tabular transaction data"""
        # Group transactions by invoice number or create single invoice
        invoices = []
        
        # Try to group by invoice number column
        invoice_col = None
        for col in df.columns:
            if 'invoice' in col.lower() and 'number' in col.lower():
                invoice_col = col
                break
        
        if invoice_col:
            # Group by invoice number
            for invoice_num, group in df.groupby(invoice_col):
                invoice = ExtractedInvoice()
                invoice.invoice_number = str(invoice_num) if pd.notna(invoice_num) else None
                invoice.extraction_method = "structured"
                
                # Calculate totals from group
                if 'amount' in group.columns:
                    invoice.total_amount = group['amount'].sum()
                
                # Extract other common fields
                for col in group.columns:
                    if not pd.isna(group[col].iloc[0]):
                        col_lower = col.lower()
                        if 'date' in col_lower and 'invoice' in col_lower:
                            invoice.invoice_date = str(group[col].iloc[0])
                        elif 'vendor' in col_lower:
                            invoice.vendor_name = str(group[col].iloc[0])
                
                invoice.confidence_score = 0.8
                invoices.append(invoice)
        else:
            # Create single invoice from all transactions
            invoice = ExtractedInvoice()
            invoice.invoice_number = f"EXCEL_{file_name}"
            invoice.extraction_method = "structured"
            
            if 'amount' in df.columns:
                invoice.total_amount = df['amount'].sum()
            
            invoice.confidence_score = 0.7
            invoices.append(invoice)
        
        return invoices
    
    def _get_file_type(self, file_name: str) -> str:
        """Determine file type from extension"""
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext == '.pdf':
            return 'pdf'
        elif ext in ['.xlsx', '.xls']:
            return 'excel'
        elif ext in ['.png', '.jpg', '.jpeg', '.tiff', '.tif']:
            return 'image'
        else:
            return 'unknown'
    
    def _update_job_progress(self, job_id: str, progress: float, step: str):
        """Update processing job progress"""
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            job.progress = progress
            job.current_step = step
            self._update_processing_job(job)
    
    # Database helper methods
    def _save_file_upload(self, file_upload: FileUpload) -> int:
        """Save file upload to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = file_upload_to_dict(file_upload)
        
        # Convert JSON objects to strings for database storage
        currency_summary_json = json.dumps(data['currency_summary']) if data['currency_summary'] else None
        metadata_json = json.dumps(data['metadata']) if data['metadata'] else None
        
        cur.execute("""
            INSERT INTO file_uploads (
                file_name, file_path, file_hash, file_size, file_type, mime_type,
                upload_timestamp, processing_status, processing_start_time,
                processing_end_time, total_invoices_found, total_invoices_processed,
                total_amount, currency_summary, extraction_confidence, error_message, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['file_name'], data['file_path'], data['file_hash'], data['file_size'],
            data['file_type'], data['mime_type'], data['upload_timestamp'],
            data['processing_status'], data['processing_start_time'],
            data['processing_end_time'], data['total_invoices_found'],
            data['total_invoices_processed'], data['total_amount'],
            currency_summary_json, data['extraction_confidence'],
            data['error_message'], metadata_json
        ))
        
        upload_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return upload_id
    
    def _update_file_upload(self, file_upload: FileUpload):
        """Update file upload in database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        data = file_upload_to_dict(file_upload)
        
        # Convert JSON objects to strings for database storage
        currency_summary_json = json.dumps(data['currency_summary']) if data['currency_summary'] else None
        metadata_json = json.dumps(data['metadata']) if data['metadata'] else None
        
        cur.execute("""
            UPDATE file_uploads SET
                processing_status = ?, processing_start_time = ?, processing_end_time = ?,
                total_invoices_found = ?, total_invoices_processed = ?, total_amount = ?,
                currency_summary = ?, extraction_confidence = ?, error_message = ?,
                metadata = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            data['processing_status'], data['processing_start_time'],
            data['processing_end_time'], data['total_invoices_found'],
            data['total_invoices_processed'], data['total_amount'],
            currency_summary_json, data['extraction_confidence'],
            data['error_message'], metadata_json, file_upload.id
        ))
        
        conn.commit()
        conn.close()
    
    def _load_file_upload(self, upload_id: int) -> Optional[FileUpload]:
        """Load file upload from database"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM file_uploads WHERE id = ?", (upload_id,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            return dict_to_file_upload(data)
        
        return None
    
    def _get_upload_by_hash(self, file_hash: str) -> Optional[FileUpload]:
        """Get file upload by hash"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM file_uploads WHERE file_hash = ?", (file_hash,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            return dict_to_file_upload(data)
        
        return None
    
    def _save_extracted_invoices(self, file_upload_id: int, invoices: List[ExtractedInvoice]):
        """Save extracted invoices to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        for invoice in invoices:
            # Save invoice
            data = extracted_invoice_to_dict(invoice)
            
            cur.execute("""
                INSERT INTO extracted_invoices (
                    file_upload_id, invoice_number, invoice_date, reference, due_date,
                    vendor_name, vendor_address, vendor_tax_id, vat_number, customer_name,
                    customer_address, customer_tax_id, subtotal, tax_total, total_vat_rate,
                    total_zero_rated, total_gbp, total_amount, currency, payment_terms,
                    purchase_order, raw_text, confidence_score, extraction_method, page_number, bounding_box
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_upload_id, data['invoice_number'], data['invoice_date'], data.get('reference'),
                data['due_date'], data['vendor_name'], data['vendor_address'], data['vendor_tax_id'],
                data.get('vat_number'), data['customer_name'], data['customer_address'],
                data['customer_tax_id'], data['subtotal'], data['tax_total'], data.get('total_vat_rate'),
                data.get('total_zero_rated'), data.get('total_gbp'), data['total_amount'], data['currency'],
                data['payment_terms'], data['purchase_order'], data['raw_text'], data['confidence_score'],
                data['extraction_method'], data['page_number'], data['bounding_box']
            ))
            
            invoice_id = cur.lastrowid
            
            # Save line items
            for line_item in invoice.line_items:
                cur.execute("""
                    INSERT INTO invoice_line_items (
                        extracted_invoice_id, description, quantity, unit_price,
                        total_amount, item_code, tax_rate, tax_amount
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    invoice_id, line_item.description, line_item.quantity,
                    line_item.unit_price, line_item.total_amount,
                    line_item.item_code, line_item.tax_rate, line_item.tax_amount
                ))
        
        conn.commit()
        conn.close()
    
    def _save_processing_job(self, job: ProcessingJob):
        """Save processing job to database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        result_data_json = json.dumps(job.result_data) if job.result_data else None
        
        cur.execute("""
            INSERT INTO processing_jobs (
                job_id, file_upload_id, status, progress, current_step,
                estimated_time_remaining, started_at, completed_at,
                error_message, result_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.job_id, job.file_upload_id, job.status, job.progress,
            job.current_step, job.estimated_time_remaining, job.started_at,
            job.completed_at, job.error_message, result_data_json
        ))
        
        conn.commit()
        conn.close()
    
    def _update_processing_job(self, job: ProcessingJob):
        """Update processing job in database"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        result_data_json = json.dumps(job.result_data) if job.result_data else None
        
        cur.execute("""
            UPDATE processing_jobs SET
                status = ?, progress = ?, current_step = ?,
                estimated_time_remaining = ?, started_at = ?, completed_at = ?,
                error_message = ?, result_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (
            job.status, job.progress, job.current_step,
            job.estimated_time_remaining, job.started_at, job.completed_at,
            job.error_message, result_data_json, job.job_id
        ))
        
        conn.commit()
        conn.close()
    
    def _load_processing_job(self, job_id: str) -> Optional[ProcessingJob]:
        """Load processing job from database"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM processing_jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            if data['result_data']:
                data['result_data'] = json.loads(data['result_data'])
            return ProcessingJob(**data)
        
        return None


# Global processor instance
multi_invoice_processor = MultiInvoiceProcessor()
