"""
Bank Transaction Upload and Storage API
Stores bank transactions from PDFs in bank_transactions table similar to invoices
"""

import os
import sys
import time
import hashlib
import json
import re
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import traceback

# Add project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import (
    UPLOAD_FOLDER, MAX_FILE_SIZE_BYTES, 
    INVOICE_ALLOWED_EXTENSIONS, INVOICE_ALLOWED_MIMETYPES,
    RATE_LIMITS, DB_TYPE
)
from database_manager import db_manager

# Bank statement allowed extensions and mimetypes
BANK_ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.csv', '.jpg', '.jpeg', '.png', '.tiff', '.tif'}
BANK_ALLOWED_MIMETYPES = {
    'application/pdf', 'image/jpeg', 'image/png', 'image/tiff',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel', 'text/csv'
}

# Directory for storing uploaded bank statement files
BANK_FOLDER = os.path.join(UPLOAD_FOLDER, "bank_statements")
os.makedirs(BANK_FOLDER, exist_ok=True)


def _normalize_date_yyyy_mm_dd(raw: str | None) -> str | None:
    """Normalize date to YYYY-MM-DD format"""
    if not raw:
        return None
    txt = str(raw).strip()
    if not txt:
        return None

    txt = re.sub(r"\s+", " ", txt)
    candidates = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %b %y",
        "%d %B %y",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(txt, fmt).date().isoformat()
        except Exception:
            continue
    return None


    return None


def _normalize_date_dd_mmm_yyyy(raw: str | None) -> str | None:
    if not raw:
        return None
    txt = str(raw).strip()
    if not txt:
        return None
    txt = re.sub(r"\s+", " ", txt)
    for fmt in ["%d %b %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(txt, fmt).date().isoformat()
        except Exception:
            continue
    return None


def _to_number(val):
    """Convert value to number safely"""
    try:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if not s:
            return None
        s = s.replace(",", "")
        return float(s)
    except Exception:
        return None


def _get_next_bank_upload_index_for_hash(base_file_hash: str) -> int:
    """Get next upload index for bank file hash"""
    try:
        rows = db_manager.execute_query(
            """
            SELECT
                MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.upload_index')) AS UNSIGNED)) AS max_idx
            FROM bank_transactions
            WHERE JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.base_file_hash')) = ?
            """,
            (base_file_hash,),
        )
        if rows and rows[0] and rows[0].get("max_idx") is not None:
            return int(rows[0]["max_idx"]) + 1
    except Exception:
        pass
    return 1


    return transactions


def _parse_tide_transaction_lines(lines: list[str]) -> dict:
    """Specialized parser for Tide bank statements"""
    transactions: dict = {}
    seq = 0

    for raw_line in lines:
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        # Tide Date format: 28 Apr 2024
        dm = re.match(r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(.*)$", line)
        if not dm:
            continue

        tx_date = _normalize_date_dd_mmm_yyyy(dm.group(1))
        rest = dm.group(2).strip()

        # Extract all money values in the line (e.g. PaidOut, PaidIn, Balance)
        money_vals = re.findall(r"(\d{1,3}(?:,\d{3})*\.\d{2})", rest)
        if not money_vals:
            continue
        nums = [_to_number(v) for v in money_vals]
        nums = [n for n in nums if n is not None]
        if not nums:
            continue

        # Logic for Columns: [Details] [Paid Out] [Paid In] [Balance]
        # Balance is typically the last number
        balance = nums[-1] if len(nums) >= 1 else None
        paid_in = None
        paid_out = None

        if len(nums) >= 3:
            paid_in = nums[-3]
            paid_out = nums[-2]
        elif len(nums) == 2:
            # Can't always disambiguate; infer from text hints
            hint = rest.lower()
            if "debit" in hint or "paid out" in hint or "out" in hint:
                paid_out = nums[-2]
            else:
                paid_in = nums[-2]

        tx_dir = None
        amount = None
        if paid_in is not None and paid_in != 0:
            tx_dir = "credit"
            amount = abs(paid_in)
        elif paid_out is not None and paid_out != 0:
            tx_dir = "debit"
            amount = abs(paid_out)

        # Remove numbers to get description/type
        rest_wo_money = re.sub(r"\d{1,3}(?:,\d{3})*\.\d{2}", " ", rest).strip()
        rest_wo_money = re.sub(r"\s+", " ", rest_wo_money)

        tx_type = None
        details = rest_wo_money
        
        # Heuristics for Tide transaction types
        for candidate in ["Domestic Transfer", "Direct Debit", "Card Transaction"]:
            if rest_wo_money.lower().startswith(candidate.lower()):
                tx_type = candidate.strip()
                details = rest_wo_money[len(candidate):].strip(" -")
                break

        if not tx_type:
            parts = rest_wo_money.split(" ")
            if len(parts) >= 2:
                # Guess first 2 words are type
                tx_type = " ".join(parts[:2])
                details = " ".join(parts[2:]).strip()

        seq += 1
        transactions[str(seq)] = {
            "transaction_date": tx_date,
            "description": details[:255] if details else None,
            "amount": amount,
            "type": tx_dir,
            "balance": balance,
            "transaction_type": tx_type
        }

        if seq >= 75000:
            break

    return transactions


def _extract_bank_transactions_from_pdf(file_path: str) -> dict:
    """Extract bank transactions from PDF using OCR"""
    from PyPDF2 import PdfReader
    
    transactions = {}
    
    try:
        # Extract text from PDF
        text = ""
        try:
            with open(file_path, "rb") as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    try:
                        text += (page.extract_text() or "") + "\n"
                    except Exception:
                        continue
        except Exception:
            text = ""
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Try Tide parser first if it looks like Tide (DD Mon YYYY at start)
        tide_tx = _parse_tide_transaction_lines(lines)
        if tide_tx and len(tide_tx) > 0:
            return tide_tx

        # Fallback to generic parser
        seq = 0
        for line in lines:
            # Pattern to detect bank transactions
            date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', line)
            amount_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', line)
            
            if date_match and amount_match:
                seq += 1
                transaction_date = _normalize_date_yyyy_mm_dd(date_match.group(1))
                amount = _to_number(amount_match.group(1))
                
                # Determine transaction type
                transaction_type = "debit"
                if any(word in line.lower() for word in ['credit', 'deposit', 'received', 'in']):
                    transaction_type = "credit"
                elif any(word in line.lower() for word in ['debit', 'withdraw', 'payment', 'out']):
                    transaction_type = "debit"
                
                # Extract description
                description = line
                description = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', '', description).strip()
                description = re.sub(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?', '', description).strip()
                description = description[:200] if description else None
                
                # Extract balance if available
                balance = None
                balance_match = re.search(r'balance[:\s]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', line, re.IGNORECASE)
                if balance_match:
                    balance = _to_number(balance_match.group(1))
                
                transactions[str(seq)] = {
                    "transaction_date": transaction_date,
                    "description": description,
                    "amount": amount,
                    "type": transaction_type,
                    "balance": balance
                }
                
                # Limit to 75000 transactions
                if seq >= 75000:
                    break
    
    except Exception as e:
        print(f"Error extracting from PDF: {e}")
    
    return transactions


def _extract_bank_transactions_from_csv(file_bytes: bytes) -> dict:
    import csv as _csv
    import io as _io

    text = file_bytes.decode("utf-8", errors="ignore")
    f = _io.StringIO(text)
    reader = _csv.DictReader(f)

    transactions: dict = {}
    seq = 0
    for row in reader:
        if not row:
            continue

        date_raw = (
            row.get("date")
            or row.get("Date")
            or row.get("transaction_date")
            or row.get("Transaction Date")
        )
        desc = row.get("description") or row.get("Description") or row.get("narration") or row.get("Narration")
        amt_raw = row.get("amount") or row.get("Amount") or row.get("debit") or row.get("Debit") or row.get("credit") or row.get("Credit")
        bal_raw = row.get("balance") or row.get("Balance")

        tx_date = _normalize_date_yyyy_mm_dd(date_raw)
        amt = _to_number(amt_raw)
        bal = _to_number(bal_raw)

        if tx_date is None and (desc is None or str(desc).strip() == "") and amt is None:
            continue

        seq += 1
        tx_type = "debit"
        if amt is not None and float(amt) >= 0:
            tx_type = "credit"

        transactions[str(seq)] = {
            "transaction_date": tx_date,
            "description": (str(desc).strip()[:200] if desc else None),
            "amount": amt,
            "type": tx_type,
            "balance": bal,
        }

        if seq >= 5000:
            break

    return transactions


def _extract_bank_transactions_from_excel(file_bytes: bytes) -> dict:
    import io as _io
    import pandas as _pd

    df = _pd.read_excel(_io.BytesIO(file_bytes))
    df.columns = [str(c).strip() for c in df.columns]

    transactions: dict = {}
    seq = 0

    date_col = None
    desc_col = None
    amt_col = None
    bal_col = None

    for c in df.columns:
        lc = c.lower()
        if date_col is None and ("date" in lc):
            date_col = c
        if desc_col is None and ("desc" in lc or "narration" in lc or "particular" in lc):
            desc_col = c
        if amt_col is None and (lc in {"amount", "amt"} or "amount" in lc):
            amt_col = c
        if bal_col is None and ("balance" in lc):
            bal_col = c

    for _, row in df.iterrows():
        date_raw = row.get(date_col) if date_col else None
        desc = row.get(desc_col) if desc_col else None
        amt_raw = row.get(amt_col) if amt_col else None
        bal_raw = row.get(bal_col) if bal_col else None

        tx_date = _normalize_date_yyyy_mm_dd(date_raw)
        amt = _to_number(amt_raw)
        bal = _to_number(bal_raw)

        if tx_date is None and (desc is None or str(desc).strip() == "") and amt is None:
            continue

        seq += 1
        tx_type = "debit"
        if amt is not None and float(amt) >= 0:
            tx_type = "credit"

        transactions[str(seq)] = {
            "transaction_date": tx_date,
            "description": (str(desc).strip()[:200] if desc is not None and str(desc).strip() else None),
            "amount": amt,
            "type": tx_type,
            "balance": bal,
        }

        if seq >= 5000:
            break

    return transactions


def _save_bank_transactions_to_db(upload_id: int, file_path: str, file_name: str, file_hash: str, transactions: dict):
    """Save bank transactions to bank_transactions table"""
    timestamp = int(time.time())
    bank_file_hash_unique = f"{file_hash}_{timestamp}"
    
    # Generate upload index
    upload_index = _get_next_bank_upload_index_for_hash(file_hash)
    
    # Build JSON payload
    extracted_payload = {
        "base_file_hash": file_hash,
        "upload_index": upload_index,
        "transactions": transactions
    }
    
    # Insert each transaction as a separate row in bank_transactions table
    transaction_ids = []
    
    for seq, transaction in transactions.items():
        try:
            insert_query = """
                INSERT INTO bank_transactions (
                    file_upload_id,
                    transaction_date,
                    description,
                    amount,
                    balance,
                    transaction_type,
                    reference_number,
                    account_number,
                    category,
                    raw_data,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
            """
            
            transaction_id = db_manager.execute_insert(
                insert_query,
                (
                    upload_id,  # file_upload_id
                    transaction.get("transaction_date"),
                    transaction.get("description"),
                    transaction.get("amount"),
                    transaction.get("balance"),
                    transaction.get("type"),
                    None,  # reference_number
                    None,  # account_number
                    None,  # category
                    json.dumps({
                        "file_name": file_name,
                        "file_hash": bank_file_hash_unique,
                        "upload_index": upload_index,
                        "sequence": seq,
                        **transaction
                    }, ensure_ascii=False, default=str)
                ),
            )
            transaction_ids.append(transaction_id)
            
        except Exception as e:
            print(f"Error saving transaction {seq}: {e}")
    
    return transaction_ids, bank_file_hash_unique, upload_index


def register_bank_transaction_routes(app: Flask):
    """Register bank transaction upload routes"""
    
    @app.route("/api/upload-bank-transactions", methods=["POST"])
    def api_upload_bank_transactions():
        """
        Upload bank statement file and store transactions in bank_transactions table
        Similar to invoice upload but for bank transactions
        
        Expected form data:
        - file: uploaded file (PDF, Excel, CSV, or image)
        """
        try:
            if 'file' not in request.files:
                return jsonify({"error": "No file provided"}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No file selected"}), 400
            
            # Validate file
            file_name = secure_filename(file.filename)
            file_ext = os.path.splitext(file_name)[1].lower()
            
            if file_ext not in BANK_ALLOWED_EXTENSIONS:
                return jsonify({
                    "error": f"File type {file_ext} not allowed",
                    "allowed_extensions": list(BANK_ALLOWED_EXTENSIONS)
                }), 400
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > MAX_FILE_SIZE_BYTES:
                return jsonify({
                    "error": f"File size {file_size} exceeds maximum allowed size {MAX_FILE_SIZE_BYTES}"
                }), 400
            
            # Read file content
            file_bytes = file.read()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            
            # Generate unique filename
            timestamp = int(time.time())
            safe_filename = f"{timestamp}_{file_name}"
            file_path = os.path.join(BANK_FOLDER, safe_filename)
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(file_bytes)

            bank_upload_id = db_manager.execute_insert(
                """
                INSERT INTO file_uploads (
                    file_name, file_type, file_size, processing_status, error_message, file_path, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_name,
                    "bank_statement",
                    file_size,
                    "processing",
                    None,
                    file_path,
                    json.dumps({"schema": "hybrid_bank_upload_v1", "status": "processing"}, ensure_ascii=False, default=str),
                ),
            )
            
            # Extract transactions
            if file_ext == ".pdf":
                transactions = _extract_bank_transactions_from_pdf(file_path)
            elif file_ext in {".xlsx", ".xls"}:
                transactions = _extract_bank_transactions_from_excel(file_bytes)
            elif file_ext == ".csv":
                transactions = _extract_bank_transactions_from_csv(file_bytes)
            else:
                # Image files - OCR
                transactions = _extract_bank_transactions_from_pdf(file_path)

            if not transactions:
                db_manager.execute_update(
                    "UPDATE file_uploads SET processing_status = ?, error_message = ? WHERE id = ?",
                    ("failed", "No transactions detected in file", bank_upload_id),
                )
                return jsonify({"error": "No transactions detected in file"}), 400
            
            # Save to database
            transaction_ids, bank_file_hash, upload_index = _save_bank_transactions_to_db(
                bank_upload_id, file_path, file_name, file_hash, transactions
            )
            
            # Calculate totals
            total_transactions = len(transactions)
            total_credits = sum(t.get("amount", 0) for t in transactions.values() if t.get("type") == "credit")
            total_debits = sum(t.get("amount", 0) for t in transactions.values() if t.get("type") == "debit")

            upload_metadata = {
                "schema": "hybrid_bank_upload_v2",
                "base_file_hash": file_hash,
                "upload_index": upload_index,
                "file": {
                    "original_filename": file_name,
                    "stored_path": file_path,
                    "stored_filename": safe_filename,
                    "file_size": file_size,
                    "file_ext": file_ext,
                    "timestamp": timestamp,
                },
                "summary": {
                    "total_transactions": total_transactions,
                    "total_credits": total_credits,
                    "total_debits": total_debits,
                },
                "transactions": transactions,
                "transaction_ids": transaction_ids,
            }

            db_manager.execute_update(
                "UPDATE file_uploads SET processing_status = ?, error_message = ?, metadata = ? WHERE id = ?",
                (
                    "completed",
                    None,
                    json.dumps(upload_metadata, ensure_ascii=False, default=str),
                    bank_upload_id,
                ),
            )
            
            return jsonify({
                "success": True,
                "upload_id": bank_upload_id,
                "transaction_ids": transaction_ids,
                "file_name": file_name,
                "file_size": file_size,
                "bank_file_hash": bank_file_hash,
                "upload_index": upload_index,
                "total_transactions": total_transactions,
                "total_credits": total_credits,
                "total_debits": total_debits,
                "transactions": transactions,
                "message": f"Bank transactions uploaded successfully. {total_transactions} transactions stored in bank_transactions table."
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/upload-bank-transactions: {e}")
            print(error_traceback)
            
            # Clean up file on error
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            
            return jsonify({
                "error": "Internal server error while uploading bank transactions.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500

    @app.route("/api/bank-uploads/<int:upload_id>", methods=["GET"])
    def api_get_bank_upload(upload_id: int):
        try:
            with db_manager.get_connection() as conn:
                cur = conn.cursor()
                upload_row = cur.execute(
                    """
                    SELECT id, file_name, file_type, file_size, upload_time, processing_status, error_message, file_path, metadata
                    FROM file_uploads
                    WHERE id = ? AND file_type = 'bank_statement'
                    """,
                    (upload_id,),
                ).fetchone()
                if not upload_row:
                    return jsonify({"error": "Bank upload not found"}), 404

                tx_rows = cur.execute(
                    """
                    SELECT *
                    FROM bank_transactions
                    WHERE file_upload_id = ?
                    ORDER BY id ASC
                    """,
                    (upload_id,),
                ).fetchall()

            upload_dict = dict(upload_row)
            transactions = [dict(r) for r in tx_rows]

            metadata_raw = upload_dict.get("metadata")
            metadata_obj = None
            if metadata_raw:
                try:
                    metadata_obj = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                except Exception:
                    metadata_obj = metadata_raw
            upload_dict["metadata"] = metadata_obj

            return jsonify({
                "success": True,
                "upload": upload_dict,
                "transactions": transactions,
                "count": len(transactions),
            })
        except Exception as e:
            return jsonify({"error": f"Failed to fetch bank upload: {str(e)}"}), 500
    
    @app.route("/api/bank-transactions", methods=["GET"])
    def api_list_bank_transactions():
        """List all bank transactions"""
        try:
            limit = min(int(request.args.get('limit', 50)), 100)
            offset = int(request.args.get('offset', 0))
            
            query = """
                SELECT id, transaction_date, description, amount, balance, 
                       transaction_type, reference_number, account_number, 
                       category, raw_data, created_at
                FROM bank_transactions
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            
            transactions = db_manager.execute_query(query, (limit, offset))
            
            # Get total count
            count_query = "SELECT COUNT(*) as total FROM bank_transactions"
            total_result = db_manager.execute_query(count_query)
            total = total_result[0]['total'] if total_result else 0
            
            return jsonify({
                "success": True,
                "transactions": transactions,
                "total": total,
                "limit": limit,
                "offset": offset
            })
            
        except Exception as e:
            return jsonify({
                "error": f"Failed to list bank transactions: {str(e)}"
            }), 500
