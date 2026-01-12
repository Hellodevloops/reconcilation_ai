"""
Financial Data Processing Integration
Production-ready integration for financial data processing system
"""

import os
import sys
from flask import Flask

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from migrations.financial_migration import run_financial_migration, verify_financial_migration, migrate_existing_financial_data
from api.financial_endpoints import register_financial_api_routes

def integrate_financial_processing(app: Flask):
    """Integrate financial data processing into Flask app"""
    
    print("Integrating financial data processing...")
    
    # Run database migration
    print("Running financial database migration...")
    if run_financial_migration():
        print("+ Financial database migration completed")
    else:
        print("- Financial database migration failed")
        return app
    
    # Verify migration
    print("Verifying financial migration...")
    if verify_financial_migration():
        print("+ Financial migration verified successfully")
    else:
        print("- Financial migration verification failed")
        return app
    
    # Migrate existing data
    print("Migrating existing financial data...")
    if migrate_existing_financial_data():
        print("+ Existing financial data migration completed")
    else:
        print("- Existing financial data migration failed")
    
    # Register financial API routes
    print("Registering financial API routes...")
    register_financial_api_routes(app)
    print("+ Financial API routes registered")
    
    print("+ Financial data processing integrated successfully!")
    
    return app

def _update_existing_routes_for_financial(app: Flask):
    """Update existing routes for financial compatibility"""
    
    @app.route("/api/financial/migrate-to-new-system", methods=["POST"])
    def api_migrate_to_financial_system():
        """Migrate existing data to financial schema"""
        try:
            from flask import jsonify
            
            # Run migration
            if run_financial_migration():
                # Verify migration
                if verify_financial_migration():
                    # Migrate existing data
                    if migrate_existing_financial_data():
                        return jsonify({
                            "success": True,
                            "message": "Successfully migrated to financial data processing system"
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
    
    @app.route("/api/financial/system-health", methods=["GET"])
    def api_financial_system_health():
        """Get financial processing system health check"""
        try:
            from flask import jsonify
            import sqlite3
            from config import DB_PATH
            
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            health_status = {
                "database_connection": True,
                "schema_status": "unknown",
                "table_counts": {},
                "system_ready": False
            }
            
            # Check migration status
            cur.execute("""
                SELECT COUNT(*) FROM schema_migrations 
                WHERE migration_name = 'financial_data_processing_v1'
            """)
            migration_complete = cur.fetchone()[0] > 0
            health_status["schema_status"] = "complete" if migration_complete else "incomplete"
            
            # Get table counts
            tables_to_check = [
                'document_uploads', 'extracted_invoices', 'bank_transactions',
                'financial_reconciliations', 'reconciliation_matches', 'unmatched_items'
            ]
            
            for table in tables_to_check:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    health_status["table_counts"][table] = count
                except sqlite3.Error:
                    health_status["table_counts"][table] = "table_missing"
            
            conn.close()
            
            # Determine system readiness
            health_status["system_ready"] = (
                migration_complete and
                all(isinstance(count, int) for count in health_status["table_counts"].values())
            )
            
            return jsonify({
                "success": True,
                "health": health_status,
                "recommendations": _get_health_recommendations(health_status)
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Health check failed: {str(e)}"
            }), 500
    
    def _get_health_recommendations(health_status):
        """Get health recommendations based on system status"""
        recommendations = []
        
        if not health_status["schema_status"] == "complete":
            recommendations.append("Run database migration: POST /api/financial/migrate-to-new-system")
        
        if health_status["table_counts"].get("document_uploads", 0) == 0:
            recommendations.append("Upload some documents to test the system")
        
        if health_status["table_counts"].get("financial_reconciliations", 0) == 0:
            recommendations.append("Create a reconciliation to test matching functionality")
        
        if not health_status["system_ready"]:
            recommendations.append("System not ready - check migration and table status")
        
        return recommendations
    
    print("+ Updated existing routes for financial compatibility")
    
    return app
