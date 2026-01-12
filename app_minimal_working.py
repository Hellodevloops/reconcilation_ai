from __future__ import annotations

import io
import os
import re
import csv
import sqlite3
import json
import hashlib
import traceback
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

# Flask imports
from flask import Flask, request, jsonify, send_file, abort

# === Basic Flask App Setup ===
app = Flask(__name__)

# === Rate Limiting Configuration ===
DEFAULT_RATE_LIMIT = "30 per minute"
RATE_LIMITS = {
    "/api/reconcile": "10 per minute",
    "/api/reconciliations": "30 per minute",
    "/api/reconciliations/<int:reconciliation_id>": "60 per minute",
    "/api/reconciliations/<int:reconciliation_id>/matches": "60 per minute",
    "/api/reconciliations/<int:reconciliation_id>/matches/<int:match_id>": "30 per minute",
    "/api/reconciliations/<int:reconciliation_id>/manual-match": "30 per minute",
}

# Initialize rate limiter (commented out for now)
# limiter = Limiter(
#     app,
#     key_func=get_remote_address,
#     default_limits=[DEFAULT_RATE_LIMIT]
# )

# === Database Configuration ===
DB_PATH = "reconcile.db"

# === Basic Logging ===
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Database Helper ===
def init_db() -> None:
    """Initialize database tables"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create reconciliations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reconciliations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                reconciliation_date DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                total_invoices INTEGER DEFAULT 0,
                total_transactions INTEGER DEFAULT 0,
                total_matches INTEGER DEFAULT 0,
                total_amount_matched REAL DEFAULT 0.0,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create reconciliation_matches table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reconciliation_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reconciliation_id INTEGER NOT NULL,
                invoice_description TEXT,
                invoice_amount REAL,
                invoice_date TEXT,
                invoice_vendor_name TEXT,
                invoice_invoice_number TEXT,
                invoice_currency TEXT,
                invoice_reference_id TEXT,
                invoice_document_subtype TEXT,
                bank_description TEXT,
                bank_amount REAL,
                bank_date TEXT,
                bank_vendor_name TEXT,
                bank_invoice_number TEXT,
                bank_currency TEXT,
                bank_reference_id TEXT,
                bank_direction TEXT,
                bank_document_subtype TEXT,
                bank_balance REAL,
                match_score REAL DEFAULT 0.0,
                is_manual_match INTEGER DEFAULT 0,
                invoice_id INTEGER,
                transaction_id INTEGER,
                invoice_file_path TEXT,
                invoice_file_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reconciliation_id) REFERENCES reconciliations (id)
            )
        """)
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization failed: {e}")
        raise

# === Basic Routes ===
@app.route("/")
def index():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "message": "OCR Reconciliation API is running",
        "version": "1.0.0"
    })

@app.route("/api/health")
def health_check():
    """Detailed health check endpoint"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reconciliations")
        reconciliation_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "reconciliation_count": reconciliation_count,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# === Error Handlers ===
@app.errorhandler(404)
def handle_not_found(e):
    """Handle 404 errors."""
    return jsonify({"error": "Not found", "path": request.path}), 404

@app.errorhandler(400)
def handle_bad_request(e):
    """Handle 400 errors."""
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(Exception)
def handle_global_exception(e: Exception):
    """Global exception handler for unhandled errors."""
    error_traceback = traceback.format_exc()
    print(f"Unhandled error: {e}")
    print(error_traceback)
    return jsonify({
        "error": "Internal server error",
        "details": str(e),
        "traceback": error_traceback
    }), 500

# === Main Entry Point ===
if __name__ == "__main__":
    init_db()
    
    # Debug flag should be controlled via environment:
    #   FLASK_DEBUG=1  -> debug mode ON
    #   FLASK_DEBUG=0  -> debug mode OFF (recommended for production)
    debug_flag = os.environ.get("FLASK_DEBUG", "1") == "1"
    
    print("Starting OCR Reconciliation API")
    print(f"Debug mode: {'ON' if debug_flag else 'OFF'}")
    print(f"Database: {DB_PATH}")
    
    app.run(host="0.0.0.0", port=5001, debug=debug_flag)
