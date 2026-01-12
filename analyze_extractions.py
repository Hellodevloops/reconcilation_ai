#!/usr/bin/env python3

from database_manager import db_manager
import json

print('=== DETAILED EXTRACTION ANALYSIS ===')

try:
    # Check the latest successful invoice extraction
    latest_invoice = db_manager.execute_query(
        'SELECT * FROM invoices ORDER BY id DESC LIMIT 1'
    )
    
    if latest_invoice:
        invoice = latest_invoice[0]
        print(f'\n--- INVOICE ID {invoice["id"]} ---')
        print(f'File: {invoice["invoice_file_path"]}')
        print(f'Invoice Number: {invoice["invoice_number"]}')
        print(f'Vendor Name: {invoice["vendor_name"]}')
        print(f'Total Amount: {invoice["total_amount"]}')
        print(f'Tax Amount: {invoice["tax_amount"]}')
        print(f'Invoice Date: {invoice["invoice_date"]}')
        print(f'Due Date: {invoice["due_date"]}')
        
        # Check extracted data in detail
        if invoice["extracted_data"]:
            try:
                extracted = json.loads(invoice["extracted_data"])
                print(f'\nExtracted Data Structure:')
                for key, value in extracted.items():
                    if key == "uploads":
                        print(f'  {key}:')
                        for upload_key, upload_data in value.items():
                            print(f'    {upload_key}:')
                            for sub_key, sub_value in upload_data.items():
                                print(f'      {sub_key}: {sub_value}')
                    else:
                        print(f'  {key}: {value}')
            except Exception as e:
                print(f'Error parsing extracted data: {e}')
        
        # Check line items
        if invoice["line_items"]:
            try:
                line_items = json.loads(invoice["line_items"])
                print(f'\nLine Items: {len(line_items)} items')
                for key, item in line_items.items():
                    print(f'  {key}: {item}')
            except Exception as e:
                print(f'Error parsing line items: {e}')
    
    # Check the latest successful bank statement extraction
    latest_bank = db_manager.execute_query(
        'SELECT * FROM bank_statements ORDER BY id DESC LIMIT 1'
    )
    
    if latest_bank:
        bank = latest_bank[0]
        print(f'\n--- BANK STATEMENT ID {bank["id"]} ---')
        print(f'File: {bank["statement_file_name"]}')
        print(f'Total Transactions: {bank["total_transactions"]}')
        print(f'Total Credits: {bank["total_credits"]}')
        print(f'Total Debits: {bank["total_debits"]}')
        print(f'Account Name: {bank["account_name"]}')
        print(f'Bank Name: {bank["bank_name"]}')
        
        # Check extracted data in detail
        if bank["extracted_data"]:
            try:
                extracted = json.loads(bank["extracted_data"])
                print(f'\nExtracted Data Structure:')
                for key, value in extracted.items():
                    if key == "statements":
                        print(f'  {key}:')
                        for stmt_key, stmt_data in value.items():
                            print(f'    {stmt_key}:')
                            for sub_key, sub_value in stmt_data.items():
                                if sub_key == "extracted_data":
                                    print(f'      {sub_key}:')
                                    extracted_data = sub_value
                                    if "transactions" in extracted_data:
                                        print(f'        transactions: {len(extracted_data["transactions"])} items')
                                        for tx_key, tx in extracted_data["transactions"].items():
                                            print(f'          {tx_key}: {tx}')
                                    else:
                                        print(f'        {sub_key}: {sub_value}')
                                else:
                                    print(f'      {sub_key}: {sub_value}')
                    else:
                        print(f'  {key}: {value}')
            except Exception as e:
                print(f'Error parsing extracted data: {e}')

except Exception as e:
    print(f'Error: {e}')
