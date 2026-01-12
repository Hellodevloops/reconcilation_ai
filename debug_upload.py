#!/usr/bin/env python3

import sys
import os
import json
import traceback
from flask import Flask

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from database_manager import db_manager
from api.bank_statement_endpoints import register_bank_statement_routes
from api.multi_invoice_endpoints import register_multi_invoice_routes

def create_test_app():
    """Create test Flask app to test endpoints"""
    app = Flask(__name__)
    
    # Load config
    from config import UPLOAD_FOLDER, MAX_FILE_SIZE_BYTES
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_BYTES
    
    # Register routes
    register_bank_statement_routes(app)
    register_multi_invoice_routes(app)
    
    return app

def test_direct_bank_insert():
    """Test direct bank statement insertion without Flask"""
    print("=== TESTING DIRECT BANK STATEMENT INSERT ===")
    
    try:
        # Create minimal test data that matches exactly what the extraction should produce
        test_extracted_data = {
            "base_file_hash": "test_direct_hash",
            "statement_index": 1,
            "statements": {
                "1": {
                    "transactions": {
                        "1": {
                            "transaction_date": "2024-01-15",
                            "description": "Test Payment",
                            "amount": 100.50,
                            "type": "debit",
                            "balance": 1000.00
                        }
                    },
                    "invoice_data": {
                        "1": {
                            "invoice_number": "INV-001",
                            "description": "Test Payment for INV-001",
                            "extracted_from": "bank_statement"
                        }
                    }
                }
            }
        }
        
        # Exact INSERT matching the bank_statement_endpoints.py
        insert_query = """
            INSERT INTO bank_statements (
                statement_file_hash,
                statement_file_name,
                statement_file_path,
                processing_status,
                total_transactions,
                total_credits,
                total_debits,
                currency,
                extracted_data,
                confidence_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        statement_id = db_manager.execute_insert(
            insert_query,
            (
                "test_direct_hash_1642248000",
                "test_bank_statement.pdf",
                "/tmp/test_bank_statement.pdf",
                "completed",
                1,  # total_transactions
                0.0,  # total_credits
                100.50,  # total_debits
                "USD",
                json.dumps(test_extracted_data, ensure_ascii=False, default=str),
                0.85,
            ),
        )
        
        print(f"[SUCCESS] Direct bank statement insert: ID {statement_id}")
        
        # Verify
        result = db_manager.execute_query('SELECT * FROM bank_statements WHERE id = ?', (statement_id,))
        if result:
            record = result[0]
            print(f"[SUCCESS] Verification:")
            print(f"   File: {record['statement_file_name']}")
            print(f"   Transactions: {record['total_transactions']}")
            print(f"   Status: {record['processing_status']}")
            print(f"   Data length: {len(record['extracted_data'] or '')} chars")
        else:
            print("[ERROR] Verification FAILED: Record not found")
            
    except Exception as e:
        print(f"[ERROR] Direct bank statement insert FAILED: {e}")
        traceback.print_exc()

def test_direct_invoice_insert():
    """Test direct invoice insertion without Flask"""
    print("\n=== TESTING DIRECT INVOICE INSERT ===")
    
    try:
        # Create minimal test data
        test_extracted_payload = {
            "base_file_hash": "test_invoice_hash",
            "upload_index": 1,
            "uploads": {
                "1": {
                    "invoice_date": "2024-01-15",
                    "total_amount": 250.00,
                    "items": {
                        "1": {
                            "description": "Test Product",
                            "amount": 250.00
                        }
                    }
                }
            }
        }
        
        # Exact INSERT matching the multi_invoice_endpoints.py
        insert_query = """
            INSERT INTO invoices (
                file_upload_id,
                invoice_number,
                invoice_date,
                vendor_name,
                total_amount,
                tax_amount,
                net_amount,
                due_date,
                description,
                line_items,
                extracted_data,
                confidence_score,
                status,
                invoice_file_path,
                invoice_file_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        invoice_id = db_manager.execute_insert(
            insert_query,
            (
                None,
                "TEST-INV-002",
                "2024-01-15",
                "Test Vendor Corp",
                250.00,
                25.00,  # tax_amount
                225.00,  # net_amount
                "2024-02-15",
                "Test invoice for debugging",
                json.dumps({"1": {"description": "Test Product", "amount": 250.00}}, ensure_ascii=False, default=str),
                json.dumps(test_extracted_payload, ensure_ascii=False, default=str),
                0.90,
                "pending",
                "/tmp/test_invoice.pdf",
                "test_invoice_hash_1642248000",
            ),
        )
        
        print(f"[SUCCESS] Direct invoice insert: ID {invoice_id}")
        
        # Verify
        result = db_manager.execute_query('SELECT * FROM invoices WHERE id = ?', (invoice_id,))
        if result:
            record = result[0]
            print(f"[SUCCESS] Verification:")
            print(f"   Invoice Number: {record['invoice_number']}")
            print(f"   Vendor: {record['vendor_name']}")
            print(f"   Total Amount: {record['total_amount']}")
            print(f"   Status: {record['status']}")
        else:
            print("[ERROR] Verification FAILED: Record not found")
            
    except Exception as e:
        print(f"[ERROR] Direct invoice insert FAILED: {e}")
        traceback.print_exc()

def check_table_counts():
    """Check current table counts"""
    print("\n=== CURRENT TABLE COUNTS ===")
    
    try:
        # Bank statements
        result = db_manager.execute_query('SELECT COUNT(*) as count FROM bank_statements')
        bank_count = result[0]['count'] if result else 0
        print(f"Bank statements: {bank_count}")
        
        # Invoices
        result = db_manager.execute_query('SELECT COUNT(*) as count FROM invoices')
        invoice_count = result[0]['count'] if result else 0
        print(f"Invoices: {invoice_count}")
        
        # Show recent records
        if bank_count > 0:
            result = db_manager.execute_query('SELECT id, statement_file_name, processing_status, upload_timestamp FROM bank_statements ORDER BY id DESC LIMIT 3')
            print("\nRecent bank statements:")
            for row in result:
                print(f"  ID {row['id']}: {row['statement_file_name']} - {row['processing_status']} - {row['upload_timestamp']}")
        
        if invoice_count > 0:
            result = db_manager.execute_query('SELECT id, invoice_number, vendor_name, status, created_at FROM invoices ORDER BY id DESC LIMIT 3')
            print("\nRecent invoices:")
            for row in result:
                print(f"  ID {row['id']}: {row['invoice_number']} - {row['vendor_name']} - {row['status']} - {row['created_at']}")
                
    except Exception as e:
        print(f"❌ Error checking counts: {e}")

def main():
    print("DEBUGGING UPLOAD ISSUES")
    print("=" * 50)
    
    # Test direct database inserts first
    test_direct_bank_insert()
    test_direct_invoice_insert()
    check_table_counts()
    
    print("\n" + "=" * 50)
    print("If direct inserts work, the issue is in the Flask endpoints.")
    print("If direct inserts fail, the issue is in database/INSERT statements.")

if __name__ == "__main__":
    main()
