"""
Production JSON Storage API Endpoints
Flask API endpoints for the single-row JSON storage system

Core Rule: One uploaded file or one reconciliation run = one database row
All extracted or generated data must be stored inside that single row as structured JSON
"""

from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
import json
import logging
from typing import Dict, Any

from services.production_json_workflows import initialize_production_json_system
from app import logger, limiter, RATE_LIMITS

# Create Blueprint for production JSON API
production_json_api = Blueprint('production_json_api', __name__)

# Initialize the production JSON system
# These will be configured during app initialization
PRODUCTION_JSON_API = None
PRODUCTION_DB_PATH = None
PRODUCTION_UPLOAD_FOLDER = None

def init_production_json_api(db_path: str, upload_folder: str):
    """Initialize the production JSON API with database and folder paths"""
    global PRODUCTION_JSON_API, PRODUCTION_DB_PATH, PRODUCTION_UPLOAD_FOLDER
    
    PRODUCTION_DB_PATH = db_path
    PRODUCTION_UPLOAD_FOLDER = upload_folder
    PRODUCTION_JSON_API = initialize_production_json_system(db_path, upload_folder)
    
    logger.info("Production JSON API initialized", 
               context={"db_path": db_path, "upload_folder": upload_folder})


# === API Endpoints ===

@production_json_api.route('/api/production/invoices/upload', methods=['POST'])
@limiter.limit(RATE_LIMITS.get('/api/process-document', '20 per minute'))
def upload_invoice_file():
    """
    Upload and process invoice file with single-row JSON storage
    
    Expected Response:
    {
        "success": true,
        "upload_id": 5,
        "db_record_id": 123,
        "file_name": "invoices_batch_2024.pdf",
        "total_invoices": 100,
        "total_amount": 125000.50,
        "processing_time_seconds": 130,
        "status": "completed"
    }
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file type
        allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.xlsx', '.xls'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"File type {file_ext} not allowed"}), 400
        
        # Read file data
        file_data = file.read()
        file_name = secure_filename(file.filename)
        
        logger.info(f"Processing invoice upload", context={"file_name": file_name, "file_size": len(file_data)})
        
        # Process with production JSON workflow
        result = PRODUCTION_JSON_API.upload_invoice_file(file_data, file_name)
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Invoice upload failed", context={"file_name": file.name if 'file' in locals() else None}, error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/bank/upload', methods=['POST'])
@limiter.limit(RATE_LIMITS.get('/api/process-document', '20 per minute'))
def upload_bank_file():
    """
    Upload and process bank statement file with single-row JSON storage
    
    Expected Response:
    {
        "success": true,
        "upload_id": 7,
        "db_record_id": 124,
        "file_name": "bank_statement_jan2024.pdf",
        "total_transactions": 342,
        "total_debits": 150000.00,
        "total_credits": 175000.00,
        "processing_time_seconds": 100,
        "status": "completed"
    }
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file type
        allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.xlsx', '.xls', '.csv'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"File type {file_ext} not allowed"}), 400
        
        # Read file data
        file_data = file.read()
        file_name = secure_filename(file.filename)
        
        logger.info(f"Processing bank statement upload", context={"file_name": file_name, "file_size": len(file_data)})
        
        # Process with production JSON workflow
        result = PRODUCTION_JSON_API.upload_bank_file(file_data, file_name)
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Bank statement upload failed", context={"file_name": file.name if 'file' in locals() else None}, error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/reconcile', methods=['POST'])
@limiter.limit(RATE_LIMITS.get('/api/reconcile', '10 per minute'))
def run_reconciliation():
    """
    Run reconciliation between invoice and bank data with single-row JSON storage
    
    Expected Request:
    {
        "invoice_upload_id": 5,
        "bank_upload_id": 7
    }
    
    Expected Response:
    {
        "success": true,
        "reconciliation_id": 3,
        "db_record_id": 125,
        "total_matches": 85,
        "match_rate_percentage": 85.0,
        "processing_time_seconds": 45,
        "status": "completed"
    }
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        
        data = request.get_json()
        invoice_upload_id = data.get('invoice_upload_id')
        bank_upload_id = data.get('bank_upload_id')
        
        if not invoice_upload_id or not bank_upload_id:
            return jsonify({"error": "Both invoice_upload_id and bank_upload_id are required"}), 400
        
        logger.info(f"Starting reconciliation", 
                   context={"invoice_upload_id": invoice_upload_id, "bank_upload_id": bank_upload_id})
        
        # Run reconciliation with production JSON workflow
        result = PRODUCTION_JSON_API.run_reconciliation(invoice_upload_id, bank_upload_id)
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Reconciliation failed", 
                    context={"invoice_upload_id": data.get('invoice_upload_id') if 'data' in locals() else None,
                           "bank_upload_id": data.get('bank_upload_id') if 'data' in locals() else None}, 
                    error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/invoices/<int:upload_id>', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/reconciliations', '30 per minute'))
def get_invoice_data(upload_id: int):
    """
    Retrieve complete invoice JSON data for a specific upload
    
    Returns the full JSON structure containing all invoices from the file
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        logger.info(f"Retrieving invoice data", context={"upload_id": upload_id})
        
        # Get complete invoice JSON data
        invoice_data = PRODUCTION_JSON_API.get_invoice_data(upload_id)
        
        if invoice_data:
            return jsonify({
                "success": True,
                "upload_id": upload_id,
                "data": invoice_data
            }), 200
        else:
            return jsonify({"error": f"Invoice upload {upload_id} not found"}), 404
            
    except Exception as e:
        logger.error(f"Failed to retrieve invoice data", context={"upload_id": upload_id}, error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/bank/<int:upload_id>', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/reconciliations', '30 per minute'))
def get_bank_data(upload_id: int):
    """
    Retrieve complete bank transaction JSON data for a specific upload
    
    Returns the full JSON structure containing all transactions from the file
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        logger.info(f"Retrieving bank data", context={"upload_id": upload_id})
        
        # Get complete bank transaction JSON data
        bank_data = PRODUCTION_JSON_API.get_bank_data(upload_id)
        
        if bank_data:
            return jsonify({
                "success": True,
                "upload_id": upload_id,
                "data": bank_data
            }), 200
        else:
            return jsonify({"error": f"Bank upload {upload_id} not found"}), 404
            
    except Exception as e:
        logger.error(f"Failed to retrieve bank data", context={"upload_id": upload_id}, error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/reconciliations/<int:reconciliation_id>', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/reconciliations/<int:reconciliation_id>/matches', '60 per minute'))
def get_reconciliation_data(reconciliation_id: int):
    """
    Retrieve complete reconciliation JSON data for a specific reconciliation run
    
    Returns the full JSON structure containing all matches, partial matches, and unmatched items
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        logger.info(f"Retrieving reconciliation data", context={"reconciliation_id": reconciliation_id})
        
        # Get complete reconciliation JSON data
        reconciliation_data = PRODUCTION_JSON_API.get_reconciliation_data(reconciliation_id)
        
        if reconciliation_data:
            return jsonify({
                "success": True,
                "reconciliation_id": reconciliation_id,
                "data": reconciliation_data
            }), 200
        else:
            return jsonify({"error": f"Reconciliation {reconciliation_id} not found"}), 404
            
    except Exception as e:
        logger.error(f"Failed to retrieve reconciliation data", context={"reconciliation_id": reconciliation_id}, error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/invoices', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/reconciliations', '30 per minute'))
def list_invoice_uploads():
    """
    List all invoice uploads with summary information
    
    Returns summary data for all invoice uploads (not full JSON data)
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        import sqlite3
        conn = sqlite3.connect(PRODUCTION_DB_PATH)
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT upload_id, file_name, file_size, total_invoices_found, total_amount,
                   currency_summary, status, upload_timestamp, processing_duration_seconds
            FROM production_invoice_uploads
            ORDER BY upload_timestamp DESC
        """)
        
        uploads = []
        for row in cursor.fetchall():
            upload = {
                "upload_id": row[0],
                "file_name": row[1],
                "file_size": row[2],
                "total_invoices_found": row[3],
                "total_amount": row[4],
                "currency_summary": json.loads(row[5]) if row[5] else {},
                "status": row[6],
                "upload_timestamp": row[7],
                "processing_duration_seconds": row[8]
            }
            uploads.append(upload)
        
        conn.close()
        
        return jsonify({
            "success": True,
            "total_uploads": len(uploads),
            "uploads": uploads
        }), 200
            
    except Exception as e:
        logger.error(f"Failed to list invoice uploads", error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/bank', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/reconciliations', '30 per minute'))
def list_bank_uploads():
    """
    List all bank statement uploads with summary information
    
    Returns summary data for all bank uploads (not full JSON data)
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        import sqlite3
        conn = sqlite3.connect(PRODUCTION_DB_PATH)
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT upload_id, file_name, file_size, total_transactions_found,
                   total_debits, total_credits, currency, status, upload_timestamp,
                   processing_duration_seconds, account_number, bank_name
            FROM production_bank_uploads
            ORDER BY upload_timestamp DESC
        """)
        
        uploads = []
        for row in cursor.fetchall():
            upload = {
                "upload_id": row[0],
                "file_name": row[1],
                "file_size": row[2],
                "total_transactions_found": row[3],
                "total_debits": row[4],
                "total_credits": row[5],
                "currency": row[6],
                "status": row[7],
                "upload_timestamp": row[8],
                "processing_duration_seconds": row[9],
                "account_number": row[10],
                "bank_name": row[11]
            }
            uploads.append(upload)
        
        conn.close()
        
        return jsonify({
            "success": True,
            "total_uploads": len(uploads),
            "uploads": uploads
        }), 200
            
    except Exception as e:
        logger.error(f"Failed to list bank uploads", error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/reconciliations', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/reconciliations', '30 per minute'))
def list_reconciliations():
    """
    List all reconciliation runs with summary information
    
    Returns summary data for all reconciliations (not full JSON data)
    """
    if not PRODUCTION_JSON_API:
        return jsonify({"error": "Production JSON API not initialized"}), 500
    
    try:
        import sqlite3
        conn = sqlite3.connect(PRODUCTION_DB_PATH)
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT reconciliation_id, invoice_upload_id, bank_upload_id,
                   invoice_file_name, bank_file_name, total_matches_found,
                   match_rate_percentage, status, reconciliation_timestamp,
                   reconciliation_duration_seconds
            FROM production_reconciliation_matches
            ORDER BY reconciliation_timestamp DESC
        """)
        
        reconciliations = []
        for row in cursor.fetchall():
            reconciliation = {
                "reconciliation_id": row[0],
                "invoice_upload_id": row[1],
                "bank_upload_id": row[2],
                "invoice_file_name": row[3],
                "bank_file_name": row[4],
                "total_matches_found": row[5],
                "match_rate_percentage": row[6],
                "status": row[7],
                "reconciliation_timestamp": row[8],
                "reconciliation_duration_seconds": row[9]
            }
            reconciliations.append(reconciliation)
        
        conn.close()
        
        return jsonify({
            "success": True,
            "total_reconciliations": len(reconciliations),
            "reconciliations": reconciliations
        }), 200
            
    except Exception as e:
        logger.error(f"Failed to list reconciliations", error=e)
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@production_json_api.route('/api/production/health', methods=['GET'])
@limiter.limit(RATE_LIMITS.get('/api/health', '120 per minute'))
def health_check():
    """
    Health check endpoint for production JSON API
    
    Returns system status and configuration information
    """
    try:
        import sqlite3
        
        # Check database connectivity
        conn = sqlite3.connect(PRODUCTION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM production_invoice_uploads")
        invoice_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM production_bank_uploads")
        bank_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM production_reconciliation_matches")
        reconciliation_count = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "production_json_api": "enabled",
            "database": {
                "path": PRODUCTION_DB_PATH,
                "invoice_uploads": invoice_count,
                "bank_uploads": bank_count,
                "reconciliations": reconciliation_count
            },
            "upload_folder": PRODUCTION_UPLOAD_FOLDER,
            "storage_mode": "single_row_json"
        }), 200
        
    except Exception as e:
        logger.error(f"Health check failed", error=e)
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@production_json_api.route('/api/production/docs', methods=['GET'])
def api_documentation():
    """
    API documentation for production JSON storage system
    
    Returns comprehensive documentation about the single-row JSON storage approach
    """
    docs = {
        "title": "Production JSON Storage API",
        "description": "Financial document processing with single-row JSON storage",
        "core_principle": "One uploaded file or one reconciliation run = one database row",
        "storage_mode": "All extracted or generated data stored inside single row as structured JSON",
        "endpoints": {
            "invoice_upload": {
                "method": "POST",
                "path": "/api/production/invoices/upload",
                "description": "Upload and process invoice file",
                "storage": "Single database row with all invoices in JSON column",
                "example_response": {
                    "success": True,
                    "upload_id": 5,
                    "total_invoices": 100,
                    "total_amount": 125000.50
                }
            },
            "bank_upload": {
                "method": "POST", 
                "path": "/api/production/bank/upload",
                "description": "Upload and process bank statement file",
                "storage": "Single database row with all transactions in JSON column",
                "example_response": {
                    "success": True,
                    "upload_id": 7,
                    "total_transactions": 342,
                    "total_debits": 150000.00
                }
            },
            "reconciliation": {
                "method": "POST",
                "path": "/api/production/reconcile", 
                "description": "Run reconciliation between invoice and bank data",
                "storage": "Single database row with all match results in JSON column",
                "example_response": {
                    "success": True,
                    "reconciliation_id": 3,
                    "total_matches": 85,
                    "match_rate_percentage": 85.0
                }
            },
            "get_invoice_data": {
                "method": "GET",
                "path": "/api/production/invoices/{upload_id}",
                "description": "Retrieve complete invoice JSON data",
                "returns": "Full JSON structure with all invoices from the file"
            },
            "get_bank_data": {
                "method": "GET", 
                "path": "/api/production/bank/{upload_id}",
                "description": "Retrieve complete bank transaction JSON data",
                "returns": "Full JSON structure with all transactions from the file"
            },
            "get_reconciliation_data": {
                "method": "GET",
                "path": "/api/production/reconciliations/{reconciliation_id}",
                "description": "Retrieve complete reconciliation JSON data", 
                "returns": "Full JSON structure with all matches and unmatched items"
            }
        },
        "database_schema": {
            "production_invoice_uploads": {
                "purpose": "Store invoice files with ALL extracted invoices in JSON",
                "key_column": "invoice_json (TEXT) - Contains complete invoice data",
                "example": "ID=5 → invoice_json = {invoices: [...100 invoice objects...]}"
            },
            "production_bank_uploads": {
                "purpose": "Store bank statements with ALL transactions in JSON", 
                "key_column": "bank_transaction_json (TEXT) - Contains complete transaction data",
                "example": "ID=7 → bank_transaction_json = {transactions: [...all transactions...]}"
            },
            "production_reconciliation_matches": {
                "purpose": "Store reconciliation results with ALL matches in JSON",
                "key_column": "reconciliation_match_json (TEXT) - Contains complete match results",
                "example": "Reconciliation_ID=3 → reconciliation_match_json = {matched: [...], partial: [...], unmatched: [...]}"
            }
        },
        "benefits": [
            "Atomic Operations: All-or-nothing saves ensure data integrity",
            "Performance: Single INSERT/UPDATE per file instead of thousands", 
            "Consistency: Same storage pattern across all modules",
            "Scalability: Handles large PDFs with thousands of records",
            "Production Safety: Validated JSON structures prevent corruption"
        ]
    }
    
    return jsonify(docs), 200


# === Error Handlers ===

@production_json_api.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({"error": "File too large"}), 413

@production_json_api.errorhandler(422)
def unprocessable_entity(e):
    """Handle unprocessable entity error"""
    return jsonify({"error": "Unprocessable entity"}), 422

@production_json_api.errorhandler(500)
def internal_error(e):
    """Handle internal server error"""
    logger.error(f"Internal server error in production JSON API", error=e)
    return jsonify({"error": "Internal server error"}), 500


# === Flask App Integration ===

def register_production_json_api(app, db_path: str, upload_folder: str):
    """
    Register the production JSON API with a Flask application
    
    Args:
        app: Flask application instance
        db_path: Path to the SQLite database
        upload_folder: Path to the upload folder
    """
    # Initialize the production JSON API
    init_production_json_api(db_path, upload_folder)
    
    # Register the blueprint
    app.register_blueprint(production_json_api)
    
    # Log registration
    logger.info("Production JSON API registered with Flask app",
               context={"db_path": db_path, "upload_folder": upload_folder})
    
    print("✓ Production JSON Storage API registered")
    print("  - Invoice uploads: /api/production/invoices/upload")
    print("  - Bank uploads: /api/production/bank/upload") 
    print("  - Reconciliation: /api/production/reconcile")
    print("  - API docs: /api/production/docs")
    print("  - Health check: /api/production/health")
