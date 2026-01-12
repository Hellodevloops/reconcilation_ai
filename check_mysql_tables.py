#!/usr/bin/env python3

from database_manager import db_manager

try:
    tables = db_manager.execute_query('SHOW TABLES')
    print('MySQL Tables:')
    for table in tables:
        table_name = list(table.values())[0]
        print(f'  - {table_name}')
        if 'bank_statement' in table_name:
            columns = db_manager.execute_query(f'DESCRIBE {table_name}')
            print(f'    Columns:')
            for col in columns:
                print(f'      - {col["Field"]} ({col["Type"]})')
except Exception as e:
    print(f'Error: {e}')
