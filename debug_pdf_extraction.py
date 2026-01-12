#!/usr/bin/env python3

import os
import sys
import tempfile
from PyPDF2 import PdfReader
from PIL import Image
import pytesseract

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.multi_invoice_processor import multi_invoice_processor

def test_pdf_extraction():
    """Test PDF text extraction and invoice processing"""
    
    # Create a simple PDF with actual text content
    pdf_content = b"""%PDF-1.1
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Page/Parent 1 0 R/Resources<</Font/F1 3 0 R>>/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj
3 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
4 0 obj<</Length 44>>stream
BT
/F1 12 Tf
72 720 Td
(Invoice #001) Tj
72 700 Td
(Date: 2024-01-15) Tj
72 680 Td
(Vendor: Test Company) Tj
72 660 Td
(Total: $100.00) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000074 00000 n 
0000000114 00000 n 
0000000158 00000 n 
trailer<</Size 5/Root 1 0 R>>
startxref
10
%%EOF"""
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(pdf_content)
        temp_pdf_path = f.name
    
    try:
        print("=== PDF EXTRACTION TEST ===")
        
        # Test PDF text extraction
        print(f"Testing PDF: {temp_pdf_path}")
        text = ""
        try:
            with open(temp_pdf_path, "rb") as f:
                reader = PdfReader(f)
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    print(f"Page {i+1} text: '{page_text}'")
                    text += page_text + "\n"
        except Exception as e:
            print(f"PDF extraction error: {e}")
            text = ""
        
        print(f"Total extracted text: '{text}'")
        
        # Test invoice processing
        print("\n=== INVOICE PROCESSING TEST ===")
        try:
            inv = multi_invoice_processor._extract_invoice_from_text(text, 1, "test.pdf")
            print(f"Invoice object: {inv}")
            if inv:
                print(f"Invoice number: {getattr(inv, 'invoice_number', None)}")
                print(f"Invoice date: {getattr(inv, 'invoice_date', None)}")
                print(f"Vendor name: {getattr(inv, 'vendor_name', None)}")
                print(f"Total amount: {getattr(inv, 'total_amount', None)}")
                print(f"Line items: {getattr(inv, 'line_items', None)}")
            else:
                print("Invoice extraction returned None")
        except Exception as e:
            print(f"Invoice processing error: {e}")
            import traceback
            traceback.print_exc()
        
        # Test the complete extraction function
        print("\n=== COMPLETE EXTRACTION FUNCTION TEST ===")
        from api.multi_invoice_endpoints import _extract_invoice_structured
        try:
            result = _extract_invoice_structured(temp_pdf_path, ".pdf")
            print(f"Extraction result: {result}")
        except Exception as e:
            print(f"Complete extraction error: {e}")
            import traceback
            traceback.print_exc()
            
    finally:
        # Clean up temp file
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

if __name__ == "__main__":
    test_pdf_extraction()
