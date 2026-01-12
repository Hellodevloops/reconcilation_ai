"""
Debug Bank Statement Processing
Find out why your bank statement PDF is not storing data
"""

import os
import re
from pathlib import Path

def debug_bank_statement():
    """Debug your bank statement PDF processing"""
    print("DEBUGGING BANK STATEMENT PDF")
    print("=" * 60)
    
    # Find bank statement files
    uploads_dir = "uploads"
    bank_dir = os.path.join(uploads_dir, "bank_statements")
    
    if not os.path.exists(bank_dir):
        print("ERROR: Bank statements directory not found")
        print(f"Looking in: {bank_dir}")
        return
    
    bank_files = [f for f in os.listdir(bank_dir) if f.endswith('.pdf')]
    if not bank_files:
        print("ERROR: No PDF bank statement files found")
        print("Files in bank_statements directory:")
        for f in os.listdir(bank_dir):
            print(f"  - {f}")
        return
    
    # Test each bank statement file
    for bank_file in bank_files:
        test_file = os.path.join(bank_dir, bank_file)
        print(f"\n{'-' * 50}")
        print(f"TESTING: {bank_file}")
        print(f"{'-' * 50}")
        
        try:
            # Read file
            with open(test_file, 'rb') as f:
                file_bytes = f.read()
            
            print(f"File size: {len(file_bytes)} bytes")
            
            # Test PDF extraction
            from PyPDF2 import PdfReader
            import io
            
            reader = PdfReader(io.BytesIO(file_bytes))
            total_pages = len(reader.pages)
            print(f"PDF pages: {total_pages}")
            
            if total_pages == 0:
                print("ERROR: PDF has no pages")
                continue
            
            # Extract text from all pages
            all_text = ""
            pages_with_text = 0
            
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    all_text += page_text + "\n"
                    pages_with_text += 1
                    print(f"Page {i+1}: {len(page_text)} characters")
                else:
                    print(f"Page {i+1}: No text (scanned image)")
            
            print(f"Pages with text: {pages_with_text}/{total_pages}")
            
            if pages_with_text == 0:
                print("WARNING: No text extracted - PDF might be scanned images")
                print("SOLUTION: Use OCR or convert to text-based PDF")
                continue
            
            # Split into lines
            lines = [line.strip() for line in all_text.splitlines() if line.strip()]
            print(f"Total lines extracted: {len(lines)}")
            
            # Show sample lines
            print("\nFirst 15 lines:")
            for i, line in enumerate(lines[:15]):
                print(f"  {i+1:2d}. {line[:80]}")
            
            # Find numbers
            numbers = []
            for line in lines:
                matches = re.findall(r"[-+]?\d[\d,]*\.?\d*", line)
                for match in matches:
                    try:
                        num = float(match.replace(",", ""))
                        numbers.append(num)
                    except ValueError:
                        continue
            
            print(f"\nNumbers found: {len(numbers)}")
            
            # Filter by minimum amount (1.0)
            significant = [n for n in numbers if abs(n) >= 1.0]
            print(f"Numbers >= 1.0: {len(significant)}")
            
            if significant:
                print("Sample significant numbers:")
                for i, num in enumerate(significant[:10]):
                    print(f"  {i+1:2d}. {num:10.2f}")
            else:
                print("WARNING: No significant numbers found")
                if numbers:
                    print("All numbers found (all < 1.0):")
                    for i, num in enumerate(numbers[:10]):
                        print(f"  {i+1:2d}. {num:10.2f}")
                    print("PROBLEM: All amounts are less than 1.0")
                    print("SOLUTION: Lower MIN_TRANSACTION_AMOUNT or check file content")
            
            # Test transaction parsing
            print(f"\nTesting transaction parsing...")
            try:
                # Try to import the parsing function
                import sys
                sys.path.insert(0, os.path.dirname(__file__))
                from app import parse_transactions_from_lines
                
                transactions = parse_transactions_from_lines(lines, source="bank")
                print(f"Parsed {len(transactions)} transactions")
                
                if transactions:
                    print("Sample transactions:")
                    for i, tx in enumerate(transactions[:5]):
                        print(f"  {i+1}. Amount: {tx.amount:10.2f} | Date: {tx.date or 'N/A'} | Desc: {tx.description[:50]}")
                else:
                    print("ERROR: No transactions parsed!")
                    print("This means the format doesn't match expected patterns")
                    
            except Exception as e:
                print(f"Error testing transaction parsing: {e}")
            
        except Exception as e:
            print(f"Error processing file: {e}")
            import traceback
            traceback.print_exc()


def check_bank_in_database():
    """Check what bank transactions are in the database"""
    print(f"\n{'=' * 60}")
    print("CHECKING BANK TRANSACTIONS IN DATABASE")
    print("=" * 60)
    
    try:
        import sqlite3
        db_path = "reconcile.db"
        
        if not os.path.exists(db_path):
            print("ERROR: Database not found")
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check recent bank transactions
        cursor.execute("""
            SELECT file_name, description, amount, date 
            FROM transactions 
            WHERE kind = 'bank' 
            ORDER BY id DESC 
            LIMIT 10
        """)
        recent_bank = cursor.fetchall()
        
        print(f"Recent bank transactions ({len(recent_bank)} shown):")
        for tx in recent_bank:
            print(f"  {tx[0][:30]} | {tx[1][:40]} | {tx[2]} | {tx[3]}")
        
        # Check if any bank transactions from today
        cursor.execute("""
            SELECT COUNT(*) FROM transactions 
            WHERE kind = 'bank' AND file_name LIKE '%bank%'
        """)
        bank_count = cursor.fetchone()[0]
        print(f"\nTotal bank transactions with 'bank' in filename: {bank_count}")
        
        # Check all bank transactions
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE kind = 'bank'")
        total_bank = cursor.fetchone()[0]
        print(f"Total bank transactions: {total_bank}")
        
        conn.close()
        
    except Exception as e:
        print(f"Database error: {e}")


def create_test_bank_statement():
    """Create a simple test bank statement"""
    print(f"\n{'=' * 60}")
    print("CREATING TEST BANK STATEMENT")
    print("=" * 60)
    
    # Create a simple CSV bank statement
    test_csv_content = """Date,Description,Amount,Balance
2024-02-14,FLOOZIE LTD,3708.67,5000.00
2024-03-14,FLOOZIE LTD,2737.19,1291.33
2024-04-14,FLOOZIE LTD,2911.54,0.00
2024-04-28,FLOOZIE LTD,1360.08,-1360.08"""
    
    test_csv_path = os.path.join("uploads", "bank_statements", "test_bank_statement.csv")
    os.makedirs(os.path.dirname(test_csv_path), exist_ok=True)
    
    with open(test_csv_path, 'w') as f:
        f.write(test_csv_content)
    
    print(f"Created test CSV: {test_csv_path}")
    print("This matches your invoice amounts for testing reconciliation")
    
    return test_csv_path


def main():
    """Main function"""
    debug_bank_statement()
    check_bank_in_database()
    
    # Create test file if needed
    create_test_bank_statement()
    
    print(f"\n{'=' * 60}")
    print("DIAGNOSIS COMPLETE")
    print("=" * 60)
    print("\nCOMMON BANK STATEMENT ISSUES:")
    print("1. PDF is scanned images (no text to extract)")
    print("2. Transaction amounts are less than 1.0")
    print("3. Format doesn't match expected patterns")
    print("4. File is corrupted or password protected")
    print("5. OCR failed on image-based PDF")
    print("\nSOLUTIONS:")
    print("1. Use CSV/Excel format instead of PDF")
    print("2. Convert scanned PDF to text using OCR")
    print("3. Check if amounts are >= 1.0")
    print("4. Try the test CSV file I created")


if __name__ == "__main__":
    main()
