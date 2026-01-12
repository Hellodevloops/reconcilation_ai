"""
Create training data based on real invoice and bank statement formats.
This script generates realistic test data based on the provided examples:
- Invoice format: Booker Wholesale with Invoice No, Date, Invoice Total
- Bank statement format: Tide with vendor names, dates, amounts

Usage:
    python create_training_data.py
"""

import sqlite3
import random
from datetime import datetime, timedelta
from app import DB_PATH, init_db

def create_sample_data():
    """Create sample invoice and bank transaction data for training."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Clear existing data (optional - comment out if you want to keep existing data)
    # cur.execute("DELETE FROM transactions")
    # cur.execute("DELETE FROM reconciliations")
    # cur.execute("DELETE FROM reconciliation_matches")
    
    # Sample vendors based on examples
    vendors = [
        "Booker Wholesale",
        "Carlsberg Marstons Brewing Company",
        "ABC Pvt Ltd",
        "Kale & Damson Ltd",
        "P.W.Amps Ltd",
        "Well Hung Biltong Company",
    ]
    
    # Generate 50 invoice-bank pairs for training
    matches_created = 0
    
    for i in range(50):
        # Generate invoice data
        vendor = random.choice(vendors)
        invoice_num = f"{random.randint(100000, 999999)}"
        base_date = datetime(2024, 1, 1) + timedelta(days=random.randint(0, 365))
        invoice_date = base_date.strftime("%d/%m/%Y")
        
        # Generate amount (realistic invoice amounts)
        amount = round(random.uniform(100, 5000), 2)
        
        # Create invoice transaction
        invoice_desc = f"Invoice No: {invoice_num}\nDate: {invoice_date}\nClient: {vendor}\nInvoice Total: £{amount:.2f}"
        
        cur.execute("""
            INSERT INTO transactions (kind, file_name, description, amount, date)
            VALUES (?, ?, ?, ?, ?)
        """, ("invoice", f"invoice_{i+1}.pdf", invoice_desc, amount, invoice_date))
        invoice_id = cur.lastrowid
        
        # Create corresponding bank transaction
        # Bank description format: "VENDOR NAME / ref: KA POLEBROOK" or "Payment received from VENDOR"
        bank_desc_variants = [
            f"{vendor.upper()} / ref: KA POLEBROOK",
            f"Payment received from {vendor}",
            f"{vendor.upper()} / ref: INV-{invoice_num}",
            f"Domestic Transfer, {vendor.upper()} / ref: Reference",
        ]
        bank_desc = random.choice(bank_desc_variants)
        
        # Bank date might be 0-3 days after invoice date
        bank_date_delta = random.randint(0, 3)
        bank_date_obj = base_date + timedelta(days=bank_date_delta)
        bank_date = bank_date_obj.strftime("%d %b %Y")  # Tide format: "29 Feb 2024"
        
        cur.execute("""
            INSERT INTO transactions (kind, file_name, description, amount, date)
            VALUES (?, ?, ?, ?, ?)
        """, ("bank", "bank_statement.pdf", bank_desc, amount, bank_date))
        bank_id = cur.lastrowid
        
        # Create reconciliation match
        cur.execute("""
            INSERT INTO reconciliations (
                invoice_file, bank_file, total_invoice_rows, total_bank_rows,
                match_count, only_in_invoices_count, only_in_bank_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (f"invoice_{i+1}.pdf", "bank_statement.pdf", 1, 1, 1, 0, 0))
        recon_id = cur.lastrowid
        
        cur.execute("""
            INSERT INTO reconciliation_matches (
                reconciliation_id, invoice_description, invoice_amount, invoice_date,
                bank_description, bank_amount, bank_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (recon_id, invoice_desc, amount, invoice_date, bank_desc, amount, bank_date))
        
        matches_created += 1
    
    # Add some unmatched invoices (no corresponding bank transaction)
    for i in range(10):
        vendor = random.choice(vendors)
        invoice_num = f"{random.randint(100000, 999999)}"
        base_date = datetime(2024, 1, 1) + timedelta(days=random.randint(0, 365))
        invoice_date = base_date.strftime("%d/%m/%Y")
        amount = round(random.uniform(100, 5000), 2)
        invoice_desc = f"Invoice No: {invoice_num}\nDate: {invoice_date}\nClient: {vendor}\nInvoice Total: £{amount:.2f}"
        
        cur.execute("""
            INSERT INTO transactions (kind, file_name, description, amount, date)
            VALUES (?, ?, ?, ?, ?)
        """, ("invoice", f"unmatched_invoice_{i+1}.pdf", invoice_desc, amount, invoice_date))
    
    # Add some unmatched bank transactions (no corresponding invoice)
    for i in range(10):
        vendor = random.choice(vendors)
        base_date = datetime(2024, 1, 1) + timedelta(days=random.randint(0, 365))
        bank_date = base_date.strftime("%d %b %Y")
        amount = round(random.uniform(100, 5000), 2)
        bank_desc = f"{vendor.upper()} / ref: UNMATCHED-{i+1}"
        
        cur.execute("""
            INSERT INTO transactions (kind, file_name, description, amount, date)
            VALUES (?, ?, ?, ?, ?)
        """, ("bank", "bank_statement.pdf", bank_desc, amount, bank_date))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Created {matches_created} matched pairs")
    print(f"✓ Created 10 unmatched invoices")
    print(f"✓ Created 10 unmatched bank transactions")
    print(f"\nTotal training data ready!")
    print(f"Now run: python retrain_model.py")

if __name__ == "__main__":
    print("="*60)
    print("Creating Training Data from Real Examples")
    print("="*60)
    print("\nThis will create sample data based on:")
    print("- Invoice format: Invoice No, Date (DD/MM/YYYY), Vendor, Amount")
    print("- Bank statement format: Vendor name / ref:, Date (DD MMM YYYY), Amount")
    print("\n" + "="*60 + "\n")
    
    create_sample_data()

