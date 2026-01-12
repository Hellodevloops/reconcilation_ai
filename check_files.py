"""
Check Files Script
Simple debugging without Unicode issues
"""

import os
import sys
import re
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

def check_pdf_file():
    """Check PDF file processing"""
    print("CHECKING PDF FILE PROCESSING")
    print("=" * 50)
    
    # Find PDF file
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
    print(f"Testing file: {invoice_files[0]}")
    
    try:
        # Read file
        with open(test_file, 'rb') as f:
            file_bytes = f.read()
        
        print(f"File size: {len(file_bytes)} bytes")
        
        # Test PDF extraction
        try:
            from PyPDF2 import PdfReader
            import io
            
            reader = PdfReader(io.BytesIO(file_bytes))
            total_pages = len(reader.pages)
            print(f"PDF pages: {total_pages}")
            
            if total_pages == 0:
                print("ERROR: PDF has no pages")
                return
            
            # Extract text from first few pages
            all_text = ""
            pages_with_text = 0
            
            for i, page in enumerate(reader.pages[:5]):  # Check first 5 pages
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    all_text += page_text + "\n"
                    pages_with_text += 1
                    print(f"Page {i+1}: {len(page_text)} characters")
                else:
                    print(f"Page {i+1}: No text extracted (might be scanned image)")
            
            print(f"Pages with text: {pages_with_text}/5")
            
            if pages_with_text == 0:
                print("WARNING: No text extracted - PDF might be scanned images")
                print("SOLUTION: Use OCR or convert to text-based PDF")
                return
            
            # Split into lines
            lines = [line.strip() for line in all_text.splitlines() if line.strip()]
            print(f"Total lines extracted: {len(lines)}")
            
            # Show sample lines
            print("\nSample lines:")
            for i, line in enumerate(lines[:10]):
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
                    print("All numbers found:")
                    for i, num in enumerate(numbers[:10]):
                        print(f"  {i+1:2d}. {num:10.2f}")
                    print("PROBLEM: All amounts are less than 1.0")
                    print("SOLUTION: Lower MIN_TRANSACTION_AMOUNT or check file content")
            
        except Exception as e:
            print(f"PDF extraction error: {e}")
        
    except Exception as e:
        print(f"File reading error: {e}")


def check_database():
    """Check database contents"""
    print("\n" + "=" * 50)
    print("CHECKING DATABASE")
    print("=" * 50)
    
    try:
        import sqlite3
        db_path = "reconcile.db"
        
        if not os.path.exists(db_path):
            print("ERROR: Database not found")
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check transaction counts
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_tx = cursor.fetchone()[0]
        print(f"Total transactions: {total_tx}")
        
        cursor.execute("SELECT kind, COUNT(*) FROM transactions GROUP BY kind")
        kinds = cursor.fetchall()
        print("Transaction types:")
        for kind, count in kinds:
            print(f"  {kind}: {count}")
        
        # Check recent transactions
        cursor.execute("""
            SELECT kind, file_name, description, amount, created_at 
            FROM transactions 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        recent = cursor.fetchall()
        print("\nRecent transactions:")
        for tx in recent:
            print(f"  {tx[0]} | {tx[1][:30]} | {tx[2][:30]} | {tx[3]}")
        
        # Check if there are any recent uploads with your file
        cursor.execute("""
            SELECT COUNT(*) FROM transactions 
            WHERE file_name LIKE '%119_ec85e5228efd3a8e021f52b4aabb9313%'
        """)
        your_file_count = cursor.fetchone()[0]
        print(f"\nYour file transactions: {your_file_count}")
        
        if your_file_count == 0:
            print("PROBLEM: No transactions from your file were stored")
            print("POSSIBLE CAUSES:")
            print("1. File processing failed during upload")
            print("2. No transactions were extracted from file")
            print("3. Transactions were filtered out as noise")
            print("4. Database insertion failed")
        
        conn.close()
        
    except Exception as e:
        print(f"Database error: {e}")


def main():
    """Main function"""
    check_pdf_file()
    check_database()
    
    print("\n" + "=" * 50)
    print("DIAGNOSIS COMPLETE")
    print("=" * 50)
    
    print("\nCOMMON SOLUTIONS:")
    print("1. If PDF has no text: Use OCR or convert to text PDF")
    print("2. If amounts < 1.0: Lower MIN_TRANSACTION_AMOUNT in app.py")
    print("3. If no transactions found: Check file format and content")
    print("4. If database empty: Check upload process for errors")


if __name__ == "__main__":
    main()
