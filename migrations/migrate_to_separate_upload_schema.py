"""
Migration Script: Implement Separate Upload & Reconciliation Schema

This script migrates from the current unified schema to the new separate upload schema
that meets the requirement for:
- Separate invoice and bank statement upload tables with unique IDs
- Reconciliation table storing both invoice_upload_id and bank_upload_id
- All reconciliation results stored as JSON under one reconciliation_id
- Clear traceability for accountants

Migration Strategy:
1. Create new separate upload tables
2. Migrate existing data from unified tables
3. Create new reconciliation records with proper ID linking
4. Validate data integrity
5. Optionally drop old tables (commented out for safety)
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Import the new models
from models.separate_upload_reconciliation_models import (
    SeparateUploadDataAccess,
    InvoiceUpload,
    BankStatementUpload,
    ReconciliationRecord,
    validate_separate_upload_json_structure,
    calculate_file_hash
)


class SeparateUploadMigration:
    """Handles migration to separate upload schema"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.data_access = SeparateUploadDataAccess(db_path)
        self.migration_log = []
    
    def log_message(self, message: str, level: str = "INFO"):
        """Log migration message"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {level}: {message}"
        self.migration_log.append(log_entry)
        print(log_entry)
    
    def check_existing_tables(self) -> Dict[str, bool]:
        """Check which tables exist in current database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            AND name IN ('document_uploads', 'extracted_invoices', 'bank_transactions', 
                        'production_invoice_uploads', 'production_bank_uploads', 
                        'production_reconciliation_matches')
        """)
        
        existing_tables = {row[0]: True for row in cursor.fetchall()}
        conn.close()
        
        return existing_tables
    
    def backup_current_data(self) -> bool:
        """Create backup of current data before migration"""
        try:
            backup_path = f"{self.db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Copy database file
            import shutil
            shutil.copy2(self.db_path, backup_path)
            
            self.log_message(f"Created database backup: {backup_path}")
            return True
            
        except Exception as e:
            self.log_message(f"Failed to create backup: {str(e)}", "ERROR")
            return False
    
    def migrate_from_unified_schema(self) -> bool:
        """Migrate from unified document_uploads schema"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get invoice uploads from unified table
            cursor.execute("""
                SELECT * FROM document_uploads 
                WHERE document_type = 'invoice'
                ORDER BY created_at
            """)
            
            invoice_columns = [description[0] for description in cursor.description]
            invoice_rows = cursor.fetchall()
            
            self.log_message(f"Found {len(invoice_rows)} invoice uploads to migrate")
            
            # Migrate invoice uploads
            for row in invoice_rows:
                row_data = dict(zip(invoice_columns, row))
                
                # Create new invoice upload record
                invoice_upload = InvoiceUpload(
                    file_name=row_data.get('file_name', ''),
                    file_path=row_data.get('file_path', ''),
                    file_hash=row_data.get('file_hash', ''),
                    file_size=row_data.get('file_size', 0),
                    mime_type=row_data.get('mime_type', ''),
                    upload_timestamp=row_data.get('upload_timestamp', ''),
                    processing_start=row_data.get('processing_start'),
                    processing_end=row_data.get('processing_end'),
                    processing_duration_seconds=None,
                    ocr_engine="tesseract",
                    confidence_score=row_data.get('extraction_confidence'),
                    status=row_data.get('processing_status', 'pending'),
                    invoice_data_json=self._convert_unified_to_invoice_json(row_data),
                    total_invoices_found=row_data.get('total_documents_found', 0),
                    total_invoices_processed=row_data.get('total_documents_processed', 0),
                    total_amount=row_data.get('total_amount'),
                    currency_summary=row_data.get('currency_summary'),
                    vendor_summary=self._extract_vendor_summary(row_data),
                    date_range_start=None,
                    date_range_end=None,
                    error_message=row_data.get('error_message'),
                    created_at=row_data.get('created_at', ''),
                    updated_at=row_data.get('updated_at', '')
                )
                
                try:
                    new_invoice_upload_id = self.data_access.insert_invoice_upload(invoice_upload)
                    self.log_message(f"Migrated invoice upload: {row_data.get('file_name')} -> ID: {new_invoice_upload_id}")
                except Exception as e:
                    self.log_message(f"Failed to migrate invoice upload {row_data.get('file_name')}: {str(e)}", "ERROR")
            
            # Get bank statement uploads from unified table
            cursor.execute("""
                SELECT * FROM document_uploads 
                WHERE document_type = 'bank_statement'
                ORDER BY created_at
            """)
            
            bank_columns = [description[0] for description in cursor.description]
            bank_rows = cursor.fetchall()
            
            self.log_message(f"Found {len(bank_rows)} bank statement uploads to migrate")
            
            # Migrate bank statement uploads
            for row in bank_rows:
                row_data = dict(zip(bank_columns, row))
                
                # Create new bank upload record
                bank_upload = BankStatementUpload(
                    file_name=row_data.get('file_name', ''),
                    file_path=row_data.get('file_path', ''),
                    file_hash=row_data.get('file_hash', ''),
                    file_size=row_data.get('file_size', 0),
                    mime_type=row_data.get('mime_type', ''),
                    upload_timestamp=row_data.get('upload_timestamp', ''),
                    processing_start=row_data.get('processing_start'),
                    processing_end=row_data.get('processing_end'),
                    processing_duration_seconds=None,
                    ocr_engine="tesseract",
                    confidence_score=row_data.get('extraction_confidence'),
                    status=row_data.get('processing_status', 'pending'),
                    bank_data_json=self._convert_unified_to_bank_json(row_data),
                    account_number=None,
                    account_name=None,
                    bank_name=None,
                    statement_period_start=None,
                    statement_period_end=None,
                    opening_balance=None,
                    closing_balance=None,
                    total_debits=None,
                    total_credits=None,
                    currency="USD",
                    statement_type=None,
                    total_transactions_found=row_data.get('total_documents_found', 0),
                    total_transactions_processed=row_data.get('total_documents_processed', 0),
                    transaction_type_summary=self._extract_transaction_summary(row_data),
                    error_message=row_data.get('error_message'),
                    created_at=row_data.get('created_at', ''),
                    updated_at=row_data.get('updated_at', '')
                )
                
                try:
                    new_bank_upload_id = self.data_access.insert_bank_upload(bank_upload)
                    self.log_message(f"Migrated bank upload: {row_data.get('file_name')} -> ID: {new_bank_upload_id}")
                except Exception as e:
                    self.log_message(f"Failed to migrate bank upload {row_data.get('file_name')}: {str(e)}", "ERROR")
            
            conn.close()
            return True
            
        except Exception as e:
            self.log_message(f"Failed to migrate from unified schema: {str(e)}", "ERROR")
            return False
    
    def migrate_from_production_schema(self) -> bool:
        """Migrate from production JSON schema"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if production tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='production_invoice_uploads'")
            if not cursor.fetchone():
                self.log_message("Production tables not found, skipping production migration")
                return True
            
            # Migrate production invoice uploads
            cursor.execute("SELECT * FROM production_invoice_uploads ORDER BY created_at")
            prod_invoice_columns = [description[0] for description in cursor.description]
            prod_invoice_rows = cursor.fetchall()
            
            self.log_message(f"Found {len(prod_invoice_rows)} production invoice uploads to migrate")
            
            for row in prod_invoice_rows:
                row_data = dict(zip(prod_invoice_columns, row))
                
                invoice_upload = InvoiceUpload(
                    file_name=row_data.get('file_name', ''),
                    file_path=row_data.get('file_path', ''),
                    file_hash=row_data.get('file_hash', ''),
                    file_size=row_data.get('file_size', 0),
                    mime_type=row_data.get('mime_type', ''),
                    upload_timestamp=row_data.get('upload_timestamp', ''),
                    processing_start=row_data.get('processing_start'),
                    processing_end=row_data.get('processing_end'),
                    processing_duration_seconds=row_data.get('processing_duration_seconds'),
                    ocr_engine=row_data.get('ocr_engine', 'tesseract'),
                    confidence_score=row_data.get('confidence_score'),
                    status=row_data.get('status', 'pending'),
                    invoice_data_json=self._convert_production_to_invoice_json(row_data),
                    total_invoices_found=row_data.get('total_invoices_found', 0),
                    total_invoices_processed=row_data.get('total_invoices_processed', 0),
                    total_amount=row_data.get('total_amount'),
                    currency_summary=row_data.get('currency_summary'),
                    vendor_summary=row_data.get('vendor_summary'),
                    date_range_start=row_data.get('date_range_start'),
                    date_range_end=row_data.get('date_range_end'),
                    error_message=row_data.get('error_message'),
                    created_at=row_data.get('created_at', ''),
                    updated_at=row_data.get('updated_at', '')
                )
                
                try:
                    new_invoice_upload_id = self.data_access.insert_invoice_upload(invoice_upload)
                    self.log_message(f"Migrated production invoice upload: {row_data.get('file_name')} -> ID: {new_invoice_upload_id}")
                except Exception as e:
                    self.log_message(f"Failed to migrate production invoice upload {row_data.get('file_name')}: {str(e)}", "ERROR")
            
            # Migrate production bank uploads
            cursor.execute("SELECT * FROM production_bank_uploads ORDER BY created_at")
            prod_bank_columns = [description[0] for description in cursor.description]
            prod_bank_rows = cursor.fetchall()
            
            self.log_message(f"Found {len(prod_bank_rows)} production bank uploads to migrate")
            
            for row in prod_bank_rows:
                row_data = dict(zip(prod_bank_columns, row))
                
                bank_upload = BankStatementUpload(
                    file_name=row_data.get('file_name', ''),
                    file_path=row_data.get('file_path', ''),
                    file_hash=row_data.get('file_hash', ''),
                    file_size=row_data.get('file_size', 0),
                    mime_type=row_data.get('mime_type', ''),
                    upload_timestamp=row_data.get('upload_timestamp', ''),
                    processing_start=row_data.get('processing_start'),
                    processing_end=row_data.get('processing_end'),
                    processing_duration_seconds=row_data.get('processing_duration_seconds'),
                    ocr_engine=row_data.get('ocr_engine', 'tesseract'),
                    confidence_score=row_data.get('confidence_score'),
                    status=row_data.get('status', 'pending'),
                    bank_data_json=self._convert_production_to_bank_json(row_data),
                    account_number=row_data.get('account_number'),
                    account_name=row_data.get('account_name'),
                    bank_name=row_data.get('bank_name'),
                    statement_period_start=row_data.get('statement_period_start'),
                    statement_period_end=row_data.get('statement_period_end'),
                    opening_balance=row_data.get('opening_balance'),
                    closing_balance=row_data.get('closing_balance'),
                    total_debits=row_data.get('total_debits'),
                    total_credits=row_data.get('total_credits'),
                    currency=row_data.get('currency', 'USD'),
                    statement_type=row_data.get('statement_type'),
                    total_transactions_found=row_data.get('total_transactions_found', 0),
                    total_transactions_processed=row_data.get('total_transactions_processed', 0),
                    transaction_type_summary=row_data.get('transaction_type_summary'),
                    error_message=row_data.get('error_message'),
                    created_at=row_data.get('created_at', ''),
                    updated_at=row_data.get('updated_at', '')
                )
                
                try:
                    new_bank_upload_id = self.data_access.insert_bank_upload(bank_upload)
                    self.log_message(f"Migrated production bank upload: {row_data.get('file_name')} -> ID: {new_bank_upload_id}")
                except Exception as e:
                    self.log_message(f"Failed to migrate production bank upload {row_data.get('file_name')}: {str(e)}", "ERROR")
            
            # Migrate production reconciliation matches
            cursor.execute("SELECT * FROM production_reconciliation_matches ORDER BY created_at")
            prod_reconcile_columns = [description[0] for description in cursor.description]
            prod_reconcile_rows = cursor.fetchall()
            
            self.log_message(f"Found {len(prod_reconcile_rows)} production reconciliation matches to migrate")
            
            for row in prod_reconcile_rows:
                row_data = dict(zip(prod_reconcile_columns, row))
                
                # Find corresponding upload IDs in new schema
                invoice_upload_id = self._find_new_upload_id('invoice', row_data.get('invoice_upload_id'))
                bank_upload_id = self._find_new_upload_id('bank', row_data.get('bank_upload_id'))
                
                if invoice_upload_id and bank_upload_id:
                    reconciliation_record = ReconciliationRecord(
                        invoice_upload_id=invoice_upload_id,
                        bank_upload_id=bank_upload_id,
                        invoice_file_name=row_data.get('invoice_file_name'),
                        bank_file_name=row_data.get('bank_file_name'),
                        reconciliation_timestamp=row_data.get('reconciliation_timestamp', ''),
                        reconciliation_duration_seconds=row_data.get('reconciliation_duration_seconds'),
                        matching_algorithm=row_data.get('matching_algorithm', 'hybrid_ml_rule_based'),
                        confidence_threshold=row_data.get('confidence_threshold', 0.75),
                        status=row_data.get('status', 'pending'),
                        reconciliation_results_json=self._convert_production_to_reconciliation_json(row_data),
                        total_invoices_processed=row_data.get('total_invoices_processed', 0),
                        total_transactions_processed=row_data.get('total_transactions_processed', 0),
                        total_matches_found=row_data.get('total_matches_found', 0),
                        partial_matches=row_data.get('partial_matches', 0),
                        unmatched_invoices=row_data.get('unmatched_invoices', 0),
                        unmatched_transactions=row_data.get('unmatched_transactions', 0),
                        total_amount_matched=row_data.get('total_amount_matched'),
                        match_rate_percentage=row_data.get('match_rate_percentage'),
                        error_message=row_data.get('error_message'),
                        created_at=row_data.get('created_at', ''),
                        updated_at=row_data.get('updated_at', '')
                    )
                    
                    try:
                        new_reconciliation_id = self.data_access.insert_reconciliation_record(reconciliation_record)
                        self.log_message(f"Migrated reconciliation record -> ID: {new_reconciliation_id}")
                    except Exception as e:
                        self.log_message(f"Failed to migrate reconciliation record: {str(e)}", "ERROR")
                else:
                    self.log_message(f"Could not find corresponding upload IDs for reconciliation record", "ERROR")
            
            conn.close()
            return True
            
        except Exception as e:
            self.log_message(f"Failed to migrate from production schema: {str(e)}", "ERROR")
            return False
    
    def _convert_unified_to_invoice_json(self, row_data: Dict) -> Optional[str]:
        """Convert unified document upload data to invoice JSON format"""
        try:
            invoice_json = {
                "upload_info": {
                    "invoice_upload_id": row_data.get('id'),
                    "file_name": row_data.get('file_name', ''),
                    "file_path": row_data.get('file_path', ''),
                    "file_hash": row_data.get('file_hash', ''),
                    "file_size": row_data.get('file_size', 0),
                    "pages_total": 0,  # Not available in unified schema
                    "mime_type": row_data.get('mime_type', '')
                },
                "processing_info": {
                    "upload_timestamp": row_data.get('upload_timestamp', ''),
                    "processing_start": row_data.get('processing_start'),
                    "processing_end": row_data.get('processing_end'),
                    "processing_duration_seconds": None,
                    "ocr_engine": "tesseract",
                    "confidence_score": row_data.get('extraction_confidence'),
                    "status": row_data.get('processing_status', 'pending')
                },
                "extraction_summary": {
                    "total_invoices_found": row_data.get('total_documents_found', 0),
                    "total_invoices_processed": row_data.get('total_documents_processed', 0),
                    "total_amount": row_data.get('total_amount', 0.0),
                    "currency_summary": json.loads(row_data.get('currency_summary') or '{}'),
                    "vendor_summary": {},  # Will be populated separately
                    "date_range": {
                        "earliest_invoice_date": None,
                        "latest_invoice_date": None
                    }
                },
                "invoices": []  # Would need to extract from extracted_invoices table
            }
            
            return json.dumps(invoice_json)
            
        except Exception as e:
            self.log_message(f"Failed to convert unified to invoice JSON: {str(e)}", "ERROR")
            return None
    
    def _convert_unified_to_bank_json(self, row_data: Dict) -> Optional[str]:
        """Convert unified document upload data to bank JSON format"""
        try:
            bank_json = {
                "upload_info": {
                    "bank_upload_id": row_data.get('id'),
                    "file_name": row_data.get('file_name', ''),
                    "file_path": row_data.get('file_path', ''),
                    "file_hash": row_data.get('file_hash', ''),
                    "file_size": row_data.get('file_size', 0),
                    "pages_total": 0,  # Not available in unified schema
                    "mime_type": row_data.get('mime_type', '')
                },
                "processing_info": {
                    "upload_timestamp": row_data.get('upload_timestamp', ''),
                    "processing_start": row_data.get('processing_start'),
                    "processing_end": row_data.get('processing_end'),
                    "processing_duration_seconds": None,
                    "ocr_engine": "tesseract",
                    "confidence_score": row_data.get('extraction_confidence'),
                    "status": row_data.get('processing_status', 'pending')
                },
                "statement_info": {
                    "account_number": None,
                    "account_name": None,
                    "bank_name": None,
                    "statement_period_start": None,
                    "statement_period_end": None,
                    "opening_balance": None,
                    "closing_balance": None,
                    "total_debits": None,
                    "total_credits": None,
                    "currency": "USD",
                    "statement_type": None
                },
                "extraction_summary": {
                    "total_transactions_found": row_data.get('total_documents_found', 0),
                    "total_transactions_processed": row_data.get('total_documents_processed', 0),
                    "total_debits": 0.0,
                    "total_credits": 0.0,
                    "transaction_types": {}
                },
                "transactions": []  # Would need to extract from bank_transactions table
            }
            
            return json.dumps(bank_json)
            
        except Exception as e:
            self.log_message(f"Failed to convert unified to bank JSON: {str(e)}", "ERROR")
            return None
    
    def _convert_production_to_invoice_json(self, row_data: Dict) -> Optional[str]:
        """Convert production invoice upload to new invoice JSON format"""
        try:
            # Parse existing JSON and update structure
            existing_json = json.loads(row_data.get('invoice_json') or '{}')
            
            # Update upload_info with new ID structure
            if 'upload_info' in existing_json:
                existing_json['upload_info']['invoice_upload_id'] = row_data.get('upload_id')
            
            return json.dumps(existing_json)
            
        except Exception as e:
            self.log_message(f"Failed to convert production to invoice JSON: {str(e)}", "ERROR")
            return None
    
    def _convert_production_to_bank_json(self, row_data: Dict) -> Optional[str]:
        """Convert production bank upload to new bank JSON format"""
        try:
            # Parse existing JSON and update structure
            existing_json = json.loads(row_data.get('bank_transaction_json') or '{}')
            
            # Update upload_info with new ID structure
            if 'upload_info' in existing_json:
                existing_json['upload_info']['bank_upload_id'] = row_data.get('upload_id')
            
            return json.dumps(existing_json)
            
        except Exception as e:
            self.log_message(f"Failed to convert production to bank JSON: {str(e)}", "ERROR")
            return None
    
    def _convert_production_to_reconciliation_json(self, row_data: Dict) -> Optional[str]:
        """Convert production reconciliation to new reconciliation JSON format"""
        try:
            # Parse existing JSON and update structure
            existing_json = json.loads(row_data.get('reconciliation_match_json') or '{}')
            
            # Update reconciliation_info with new ID structure
            if 'reconciliation_info' in existing_json:
                existing_json['reconciliation_info']['reconciliation_id'] = row_data.get('reconciliation_id')
            
            return json.dumps(existing_json)
            
        except Exception as e:
            self.log_message(f"Failed to convert production to reconciliation JSON: {str(e)}", "ERROR")
            return None
    
    def _extract_vendor_summary(self, row_data: Dict) -> Optional[str]:
        """Extract vendor summary from metadata or other fields"""
        try:
            metadata = json.loads(row_data.get('metadata') or '{}')
            return json.dumps(metadata.get('vendor_summary', {}))
        except:
            return json.dumps({})
    
    def _extract_transaction_summary(self, row_data: Dict) -> Optional[str]:
        """Extract transaction type summary from metadata or other fields"""
        try:
            metadata = json.loads(row_data.get('metadata') or '{}')
            return json.dumps(metadata.get('transaction_types', {}))
        except:
            return json.dumps({})
    
    def _find_new_upload_id(self, upload_type: str, old_upload_id: int) -> Optional[int]:
        """Find new upload ID based on old upload ID and file hash"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if upload_type == 'invoice':
                # Find by looking up the old production invoice upload
                cursor.execute("""
                    SELECT invoice_upload_id FROM invoice_uploads 
                    WHERE file_hash = (
                        SELECT file_hash FROM production_invoice_uploads 
                        WHERE upload_id = ?
                    )
                """, (old_upload_id,))
            else:  # bank
                # Find by looking up the old production bank upload
                cursor.execute("""
                    SELECT bank_upload_id FROM bank_statement_uploads 
                    WHERE file_hash = (
                        SELECT file_hash FROM production_bank_uploads 
                        WHERE upload_id = ?
                    )
                """, (old_upload_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            self.log_message(f"Failed to find new upload ID for {upload_type} {old_upload_id}: {str(e)}", "ERROR")
            return None
    
    def validate_migration(self) -> Tuple[bool, List[str]]:
        """Validate migration results"""
        validation_errors = []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check new tables exist and have data
            cursor.execute("SELECT COUNT(*) FROM invoice_uploads")
            invoice_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM bank_statement_uploads")
            bank_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reconciliation_records")
            reconciliation_count = cursor.fetchone()[0]
            
            self.log_message(f"Validation: {invoice_count} invoice uploads, {bank_count} bank uploads, {reconciliation_count} reconciliation records")
            
            # Validate foreign key constraints
            cursor.execute("""
                SELECT COUNT(*) FROM reconciliation_records rr
                LEFT JOIN invoice_uploads iu ON rr.invoice_upload_id = iu.invoice_upload_id
                WHERE iu.invoice_upload_id IS NULL
            """)
            orphaned_invoice_reconciliations = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM reconciliation_records rr
                LEFT JOIN bank_statement_uploads bu ON rr.bank_upload_id = bu.bank_upload_id
                WHERE bu.bank_upload_id IS NULL
            """)
            orphaned_bank_reconciliations = cursor.fetchone()[0]
            
            if orphaned_invoice_reconciliations > 0:
                validation_errors.append(f"Found {orphaned_invoice_reconciliations} reconciliation records with invalid invoice_upload_id")
            
            if orphaned_bank_reconciliations > 0:
                validation_errors.append(f"Found {orphaned_bank_reconciliations} reconciliation records with invalid bank_upload_id")
            
            # Validate JSON structures
            cursor.execute("SELECT invoice_data_json FROM invoice_uploads WHERE invoice_data_json IS NOT NULL LIMIT 10")
            for row in cursor.fetchall():
                is_valid, error_msg = validate_separate_upload_json_structure(row[0], "invoice")
                if not is_valid:
                    validation_errors.append(f"Invalid invoice JSON structure: {error_msg}")
            
            cursor.execute("SELECT bank_data_json FROM bank_statement_uploads WHERE bank_data_json IS NOT NULL LIMIT 10")
            for row in cursor.fetchall():
                is_valid, error_msg = validate_separate_upload_json_structure(row[0], "bank")
                if not is_valid:
                    validation_errors.append(f"Invalid bank JSON structure: {error_msg}")
            
            cursor.execute("SELECT reconciliation_results_json FROM reconciliation_records WHERE reconciliation_results_json IS NOT NULL LIMIT 10")
            for row in cursor.fetchall():
                is_valid, error_msg = validate_separate_upload_json_structure(row[0], "reconciliation")
                if not is_valid:
                    validation_errors.append(f"Invalid reconciliation JSON structure: {error_msg}")
            
            conn.close()
            
            if validation_errors:
                self.log_message(f"Validation found {len(validation_errors)} errors", "ERROR")
                for error in validation_errors:
                    self.log_message(f"  - {error}", "ERROR")
                return False, validation_errors
            else:
                self.log_message("Migration validation passed successfully")
                return True, validation_errors
                
        except Exception as e:
            error_msg = f"Migration validation failed: {str(e)}"
            self.log_message(error_msg, "ERROR")
            validation_errors.append(error_msg)
            return False, validation_errors
    
    def run_migration(self) -> bool:
        """Run complete migration process"""
        self.log_message("Starting migration to separate upload schema")
        
        # Step 1: Check existing tables
        existing_tables = self.check_existing_tables()
        self.log_message(f"Existing tables: {list(existing_tables.keys())}")
        
        # Step 2: Create backup
        if not self.backup_current_data():
            self.log_message("Migration aborted: Failed to create backup", "ERROR")
            return False
        
        # Step 3: Initialize new schema
        try:
            self.data_access.init_separate_upload_tables()
            self.log_message("New separate upload schema initialized")
        except Exception as e:
            self.log_message(f"Failed to initialize new schema: {str(e)}", "ERROR")
            return False
        
        # Step 4: Migrate data based on existing schema
        migration_success = False
        
        if 'production_invoice_uploads' in existing_tables:
            migration_success = self.migrate_from_production_schema()
        elif 'document_uploads' in existing_tables:
            migration_success = self.migrate_from_unified_schema()
        else:
            self.log_message("No recognizable source schema found, creating empty new schema")
            migration_success = True
        
        if not migration_success:
            self.log_message("Data migration failed", "ERROR")
            return False
        
        # Step 5: Validate migration
        is_valid, errors = self.validate_migration()
        if not is_valid:
            self.log_message("Migration validation failed", "ERROR")
            return False
        
        # Step 6: Save migration log
        self._save_migration_log()
        
        self.log_message("Migration completed successfully")
        return True
    
    def _save_migration_log(self):
        """Save migration log to file"""
        try:
            log_file = f"migration_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_file, 'w') as f:
                f.write("\n".join(self.migration_log))
            self.log_message(f"Migration log saved to: {log_file}")
        except Exception as e:
            self.log_message(f"Failed to save migration log: {str(e)}", "ERROR")


def main():
    """Main migration function"""
    db_path = "reconciliation.db"  # Update with actual database path
    
    print("Separate Upload Schema Migration")
    print("=" * 50)
    print(f"Database: {db_path}")
    print()
    
    # Confirm migration
    response = input("This will migrate your database to the new separate upload schema. Continue? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled")
        return
    
    # Run migration
    migration = SeparateUploadMigration(db_path)
    success = migration.run_migration()
    
    if success:
        print("\n" + "=" * 50)
        print("Migration completed successfully!")
        print("Your database now uses the separate upload schema with:")
        print("- Separate invoice and bank statement upload tables")
        print("- Reconciliation records linking both upload IDs")
        print("- All results stored as JSON for clear traceability")
    else:
        print("\n" + "=" * 50)
        print("Migration failed! Check the migration log for details.")
        print("Your original data is safe in the backup file.")


if __name__ == "__main__":
    main()
