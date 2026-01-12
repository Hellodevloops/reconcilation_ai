"""
Debug File Processing Script
Helps diagnose why bank statement and invoice files are not storing data in database
"""

import os
import sys
import json
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from app import (
    pdf_to_lines, pdf_to_pages_lines, parse_transactions_from_lines,
    excel_to_transactions, csv_to_transactions, ocr_image_to_lines,
    detect_currency_from_text, MIN_TRANSACTION_AMOUNT
)


def debug_file_processing(file_path: str, file_type: str = "auto"):
    """
    Debug file processing to see why no data is being extracted
    
    Args:
        file_path: Path to the file to debug
        file_type: "auto", "invoice", or "bank"
    """
    print(f"\n{'='*60}")
    print(f"DEBUGGING FILE: {file_path}")
    print(f"{'='*60}")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    # Read file
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
    
    print(f"📁 File size: {len(file_bytes)} bytes")
    
    # Determine file type
    file_name = os.path.basename(file_path)
    file_ext = os.path.splitext(file_name.lower())[1]
    print(f"📄 File extension: {file_ext}")
    
    # Determine source type
    if file_type == "auto":
        source = "bank" if "bank" in file_name.lower() or "statement" in file_name.lower() else "invoice"
    else:
        source = file_type
    
    print(f"🏷️  Processing as: {source}")
    
    # Step 1: Extract text/lines from file
    print(f"\n🔍 STEP 1: Extracting text/lines...")
    
    lines = []
    try:
        if file_ext == ".pdf":
            lines = pdf_to_lines(file_bytes)
            print(f"✅ PDF extraction successful: {len(lines)} lines")
        elif file_ext in [".xlsx", ".xls"]:
            transactions = excel_to_transactions(file_bytes, source=source)
            print(f"✅ Excel extraction successful: {len(transactions)} transactions")
            for i, tx in enumerate(transactions[:5]):  # Show first 5
                print(f"   {i+1}. {tx.date or 'No date'} | {tx.description[:50]} | {tx.amount}")
            if len(transactions) > 5:
                print(f"   ... and {len(transactions) - 5} more")
            return transactions
        elif file_ext == ".csv":
            transactions = csv_to_transactions(file_bytes, source=source)
            print(f"✅ CSV extraction successful: {len(transactions)} transactions")
            for i, tx in enumerate(transactions[:5]):  # Show first 5
                print(f"   {i+1}. {tx.date or 'No date'} | {tx.description[:50]} | {tx.amount}")
            if len(transactions) > 5:
                print(f"   ... and {len(transactions) - 5} more")
            return transactions
        elif file_ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff"]:
            lines = ocr_image_to_lines(file_bytes)
            print(f"✅ Image OCR successful: {len(lines)} lines")
        else:
            print(f"❌ Unsupported file type: {file_ext}")
            return []
    except Exception as e:
        print(f"❌ Error extracting text: {e}")
        return []
    
    # Show sample lines
    print(f"\n📝 First 10 lines extracted:")
    for i, line in enumerate(lines[:10]):
        print(f"   {i+1:2d}. {line[:100]}")
    if len(lines) > 10:
        print(f"   ... and {len(lines) - 10} more lines")
    
    # Step 2: Detect currency
    print(f"\n💱 STEP 2: Detecting currency...")
    all_text = " ".join(lines)
    detected_currency = detect_currency_from_text(all_text)
    print(f"   Detected currency: {detected_currency or 'None'}")
    
    # Step 3: Find all numbers in text
    print(f"\n🔢 STEP 3: Finding all numbers...")
    import re
    all_numbers = []
    for line in lines:
        nums = re.findall(r"[-+]?\d[\d,]*\.?\d*", line)
        for num in nums:
            try:
                val = float(num.replace(",", ""))
                all_numbers.append((val, line.strip()))
            except ValueError:
                continue
    
    print(f"   Total numbers found: {len(all_numbers)}")
    
    # Filter by minimum amount
    significant_numbers = [(val, line) for val, line in all_numbers if abs(val) >= MIN_TRANSACTION_AMOUNT]
    print(f"   Numbers >= {MIN_TRANSACTION_AMOUNT}: {len(significant_numbers)}")
    
    # Show sample numbers
    print(f"\n💰 Sample significant numbers:")
    for i, (val, line) in enumerate(significant_numbers[:10]):
        print(f"   {i+1:2d}. {val:10.2f} | {line[:80]}")
    if len(significant_numbers) > 10:
        print(f"   ... and {len(significant_numbers) - 10} more")
    
    # Step 4: Parse transactions
    print(f"\n🏦 STEP 4: Parsing transactions...")
    try:
        transactions = parse_transactions_from_lines(lines, source=source)
        print(f"✅ Transaction parsing successful: {len(transactions)} transactions")
        
        if transactions:
            print(f"\n📊 Extracted transactions:")
            for i, tx in enumerate(transactions[:10]):  # Show first 10
                print(f"   {i+1:2d}. Date: {tx.date or 'N/A'} | Amount: {tx.amount:10.2f} | Description: {tx.description[:60]}")
                if tx.vendor_name:
                    print(f"       Vendor: {tx.vendor_name}")
                if tx.invoice_number:
                    print(f"       Invoice #: {tx.invoice_number}")
                if tx.currency:
                    print(f"       Currency: {tx.currency}")
            
            if len(transactions) > 10:
                print(f"   ... and {len(transactions) - 10} more transactions")
        else:
            print(f"❌ No transactions parsed!")
            
            # Debug why no transactions were parsed
            print(f"\n🔍 DEBUGGING: Why no transactions?")
            print(f"   - Total lines: {len(lines)}")
            print(f"   - Numbers found: {len(all_numbers)}")
            print(f"   - Significant numbers: {len(significant_numbers)}")
            print(f"   - MIN_TRANSACTION_AMOUNT: {MIN_TRANSACTION_AMOUNT}")
            
            if len(significant_numbers) == 0:
                print(f"   ⚠️  No numbers >= {MIN_TRANSACTION_AMOUNT} found!")
                print(f"   💡 Consider lowering MIN_TRANSACTION_AMOUNT or check file content")
            else:
                print(f"   ⚠️  Numbers found but no transactions parsed")
                print(f"   💡 Check if lines have proper transaction format (date + description + amount)")
        
        return transactions
        
    except Exception as e:
        print(f"❌ Error parsing transactions: {e}")
        import traceback
        traceback.print_exc()
        return []


def create_test_files():
    """Create simple test files to verify processing works"""
    print(f"\n{'='*60}")
    print(f"CREATING TEST FILES")
    print(f"{'='*60}")
    
    # Create a simple test CSV bank statement
    test_csv_content = """Date,Description,Amount,Balance
2024-01-01,Coffee Shop,5.50,1000.00
2024-01-02,Gas Station,45.00,954.50
2024-01-03,Grocery Store,125.75,828.75
2024-01-04,Restaurant,32.00,796.75
2024-01-05,ATM Withdrawal,200.00,596.75"""
    
    test_csv_path = "test_bank_statement.csv"
    with open(test_csv_path, 'w') as f:
        f.write(test_csv_content)
    
    print(f"✅ Created test CSV: {test_csv_path}")
    
    # Create a simple test invoice text
    test_invoice_content = """Invoice #INV-001
Date: 2024-01-05
Vendor: Test Company
Description: Professional Services
Amount: 500.00
Total Due: 500.00"""
    
    test_invoice_path = "test_invoice.txt"
    with open(test_invoice_path, 'w') as f:
        f.write(test_invoice_content)
    
    print(f"✅ Created test invoice: {test_invoice_path}")
    
    return test_csv_path, test_invoice_path


def main():
    """Main debug function"""
    print("🐛 FILE PROCESSING DEBUG TOOL")
    print("=" * 60)
    
    # Check if test files exist in uploads directory
    uploads_dir = "uploads"
    if os.path.exists(uploads_dir):
        print(f"\n📁 Checking files in uploads directory...")
        
        invoice_dir = os.path.join(uploads_dir, "invoices")
        bank_dir = os.path.join(uploads_dir, "bank_statements")
        
        # Find files to debug
        files_to_debug = []
        
        if os.path.exists(invoice_dir):
            invoice_files = [f for f in os.listdir(invoice_dir) if not f.startswith('.')]
            if invoice_files:
                files_to_debug.append((os.path.join(invoice_dir, invoice_files[0]), "invoice"))
                print(f"   Found invoice file: {invoice_files[0]}")
        
        if os.path.exists(bank_dir):
            bank_files = [f for f in os.listdir(bank_dir) if not f.startswith('.')]
            if bank_files:
                files_to_debug.append((os.path.join(bank_dir, bank_files[0]), "bank"))
                print(f"   Found bank file: {bank_files[0]}")
        
        # Debug found files
        for file_path, file_type in files_to_debug:
            debug_file_processing(file_path, file_type)
    
    else:
        print(f"❌ Uploads directory not found: {uploads_dir}")
        
        # Create test files and debug them
        print(f"\n🔧 Creating test files for debugging...")
        test_csv, test_invoice = create_test_files()
        
        print(f"\n🧪 Testing with created files...")
        debug_file_processing(test_csv, "bank")
        debug_file_processing(test_invoice, "invoice")
        
        # Clean up test files
        try:
            os.remove(test_csv)
            os.remove(test_invoice)
            print(f"\n🧹 Cleaned up test files")
        except:
            pass
    
    print(f"\n{'='*60}")
    print("DEBUG COMPLETE")
    print("=" * 60)
    print("\n💡 TIPS:")
    print("1. If no numbers are found, check if file is image-based (needs OCR)")
    print("2. If numbers are found but no transactions, check transaction format")
    print("3. If amounts are too small, consider lowering MIN_TRANSACTION_AMOUNT")
    print("4. For PDF files, ensure they contain text (not scanned images)")


if __name__ == "__main__":
    main()
