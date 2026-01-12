"""
Analyze File Content in Detail
Show exactly what's in your PDF file
"""

import os
import re
from pathlib import Path

def analyze_pdf_content():
    """Analyze the exact content of your PDF file"""
    print("ANALYZING PDF CONTENT")
    print("=" * 60)
    
    # Find your file
    uploads_dir = "uploads"
    invoice_dir = os.path.join(uploads_dir, "invoices")
    
    if not os.path.exists(invoice_dir):
        print("ERROR: Invoice directory not found")
        return
    
    invoice_files = [f for f in os.listdir(invoice_dir) if f.endswith('.pdf')]
    if not invoice_files:
        print("ERROR: No PDF files found")
        return
    
    test_file = os.path.join(invoice_dir, invoice_files[0])
    print(f"Analyzing file: {invoice_files[0]}")
    
    try:
        # Extract text
        from PyPDF2 import PdfReader
        import io
        
        with open(test_file, 'rb') as f:
            file_bytes = f.read()
        
        reader = PdfReader(io.BytesIO(file_bytes))
        print(f"Total pages: {len(reader.pages)}")
        
        # Analyze each page
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                print(f"\n{'=' * 40}")
                print(f"PAGE {i+1} CONTENT")
                print(f"{'=' * 40}")
                print(page_text)
                
                # Look for amount patterns on this page
                lines = page_text.splitlines()
                for line_num, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Look for amount patterns
                    if re.search(r'\b[0-9,]+\.[0-9]{2}\b', line):
                        print(f"\nLINE {line_num+1} (has amount): {line}")
                        
                        # Extract all numbers from this line
                        numbers = re.findall(r'[-+]?\d[\d,]*\.?\d*', line)
                        for num in numbers:
                            try:
                                val = float(num.replace(",", ""))
                                print(f"  Number: {val}")
                            except ValueError:
                                continue
            else:
                print(f"\nPAGE {i+1}: No text (scanned image)")
        
        # Full text analysis
        print(f"\n{'=' * 60}")
        print("FULL TEXT ANALYSIS")
        print(f"{'=' * 60}")
        
        all_text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                all_text += page_text + "\n"
        
        lines = [line.strip() for line in all_text.splitlines() if line.strip()]
        print(f"Total lines: {len(lines)}")
        
        # Find all lines with amounts
        amount_lines = []
        for line in lines:
            if re.search(r'\b[0-9,]+\.[0-9]{2}\b', line):
                amount_lines.append(line)
        
        print(f"Lines with amounts: {len(amount_lines)}")
        
        for i, line in enumerate(amount_lines):
            print(f"\n{i+1}. {line}")
            
            # Extract numbers
            numbers = re.findall(r'[-+]?\d[\d,]*\.?\d*', line)
            for num in numbers:
                try:
                    val = float(num.replace(",", ""))
                    if val >= 1.0:
                        print(f"   Significant amount: {val}")
                except ValueError:
                    continue
        
        # Look for specific patterns
        print(f"\n{'=' * 60}")
        print("PATTERN SEARCH")
        print(f"{'=' * 60}")
        
        # Payment advice patterns
        payment_advice_patterns = [
            r'payment advice',
            r'amount due',
            r'total due',
            r'invoice number',
            r'to:',
            r'due date',
            r'£\s*[0-9,]+\.[0-9]{2}',
            r'[0-9,]+\.[0-9]{2}\s*£'
        ]
        
        for pattern in payment_advice_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                print(f"Pattern '{pattern}': {len(matches)} matches")
                for match in matches[:3]:  # Show first 3
                    print(f"  - {match}")
        
        # Find vendor patterns
        vendor_patterns = [
            r'to:([A-Za-z0-9\s&.,\-]+)',
            r'([A-Z][A-Za-z\s]+LTD)',
            r'([A-Z][A-Za-z\s]+LIMITED)',
            r'([A-Z][A-Za-z\s]+INC)'
        ]
        
        print(f"\nVendor patterns:")
        for pattern in vendor_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                print(f"  {pattern}: {matches}")
        
        # Find invoice patterns
        invoice_patterns = [
            r'invoice number\s+([A-Za-z0-9\-]+)',
            r'INV[-\s]?([0-9]+)',
            r'invoice\s+([A-Za-z0-9\-]+)'
        ]
        
        print(f"\nInvoice patterns:")
        for pattern in invoice_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                print(f"  {pattern}: {matches}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    analyze_pdf_content()
    
    print(f"\n{'=' * 60}")
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print("\nNEXT STEPS:")
    print("1. If you see amounts but no transactions: Parser needs adjustment")
    print("2. If most pages are blank: Use OCR for scanned pages")
    print("3. If format is unusual: Create custom parser for this format")


if __name__ == "__main__":
    main()
