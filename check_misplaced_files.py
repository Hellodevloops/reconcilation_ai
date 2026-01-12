"""
Check Misplaced Files
Your bank statements are being uploaded to the wrong folder
"""

import os
import re
from pathlib import Path

def check_misplaced_files():
    """Check if bank statements are in the wrong folder"""
    print("CHECKING MISPLACED FILES")
    print("=" * 50)
    
    # Check invoices folder for bank statements
    invoice_dir = "uploads/invoices"
    bank_dir = "uploads/bank_statements"
    
    if not os.path.exists(invoice_dir):
        print("ERROR: Invoices directory not found")
        return
    
    # Get all PDF files in invoices folder
    invoice_files = [f for f in os.listdir(invoice_dir) if f.endswith('.pdf')]
    print(f"Found {len(invoice_files)} PDF files in invoices folder")
    
    # Check each file to see if it's actually a bank statement
    bank_statements_in_invoice_folder = []
    
    for pdf_file in invoice_files:
        file_path = os.path.join(invoice_dir, pdf_file)
        
        try:
            # Read first page to check content
            from PyPDF2 import PdfReader
            import io
            
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            reader = PdfReader(io.BytesIO(file_bytes))
            if len(reader.pages) == 0:
                continue
            
            # Get text from first page
            first_page_text = reader.pages[0].extract_text() or ""
            
            # Check if it looks like a bank statement
            bank_keywords = [
                'bank', 'statement', 'account', 'balance', 'transaction',
                'debit', 'credit', 'deposit', 'withdrawal', 'transfer',
                'revolut', ' Barclays', 'HSBC', 'Lloyds', 'NatWest'
            ]
            
            invoice_keywords = [
                'invoice', 'bill', 'payment advice', 'due', 'amount due',
                'vendor', 'client', 'customer', 'tax', 'VAT'
            ]
            
            lower_text = first_page_text.lower()
            
            bank_score = sum(1 for keyword in bank_keywords if keyword in lower_text)
            invoice_score = sum(1 for keyword in invoice_keywords if keyword in lower_text)
            
            print(f"\n{pdf_file}:")
            print(f"  Bank keywords: {bank_score}")
            print(f"  Invoice keywords: {invoice_score}")
            
            if bank_score > invoice_score:
                bank_statements_in_invoice_folder.append(pdf_file)
                print(f"  -> LIKELY BANK STATEMENT (in wrong folder)")
                
                # Show sample text
                sample_lines = first_page_text.splitlines()[:3]
                for line in sample_lines:
                    if line.strip():
                        print(f"     Sample: {line[:60]}")
            elif invoice_score > 0:
                print(f"  -> Invoice (correct folder)")
            else:
                print(f"  -> Unknown (need manual check)")
                
        except Exception as e:
            print(f"  Error reading {pdf_file}: {e}")
    
    print(f"\n{'=' * 50}")
    print(f"FOUND {len(bank_statements_in_invoice_folder)} BANK STATEMENTS IN WRONG FOLDER")
    print("=" * 50)
    
    if bank_statements_in_invoice_folder:
        print("Bank statements that need to be moved:")
        for i, filename in enumerate(bank_statements_in_invoice_folder):
            print(f"  {i+1}. {filename}")
        
        # Move them to correct folder
        print(f"\nMoving files to correct folder...")
        
        # Ensure bank_statements directory exists
        os.makedirs(bank_dir, exist_ok=True)
        
        moved_count = 0
        for filename in bank_statements_in_invoice_folder:
            src_path = os.path.join(invoice_dir, filename)
            dst_path = os.path.join(bank_dir, filename)
            
            try:
                # Check if destination already exists
                if os.path.exists(dst_path):
                    print(f"  Skipping {filename} (already exists in bank folder)")
                    continue
                
                # Move file
                os.rename(src_path, dst_path)
                print(f"  Moved: {filename}")
                moved_count += 1
                
            except Exception as e:
                print(f"  Error moving {filename}: {e}")
        
        print(f"\nSuccessfully moved {moved_count} files to bank_statements folder")
        
    else:
        print("No bank statements found in wrong folder")
    
    return bank_statements_in_invoice_folder


def test_moved_files():
    """Test the moved bank statement files"""
    print(f"\n{'=' * 50}")
    print("TESTING MOVED BANK STATEMENTS")
    print("=" * 50)
    
    bank_dir = "uploads/bank_statements"
    if not os.path.exists(bank_dir):
        print("Bank statements directory not found")
        return
    
    bank_files = [f for f in os.listdir(bank_dir) if f.endswith('.pdf')]
    print(f"Found {len(bank_files)} PDF files in bank_statements folder")
    
    for bank_file in bank_files:
        file_path = os.path.join(bank_dir, bank_file)
        
        try:
            # Read and extract text
            from PyPDF2 import PdfReader
            import io
            
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            reader = PdfReader(io.BytesIO(file_bytes))
            
            # Extract text from all pages
            all_text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    all_text += page_text + "\n"
            
            lines = [line.strip() for line in all_text.splitlines() if line.strip()]
            
            print(f"\n{bank_file}:")
            print(f"  Pages: {len(reader.pages)}")
            print(f"  Lines: {len(lines)}")
            
            # Show sample lines
            print("  Sample lines:")
            for i, line in enumerate(lines[:5]):
                print(f"    {i+1}. {line[:60]}")
            
            # Look for amounts
            amounts = []
            for line in lines:
                matches = re.findall(r"[-+]?\d[\d,]*\.?\d*", line)
                for match in matches:
                    try:
                        val = float(match.replace(",", ""))
                        if abs(val) >= 1.0:
                            amounts.append(val)
                    except ValueError:
                        continue
            
            print(f"  Significant amounts found: {len(amounts)}")
            if amounts:
                for i, amount in enumerate(amounts[:5]):
                    print(f"    {i+1}. {amount:10.2f}")
            
        except Exception as e:
            print(f"  Error processing {bank_file}: {e}")


def main():
    """Main function"""
    misplaced_files = check_misplaced_files()
    
    if misplaced_files:
        test_moved_files()
        
        print(f"\n{'=' * 50}")
        print("SOLUTION COMPLETE")
        print("=" * 50)
        print("1. Moved bank statements to correct folder")
        print("2. Try uploading bank statement again")
        print("3. Run reconciliation - should work now!")
    else:
        print(f"\n{'=' * 50}")
        print("NO MISPLACED FILES FOUND")
        print("=" * 50)
        print("Your bank statements might be:")
        print("1. In a different location")
        print("2. Not uploaded yet")
        print("3. In a different format")


if __name__ == "__main__":
    main()
