#!/usr/bin/env python3

from database_manager import db_manager
import json

try:
    # Get the extraction record details
    extraction = db_manager.execute_query('SELECT * FROM bank_statement_extractions WHERE id = 1')
    if extraction:
        ext = extraction[0]
        print(f'Extraction ID: {ext["id"]}')
        print(f'Parent Statement ID: {ext["parent_bank_statement_id"]}')
        print(f'Original Filename: {ext["original_filename"]}')
        print(f'JSON File Path: {ext["json_file_path"]}')
        print(f'Sequence No: {ext["sequence_no"]}')
        print(f'Page No: {ext["page_no"]}')
        
        # Parse and display extracted data
        if ext['extracted_data']:
            data = json.loads(ext['extracted_data'])
            print(f'\nExtracted Data Keys: {list(data.keys())}')
            if 'extracted_data' in data:
                extracted = data['extracted_data']
                print(f'Transactions: {len(extracted.get("transactions", {}))}')
                print(f'Invoice Data: {len(extracted.get("invoice_data", {}))}')
                if 'statement_metadata' in extracted:
                    meta = extracted['statement_metadata']
                    print(f'Metadata: {meta}')
                    
                # Show some transaction details
                transactions = extracted.get('transactions', {})
                if transactions:
                    print(f'\nSample Transactions:')
                    for i, (key, tx) in enumerate(transactions.items()):
                        if i < 3:  # Show first 3
                            print(f'  {key}: {tx}')
                        else:
                            break
except Exception as e:
    print(f'Error: {e}')
