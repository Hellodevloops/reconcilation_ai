"""
Unified Document Processing Integration
Production-ready integration for unified invoice and bank statement processing
"""

import os
import sys
from flask import Flask

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from migrations.unified_migration import run_unified_migration, verify_unified_migration, migrate_existing_data
from api.unified_endpoints import register_unified_document_routes

def integrate_unified_document_support(app: Flask):
    """Integrate unified document processing into Flask app"""
    
    print("Integrating unified document processing...")
    
    # Run database migration
    print("Running unified database migration...")
    if run_unified_migration():
        print("+ Unified database migration completed")
    else:
        print("- Unified database migration failed")
        return app
    
    # Verify migration
    print("Verifying unified migration...")
    if verify_unified_migration():
        print("+ Unified migration verified successfully")
    else:
        print("- Unified migration verification failed")
        return app
    
    # Migrate existing data
    print("Migrating existing data...")
    if migrate_existing_data():
        print("+ Existing data migration completed")
    else:
        print("- Existing data migration failed")
    
    # Register unified API routes
    print("Registering unified document API routes...")
    register_unified_document_routes(app)
    print("+ Unified API routes registered")
    
    print("+ Unified document processing integrated successfully!")
    
    return app

def _update_existing_routes_for_unified(app: Flask):
    """Update existing routes for unified compatibility"""
    
    @app.route("/api/migrate-to-unified", methods=["POST"])
    def api_migrate_to_unified():
        """Migrate existing data to unified schema"""
        try:
            from flask import jsonify
            
            # Run migration
            if run_unified_migration():
                # Verify migration
                if verify_unified_migration():
                    # Migrate existing data
                    if migrate_existing_data():
                        return jsonify({
                            "success": True,
                            "message": "Successfully migrated to unified document processing"
                        })
                    else:
                        return jsonify({
                            "success": False,
                            "error": "Data migration failed"
                        }), 500
                else:
                    return jsonify({
                        "success": False,
                        "error": "Migration verification failed"
                    }), 500
            else:
                return jsonify({
                    "success": False,
                    "error": "Migration failed"
                }), 500
                
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Migration failed: {str(e)}"
            }), 500
    
    @app.route("/api/unified-status", methods=["GET"])
    def api_unified_status():
        """Get unified processing system status"""
        try:
            from flask import jsonify
            import sqlite3
            from config import DB_PATH
            
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # Check migration status
            cur.execute("""
                SELECT COUNT(*) FROM schema_migrations 
                WHERE migration_name = 'unified_document_processing_v1'
            """)
            migration_complete = cur.fetchone()[0] > 0
            
            # Get document counts
            cur.execute("SELECT COUNT(*) FROM document_uploads")
            total_documents = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM document_uploads WHERE document_type = 'invoice'")
            invoice_documents = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM document_uploads WHERE document_type = 'bank_statement'")
            bank_documents = cur.fetchone()[0]
            
            # Get processing counts
            cur.execute("SELECT COUNT(*) FROM extracted_invoices")
            total_invoices = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM bank_transactions")
            total_transactions = cur.fetchone()[0]
            
            conn.close()
            
            return jsonify({
                "success": True,
                "unified_system": {
                    "migration_complete": migration_complete,
                    "total_documents": total_documents,
                    "invoice_documents": invoice_documents,
                    "bank_documents": bank_documents,
                    "total_invoices": total_invoices,
                    "total_transactions": total_transactions,
                    "supported_document_types": ["invoice", "bank_statement"],
                    "features": [
                        "Single primary key per file upload",
                        "Parent-child data relationships",
                        "Unified processing workflow",
                        "Background processing",
                        "Duplicate detection",
                        "Production-ready error handling"
                    ]
                }
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to get unified status: {str(e)}"
            }), 500
    
    print("+ Updated existing routes for unified compatibility")
    
    return app
