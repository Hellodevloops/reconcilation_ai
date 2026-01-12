#!/usr/bin/env python3

import os
import sys
from PyPDF2 import PdfReader

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.multi_invoice_processor import multi_invoice_processor

def check_uploaded_files():
    """Check the actual uploaded files to see what's in them"""
    
    print("=== CHECKING UPLOADED FILES ===")
    
    # Check latest invoice file
    invoice_path = "C:\\xampp\\htdocs\\reconcile\\aiprojects\\python_ocr_reconcile\\uploads\\invoices\\1767768202_test_invoice.pdf"
    if os.path.exists(invoice_path):
        print(f"\n--- INVOICE FILE: {invoice_path} ---")
        try:
            with open(invoice_path, "rb") as f:
                reader = PdfReader(f)
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    print(f"Page {i+1} text: '{page_text}'")
                    
                    # Test invoice processing on this text
                    try:
                        inv = multi_invoice_processor._extract_invoice_from_text(page_text, 1, os.path.basename(invoice_path))
                        print(f"Invoice extraction: {inv}")
                        if inv:
                            print(f"  Number: {getattr(inv, 'invoice_number', None)}")
                            print(f"  Date: {getattr(inv, 'invoice_date', None)}")
                            print(f"  Vendor: {getattr(inv, 'vendor_name', None)}")
                            print(f"  Total: {getattr(inv, 'total_amount', None)}")
                            print(f"  Items: {len(getattr(inv, 'line_items', []))}")
                    except Exception as e:
                        print(f"  Invoice processing error: {e}")
        except Exception as e:
            print(f"Error reading PDF: {e}")
    else:
        print(f"Invoice file not found: {invoice_path}")
    
    # Check latest bank statement file
    bank_path = "C:\\xampp\\htdocs\\reconcile\\aiprojects\\python_ocr_reconcile\\uploads\\bank_statements\\1767768202_test_bank.pdf"
    if os.path.exists(bank_path):
        print(f"\n--- BANK STATEMENT FILE: {bank_path} ---")
        try:
            with open(bank_path, "rb") as f:
                reader = PdfReader(f)
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    print(f"Page {i+1} text: '{page_text}'")
        except Exception as e:
            print(f"Error reading PDF: {e}")
    else:
        print(f"Bank statement file not found: {bank_path}")

if __name__ == "__main__":
    check_uploaded_files()
