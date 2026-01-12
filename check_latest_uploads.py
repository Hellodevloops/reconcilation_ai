#!/usr/bin/env python3

from database_manager import db_manager
import json

print('=== LATEST UPLOAD INVESTIGATION ===')

# Check the most recent uploads from today
try:
    # Get latest invoice
    latest_invoice = db_manager.execute_query(
        'SELECT * FROM invoices ORDER BY id DESC LIMIT 3'
    )
    print('\n--- LATEST INVOICES ---')
    for invoice in latest_invoice:
        print(f'Invoice ID: {invoice["id"]}')
        print(f'  File: {invoice["invoice_file_path"]}')
        print(f'  Number: {invoice["invoice_number"]}')
        print(f'  Vendor: {invoice["vendor_name"]}')
        print(f'  Total Amount: {invoice["total_amount"]}')
        print(f'  Status: {invoice["status"]}')
        print(f'  Created: {invoice["created_at"]}')
        
        # Check extracted data
        if invoice["extracted_data"]:
            try:
                extracted = json.loads(invoice["extracted_data"])
                print(f'  Extracted Keys: {list(extracted.keys())}')
                if "uploads" in extracted:
                    uploads = extracted["uploads"]
                    print(f'  Uploads Count: {len(uploads)}')
                    for key, upload in uploads.items():
                        print(f'    Upload {key}: {upload.get("total_amount", "N/A")} total, {len(upload.get("items", {}))} items')
            except Exception as e:
                print(f'  Extracted Data Error: {e}')
        print()

    # Get latest bank statement
    latest_bank = db_manager.execute_query(
        'SELECT * FROM bank_statements ORDER BY id DESC LIMIT 3'
    )
    print('\n--- LATEST BANK STATEMENTS ---')
    for bank in latest_bank:
        print(f'Statement ID: {bank["id"]}')
        print(f'  File: {bank["statement_file_name"]}')
        print(f'  Transactions: {bank["total_transactions"]}')
        print(f'  Credits: {bank["total_credits"]}')
        print(f'  Debits: {bank["total_debits"]}')
        print(f'  Status: {bank["processing_status"]}')
        print(f'  Created: {bank["upload_timestamp"]}')
        
        # Check extracted data
        if bank["extracted_data"]:
            try:
                extracted = json.loads(bank["extracted_data"])
                print(f'  Extracted Keys: {list(extracted.keys())}')
                if "extracted_data" in extracted:
                    data = extracted["extracted_data"]
                    transactions = data.get("transactions", {})
                    print(f'  Transactions Count: {len(transactions)}')
                    for key, tx in transactions.items():
                        print(f'    TX {key}: {tx.get("amount", "N/A")} - {tx.get("description", "N/A")}')
            except Exception as e:
                print(f'  Extracted Data Error: {e}')
        print()

    # Check latest extractions
    latest_invoice_ext = db_manager.execute_query(
        'SELECT * FROM invoice_extractions ORDER BY id DESC LIMIT 3'
    )
    print('\n--- LATEST INVOICE EXTRACTIONS ---')
    for ext in latest_invoice_ext:
        print(f'Extraction ID: {ext["id"]}')
        print(f'  Parent Invoice: {ext["parent_invoice_id"]}')
        print(f'  File: {ext["original_filename"]}')
        print(f'  JSON Path: {ext["json_file_path"]}')
        print(f'  Created: {ext["created_at"]}')
        print()

    latest_bank_ext = db_manager.execute_query(
        'SELECT * FROM bank_statement_extractions ORDER BY id DESC LIMIT 3'
    )
    print('\n--- LATEST BANK STATEMENT EXTRACTIONS ---')
    for ext in latest_bank_ext:
        print(f'Extraction ID: {ext["id"]}')
        print(f'  Parent Statement: {ext["parent_bank_statement_id"]}')
        print(f'  File: {ext["original_filename"]}')
        print(f'  JSON Path: {ext["json_file_path"]}')
        print(f'  Created: {ext["created_at"]}')
        print()

except Exception as e:
    print(f'Error: {e}')
