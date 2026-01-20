"""
Enhanced API Endpoints for Multi-Invoice File Processing
Provides new endpoints for uploading and processing files with multiple invoices
"""

import os
import sys
import time
import hashlib
import json
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import traceback

# Add project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import (
    UPLOAD_FOLDER, INVOICE_FOLDER, MAX_FILE_SIZE_BYTES, 
    MAX_TOTAL_SIZE_BYTES, INVOICE_ALLOWED_EXTENSIONS, INVOICE_ALLOWED_MIMETYPES,
    RATE_LIMITS, DB_TYPE
)
from database_manager import db_manager



def _normalize_date_yyyy_mm_dd(raw: str | None) -> str | None:
    if not raw:
        return None
    txt = str(raw).strip()
    if not txt:
        return None

    # Normalize separators/spaces
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


def _to_number(val):
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


def _split_invoice_sections(lines: list[str]) -> list[list[str]]:
    if not lines:
        return []
    joined = "\n".join(lines)
    markers = [
        r"\bTAX\s+INVOICE\b",
        r"\bVAT\s+INVOICE\b",
        r"\bPAYMENT\s+ADVICE\b",
        r"\bINVOICE\b",
    ]
    hits: list[int] = []
    for m in re.finditer("|".join(markers), joined, flags=re.IGNORECASE):
        hits.append(m.start())
    if len(hits) <= 1:
        return [lines]

    sections: list[list[str]] = []
    hits_sorted = sorted(set(hits))
    for i, start in enumerate(hits_sorted):
        end = hits_sorted[i + 1] if i + 1 < len(hits_sorted) else len(joined)
        block = joined[start:end]
        block_lines = [re.sub(r"\s+", " ", (ln or "")).strip() for ln in block.splitlines()]
        block_lines = [ln for ln in block_lines if ln]
        if block_lines:
            sections.append(block_lines)

    return sections or [lines]


def _extract_invoices_structured(file_path: str, file_ext: str, original_filename: str) -> list[dict]:
    if file_ext != ".pdf":
        return [_extract_invoice_structured(file_path, file_ext)]

    from services.multi_invoice_processor import multi_invoice_processor
    from PyPDF2 import PdfReader
    invoices: list[dict] = []
    try:
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            for page_num, page in enumerate(reader.pages, start=1):
                text = ""
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                lines = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]
                if not lines:
                    continue

                for section_lines in _split_invoice_sections(lines):
                    section_text = "\n".join(section_lines)
                    inv = None
                    try:
                        inv = multi_invoice_processor._extract_invoice_from_text(section_text, page_num, original_filename)
                    except Exception:
                        inv = None

                    if not inv:
                        continue

                    upload_obj = {
                        "invoice_date": _normalize_date_yyyy_mm_dd(getattr(inv, "invoice_date", None)),
                        "due_date": _normalize_date_yyyy_mm_dd(getattr(inv, "due_date", None)),
                        "total_amount": _to_number(getattr(inv, "total_amount", None)),
                        "invoice_number": getattr(inv, "invoice_number", None),
                        "reference": getattr(inv, "reference", None),
                        "vendor_name": getattr(inv, "vendor_name", None),
                        "tax_amount": _to_number(getattr(inv, "tax_total", None)),
                        "vat_number": getattr(inv, "vat_number", None),
                        "total_vat_rate": _to_number(getattr(inv, "total_vat_rate", None)),
                        "total_zero_rated": _to_number(getattr(inv, "total_zero_rated", None)),
                        "total_gbp": _to_number(getattr(inv, "total_gbp", None)),
                        "bank_name": getattr(inv, "bank_name", None),
                        "account_number": getattr(inv, "account_number", None),
                        "sort_code": getattr(inv, "sort_code", None),
                        "iban": getattr(inv, "iban", None),
                        "bic": getattr(inv, "bic", None),
                        "account_name": getattr(inv, "account_name", None),
                        "description": None,
                        "items": {},
                        "page_no": page_num,
                    }

                    desc_parts = []
                    if upload_obj.get("vendor_name"):
                        desc_parts.append(f"Vendor: {upload_obj['vendor_name']}")
                    if upload_obj.get("invoice_number"):
                        desc_parts.append(f"Invoice: {upload_obj['invoice_number']}")
                    if upload_obj.get("invoice_date"):
                        desc_parts.append(f"Date: {upload_obj['invoice_date']}")
                    upload_obj["description"] = " | ".join(desc_parts) if desc_parts else None

                    items: dict[str, dict] = {}
                    seq = 0
                    for li in (getattr(inv, "line_items", None) or []):
                        seq += 1
                        items[str(seq)] = {
                            "description": (getattr(li, "description", None) or "") or None,
                            "amount": _to_number(getattr(li, "total_amount", None)),
                        }
                    upload_obj["items"] = items
                    invoices.append(upload_obj)
    except Exception:
        return []

    return invoices


def _get_next_upload_index_for_hash(base_file_hash: str) -> int:
    # Find max upload_index across all invoice rows for the same original file hash
    # (stored inside extracted_data JSON).
    try:
        rows = db_manager.execute_query(
            """
            SELECT
                MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(extracted_data, '$.upload_index')) AS UNSIGNED)) AS max_idx
            FROM invoices
            WHERE JSON_UNQUOTE(JSON_EXTRACT(extracted_data, '$.base_file_hash')) = ?
            """,
            (base_file_hash,),
        )
        if rows and rows[0] and rows[0].get("max_idx") is not None:
            return int(rows[0]["max_idx"]) + 1
    except Exception:
        pass
    return 1


def _get_next_upload_index_for_hash(file_hash: str) -> int:
    """Get next upload index for file hash (same file re-upload → new index)"""
    try:
        # Check existing uploads for this file hash
        existing = db_manager.execute_query(
            "SELECT COUNT(*) as count FROM invoices WHERE invoice_file_hash LIKE ?",
            (f"{file_hash}_%",)
        )
        if existing and existing[0]:
            return existing[0]["count"] + 1
        return 1
    except Exception:
        return 1


def _extract_invoice_structured(file_path: str, file_ext: str) -> dict:
    """Best-effort extraction into the required JSON schema."""
    extracted_invoice_date: str | None = None
    extracted_due_date: str | None = None
    extracted_total_amount: float | None = None
    extracted_invoice_number: str | None = None
    extracted_reference: str | None = None
    extracted_vendor_name: str | None = None
    extracted_tax_amount: float | None = None
    extracted_vat_number: str | None = None
    extracted_total_vat_rate: float | None = None
    extracted_total_zero_rated: float | None = None
    extracted_total_gbp: float | None = None
    extracted_description: str | None = None
    items: dict[str, dict] = {}

    # Use existing heuristic extractor from multi_invoice_processor for text parsing.
    from services.multi_invoice_processor import multi_invoice_processor
    from PyPDF2 import PdfReader
    from PIL import Image
    import pytesseract

    # Excel is supported for upload, but this endpoint stores a single invoice JSON.
    # If you need multi-row Excel parsing into line items, we need to extend this.
    if file_ext in {".xlsx", ".xls"}:
        return {
            "invoice_date": None,
            "due_date": None,
            "total_amount": None,
            "invoice_number": None,
            "vendor_name": None,
            "tax_amount": None,
            "description": None,
            "items": {},
        }

    text = ""
    if file_ext == ".pdf":
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
    else:
        # image types
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
        except Exception:
            text = ""

    inv = None
    try:
        inv = multi_invoice_processor._extract_invoice_from_text(text, 1, os.path.basename(file_path))
    except Exception:
        inv = None

    if inv:
        extracted_invoice_date = _normalize_date_yyyy_mm_dd(inv.invoice_date)
        extracted_due_date = _normalize_date_yyyy_mm_dd(inv.due_date)
        extracted_total_amount = _to_number(inv.total_amount)
        extracted_invoice_number = getattr(inv, 'invoice_number', None)
        extracted_reference = getattr(inv, 'reference', None)
        extracted_vendor_name = getattr(inv, 'vendor_name', None)
        extracted_tax_amount = _to_number(getattr(inv, 'tax_total', None))
        extracted_vat_number = getattr(inv, 'vat_number', None)
        extracted_total_vat_rate = _to_number(getattr(inv, 'total_vat_rate', None))
        extracted_total_zero_rated = _to_number(getattr(inv, 'total_zero_rated', None))
        extracted_total_gbp = _to_number(getattr(inv, 'total_gbp', None))
        
        # Create description from vendor and basic info
        desc_parts = []
        if extracted_vendor_name:
            desc_parts.append(f"Vendor: {extracted_vendor_name}")
        if extracted_invoice_number:
            desc_parts.append(f"Invoice: {extracted_invoice_number}")
        if extracted_invoice_date:
            desc_parts.append(f"Date: {extracted_invoice_date}")
        
        # Append line items to description for better matching
        if getattr(inv, "line_items", None):
            item_descs = [li.description for li in inv.line_items if li.description]
            if item_descs:
                # Limit to 5 items to keep it readable, and truncate very long individual descriptions
                clean_items = [d[:30] + "..." if len(d) > 30 else d for d in item_descs]
                desc_parts.append(f"Includes: {', '.join(clean_items[:5])}")

        extracted_description = " | ".join(desc_parts) if desc_parts else None

        seq = 0
        for li in (inv.line_items or []):
            seq += 1
            desc = (getattr(li, "description", None) or "")
            amt = _to_number(getattr(li, "total_amount", None))
            items[str(seq)] = {
                "description": desc if desc else None,
                "amount": amt,
            }

    upload_obj = {
        "invoice_date": extracted_invoice_date,
        "due_date": extracted_due_date,
        "total_amount": extracted_total_amount,
        "invoice_number": extracted_invoice_number,
        "reference": extracted_reference,
        "vendor_name": extracted_vendor_name,
        "tax_amount": extracted_tax_amount,
        "vat_number": extracted_vat_number,
        "total_vat_rate": extracted_total_vat_rate,
        "total_zero_rated": extracted_total_zero_rated,
        "total_gbp": extracted_total_gbp,
        "bank_name": getattr(inv, "bank_name", None),
        "account_number": getattr(inv, "account_number", None),
        "sort_code": getattr(inv, "sort_code", None),
        "iban": getattr(inv, "iban", None),
        "bic": getattr(inv, "bic", None),
        "account_name": getattr(inv, "account_name", None),
        "description": extracted_description,
        "items": items,
    }

    return upload_obj




def register_multi_invoice_routes(app: Flask):
    """Register enhanced API routes for multi-invoice processing"""
    
    @app.route("/api/upload-invoice-file", methods=["POST"])
    def api_upload_invoice_file():
        """
        Upload a file containing multiple invoices.
        Creates a single parent record and processes all invoices within the file.
        
        Expected form data:
        - file: uploaded file (PDF, Excel, or image)
        - description: optional description of the file
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
            
            if file_ext not in INVOICE_ALLOWED_EXTENSIONS:
                return jsonify({
                    "error": f"File type {file_ext} not allowed",
                    "allowed_extensions": list(INVOICE_ALLOWED_EXTENSIONS)
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
            file_path = os.path.join(INVOICE_FOLDER, safe_filename)
            
            # Save file
            os.makedirs(INVOICE_FOLDER, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(file_bytes)

            # Build required JSON payload (schema enforced)
            upload_index = _get_next_upload_index_for_hash(file_hash)
            invoice_upload_id = db_manager.execute_insert(
                """
                INSERT INTO file_uploads (
                    file_name, file_type, file_size, processing_status, error_message, file_path, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    file_name,
                    "invoice",
                    file_size,
                    "processing",
                    None,
                    file_path,
                    json.dumps({"schema": "hybrid_invoice_upload_v1", "status": "processing"}, ensure_ascii=False, default=str),
                ),
            )

            invoice_objs = _extract_invoices_structured(file_path, file_ext, file_name)
            if not invoice_objs:
                db_manager.execute_update(
                    "UPDATE file_uploads SET processing_status = ?, error_message = ? WHERE id = ?",
                    ("failed", "No invoices detected in file", invoice_upload_id),
                )
                return jsonify({"error": "No invoices detected in file"}), 400

            extracted_payload = {
                "base_file_hash": file_hash,
                "upload_index": upload_index,
                "uploads": {str(i + 1): obj for i, obj in enumerate(invoice_objs)},
            }

            invoice_number = request.form.get('invoice_number')
            invoice_date = request.form.get('invoice_date')
            due_date = request.form.get('due_date')
            vendor_name = request.form.get('vendor_name')
            total_amount = request.form.get('total_amount')
            tax_amount = request.form.get('tax_amount')
            description = request.form.get('description', '')

            def _to_float(val):
                try:
                    if val is None or val == "":
                        return None
                    return float(val)
                except Exception:
                    return None

            def _get_next_index_for_file_hash(file_hash: str) -> int:
                """Get next index for file hash (same file re-upload → new index)"""
                try:
                    # Check existing uploads for this file hash
                    existing = db_manager.execute_query(
                        "SELECT COUNT(*) as count FROM invoices WHERE invoice_file_hash LIKE ?",
                        (f"{file_hash}_%",)
                    )
                    if existing and existing[0]:
                        return existing[0]["count"] + 1
                    return 1
                except Exception:
                    return 1

            # IMPORTANT: allow re-uploads by ensuring invoice_file_hash is unique per upload
            invoice_file_hash_unique = f"{file_hash}_{timestamp}"

            # INDEXED JSON STRUCTURE: Extract invoice data in indexed format
            # Get next index for this file (same file re-upload → new index)
            next_index = _get_next_index_for_file_hash(file_hash)
            
            invoice_ids: list[int] = []
            extracted_invoices_for_metadata: list[dict] = []

            insert_query = """
                INSERT INTO invoices (
                    file_upload_id,
                    invoice_number,
                    invoice_date,
                    reference,
                    vendor_name,
                    vat_number,
                    invoice_file_path,
                    invoice_file_hash,
                    bank_name,
                    account_name,
                    account_number,
                    sort_code,
                    iban,
                    bic
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            try:
                for idx, upload_obj in enumerate(invoice_objs, start=1):
                    invoice_date_extracted = upload_obj.get("invoice_date")
                    due_date_extracted = upload_obj.get("due_date")
                    description_extracted = upload_obj.get("description", "")
                    total_amount_extracted = _to_float(upload_obj.get("total_amount"))

                    items = upload_obj.get("items", {})
                    indexed_items = {}
                    item_index = 1
                    if isinstance(items, dict):
                        for _, item in items.items():
                            if isinstance(item, dict):
                                indexed_items[str(item_index)] = {
                                    "description": item.get("description", ""),
                                    "amount": _to_float(item.get("amount", 0)),
                                }
                                item_index += 1
                    elif isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                indexed_items[str(item_index)] = {
                                    "description": item.get("description", ""),
                                    "amount": _to_float(item.get("amount", 0)),
                                }
                                item_index += 1

                    exact_json_format = {
                        "uploads": {
                            str(idx): {
                                "invoice_date": invoice_date_extracted,
                                "due_date": due_date_extracted,
                                "total_amount": total_amount_extracted if total_amount_extracted is not None else 0,
                                "items": indexed_items,
                                "page_no": upload_obj.get("page_no"),
                            }
                        }
                    }

                    inv_hash_unique = f"{file_hash}_{timestamp}_{idx}"

                    invoice_id = db_manager.execute_insert(
                        insert_query,
                        (
                            invoice_upload_id,
                            invoice_number or upload_obj.get("invoice_number"),
                            invoice_date or invoice_date_extracted,
                            upload_obj.get("reference"),
                            vendor_name or upload_obj.get("vendor_name"),
                            upload_obj.get("vat_number"),
                            total_amount_extracted,
                            _to_float(upload_obj.get("tax_amount")),
                            _to_float(upload_obj.get("total_vat_rate")),
                            _to_float(upload_obj.get("total_zero_rated")),
                            _to_float(upload_obj.get("total_gbp")) or total_amount_extracted,
                            total_amount_extracted,
                            due_date or due_date_extracted,
                            (description or description_extracted),
                            json.dumps(indexed_items, ensure_ascii=False, default=str),
                            json.dumps(exact_json_format, ensure_ascii=False, default=str),
                            0.85 if total_amount_extracted else 0.0,
                            "completed",
                            file_path,
                            inv_hash_unique,
                            upload_obj.get("bank_name"),
                            upload_obj.get("account_name"),
                            upload_obj.get("account_number"),
                            upload_obj.get("sort_code"),
                            upload_obj.get("iban"),
                            upload_obj.get("bic")
                        ),
                    )
                    invoice_ids.append(int(invoice_id))
                    extracted_invoices_for_metadata.append({
                        **upload_obj,
                        "invoice_db_id": int(invoice_id),
                        "invoice_file_hash": inv_hash_unique,
                    })

                upload_metadata = {
                    "schema": "hybrid_invoice_upload_v2",
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
                    "extracted_payload": extracted_payload,
                    "invoices": extracted_invoices_for_metadata,
                }

                db_manager.execute_update(
                    "UPDATE file_uploads SET processing_status = ?, error_message = ?, metadata = ? WHERE id = ?",
                    (
                        "completed",
                        None,
                        json.dumps(upload_metadata, ensure_ascii=False, default=str),
                        invoice_upload_id,
                    ),
                )
            except Exception as e:
                # Clean up file if DB insert fails (or duplicate hash)
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({"error": str(e)}), 409

            # Create extractions directory if it doesn't exist
            extractions_dir = os.path.join(INVOICE_FOLDER, "extractions")
            os.makedirs(extractions_dir, exist_ok=True)
            
            # Insert into invoice_extractions table (INDEXED JSON ROW ONLY)
            try:
                # Create JSON file for ALL indexed data
                json_filename = f"invoice_{invoice_id}_indexed_data.json"
                json_file_path = os.path.join(extractions_dir, json_filename)
                
                # ALL INDEXED DATA IN ONE JSON STRUCTURE
                indexed_extraction_data = {
                    "parent_invoice_id": invoice_id,
                    "parent_info": {
                        "file_name": file_name,
                        "file_hash": file_hash,
                        "upload_timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "file_size": file_size,
                        "file_type": file_ext,
                        "upload_index": next_index
                    },
                    "indexed_data": indexed_invoice_data,
                    "extraction_metadata": {
                        "total_items": len(indexed_items),
                        "total_amount": total_amount if total_amount else 0,
                        "extraction_confidence": 0.85 if total_amount else 0.0,
                        "processed_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "source": "invoice_upload_endpoint"
                    }
                }
                
                with open(json_file_path, 'w', encoding='utf-8') as f:
                    json.dump(indexed_extraction_data, f, ensure_ascii=False, indent=2, default=str)
                
                # Insert ONE ROW ONLY into invoice_extractions table
                db_manager.execute_insert(
                    """
                    INSERT INTO invoice_extractions (
                        parent_invoice_id, sequence_no, page_no, section_no, original_filename, json_file_path, extracted_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        invoice_id,  # parent_invoice_id
                        next_index,  # sequence_no (use upload index)
                        1,  # page_no
                        None,  # section_no
                        file_name,  # original_filename
                        json_file_path,  # json_file_path
                        json.dumps(indexed_extraction_data, ensure_ascii=False, default=str),  # INDEXED JSON DATA
                    ),
                )
            except Exception as e:
                print(f"Warning: Failed to store invoice extraction: {e}")

            return jsonify({
                "success": True,
                "upload_id": invoice_upload_id,
                "invoice_ids": invoice_ids,
                "total_invoices": len(invoice_ids),
                "file_name": file_name,
                "file_size": file_size,
                "invoice_file_path": file_path,
                "invoice_file_hash": invoice_file_hash_unique,
                "status": "pending",
                "data": extracted_payload,
                "message": "Invoice uploaded successfully. Stored in file_uploads (parent JSON) and invoices (child rows)."
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/upload-invoice-file: {e}")
            print(error_traceback)
            
            # Clean up file on error
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            
            return jsonify({
                "error": "Internal server error while uploading file.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
        
    @app.route("/api/upload-status/<job_id>", methods=["GET"])
    def api_get_upload_status(job_id: str):
        """
        Get the status of a file processing job.
        
        Path parameters:
        - job_id: The job ID returned by upload-invoice-file endpoint
        """
        try:
            if DB_TYPE == "mysql":
                return jsonify({
                    "error": "Endpoint disabled",
                    "details": "MySQL mode stores invoices directly in invoices table; background file_uploads processing is disabled."
                }), 410

            from services.multi_invoice_processor import multi_invoice_processor

            job = multi_invoice_processor.get_processing_status(job_id)
            
            if not job:
                return jsonify({"error": "Job not found"}), 404
            
            response = {
                "job_id": job.job_id,
                "file_upload_id": job.file_upload_id,
                "status": job.status,
                "progress": job.progress,
                "current_step": job.current_step,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "error_message": job.error_message,
                "result_data": job.result_data
            }
            
            # Add file upload details if available
            if job.file_upload_id:
                file_upload = multi_invoice_processor._load_file_upload(job.file_upload_id)
                if file_upload:
                    response["file_upload"] = {
                        "id": file_upload.id,
                        "file_name": file_upload.file_name,
                        "file_type": file_upload.file_type,
                        "file_size": file_upload.file_size,
                        "processing_status": file_upload.processing_status,
                        "total_invoices_found": file_upload.total_invoices_found,
                        "total_invoices_processed": file_upload.total_invoices_processed,
                        "total_amount": file_upload.total_amount,
                        "currency_summary": file_upload.currency_summary,
                        "extraction_confidence": file_upload.extraction_confidence,
                        "upload_timestamp": file_upload.upload_timestamp,
                        "error_message": file_upload.error_message
                    }
            
            return jsonify(response)
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/upload-status/{job_id}: {e}")
            print(error_traceback)
            
            return jsonify({
                "error": "Internal server error while getting upload status.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    @app.route("/api/file-uploads", methods=["GET"])
    def api_list_file_uploads():
        """
        List all file uploads with pagination and filtering.
        
        Query parameters:
        - page: page number (default: 1)
        - limit: items per page (default: 20, max: 100)
        - status: filter by processing status
        - file_type: filter by file type
        - search: search in file names
        """
        try:
            if DB_TYPE == "mysql":
                return jsonify({
                    "error": "Endpoint disabled",
                    "details": "MySQL mode stores invoices directly in invoices table; file_uploads listing is disabled."
                }), 410

            import sqlite3
            
            # Parse query parameters
            page = max(1, int(request.args.get('page', 1)))
            limit = min(100, max(1, int(request.args.get('limit', 20))))
            offset = (page - 1) * limit
            
            status_filter = request.args.get('status')
            file_type_filter = request.args.get('file_type')
            search_query = request.args.get('search', '').strip()
            
            # Build query
            where_clauses = []
            params = []
            
            if status_filter:
                where_clauses.append("processing_status = ?")
                params.append(status_filter)
            
            if file_type_filter:
                where_clauses.append("file_type = ?")
                params.append(file_type_filter)
            
            if search_query:
                where_clauses.append("file_name LIKE ?")
                params.append(f"%{search_query}%")
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Get total count
            cur.execute(f"SELECT COUNT(*) FROM file_uploads WHERE {where_sql}", params)
            total_count = cur.fetchone()[0]
            
            # Get paginated results
            query = f"""
                SELECT * FROM file_uploads 
                WHERE {where_sql}
                ORDER BY upload_timestamp DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
            # Convert to list of dicts
            uploads = []
            for row in rows:
                upload = dict(row)
                # Parse JSON fields
                import json
                if upload['currency_summary']:
                    upload['currency_summary'] = json.loads(upload['currency_summary'])
                if upload['metadata']:
                    upload['metadata'] = json.loads(upload['metadata'])
                uploads.append(upload)
            
            conn.close()
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit
            has_next = page < total_pages
            has_prev = page > 1
            
            return jsonify({
                "uploads": uploads,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev
                },
                "filters": {
                    "status": status_filter,
                    "file_type": file_type_filter,
                    "search": search_query
                }
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/file-uploads: {e}")
            print(error_traceback)
            
            return jsonify({
                "error": "Internal server error while listing file uploads.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    @app.route("/api/file-uploads/<int:upload_id>", methods=["GET"])
    def api_get_file_upload(upload_id: int):
        """
        Get detailed information about a specific file upload.
        
        Path parameters:
        - upload_id: The ID of the file upload
        """
        try:
            import sqlite3
            import json
            
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Get file upload details
            cur.execute("SELECT * FROM file_uploads WHERE id = ?", (upload_id,))
            row = cur.fetchone()
            
            if not row:
                conn.close()
                return jsonify({"error": "File upload not found"}), 404
            
            upload = dict(row)
            
            # Parse JSON fields
            if upload['currency_summary']:
                upload['currency_summary'] = json.loads(upload['currency_summary'])
            if upload['metadata']:
                upload['metadata'] = json.loads(upload['metadata'])
            
            # Get extracted invoices
            cur.execute("""
                SELECT * FROM extracted_invoices 
                WHERE file_upload_id = ?
                ORDER BY page_number ASC, id ASC
            """, (upload_id,))
            
            invoices = []
            for invoice_row in cur.fetchall():
                invoice = dict(invoice_row)
                if invoice['bounding_box']:
                    invoice['bounding_box'] = json.loads(invoice['bounding_box'])
                
                # Get line items for this invoice
                cur.execute("""
                    SELECT * FROM invoice_line_items 
                    WHERE extracted_invoice_id = ?
                    ORDER BY id ASC
                """, (invoice['id'],))
                
                line_items = [dict(item_row) for item_row in cur.fetchall()]
                invoice['line_items'] = line_items
                invoices.append(invoice)
            
            upload['extracted_invoices'] = invoices
            
            # Get processing jobs
            cur.execute("""
                SELECT * FROM processing_jobs 
                WHERE file_upload_id = ?
                ORDER BY created_at DESC
            """, (upload_id,))
            
            jobs = []
            for job_row in cur.fetchall():
                job = dict(job_row)
                if job['result_data']:
                    job['result_data'] = json.loads(job['result_data'])
                jobs.append(job)
            
            upload['processing_jobs'] = jobs
            
            conn.close()
            
            return jsonify(upload)
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/file-uploads/{upload_id}: {e}")
            print(error_traceback)
            
            return jsonify({
                "error": "Internal server error while getting file upload details.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    @app.route("/api/file-uploads/<int:upload_id>/invoices", methods=["GET"])
    def api_get_upload_invoices(upload_id: int):
        """
        Get all invoices extracted from a specific file upload.
        
        Path parameters:
        - upload_id: The ID of the file upload
        """
        try:
            import sqlite3
            import json
            
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Verify file upload exists
            cur.execute("SELECT id, file_name FROM file_uploads WHERE id = ?", (upload_id,))
            file_upload = cur.fetchone()
            
            if not file_upload:
                conn.close()
                return jsonify({"error": "File upload not found"}), 404
            
            # Get extracted invoices
            cur.execute("""
                SELECT * FROM extracted_invoices 
                WHERE file_upload_id = ?
                ORDER BY page_number ASC, id ASC
            """, (upload_id,))
            
            invoices = []
            for invoice_row in cur.fetchall():
                invoice = dict(invoice_row)
                if invoice['bounding_box']:
                    invoice['bounding_box'] = json.loads(invoice['bounding_box'])
                
                # Get line items for this invoice
                cur.execute("""
                    SELECT * FROM invoice_line_items 
                    WHERE extracted_invoice_id = ?
                    ORDER BY id ASC
                """, (invoice['id'],))
                
                line_items = [dict(item_row) for item_row in cur.fetchall()]
                invoice['line_items'] = line_items
                invoices.append(invoice)
            
            conn.close()
            
            return jsonify({
                "file_upload_id": upload_id,
                "file_name": file_upload['file_name'],
                "total_invoices": len(invoices),
                "invoices": invoices
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/file-uploads/{upload_id}/invoices: {e}")
            print(error_traceback)
            
            return jsonify({
                "error": "Internal server error while getting upload invoices.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    @app.route("/api/file-uploads/<int:upload_id>/download", methods=["GET"])
    def api_download_file(upload_id: int):
        """
        Download the original uploaded file.
        
        Path parameters:
        - upload_id: The ID of the file upload
        """
        try:
            import sqlite3
            
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Get file upload details
            cur.execute("SELECT file_path, file_name FROM file_uploads WHERE id = ?", (upload_id,))
            row = cur.fetchone()
            
            if not row:
                conn.close()
                return jsonify({"error": "File upload not found"}), 404
            
            file_path = row['file_path']
            file_name = row['file_name']
            
            conn.close()
            
            # Check if file exists
            if not os.path.exists(file_path):
                return jsonify({"error": "File not found on disk"}), 404
            
            # Send file
            return send_from_directory(
                os.path.dirname(file_path),
                os.path.basename(file_path),
                as_attachment=True,
                download_name=file_name
            )
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/file-uploads/{upload_id}/download: {e}")
            print(error_traceback)
            
            return jsonify({
                "error": "Internal server error while downloading file.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    @app.route("/api/file-uploads/<int:upload_id>", methods=["DELETE"])
    def api_delete_file_upload(upload_id: int):
        """
        Delete a file upload and all its extracted invoices.
        
        Path parameters:
        - upload_id: The ID of the file upload
        """
        try:
            import sqlite3
            
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # Get file upload details
            cur.execute("SELECT file_path FROM file_uploads WHERE id = ?", (upload_id,))
            row = cur.fetchone()
            
            if not row:
                conn.close()
                return jsonify({"error": "File upload not found"}), 404
            
            file_path = row[0]
            
            # Delete from database (cascading delete will handle related records)
            cur.execute("DELETE FROM file_uploads WHERE id = ?", (upload_id,))
            
            conn.commit()
            conn.close()
            
            # Delete physical file
            if os.path.exists(file_path):
                os.remove(file_path)
            
            return jsonify({
                "success": True,
                "message": "File upload and all related data deleted successfully"
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Error in /api/file-uploads/{upload_id}: {e}")
            print(error_traceback)
            
            return jsonify({
                "error": "Internal server error while deleting file upload.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }), 500
    
    return app
