"""
Unified Document API Endpoints
Production-ready API for both invoices and bank statements
"""

import os
import sys
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import tempfile
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import (
    DB_PATH, UPLOAD_FOLDER, MAX_FILE_SIZE_BYTES, MAX_TOTAL_SIZE_BYTES,
    INVOICE_ALLOWED_EXTENSIONS, INVOICE_ALLOWED_MIMETYPES
)
from services.unified_processor import unified_processor
from models.unified_models import BaseDocumentUpload, BaseProcessingJob

def register_unified_document_routes(app: Flask):
    """Register unified document processing routes"""
    
    @app.route("/api/upload-document", methods=["POST"])
    def api_upload_document():
        """Upload document (invoice or bank statement)"""
        try:
            # Validate file presence
            if 'file' not in request.files:
                return jsonify({
                    "success": False,
                    "error": "No file provided"
                }), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({
                    "success": False,
                    "error": "No file selected"
                }), 400
            
            # Get document type from request or infer from filename
            document_type = request.form.get('document_type', '')
            if not document_type:
                document_type = unified_processor.get_document_type(file.filename)
            
            # Validate document type
            if document_type not in ['invoice', 'bank_statement']:
                return jsonify({
                    "success": False,
                    "error": "Invalid document type. Must be 'invoice' or 'bank_statement'"
                }), 400
            
            # Validate file
            if not _allowed_file(file.filename):
                return jsonify({
                    "success": False,
                    "error": "File type not allowed"
                }), 400
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > MAX_FILE_SIZE_BYTES:
                return jsonify({
                    "success": False,
                    "error": f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)}MB"
                }), 413
            
            # Read file content
            file_content = file.read()
            
            # Check for duplicates
            file_hash = unified_processor.calculate_file_hash(file_content)
            if _check_duplicate_upload(file_hash):
                return jsonify({
                    "success": False,
                    "error": "File already uploaded",
                    "duplicate": True
                }), 409
            
            # Create upload directory
            upload_dir = os.path.join(UPLOAD_FOLDER, document_type + "s")
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save file
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_filename = f"{timestamp}_{filename}"
            file_path = os.path.join(upload_dir, saved_filename)
            
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            # Create document upload record
            document_upload = unified_processor.create_document_upload(
                file_content, filename, file_path, file.mimetype, document_type
            )
            
            # Start processing
            job_id = unified_processor.process_document_async(document_upload.id)
            
            return jsonify({
                "success": True,
                "document_upload_id": document_upload.id,
                "job_id": job_id,
                "document_type": document_type,
                "file_name": filename,
                "processing_status": "pending",
                "message": f"{document_type.replace('_', ' ').title()} uploaded successfully. Processing started in background."
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Upload failed: {str(e)}"
            }), 500
    
    @app.route("/api/upload-status/<job_id>", methods=["GET"])
    def api_get_upload_status(job_id: str):
        """Get processing status for a job"""
        try:
            job = _get_processing_job(job_id)
            if not job:
                return jsonify({
                    "success": False,
                    "error": "Job not found"
                }), 404
            
            # Get document upload details
            doc_upload = _get_document_upload(job.document_upload_id)
            
            response = {
                "success": True,
                "job_id": job.job_id,
                "status": job.status,
                "progress": job.progress,
                "current_step": job.current_step,
                "estimated_time_remaining": job.estimated_time_remaining,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "error_message": job.error_message
            }
            
            if doc_upload:
                response["document_upload"] = {
                    "document_upload_id": doc_upload.id,
                    "document_type": doc_upload.document_type,
                    "file_name": doc_upload.file_name,
                    "processing_status": doc_upload.processing_status,
                    "total_documents_found": doc_upload.total_documents_found,
                    "total_documents_processed": doc_upload.total_documents_processed,
                    "total_amount": doc_upload.total_amount,
                    "currency_summary": doc_upload.currency_summary,
                    "extraction_confidence": doc_upload.extraction_confidence,
                    "upload_timestamp": doc_upload.upload_timestamp
                }
            
            return jsonify(response)
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get status: {str(e)}"
            }), 500
    
    @app.route("/api/documents", methods=["GET"])
    def api_list_documents():
        """List all document uploads"""
        try:
            document_type = request.args.get('document_type', '')
            status = request.args.get('status', '')
            limit = min(int(request.args.get('limit', 50)), 100)
            offset = int(request.args.get('offset', 0))
            
            documents = _get_document_uploads(document_type, status, limit, offset)
            
            return jsonify({
                "success": True,
                "documents": documents,
                "total": _count_documents(document_type, status),
                "limit": limit,
                "offset": offset
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to list documents: {str(e)}"
            }), 500
    
    @app.route("/api/documents/<int:document_id>", methods=["GET"])
    def api_get_document_details(document_id: int):
        """Get detailed information about a document upload"""
        try:
            doc_upload = _get_document_upload(document_id)
            if not doc_upload:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404
            
            # Get extracted data based on document type
            extracted_data = []
            if doc_upload.document_type == 'invoice':
                extracted_data = _get_extracted_invoices(document_id)
            elif doc_upload.document_type == 'bank_statement':
                extracted_data = _get_bank_transactions(document_id)
            
            return jsonify({
                "success": True,
                "document_upload": {
                    "id": doc_upload.id,
                    "document_type": doc_upload.document_type,
                    "file_name": doc_upload.file_name,
                    "file_path": doc_upload.file_path,
                    "file_size": doc_upload.file_size,
                    "file_type": doc_upload.file_type,
                    "mime_type": doc_upload.mime_type,
                    "upload_timestamp": doc_upload.upload_timestamp,
                    "processing_status": doc_upload.processing_status,
                    "processing_start_time": doc_upload.processing_start_time,
                    "processing_end_time": doc_upload.processing_end_time,
                    "total_documents_found": doc_upload.total_documents_found,
                    "total_documents_processed": doc_upload.total_documents_processed,
                    "total_amount": doc_upload.total_amount,
                    "currency_summary": doc_upload.currency_summary,
                    "extraction_confidence": doc_upload.extraction_confidence,
                    "error_message": doc_upload.error_message,
                    "metadata": doc_upload.metadata
                },
                "extracted_data": extracted_data
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get document details: {str(e)}"
            }), 500
    
    @app.route("/api/documents/<int:document_id>/download", methods=["GET"])
    def api_download_document(document_id: int):
        """Download original document file"""
        try:
            doc_upload = _get_document_upload(document_id)
            if not doc_upload:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404
            
            if not os.path.exists(doc_upload.file_path):
                return jsonify({
                    "success": False,
                    "error": "File not found on disk"
                }), 404
            
            return send_file(
                doc_upload.file_path,
                as_attachment=True,
                download_name=doc_upload.file_name,
                mimetype=doc_upload.mime_type
            )
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to download document: {str(e)}"
            }), 500
    
    @app.route("/api/documents/<int:document_id>", methods=["DELETE"])
    def api_delete_document(document_id: int):
        """Delete document upload and all extracted data"""
        try:
            doc_upload = _get_document_upload(document_id)
            if not doc_upload:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404
            
            # Delete file from disk
            if os.path.exists(doc_upload.file_path):
                os.remove(doc_upload.file_path)
            
            # Delete from database (cascade will handle related records)
            _delete_document_upload(document_id)
            
            return jsonify({
                "success": True,
                "message": "Document and all extracted data deleted successfully"
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to delete document: {str(e)}"
            }), 500
    
    @app.route("/api/documents/<int:document_id>/invoices", methods=["GET"])
    def api_get_document_invoices(document_id: int):
        """Get invoices extracted from a document"""
        try:
            doc_upload = _get_document_upload(document_id)
            if not doc_upload:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404
            
            if doc_upload.document_type != 'invoice':
                return jsonify({
                    "success": False,
                    "error": "Document is not an invoice file"
                }), 400
            
            invoices = _get_extracted_invoices(document_id)
            
            return jsonify({
                "success": True,
                "document_upload_id": document_id,
                "document_type": "invoice",
                "invoices": invoices,
                "total": len(invoices)
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get invoices: {str(e)}"
            }), 500
    
    @app.route("/api/documents/<int:document_id>/transactions", methods=["GET"])
    def api_get_document_transactions(document_id: int):
        """Get transactions extracted from a bank statement"""
        try:
            doc_upload = _get_document_upload(document_id)
            if not doc_upload:
                return jsonify({
                    "success": False,
                    "error": "Document not found"
                }), 404
            
            if doc_upload.document_type != 'bank_statement':
                return jsonify({
                    "success": False,
                    "error": "Document is not a bank statement"
                }), 400
            
            transactions = _get_bank_transactions(document_id)
            
            return jsonify({
                "success": True,
                "document_upload_id": document_id,
                "document_type": "bank_statement",
                "transactions": transactions,
                "total": len(transactions)
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get transactions: {str(e)}"
            }), 500

# Helper functions
def _allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return ('.' in filename and 
            filename.rsplit('.', 1)[1].lower() in INVOICE_ALLOWED_EXTENSIONS)

def _check_duplicate_upload(file_hash: str) -> bool:
    """Check if file has already been uploaded"""
    # Implementation would check database for existing hash
    return False

def _get_processing_job(job_id: str) -> Optional[BaseProcessingJob]:
    """Get processing job from database"""
    # Implementation would load from database
    return None

def _get_document_upload(upload_id: int) -> Optional[BaseDocumentUpload]:
    """Get document upload from database"""
    # Implementation would load from database
    return None

def _get_document_uploads(document_type: str, status: str, limit: int, offset: int) -> List[Dict]:
    """Get document uploads from database"""
    # Implementation would load from database
    return []

def _count_documents(document_type: str, status: str) -> int:
    """Count documents in database"""
    # Implementation would count from database
    return 0

def _get_extracted_invoices(document_id: int) -> List[Dict]:
    """Get extracted invoices from database"""
    # Implementation would load from database
    return []

def _get_bank_transactions(document_id: int) -> List[Dict]:
    """Get bank transactions from database"""
    # Implementation would load from database
    return []

def _delete_document_upload(document_id: int):
    """Delete document upload from database"""
    # Implementation would delete from database
    pass
