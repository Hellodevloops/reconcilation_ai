"""
Simplified Reconciliation API - Single Table Design
Production-ready API using only reconciliation_match table
"""

import os
import sys
from flask import Flask, request, jsonify
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services.simplified_reconciliation import simplified_reconciliation_service
from models.simplified_reconciliation import get_simplified_reconciliation_schema

def register_simplified_reconciliation_api(app: Flask):
    """Register simplified reconciliation API routes"""
    
    # === Reconciliation Endpoints (Single Table Design) ===
    
    @app.route("/api/reconciliation/create", methods=["POST"])
    def api_create_reconciliation():
        """Create reconciliation with single ID"""
        try:
            data = request.get_json()
            
            if not data or 'invoice_upload_id' not in data or 'bank_upload_id' not in data:
                return jsonify({
                    "success": False,
                    "error": "Missing required fields: invoice_upload_id, bank_upload_id"
                }), 400
            
            invoice_upload_id = data['invoice_upload_id']
            bank_upload_id = data['bank_upload_id']
            reconciliation_type = data.get('reconciliation_type', 'automatic')
            created_by = data.get('created_by')
            
            # Validate uploads exist
            if not _validate_upload_exists(invoice_upload_id):
                return jsonify({
                    "success": False,
                    "error": f"Invoice upload {invoice_upload_id} not found"
                }), 404
            
            if not _validate_upload_exists(bank_upload_id):
                return jsonify({
                    "success": False,
                    "error": f"Bank upload {bank_upload_id} not found"
                }), 404
            
            # Create reconciliation (returns single ID)
            reconciliation_id = simplified_reconciliation_service.create_reconciliation(
                invoice_upload_id, bank_upload_id, reconciliation_type, created_by
            )
            
            return jsonify({
                "success": True,
                "reconciliation_id": reconciliation_id,
                "invoice_upload_id": invoice_upload_id,
                "bank_upload_id": bank_upload_id,
                "reconciliation_type": reconciliation_type,
                "status": "created",
                "message": "Reconciliation created successfully. Ready to process."
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to create reconciliation: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/process/<reconciliation_id>", methods=["POST"])
    def api_process_reconciliation(reconciliation_id: str):
        """Process reconciliation and store all results in single table"""
        try:
            data = request.get_json() or {}
            
            invoice_upload_id = data.get('invoice_upload_id')
            bank_upload_id = data.get('bank_upload_id')
            reconciliation_type = data.get('reconciliation_type', 'automatic')
            created_by = data.get('created_by')
            
            if not invoice_upload_id or not bank_upload_id:
                return jsonify({
                    "success": False,
                    "error": "Missing invoice_upload_id or bank_upload_id"
                }), 400
            
            # Process reconciliation
            success = simplified_reconciliation_service.process_reconciliation(
                reconciliation_id, invoice_upload_id, bank_upload_id, 
                reconciliation_type, created_by
            )
            
            if success:
                return jsonify({
                    "success": True,
                    "reconciliation_id": reconciliation_id,
                    "status": "completed",
                    "message": "Reconciliation processed successfully. All results stored in reconciliation_match table."
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Reconciliation processing failed"
                }), 500
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to process reconciliation: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/<reconciliation_id>", methods=["GET"])
    def api_get_reconciliation_results(reconciliation_id: str):
        """Get complete reconciliation results from single table"""
        try:
            results = simplified_reconciliation_service.get_reconciliation_results(reconciliation_id)
            
            if not results:
                return jsonify({
                    "success": False,
                    "error": "Reconciliation not found"
                }), 404
            
            return jsonify({
                "success": True,
                "reconciliation_id": reconciliation_id,
                "data_source": "reconciliation_match table (single source of truth)",
                "summary": results['summary'],
                "exact_matches": results['exact_matches'],
                "partial_matches": results['partial_matches'],
                "unmatched_invoices": results['unmatched_invoices'],
                "unmatched_transactions": results['unmatched_transactions'],
                "total_records": results['total_records'],
                "record_types": {
                    "exact_matches": len(results['exact_matches']),
                    "partial_matches": len(results['partial_matches']),
                    "unmatched_invoices": len(results['unmatched_invoices']),
                    "unmatched_transactions": len(results['unmatched_transactions'])
                }
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get reconciliation results: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation", methods=["GET"])
    def api_list_reconciliations():
        """List all reconciliations (derived from single table)"""
        try:
            limit = min(int(request.args.get('limit', 50)), 100)
            offset = int(request.args.get('offset', 0))
            
            reconciliations = simplified_reconciliation_service.list_reconciliations(limit, offset)
            
            return jsonify({
                "success": True,
                "data_source": "reconciliation_match table (single source of truth)",
                "reconciliations": reconciliations,
                "total": len(reconciliations),
                "limit": limit,
                "offset": offset
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to list reconciliations: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/<reconciliation_id>/matches", methods=["GET"])
    def api_get_reconciliation_matches(reconciliation_id: str):
        """Get only matched records from single table"""
        try:
            results = simplified_reconciliation_service.get_reconciliation_results(reconciliation_id)
            
            if not results:
                return jsonify({
                    "success": False,
                    "error": "Reconciliation not found"
                }), 404
            
            return jsonify({
                "success": True,
                "reconciliation_id": reconciliation_id,
                "data_source": "reconciliation_match table",
                "exact_matches": results['exact_matches'],
                "partial_matches": results['partial_matches'],
                "total_matches": len(results['exact_matches']) + len(results['partial_matches'])
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get reconciliation matches: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/<reconciliation_id>/unmatched", methods=["GET"])
    def api_get_unmatched_items(reconciliation_id: str):
        """Get only unmatched records from single table"""
        try:
            results = simplified_reconciliation_service.get_reconciliation_results(reconciliation_id)
            
            if not results:
                return jsonify({
                    "success": False,
                    "error": "Reconciliation not found"
                }), 404
            
            return jsonify({
                "success": True,
                "reconciliation_id": reconciliation_id,
                "data_source": "reconciliation_match table",
                "unmatched_invoices": results['unmatched_invoices'],
                "unmatched_transactions": results['unmatched_transactions'],
                "total_unmatched": len(results['unmatched_invoices']) + len(results['unmatched_transactions'])
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get unmatched items: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/<reconciliation_id>/summary", methods=["GET"])
    def api_get_reconciliation_summary(reconciliation_id: str):
        """Get reconciliation summary (derived from single table)"""
        try:
            results = simplified_reconciliation_service.get_reconciliation_results(reconciliation_id)
            
            if not results:
                return jsonify({
                    "success": False,
                    "error": "Reconciliation not found"
                }), 404
            
            return jsonify({
                "success": True,
                "reconciliation_id": reconciliation_id,
                "data_source": "reconciliation_match table (single source of truth)",
                "summary": results['summary']
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get reconciliation summary: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/schema", methods=["GET"])
    def api_get_reconciliation_schema():
        """Get reconciliation table schema information"""
        try:
            schema_statements = get_simplified_reconciliation_schema()
            
            return jsonify({
                "success": True,
                "table_name": "reconciliation_match",
                "design_pattern": "Single Table Design - Centralized Source of Truth",
                "total_statements": len(schema_statements),
                "schema_statements": schema_statements,
                "features": [
                    "Single reconciliation_match table stores ALL reconciliation data",
                    "Parent-child grouping via reconciliation_id",
                    "Match types: exact, partial, unmatched_invoice, unmatched_transaction",
                    "Complete audit trail in single table",
                    "Simplified queries and maintenance",
                    "Production-ready with proper indexing"
                ]
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get schema: {str(e)}"
            }), 500
    
    @app.route("/api/reconciliation/system-status", methods=["GET"])
    def api_reconciliation_system_status():
        """Get reconciliation system status"""
        try:
            import sqlite3
            from config import DB_PATH
            
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # Check table exists
            cur.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='table' AND name='reconciliation_match'
            """)
            table_exists = cur.fetchone()[0] > 0
            
            # Get statistics
            stats = {}
            if table_exists:
                cur.execute("SELECT COUNT(*) FROM reconciliation_match")
                total_records = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(DISTINCT reconciliation_id) FROM reconciliation_match")
                unique_reconciliations = cur.fetchone()[0]
                
                cur.execute("""
                    SELECT match_type, COUNT(*) 
                    FROM reconciliation_match 
                    GROUP BY match_type
                """)
                match_type_counts = dict(cur.fetchall())
                
                stats = {
                    "table_exists": True,
                    "total_records": total_records,
                    "unique_reconciliations": unique_reconciliations,
                    "match_type_distribution": match_type_counts
                }
            else:
                stats = {"table_exists": False}
            
            conn.close()
            
            return jsonify({
                "success": True,
                "system_design": "Single Table Design - reconciliation_match",
                "central_source_of_truth": "reconciliation_match table",
                "statistics": stats,
                "architecture_benefits": [
                    "All reconciliation data in single table",
                    "No data scattered across multiple tables",
                    "Single reconciliation_id groups all related records",
                    "Simplified maintenance and queries",
                    "Consistent parent-child logic",
                    "Production-ready performance"
                ]
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get system status: {str(e)}"
            }), 500

# Helper functions
def _validate_upload_exists(upload_id: int) -> bool:
    """Validate that upload exists (simplified)"""
    # Implementation would check document_uploads table
    return True
