"""
Database Troubleshooting Script
Check reconciliation data and tables
"""

import os
import sys
import sqlite3
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import DB_PATH

def check_database_state():
    """Check current database state and reconciliation data"""
    print("=" * 60)
    print("DATABASE TROUBLESHOOTING - RECONCILIATION DATA")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # 1. Check all tables
        print("1. CHECKING ALL TABLES IN DATABASE:")
        print("-" * 40)
        cur.execute("""
            SELECT name, type FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        tables = cur.fetchall()
        
        if not tables:
            print("  No tables found in database!")
            return
        
        print(f"  Found {len(tables)} tables:")
        for table_name, table_type in tables:
            print(f"    - {table_name} ({table_type})")
        
        # 2. Check reconciliation-related tables specifically
        print("\n2. CHECKING RECONCILIATION TABLES:")
        print("-" * 40)
        
        reconciliation_tables = [
            'reconciliation_match',
            'financial_reconciliations', 
            'reconciliation_matches',
            'unmatched_items'
        ]
        
        for table_name in reconciliation_tables:
            cur.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table_name,))
            exists = cur.fetchone()[0] > 0
            status = "EXISTS" if exists else "NOT FOUND"
            print(f"    {table_name}: {status}")
            
            if exists:
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cur.fetchone()[0]
                print(f"      Records: {count}")
        
        # 3. Check if reconciliation_match has data
        print("\n3. CHECKING RECONCILIATION_MATCH TABLE:")
        print("-" * 40)
        
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='reconciliation_match'
        """)
        table_exists = cur.fetchone()[0] > 0
        
        if table_exists:
            cur.execute("SELECT COUNT(*) FROM reconciliation_match")
            record_count = cur.fetchone()[0]
            print(f"  reconciliation_match table exists with {record_count} records")
            
            if record_count > 0:
                # Show sample data
                cur.execute("""
                    SELECT reconciliation_id, match_type, created_at 
                    FROM reconciliation_match 
                    LIMIT 5
                """)
                samples = cur.fetchall()
                print("  Sample records:")
                for rec_id, match_type, created_at in samples:
                    print(f"    - {rec_id}: {match_type} (created: {created_at})")
                
                # Show unique reconciliation IDs
                cur.execute("SELECT DISTINCT reconciliation_id FROM reconciliation_match")
                unique_ids = [row[0] for row in cur.fetchall()]
                print(f"  Unique reconciliation IDs: {len(unique_ids)}")
                for rec_id in unique_ids[:5]:  # Show first 5
                    print(f"    - {rec_id}")
            else:
                print("  reconciliation_match table exists but is EMPTY")
                print("  This means no reconciliation has been processed yet")
        else:
            print("  reconciliation_match table does NOT exist")
            print("  Need to run the simplified reconciliation migration")
        
        # 4. Check document_uploads table
        print("\n4. CHECKING DOCUMENT UPLOADS:")
        print("-" * 40)
        
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='document_uploads'
        """)
        doc_table_exists = cur.fetchone()[0] > 0
        
        if doc_table_exists:
            cur.execute("SELECT COUNT(*) FROM document_uploads")
            doc_count = cur.fetchone()[0]
            print(f"  document_uploads table exists with {doc_count} records")
            
            if doc_count > 0:
                cur.execute("""
                    SELECT id, file_name, document_type, processing_status 
                    FROM document_uploads 
                    LIMIT 5
                """)
                samples = cur.fetchall()
                print("  Sample uploads:")
                for doc_id, file_name, doc_type, status in samples:
                    print(f"    - ID {doc_id}: {file_name} ({doc_type}) - {status}")
        else:
            print("  document_uploads table does NOT exist")
        
        # 5. Check extracted_invoices and bank_transactions
        print("\n5. CHECKING EXTRACTED DATA:")
        print("-" * 40)
        
        # Check invoices
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='extracted_invoices'
        """)
        inv_table_exists = cur.fetchone()[0] > 0
        
        if inv_table_exists:
            cur.execute("SELECT COUNT(*) FROM extracted_invoices")
            inv_count = cur.fetchone()[0]
            print(f"  extracted_invoices: {inv_count} records")
        else:
            print("  extracted_invoices: Table not found")
        
        # Check bank transactions
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='bank_transactions'
        """)
        trans_table_exists = cur.fetchone()[0] > 0
        
        if trans_table_exists:
            cur.execute("SELECT COUNT(*) FROM bank_transactions")
            trans_count = cur.fetchone()[0]
            print(f"  bank_transactions: {trans_count} records")
        else:
            print("  bank_transactions: Table not found")
        
        conn.close()
        
        # 6. Provide recommendations
        print("\n6. RECOMMENDATIONS:")
        print("-" * 40)
        
        if not table_exists:
            print("  ACTION NEEDED: Run simplified reconciliation migration")
            print("  Command: python migrations/simplified_reconciliation_migration.py")
        
        elif record_count == 0:
            if doc_count > 0:
                print("  ACTION NEEDED: Create and process a reconciliation")
                print("  Steps:")
                print("    1. Use API to create reconciliation")
                print("    2. Process reconciliation to populate table")
                print("  API Endpoint: POST /api/reconciliation/create")
                print("  API Endpoint: POST /api/reconciliation/process/<reconciliation_id>")
            else:
                print("  ACTION NEEDED: Upload documents first")
                print("  Steps:")
                print("    1. Upload invoice documents")
                print("    2. Upload bank statement documents")
                print("    3. Then create reconciliation")
        else:
            print("  reconciliation_match table has data")
            print("  Check your SQL query - ensure you're querying the right table")
            print("  Example query:")
            print("    SELECT * FROM reconciliation_match")
        
        return True
        
    except Exception as e:
        print(f"Error checking database: {e}")
        import traceback
        traceback.print_exc()
        return False

def provide_sql_examples():
    """Provide SQL examples for querying reconciliation data"""
    print("\n" + "=" * 60)
    print("SQL EXAMPLES FOR RECONCILIATION DATA")
    print("=" * 60)
    
    print("1. CHECK IF TABLE EXISTS:")
    print("-" * 30)
    print("""
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name='reconciliation_match';
    """)
    
    print("\n2. GET ALL RECONCILIATION DATA:")
    print("-" * 30)
    print("""
    SELECT * FROM reconciliation_match;
    """)
    
    print("\n3. GET RECONCILIATION SUMMARY:")
    print("-" * 30)
    print("""
    SELECT 
        reconciliation_id,
        match_type,
        COUNT(*) as count,
        SUM(invoice_amount) as total_invoice_amount
    FROM reconciliation_match 
    GROUP BY reconciliation_id, match_type;
    """)
    
    print("\n4. GET SPECIFIC RECONCILIATION:")
    print("-" * 30)
    print("""
    SELECT * FROM reconciliation_match 
    WHERE reconciliation_id = 'REC-2024-001';
    """)
    
    print("\n5. GET ONLY MATCHED RECORDS:")
    print("-" * 30)
    print("""
    SELECT * FROM reconciliation_match 
    WHERE match_type IN ('exact', 'partial');
    """)

def main():
    """Main troubleshooting function"""
    print("RECONCILIATION DATA TROUBLESHOOTING TOOL")
    print("=" * 60)
    
    # Check database state
    if check_database_state():
        # Provide SQL examples
        provide_sql_examples()
        
        print("\n" + "=" * 60)
        print("TROUBLESHOOTING COMPLETE")
        print("=" * 60)
        print("Follow the recommendations above to resolve your reconciliation data issue.")
    
    return True

if __name__ == "__main__":
    main()
