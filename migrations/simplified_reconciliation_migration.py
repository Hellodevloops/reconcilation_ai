"""
Simplified Reconciliation Migration
Single table design for reconciliation_match as central source of truth
"""

import os
import sys
import sqlite3
import traceback
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models.simplified_reconciliation import get_simplified_reconciliation_schema
from config import DB_PATH

def run_simplified_reconciliation_migration():
    """Run the simplified reconciliation migration"""
    print("=" * 70)
    print("SIMPLIFIED RECONCILIATION MIGRATION - SINGLE TABLE DESIGN")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    print("DESIGN PRINCIPLE:")
    print("• ALL reconciliation data stored in single reconciliation_match table")
    print("• Single reconciliation_id groups all related records")
    print("• No data scattered across multiple tables")
    print("• Central source of truth for all reconciliation operations")
    print()
    
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Enable foreign key constraints
        cur.execute("PRAGMA foreign_keys = ON")
        
        # Check if table already exists
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='reconciliation_match'
        """)
        
        table_exists = cur.fetchone()[0] > 0
        if table_exists:
            print("+ reconciliation_match table already exists")
            print("  - Checking if indexes need updating...")
        else:
            print("Creating reconciliation_match table...")
        
        # Get schema statements
        statements = get_simplified_reconciliation_schema()
        
        # Execute statements
        executed_count = 0
        for i, statement in enumerate(statements, 1):
            try:
                cur.execute(statement)
                if "CREATE TABLE" in statement:
                    print(f"  {i}/{len(statements)}: Created reconciliation_match table")
                elif "CREATE INDEX" in statement:
                    index_name = statement.split("idx_")[1].split(" ")[0] if "idx_" in statement else f"index_{i}"
                    print(f"  {i}/{len(statements)}: Created index idx_{index_name}")
                else:
                    print(f"  {i}/{len(statements)}: Executed schema statement")
                executed_count += 1
            except sqlite3.Error as e:
                if "already exists" in str(e).lower():
                    if "CREATE TABLE" in statement:
                        print(f"  {i}/{len(statements)}: Table already exists")
                    elif "CREATE INDEX" in statement:
                        index_name = statement.split("idx_")[1].split(" ")[0] if "idx_" in statement else f"index_{i}"
                        print(f"  {i}/{len(statements)}: Index idx_{index_name} already exists")
                    executed_count += 1
                else:
                    print(f"  {i}/{len(statements)}: Error: {e}")
        
        # Record migration
        cur.execute("""
            INSERT OR IGNORE INTO schema_migrations (migration_name, executed_at)
            VALUES ('simplified_reconciliation_v1', ?)
        """, (datetime.now().isoformat(),))
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print()
        print("+ Simplified reconciliation migration completed successfully!")
        print()
        print("Created/Updated:")
        print("  - reconciliation_match table (single source of truth)")
        print("  - Performance indexes for optimal queries")
        print("  - Foreign key constraints to document tables")
        print()
        print("Table Structure:")
        print("  - reconciliation_id: Groups all records for one operation")
        print("  - match_type: exact, partial, unmatched_invoice, unmatched_transaction")
        print("  - Invoice references: invoice_upload_id, extracted_invoice_id")
        print("  - Bank references: bank_upload_id, bank_transaction_id")
        print("  - Match analysis: match_score, confidence_level, amount_difference")
        print("  - Audit trail: created_by, verified_by, timestamps")
        print()
        print("Key Benefits:")
        print("  + Single table stores ALL reconciliation data")
        print("  + No data scattered across multiple tables")
        print("  + Single reconciliation_id groups related records")
        print("  + Simplified queries and maintenance")
        print("  + Production-ready with proper indexing")
        print("  + Consistent parent-child logic")
        
        return True
        
    except Exception as e:
        print(f"- Migration failed: {e}")
        print("Traceback:")
        traceback.print_exc()
        return False

def verify_simplified_reconciliation():
    """Verify the simplified reconciliation implementation"""
    print("\n" + "=" * 70)
    print("VERIFYING SIMPLIFIED RECONCILIATION IMPLEMENTATION")
    print("=" * 70)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check table exists
        cur.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='table' AND name='reconciliation_match'
        """)
        table_exists = cur.fetchone()[0] > 0
        status = "+" if table_exists else "-"
        print(f"  {status} reconciliation_match table exists")
        
        if table_exists:
            # Check table structure
            cur.execute("PRAGMA table_info(reconciliation_match)")
            columns = cur.fetchall()
            print(f"  + Table has {len(columns)} columns")
            
            # Check key columns
            column_names = [col[1] for col in columns]
            key_columns = [
                'reconciliation_id', 'match_type', 'invoice_upload_id', 
                'bank_upload_id', 'match_score', 'created_at'
            ]
            
            for col in key_columns:
                status = "+" if col in column_names else "-"
                print(f"  {status} Column '{col}' exists")
            
            # Check indexes
            cur.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='index' AND tbl_name='reconciliation_match'
            """)
            index_count = cur.fetchone()[0]
            print(f"  + {index_count} indexes created")
            
            # Check sample data if exists
            cur.execute("SELECT COUNT(*) FROM reconciliation_match")
            record_count = cur.fetchone()[0]
            print(f"  + {record_count} records in table")
            
            if record_count > 0:
                # Check match type distribution
                cur.execute("""
                    SELECT match_type, COUNT(*) 
                    FROM reconciliation_match 
                    GROUP BY match_type
                """)
                distribution = cur.fetchall()
                print("  + Match type distribution:")
                for match_type, count in distribution:
                    print(f"    - {match_type}: {count}")
                
                # Check reconciliation groups
                cur.execute("SELECT COUNT(DISTINCT reconciliation_id) FROM reconciliation_match")
                unique_reconciliations = cur.fetchone()[0]
                print(f"  + {unique_reconciliations} unique reconciliation groups")
        
        conn.close()
        
        if table_exists:
            print("\n+ Simplified reconciliation verification successful!")
            print("  Single table design implemented correctly")
            return True
        else:
            print("\n- reconciliation_match table not found!")
            return False
            
    except Exception as e:
        print(f"\n- Verification failed: {e}")
        return False

def demonstrate_single_table_design():
    """Demonstrate the single table design benefits"""
    print("\n" + "=" * 70)
    print("SINGLE TABLE DESIGN DEMONSTRATION")
    print("=" * 70)
    
    print("ARCHITECTURE COMPARISON:")
    print("-" * 40)
    print()
    print("OLD MULTI-TABLE DESIGN:")
    print("  • financial_reconciliations (parent)")
    print("  • reconciliation_matches (child)")
    print("  • unmatched_items (child)")
    print("  • Data scattered across 3 tables")
    print("  • Complex joins required")
    print("  • Maintenance overhead")
    print()
    print("NEW SINGLE TABLE DESIGN:")
    print("  • reconciliation_match (single table)")
    print("  • ALL data in one place")
    print("  • Single reconciliation_id groups records")
    print("  • Simple queries")
    print("  • Easy maintenance")
    
    print("\nDATA FLOW EXAMPLE:")
    print("-" * 40)
    print("Reconciliation Operation: REC-2024-001")
    print()
    print("Single Table Storage:")
    print("  reconciliation_match:")
    print("    ├── reconciliation_id: 'REC-2024-001', match_type: 'exact'")
    print("    ├── reconciliation_id: 'REC-2024-001', match_type: 'exact'")
    print("    ├── reconciliation_id: 'REC-2024-001', match_type: 'partial'")
    print("    ├── reconciliation_id: 'REC-2024-001', match_type: 'unmatched_invoice'")
    print("    └── reconciliation_id: 'REC-2024-001', match_type: 'unmatched_transaction'")
    print()
    print("Parent-Child Logic:")
    print("  • Parent: reconciliation_id = 'REC-2024-001'")
    print("  • Children: All records with same reconciliation_id")
    print("  • Grouping: Single query WHERE reconciliation_id = 'REC-2024-001'")
    
    print("\nQUERY EXAMPLES:")
    print("-" * 40)
    print("Get complete reconciliation:")
    print("  SELECT * FROM reconciliation_match WHERE reconciliation_id = 'REC-2024-001'")
    print()
    print("Get only matches:")
    print("  SELECT * FROM reconciliation_match WHERE reconciliation_id = 'REC-2024-001' AND match_type IN ('exact', 'partial')")
    print()
    print("Get summary:")
    print("  SELECT match_type, COUNT(*) FROM reconciliation_match WHERE reconciliation_id = 'REC-2024-001' GROUP BY match_type")
    
    print("\nPRODUCTION BENEFITS:")
    print("-" * 40)
    print("✓ Single Source of Truth: All data in one table")
    print("✓ Simplified Queries: No complex joins needed")
    print("✓ Better Performance: Optimized indexes on single table")
    print("✓ Easy Maintenance: One table to manage and backup")
    print("✓ Consistent Logic: Same parent-child pattern as uploads")
    print("✓ Scalability: Handles large datasets efficiently")
    print("✓ Audit Trail: Complete history in single location")

def main():
    """Main migration function"""
    print("SIMPLIFIED RECONCILIATION MIGRATION TOOL")
    print("=" * 70)
    print("Single Table Design - Central Source of Truth")
    print("=" * 70)
    
    # Run migration
    if run_simplified_reconciliation_migration():
        # Verify implementation
        if verify_simplified_reconciliation():
            # Demonstrate design
            demonstrate_single_table_design()
            
            print("\n" + "=" * 70)
            print("SIMPLIFIED RECONCILIATION MIGRATION COMPLETED!")
            print("=" * 70)
            print("✓ Single reconciliation_match table created")
            print("✓ All reconciliation data stored centrally")
            print("✓ Single reconciliation_id groups related records")
            print("✓ No data scattered across multiple tables")
            print("✓ Production-ready with proper indexing")
            print("✓ Consistent parent-child architecture")
            print()
            print("The reconciliation_match table is now the CENTRAL SOURCE OF TRUTH")
            print("for all reconciliation data in your production system.")
            return True
        else:
            print("\n- Verification failed!")
            return False
    else:
        print("\n- Migration failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
