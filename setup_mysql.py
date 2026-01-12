#!/usr/bin/env python3
"""
MySQL Setup and Test Script
Run this script to set up MySQL database and test the integration
"""

import os
import sys
from database_manager import db_manager
from migrations.mysql_migration import main as run_migration

def test_mysql_connection():
    """Test MySQL connection"""
    print("Testing MySQL connection...")
    try:
        # Test basic connection
        result = db_manager.execute_query("SELECT 1 as test")
        if result and result[0]['test'] == 1:
            print("MySQL connection successful!")
            return True
        else:
            print("MySQL connection failed!")
            return False
    except Exception as e:
        print(f"MySQL connection error: {e}")
        return False

def test_database_tables():
    """Test if all tables were created"""
    print("\nChecking database tables...")
    required_tables = [
        'file_uploads',
        'invoices', 
        'bank_transactions',
        'reconciliations',
        'reconciliation_matches',
        'unmatched_invoices',
        'unmatched_transactions',
        'ml_models',
        'training_data'
    ]
    
    all_exist = True
    for table in required_tables:
        if db_manager.table_exists(table):
            print(f"Table '{table}' exists")
        else:
            print(f"Table '{table}' missing")
            all_exist = False
    
    return all_exist

def test_basic_operations():
    """Test basic database operations"""
    print("\nTesting basic database operations...")
    
    try:
        # Test INSERT
        insert_query = """
            INSERT INTO file_uploads 
            (file_name, file_type, file_size, processing_status) 
            VALUES (%s, %s, %s, %s)
        """
        file_id = db_manager.execute_insert(
            insert_query, 
            ('test_file.pdf', 'invoice', 1024, 'completed')
        )
        print(f"INSERT successful - ID: {file_id}")
        
        # Test SELECT
        select_query = "SELECT * FROM file_uploads WHERE id = %s"
        result = db_manager.execute_query(select_query, (file_id,))
        
        if result and len(result) > 0:
            print(f"SELECT successful - Found: {result[0]['file_name']}")
        else:
            print("SELECT failed - No data found")
            return False
        
        # Test UPDATE
        update_query = """
            UPDATE file_uploads 
            SET processing_status = %s 
            WHERE id = %s
        """
        updated = db_manager.execute_update(update_query, ('tested', file_id))
        print(f"UPDATE successful - Rows affected: {updated}")
        
        # Test DELETE
        delete_query = "DELETE FROM file_uploads WHERE id = %s"
        deleted = db_manager.execute_update(delete_query, (file_id,))
        print(f"DELETE successful - Rows deleted: {deleted}")
        
        return True
        
    except Exception as e:
        print(f"Database operations failed: {e}")
        return False

def main():
    """Main setup and test function"""
    print("MySQL Database Setup and Test")
    print("=" * 50)
    
    # Check if we're using MySQL
    if db_manager.db_type != "mysql":
        print("❌ This script requires MySQL. Set DB_TYPE=mysql in your environment or .env file")
        print("\nTo use MySQL, add this to your .env file:")
        print("DB_TYPE=mysql")
        print("MYSQL_HOST=localhost")
        print("MYSQL_USER=root")
        print("MYSQL_PASSWORD=your_password")
        print("MYSQL_DATABASE=reconciliation")
        sys.exit(1)
    
    print(f"Database Type: {db_manager.db_type}")
    print(f"MySQL Host: {db_manager.connection_params['host']}")
    print(f"MySQL Database: {db_manager.connection_params['database']}")
    print()
    
    # Step 1: Run migration
    print("Step 1: Running database migration...")
    try:
        run_migration()
    except SystemExit:
        print("❌ Migration failed!")
        sys.exit(1)
    
    # Step 2: Test connection
    if not test_mysql_connection():
        sys.exit(1)
    
    # Step 3: Check tables
    if not test_database_tables():
        sys.exit(1)
    
    # Step 4: Test operations
    if not test_basic_operations():
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("MySQL setup completed successfully!")
    print("Your reconciliation system is now ready to use with MySQL.")
    print("\nNext steps:")
    print("1. Start your Flask application")
    print("2. Upload invoices and bank statements")
    print("3. Perform reconciliation")

if __name__ == "__main__":
    main()
