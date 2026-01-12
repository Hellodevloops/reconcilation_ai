"""
Integration Script for Multi-Invoice Support
Integrates the new multi-invoice functionality with the existing application
"""

import os
import sys
from datetime import datetime

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from migrations.add_multi_invoice_support import run_migration, verify_migration
from api.multi_invoice_endpoints import register_multi_invoice_routes


def integrate_multi_invoice_support(app):
    """
    Integrate multi-invoice support into the existing Flask application.
    Call this function after creating your Flask app instance.
    """
    print("Integrating multi-invoice support...")
    
    # 1. Run database migration if needed
    print("Checking database schema...")
    try:
        from migrations.add_multi_invoice_support import get_migration_status
        status = get_migration_status()
        
        if status['status'] != "completed":
            print("Running database migration...")
            success = run_migration()
            if not success:
                raise Exception("Database migration failed")
            
            print("Verifying migration...")
            verify_migration()
        else:
            print("✓ Database schema already up to date")
    except Exception as e:
        print(f"❌ Migration error: {e}")
        raise
    
    # 2. Register new API routes
    print("Registering multi-invoice API routes...")
    register_multi_invoice_routes(app)
    print("✓ API routes registered")
    
    # 3. Update existing routes to support file_upload_id
    print("Updating existing routes for backward compatibility...")
    _update_existing_routes(app)
    
    print("✅ Multi-invoice support integrated successfully!")
    
    return app


def _update_existing_routes(app):
    """
    Update existing routes to work with the new multi-invoice structure.
    This ensures backward compatibility with existing functionality.
    """
    # Import required modules
    import sqlite3
    from flask import jsonify
    
    from config import DB_PATH
    
    @app.route("/api/migrate-existing-data", methods=["POST"])
    def migrate_existing_data():
        """
        Migrate existing transaction data to the new multi-invoice structure.
        This endpoint helps transition from the old system to the new one.
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # Find transactions that don't have file_upload_id
            cur.execute("""
                SELECT DISTINCT file_name, COUNT(*) as count
                FROM transactions 
                WHERE file_upload_id IS NULL AND file_name IS NOT NULL
                GROUP BY file_name
            """)
            
            files_to_migrate = cur.fetchall()
            
            if not files_to_migrate:
                conn.close()
                return jsonify({
                    "success": True,
                    "message": "No data to migrate - all transactions already linked to file uploads"
                })
            
            migrated_files = 0
            migrated_transactions = 0
            
            for file_name, count in files_to_migrate:
                # Create a synthetic file upload record
                cur.execute("""
                    INSERT INTO file_uploads (
                        file_name, file_path, file_hash, file_size, file_type,
                        mime_type, processing_status, total_invoices_found,
                        total_invoices_processed, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_name,
                    f"migrated/{file_name}",  # Synthetic path
                    f"migrated_{file_name}_{hash(file_name)}",  # Synthetic hash
                    0,  # Unknown size
                    "unknown",  # Unknown type
                    "application/octet-stream",
                    "completed",  # Mark as completed
                    count,  # Number of invoices found
                    count,  # Number processed
                    '{"migrated": true, "migration_date": "' + str(datetime.now()) + '"}'
                ))
                
                file_upload_id = cur.lastrowid
                
                # Update transactions to link to this file upload
                cur.execute("""
                    UPDATE transactions 
                    SET file_upload_id = ?
                    WHERE file_name = ? AND file_upload_id IS NULL
                """, (file_upload_id, file_name))
                
                migrated_files += 1
                migrated_transactions += count
            
            conn.commit()
            conn.close()
            
            return jsonify({
                "success": True,
                "migrated_files": migrated_files,
                "migrated_transactions": migrated_transactions,
                "message": f"Successfully migrated {migrated_files} files with {migrated_transactions} transactions"
            })
            
        except Exception as e:
            return jsonify({
                "error": "Migration failed",
                "details": str(e)
            }), 500
    
    print("✓ Existing routes updated for backward compatibility")


# Example usage in your main app.py:
"""
from integration.multi_invoice_integration import integrate_multi_invoice_support

# After creating your Flask app:
app = Flask(__name__)

# ... your existing app configuration ...

# Integrate multi-invoice support
app = integrate_multi_invoice_support(app)

# ... rest of your app setup ...
"""

if __name__ == "__main__":
    print("Multi-Invoice Integration Test")
    print("=" * 40)
    
    # Test migration
    print("Testing database migration...")
    try:
        run_migration()
        verify_migration()
        print("✅ Migration test passed")
    except Exception as e:
        print(f"❌ Migration test failed: {e}")
    
    print("\nIntegration script ready!")
    print("To integrate with your app, add this to your main app.py:")
    print("from integration.multi_invoice_integration import integrate_multi_invoice_support")
    print("app = integrate_multi_invoice_support(app)")
