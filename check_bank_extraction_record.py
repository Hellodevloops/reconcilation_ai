#!/usr/bin/env python3

from database_manager import db_manager
import json

print('=== CHECKING BANK STATEMENT EXTRACTION RECORD ===')

try:
    # Get latest bank statement extraction record
    latest_extraction = db_manager.execute_query(
        'SELECT * FROM bank_statement_extractions ORDER BY id DESC LIMIT 1'
    )
    
    if latest_extraction:
        ext = latest_extraction[0]
        print(f'Latest Bank Statement Extraction (ID: {ext["id"]})')
        print(f'Parent Statement ID: {ext["parent_bank_statement_id"]}')
        print(f'Original Filename: {ext["original_filename"]}')
        print(f'JSON File Path: {ext["json_file_path"]}')
        print(f'Created At: {ext["created_at"]}')
        
        # Check extracted data
        if ext["extracted_data"]:
            try:
                extracted = json.loads(ext["extracted_data"])
                print(f'\nExtracted Data Keys: {list(extracted.keys())}')
                
                if "extracted_data" in extracted:
                    data = extracted["extracted_data"]
                    if "transactions" in data:
                        transactions = data["transactions"]
                        print(f'\nTransactions: {len(transactions)} items')
                        for tx_key, tx in transactions.items():
                            print(f'  {tx_key}:')
                            print(f'    Date: {tx.get("transaction_date", "N/A")}')
                            print(f'    Description: {tx.get("description", "N/A")}')
                            print(f'    Amount: {tx.get("amount", "N/A")}')
                            print(f'    Type: {tx.get("type", "N/A")}')
                    else:
                        print(f'No transactions found in extracted_data')
                else:
                    print(f'No extracted_data key found')
                    
            except Exception as e:
                print(f'Error parsing extracted data: {e}')
        else:
            print('No extracted data found')
            
except Exception as e:
    print(f'Error: {e}')
