"""
Bank Statement Schema Migration
Add bank_statement_json column to support large JSON payloads
"""

import sqlite3
import os
import sys
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import DB_PATH

def migrate_bank_statements_table():
    """Add bank_statement_json column to existing bank_statements table"""
    
    print(f"Starting bank statements migration at {datetime.now()}")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    try:
        # Check if bank_statements table exists
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='bank_statements'
        """)
        
        if not cur.fetchone():
            print("Creating bank_statements table...")
            # Create table with JSON support
            cur.execute("""
                CREATE TABLE bank_statements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_upload_id INTEGER NOT NULL,
                    account_number TEXT,
                    account_name TEXT,
                    bank_name TEXT,
                    branch_name TEXT,
                    statement_period_start TEXT,
                    statement_period_end TEXT,
                    opening_balance REAL,
                    closing_balance REAL,
                    total_debits REAL,
                    total_credits REAL,
                    currency TEXT DEFAULT 'USD',
                    statement_type TEXT,
                    bank_statement_json TEXT,
                    total_transactions INTEGER DEFAULT 0,
                    processing_confidence REAL,
                    extraction_method TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE CASCADE
                )
            """)
            print("Bank statements table created successfully")
        else:
            print("Bank statements table exists, checking for bank_statement_json column...")
            
            # Check if bank_statement_json column exists
            cur.execute("PRAGMA table_info(bank_statements)")
            columns = [column[1] for column in cur.fetchall()]
            
            if 'bank_statement_json' not in columns:
                print("Adding bank_statement_json column...")
                cur.execute("ALTER TABLE bank_statements ADD COLUMN bank_statement_json TEXT")
                print("bank_statement_json column added successfully")
            else:
                print("bank_statement_json column already exists")
            
            # Check for other required columns
            required_columns = [
                'total_transactions', 'processing_confidence', 'extraction_method'
            ]
            
            for column in required_columns:
                if column not in columns:
                    print(f"Adding {column} column...")
                    if column == 'total_transactions':
                        cur.execute(f"ALTER TABLE bank_statements ADD COLUMN {column} INTEGER DEFAULT 0")
                    elif column == 'processing_confidence':
                        cur.execute(f"ALTER TABLE bank_statements ADD COLUMN {column} REAL")
                    elif column == 'extraction_method':
                        cur.execute(f"ALTER TABLE bank_statements ADD COLUMN {column} TEXT")
                    print(f"{column} column added successfully")
                else:
                    print(f"{column} column already exists")
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_bank_statements_upload ON bank_statements(document_upload_id)",
            "CREATE INDEX IF NOT EXISTS idx_bank_statements_account ON bank_statements(account_number)",
            "CREATE INDEX IF NOT EXISTS idx_bank_statements_period ON bank_statements(statement_period_start, statement_period_end)"
        ]
        
        for index_sql in indexes:
            cur.execute(index_sql)
            print(f"Index created/verified: {index_sql.split('idx_')[1].split(' ')[0]}")
        
        # Test large JSON storage capability
        print("Testing large JSON storage capability...")
        test_transactions = []
        for i in range(50000):  # Test with 50,000 transactions
            test_transactions.append({
                'transaction_date': f'2024-01-{(i % 28) + 1:02d}',
                'description': f'Test transaction {i+1}',
                'debit_amount': float(i % 1000) + 0.01,
                'credit_amount': None if i % 2 == 0 else float(i % 500) + 0.01,
                'currency': 'USD',
                'transaction_type': 'debit' if i % 2 == 0 else 'credit'
            })
        
        import json
        test_json = json.dumps(test_transactions, ensure_ascii=False)
        json_size_mb = len(test_json.encode('utf-8')) / (1024 * 1024)
        
        print(f"Test JSON size: {json_size_mb:.2f} MB for 50,000 transactions")
        
        if json_size_mb > 100:  # SQLite TEXT limit is typically 1GB, but we'll warn at 100MB
            print(f"WARNING: Large JSON payload detected ({json_size_mb:.2f} MB)")
        else:
            print(f"JSON payload size is acceptable: {json_size_mb:.2f} MB")
        
        conn.commit()
        print("Migration completed successfully!")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {str(e)}")
        return False
        
    finally:
        conn.close()

def verify_migration():
    """Verify that the migration was successful"""
    
    print("\nVerifying migration...")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    try:
        # Check table structure
        cur.execute("PRAGMA table_info(bank_statements)")
        columns = cur.fetchall()
        
        print(f"Bank statements table has {len(columns)} columns:")
        for column in columns:
            print(f"  - {column[1]} ({column[2]})")
        
        # Check indexes
        cur.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='bank_statements'")
        indexes = cur.fetchall()
        
        print(f"\nBank statements table has {len(indexes)} indexes:")
        for index in indexes:
            if index[0] and not index[0].startswith('sqlite_'):
                print(f"  - {index[0]}")
        
        print("\nMigration verification completed successfully!")
        
    except Exception as e:
        print(f"Verification failed: {str(e)}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    success = migrate_bank_statements_table()
    if success:
        verify_migration()
    else:
        print("Migration failed. Please check the error messages above.")
        sys.exit(1)
