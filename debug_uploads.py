#!/usr/bin/env python3

import requests
import json
import os

# Test both invoice and bank statement uploads
def test_upload(endpoint, file_content, filename, file_type):
    """Test upload to specific endpoint"""
    url = f"http://localhost:5001{endpoint}"
    
    files = {
        'file': (filename, file_content, 'application/pdf')
    }
    
    try:
        response = requests.post(url, files=files)
        print(f"\n=== {file_type.upper()} UPLOAD TEST ===")
        print(f"URL: {url}")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success: {data.get('success', False)}")
            if 'id' in data:
                print(f"✅ Record ID: {data['id']}")
            if 'statement_id' in data:
                print(f"✅ Statement ID: {data['statement_id']}")
            if 'total_transactions' in data:
                print(f"✅ Transactions: {data['total_transactions']}")
            if 'total_invoices_found' in data:
                print(f"✅ Invoices Found: {data['total_invoices_found']}")
        else:
            print(f"❌ Error Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Upload Error: {e}")

# Create a simple test PDF content (minimal)
pdf_content = b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 1 0 R/Resources>>endobj\nxref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000079 00000 n \ntrailer<</Size 3/Root 1 0 R>>startxref\n10\n%%EOF"

# Test Invoice Upload
test_upload("/api/upload-invoice", pdf_content, "test_invoice.pdf", "Invoice")

# Test Bank Statement Upload  
test_upload("/api/upload-bank-statement", pdf_content, "test_bank.pdf", "Bank Statement")
