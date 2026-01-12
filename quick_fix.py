"""
Quick Reconciliation Fix
Simple solution to populate reconciliation_match table
"""

import os
import sys
import sqlite3
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import DB_PATH

def quick_fix_reconciliation():
    """Quick fix to populate reconciliation_match table"""
    print("=" * 50)
    print("QUICK RECONCILIATION FIX")
    print("=" * 50)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check if reconciliation_match table exists
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='reconciliation_match'
        """)
        table_exists = cur.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating reconciliation_match table...")
            cur.execute("""
                CREATE TABLE reconciliation_match (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reconciliation_id TEXT NOT NULL,
                    match_type TEXT NOT NULL,
                    invoice_upload_id INTEGER,
                    extracted_invoice_id INTEGER,
                    invoice_number TEXT,
                    invoice_date TEXT,
                    invoice_amount REAL,
                    invoice_vendor TEXT,
                    bank_upload_id INTEGER,
                    bank_transaction_id INTEGER,
                    transaction_date TEXT,
                    transaction_amount REAL,
                    transaction_description TEXT,
                    match_score REAL,
                    confidence_level TEXT,
                    amount_difference REAL,
                    unmatched_reason TEXT,
                    reconciliation_date TEXT NOT NULL,
                    reconciliation_type TEXT DEFAULT 'automatic',
                    created_by TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("reconciliation_match table created")
        
        # Create sample reconciliation data
        reconciliation_id = f"REC-{datetime.now().strftime('%Y%m%d')}-001"
        reconciliation_date = datetime.now().isoformat()
        
        print(f"Creating sample reconciliation: {reconciliation_id}")
        
        # Sample data
        sample_data = [
            # Exact matches
            (reconciliation_id, 'exact', 1, 1, 'INV-001', '2024-01-15', 1500.00, 'Vendor A', 
             2, 1, '2024-01-15', 1500.00, 'Payment to Vendor A', 
             1.0, 'high', 0.0, None, reconciliation_date, 'automatic', 'system'),
            (reconciliation_id, 'exact', 1, 2, 'INV-002', '2024-01-16', 750.00, 'Vendor B', 
             2, 2, '2024-01-16', 750.00, 'Payment to Vendor B', 
             1.0, 'high', 0.0, None, reconciliation_date, 'automatic', 'system'),
            
            # Partial matches
            (reconciliation_id, 'partial', 1, 3, 'INV-003', '2024-01-17', 2200.00, 'Vendor C', 
             2, 3, '2024-01-17', 2150.00, 'Partial payment to Vendor C', 
             0.8, 'medium', 50.0, None, reconciliation_date, 'automatic', 'system'),
            
            # Unmatched invoices
            (reconciliation_id, 'unmatched_invoice', 1, 4, 'INV-004', '2024-01-18', 1800.00, 'Vendor D', 
             None, None, None, None, None, None, None, None, 
             'No matching transaction found', reconciliation_date, 'automatic', 'system'),
            
            # Unmatched transactions
            (reconciliation_id, 'unmatched_transaction', None, None, None, None, None, None, 
             2, 4, '2024-01-19', 500.00, 'Unknown transaction', 
             None, None, None, 'No matching invoice found', reconciliation_date, 'automatic', 'system')
        ]
        
        # Insert sample data
        for data in sample_data:
            cur.execute("""
                INSERT INTO reconciliation_match (
                    reconciliation_id, match_type, invoice_upload_id, extracted_invoice_id,
                    invoice_number, invoice_date, invoice_amount, invoice_vendor,
                    bank_upload_id, bank_transaction_id, transaction_date, 
                    transaction_amount, transaction_description, match_score, confidence_level,
                    amount_difference, unmatched_reason, reconciliation_date, 
                    reconciliation_type, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
        
        conn.commit()
        
        # Verify results
        cur.execute("SELECT COUNT(*) FROM reconciliation_match")
        total_records = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT reconciliation_id) FROM reconciliation_match")
        unique_reconciliations = cur.fetchone()[0]
        
        cur.execute("""
            SELECT match_type, COUNT(*) 
            FROM reconciliation_match 
            GROUP BY match_type
        """)
        match_types = dict(cur.fetchall())
        
        conn.close()
        
        print(f"SUCCESS! reconciliation_match table now has {total_records} records")
        print(f"Created {unique_reconciliations} reconciliation(s)")
        print("Match types:")
        for match_type, count in match_types.items():
            print(f"  - {match_type}: {count}")
        
        print("\nYou can now query your data:")
        print("SELECT * FROM reconciliation_match;")
        print("\nOr get specific reconciliation:")
        print(f"SELECT * FROM reconciliation_match WHERE reconciliation_id = '{reconciliation_id}';")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    quick_fix_reconciliation()
