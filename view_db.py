"""
Database Viewer Script
Shows database structure and data for the reconcile system
"""

import sqlite3
import os
from config import DB_PATH

def show_database_info():
    """Display comprehensive database information"""
    
    print("=" * 60)
    print("DATABASE INFORMATION")
    print("=" * 60)
    print(f"Database Path: {DB_PATH}")
    print(f"Database Size: {os.path.getsize(DB_PATH) / 1024 / 1024:.2f} MB")
    print(f"Database Exists: {os.path.exists(DB_PATH)}")
    print()
    
    if not os.path.exists(DB_PATH):
        print("❌ Database file not found!")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Show all tables
        print("📋 TABLES IN DATABASE:")
        print("-" * 40)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\n📁 Table: {table_name}")
            
            # Get table structure
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            print("   Columns:")
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                nullable = "NULL" if col[3] == 0 else "NOT NULL"
                default_val = col[4] if col[4] else ""
                print(f"     - {col_name} ({col_type}) {nullable} {default_val}")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            print(f"   Rows: {row_count}")
            
            # Show sample data for tables with data
            if row_count > 0 and row_count <= 10:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                sample_data = cursor.fetchall()
                if sample_data:
                    print("   Sample Data:")
                    for i, row in enumerate(sample_data):
                        print(f"     Row {i+1}: {row}")
        
        print("\n" + "=" * 60)
        print("MULTI-INVOICE TABLES STATUS:")
        print("=" * 60)
        
        # Check multi-invoice specific tables
        multi_invoice_tables = ['file_uploads', 'extracted_invoices', 'invoice_line_items', 'processing_jobs', 'schema_migrations']
        
        for table in multi_invoice_tables:
            if any(t[0] == table for t in tables):
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"✅ {table}: {count} records")
            else:
                print(f"❌ {table}: Not found")
        
        # Show recent file uploads if any
        cursor.execute("SELECT * FROM file_uploads ORDER BY upload_timestamp DESC LIMIT 5")
        recent_uploads = cursor.fetchall()
        
        if recent_uploads:
            print("\n📤 RECENT FILE UPLOADS:")
            print("-" * 40)
            for upload in recent_uploads:
                print(f"ID: {upload[0]}, File: {upload[1]}, Status: {upload[7]}, Invoices: {upload[10]}")
        
        # Show extracted invoices if any
        cursor.execute("SELECT COUNT(*) FROM extracted_invoices")
        invoice_count = cursor.fetchone()[0]
        
        if invoice_count > 0:
            print(f"\n📄 TOTAL EXTRACTED INVOICES: {invoice_count}")
            
            cursor.execute("""
                SELECT ei.id, ei.invoice_number, ei.total_amount, ei.vendor_name, 
                       fu.file_name 
                FROM extracted_invoices ei
                JOIN file_uploads fu ON ei.file_upload_id = fu.id
                LIMIT 10
            """)
            invoices = cursor.fetchall()
            
            print("Sample Invoices:")
            for inv in invoices:
                print(f"  ID: {inv[0]}, Invoice: {inv[1]}, Amount: ${inv[2]}, Vendor: {inv[3]}, File: {inv[4]}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error accessing database: {e}")
        import traceback
        traceback.print_exc()

def show_table_data(table_name, limit=10):
    """Show data from a specific table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            print(f"❌ Table '{table_name}' does not exist")
            return
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Get data
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
        rows = cursor.fetchall()
        
        print(f"\n📋 Table: {table_name}")
        print(f"Columns: {', '.join(columns)}")
        print(f"Rows shown: {len(rows)}")
        print("-" * 60)
        
        for i, row in enumerate(rows):
            print(f"Row {i+1}: {row}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    show_database_info()
    
    # Optional: Show specific table data
    print("\n" + "=" * 60)
    print("SHOWING SPECIFIC TABLE DATA:")
    print("=" * 60)
    
    # Show file_uploads table
    show_table_data("file_uploads", 5)
    
    # Show extracted_invoices table
    show_table_data("extracted_invoices", 5)
    
    # Show processing_jobs table
    show_table_data("processing_jobs", 5)
