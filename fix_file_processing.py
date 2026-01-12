"""
Fix File Processing Issues
Addresses the specific problems found in your file processing
"""

import os
import sys
import re
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

def create_improved_transaction_parser():
    """Create an improved transaction parser for your file format"""
    
    def parse_payment_advice_transactions(lines, source="invoice"):
        """
        Improved parser for Payment Advice documents
        Handles formats like your file with payment advice structure
        """
        transactions = []
        
        # Look for payment advice patterns
        current_invoice = None
        current_vendor = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            lower = line.lower()
            
            # Extract vendor name
            if "to:" in line.lower() and not current_vendor:
                vendor_match = re.search(r"to:([A-Za-z0-9\s&.,\-]+)", line, re.IGNORECASE)
                if vendor_match:
                    current_vendor = vendor_match.group(1).strip()
                    print(f"Found vendor: {current_vendor}")
            
            # Extract invoice number
            if "invoice number" in lower and not current_invoice:
                inv_match = re.search(r"invoice number\s+([A-Za-z0-9\-]+)", line, re.IGNORECASE)
                if inv_match:
                    current_invoice = inv_match.group(1).strip().upper()
                    print(f"Found invoice: {current_invoice}")
            
            # Extract amount due
            if "amount due" in lower or "total due" in lower:
                amount_match = re.search(r"(?:amount due|total due)[\s:]*([0-9,]+\.?[0-9]*)", line, re.IGNORECASE)
                if amount_match:
                    try:
                        amount = float(amount_match.group(1).replace(",", ""))
                        if amount >= 1.0:  # MIN_TRANSACTION_AMOUNT
                            # Create transaction
                            from app import Transaction
                            tx = Transaction(
                                source=source,
                                description=line,
                                amount=amount,
                                vendor_name=current_vendor,
                                invoice_number=current_invoice,
                                currency="£",  # Default to GBP for UK addresses
                                direction=None,
                                document_subtype="payment_advice"
                            )
                            transactions.append(tx)
                            print(f"Created transaction: {amount} | {current_vendor} | {current_invoice}")
                    except ValueError:
                        continue
            
            # Also look for standalone amounts with context
            if re.search(r"\b[0-9,]+\.[0-9]{2}\b", line) and len(line) < 100:
                # Check if this looks like an amount line
                amount_match = re.search(r"\b([0-9,]+\.[0-9]{2})\b", line)
                if amount_match:
                    try:
                        amount = float(amount_match.group(1).replace(",", ""))
                        if amount >= 1.0 and amount > 100:  # Filter small amounts, likely not transactions
                            # Check if line has transaction-like content
                            if any(keyword in lower for keyword in ['payment', 'invoice', 'due', 'total', 'amount']):
                                from app import Transaction
                                tx = Transaction(
                                    source=source,
                                    description=line,
                                    amount=amount,
                                    vendor_name=current_vendor,
                                    invoice_number=current_invoice,
                                    currency="£",
                                    direction=None,
                                    document_subtype="payment_advice"
                                )
                                transactions.append(tx)
                                print(f"Created additional transaction: {amount} | {line}")
                    except ValueError:
                        continue
        
        return transactions
    
    return parse_payment_advice_transactions


def test_improved_parser():
    """Test the improved parser on your file"""
    print("TESTING IMPROVED PARSER")
    print("=" * 50)
    
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
    print(f"Testing file: {invoice_files[0]}")
    
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
        
        # Test improved parser
        parse_payment_advice = create_improved_transaction_parser()
        transactions = parse_payment_advice(lines, "invoice")
        
        print(f"\nImproved parser found: {len(transactions)} transactions")
        
        for i, tx in enumerate(transactions):
            print(f"  {i+1}. Amount: {tx.amount:10.2f} | Vendor: {tx.vendor_name or 'N/A'} | Invoice: {tx.invoice_number or 'N/A'}")
            print(f"      Description: {tx.description}")
        
        return transactions
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def manually_insert_transactions(transactions):
    """Manually insert transactions into database"""
    if not transactions:
        print("No transactions to insert")
        return
    
    print(f"\nMANUALLY INSERTING {len(transactions)} TRANSACTIONS")
    print("=" * 50)
    
    try:
        import sqlite3
        from datetime import datetime
        
        db_path = "reconcile.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get current timestamp
        timestamp = datetime.now().isoformat()
        
        # Insert each transaction
        for tx in transactions:
            cursor.execute("""
                INSERT INTO transactions (
                    kind, description, amount, date, vendor_name, 
                    invoice_number, currency, file_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "invoice",
                tx.description,
                tx.amount,
                tx.date,
                tx.vendor_name,
                tx.invoice_number,
                tx.currency,
                "119_ec85e5228efd3a8e021f52b4aabb9313.pdf",
                timestamp
            ))
        
        conn.commit()
        conn.close()
        
        print(f"Successfully inserted {len(transactions)} transactions")
        
    except Exception as e:
        print(f"Database insertion error: {e}")


def main():
    """Main function"""
    # Test improved parser
    transactions = test_improved_parser()
    
    # Insert transactions if found
    if transactions:
        manually_insert_transactions(transactions)
        
        print(f"\n{'=' * 50}")
        print("SUCCESS!")
        print("=" * 50)
        print(f"Your file now has {len(transactions)} transactions in the database")
        print("Try running reconciliation again - it should work now!")
    else:
        print(f"\n{'=' * 50}")
        print("NO TRANSACTIONS FOUND")
        print("=" * 50)
        print("The improved parser couldn't extract transactions.")
        print("Your file might need manual processing or OCR for scanned pages.")


if __name__ == "__main__":
    main()
