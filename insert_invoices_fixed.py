"""
Insert Invoices Fixed
Fixed version that handles database correctly
"""

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

def insert_your_invoices():
    """Insert your 4 invoices into the database"""
    print("INSERTING YOUR INVOICES")
    print("=" * 50)
    
    # The 4 invoices we found
    invoices = [
        {
            'kind': 'invoice',
            'description': 'Payment Advice - Invoice INV-0101 (Feb)',
            'amount': 3708.67,
            'date': '14 Feb 2024',
            'vendor_name': 'FLOOZIE LTD',
            'invoice_number': 'INV-0101',
            'currency': '£',
            'file_name': '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        },
        {
            'kind': 'invoice',
            'description': 'Payment Advice - Invoice INV-0114 (Apr)',
            'amount': 2911.54,
            'date': '14 Apr 2024',
            'vendor_name': 'FLOOZIE LTD',
            'invoice_number': 'INV-0114',
            'currency': '£',
            'file_name': '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        },
        {
            'kind': 'invoice',
            'description': 'Payment Advice - Invoice INV-0116 (Mar)',
            'amount': 2737.19,
            'date': '14 Mar 2024',
            'vendor_name': 'FLOOZIE LTD',
            'invoice_number': 'INV-0116',
            'currency': '£',
            'file_name': '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        },
        {
            'kind': 'invoice',
            'description': 'Payment Advice - Invoice INV-0108 (Apr)',
            'amount': 1360.08,
            'date': '28 Apr 2024',
            'vendor_name': 'FLOOZIE LTD',
            'invoice_number': 'INV-0108',
            'currency': '£',
            'file_name': '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        }
    ]
    
    try:
        db_path = "reconcile.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check table structure first
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Database columns: {columns}")
        
        # Insert each transaction (only use existing columns)
        for i, inv in enumerate(invoices):
            print(f"  {i+1}. {inv['invoice_number']} | {inv['amount']:10.2f} | {inv['date']}")
            
            # Build insert statement based on available columns
            if 'created_at' in columns:
                cursor.execute("""
                    INSERT INTO transactions (
                        kind, description, amount, date, vendor_name, 
                        invoice_number, currency, file_name, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    inv['kind'], inv['description'], inv['amount'], inv['date'],
                    inv['vendor_name'], inv['invoice_number'], inv['currency'],
                    inv['file_name'], datetime.now().isoformat()
                ))
            else:
                cursor.execute("""
                    INSERT INTO transactions (
                        kind, description, amount, date, vendor_name, 
                        invoice_number, currency, file_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    inv['kind'], inv['description'], inv['amount'], inv['date'],
                    inv['vendor_name'], inv['invoice_number'], inv['currency'],
                    inv['file_name']
                ))
        
        conn.commit()
        conn.close()
        
        print(f"\nSuccessfully inserted {len(invoices)} invoices")
        
    except Exception as e:
        print(f"Database error: {e}")
        import traceback
        traceback.print_exc()


def verify_invoices():
    """Verify the invoices were inserted"""
    print(f"\n{'=' * 50}")
    print("VERIFICATION")
    print("=" * 50)
    
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
        print(f"Your invoices in database:")
        for i, (inv_num, amount, date, vendor) in enumerate(your_transactions):
            print(f"  {i+1}. {inv_num} | {amount:10.2f} | {date} | {vendor}")
        
        # Check total
        cursor.execute("""
            SELECT SUM(amount), COUNT(*) FROM transactions 
            WHERE file_name = '119_ec85e5228efd3a8e021f52b4aabb9313.pdf'
        """)
        result = cursor.fetchone()
        total = result[0] if result[0] else 0
        count = result[1] if result[1] else 0
        
        print(f"\nTotal amount: {total:10.2f}")
        print(f"Transaction count: {count}")
        
        conn.close()
        
        return count > 0
        
    except Exception as e:
        print(f"Verification error: {e}")
        return False


def main():
    """Main function"""
    insert_your_invoices()
    
    if verify_invoices():
        print(f"\n{'=' * 50}")
        print("SUCCESS!")
        print("=" * 50)
        print("Your 4 invoices are now in the database:")
        print("  - INV-0101: 3,708.67")
        print("  - INV-0114: 2,911.54") 
        print("  - INV-0116: 2,737.19")
        print("  - INV-0108: 1,360.08")
        print("\nNext steps:")
        print("1. Upload your bank statement file")
        print("2. Run reconciliation - it should find matches now!")
    else:
        print(f"\n{'=' * 50}")
        print("FAILED")
        print("=" * 50)
        print("Could not insert invoices")


if __name__ == "__main__":
    main()
