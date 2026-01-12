"""
Simple Debug Script for File Processing
Helps identify why bank statement and invoice files are not storing data
"""

import os
import sys
import re
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

def debug_text_extraction():
    """Debug text extraction from files"""
    print("DEBUG: File Processing Issues")
    print("=" * 50)
    
    # Check uploads directory
    uploads_dir = "uploads"
    if not os.path.exists(uploads_dir):
        print("ERROR: Uploads directory not found")
        return
    
    print(f"Uploads directory found: {uploads_dir}")
    
    # Check subdirectories
    invoice_dir = os.path.join(uploads_dir, "invoices")
    bank_dir = os.path.join(uploads_dir, "bank_statements")
    
    # Find files
    files_found = []
    
    if os.path.exists(invoice_dir):
        invoice_files = [f for f in os.listdir(invoice_dir) if not f.startswith('.')]
        if invoice_files:
            files_found.append(("invoice", os.path.join(invoice_dir, invoice_files[0])))
            print(f"Found invoice file: {invoice_files[0]}")
    
    if os.path.exists(bank_dir):
        bank_files = [f for f in os.listdir(bank_dir) if not f.startswith('.')]
        if bank_files:
            files_found.append(("bank", os.path.join(bank_dir, bank_files[0])))
            print(f"Found bank file: {bank_files[0]}")
    
    if not files_found:
        print("No files found in uploads directory")
        return
    
    # Debug each file
    for file_type, file_path in files_found:
        print(f"\n{'-' * 50}")
        print(f"DEBUGGING {file_type.upper()} FILE: {os.path.basename(file_path)}")
        print(f"{'-' * 50}")
        
        try:
            # Read file
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            print(f"File size: {len(file_bytes)} bytes")
            
            # Try to extract text
            if file_path.lower().endswith('.pdf'):
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(file_bytes)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    print(f"PDF text extraction: {len(lines)} lines")
                    
                    # Show first few lines
                    print("First 5 lines:")
                    for i, line in enumerate(lines[:5]):
                        print(f"  {i+1}. {line[:80]}")
                    
                    # Find numbers
                    numbers = find_numbers_in_lines(lines)
                    print(f"Numbers found: {len(numbers)}")
                    
                    # Show significant numbers
                    significant = [n for n in numbers if abs(n) >= 1.0]
                    print(f"Significant numbers (>=1.0): {len(significant)}")
                    
                    if significant:
                        print("Sample significant numbers:")
                        for i, num in enumerate(significant[:5]):
                            print(f"  {i+1}. {num}")
                    
                except Exception as e:
                    print(f"PDF extraction error: {e}")
            
            elif file_path.lower().endswith(('.xlsx', '.xls')):
                try:
                    import pandas as pd
                    df = pd.read_excel(file_bytes)
                    print(f"Excel extraction: {len(df)} rows")
                    print("Columns:", list(df.columns))
                    print("First 3 rows:")
                    print(df.head(3).to_string())
                    
                    # Find numeric columns
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    print(f"Numeric columns: {list(numeric_cols)}")
                    
                except Exception as e:
                    print(f"Excel extraction error: {e}")
            
            elif file_path.lower().endswith('.csv'):
                try:
                    import pandas as pd
                    df = pd.read_csv(file_bytes.decode('utf-8'))
                    print(f"CSV extraction: {len(df)} rows")
                    print("Columns:", list(df.columns))
                    print("First 3 rows:")
                    print(df.head(3).to_string())
                    
                    # Find numeric columns
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    print(f"Numeric columns: {list(numeric_cols)}")
                    
                except Exception as e:
                    print(f"CSV extraction error: {e}")
            
            else:
                print(f"Unsupported file type: {os.path.splitext(file_path)[1]}")
        
        except Exception as e:
            print(f"Error processing file: {e}")


def find_numbers_in_lines(lines):
    """Find all numeric values in text lines"""
    numbers = []
    for line in lines:
        # Find numbers with optional commas and decimals
        matches = re.findall(r"[-+]?\d[\d,]*\.?\d*", line)
        for match in matches:
            try:
                # Remove commas and convert to float
                num = float(match.replace(",", ""))
                numbers.append(num)
            except ValueError:
                continue
    return numbers


def check_database_storage():
    """Check what's actually stored in the database"""
    print(f"\n{'=' * 50}")
    print("CHECKING DATABASE STORAGE")
    print("=" * 50)
    
    try:
        import sqlite3
        db_path = "reconcile.db"
        
        if not os.path.exists(db_path):
            print("Database file not found")
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables found: {tables}")
        
        # Check transaction table
        if 'transactions' in tables:
            cursor.execute("SELECT COUNT(*) FROM transactions")
            tx_count = cursor.fetchone()[0]
            print(f"Total transactions in database: {tx_count}")
            
            if tx_count > 0:
                cursor.execute("SELECT kind, COUNT(*) FROM transactions GROUP BY kind")
                kinds = cursor.fetchall()
                print("Transaction types:")
                for kind, count in kinds:
                    print(f"  {kind}: {count}")
                
                # Show recent transactions
                cursor.execute("SELECT kind, description, amount, file_name FROM transactions ORDER BY id DESC LIMIT 5")
                recent = cursor.fetchall()
                print("\nRecent transactions:")
                for tx in recent:
                    print(f"  {tx[0]} | {tx[1][:40]} | {tx[2]} | {tx[3]}")
        
        # Check production tables
        prod_tables = [t for t in tables if t.startswith('production_')]
        if prod_tables:
            print(f"\nProduction tables: {prod_tables}")
            for table in prod_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} records")
        
        conn.close()
        
    except Exception as e:
        print(f"Database check error: {e}")


def main():
    """Main debug function"""
    print("SIMPLE DEBUG TOOL")
    print("=" * 50)
    
    # Debug file processing
    debug_text_extraction()
    
    # Check database
    check_database_storage()
    
    print(f"\n{'=' * 50}")
    print("DEBUG COMPLETE")
    print("=" * 50)
    print("\nCOMMON ISSUES:")
    print("1. PDF files are scanned images (no text to extract)")
    print("2. Transaction amounts are less than 1.0 (filtered as noise)")
    print("3. File format doesn't match expected patterns")
    print("4. OCR failed on image files")
    print("5. Excel/CSV columns don't match expected names")


if __name__ == "__main__":
    main()
