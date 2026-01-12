#!/usr/bin/env python3

from database_manager import db_manager

try:
    # Check bank_statement_extractions records
    extractions = db_manager.execute_query('SELECT * FROM bank_statement_extractions')
    print(f'Bank statement extractions: {len(extractions)} records')
    for ext in extractions:
        print(f'  ID: {ext["id"]}, Parent: {ext["parent_bank_statement_id"]}, File: {ext["original_filename"]}')
    
    # Check bank_statements records  
    statements = db_manager.execute_query('SELECT id, statement_file_name, total_transactions FROM bank_statements ORDER BY id DESC LIMIT 3')
    print(f'\nBank statements: {len(statements)} records')
    for stmt in statements:
        print(f'  ID: {stmt["id"]}, File: {stmt["statement_file_name"]}, Transactions: {stmt["total_transactions"]}')
        
except Exception as e:
    print(f'Error: {e}')
