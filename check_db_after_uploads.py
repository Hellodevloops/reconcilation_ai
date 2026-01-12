#!/usr/bin/env python3

from database_manager import db_manager

try:
    # Check all tables after uploads
    tables = ['invoices', 'invoice_extractions', 'reconciliations']
    for table in tables:
        try:
            result = db_manager.execute_query(f'SELECT COUNT(*) as count FROM {table}')
            count = result[0]['count'] if result else 0
            print(f'{table}: {count} records')
            
            # Get latest record
            if count > 0:
                latest = db_manager.execute_query(f'SELECT * FROM {table} ORDER BY id DESC LIMIT 1')
                if latest:
                    record = latest[0]
                    if 'file_name' in record:
                        print(f'  Latest: {record["file_name"]} (ID: {record["id"]})')
                    elif 'source_file_name' in record:
                        print(f'  Latest: {record.get("source_file_name")} (ID: {record["id"]})')
        except Exception as e:
            print(f'{table}: ERROR - {e}')
except Exception as e:
    print(f'Database connection error: {e}')
