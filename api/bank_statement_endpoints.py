"""
Bank Statement Extraction API - STRICT Implementation
One file = ONE bank_statement record with ALL transactions in JSON
"""

import os
import sys
import time
import hashlib
import json
import re
from datetime import datetime
from typing import Optional, List, Tuple, Dict
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


def _normalize_date_yyyy_mm_dd(raw: Optional[str]) -> Optional[str]:
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
        "%m/%d/%Y",  # US format (MM/DD/YYYY)
        "%d-%m-%Y",
        "%m-%d-%Y",  # US format with dashes
        "%d/%m/%y",
        "%m/%d/%y",  # US format short year
        "%d-%m-%y",
        "%m-%d-%y",  # US format short year with dashes
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


def _normalize_date_dd_mmm_yyyy(raw: Optional[str]) -> Optional[str]:
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


def _extract_tide_statement_info(text: str) -> dict:
    info: dict = {}
    if not text:
        return info

    t = text
    t_norm = re.sub(r"\s+", " ", t)

    m = re.search(r"Account\s+number\s*[:\-]?\s*(\d{5,})", t, re.IGNORECASE)
    if m:
        info["bank_account_number"] = m.group(1).strip()

    m = re.search(r"Sort\s+code\s*[:\-]?\s*(\d{2}[- ]?\d{2}[- ]?\d{2})", t, re.IGNORECASE)
    if m:
        info["bank_sort_code"] = m.group(1).strip().replace(" ", "")

    m = re.search(r"Statement\s+from\s+(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})\s*[-–]\s*(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})", t_norm, re.IGNORECASE)
    if m:
        info["statement_period_start"] = _normalize_date_dd_mmm_yyyy(m.group(1))
        info["statement_period_end"] = _normalize_date_dd_mmm_yyyy(m.group(2))

    def _money(pat: str) -> Optional[float]:
        mm = re.search(pat, t_norm, re.IGNORECASE)
        if not mm:
            return None
        return _to_number(mm.group(1))

    # Tide headers usually show balances like:
    # Balance on 1 Apr 2024  £3,860.45
    # Balance on 1 May 2024  £317.38
    # We extract all of them and map start->opening, end->closing when possible.
    balance_entries: List[Tuple[Optional[str], Optional[float]]] = []
    for m_bal in re.finditer(
        r"Balance\s+on\s+(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})\s*£?\s*([\d,]+\.\d{2})",
        t_norm,
        re.IGNORECASE,
    ):
        bal_date = _normalize_date_dd_mmm_yyyy(m_bal.group(1))
        bal_amt = _to_number(m_bal.group(2))
        balance_entries.append((bal_date, bal_amt))

    if balance_entries:
        # Prefer statement period mapping if available
        sp = info.get("statement_period_start")
        ep = info.get("statement_period_end")
        opening = None
        closing = None
        if sp:
            for d, a in balance_entries:
                if d == sp and a is not None:
                    opening = a
                    break
        if ep:
            for d, a in balance_entries:
                if d == ep and a is not None:
                    closing = a
                    break
        # Fallback: first is opening, last is closing
        if opening is None:
            opening = balance_entries[0][1]
        if closing is None:
            closing = balance_entries[-1][1]
        info["opening_balance"] = opening
        info["closing_balance"] = closing

    info["statement_total_paid_in"] = _money(r"Total\s+paid\s+in\s*£?\s*([\d,]+\.\d{2})")
    info["statement_total_paid_out"] = _money(r"Total\s+paid\s+out\s*£?\s*([\d,]+\.\d{2})")

    m = re.search(r"Business\s+Owner\s*[:\-]?\s*([A-Za-z0-9 &'\-\.]+)", t_norm, re.IGNORECASE)
    if m:
        info["business_owner"] = m.group(1).strip()
    m = re.search(r"Address\s*[:\-]?\s*([A-Za-z0-9,\.\-\s]{10,})", t, re.IGNORECASE)
    if m:
        info["business_address"] = re.sub(r"\s+", " ", m.group(1)).strip()

    return info


def _parse_tide_transaction_lines(lines: List[str]) -> Dict:
    transactions: dict = {}
    seq = 0

    for raw_line in lines:
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        dm = re.match(r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(.*)$", line)
        if not dm:
            continue

        tx_date = _normalize_date_dd_mmm_yyyy(dm.group(1))
        rest = dm.group(2).strip()

        money_vals = re.findall(r"(\d{1,3}(?:,\d{3})*\.\d{2})", rest)
        if not money_vals:
            continue
        nums = [_to_number(v) for v in money_vals]
        nums = [n for n in nums if n is not None]
        if not nums:
            continue

        balance = nums[-1] if len(nums) >= 1 else None
        paid_in = None
        paid_out = None

        if len(nums) >= 3:
            paid_in = nums[-3]
            paid_out = nums[-2]
        elif len(nums) == 2:
            # Can't always disambiguate; infer from text hints
            hint = rest.lower()
            if "debit" in hint or "paid out" in hint:
                paid_out = nums[-2]
            else:
                paid_in = nums[-2]

        # Keep the canonical 'amount' positive (like the Tide table)
        # and use 'type' = credit/debit.
        tx_dir = None
        amount = None
        if paid_in is not None and paid_in != 0:
            tx_dir = "credit"
            amount = abs(paid_in)
        elif paid_out is not None and paid_out != 0:
            tx_dir = "debit"
            amount = abs(paid_out)

        rest_wo_money = re.sub(r"\d{1,3}(?:,\d{3})*\.\d{2}", " ", rest).strip()
        rest_wo_money = re.sub(r"\s+", " ", rest_wo_money)

        tx_type = None
        details = rest_wo_money
        # Common Tide types: Domestic Transfer / Direct Debit / Card Transaction
        for candidate in ["Domestic Transfer", "Direct Debit", "Card Transaction", "Card Transaction "]:
            if rest_wo_money.lower().startswith(candidate.lower()):
                tx_type = candidate.strip()
                details = rest_wo_money[len(candidate):].strip(" -")
                break

        if not tx_type:
            # Take first token chunk as type if it looks like Title Case words
            parts = rest_wo_money.split(" ")
            if len(parts) >= 2:
                tx_type = " ".join(parts[:2])
                details = " ".join(parts[2:]).strip()

        seq += 1
        transactions[str(seq)] = {
            "transaction_date": tx_date,
            "transaction_type": tx_type,
            "description": details[:500] if details else None,
            "paid_in": paid_in,
            "paid_out": paid_out,
            "amount": amount,
            "type": tx_dir,
            "balance": balance,
        }

        if seq >= 75000:
            break

    return transactions


def _get_next_statement_index_for_hash(base_file_hash: str) -> int:
    """Get next statement index for file hash"""
    try:
        rows = db_manager.execute_query(
            """
            SELECT
                MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(extracted_data, '$.statement_index')) AS UNSIGNED)) AS max_idx
            FROM reconciliations
            WHERE source_file_hash LIKE ?
            """,
            (f"{base_file_hash}_%",),
        )
        if rows and rows[0] and rows[0].get("max_idx") is not None:
            return int(rows[0]["max_idx"]) + 1
    except Exception:
        pass
    return 1


def _extract_invoice_data_from_text(text: str) -> dict:
    """Extract invoice-like data from bank statement text"""
    invoice_data = {}
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Look for invoice numbers in descriptions
    invoice_patterns = [
        r'inv(?:\s*)#?\s*(\w+)',
        r'invoice\s*(?:no|#)?\s*[:\s]*(\w+)',
        r'bill\s*(?:no|#)?\s*[:\s]*(\w+)',
        r'ref\s*[:\s]*(\w+)',
    ]
    
    # Look for vendor names
    vendor_patterns = [
        r'paid\s+to\s+([A-Za-z0-9\s&]+)',
        r'transfer\s+to\s+([A-Za-z0-9\s&]+)',
        r'debit\s+([A-Za-z0-9\s&]+)',
    ]
    
    seq = 0
    for line in lines:
        # Extract invoice numbers
        for pattern in invoice_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                seq += 1
                invoice_data[str(seq)] = {
                    "invoice_number": match.group(1),
                    "description": line[:200],
                    "extracted_from": "bank_statement"
                }
                break
    
    return invoice_data


def _extract_transactions_from_pdf(file_path: str) -> dict:
    """Extract transactions from PDF using OCR"""
    from PyPDF2 import PdfReader
    from PIL import Image
    import pytesseract
    
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
        
        # Extract invoice data first
        invoice_data = _extract_invoice_data_from_text(text)

        statement_info = _extract_tide_statement_info(text)
        
        # Parse transactions from text
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        tide_tx = _parse_tide_transaction_lines(lines)
        if tide_tx:
            transactions = tide_tx
        else:
            # Fallback parser (older format)
            seq = 0
            for line in lines:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', line)
                if date_match:
                    amount_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*$', line)
                    if not amount_match:
                        remaining_text = line[date_match.end():]
                        amount_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', remaining_text)
                if date_match and amount_match:
                    seq += 1
                    transaction_date = _normalize_date_yyyy_mm_dd(date_match.group(1))
                    amount = _to_number(amount_match.group(1))
                    transaction_type = "debit"
                    if any(word in line.lower() for word in ['credit', 'deposit', 'received', 'in']):
                        transaction_type = "credit"
                    elif any(word in line.lower() for word in ['debit', 'withdraw', 'payment', 'out']):
                        transaction_type = "debit"
                    description = line
                    description = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', '', description).strip()
                    description = re.sub(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?', '', description).strip()
                    description = description[:200] if description else None
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
                    if seq >= 75000:
                        break
    
    except Exception as e:
        print(f"Error extracting from PDF: {e}")
    
    # Return both transactions and invoice data
    return {
        "transactions": transactions,
        "invoice_data": invoice_data,
        "statement_info": statement_info if 'statement_info' in locals() else {}
    }


def _extract_transactions_from_excel(file_path: str) -> dict:
    """Extract transactions from Excel file"""
    import pandas as pd
    
    transactions = {}
    invoice_data = {}
    
    try:
        df = pd.read_excel(file_path)
        
        # Auto-detect columns
        date_col = None
        desc_col = None
        amount_col = None
        balance_col = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            if date_col is None and any(x in col_lower for x in ['date', 'transaction date', 'value date']):
                date_col = col
            elif desc_col is None and any(x in col_lower for x in ['description', 'particulars', 'narration', 'details']):
                desc_col = col
            elif amount_col is None and any(x in col_lower for x in ['amount', 'debit', 'credit', 'value']):
                amount_col = col
            elif balance_col is None and any(x in col_lower for x in ['balance', 'running balance']):
                balance_col = col
        
        seq = 0
        for _, row in df.iterrows():
            seq += 1
            if seq > 75000:  # Limit to 75000 transactions
                break
            
            transaction_date = None
            if date_col and pd.notna(row.get(date_col)):
                transaction_date = _normalize_date_yyyy_mm_dd(str(row[date_col]))
            
            description = None
            if desc_col and pd.notna(row.get(desc_col)):
                description = str(row[desc_col])[:200]
            
            amount = None
            transaction_type = "debit"
            if amount_col and pd.notna(row.get(amount_col)):
                amount_val = _to_number(row[amount_col])
                if amount_val is not None:
                    if 'credit' in str(amount_col).lower() or amount_val > 0:
                        transaction_type = "credit"
                    elif 'debit' in str(amount_col).lower() or amount_val < 0:
                        transaction_type = "debit"
                    amount = abs(amount_val)
            
            balance = None
            if balance_col and pd.notna(row.get(balance_col)):
                balance = _to_number(row[balance_col])
            
            if transaction_date or description or amount:
                transactions[str(seq)] = {
                    "transaction_date": transaction_date,
                    "description": description,
                    "amount": amount,
                    "type": transaction_type,
                    "balance": balance
                }
        
        # Extract invoice data from descriptions
        if desc_col:
            for _, row in df.iterrows():
                if pd.notna(row.get(desc_col)):
                    text = str(row[desc_col])
                    invoice_matches = _extract_invoice_data_from_text(text)
                    if invoice_matches:
                        invoice_data.update(invoice_matches)
    
    except Exception as e:
        print(f"Error parsing Excel file: {e}")
    
    return {
        "transactions": transactions,
        "invoice_data": invoice_data
    }


def _extract_transactions_from_csv(file_path: str) -> dict:
    """Extract transactions from CSV file"""
    import pandas as pd
    
    transactions = {}
    invoice_data = {}
    
    try:
        df = pd.read_csv(file_path)
        
        # Auto-detect columns (same logic as Excel)
        date_col = None
        desc_col = None
        amount_col = None
        balance_col = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            if date_col is None and any(x in col_lower for x in ['date', 'transaction date', 'value date']):
                date_col = col
            elif desc_col is None and any(x in col_lower for x in ['description', 'particulars', 'narration', 'details']):
                desc_col = col
            elif amount_col is None and any(x in col_lower for x in ['amount', 'debit', 'credit', 'value']):
                amount_col = col
            elif balance_col is None and any(x in col_lower for x in ['balance', 'running balance']):
                balance_col = col
        
        seq = 0
        for _, row in df.iterrows():
            seq += 1
            if seq > 75000:  # Limit to 75000 transactions
                break
            
            transaction_date = None
            if date_col and pd.notna(row.get(date_col)):
                transaction_date = _normalize_date_yyyy_mm_dd(str(row[date_col]))
            
            description = None
            if desc_col and pd.notna(row.get(desc_col)):
                description = str(row[desc_col])[:200]
            
            amount = None
            transaction_type = "debit"
            if amount_col and pd.notna(row.get(amount_col)):
                amount_val = _to_number(row[amount_col])
                if amount_val is not None:
                    if 'credit' in str(amount_col).lower() or amount_val > 0:
                        transaction_type = "credit"
                    elif 'debit' in str(amount_col).lower() or amount_val < 0:
                        transaction_type = "debit"
                    amount = abs(amount_val)
            
            balance = None
            if balance_col and pd.notna(row.get(balance_col)):
                balance = _to_number(row[balance_col])
            
            if transaction_date or description or amount:
                transactions[str(seq)] = {
                    "transaction_date": transaction_date,
                    "description": description,
                    "amount": amount,
                    "type": transaction_type,
                    "balance": balance
                }
        
        # Extract invoice data from descriptions
        if desc_col:
            for _, row in df.iterrows():
                if pd.notna(row.get(desc_col)):
                    text = str(row[desc_col])
                    invoice_matches = _extract_invoice_data_from_text(text)
                    if invoice_matches:
                        invoice_data.update(invoice_matches)
    
    except Exception as e:
        print(f"Error parsing CSV file: {e}")
    
    return {
        "transactions": transactions,
        "invoice_data": invoice_data
    }


def _extract_transactions_from_image(file_path: str) -> dict:
    """Extract transactions from image using OCR"""
    from PIL import Image
    import pytesseract
    
    transactions = {}
    invoice_data = {}
    
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Extract invoice data first
        invoice_data = _extract_invoice_data_from_text(text)

        statement_info = _extract_tide_statement_info(text)

        tide_tx = _parse_tide_transaction_lines(lines)
        if tide_tx:
            transactions = tide_tx
        else:
            # Fallback legacy parser
            seq = 0
            for line in lines:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', line)
                amount_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', line)
                if date_match and amount_match:
                    seq += 1
                    transaction_date = _normalize_date_yyyy_mm_dd(date_match.group(1))
                    amount = _to_number(amount_match.group(1))
                    transaction_type = "debit" if any(word in line.lower() for word in ['debit', 'withdraw', 'payment']) else "credit"
                    description = line
                    description = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', '', description).strip()
                    description = re.sub(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?', '', description).strip()
                    description = description[:200] if description else None
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
                    if seq >= 75000:
                        break
    
    except Exception as e:
        print(f"Error processing image file: {e}")
    
    return {
        "transactions": transactions,
        "invoice_data": invoice_data,
        "statement_info": statement_info if 'statement_info' in locals() else {}
    }


def register_bank_statement_routes(app: Flask):
    """Register bank statement upload routes - STRICT Implementation"""
    
    @app.route("/api/upload-bank-statement", methods=["POST"])
    def api_upload_bank_statement():
        """
        Upload bank statement file - STRICT: One file = ONE bank_statement record
        All transactions stored in single JSON object in bank_statements table
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
            
            # Generate unique filename and hash
            timestamp = int(time.time())
            statement_file_hash_unique = f"{file_hash}_{timestamp}"
            safe_filename = f"{timestamp}_{file_name}"
            file_path = os.path.join(BANK_FOLDER, safe_filename)
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            
            # Extract transactions based on file type
            if file_ext == ".pdf":
                extraction_result = _extract_transactions_from_pdf(file_path)
            elif file_ext in {".xlsx", ".xls"}:
                extraction_result = _extract_transactions_from_excel(file_path)
            elif file_ext == ".csv":
                extraction_result = _extract_transactions_from_csv(file_path)
            else:
                # Image files - OCR
                extraction_result = _extract_transactions_from_image(file_path)
            
            # STRICT JSON FORMAT: Store bank statement data in exact format requested
            # Get next index for this file (same file re-upload → new index)
            def _get_next_index_for_file_hash(file_hash: str) -> int:
                """Get next index for file hash (same file re-upload → new index)"""
                try:
                    # Check existing uploads for this file hash
                    existing = db_manager.execute_query(
                        "SELECT COUNT(*) as count FROM reconciliations WHERE source_file_hash LIKE ?",
                        (f"{file_hash}_%",)
                    )
                    if existing and existing[0]:
                        return existing[0]["count"] + 1
                    return 1
                except Exception:
                    return 1

            def _to_float(val):
                try:
                    if val is None or val == "":
                        return None
                    return float(val)
                except Exception:
                    return None

            next_index = _get_next_index_for_file_hash(file_hash)
            
            # Extract transactions + statement header info from result
            transactions = extraction_result.get("transactions", {})
            statement_info = extraction_result.get("statement_info", {})
            
            # Create STRICT JSON format with 1->1, 1->2, 1->3 format
            strict_json_format = {
                "statements": {
                    "1": {
                        "statement_info": statement_info,
                        "transactions": {}
                    }
                }
            }
            
            # Add all transactions with 1->1, 1->2, 1->3 format
            transaction_counter = 1
            for seq, transaction in transactions.items():
                strict_json_format["statements"]["1"]["transactions"][str(transaction_counter)] = {
                    "transaction_date": transaction.get("transaction_date"),
                    "transaction_type": transaction.get("transaction_type") or transaction.get("type"),
                    "description": transaction.get("description"),
                    "paid_in": _to_float(transaction.get("paid_in")),
                    "paid_out": _to_float(transaction.get("paid_out")),
                    "amount": _to_float(transaction.get("amount", 0)),
                    "type": transaction.get("type", "credit" if transaction.get("amount", 0) > 0 else "debit"),
                    "balance": transaction.get("balance")
                }
                transaction_counter += 1
            
            # Calculate totals for display
            total_transactions = len(transactions)
            total_credits = sum(t.get("amount", 0) for t in transactions.values() if t.get("type") == "credit")
            total_debits = sum(t.get("amount", 0) for t in transactions.values() if t.get("type") == "debit")
            
            # Store extracted data ONLY in reconciliations table (one row per transaction)
            insert_query = """
                INSERT INTO reconciliations (
                    name,
                    description,
                    reconciliation_date,
                    status,
                    total_invoices,
                    total_transactions,
                    total_matches,
                    total_amount_matched,
                    date_started_utc,
                    date_ended_utc,
                    date_utc,
                    external_id,
                    type,
                    bank_description,
                    reference,
                    payer,
                    card_number,
                    orig_currency,
                    orig_amount,
                    amount,
                    fee,
                    balance,
                    paid_in,
                    paid_out,
                    account,
                    beneficiary,
                    bic,
                    raw_json,
                    source_file_name,
                    source_file_hash
                    ,bank_account_number,
                    bank_sort_code,
                    statement_period_start,
                    statement_period_end,
                    opening_balance,
                    closing_balance,
                    statement_total_paid_in,
                    statement_total_paid_out,
                    business_owner,
                    business_address
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """

            stored_ids: List[int] = []
            try:
                transaction_counter = 1
                for _, transaction in transactions.items():
                    tx_date = transaction.get("transaction_date")
                    try:
                        # tx_date is typically YYYY-MM-DD; store as DATETIME with midnight
                        date_utc = f"{tx_date} 00:00:00" if tx_date else None
                    except Exception:
                        date_utc = None

                    tx_desc = transaction.get("description")
                    tx_amount = _to_float(transaction.get("amount"))
                    tx_type = transaction.get("transaction_type") or transaction.get("type")
                    tx_paid_in = _to_float(transaction.get("paid_in"))
                    tx_paid_out = _to_float(transaction.get("paid_out"))

                    statement_label = f"Bank Statement Upload: {file_name}"
                    tx_name = f"{statement_label} - TX {transaction_counter}"

                    rec_id = db_manager.execute_insert(
                        insert_query,
                        (
                            tx_name,
                            statement_label,
                            datetime.utcnow().date().isoformat(),
                            "completed",
                            0,
                            1,
                            0,
                            0,
                            None,
                            None,
                            date_utc,
                            None,
                            tx_type,
                            tx_desc,
                            None,
                            None,
                            None,
                            None,
                            None,
                            tx_amount,
                            None,
                            transaction.get("balance"),
                            tx_paid_in,
                            tx_paid_out,
                            None,
                            None,
                            None,
                            json.dumps(strict_json_format, ensure_ascii=False, default=str),
                            file_name,
                            bank_statement_file_hash_unique,
                            statement_info.get("bank_account_number"),
                            statement_info.get("bank_sort_code"),
                            statement_info.get("statement_period_start"),
                            statement_info.get("statement_period_end"),
                            statement_info.get("opening_balance"),
                            statement_info.get("closing_balance"),
                            statement_info.get("statement_total_paid_in"),
                            statement_info.get("statement_total_paid_out"),
                            statement_info.get("business_owner"),
                            statement_info.get("business_address"),
                        ),
                    )
                    stored_ids.append(int(rec_id))
                    transaction_counter += 1
            except Exception as e:
                print(f"Database insert error: {e}")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({"error": f"Database error: {str(e)}"}), 409
            
            # Return STRICT JSON format
            return jsonify({
                "success": True,
                "reconciliation_ids": stored_ids,
                "file_name": file_name,
                "file_size": file_size,
                "statement_file_hash": bank_statement_file_hash_unique,
                "total_transactions": total_transactions,
                "total_credits": total_credits,
                "total_debits": total_debits,
                "data": strict_json_format,  # STRICT JSON format
                "message": "Bank statement uploaded successfully. Stored in reconciliations table."
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/upload-bank-statement: {e}")
            print(error_traceback)
            
            # Clean up file on error
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            
            return jsonify({
                "error": "Internal server error while uploading bank statement.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    @app.route("/api/bank-statements", methods=["GET"])
    def api_list_bank_statements():
        """List all bank statements"""
        try:
            limit = min(int(request.args.get('limit', 50)), 100)
            offset = int(request.args.get('offset', 0))
            
            query = """
                SELECT id,
                       source_file_hash AS statement_file_hash,
                       source_file_name AS statement_file_name,
                       date_utc,
                       type,
                       bank_description,
                       reference,
                       amount,
                       fee,
                       balance,
                       created_at,
                       updated_at
                FROM reconciliations
                WHERE source_file_hash IS NOT NULL
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            
            statements = db_manager.execute_query(query, (limit, offset))
            
            # Get total count
            count_query = "SELECT COUNT(*) as total FROM reconciliations WHERE source_file_hash IS NOT NULL"
            total_result = db_manager.execute_query(count_query)
            total = total_result[0]['total'] if total_result else 0
            
            return jsonify({
                "success": True,
                "statements": statements,
                "total": total,
                "limit": limit,
                "offset": offset
            })
            
        except Exception as e:
            return jsonify({
                "error": f"Failed to list bank statements: {str(e)}"
            }), 500
