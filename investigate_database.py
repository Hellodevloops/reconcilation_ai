#!/usr/bin/env python3

from database_manager import db_manager

print('=== DETAILED DATABASE INVESTIGATION ===')

# Check all tables and their actual structure
tables_to_check = [
    'invoices', 'invoice_extractions', 
    'bank_statements', 'bank_statement_extractions',
    'reconciliations', 'reconciliation_matches', 'reconciliation_match'
]

for table in tables_to_check:
    try:
        # Get table structure
        structure = db_manager.execute_query(f'DESCRIBE {table}')
        print(f'\n--- {table.upper()} TABLE STRUCTURE ---')
        for col in structure:
            print(f'  {col["Field"]} ({col["Type"]})')
        
        # Get count
        result = db_manager.execute_query(f'SELECT COUNT(*) as count FROM {table}')
        count = result[0]['count'] if result else 0
        print(f'  Total Records: {count}')
        
        # Get sample data if any records
        if count > 0:
            sample = db_manager.execute_query(f'SELECT * FROM {table} LIMIT 3')
            print(f'  Sample Records:')
            for i, record in enumerate(sample, 1):
                # Show key fields for each record type
                if table == 'invoices':
                    key_fields = ['id', 'invoice_number', 'vendor_name', 'total_amount', 'created_at']
                elif table == 'bank_statements':
                    key_fields = ['id', 'statement_file_name', 'total_transactions', 'created_at']
                elif table == 'invoice_extractions':
                    key_fields = ['id', 'parent_invoice_id', 'original_filename', 'created_at']
                elif table == 'bank_statement_extractions':
                    key_fields = ['id', 'parent_bank_statement_id', 'original_filename', 'created_at']
                else:
                    key_fields = list(record.keys())[:5]  # Show first 5 fields
                
                sample_str = ', '.join([f'{k}: {record.get(k, "N/A")}' for k in key_fields])
                print(f'    {i}: {sample_str}')
        
    except Exception as e:
        print(f'ERROR checking {table}: {e}')

print('\n=== DATABASE CONNECTION INFO ===')
print(f'DB Type: {db_manager.db_type}')
print(f'MySQL Host: {getattr(db_manager, "host", "N/A")}')
