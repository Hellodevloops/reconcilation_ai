#!/usr/bin/env python3
"""
Bank Statement Data Inserter
Simple script to insert bank statement data from your spreadsheet
"""

from database_manager import db_manager
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def insert_bank_statement(data_dict):
    """Insert a single bank statement record"""

    # Map incoming keys (old bank_statement schema) to reconciliations (bs_* columns)
    mapped = {
        "name": data_dict.get("name") or "Bank Statement Record",
        "description": data_dict.get("description") or "Bank statement import",
        "reconciliation_date": datetime.utcnow().date().isoformat(),
        "status": "completed",
        "total_invoices": 0,
        "total_transactions": 1,
        "total_matches": 0,
        "total_amount_matched": 0,
        "date_utc": data_dict.get("date_utc"),
        "type": data_dict.get("type"),
        "bank_description": data_dict.get("description"),
        "reference": data_dict.get("reference"),
        "payer": data_dict.get("payer"),
        "card_number": data_dict.get("card_number"),
        "orig_currency": data_dict.get("orig_currency"),
        "orig_amount": data_dict.get("orig_amount"),
        "amount": data_dict.get("amount"),
        "fee": data_dict.get("fee"),
        "balance": data_dict.get("balance"),
        "account": data_dict.get("account") or data_dict.get("bank_account_id"),
        "beneficiary": data_dict.get("beneficiary"),
        "bic": data_dict.get("bic"),
        "raw_json": None,
        "source_file_name": data_dict.get("source_file_name"),
        "source_file_hash": data_dict.get("source_file_hash"),
    }

    columns = list(mapped.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    values = [mapped[c] for c in columns]

    query = f"""
        INSERT INTO reconciliations ({', '.join(columns)})
        VALUES ({placeholders})
    """
    
    try:
        record_id = db_manager.execute_insert(query, tuple(values))
        logger.info(f"Successfully inserted bank statement record with ID: {record_id}")
        return record_id
    except Exception as e:
        logger.error(f"Error inserting bank statement data: {e}")
        raise

def insert_sample_from_image():
    """Insert sample data matching the image format"""
    
    sample_data = {
        'date_utc': '2024-01-15 10:30:00',
        'currency': 'GBP',
        'amount': 45.99,
        'fee': 2.50,
        'balance': 1234.56,
        'type': 'CARD_PAYMENT',
        'description': 'Amazon Purchase - Electronics',
        'reference': 'TXN123456789',
        'bank_account_id': 'ACC123456789',
        'transaction_id': 'TXN123456789',
        'payer': 'John Smith',
        'confirmation': 'CONF123456',
        'statement': 'STMT001',
        'beneficiary': 'Amazon Services LLC',
        'beneficiary_account': 'ACC987654321',
        'category': 'Shopping',
        'subcategory': 'Electronics',
        'merchant_name': 'Amazon.com',
        'merchant_category': 'Online Retail',
        'merchant_address': '410 Terry Ave N',
        'merchant_city': 'Seattle',
        'merchant_state': 'WA',
        'merchant_zip': '98109',
        'merchant_country': 'USA',
        'card_id': 'CARD987654321',
        'card_type': 'Credit Card',
        'card_last_4': '1234',
        'card_expiry_month': 12,
        'card_expiry_year': 2025,
        'card_holder_name': 'John Doe',
        'card_holder_email': 'john.doe@email.com',
        'card_holder_phone': '+1-555-0123',
        'card_holder_address': '123 Main St',
        'card_holder_city': 'New York',
        'card_holder_state': 'NY',
        'card_holder_zip': '10001',
        'card_holder_country': 'USA'
    }
    
    return insert_bank_statement(sample_data)

def insert_transfer_example():
    """Insert a TRANSFER type transaction example"""
    
    transfer_data = {
        'date_utc': '2024-01-16 14:22:00',
        'currency': 'GBP',
        'amount': 250.00,
        'fee': 0.00,
        'balance': 984.56,
        'type': 'TRANSFER',
        'description': 'Bank Transfer to Savings Account',
        'reference': 'TRF987654321',
        'bank_account_id': 'ACC123456789',
        'transaction_id': 'TRF987654321',
        'payer': 'John Smith',
        'confirmation': 'CONF789012',
        'statement': 'STMT002',
        'beneficiary': 'John Smith Savings',
        'beneficiary_account': 'SAV456789',
        'category': 'Transfer',
        'subcategory': 'Internal Transfer'
    }
    
    return insert_bank_statement(transfer_data)

def view_recent_records(limit=5):
    """View recent bank statement records"""
    try:
        query = "SELECT id, date_utc, type, amount, bank_description FROM reconciliations WHERE source_file_hash IS NOT NULL OR type IS NOT NULL ORDER BY id DESC LIMIT %s"
        records = db_manager.execute_query(query, (limit,))
        
        if records:
            print(f"\nRecent {len(records)} Bank Statement Records:")
            print("-" * 100)
            for record in records:
                print(
                    f"ID: {record['id']} | Date: {record.get('date_utc')} | Type: {record.get('type')} | "
                    f"Amount: {record.get('amount')} | Description: {record.get('bank_description')}"
                )
            print("-" * 100)
        else:
            print("No records found in reconciliations table")
            
    except Exception as e:
        logger.error(f"Error viewing records: {e}")

if __name__ == "__main__":
    print("Bank Statement Data Inserter")
    print("=" * 40)
    
    # Insert sample data
    print("\n1. Inserting sample data from image...")
    insert_sample_from_image()
    
    print("\n2. Inserting TRANSFER example...")
    insert_transfer_example()
    
    # View recent records
    print("\n3. Viewing recent records...")
    view_recent_records()
    
    print("\nData insertion complete!")
    print("You can now use the insert_bank_statement() function to add your own data")
