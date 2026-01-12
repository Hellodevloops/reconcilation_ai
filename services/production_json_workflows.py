"""
Production JSON Storage Workflows
Complete upload, extraction, and reconciliation workflows for single-row JSON storage

Core Rule: One uploaded file or one reconciliation run = one database row
All extracted or generated data must be stored inside that single row as structured JSON
"""

import os
import json
import time
import hashlib
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import asdict
from pathlib import Path

# Import existing OCR and processing components
from models.production_json_models import (
    InvoiceUpload, BankTransactionUpload, ReconciliationMatch,
    ProductionJSONDataAccess, generate_upload_id, generate_reconciliation_id,
    calculate_file_hash, validate_json_structure,
    INVOICE_JSON_EXAMPLE, BANK_TRANSACTION_JSON_EXAMPLE, RECONCILIATION_JSON_EXAMPLE
)

# Import existing OCR functionality
from app import (
    extract_invoices_from_pdf, extract_bank_transactions_from_pdf,
    find_matches, Transaction, ReconciliationResult,
    logger, _db_write_lock
)


class ProductionJSONWorkflows:
    """Production-ready workflows for JSON-based document processing"""
    
    def __init__(self, db_path: str, upload_folder: str):
        self.db_path = db_path
        self.upload_folder = upload_folder
        self.data_access = ProductionJSONDataAccess(db_path)
        
        # Ensure upload directories exist
        self.invoice_upload_dir = os.path.join(upload_folder, "invoices")
        self.bank_upload_dir = os.path.join(upload_folder, "bank_statements")
        os.makedirs(self.invoice_upload_dir, exist_ok=True)
        os.makedirs(self.bank_upload_dir, exist_ok=True)
    
    def process_invoice_upload(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """
        Process invoice file upload with single-row JSON storage
        
        Workflow:
        1. Upload file → Generate upload_id
        2. Extract ALL invoices from file
        3. Build JSON structure with ALL invoice data
        4. Store in SINGLE database row
        5. Return upload_id and summary
        """
        start_time = time.time()
        upload_id = generate_upload_id()
        
        try:
            # Step 1: File validation and storage
            file_size = os.path.getsize(file_path)
            file_hash = calculate_file_hash(file_path)
            
            # Step 2: Start processing
            processing_start = datetime.now().isoformat()
            logger.info(f"Starting invoice processing for upload_id: {upload_id}", 
                       context={"file_name": file_name, "file_size": file_size})
            
            # Step 3: Extract ALL invoices using existing OCR functionality
            invoices_data = extract_invoices_from_pdf(file_path)
            
            # Step 4: Build comprehensive JSON structure
            invoice_json = self._build_invoice_json_structure(
                upload_id=upload_id,
                file_name=file_name,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                invoices_data=invoices_data,
                processing_start=processing_start
            )
            
            # Step 5: Create database record with single row
            invoice_upload = InvoiceUpload(
                upload_id=upload_id,
                file_name=file_name,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                pages_total=len(invoices_data.get('pages', [])) if isinstance(invoices_data, dict) else 1,
                mime_type="application/pdf",
                processing_start=processing_start,
                processing_end=datetime.now().isoformat(),
                processing_duration_seconds=int(time.time() - start_time),
                confidence_score=self._calculate_overall_confidence(invoices_data),
                status="completed",
                invoice_json=json.dumps(invoice_json, indent=2),
                total_invoices_found=len(invoices_data.get('invoices', [])) if isinstance(invoices_data, dict) else 0,
                total_invoices_processed=len(invoices_data.get('invoices', [])) if isinstance(invoices_data, dict) else 0,
                total_amount=self._calculate_total_amount(invoices_data),
                currency_summary=json.dumps(self._calculate_currency_summary(invoices_data)),
                vendor_summary=json.dumps(self._calculate_vendor_summary(invoices_data)),
                date_range_start=self._get_date_range_start(invoices_data),
                date_range_end=self._get_date_range_end(invoices_data)
            )
            
            # Step 6: Atomic database insertion
            with _db_write_lock:
                db_record_id = self.data_access.insert_invoice_upload(invoice_upload)
            
            processing_time = time.time() - start_time
            logger.info(f"Invoice processing completed", 
                       context={
                           "upload_id": upload_id,
                           "db_record_id": db_record_id,
                           "total_invoices": invoice_upload.total_invoices_found,
                           "processing_time_seconds": processing_time
                       })
            
            return {
                "success": True,
                "upload_id": upload_id,
                "db_record_id": db_record_id,
                "file_name": file_name,
                "total_invoices": invoice_upload.total_invoices_found,
                "total_amount": invoice_upload.total_amount,
                "processing_time_seconds": processing_time,
                "status": "completed"
            }
            
        except Exception as e:
            error_time = datetime.now().isoformat()
            logger.error(f"Invoice processing failed", 
                        context={"upload_id": upload_id, "file_name": file_name}, 
                        error=e)
            
            # Store error record for debugging
            error_upload = InvoiceUpload(
                upload_id=upload_id,
                file_name=file_name,
                file_path=file_path,
                file_hash=file_hash if 'file_hash' in locals() else "",
                file_size=file_size if 'file_size' in locals() else 0,
                processing_start=processing_start if 'processing_start' in locals() else error_time,
                processing_end=error_time,
                status="failed",
                error_message=str(e)
            )
            
            try:
                with _db_write_lock:
                    self.data_access.insert_invoice_upload(error_upload)
            except Exception as db_error:
                logger.error(f"Failed to store error record", error=db_error)
            
            return {
                "success": False,
                "upload_id": upload_id,
                "error": str(e),
                "status": "failed"
            }
    
    def process_bank_upload(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """
        Process bank statement file upload with single-row JSON storage
        
        Workflow:
        1. Upload file → Generate upload_id
        2. Extract ALL transactions from file
        3. Build JSON structure with ALL transaction data
        4. Store in SINGLE database row
        5. Return upload_id and summary
        """
        start_time = time.time()
        upload_id = generate_upload_id()
        
        try:
            # Step 1: File validation and storage
            file_size = os.path.getsize(file_path)
            file_hash = calculate_file_hash(file_path)
            
            # Step 2: Start processing
            processing_start = datetime.now().isoformat()
            logger.info(f"Starting bank statement processing for upload_id: {upload_id}", 
                       context={"file_name": file_name, "file_size": file_size})
            
            # Step 3: Extract ALL transactions using existing OCR functionality
            transactions_data = extract_bank_transactions_from_pdf(file_path)
            
            # Step 4: Build comprehensive JSON structure
            bank_json = self._build_bank_json_structure(
                upload_id=upload_id,
                file_name=file_name,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                transactions_data=transactions_data,
                processing_start=processing_start
            )
            
            # Step 5: Create database record with single row
            bank_upload = BankTransactionUpload(
                upload_id=upload_id,
                file_name=file_name,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                pages_total=len(transactions_data.get('pages', [])) if isinstance(transactions_data, dict) else 1,
                mime_type="application/pdf",
                processing_start=processing_start,
                processing_end=datetime.now().isoformat(),
                processing_duration_seconds=int(time.time() - start_time),
                confidence_score=self._calculate_overall_confidence(transactions_data),
                status="completed",
                bank_transaction_json=json.dumps(bank_json, indent=2),
                account_number=self._extract_account_number(transactions_data),
                account_name=self._extract_account_name(transactions_data),
                bank_name=self._extract_bank_name(transactions_data),
                statement_period_start=self._extract_period_start(transactions_data),
                statement_period_end=self._extract_period_end(transactions_data),
                opening_balance=self._extract_opening_balance(transactions_data),
                closing_balance=self._extract_closing_balance(transactions_data),
                total_debits=self._calculate_total_debits(transactions_data),
                total_credits=self._calculate_total_credits(transactions_data),
                currency=self._extract_currency(transactions_data),
                statement_type=self._extract_statement_type(transactions_data),
                total_transactions_found=len(transactions_data.get('transactions', [])) if isinstance(transactions_data, dict) else 0,
                total_transactions_processed=len(transactions_data.get('transactions', [])) if isinstance(transactions_data, dict) else 0,
                transaction_type_summary=json.dumps(self._calculate_transaction_type_summary(transactions_data))
            )
            
            # Step 6: Atomic database insertion
            with _db_write_lock:
                db_record_id = self.data_access.insert_bank_upload(bank_upload)
            
            processing_time = time.time() - start_time
            logger.info(f"Bank statement processing completed", 
                       context={
                           "upload_id": upload_id,
                           "db_record_id": db_record_id,
                           "total_transactions": bank_upload.total_transactions_found,
                           "processing_time_seconds": processing_time
                       })
            
            return {
                "success": True,
                "upload_id": upload_id,
                "db_record_id": db_record_id,
                "file_name": file_name,
                "total_transactions": bank_upload.total_transactions_found,
                "total_debits": bank_upload.total_debits,
                "total_credits": bank_upload.total_credits,
                "processing_time_seconds": processing_time,
                "status": "completed"
            }
            
        except Exception as e:
            error_time = datetime.now().isoformat()
            logger.error(f"Bank statement processing failed", 
                        context={"upload_id": upload_id, "file_name": file_name}, 
                        error=e)
            
            # Store error record for debugging
            error_upload = BankTransactionUpload(
                upload_id=upload_id,
                file_name=file_name,
                file_path=file_path,
                file_hash=file_hash if 'file_hash' in locals() else "",
                file_size=file_size if 'file_size' in locals() else 0,
                processing_start=processing_start if 'processing_start' in locals() else error_time,
                processing_end=error_time,
                status="failed",
                error_message=str(e)
            )
            
            try:
                with _db_write_lock:
                    self.data_access.insert_bank_upload(error_upload)
            except Exception as db_error:
                logger.error(f"Failed to store error record", error=db_error)
            
            return {
                "success": False,
                "upload_id": upload_id,
                "error": str(e),
                "status": "failed"
            }
    
    def process_reconciliation(self, invoice_upload_id: int, bank_upload_id: int) -> Dict[str, Any]:
        """
        Process reconciliation between invoice and bank data with single-row JSON storage
        
        Workflow:
        1. Load JSON data from both uploads
        2. Run reconciliation algorithm on ALL data
        3. Build JSON structure with ALL match results
        4. Store in SINGLE database row
        5. Return reconciliation_id and summary
        """
        start_time = time.time()
        reconciliation_id = generate_reconciliation_id()
        
        try:
            # Step 1: Load source data from JSON columns
            invoice_data = self._load_invoice_data(invoice_upload_id)
            bank_data = self._load_bank_data(bank_upload_id)
            
            if not invoice_data or not bank_data:
                raise ValueError(f"Invalid source data: invoice_upload_id={invoice_upload_id}, bank_upload_id={bank_upload_id}")
            
            # Step 2: Start reconciliation
            reconciliation_start = datetime.now().isoformat()
            logger.info(f"Starting reconciliation for reconciliation_id: {reconciliation_id}", 
                       context={
                           "invoice_upload_id": invoice_upload_id,
                           "bank_upload_id": bank_upload_id,
                           "total_invoices": len(invoice_data.get('invoices', [])),
                           "total_transactions": len(bank_data.get('transactions', []))
                       })
            
            # Step 3: Convert to existing Transaction format for compatibility
            invoice_transactions = self._convert_invoices_to_transactions(invoice_data.get('invoices', []))
            bank_transactions = self._convert_bank_to_transactions(bank_data.get('transactions', []))
            
            # Step 4: Run reconciliation using existing algorithm
            reconciliation_result = find_matches(invoice_transactions, bank_transactions)
            
            # Step 5: Build comprehensive JSON structure
            reconciliation_json = self._build_reconciliation_json_structure(
                reconciliation_id=reconciliation_id,
                invoice_upload_id=invoice_upload_id,
                bank_upload_id=bank_upload_id,
                invoice_file_name=invoice_data.get('file_info', {}).get('file_name', ''),
                bank_file_name=bank_data.get('file_info', {}).get('file_name', ''),
                reconciliation_result=reconciliation_result,
                reconciliation_start=reconciliation_start
            )
            
            # Step 6: Create database record with single row
            reconciliation_match = ReconciliationMatch(
                reconciliation_id=reconciliation_id,
                invoice_upload_id=invoice_upload_id,
                bank_upload_id=bank_upload_id,
                invoice_file_name=invoice_data.get('file_info', {}).get('file_name', ''),
                bank_file_name=bank_data.get('file_info', {}).get('file_name', ''),
                reconciliation_timestamp=reconciliation_start,
                reconciliation_duration_seconds=int(time.time() - start_time),
                status="completed",
                reconciliation_match_json=json.dumps(reconciliation_json, indent=2),
                total_invoices_processed=len(invoice_data.get('invoices', [])),
                total_transactions_processed=len(bank_data.get('transactions', [])),
                total_matches_found=len(reconciliation_result.matches),
                partial_matches=0,  # TODO: Implement partial matching logic
                unmatched_invoices=len(reconciliation_result.only_in_invoices),
                unmatched_transactions=len(reconciliation_result.only_in_bank),
                total_amount_matched=sum(match.get('invoice_amount', 0) for match in reconciliation_result.matches),
                match_rate_percentage=(len(reconciliation_result.matches) / len(invoice_data.get('invoices', [])) * 100) if invoice_data.get('invoices') else 0
            )
            
            # Step 7: Atomic database insertion
            with _db_write_lock:
                db_record_id = self.data_access.insert_reconciliation_match(reconciliation_match)
            
            processing_time = time.time() - start_time
            logger.info(f"Reconciliation completed", 
                       context={
                           "reconciliation_id": reconciliation_id,
                           "db_record_id": db_record_id,
                           "total_matches": reconciliation_match.total_matches_found,
                           "match_rate": reconciliation_match.match_rate_percentage,
                           "processing_time_seconds": processing_time
                       })
            
            return {
                "success": True,
                "reconciliation_id": reconciliation_id,
                "db_record_id": db_record_id,
                "total_matches": reconciliation_match.total_matches_found,
                "match_rate_percentage": reconciliation_match.match_rate_percentage,
                "processing_time_seconds": processing_time,
                "status": "completed"
            }
            
        except Exception as e:
            error_time = datetime.now().isoformat()
            logger.error(f"Reconciliation failed", 
                        context={
                            "reconciliation_id": reconciliation_id,
                            "invoice_upload_id": invoice_upload_id,
                            "bank_upload_id": bank_upload_id
                        }, 
                        error=e)
            
            # Store error record for debugging
            error_match = ReconciliationMatch(
                reconciliation_id=reconciliation_id,
                invoice_upload_id=invoice_upload_id,
                bank_upload_id=bank_upload_id,
                reconciliation_timestamp=error_time,
                status="failed",
                error_message=str(e)
            )
            
            try:
                with _db_write_lock:
                    self.data_access.insert_reconciliation_match(error_match)
            except Exception as db_error:
                logger.error(f"Failed to store error record", error=db_error)
            
            return {
                "success": False,
                "reconciliation_id": reconciliation_id,
                "error": str(e),
                "status": "failed"
            }
    
    def _build_invoice_json_structure(self, upload_id: int, file_name: str, file_path: str,
                                   file_hash: str, file_size: int, invoices_data: Dict[str, Any],
                                   processing_start: str) -> Dict[str, Any]:
        """Build comprehensive JSON structure for invoice upload"""
        processing_end = datetime.now().isoformat()
        processing_duration = int((datetime.fromisoformat(processing_end.replace('Z', '+00:00')) - 
                                  datetime.fromisoformat(processing_start.replace('Z', '+00:00'))).total_seconds())
        
        invoices_list = invoices_data.get('invoices', [])
        
        return {
            "upload_id": upload_id,
            "file_info": {
                "file_name": file_name,
                "file_path": file_path,
                "file_hash": file_hash,
                "file_size": file_size,
                "pages_total": len(invoices_data.get('pages', [])) if isinstance(invoices_data, dict) else 1,
                "mime_type": "application/pdf"
            },
            "processing_info": {
                "upload_timestamp": processing_start,
                "processing_start": processing_start,
                "processing_end": processing_end,
                "processing_duration_seconds": processing_duration,
                "ocr_engine": "tesseract",
                "confidence_score": self._calculate_overall_confidence(invoices_data),
                "status": "completed"
            },
            "extraction_summary": {
                "total_invoices_found": len(invoices_list),
                "total_invoices_processed": len(invoices_list),
                "total_amount": self._calculate_total_amount(invoices_data),
                "currency_summary": self._calculate_currency_summary(invoices_data),
                "vendor_summary": self._calculate_vendor_summary(invoices_data),
                "date_range": {
                    "earliest_invoice_date": self._get_date_range_start(invoices_data),
                    "latest_invoice_date": self._get_date_range_end(invoices_data)
                }
            },
            "invoices": invoices_list
        }
    
    def _build_bank_json_structure(self, upload_id: int, file_name: str, file_path: str,
                                file_hash: str, file_size: int, transactions_data: Dict[str, Any],
                                processing_start: str) -> Dict[str, Any]:
        """Build comprehensive JSON structure for bank transaction upload"""
        processing_end = datetime.now().isoformat()
        processing_duration = int((datetime.fromisoformat(processing_end.replace('Z', '+00:00')) - 
                                  datetime.fromisoformat(processing_start.replace('Z', '+00:00'))).total_seconds())
        
        transactions_list = transactions_data.get('transactions', [])
        
        return {
            "upload_id": upload_id,
            "file_info": {
                "file_name": file_name,
                "file_path": file_path,
                "file_hash": file_hash,
                "file_size": file_size,
                "pages_total": len(transactions_data.get('pages', [])) if isinstance(transactions_data, dict) else 1,
                "mime_type": "application/pdf"
            },
            "processing_info": {
                "upload_timestamp": processing_start,
                "processing_start": processing_start,
                "processing_end": processing_end,
                "processing_duration_seconds": processing_duration,
                "ocr_engine": "tesseract",
                "confidence_score": self._calculate_overall_confidence(transactions_data),
                "status": "completed"
            },
            "statement_info": {
                "account_number": self._extract_account_number(transactions_data),
                "account_name": self._extract_account_name(transactions_data),
                "bank_name": self._extract_bank_name(transactions_data),
                "branch_name": self._extract_branch_name(transactions_data),
                "statement_period_start": self._extract_period_start(transactions_data),
                "statement_period_end": self._extract_period_end(transactions_data),
                "opening_balance": self._extract_opening_balance(transactions_data),
                "closing_balance": self._extract_closing_balance(transactions_data),
                "total_debits": self._calculate_total_debits(transactions_data),
                "total_credits": self._calculate_total_credits(transactions_data),
                "currency": self._extract_currency(transactions_data),
                "statement_type": self._extract_statement_type(transactions_data)
            },
            "extraction_summary": {
                "total_transactions_found": len(transactions_list),
                "total_transactions_processed": len(transactions_list),
                "total_debits": self._calculate_total_debits(transactions_data),
                "total_credits": self._calculate_total_credits(transactions_data),
                "transaction_types": self._calculate_transaction_type_summary(transactions_data)
            },
            "transactions": transactions_list
        }
    
    def _build_reconciliation_json_structure(self, reconciliation_id: int, invoice_upload_id: int,
                                           bank_upload_id: int, invoice_file_name: str, bank_file_name: str,
                                           reconciliation_result: ReconciliationResult, reconciliation_start: str) -> Dict[str, Any]:
        """Build comprehensive JSON structure for reconciliation results"""
        processing_end = datetime.now().isoformat()
        processing_duration = int((datetime.fromisoformat(processing_end.replace('Z', '+00:00')) - 
                                  datetime.fromisoformat(reconciliation_start.replace('Z', '+00:00'))).total_seconds())
        
        return {
            "reconciliation_id": reconciliation_id,
            "reconciliation_info": {
                "reconciliation_timestamp": reconciliation_start,
                "reconciliation_duration_seconds": processing_duration,
                "matching_algorithm": "hybrid_ml_rule_based",
                "confidence_threshold": 0.75,
                "status": "completed"
            },
            "source_documents": {
                "invoice_upload_id": invoice_upload_id,
                "invoice_file_name": invoice_file_name,
                "bank_upload_id": bank_upload_id,
                "bank_file_name": bank_file_name
            },
            "reconciliation_summary": {
                "total_invoices_processed": len(reconciliation_result.only_in_invoices) + len(reconciliation_result.matches),
                "total_transactions_processed": len(reconciliation_result.only_in_bank) + len(reconciliation_result.matches),
                "total_matches_found": len(reconciliation_result.matches),
                "partial_matches": 0,  # TODO: Implement partial matching
                "unmatched_invoices": len(reconciliation_result.only_in_invoices),
                "unmatched_transactions": len(reconciliation_result.only_in_bank),
                "total_amount_matched": sum(match.get('invoice_amount', 0) for match in reconciliation_result.matches),
                "match_rate_percentage": (len(reconciliation_result.matches) / (len(reconciliation_result.only_in_invoices) + len(reconciliation_result.matches)) * 100) if (len(reconciliation_result.only_in_invoices) + len(reconciliation_result.matches)) > 0 else 0
            },
            "matched": reconciliation_result.matches,
            "partial": [],  # TODO: Implement partial matching
            "unmatched": {
                "invoices": reconciliation_result.only_in_invoices,
                "bank_transactions": reconciliation_result.only_in_bank
            }
        }
    
    # Helper methods for data extraction and calculation
    def _calculate_overall_confidence(self, data: Dict[str, Any]) -> float:
        """Calculate overall confidence score from extracted data"""
        if not isinstance(data, dict):
            return 0.0
        
        # Simple confidence calculation - can be enhanced
        return 0.85  # Placeholder
    
    def _calculate_total_amount(self, invoices_data: Dict[str, Any]) -> Optional[float]:
        """Calculate total amount from all invoices"""
        if not isinstance(invoices_data, dict):
            return None
        
        invoices = invoices_data.get('invoices', [])
        total = 0.0
        for invoice in invoices:
            if isinstance(invoice, dict) and invoice.get('total_amount'):
                try:
                    total += float(invoice['total_amount'])
                except (ValueError, TypeError):
                    continue
        return total if total > 0 else None
    
    def _calculate_currency_summary(self, invoices_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate currency summary from all invoices"""
        if not isinstance(invoices_data, dict):
            return {}
        
        invoices = invoices_data.get('invoices', [])
        summary = {}
        for invoice in invoices:
            if isinstance(invoice, dict):
                currency = invoice.get('currency', 'USD')
                amount = invoice.get('total_amount', 0)
                if amount:
                    try:
                        summary[currency] = summary.get(currency, 0) + float(amount)
                    except (ValueError, TypeError):
                        continue
        return summary
    
    def _calculate_vendor_summary(self, invoices_data: Dict[str, Any]) -> Dict[str, int]:
        """Calculate vendor summary from all invoices"""
        if not isinstance(invoices_data, dict):
            return {}
        
        invoices = invoices_data.get('invoices', [])
        summary = {}
        for invoice in invoices:
            if isinstance(invoice, dict) and invoice.get('vendor_name'):
                vendor = invoice['vendor_name']
                summary[vendor] = summary.get(vendor, 0) + 1
        return summary
    
    def _get_date_range_start(self, invoices_data: Dict[str, Any]) -> Optional[str]:
        """Get earliest invoice date"""
        if not isinstance(invoices_data, dict):
            return None
        
        invoices = invoices_data.get('invoices', [])
        dates = []
        for invoice in invoices:
            if isinstance(invoice, dict) and invoice.get('invoice_date'):
                dates.append(invoice['invoice_date'])
        
        return min(dates) if dates else None
    
    def _get_date_range_end(self, invoices_data: Dict[str, Any]) -> Optional[str]:
        """Get latest invoice date"""
        if not isinstance(invoices_data, dict):
            return None
        
        invoices = invoices_data.get('invoices', [])
        dates = []
        for invoice in invoices:
            if isinstance(invoice, dict) and invoice.get('invoice_date'):
                dates.append(invoice['invoice_date'])
        
        return max(dates) if dates else None
    
    # Bank statement helper methods
    def _extract_account_number(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract account number from bank data"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('account_number', '****1234')
    
    def _extract_account_name(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract account name from bank data"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('account_name', 'Business Account')
    
    def _extract_bank_name(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract bank name from bank data"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('bank_name', 'Bank')
    
    def _extract_branch_name(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract branch name from bank data"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('branch_name')
    
    def _extract_period_start(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract statement period start"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('period_start')
    
    def _extract_period_end(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract statement period end"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('period_end')
    
    def _extract_opening_balance(self, transactions_data: Dict[str, Any]) -> Optional[float]:
        """Extract opening balance"""
        if not isinstance(transactions_data, dict):
            return None
        balance = transactions_data.get('opening_balance')
        return float(balance) if balance else None
    
    def _extract_closing_balance(self, transactions_data: Dict[str, Any]) -> Optional[float]:
        """Extract closing balance"""
        if not isinstance(transactions_data, dict):
            return None
        balance = transactions_data.get('closing_balance')
        return float(balance) if balance else None
    
    def _calculate_total_debits(self, transactions_data: Dict[str, Any]) -> Optional[float]:
        """Calculate total debits from all transactions"""
        if not isinstance(transactions_data, dict):
            return None
        
        transactions = transactions_data.get('transactions', [])
        total = 0.0
        for transaction in transactions:
            if isinstance(transaction, dict) and transaction.get('debit_amount'):
                try:
                    total += float(transaction['debit_amount'])
                except (ValueError, TypeError):
                    continue
        return total if total > 0 else None
    
    def _calculate_total_credits(self, transactions_data: Dict[str, Any]) -> Optional[float]:
        """Calculate total credits from all transactions"""
        if not isinstance(transactions_data, dict):
            return None
        
        transactions = transactions_data.get('transactions', [])
        total = 0.0
        for transaction in transactions:
            if isinstance(transaction, dict) and transaction.get('credit_amount'):
                try:
                    total += float(transaction['credit_amount'])
                except (ValueError, TypeError):
                    continue
        return total if total > 0 else None
    
    def _extract_currency(self, transactions_data: Dict[str, Any]) -> str:
        """Extract currency from bank data"""
        if not isinstance(transactions_data, dict):
            return "USD"
        return transactions_data.get('currency', 'USD')
    
    def _extract_statement_type(self, transactions_data: Dict[str, Any]) -> Optional[str]:
        """Extract statement type"""
        if not isinstance(transactions_data, dict):
            return None
        return transactions_data.get('statement_type', 'checking')
    
    def _calculate_transaction_type_summary(self, transactions_data: Dict[str, Any]) -> Dict[str, int]:
        """Calculate transaction type summary"""
        if not isinstance(transactions_data, dict):
            return {}
        
        transactions = transactions_data.get('transactions', [])
        summary = {}
        for transaction in transactions:
            if isinstance(transaction, dict) and transaction.get('transaction_type'):
                t_type = transaction['transaction_type']
                summary[t_type] = summary.get(t_type, 0) + 1
        return summary
    
    # Reconciliation helper methods
    def _load_invoice_data(self, invoice_upload_id: int) -> Optional[Dict[str, Any]]:
        """Load invoice JSON data from database"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT invoice_json FROM production_invoice_uploads WHERE upload_id = ?",
                (invoice_upload_id,)
            )
            result = cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to load invoice data", context={"upload_id": invoice_upload_id}, error=e)
            return None
        finally:
            conn.close()
    
    def _load_bank_data(self, bank_upload_id: int) -> Optional[Dict[str, Any]]:
        """Load bank transaction JSON data from database"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT bank_transaction_json FROM production_bank_uploads WHERE upload_id = ?",
                (bank_upload_id,)
            )
            result = cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to load bank data", context={"upload_id": bank_upload_id}, error=e)
            return None
        finally:
            conn.close()
    
    def _convert_invoices_to_transactions(self, invoices: List[Dict[str, Any]]) -> List[Transaction]:
        """Convert invoice JSON to Transaction objects for compatibility"""
        transactions = []
        for invoice in invoices:
            if isinstance(invoice, dict):
                transaction = Transaction(
                    source="invoice",
                    description=invoice.get('vendor_name', ''),
                    amount=invoice.get('total_amount', 0),
                    date=invoice.get('invoice_date'),
                    vendor_name=invoice.get('vendor_name'),
                    invoice_number=invoice.get('invoice_number'),
                    currency=invoice.get('currency', 'USD')
                )
                transactions.append(transaction)
        return transactions
    
    def _convert_bank_to_transactions(self, transactions: List[Dict[str, Any]]) -> List[Transaction]:
        """Convert bank transaction JSON to Transaction objects for compatibility"""
        transaction_objects = []
        for transaction in transactions:
            if isinstance(transaction, dict):
                # Use debit_amount if available, otherwise credit_amount
                amount = transaction.get('debit_amount', 0) or transaction.get('credit_amount', 0)
                
                transaction_obj = Transaction(
                    source="bank",
                    description=transaction.get('description', ''),
                    amount=amount,
                    date=transaction.get('transaction_date'),
                    currency=transaction.get('currency', 'USD'),
                    reference_id=transaction.get('reference_number'),
                    direction='debit' if transaction.get('debit_amount') else 'credit'
                )
                transaction_objects.append(transaction_obj)
        return transaction_objects


# === Production API Integration ===

class ProductionJSONAPI:
    """API endpoints for production JSON storage system"""
    
    def __init__(self, workflows: ProductionJSONWorkflows):
        self.workflows = workflows
    
    def upload_invoice_file(self, file_data: bytes, file_name: str) -> Dict[str, Any]:
        """Handle invoice file upload with JSON storage"""
        # Save file temporarily
        temp_path = os.path.join(self.workflows.invoice_upload_dir, f"temp_{file_name}")
        try:
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # Process with JSON workflow
            result = self.workflows.process_invoice_upload(temp_path, file_name)
            
            # Move to permanent location if successful
            if result.get('success'):
                permanent_path = os.path.join(self.workflows.invoice_upload_dir, f"invoice_{result['upload_id']}_{file_name}")
                os.rename(temp_path, permanent_path)
                result['file_path'] = permanent_path
            else:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            return result
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
    
    def upload_bank_file(self, file_data: bytes, file_name: str) -> Dict[str, Any]:
        """Handle bank statement file upload with JSON storage"""
        # Save file temporarily
        temp_path = os.path.join(self.workflows.bank_upload_dir, f"temp_{file_name}")
        try:
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # Process with JSON workflow
            result = self.workflows.process_bank_upload(temp_path, file_name)
            
            # Move to permanent location if successful
            if result.get('success'):
                permanent_path = os.path.join(self.workflows.bank_upload_dir, f"bank_{result['upload_id']}_{file_name}")
                os.rename(temp_path, permanent_path)
                result['file_path'] = permanent_path
            else:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            return result
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
    
    def run_reconciliation(self, invoice_upload_id: int, bank_upload_id: int) -> Dict[str, Any]:
        """Run reconciliation with JSON storage"""
        return self.workflows.process_reconciliation(invoice_upload_id, bank_upload_id)
    
    def get_invoice_data(self, upload_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve complete invoice JSON data"""
        return self.workflows._load_invoice_data(upload_id)
    
    def get_bank_data(self, upload_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve complete bank transaction JSON data"""
        return self.workflows._load_bank_data(upload_id)
    
    def get_reconciliation_data(self, reconciliation_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve complete reconciliation JSON data"""
        import sqlite3
        conn = sqlite3.connect(self.workflows.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT reconciliation_match_json FROM production_reconciliation_matches WHERE reconciliation_id = ?",
                (reconciliation_id,)
            )
            result = cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to load reconciliation data", context={"reconciliation_id": reconciliation_id}, error=e)
            return None
        finally:
            conn.close()


# === System Initialization ===

def initialize_production_json_system(db_path: str, upload_folder: str) -> ProductionJSONAPI:
    """Initialize the complete production JSON storage system"""
    
    # Initialize database tables
    data_access = ProductionJSONDataAccess(db_path)
    data_access.init_production_tables()
    
    # Create workflows
    workflows = ProductionJSONWorkflows(db_path, upload_folder)
    
    # Create API interface
    api = ProductionJSONAPI(workflows)
    
    logger.info("Production JSON storage system initialized", 
               context={"db_path": db_path, "upload_folder": upload_folder})
    
    return api
