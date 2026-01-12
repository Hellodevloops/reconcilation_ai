#!/usr/bin/env python3

from database_manager import db_manager
import json

print('=== CHECKING LATEST BANK STATEMENT ===')

try:
    # Get latest bank statement record
    latest_bank = db_manager.execute_query(
        "SELECT * FROM reconciliations WHERE source_file_hash IS NOT NULL OR type IS NOT NULL ORDER BY id DESC LIMIT 1"
    )
    if latest_bank:
        bank = latest_bank[0]
        print(f'Latest Bank Row in Reconciliations (ID: {bank["id"]})')
        print(f'File Name: {bank.get("source_file_name")}')
        print(f'Date UTC: {bank.get("date_utc")}')
        print(f'Type: {bank.get("type")}')
        print(f'Reference: {bank.get("reference")}')
        print(f'Amount: {bank.get("amount")}')
        print(f'Fee: {bank.get("fee")}')
        print(f'Balance: {bank.get("balance")}')
        print(f'Created At: {bank.get("created_at")}')
        
        # Check extracted data in detail
        if bank.get("raw_json"):
            try:
                extracted = json.loads(bank["raw_json"])
                print(f'\nExtracted Data Keys: {list(extracted.keys())}')
                if "statements" in extracted:
                    statements = extracted["statements"]
                    for stmt_key, stmt_data in statements.items():
                        print(f'\nStatement {stmt_key}:')
                        if "transactions" in stmt_data:
                            transactions = stmt_data["transactions"]
                            print(f'  Transactions: {len(transactions)} items')
                            for tx_key, tx in transactions.items():
                                print(f'    {tx_key}: Date={tx.get("transaction_date", "N/A")}, Desc={tx.get("description", "N/A")}, Amount={tx.get("amount", "N/A")}, Type={tx.get("type", "N/A")}')
                        else:
                            print(f'  No transactions found in statement')
                else:
                    print(f'  No statements found in extracted data')
            except Exception as e:
                print(f'Error parsing extracted data: {e}')
        else:
            print('No extracted data found')
            
except Exception as e:
    print(f'Error: {e}')
