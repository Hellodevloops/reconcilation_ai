#!/usr/bin/env python3

from database_manager import db_manager

print('=== CHECKING TABLE STRUCTURES ===')

try:
    # Check bank_statements table structure
    bank_structure = db_manager.execute_query('DESCRIBE bank_statements')
    print('\n--- BANK_STATEMENTS TABLE STRUCTURE ---')
    for col in bank_structure:
        print(f'  {col["Field"]} ({col["Type"]})')
    
    # Check latest bank statement record
    latest_bank = db_manager.execute_query('SELECT * FROM bank_statements ORDER BY id DESC LIMIT 1')
    if latest_bank:
        bank = latest_bank[0]
        print(f'\n--- LATEST BANK STATEMENT (ID: {bank["id"]}) ---')
        print(f'File Name: {bank["statement_file_name"]}')
        print(f'Total Transactions: {bank["total_transactions"]}')
        print(f'Total Credits: {bank["total_credits"]}')
        print(f'Total Debits: {bank["total_debits"]}')
        print(f'Processing Status: {bank["processing_status"]}')
        print(f'Upload Timestamp: {bank["upload_timestamp"]}')
        
        # Check extracted data
        if bank["extracted_data"]:
            import json
            try:
                extracted = json.loads(bank["extracted_data"])
                print(f'Extracted Data Keys: {list(extracted.keys())}')
                if "statements" in extracted:
                    statements = extracted["statements"]
                    for stmt_key, stmt_data in statements.items():
                        print(f'  Statement {stmt_key}:')
                        if "extracted_data" in stmt_data:
                            data = stmt_data["extracted_data"]
                            if "transactions" in data:
                                transactions = data["transactions"]
                                print(f'    Transactions: {len(transactions)} items')
                                for tx_key, tx in transactions.items():
                                    print(f'      {tx_key}: {tx}')
            except Exception as e:
                print(f'Error parsing extracted data: {e}')
        else:
            print('No extracted data found')
            
except Exception as e:
    print(f'Error: {e}')
