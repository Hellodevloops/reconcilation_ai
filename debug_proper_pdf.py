#!/usr/bin/env python3

import os
import sys
import tempfile
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.multi_invoice_processor import multi_invoice_processor

def create_test_pdf():
    """Create a proper PDF with text content using reportlab"""
    temp_path = tempfile.mktemp(suffix='.pdf')
    
    try:
        # Create PDF with reportlab
        c = canvas.Canvas(temp_path, pagesize=letter)
        c.setFont("Helvetica", 12)
        
        # Add invoice content
        c.drawString(72, 750, "Invoice #001")
        c.drawString(72, 730, "Date: 2024-01-15")
        c.drawString(72, 710, "Vendor: Test Company")
        c.drawString(72, 690, "Amount: $100.00")
        c.drawString(72, 670, "Due Date: 2024-02-15")
        
        # Add line items
        c.drawString(72, 630, "Line Item 1: $50.00")
        c.drawString(72, 610, "Line Item 2: $50.00")
        
        c.save()
        return temp_path
    except Exception as e:
        print(f"Error creating PDF: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None

def test_pdf_extraction():
    """Test PDF text extraction and invoice processing"""
    
    # Create a proper PDF
    temp_pdf_path = create_test_pdf()
    if not temp_pdf_path:
        return
    
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
