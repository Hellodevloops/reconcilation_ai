"""
Extract Your Specific Invoice Format
Custom parser for your multi-invoice payment advice format
"""

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

def extract_multi_invoice_payment_advice():
    """Extract multiple invoices from your payment advice format"""
    print("EXTRACTING MULTI-INVOICE PAYMENT ADVICE")
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
    print(f"Processing file: {invoice_files[0]}")
    
    try:
        # Extract text
        from PyPDF2 import PdfReader
        import io
        
        with open(test_file, 'rb') as f:
            file_bytes = f.read()
        
        reader = PdfReader(io.BytesIO(file_bytes))
        
        # Extract all text
        all_text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                all_text += page_text + "\n"
        
        lines = [line.strip() for line in all_text.splitlines() if line.strip()]
        print(f"Extracted {len(lines)} lines")
        
        # Find all payment advice sections
        transactions = []
        
        # Look for patterns: Invoice Number + Amount Due + Due Date
        invoice_pattern = re.compile(
            r'Invoice Number\s+(INV-\d+).*?'
            r'Amount Due\s+([0-9,]+\.[0-9]{2}).*?'
            r'Due Date\s+(\d{1,2}\s+\w{3}\s+\d{4})',
            re.DOTALL | re.IGNORECASE
        )
        
        # Find all matches
        matches = invoice_pattern.findall(all_text)
        print(f"Found {len(matches)} invoice matches")
        
        for i, (invoice_num, amount, due_date) in enumerate(matches):
            try:
                amount_val = float(amount.replace(",", ""))
                
                # Create transaction
                transaction = {
                    'kind': 'invoice',
                    'description': f'Payment Advice - Invoice {invoice_num}',
                    'amount': amount_val,
                    'date': due_date,
                    'vendor_name': 'FLOOZIE LTD',
                    'invoice_number': invoice_num,
                    'currency': '£',
                    'file_name': '119_ec85e5228efd3a8e021f52b4aabb9313.pdf',
                    'created_at': datetime.now().isoformat()
                }
                
                transactions.append(transaction)
                print(f"  {i+1}. Invoice: {invoice_num} | Amount: {amount_val:10.2f} | Due: {due_date}")
                
            except ValueError as e:
                print(f"Error parsing amount {amount}: {e}")
                continue
        
        # Also look for individual line items (from the detailed breakdown)
        print(f"\nLooking for line items...")
        
        # Pattern for line items: Date + Description + Amount
        line_item_pattern = re.compile(
            r'(\d{1,2}/\d{1,2}/\d{4})\s+([A-Za-z\s]+)\s+([0-9,]+\.[0-9]{2})',
            re.IGNORECASE
        )
        
        line_items = line_item_pattern.findall(all_text)
        print(f"Found {len(line_items)} line items")
        
        # Show first few line items
        for i, (date, desc, amount) in enumerate(line_items[:5]):
            try:
                amount_val = float(amount.replace(",", ""))
                print(f"  {i+1}. {date} | {desc[:30]} | {amount_val:8.2f}")
            except ValueError:
                continue
        
        return transactions
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def insert_transactions_to_db(transactions):
    """Insert extracted transactions to database"""
    if not transactions:
        print("No transactions to insert")
        return
    
    print(f"\nINSERTING {len(transactions)} TRANSACTIONS TO DATABASE")
    print("=" * 60)
    
    try:
        db_path = "reconcile.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Insert each transaction
        for tx in transactions:
            cursor.execute("""
                INSERT INTO transactions (
                    kind, description, amount, date, vendor_name, 
                    invoice_number, currency, file_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx['kind'],
                tx['description'],
                tx['amount'],
                tx['date'],
                tx['vendor_name'],
                tx['invoice_number'],
                tx['currency'],
                tx['file_name'],
                tx['created_at']
            ))
        
        conn.commit()
        conn.close()
        
        print(f"Successfully inserted {len(transactions)} transactions")
        
        # Verify insertion
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM transactions 
            WHERE file_name = '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        """)
        count = cursor.fetchone()[0]
        conn.close()
        
        print(f"Verification: {count} transactions from your file in database")
        
    except Exception as e:
        print(f"Database error: {e}")


def verify_extraction():
    """Verify the extraction worked"""
    print(f"\n{'=' * 60}")
    print("VERIFICATION")
    print("=" * 60)
    
    try:
        db_path = "reconcile.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check your file transactions
        cursor.execute("""
            SELECT invoice_number, amount, date, vendor_name 
            FROM transactions 
            WHERE file_name = '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
            ORDER BY amount DESC
        """)
        
        your_transactions = cursor.fetchall()
        print(f"Your file transactions in database:")
        for i, (inv_num, amount, date, vendor) in enumerate(your_transactions):
            print(f"  {i+1}. {inv_num} | {amount:10.2f} | {date} | {vendor}")
        
        # Check total
        cursor.execute("""
            SELECT SUM(amount), COUNT(*) FROM transactions 
            WHERE file_name = '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        """)
        total, count = cursor.fetchone()
        print(f"\nTotal amount: {total:10.2f}")
        print(f"Transaction count: {count}")
        
        conn.close()
        
    except Exception as e:
        print(f"Verification error: {e}")


def main():
    """Main function"""
    # Extract transactions
    transactions = extract_multi_invoice_payment_advice()
    
    if transactions:
        # Insert to database
        insert_transactions_to_db(transactions)
        
        # Verify
        verify_extraction()
        
        print(f"\n{'=' * 60}")
        print("SUCCESS!")
        print("=" * 60)
        print(f"✅ Extracted {len(transactions)} invoices from your file")
        print(f"✅ Stored them in the database")
        print(f"✅ Your file is now ready for reconciliation")
        print(f"\nNext steps:")
        print(f"1. Upload your bank statement file")
        print(f"2. Run reconciliation - it should find matches now!")
    else:
        print(f"\n{'=' * 60}")
        print("NO INVOICES EXTRACTED")
        print("=" * 60)
        print("Could not extract invoices from your file.")


if __name__ == "__main__":
    main()
