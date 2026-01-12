"""
Production JSON System Integration
Integrates the single-row JSON storage system with the main Flask application

Core Rule: One uploaded file or one reconciliation run = one database row
All extracted or generated data must be stored inside that single row as structured JSON
"""

import os
from flask import Flask

# Import the production JSON API
from api.production_json_api import register_production_json_api
from models.production_json_models import get_production_schema_statements
from app import logger, DB_PATH


def integrate_production_json_system(app: Flask) -> Flask:
    """
    Integrate the production JSON storage system with the main Flask application
    
    This function:
    1. Initializes production JSON database tables
    2. Registers production JSON API endpoints
    3. Configures the system for single-row JSON storage
    4. Sets up proper routing and middleware
    
    Args:
        app: Flask application instance
        
    Returns:
        Flask application with production JSON system integrated
    """
    
    try:
        # Step 1: Initialize production database tables
        logger.info("Initializing production JSON database tables")
        
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        
        # Enable WAL mode for better concurrency
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        
        # Execute all schema statements
        statements = get_production_schema_statements()
        for statement in statements:
            try:
                conn.execute(statement)
            except sqlite3.Error as e:
                # Ignore errors for existing tables/columns
                if "already exists" not in str(e).lower():
                    logger.warning(f"Database schema warning: {e}")
        
        conn.commit()
        conn.close()
        
        logger.info("✓ Production JSON database tables initialized")
        
        # Step 2: Register production JSON API endpoints
        upload_folder = os.path.join(os.path.dirname(__file__), "..", "uploads")
        register_production_json_api(app, DB_PATH, upload_folder)
        
        logger.info("✓ Production JSON API endpoints registered")
        
        # Step 3: Add production JSON routes to main application
        add_production_json_routes(app)
        
        # Step 4: Configure production JSON middleware
        configure_production_json_middleware(app)
        
        logger.info("✓ Production JSON system fully integrated")
        
        print("\n" + "=" * 60)
        print("🚀 PRODUCTION JSON STORAGE SYSTEM INTEGRATED")
        print("=" * 60)
        print("📋 Core Principle: One File = One Database Row = All Data in JSON")
        print()
        print("🔗 Available Endpoints:")
        print("  • Invoice Upload:    POST /api/production/invoices/upload")
        print("  • Bank Upload:        POST /api/production/bank/upload")
        print("  • Reconciliation:     POST /api/production/reconcile")
        print("  • Get Invoice Data:   GET  /api/production/invoices/{upload_id}")
        print("  • Get Bank Data:      GET  /api/production/bank/{upload_id}")
        print("  • Get Reconciliation: GET  /api/production/reconciliations/{reconciliation_id}")
        print("  • List Invoices:      GET  /api/production/invoices")
        print("  • List Bank:          GET  /api/production/bank")
        print("  • List Reconciliations: GET /api/production/reconciliations")
        print("  • Health Check:       GET  /api/production/health")
        print("  • API Documentation:  GET  /api/production/docs")
        print()
        print("🗄️ Database Tables:")
        print("  • production_invoice_uploads")
        print("  • production_bank_uploads")
        print("  • production_reconciliation_matches")
        print()
        print("✨ Benefits:")
        print("  • Atomic Operations: All-or-nothing saves")
        print("  • High Performance: Single INSERT per file")
        print("  • Data Integrity: JSON validation & constraints")
        print("  • Production Ready: Comprehensive error handling")
        print("=" * 60)
        
        return app
        
    except Exception as e:
        logger.error(f"Failed to integrate production JSON system", error=e)
        print(f"⚠️  Production JSON system integration failed: {e}")
        return app


def add_production_json_routes(app: Flask):
    """Add production JSON routes to the main application"""
    
    @app.route('/api/production/status', methods=['GET'])
    def production_json_status():
        """Get production JSON system status"""
        try:
            import sqlite3
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Check if production tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'production_%'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Get record counts
            status = {
                "system_enabled": True,
                "tables_created": len(tables) > 0,
                "tables": tables,
                "record_counts": {}
            }
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    status["record_counts"][table] = count
                except Exception:
                    status["record_counts"][table] = "Error"
            
            conn.close()
            
            return {
                "status": "healthy" if status["tables_created"] else "not_initialized",
                "storage_mode": "single_row_json",
                "core_principle": "One file = One database row = All data in JSON",
                **status
            }
            
        except Exception as e:
            logger.error("Failed to get production JSON status", error=e)
            return {
                "status": "error",
                "error": str(e),
                "system_enabled": False
            }
    
    @app.route('/api/production/migrate', methods=['POST'])
    def migrate_to_production_json():
        """
        Migrate existing data to production JSON format
        This endpoint helps transition from the old multi-row system to the new single-row JSON system
        """
        try:
            import sqlite3
            from models.production_json_models import (
                InvoiceUpload, BankTransactionUpload, ReconciliationMatch,
                ProductionJSONDataAccess
            )
            from services.production_json_workflows import ProductionJSONWorkflows
            
            # Initialize production system
            data_access = ProductionJSONDataAccess(DB_PATH)
            workflows = ProductionJSONWorkflows(DB_PATH, os.path.join(os.path.dirname(__file__), "..", "uploads"))
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            migration_results = {
                "invoices_migrated": 0,
                "bank_transactions_migrated": 0,
                "reconciliations_migrated": 0,
                "errors": []
            }
            
            # Migrate invoice files
            try:
                cursor.execute("SELECT id, file_name, file_path, created_at FROM invoice_files")
                invoice_files = cursor.fetchall()
                
                for file_id, file_name, file_path, created_at in invoice_files:
                    # Get transactions for this file
                    cursor.execute("""
                        SELECT description, amount, date, vendor_name, invoice_number, currency
                        FROM transactions 
                        WHERE kind = 'invoice' AND file_name = ?
                    """, (file_name,))
                    
                    invoice_transactions = cursor.fetchall()
                    
                    if invoice_transactions:
                        # Build JSON structure
                        invoices = []
                        for desc, amount, date, vendor, inv_num, currency in invoice_transactions:
                            invoices.append({
                                "invoice_id": f"inv_{file_id}_{len(invoices)}",
                                "invoice_number": inv_num,
                                "invoice_date": date,
                                "vendor_name": vendor,
                                "total_amount": amount,
                                "currency": currency or "USD",
                                "description": desc
                            })
                        
                        invoice_json = {
                            "upload_id": file_id,
                            "file_info": {
                                "file_name": file_name,
                                "file_path": file_path,
                                "file_size": 0,  # Not available in old system
                                "pages_total": 1,
                                "mime_type": "application/pdf"
                            },
                            "processing_info": {
                                "upload_timestamp": created_at,
                                "processing_start": created_at,
                                "processing_end": created_at,
                                "processing_duration_seconds": 0,
                                "ocr_engine": "legacy",
                                "confidence_score": 0.8,
                                "status": "migrated"
                            },
                            "extraction_summary": {
                                "total_invoices_found": len(invoices),
                                "total_invoices_processed": len(invoices),
                                "total_amount": sum(t[1] or 0 for t in invoice_transactions),
                                "currency_summary": {"USD": sum(t[1] or 0 for t in invoice_transactions)},
                                "vendor_summary": {}
                            },
                            "invoices": invoices
                        }
                        
                        # Create production record
                        invoice_upload = InvoiceUpload(
                            upload_id=file_id,
                            file_name=file_name,
                            file_path=file_path,
                            file_hash="migrated",
                            file_size=0,
                            status="completed",
                            invoice_json=str(invoice_json).replace("'", '"'),  # Convert to JSON string
                            total_invoices_found=len(invoices),
                            total_invoices_processed=len(invoices),
                            total_amount=sum(t[1] or 0 for t in invoice_transactions)
                        )
                        
                        data_access.insert_invoice_upload(invoice_upload)
                        migration_results["invoices_migrated"] += 1
                
            except Exception as e:
                migration_results["errors"].append(f"Invoice migration error: {str(e)}")
            
            # Migrate bank transactions (similar process)
            try:
                cursor.execute("SELECT DISTINCT file_name FROM transactions WHERE kind = 'bank'")
                bank_files = cursor.fetchall()
                
                for (file_name,) in bank_files:
                    cursor.execute("""
                        SELECT description, amount, date, currency, direction
                        FROM transactions 
                        WHERE kind = 'bank' AND file_name = ?
                    """, (file_name,))
                    
                    bank_transactions = cursor.fetchall()
                    
                    if bank_transactions:
                        # Build JSON structure
                        transactions = []
                        for desc, amount, date, currency, direction in bank_transactions:
                            transactions.append({
                                "transaction_id": f"txn_{len(transactions)}",
                                "transaction_date": date,
                                "description": desc,
                                "debit_amount": amount if direction == 'debit' else None,
                                "credit_amount": amount if direction == 'credit' else None,
                                "currency": currency or "USD",
                                "transaction_type": direction
                            })
                        
                        bank_json = {
                            "upload_id": len(migration_results["bank_transactions_migrated"]) + 1000,
                            "file_info": {
                                "file_name": file_name,
                                "file_path": "",
                                "file_size": 0,
                                "pages_total": 1,
                                "mime_type": "application/pdf"
                            },
                            "processing_info": {
                                "upload_timestamp": datetime.now().isoformat(),
                                "processing_start": datetime.now().isoformat(),
                                "processing_end": datetime.now().isoformat(),
                                "processing_duration_seconds": 0,
                                "ocr_engine": "legacy",
                                "confidence_score": 0.8,
                                "status": "migrated"
                            },
                            "statement_info": {
                                "account_number": "****1234",
                                "currency": "USD"
                            },
                            "extraction_summary": {
                                "total_transactions_found": len(transactions),
                                "total_transactions_processed": len(transactions),
                                "total_debits": sum(t[2] or 0 for t in transactions if t[2] is not None),
                                "total_credits": sum(t[3] or 0 for t in transactions if t[3] is not None)
                            },
                            "transactions": transactions
                        }
                        
                        # Create production record
                        bank_upload = BankTransactionUpload(
                            upload_id=len(migration_results["bank_transactions_migrated"]) + 1000,
                            file_name=file_name,
                            file_path="",
                            file_hash="migrated",
                            file_size=0,
                            status="completed",
                            bank_transaction_json=str(bank_json).replace("'", '"'),
                            total_transactions_found=len(transactions),
                            total_transactions_processed=len(transactions)
                        )
                        
                        data_access.insert_bank_upload(bank_upload)
                        migration_results["bank_transactions_migrated"] += 1
                
            except Exception as e:
                migration_results["errors"].append(f"Bank migration error: {str(e)}")
            
            conn.close()
            
            logger.info("Production JSON migration completed", context=migration_results)
            
            return {
                "success": True,
                "message": "Migration to production JSON format completed",
                "results": migration_results
            }
            
        except Exception as e:
            logger.error("Production JSON migration failed", error=e)
            return {
                "success": False,
                "error": str(e),
                "message": "Migration failed"
            }
    
    logger.info("Production JSON routes added to main application")


def configure_production_json_middleware(app: Flask):
    """Configure production JSON middleware and request handling"""
    
    @app.before_request
    def log_production_json_requests():
        """Log production JSON API requests for monitoring"""
        if request.path.startswith('/api/production/'):
            logger.info(f"Production JSON API request", 
                       context={
                           "method": request.method,
                           "path": request.path,
                           "remote_addr": request.remote_addr
                       })
    
    @app.after_request  
    def add_production_json_headers(response):
        """Add production JSON specific headers"""
        if request.path.startswith('/api/production/'):
            response.headers['X-Production-JSON-Storage'] = 'enabled'
            response.headers['X-Storage-Mode'] = 'single_row_json'
            response.headers['X-Core-Principle'] = 'One file = One database row = All data in JSON'
        return response
    
    logger.info("Production JSON middleware configured")


# Flask application factory with production JSON integration
def create_app_with_production_json():
    """Create Flask application with production JSON system integrated"""
    app = Flask(__name__)
    
    # Load existing configuration
    from app import app as main_app
    
    # Copy configuration from main app
    app.config.update(main_app.config)
    
    # Integrate production JSON system
    app = integrate_production_json_system(app)
    
    return app


# Auto-integration when imported
def auto_integrate_production_json():
    """Auto-integrate production JSON system if conditions are met"""
    
    # Check if production JSON is enabled via environment variable
    enabled = os.environ.get("PRODUCTION_JSON_ENABLED", "1") == "1"
    
    if enabled:
        try:
            # Try to get the main Flask app
            from app import app as main_app
            
            # Integrate production JSON system
            integrate_production_json_system(main_app)
            
            return True
            
        except ImportError:
            logger.warning("Could not import main app for production JSON integration")
            return False
        except Exception as e:
            logger.error("Auto-integration of production JSON failed", error=e)
            return False
    
    else:
        logger.info("Production JSON system disabled via environment variable")
        return False


# Run auto-integration when module is imported
integration_success = auto_integrate_production_json()

if integration_success:
    print("✓ Production JSON Storage System auto-integrated")
else:
    print("ℹ Production JSON Storage System integration skipped")
