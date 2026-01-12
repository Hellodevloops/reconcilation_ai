"""
Complete Bank Transaction Storage Solution
==========================================

This implementation stores bank transactions from uploaded PDFs in the 
bank_transactions table exactly like invoices are stored in the invoices table.

Key Features:
1. PDF upload with OCR extraction
2. Each transaction stored as separate row in bank_transactions table
3. JSON metadata stored in raw_data column
4. Re-upload support with unique indexing
5. Same logic as invoice upload but for bank transactions

Database Schema (bank_transactions table):
- id: Primary key (auto-increment)
- file_upload_id: NULL (not linking to file_uploads table)
- transaction_date: Date of transaction
- description: Transaction description
- amount: Transaction amount
- balance: Account balance (if available)
- transaction_type: 'credit' or 'debit'
- reference_number: Reference number (NULL for now)
- account_number: Account number (NULL for now)
- category: Category (NULL for now)
- raw_data: JSON metadata with file info and upload index
- created_at: Timestamp

API Endpoints:
- POST /api/upload-bank-transactions - Upload and process bank statement
- GET /api/bank-transactions - List all bank transactions

Usage Example:
--------------
1. Upload PDF:
   curl -X POST -F "file=@bank_statement.pdf" http://localhost:5001/api/upload-bank-transactions

2. Response:
   {
     "success": true,
     "transaction_ids": [1, 2, 3, 4, 5],
     "file_name": "bank_statement.pdf",
     "file_size": 1024000,
     "bank_file_hash": "abc123_1641234567",
     "upload_index": 1,
     "total_transactions": 5,
     "total_credits": 3000.0,
     "total_debits": 1250.5,
     "transactions": {
       "1": {
         "transaction_date": "2024-01-15",
         "description": "CARLSBERG MARSTONS BREWING COMPANY",
         "amount": 1250.5,
         "type": "debit",
         "balance": 5000.0
       },
       "2": {
         "transaction_date": "2024-01-16",
         "description": "Payment received from ABC Pvt Ltd",
         "amount": 3000.0,
         "type": "credit",
         "balance": 8000.0
       }
     },
     "message": "Bank transactions uploaded successfully. 5 transactions stored in bank_transactions table."
   }

3. List transactions:
   curl http://localhost:5001/api/bank-transactions

Re-upload Behavior:
-----------------
Same file uploaded again creates new records with upload_index = 2:
- First upload: upload_index = 1
- Second upload: upload_index = 2
- Third upload: upload_index = 3
etc.

Each transaction in bank_transactions table has raw_data like:
{
  "file_name": "bank_statement.pdf",
  "file_hash": "abc123_1641234568",
  "upload_index": 2,
  "sequence": "1",
  "transaction_date": "2024-01-15",
  "description": "CARLSBERG MARSTONS BREWING COMPANY",
  "amount": 1250.5,
  "type": "debit",
  "balance": 5000.0
}

Files Created/Modified:
----------------------
1. api/bank_transaction_endpoints.py - New file with bank transaction upload logic
2. app.py - Modified to register bank transaction routes
3. migrations/mysql_migration.py - Already has bank_transactions table
4. test_bank_transactions.py - Test script for verification

Installation:
------------
1. Ensure MySQL database is running
2. Run migration: python migrations/mysql_migration.py
3. Start server: python app.py
4. Test with: python test_bank_transactions.py

This is exactly the same logic as invoice upload but stores data in 
bank_transactions table instead of invoices table.
"""
