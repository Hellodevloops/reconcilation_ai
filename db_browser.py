"""
Simple SQLite Database Browser
Interactive tool to view and manage your reconcile database
"""

import sqlite3
import os
from config import DB_PATH

class DatabaseBrowser:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        
    def connect(self):
        """Connect to database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Enable dict-like access
            return True
        except Exception as e:
            print(f"Error connecting to database: {e}")
            return False
    
    def show_tables(self):
        """Show all tables with row counts"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        print("\n" + "=" * 80)
        print("DATABASE TABLES")
        print("=" * 80)
        print(f"{'Table':<30} {'Rows':<10} {'Size (KB)':<10}")
        print("-" * 80)
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            
            # Get approximate table size
            cursor.execute(f"SELECT COUNT(*) * 100 FROM {table_name}")
            size_kb = row_count * 0.1  # Rough estimate
            
            print(f"{table_name:<30} {row_count:<10} {size_kb:<10.1f}")
    
    def show_table_structure(self, table_name):
        """Show detailed table structure"""
        cursor = self.conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            print(f"Table '{table_name}' does not exist")
            return
        
        # Get table info
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        print(f"\n" + "=" * 80)
        print(f"TABLE STRUCTURE: {table_name}")
        print("=" * 80)
        print(f"{'Column':<25} {'Type':<15} {'Nullable':<10} {'Default':<20}")
        print("-" * 80)
        
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            nullable = "YES" if col[3] == 0 else "NO"
            default_val = str(col[4]) if col[4] else ""
            print(f"{col_name:<25} {col_type:<15} {nullable:<10} {default_val:<20}")
    
    def show_table_data(self, table_name, limit=20):
        """Show data from table"""
        cursor = self.conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            print(f"Table '{table_name}' does not exist")
            return
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Get total row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cursor.fetchone()[0]
        
        # Get data
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
        rows = cursor.fetchall()
        
        print(f"\n" + "=" * 80)
        print(f"TABLE DATA: {table_name}")
        print("=" * 80)
        print(f"Total Rows: {total_rows} (Showing {len(rows)})")
        print("-" * 80)
        
        if not rows:
            print("No data in table")
            return
        
        # Show column headers
        col_width = 15
        header = " | ".join([col[:col_width].ljust(col_width) for col in columns])
        print(header)
        print("-" * len(header))
        
        # Show data rows
        for row in rows:
            row_data = " | ".join([str(row[col])[:col_width].ljust(col_width) if row[col] else "NULL" for col in columns])
            print(row_data)
    
    def run_query(self, query):
        """Execute custom SQL query"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(query)
            
            if query.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                if rows:
                    # Show column names
                    columns = [description[0] for description in cursor.description]
                    col_width = 15
                    header = " | ".join([col[:col_width].ljust(col_width) for col in columns])
                    print(header)
                    print("-" * len(header))
                    
                    # Show data
                    for row in rows:
                        row_data = " | ".join([str(row[col])[:col_width].ljust(col_width) if row[col] else "NULL" for col in range(len(columns))])
                        print(row_data)
                    
                    print(f"\n{len(rows)} rows returned")
                else:
                    print("No rows returned")
            else:
                self.conn.commit()
                print(f"Query executed successfully. {cursor.rowcount} rows affected.")
                
        except Exception as e:
            print(f"Error executing query: {e}")
    
    def interactive_mode(self):
        """Interactive database browser"""
        if not self.connect():
            return
        
        print("\n" + "=" * 80)
        print("SQLITE DATABASE BROWSER")
        print("=" * 80)
        print(f"Database: {self.db_path}")
        print(f"Size: {os.path.getsize(self.db_path) / 1024 / 1024:.2f} MB")
        
        while True:
            print("\n" + "-" * 80)
            print("OPTIONS:")
            print("1. Show all tables")
            print("2. Show table structure")
            print("3. Show table data")
            print("4. Run custom query")
            print("5. Exit")
            print("-" * 80)
            
            choice = input("Enter your choice (1-5): ").strip()
            
            if choice == "1":
                self.show_tables()
            
            elif choice == "2":
                table_name = input("Enter table name: ").strip()
                self.show_table_structure(table_name)
            
            elif choice == "3":
                table_name = input("Enter table name: ").strip()
                try:
                    limit = int(input("Enter row limit (default 20): ").strip() or "20")
                except:
                    limit = 20
                self.show_table_data(table_name, limit)
            
            elif choice == "4":
                query = input("Enter SQL query: ").strip()
                if query:
                    self.run_query(query)
            
            elif choice == "5":
                print("Goodbye!")
                break
            
            else:
                print("Invalid choice. Please try again.")
        
        if self.conn:
            self.conn.close()

def main():
    """Main function"""
    print("SQLITE DATABASE BROWSER")
    print("=" * 50)
    print(f"Database: {DB_PATH}")
    print(f"Size: {os.path.getsize(DB_PATH) / 1024 / 1024:.2f} MB")
    
    browser = DatabaseBrowser(DB_PATH)
    browser.interactive_mode()

if __name__ == "__main__":
    main()
