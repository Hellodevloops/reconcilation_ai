from __future__ import annotations

import io
import os
import re
import csv
import traceback
import time
import threading
import subprocess
import sys
import json
import logging
import hashlib
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from functools import lru_cache

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from api.manual_entry_endpoint import manual_entry_bp
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import pymysql
import pytesseract
from PyPDF2 import PdfReader
import joblib
import pandas as pd
from dotenv import load_dotenv
try:
    from flasgger import Swagger
    SWAGGER_AVAILABLE = True
except ImportError:
    SWAGGER_AVAILABLE = False


class UserInputError(Exception):
    """Custom exception type for user-facing validation errors."""
    pass


# === Structured Logging System ===

class StructuredLogger:
    """
    Production-ready structured logging system.
    Logs include: timestamp, level, message, context, and error details.
    """
    
    def __init__(self, name: str = "reconcile_app"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            # Console handler with structured format
            console_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def _log(self, level: str, message: str, context: Optional[Dict[str, Any]] = None, 
             error: Optional[Exception] = None):
        """Internal method to create structured log entries."""
        log_data = {
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "level": level
        }
        
        if context:
            log_data["context"] = context
        
        if error:
            log_data["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc() if app.debug else None
            }
        
        # Format for console output
        context_str = f" | Context: {json.dumps(context)}" if context else ""
        error_str = f" | Error: {type(error).__name__}: {str(error)}" if error else ""
        
        log_message = f"{message}{context_str}{error_str}"
        
        if level == "DEBUG":
            self.logger.debug(log_message)
        elif level == "INFO":
            self.logger.info(log_message)
        elif level == "WARNING":
            self.logger.warning(log_message)
        elif level == "ERROR":
            self.logger.error(log_message)
        elif level == "CRITICAL":
            self.logger.critical(log_message)
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log debug message."""
        self._log("DEBUG", message, context)
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log info message."""
        self._log("INFO", message, context)
    
    def warning(self, message: str, context: Optional[Dict[str, Any]] = None, 
                error: Optional[Exception] = None):
        """Log warning message."""
        self._log("WARNING", message, context, error)
    
    def error(self, message: str, context: Optional[Dict[str, Any]] = None, 
              error: Optional[Exception] = None):
        """Log error message."""
        self._log("ERROR", message, context, error)
    
    def critical(self, message: str, context: Optional[Dict[str, Any]] = None, 
                error: Optional[Exception] = None):
        """Log critical message."""
        self._log("CRITICAL", message, context, error)


# Initialize structured logger
logger = StructuredLogger("reconcile_app")


#
# === Configuration & environment ===
#

# Load variables from a .env file if present (local development convenience)
load_dotenv()

# Optional: Tesseract path from environment (so it is not hard-coded in code)
TESSERACT_CMD = os.environ.get("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Database configuration - now using MySQL
from config import get_database_url
from database_manager import db_manager

# Directory for storing uploaded invoice files
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
INVOICE_FOLDER = os.path.join(UPLOAD_FOLDER, "invoices")
os.makedirs(INVOICE_FOLDER, exist_ok=True)

INVOICE_JSON_FOLDER = os.path.join(UPLOAD_FOLDER, "invoice_json")
os.makedirs(INVOICE_JSON_FOLDER, exist_ok=True)

# Maximum number of invoice files allowed per request (input validation)
MAX_INVOICE_FILES = int(os.environ.get("MAX_INVOICE_FILES", "10"))

# === API Rate Limiting Configuration ===
# Basic per-IP rate limits for API calls (can be tuned via environment)
DEFAULT_RATE_LIMIT = os.environ.get("RATE_LIMIT", "30 per minute")

# Per-endpoint rate limits (more restrictive for resource-intensive endpoints)
# Format: "number per time_period" (e.g., "10 per minute", "5 per hour")
RATE_LIMITS = {
    # Heavy endpoints (file processing, reconciliation)
    "/api/reconcile": os.environ.get("RATE_LIMIT_RECONCILE", "10 per minute"),
    "/api/process-document": os.environ.get("RATE_LIMIT_PROCESS_DOC", "20 per minute"),
    
    # Medium endpoints (data retrieval)
    "/api/reconciliations": os.environ.get("RATE_LIMIT_LIST", "30 per minute"),
    "/api/reconciliations/<int:reconciliation_id>/matches": os.environ.get("RATE_LIMIT_MATCHES", "60 per minute"),
    
    # Light endpoints (health, export, delete)
    "/api/health": os.environ.get("RATE_LIMIT_HEALTH", "120 per minute"),
    "/api/reconciliations/<int:reconciliation_id>/matches/export": os.environ.get("RATE_LIMIT_EXPORT", "20 per minute"),
    "/api/reconciliations/<int:reconciliation_id>/matches/<int:match_id>": os.environ.get("RATE_LIMIT_DELETE", "30 per minute"),
    "/api/reconciliations/<int:reconciliation_id>/manual-match": os.environ.get("RATE_LIMIT_MANUAL_MATCH", "30 per minute"),
}

# Maximum allowed rows for large tabular files to avoid accidental huge uploads
MAX_EXCEL_ROWS = int(os.environ.get("MAX_EXCEL_ROWS", "50000"))
MAX_CSV_ROWS = int(os.environ.get("MAX_CSV_ROWS", "50000"))

# === File Size Limits & Memory Protection ===
# Maximum file sizes (in bytes) to prevent memory exhaustion and DoS attacks
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "100"))  # 100 MB default
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Maximum total size for all files in a single request
MAX_TOTAL_SIZE_MB = int(os.environ.get("MAX_TOTAL_SIZE_MB", "500"))  # 500 MB default
MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024

# Maximum memory usage estimate (for processing large files)
# This is a conservative estimate to prevent OOM errors
MAX_MEMORY_USAGE_MB = int(os.environ.get("MAX_MEMORY_USAGE_MB", "2000"))  # 2 GB default

# === Performance Optimization: Caching Configuration ===
# Enable/disable caching for frequently accessed data
ENABLE_CACHING = os.environ.get("ENABLE_CACHING", "1") == "1"
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))  # 5 minutes default

# Simple in-memory cache (for production, use Redis or similar)
_cache: Dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()

# Serialize SQLite write operations to avoid intermittent "database is locked"
# errors under concurrent requests/background threads.
_db_write_lock = threading.RLock()

# === Progress Tracking for Long-Running Operations ===
# Store progress for reconciliation jobs
_progress_tracker: Dict[str, Dict[str, Any]] = {}
_progress_lock = threading.Lock()


def get_progress(job_id: str) -> Optional[Dict[str, Any]]:
    """Get progress for a job."""
    with _progress_lock:
        return _progress_tracker.get(job_id)


def set_progress(job_id: str, status: str, progress: float, message: str = "", data: Dict[str, Any] = None):
    """Set progress for a job."""
    with _progress_lock:
        _progress_tracker[job_id] = {
            "status": status,  # "pending", "processing", "completed", "error"
            "progress": progress,  # 0.0 to 1.0
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "data": data or {}
        }


def clear_progress(job_id: str):
    """Clear progress for a job."""
    with _progress_lock:
        if job_id in _progress_tracker:
            del _progress_tracker[job_id]


def cache_get(key: str) -> Optional[Any]:
    """Get value from cache if not expired."""
    if not ENABLE_CACHING:
        return None
    
    with _cache_lock:
        if key in _cache:
            value, expiry = _cache[key]
            if time.time() < expiry:
                return value
            else:
                del _cache[key]
    return None


def cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS):
    """Set value in cache with TTL."""
    if not ENABLE_CACHING:
        return
    
    with _cache_lock:
        expiry = time.time() + ttl
        _cache[key] = (value, expiry)
        
        # Cleanup expired entries periodically (every 100 entries)
        if len(_cache) > 100:
            now = time.time()
            expired_keys = [k for k, (_, exp) in _cache.items() if exp < now]
            for k in expired_keys:
                del _cache[k]


def cache_clear():
    """Clear all cache entries."""
    with _cache_lock:
        _cache.clear()

# Minimum absolute amount to consider a line as a real transaction
# (lines with amounts smaller than this are treated as noise).
MIN_TRANSACTION_AMOUNT = 1.0

# Common "noise" phrases often found in bank PDFs (headers, footers, legal text, etc.)
BANK_NOISE_KEYWORDS = [
    "bank account legal",
    "clearbank limited",
    "tide platform limited",
    "your eligible deposits",
    "financial services compensation scheme",
    "for further information",
    "sort code",
    "account number",
    "page  of",  # pagination
    "bank statement",
    "this is not a statement",
    "no transactions in the period",
]

# Common keywords that indicate a real transaction row in Tide-style statements
TIDE_TRANSACTION_KEYWORDS = [
    "domestic transfer",
    "card transaction",
    "direct debit",
    "internal book transfer",
]


# Allowed file extensions and MIME types for strict validation
INVOICE_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".xlsx", ".xls"}
BANK_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}

INVOICE_ALLOWED_MIMETYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    # Excel (both legacy and new)
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

BANK_ALLOWED_MIMETYPES = INVOICE_ALLOWED_MIMETYPES.union(
    {
        "text/csv",
        "application/csv",
    }
)


app = Flask(__name__, static_folder="static", static_url_path="/static")

# Register blueprints
app.register_blueprint(manual_entry_bp)

# === Security Configuration ===
# CORS configuration (Cross-Origin Resource Sharing)
# Allow specific origins in production, or all for development
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
CORS_ENABLED = os.environ.get("CORS_ENABLED", "1") == "1"

@app.after_request
def after_request(response):
    """Add security headers and CORS support."""
    if CORS_ENABLED:
        origin = request.headers.get("Origin")
        if origin and (origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Credentials"] = "true"
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response

@app.route("/api/*", methods=["OPTIONS"])
def handle_options():
    """Handle CORS preflight requests."""
    return "", 200

# Attach a rate limiter to the app (protects all routes by default)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[DEFAULT_RATE_LIMIT],
)

# === API Documentation (Swagger/OpenAPI) ===
if SWAGGER_AVAILABLE:
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/api/swagger.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/api/docs"
    }
    
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "OCR Reconciliation API",
            "description": "API for OCR-based invoice and bank statement reconciliation with ML matching",
            "version": "1.0.0",
            "contact": {
                "name": "API Support"
            }
        },
        "basePath": "/api",
        "schemes": ["http", "https"],
        "securityDefinitions": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header"
            }
        }
    }
    
    swagger = Swagger(app, config=swagger_config, template=swagger_template)
    print("✓ Swagger API documentation available at /api/docs")
else:
    print("ℹ Swagger not available. Install flasgger for API documentation: pip install flasgger")

# === Financial Data Processing Integration ===
try:
    from integration.financial_integration import integrate_financial_processing
    app = integrate_financial_processing(app)
    print("✓ Financial data processing integrated successfully")
except ImportError as e:
    print(f"⚠ Financial data processing integration not available: {e}")
except Exception as e:
    print(f"⚠ Financial data processing integration failed: {e}")

# === Unified Document Processing Integration ===
try:
    from integration.unified_integration import integrate_unified_document_support
    app = integrate_unified_document_support(app)
    print("✓ Unified document processing integrated successfully")
except ImportError as e:
    print(f"⚠ Unified document processing integration not available: {e}")
except Exception as e:
    print(f"⚠ Unified document processing integration failed: {e}")

# === Multi-Invoice Support Integration ===
try:
    from integration.multi_invoice_integration import integrate_multi_invoice_support
    app = integrate_multi_invoice_support(app)
    print("✓ Multi-invoice support integrated successfully")
except ImportError as e:
    print(f"⚠ Multi-invoice integration not available: {e}")
except Exception as e:
    print(f"⚠ Multi-invoice integration failed: {e}")

# === Enhanced Error Handling ===
try:
    from utils.error_handlers import register_error_handlers, APIError, ValidationError, NotFoundError
    register_error_handlers(app)
    print("✓ Enhanced error handling registered")
except ImportError:
    print("ℹ Enhanced error handlers not available")

# === Request Logging ===
try:
    from utils.request_logging import register_request_logging
    register_request_logging(app)
    print("✓ Request logging middleware registered")
except ImportError:
    print("ℹ Request logging not available")

# === Database Optimization ===
try:
    from utils.db_optimization import add_database_indexes, optimize_database
    from config import DB_TYPE, DB_PATH
    if DB_TYPE == "sqlite" and os.path.exists(DB_PATH):
        add_database_indexes(DB_PATH)
        print("✓ Database indexes added")
except ImportError:
    print("ℹ Database optimization not available")

# === Monitoring & Observability ===
try:
    from utils.monitoring import register_monitoring_routes
    register_monitoring_routes(app)
except ImportError:
    print("ℹ Monitoring not available")

# === Bank Statement Routes (STRICT: One file = ONE record) ===
try:
    from api.bank_statement_endpoints import register_bank_statement_routes
    register_bank_statement_routes(app)
    print("✓ Bank statement routes registered (STRICT implementation)")
except ImportError as e:
    print(f"ℹ Bank statement routes not available: {e}")

# === Invoice Upload Routes ===
# Note: Already registered by integrate_multi_invoice_support above
print("✓ Invoice upload routes already registered by integration")

# === Global Error Handler for Production ===

@app.errorhandler(Exception)
def handle_global_exception(e: Exception):
    """
    Global exception handler for unhandled errors.
    Provides structured error responses and logging.
    """
    error_traceback = traceback.format_exc()
    
    # Log the error with context
    logger.error(
        "Unhandled exception in application",
        context={
            "error_type": type(e).__name__,
            "endpoint": request.path if request else None,
            "method": request.method if request else None,
        },
        error=e
    )
    
    # Return appropriate error response
    if app.debug:
        return jsonify({
            "error": "Internal server error",
            "message": str(e),
            "type": type(e).__name__,
            "traceback": error_traceback
        }), 500
    else:
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }), 500


@app.errorhandler(404)
def handle_not_found(e):
    """Handle 404 errors."""
    logger.warning("404 Not Found", context={"path": request.path})
    return jsonify({"error": "Not found", "path": request.path}), 404


@app.errorhandler(400)
def handle_bad_request(e):
    """Handle 400 errors."""
    logger.warning("400 Bad Request", context={"path": request.path})
    return jsonify({"error": "Bad request"}), 400

# Optional ML model (loaded from model.pkl if available)
MODEL = None
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")
MODEL_LOAD_ERROR = None  # Track the last error for debugging
MODEL_FEATURE_COUNT = None  # Track expected feature count

def _validate_ml_model(model) -> tuple[bool, str | None]:
    """
    Validate that the loaded ML model is usable.
    Returns (is_valid, error_message)
    """
    if model is None:
        return False, "Model is None"
    
    # Check if model has required methods
    if not hasattr(model, 'predict_proba'):
        return False, "Model missing predict_proba method"
    
    # Try to get feature count from model (if available)
    try:
        if hasattr(model, 'n_features_in_'):
            return True, None
        elif hasattr(model, 'feature_importances_'):
            # RandomForest or similar - try to infer feature count
            return True, None
    except Exception:
        pass
    
    return True, None  # Assume valid if basic checks pass

if os.path.exists(MODEL_PATH):
    try:
        MODEL = joblib.load(MODEL_PATH)
        is_valid, error_msg = _validate_ml_model(MODEL)
        if is_valid:
            print(f"✓ Loaded ML model from {MODEL_PATH}")
            # Try to determine feature count
            try:
                if hasattr(MODEL, 'n_features_in_'):
                    MODEL_FEATURE_COUNT = MODEL.n_features_in_
                    print(f"  Model expects {MODEL_FEATURE_COUNT} features")
            except Exception:
                pass
        else:
            print(f"⚠ ML model loaded but validation failed: {error_msg}")
            print(f"  Falling back to rule-based scoring")
            MODEL = None
            MODEL_LOAD_ERROR = error_msg
    except Exception as e:
        # If loading fails, fall back to rule-based scoring.
        error_msg = f"Could not load ML model from {MODEL_PATH}: {e}"
        print(f"⚠ {error_msg}")
        MODEL_LOAD_ERROR = str(e)
        MODEL = None
else:
    print(f"ℹ No ML model found at {MODEL_PATH} - using rule-based scoring")


# === Auto‑training configuration & state ===

# Minimum number of NEW matched pairs before we consider retraining
AUTO_TRAIN_MIN_NEW_MATCHES = int(os.environ.get("AUTO_TRAIN_MIN_NEW_MATCHES", "50"))

# Minimum seconds between two automatic retrains (to avoid constant retraining)
AUTO_TRAIN_MIN_INTERVAL_SECONDS = int(os.environ.get("AUTO_TRAIN_MIN_INTERVAL_SECONDS", "900"))  # 15 minutes

# Whether auto‑training is enabled at all
AUTO_TRAIN_ENABLED = os.environ.get("AUTO_TRAIN_ENABLED", "1") == "1"

# Internal state to throttle background retraining
_last_auto_train_ts: float = 0.0
_auto_train_lock = threading.Lock()
_auto_train_in_progress = False


def _background_retrain_model() -> None:
    """
    Run retrain_model.py in a background thread so the main API request
    is not blocked. After successful training, reload MODEL in‑process.
    """
    global MODEL, _auto_train_in_progress, _last_auto_train_ts

    with _auto_train_lock:
        if _auto_train_in_progress:
            # Another retrain is already running
            print("Auto‑train: retrain already in progress, skipping.")
            return
        _auto_train_in_progress = True

    try:
        print("\n" + "=" * 60)
        print("Auto‑train: starting background model retraining...")
        print("=" * 60)

        script_path = os.path.join(os.path.dirname(__file__), "retrain_model.py")
        # Run retrain_model.py using the same Python interpreter
        result = subprocess.run(
            [sys.executable, script_path],
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=os.path.dirname(__file__),
            check=False,
        )

        if result.returncode != 0:
            print(f"Auto‑train: retrain_model.py exited with code {result.returncode}")
            return

        # Reload MODEL from disk with validation
        global MODEL_FEATURE_COUNT, MODEL_LOAD_ERROR
        try:
            new_model = joblib.load(MODEL_PATH)
            is_valid, error_msg = _validate_ml_model(new_model)
            if is_valid:
                MODEL = new_model
                MODEL_LOAD_ERROR = None
                _last_auto_train_ts = time.time()
                # Update feature count
                try:
                    if hasattr(MODEL, 'n_features_in_'):
                        MODEL_FEATURE_COUNT = MODEL.n_features_in_
                        print(f"Auto‑train: ✓ Model reloaded from {MODEL_PATH} ({MODEL_FEATURE_COUNT} features)")
                    else:
                        print(f"Auto‑train: ✓ Model reloaded from {MODEL_PATH}")
                except Exception:
                    print(f"Auto‑train: ✓ Model reloaded from {MODEL_PATH}")
            else:
                print(f"Auto‑train: ⚠ Model reloaded but validation failed: {error_msg}")
                MODEL_LOAD_ERROR = error_msg
        except Exception as e:
            error_msg = f"Auto‑train: failed to reload model from {MODEL_PATH}: {e}"
            print(error_msg)
            MODEL_LOAD_ERROR = str(e)
            MODEL = None
    finally:
        with _auto_train_lock:
            _auto_train_in_progress = False


def maybe_trigger_auto_train(new_match_count: int) -> None:
    """
    Decide whether to trigger background auto‑training based on:
    - Whether AUTO_TRAIN_ENABLED is on
    - How many NEW matches were just created
    - How long since the last auto‑train run
    """
    global _last_auto_train_ts

    if not AUTO_TRAIN_ENABLED:
        return

    if new_match_count <= 0:
        return

    if new_match_count < AUTO_TRAIN_MIN_NEW_MATCHES:
        print(
            f"Auto‑train: only {new_match_count} new matches "
            f"(min required {AUTO_TRAIN_MIN_NEW_MATCHES}), skipping."
        )
        return

    now = time.time()
    if _last_auto_train_ts and (now - _last_auto_train_ts) < AUTO_TRAIN_MIN_INTERVAL_SECONDS:
        remaining = int(AUTO_TRAIN_MIN_INTERVAL_SECONDS - (now - _last_auto_train_ts))
        print(
            f"Auto‑train: last run was recently, wait another {remaining}s "
            f"before next retrain."
        )
        return

    # Fire‑and‑forget background training thread
    t = threading.Thread(target=_background_retrain_model, daemon=True)
    t.start()


# === Data models ===

@dataclass
class Transaction:
    source: str  # "invoice" or "bank"
    description: str
    amount: float
    date: str | None = None
    vendor_name: str | None = None  # Extracted vendor/client name
    invoice_number: str | None = None  # Extracted invoice number
    currency: str | None = None  # Detected currency symbol (₹, $, £, €, etc.)
    reference_id: str | None = None
    direction: str | None = None  # "credit" or "debit"
    owner_name: str | None = None  # Bank statement business/company name (if found)
    document_subtype: str | None = None
    file_name: str | None = None
    balance: float | None = None  # Account balance (for bank transactions)


def _extract_bank_owner_name(lines: List[str]) -> str | None:
    """Best-effort extraction of owner/company name from bank statement header."""
    if not lines:
        return None

    header = "\n".join(lines[:60])
    header_norm = re.sub(r"\s+", " ", header)

    patterns = [
        r"Business\s+Owner\s*[:\-]?\s*([A-Za-z0-9 &'\-\.]+)",
        r"Account\s+Name\s*[:\-]?\s*([A-Za-z0-9 &'\-\.]+)",
        r"Company\s*[:\-]?\s*([A-Za-z0-9 &'\-\.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, header_norm, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            return val[:255] if val else None

    # Fallback heuristic: first long ALL-CAPS-ish line (often company name)
    for raw in lines[:30]:
        s = re.sub(r"\s+", " ", (raw or "")).strip()
        if len(s) < 6:
            continue
        if re.search(r"\d", s):
            continue
        if s.isupper() and len(s) <= 60:
            return s[:255]
    return None


@dataclass
class ReconciliationResult:
    matches: List[Dict[str, Any]]
    only_in_invoices: List[Dict[str, Any]]
    only_in_bank: List[Dict[str, Any]]


# === DB helpers ===

def init_db() -> None:
    """Initialize database tables"""
    try:
        # Create database and tables using migration script
        if db_manager.db_type == "mysql":
            from migrations.mysql_migration import create_tables
        else:
            from migrations.sqlite_migration import create_tables
        create_tables()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def save_invoice_file(file_bytes: bytes, file_name: str, reconciliation_id: int) -> tuple[int, str]:
    """
    Save an invoice file to disk and store its path in database.
    
    Returns:
        Tuple of (invoice_file_id, file_path)
    """
    # Generate a unique filename to avoid conflicts
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    file_ext = os.path.splitext(file_name)[1] or '.jpg'
    safe_filename = f"{reconciliation_id}_{file_hash}{file_ext}"
    file_path = os.path.join(INVOICE_FOLDER, safe_filename)
    
    # Save file to disk
    with open(file_path, 'wb') as f:
        f.write(file_bytes)
    
    # Store in database using MySQL (invoices table)
    try:
        insert_query = """
            INSERT INTO invoices (
                file_upload_id,
                invoice_number,
                invoice_date,
                vendor_name,
                total_amount,
                tax_amount,
                status,
                invoice_file_path,
                invoice_file_hash,
                description,
                extracted_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        invoice_id = db_manager.execute_insert(
            insert_query,
            (
                None,
                None,
                None,
                None,
                None,
                None,
                "pending",
                file_path,
                file_hash,
                file_name,
                None,
            ),
        )
        return invoice_id, file_path
    except Exception as e:
        try:
            existing = db_manager.execute_query(
                "SELECT id, invoice_file_path FROM invoices WHERE invoice_file_hash = ? LIMIT 1",
                (file_hash,),
            )
            if existing:
                existing_id = existing[0].get("id")
                existing_path = existing[0].get("invoice_file_path")
                return int(existing_id), existing_path or file_path
        except Exception:
            pass

        logger.error(f"Failed to save invoice file to database: {e}")
        raise


def store_transactions(
    invoice_txs: List[Transaction],
    bank_txs: List[Transaction],
    invoice_file_names: List[str],
    bank_file_names: List[str],
) -> None:
    """Store transactions in MySQL database using PARENT-CHILD JSON structure"""
    import time
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting to store {len(invoice_txs)} invoice transactions and {len(bank_txs)} bank transactions")
    
    # PARENT-CHILD STRUCTURE: Group transactions by file
    # Create parent records for each unique file
    successful_invoices = 0
    failed_invoices = 0
    
    # Group invoice transactions by file name
    invoice_file_groups = {}
    for i, tx in enumerate(invoice_txs):
        file_name = tx.file_name or f"invoice_file_{i}"
        if file_name not in invoice_file_groups:
            invoice_file_groups[file_name] = []
        invoice_file_groups[file_name].append(tx)
    
    # Store each invoice file as one parent record with JSON children
    for file_name, transactions in invoice_file_groups.items():
        try:
            # Pick representative header fields for invoices table (do not rely only on transactions[0])
            representative_invoice_number = None
            representative_invoice_date = None
            representative_vendor_name = None
            for tx in transactions:
                if not representative_invoice_number:
                    try:
                        if getattr(tx, "invoice_number", None):
                            representative_invoice_number = str(tx.invoice_number).strip().upper()
                    except Exception:
                        pass
                    if not representative_invoice_number:
                        try:
                            ef = getattr(tx, "extracted_fields", None) or {}
                            inv_no = ef.get("invoice_number")
                            if inv_no:
                                representative_invoice_number = str(inv_no).strip().upper()
                        except Exception:
                            pass

                if not representative_invoice_date:
                    try:
                        if getattr(tx, "date", None):
                            representative_invoice_date = tx.date
                    except Exception:
                        pass
                    if not representative_invoice_date:
                        try:
                            ef = getattr(tx, "extracted_fields", None) or {}
                            inv_dt = ef.get("invoice_date")
                            if inv_dt:
                                representative_invoice_date = str(inv_dt).strip()
                        except Exception:
                            pass

                if not representative_vendor_name:
                    try:
                        if getattr(tx, "vendor_name", None):
                            representative_vendor_name = str(tx.vendor_name).strip()
                    except Exception:
                        pass

                if representative_invoice_number and representative_invoice_date and representative_vendor_name:
                    break

            # Generate unique hash for this invoice file
            timestamp = int(time.time())
            invoice_hash = f"reconcile_invoice_{timestamp}_{hash(file_name) % 10000}"
            
            # Convert transactions to child records format
            child_records = []
            for idx, tx in enumerate(transactions):
                extracted_fields = None
                try:
                    extracted_fields = getattr(tx, "extracted_fields", None)
                except Exception:
                    extracted_fields = None

                child_records.append({
                    "record_id": idx + 1,
                    "invoice_number": tx.invoice_number,
                    "invoice_date": tx.date,
                    "vendor_name": tx.vendor_name,
                    "total_amount": tx.amount,
                    "description": tx.description,
                    "currency": tx.currency,
                    "file_name": tx.file_name
                    ,"extracted_fields": extracted_fields
                })
            
            # PARENT-CHILD JSON STRUCTURE
            parent_data = {
                "parent_info": {
                    "file_name": file_name,
                    "file_hash": invoice_hash,
                    "upload_timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "source": "reconciliation_endpoint"
                },
                "extracted_records": {
                    "records": child_records
                }
            }

            invoice_upload_id = db_manager.execute_insert(
                """
                INSERT INTO file_uploads (
                    file_name, file_type, file_size, processing_status, error_message, file_path, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_name,
                    "invoice",
                    0,
                    "completed",
                    None,
                    None,
                    json.dumps(parent_data, ensure_ascii=False, default=str),
                ),
            )
            
            # Calculate totals for parent record
            total_amount = sum(tx.amount for tx in transactions if tx.amount)
            
            insert_query = """
                INSERT INTO invoices (
                    file_upload_id,
                    invoice_number,
                    invoice_date,
                    vendor_name,
                    total_amount,
                    tax_amount,
                    net_amount,
                    due_date,
                    description,
                    line_items,
                    extracted_data,
                    confidence_score,
                    status,
                    invoice_file_path,
                    invoice_file_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            
            invoice_id = db_manager.execute_insert(
                insert_query,
                (
                    invoice_upload_id,  # file_upload_id
                    representative_invoice_number,  # Main invoice number
                    representative_invoice_date,  # Main invoice date
                    representative_vendor_name,  # Main vendor
                    total_amount,  # Total amount
                    None,  # tax_amount
                    total_amount,  # net_amount
                    None,  # due_date
                    f"Reconciliation upload: {len(transactions)} transactions from {file_name}",  # description
                    json.dumps([
                        {
                            "description": tx.description,
                            "amount": tx.amount,
                            "invoice_number": tx.invoice_number,
                            "invoice_date": tx.date,
                            "currency": tx.currency,
                            "extracted_fields": getattr(tx, "extracted_fields", None),
                        }
                        for tx in transactions
                    ], ensure_ascii=False, default=str),  # line_items
                    json.dumps(parent_data, ensure_ascii=False, default=str),  # PARENT-CHILD JSON STRUCTURE
                    0.85 if total_amount else 0.0,  # confidence_score
                    "completed",  # status
                    None,  # invoice_file_path
                    invoice_hash,  # invoice_file_hash
                ),
            )

            # Attach generated DB id back to the in-memory transactions so later reconciliation can link it
            for tx in transactions:
                try:
                    setattr(tx, "id", invoice_id)
                    setattr(tx, "invoice_id", invoice_id)
                except Exception:
                    pass
            
            # Store child data in invoice_extractions table (ONE JSON ROW ONLY)
            try:
                from config import INVOICE_FOLDER
                extractions_dir = os.path.join(INVOICE_FOLDER, "extractions")
                os.makedirs(extractions_dir, exist_ok=True)
                
                json_filename = f"invoice_{invoice_id}_reconcile_all_data.json"
                json_file_path = os.path.join(extractions_dir, json_filename)
                
                # ALL EXTRACTED DATA IN ONE JSON STRUCTURE
                all_extracted_data = {
                    "parent_invoice_id": invoice_id,
                    "parent_info": parent_data["parent_info"],
                    "all_extracted_records": child_records,
                    "extraction_metadata": {
                        "total_records": len(child_records),
                        "extraction_confidence": 0.85 if total_amount else 0.0,
                        "processed_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "source": "reconciliation_endpoint"
                    }
                }
                
                with open(json_file_path, 'w', encoding='utf-8') as f:
                    json.dump(all_extracted_data, f, ensure_ascii=False, indent=2, default=str)
                
                # Insert ONE ROW ONLY into invoice_extractions table
                db_manager.execute_insert(
                    """
                    INSERT INTO invoice_extractions (
                        parent_invoice_id, sequence_no, page_no, section_no, original_filename, json_file_path, extracted_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_id,  # parent_invoice_id
                        1,  # sequence_no
                        1,  # page_no
                        None,  # section_no
                        file_name,  # original_filename
                        json_file_path,  # json_file_path
                        json.dumps(all_extracted_data, ensure_ascii=False, default=str),  # ALL DATA IN ONE JSON
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to store invoice child data for {file_name}: {e}")
            
            successful_invoices += 1
            
        except Exception as e:
            failed_invoices += 1
            logger.error(f"Error storing invoice file {file_name}: {e}")
            continue
    
    # Store bank transactions in bank_statements table using PARENT-CHILD structure
    successful_banks = 0
    failed_banks = 0
    
    # Group bank transactions by file name
    bank_file_groups = {}
    for i, tx in enumerate(bank_txs):
        file_name = tx.file_name or f"bank_file_{i}"
        if file_name not in bank_file_groups:
            bank_file_groups[file_name] = []
        bank_file_groups[file_name].append(tx)
    
    # Store each bank file as one parent record with JSON children
    for file_name, transactions in bank_file_groups.items():
        try:
            # Generate unique hash for this bank file
            timestamp = int(time.time())
            bank_hash = f"reconcile_bank_{timestamp}_{hash(file_name) % 10000}"
            
            # Convert transactions to child records format
            child_records = []
            for idx, tx in enumerate(transactions):
                child_records.append({
                    "record_id": idx + 1,
                    "transaction_date": tx.date,
                    "description": tx.description,
                    "amount": tx.amount,
                    "currency": tx.currency,
                    "file_name": tx.file_name
                })
            
            # PARENT-CHILD JSON STRUCTURE
            parent_data = {
                "parent_info": {
                    "file_name": file_name,
                    "file_hash": bank_hash,
                    "upload_timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "source": "reconciliation_endpoint"
                },
                "extracted_records": {
                    "transactions": child_records
                }
            }
            
            # Calculate totals for parent record
            total_credits = sum(abs(tx.amount) for tx in transactions if tx.amount and tx.amount > 0)
            total_debits = sum(abs(tx.amount) for tx in transactions if tx.amount and tx.amount < 0)

            # Store extracted bank transactions in bank_transactions (MySQL authoritative table)
            # Create one parent file_uploads row per bank file (bank_transactions.file_upload_id is NOT NULL)
            bank_upload_id = None
            try:
                bank_upload_id = db_manager.execute_insert(
                    """
                    INSERT INTO file_uploads (
                        file_name, file_type, file_size, processing_status, error_message, file_path, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_name,
                        "bank_statement",
                        0,
                        "completed",
                        None,
                        None,
                        json.dumps(parent_data, ensure_ascii=False, default=str),
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to create file_uploads row for bank file {file_name}: {e}")
                raise

            insert_query = """
                INSERT INTO bank_transactions (
                    file_upload_id,
                    transaction_date,
                    description,
                    amount,
                    balance,
                    transaction_type,
                    reference_number,
                    account_number,
                    category,
                    raw_data
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            for tx in transactions:
                tx_date = tx.date
                if not tx_date:
                    tx_date = datetime.utcnow().date().isoformat()

                tx_amount = tx.amount
                tx_type = "credit" if (tx_amount is not None and float(tx_amount) >= 0) else "debit"

                reference_number = getattr(tx, "reference_id", None) or getattr(tx, "reference", None)
                balance = getattr(tx, "balance", None)
                account_number = getattr(tx, "account", None) or getattr(tx, "account_number", None)

                raw_data = {
                    "file_hash": bank_hash,
                    "totals": {"total_credits": total_credits, "total_debits": total_debits},
                    "transaction": {
                        "date": tx.date,
                        "description": tx.description,
                        "amount": tx.amount,
                        "currency": tx.currency,
                        "vendor_name": tx.vendor_name,
                        "invoice_number": tx.invoice_number,
                        "reference_id": getattr(tx, "reference_id", None),
                        "direction": getattr(tx, "direction", None),
                        "balance": getattr(tx, "balance", None),
                        "owner_name": getattr(tx, "owner_name", None),
                    },
                }

                bank_tx_id = db_manager.execute_insert(
                    insert_query,
                    (
                        bank_upload_id,
                        tx_date,
                        tx.description,
                        tx_amount,
                        balance,
                        tx_type,
                        reference_number,
                        account_number,
                        None,
                        json.dumps(raw_data, ensure_ascii=False, default=str),
                    ),
                )

                # Attach generated DB id back to the in-memory transaction so later reconciliation can link it
                try:
                    setattr(tx, "id", bank_tx_id)
                except Exception:
                    pass
            
            successful_banks += 1
            
        except Exception as e:
            failed_banks += 1
            logger.error(f"Error storing bank file {file_name}: {e}")
            continue
    
    logger.info(f"Transaction storage completed: {successful_invoices}/{len(invoice_txs)} invoices stored, {failed_invoices} failed")
    logger.info(f"Transaction storage completed: {successful_banks}/{len(bank_txs)} bank transactions stored, {failed_banks} failed")


@app.route("/api/invoice-uploads/<int:upload_id>", methods=["GET"])
@limiter.limit("60 per minute")
def api_get_invoice_upload(upload_id: int):
    try:
        with db_manager.get_connection() as conn:
            cur = conn.cursor()

            upload_row = cur.execute(
                """
                SELECT id, file_name, file_type, file_size, upload_time, processing_status, error_message, file_path, metadata
                FROM file_uploads
                WHERE id = ? AND file_type = 'invoice'
                """,
                (upload_id,),
            ).fetchone()

            if not upload_row:
                return jsonify({"error": "Invoice upload not found"}), 404

            invoice_rows = cur.execute(
                """
                SELECT *
                FROM invoices
                WHERE file_upload_id = ?
                ORDER BY id ASC
                """,
                (upload_id,),
            ).fetchall()

        upload_dict = dict(upload_row)
        invoices = [dict(r) for r in invoice_rows]

        metadata_raw = upload_dict.get("metadata")
        metadata_obj = None
        if metadata_raw:
            try:
                metadata_obj = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
            except Exception:
                metadata_obj = metadata_raw

        upload_dict["metadata"] = metadata_obj

        return jsonify({
            "success": True,
            "upload": upload_dict,
            "invoices": invoices,
            "count": len(invoices),
        })
    except Exception as e:
        error_traceback = traceback.format_exc()
        return (
            jsonify(
                {
                    "error": "Internal server error while fetching invoice upload.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


def store_reconciliation_summary(
    invoice_file_names: List[str],
    bank_file_name: str,
    result: ReconciliationResult,
    total_invoice_rows: int,
    total_bank_rows: int,
    invoice_file_date: str | None = None,
    bank_file_date: str | None = None,
    invoice_files_data: List[Dict[str, Any]] = None,  # List of {file_bytes, file_name}
    invoice_extractions_data: Dict[str, List[Dict[str, Any]]] = None,
) -> int:
    """
    Insert one row per reconciliation run and return its ID.
    Also inserts all matched pairs into reconciliation_matches.
    
    Args:
        invoice_file_date: Date extracted from invoice file(s)
        bank_file_date: Date extracted from bank file
        invoice_files_data: List of dicts with 'file_bytes' and 'file_name' for saving invoice files
    """
    # For summary table, store unique invoice file names as a comma-separated string
    unique_invoice_files = ", ".join(sorted(set(invoice_file_names))) if invoice_file_names else None

    # Prefer invoice number as reference_name for traceability in reconciliation table
    reference_name = None
    reference = None
    try:
        invoice_numbers: List[str] = []

        # 1) Best effort: harvest from match payload first
        if result.matches:
            for m in result.matches:
                inv = (m or {}).get("invoice", {})
                inv_no = (inv.get("invoice_number") or inv.get("reference_id"))
                if inv_no:
                    inv_no = str(inv_no).strip()
                    if inv_no:
                        invoice_numbers.append(inv_no)

        # 2) MySQL enrichment: if invoice_id is known, resolve authoritative invoice_number
        if db_manager.db_type == "mysql" and result.matches:
            for m in result.matches:
                inv = (m or {}).get("invoice", {})
                invoice_id = inv.get("id") or inv.get("invoice_id")
                try:
                    if isinstance(invoice_id, str) and invoice_id.isdigit():
                        invoice_id = int(invoice_id)
                except Exception:
                    pass

                if invoice_id:
                    try:
                        row = db_manager.execute_query(
                            "SELECT invoice_number FROM invoices WHERE id = %s LIMIT 1",
                            (invoice_id,),
                        )
                        if row and row[0].get("invoice_number"):
                            invoice_numbers.append(str(row[0].get("invoice_number")).strip())
                    except Exception:
                        pass

        # Normalize + de-duplicate while preserving order
        seen = set()
        normalized_numbers: List[str] = []
        for n in invoice_numbers:
            n2 = str(n).strip().upper()
            if not n2:
                continue
            if n2 in seen:
                continue
            seen.add(n2)
            normalized_numbers.append(n2)

        if normalized_numbers:
            reference_name = normalized_numbers[0]
            # Store all matched invoice numbers for traceability
            reference = ", ".join(normalized_numbers[:20])

        # 3) Fallback: parse from invoice filename (e.g. "Invoice INV-0111.pdf")
        if not reference_name and invoice_file_names:
            import re

            for fn in invoice_file_names:
                if not fn:
                    continue
                m = re.search(r"\bINV[-\s_]*\d+\b", str(fn), re.IGNORECASE)
                if m:
                    reference_name = m.group(0).replace(" ", "").replace("_", "-").upper()
                    reference = reference_name
                    break
    except Exception:
        reference_name = None
        reference = None

    # Insert reconciliation summary
    insert_query = """
        INSERT INTO reconciliations (
            name, description, reconciliation_date, status,
            total_invoices, total_transactions, total_matches,
            total_amount_matched, reference, reference_name, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    reconciliation_id = db_manager.execute_insert(
        insert_query,
        (
            f"Reconciliation {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Invoices: {unique_invoice_files}, Bank: {bank_file_name}",
            datetime.now().date(),
            'completed',
            total_invoice_rows,
            total_bank_rows,
            len(result.matches),
            sum(match.get('invoice', {}).get('amount', 0) for match in result.matches),
            reference,
            reference_name,
            'system'
        )
    )

    try:
        raw_payload = {
            "schema": "hybrid_reconciliation_v1",
            "reconciliation_id": reconciliation_id,
            "generated_at": datetime.now().isoformat(),
            "inputs": {
                "invoice_file_names": sorted(set(invoice_file_names or [])),
                "bank_file_name": bank_file_name,
                "invoice_file_date": invoice_file_date,
                "bank_file_date": bank_file_date,
                "total_invoice_rows": total_invoice_rows,
                "total_bank_rows": total_bank_rows,
            },
            "results": {
                "matches": result.matches,
                "only_in_invoices": result.only_in_invoices,
                "only_in_bank": result.only_in_bank,
                "summary": {
                    "total_matches": len(result.matches),
                    "total_unmatched_invoices": len(result.only_in_invoices),
                    "total_unmatched_bank": len(result.only_in_bank),
                },
            },
        }

        db_manager.execute_update(
            "UPDATE reconciliations SET raw_json = %s WHERE id = %s",
            (json.dumps(raw_payload, ensure_ascii=False, default=str), reconciliation_id),
        )
    except Exception as e:
        logger.warning(f"Failed to store reconciliations.raw_json for reconciliation_id={reconciliation_id}: {e}")
    
    # Save invoice files if provided
    invoice_file_map = {}  # Maps file_name to (invoice_file_id, file_path)
    if invoice_files_data:
        for file_data in invoice_files_data:
            file_bytes = file_data.get('file_bytes')
            file_name = file_data.get('file_name')
            if file_bytes and file_name:
                try:
                    invoice_file_id, file_path = save_invoice_file(file_bytes, file_name, reconciliation_id)
                    invoice_file_map[file_name] = (invoice_file_id, file_path)
                except Exception as e:
                    logger.warning(f"Failed to save invoice file {file_name}: {str(e)}")

    if invoice_extractions_data and invoice_file_map and db_manager.db_type == "mysql":
        for base_file_name, extractions in invoice_extractions_data.items():
            if base_file_name not in invoice_file_map:
                continue
            parent_invoice_id, _parent_path = invoice_file_map[base_file_name]

            parent_dir = os.path.join(INVOICE_JSON_FOLDER, str(parent_invoice_id))
            os.makedirs(parent_dir, exist_ok=True)

            seq = 0
            for extraction in (extractions or []):
                seq += 1
                json_file_path = os.path.join(parent_dir, f"{seq}.json")
                try:
                    with open(json_file_path, "w", encoding="utf-8") as f:
                        json.dump(extraction, f, ensure_ascii=False, indent=2, default=str)
                except Exception as e:
                    logger.warning(f"Failed to write invoice extraction JSON for parent_invoice_id={parent_invoice_id}: {e}")

                try:
                    db_manager.execute_insert(
                        """
                        INSERT INTO invoice_extractions (
                            parent_invoice_id, sequence_no, page_no, section_no, original_filename, json_file_path, extracted_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            parent_invoice_id,
                            seq,
                            extraction.get("page_no"),
                            extraction.get("section_no"),
                            extraction.get("original_filename") or base_file_name,
                            json_file_path,
                            json.dumps(extraction, ensure_ascii=False, default=str),
                        ),
                    )
                except Exception as e:
                    logger.warning(f"Failed to store invoice extraction in DB for parent_invoice_id={parent_invoice_id}, seq={seq}: {e}")

    # Create a mapping from invoice transaction to file name
    # This helps us link matches to invoice files
    invoice_tx_to_file = {}
    for idx, match in enumerate(result.matches):
        inv = match.get("invoice", {})
        # Try to find which file this invoice came from based on description/amount
        # We'll use the first matching file for now
        inv_file_name = inv.get("file_name") or invoice_file_names[0] if invoice_file_names else None
        if inv_file_name:
            base_file_name = inv_file_name.split("#", 1)[0]
            if base_file_name in invoice_file_map:
                invoice_tx_to_file[idx] = invoice_file_map[base_file_name]

    # Insert each match into reconciliation_matches and collect match IDs
    match_id_map = {}  # Maps match index to database match_id
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        for idx, match in enumerate(result.matches):
            inv = match.get("invoice", {})
            bank = match.get("bank", {})
            match_score = match.get("match_score", 0.0)

            invoice_reference_val = (
                inv.get("invoice_number")
                or inv.get("reference_id")
                or inv.get("description")
            )
            
            # Get invoice file info if available
            invoice_file_id = None
            invoice_file_path = None
            if idx in invoice_tx_to_file:
                invoice_file_id, invoice_file_path = invoice_tx_to_file[idx]
            elif invoice_file_map:
                # Fallback to first file if no specific match
                first_file = list(invoice_file_map.values())[0]
                invoice_file_id, invoice_file_path = first_file
            
            # Get invoice_id and transaction_id from match if available
            invoice_id = inv.get("id") or inv.get("invoice_id")
            transaction_id = bank.get("id") or bank.get("transaction_id")

            # MySQL schema uses foreign keys to invoices/bank_transactions and does not store
            # the full invoice/bank fields in reconciliation_matches.
            if db_manager.db_type == "mysql":
                try:
                    if isinstance(invoice_id, str) and invoice_id.isdigit():
                        invoice_id = int(invoice_id)
                    if isinstance(transaction_id, str) and transaction_id.isdigit():
                        transaction_id = int(transaction_id)
                except Exception:
                    pass

                # If IDs are missing, try to resolve them from MySQL tables
                if not invoice_id:
                    try:
                        inv_no = inv.get("invoice_number")
                        if inv_no:
                            row = db_manager.execute_query(
                                "SELECT id FROM invoices WHERE invoice_number = %s ORDER BY id DESC LIMIT 1",
                                (inv_no,),
                            )
                            if row and row[0].get("id"):
                                invoice_id = int(row[0]["id"])
                    except Exception as e:
                        logger.warning(f"Could not resolve invoice_id from invoice_number: {e}")

                if not transaction_id:
                    try:
                        bank_date = bank.get("date")
                        bank_desc = bank.get("description")
                        bank_amt = bank.get("amount")
                        if bank_date and bank_desc and bank_amt is not None:
                            row = db_manager.execute_query(
                                """
                                SELECT id FROM bank_transactions
                                WHERE transaction_date = %s
                                  AND ABS(amount) = %s
                                  AND description = %s
                                ORDER BY id DESC
                                LIMIT 1
                                """,
                                (bank_date, abs(float(bank_amt)), bank_desc),
                            )
                            if row and row[0].get("id"):
                                transaction_id = int(row[0]["id"])
                    except Exception as e:
                        logger.warning(f"Could not resolve transaction_id from bank transaction fields: {e}")

                # Guard: ensure chosen IDs match the in-memory amounts.
                # If they don't, try to re-resolve by amount (and optionally description/date) to avoid wrong reconciliation pairs.
                inv_amt = inv.get("amount")
                bank_amt = bank.get("amount")
                try:
                    inv_amt_abs = abs(float(inv_amt)) if inv_amt is not None else None
                    bank_amt_abs = abs(float(bank_amt)) if bank_amt is not None else None
                except Exception:
                    inv_amt_abs = None
                    bank_amt_abs = None

                if invoice_id and transaction_id and (inv_amt_abs is not None) and (bank_amt_abs is not None):
                    try:
                        chk = db_manager.execute_query(
                            """
                            SELECT
                                inv.total_amount AS inv_amount,
                                bt.amount AS bank_amount
                            FROM invoices inv
                            JOIN bank_transactions bt ON bt.id = %s
                            WHERE inv.id = %s
                            LIMIT 1
                            """,
                            (transaction_id, invoice_id),
                        )
                        if chk:
                            db_inv_amt = chk[0].get("inv_amount")
                            db_bank_amt = chk[0].get("bank_amount")
                            if (db_inv_amt is not None) and (db_bank_amt is not None):
                                db_inv_cents = int(round(abs(float(db_inv_amt)) * 100))
                                db_bank_cents = int(round(abs(float(db_bank_amt)) * 100))
                                mem_inv_cents = int(round(inv_amt_abs * 100))
                                mem_bank_cents = int(round(bank_amt_abs * 100))

                                # If the stored IDs don't match the expected amounts, attempt re-resolution.
                                if (db_inv_cents != mem_inv_cents) or (db_bank_cents != mem_bank_cents) or (mem_inv_cents != mem_bank_cents):
                                    resolved_invoice_id = None
                                    resolved_transaction_id = None

                                    try:
                                        inv_desc = inv.get("description")
                                        q = "SELECT id FROM invoices WHERE ABS(total_amount) = %s"
                                        params = [inv_amt_abs]
                                        if inv_desc:
                                            q += " AND description = %s"
                                            params.append(inv_desc)
                                        q += " ORDER BY id DESC LIMIT 1"
                                        row2 = db_manager.execute_query(q, tuple(params))
                                        if row2 and row2[0].get("id"):
                                            resolved_invoice_id = int(row2[0]["id"])
                                    except Exception:
                                        pass

                                    try:
                                        bank_date = bank.get("date")
                                        bank_desc = bank.get("description")
                                        q = "SELECT id FROM bank_transactions WHERE ABS(amount) = %s"
                                        params = [bank_amt_abs]
                                        if bank_date:
                                            q += " AND transaction_date = %s"
                                            params.append(bank_date)
                                        if bank_desc:
                                            q += " AND description = %s"
                                            params.append(bank_desc)
                                        q += " ORDER BY id DESC LIMIT 1"
                                        row3 = db_manager.execute_query(q, tuple(params))
                                        if row3 and row3[0].get("id"):
                                            resolved_transaction_id = int(row3[0]["id"])
                                    except Exception:
                                        pass

                                    if resolved_invoice_id and resolved_transaction_id:
                                        invoice_id = resolved_invoice_id
                                        transaction_id = resolved_transaction_id
                                    else:
                                        logger.warning(
                                            "Skipping reconciliation match insert (MySQL) due to amount mismatch after ID resolution: "
                                            f"invoice_id={invoice_id}, transaction_id={transaction_id}, inv_amt={inv_amt}, bank_amt={bank_amt}"
                                        )
                                        continue
                    except Exception:
                        # If validation fails, prefer safety: skip inserting potentially wrong match
                        logger.warning(
                            "Skipping reconciliation match insert (MySQL) due to validation error while checking amounts: "
                            f"invoice_id={invoice_id}, transaction_id={transaction_id}"
                        )
                        continue

                if not invoice_id or not transaction_id:
                    logger.warning(
                        "Skipping reconciliation match insert (MySQL) due to missing IDs: "
                        f"invoice_id={invoice_id}, transaction_id={transaction_id}"
                    )
                    continue

                insert_query = """
                    INSERT INTO reconciliation_matches (
                        reconciliation_id,
                        invoice_id,
                        transaction_id,
                        match_score,
                        match_type,
                        status,
                        amount_difference,
                        date_difference,
                        confidence_score,
                        matching_rules,
                        notes,
                        created_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                amount_difference = None
                try:
                    if inv_amt is not None and bank_amt is not None:
                        amount_difference = float(inv_amt) - float(bank_amt)
                except Exception:
                    amount_difference = None

                cur.execute(
                    insert_query,
                    (
                        reconciliation_id,
                        invoice_id,
                        transaction_id,
                        match_score,
                        "auto",
                        "pending",
                        amount_difference,
                        None,
                        match_score,
                        None,
                        None,
                        "system",
                    ),
                )
                match_id_map[idx] = cur.lastrowid
                continue
            
            # Insert match into database
            insert_query = """
                INSERT INTO reconciliation_matches (
                    reconciliation_id,
                    invoice_description, invoice_amount, invoice_date, invoice_vendor_name,
                    invoice_invoice_number, invoice_currency, invoice_reference_id, invoice_document_subtype,
                    bank_description, bank_amount, bank_date, bank_vendor_name, bank_invoice_number,
                    bank_currency, bank_reference_id, bank_direction, bank_document_subtype, bank_balance,
                    match_score, invoice_id, transaction_id, invoice_file_path, invoice_file_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            cur.execute(insert_query, (
                reconciliation_id,
                inv.get("description"),
                inv.get("amount"),
                inv.get("date"),
                inv.get("vendor_name"),
                inv.get("invoice_number"),
                inv.get("currency"),
                invoice_reference_val,
                inv.get("document_subtype"),
                bank.get("description"),
                bank.get("amount"),
                bank.get("date"),
                bank.get("vendor_name"),
                bank.get("invoice_number"),
                bank.get("currency"),
                bank.get("reference_id"),
                bank.get("direction"),
                bank.get("document_subtype"),
                bank.get("balance"),
                match_score,
                invoice_id,
                transaction_id,
                invoice_file_path,
                invoice_file_id,
            ))
            # Store the match_id for this match index
            match_id_map[idx] = cur.lastrowid

        conn.commit()
    # Add match_id, invoice_file_id, invoice_id, and transaction_id to each match in result.matches
    for idx, match in enumerate(result.matches):
        if idx in match_id_map:
            match["match_id"] = match_id_map[idx]
        
        # Add invoice_file_id if available
        if idx in invoice_tx_to_file:
            invoice_file_id, invoice_file_path = invoice_tx_to_file[idx]
            match["invoice_file_id"] = invoice_file_id
            match["invoice_file_path"] = invoice_file_path
        elif invoice_file_map:
            # Fallback to first file if no specific match
            first_file = list(invoice_file_map.values())[0]
            invoice_file_id, invoice_file_path = first_file
            match["invoice_file_id"] = invoice_file_id
            match["invoice_file_path"] = invoice_file_path
        
        # Add invoice_id and transaction_id if available
        inv = match.get("invoice", {})
        bank = match.get("bank", {})
        if inv.get("id") or inv.get("invoice_id"):
            match["invoice_id"] = inv.get("id") or inv.get("invoice_id")
        if bank.get("id") or bank.get("transaction_id"):
            match["transaction_id"] = bank.get("id") or bank.get("transaction_id")
    
    # Invalidate cache for reconciliation list
    cache_clear()
    
    return reconciliation_id


def _validate_uploaded_file(
    file_storage, 
    allowed_exts: set[str], 
    allowed_mimetypes: set[str],
    check_size: bool = True
) -> tuple[bool, str | None]:
    """
    Enhanced server-side validation for uploaded files with security checks.
    - Checks extension against an allow-list.
    - Checks Content-Type (MIME type) against an allow-list.
    - Validates file size to prevent memory exhaustion and DoS attacks.
    - Security: Prevents path traversal and dangerous file names.
    
    Args:
        file_storage: Flask file storage object
        allowed_exts: Set of allowed file extensions
        allowed_mimetypes: Set of allowed MIME types
        check_size: Whether to check file size (default: True)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if file_storage is None:
        return False, "No file uploaded."

    filename = (file_storage.filename or "").strip()
    if not filename:
        return False, "Uploaded file must have a filename."

    # Security: Prevent path traversal attacks
    if ".." in filename or "/" in filename or "\\" in filename:
        logger.warning(
            "Path traversal attempt detected",
            context={"file_name": filename, "client_ip": get_remote_address()}
        )
        return False, "Invalid filename: path traversal detected"

    # Security: Prevent dangerous file names
    dangerous_patterns = [".exe", ".bat", ".cmd", ".sh", ".php", ".jsp", ".asp"]
    filename_lower = filename.lower()
    if any(pattern in filename_lower for pattern in dangerous_patterns):
        logger.warning(
            "Potentially dangerous file type detected",
            context={"file_name": filename, "client_ip": get_remote_address()}
        )
        return False, f"File type not allowed for security reasons"

    _, ext = os.path.splitext(filename.lower())
    if ext not in allowed_exts:
        return (
            False,
            f"File '{filename}' has unsupported extension '{ext}'. "
            f"Allowed: {', '.join(sorted(allowed_exts))}",
        )

    mimetype = (file_storage.mimetype or "").lower()
    if mimetype and mimetype not in allowed_mimetypes:
        # Some browsers send slightly different CSV/Excel mimetypes;
        # be tolerant but log mismatches.
        logger.warning(
            f"MIME type mismatch for file '{filename}'",
            context={
                "file_name": filename,
                "detected_mimetype": mimetype,
                "allowed_mimetypes": list(allowed_mimetypes)
            }
        )

    # File size validation (memory protection)
    if check_size:
        try:
            # Get file size by seeking to end
            current_pos = file_storage.tell()
            file_storage.seek(0, 2)  # Seek to end
            file_size = file_storage.tell()
            file_storage.seek(current_pos)  # Reset to original position
            
            if file_size > MAX_FILE_SIZE_BYTES:
                size_mb = file_size / (1024 * 1024)
                max_mb = MAX_FILE_SIZE_MB
                return (
                    False,
                    f"File '{filename}' is too large ({size_mb:.2f} MB). "
                    f"Maximum allowed size is {max_mb} MB per file."
                )
            
            # Log large file uploads for monitoring
            if file_size > 50 * 1024 * 1024:  # > 50 MB
                logger.info(
                    f"Large file uploaded: {filename}",
                    context={
                        "file_name": filename,
                        "file_size_mb": round(file_size / (1024 * 1024), 2)
                    }
                )
        except Exception as e:
            # If we can't determine file size, log warning but allow (might be streaming)
            logger.warning(
                f"Could not determine file size for '{filename}'",
                context={"file_name": filename},
                error=e
            )

    return True, None


def _validate_total_file_size(file_sizes: List[int]) -> tuple[bool, str | None]:
    """
    Validate that the total size of all uploaded files doesn't exceed limits.
    This prevents memory exhaustion from multiple large files.
    
    Args:
        file_sizes: List of file sizes in bytes
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    total_size = sum(file_sizes)
    
    if total_size > MAX_TOTAL_SIZE_BYTES:
        total_mb = total_size / (1024 * 1024)
        max_mb = MAX_TOTAL_SIZE_MB
        return (
            False,
            f"Total size of all uploaded files ({total_mb:.2f} MB) exceeds "
            f"maximum allowed ({max_mb} MB). Please reduce file sizes or split into multiple requests."
        )
    
    return True, None


def _estimate_memory_usage(file_sizes: List[int], file_types: List[str]) -> float:
    """
    Estimate memory usage in MB based on file sizes and types.
    This is a conservative estimate to help prevent OOM errors.
    
    Args:
        file_sizes: List of file sizes in bytes
        file_types: List of file extensions (e.g., ['.pdf', '.xlsx'])
    
    Returns:
        Estimated memory usage in MB
    """
    total_size_mb = sum(file_sizes) / (1024 * 1024)
    
    # Memory multiplier based on file type:
    # - Images: 3-5x (OCR processing creates multiple copies)
    # - PDFs: 2-3x (text extraction + processing)
    # - Excel/CSV: 1.5-2x (pandas DataFrames)
    multipliers = {
        '.pdf': 2.5,
        '.png': 4.0,
        '.jpg': 4.0,
        '.jpeg': 4.0,
        '.tif': 4.0,
        '.tiff': 4.0,
        '.xlsx': 1.8,
        '.xls': 1.8,
        '.csv': 1.5,
    }
    
    estimated_memory = 0
    for size_bytes, ext in zip(file_sizes, file_types):
        size_mb = size_bytes / (1024 * 1024)
        multiplier = multipliers.get(ext.lower(), 2.0)  # Default 2x
        estimated_memory += size_mb * multiplier
    
    # Add base memory overhead (Python, libraries, etc.)
    estimated_memory += 100  # ~100 MB base
    
    return estimated_memory


def fetch_recent_reconciliations(
    limit: int = 50,
    search: str = None,
    date_from: str = None,
    date_to: str = None,
    min_matches: int = None,
    max_matches: int = None
) -> List[Dict[str, Any]]:
    """
    Return the most recent reconciliation runs from the database with filtering support.
    Enhanced with caching for better performance.
    """
    # Create cache key from parameters
    cache_key = f"reconciliations_{limit}_{search}_{date_from}_{date_to}_{min_matches}_{max_matches}"
    cached_result = cache_get(cache_key)
    if cached_result is not None:
        return cached_result
    """
    Return the most recent reconciliation runs from the database with filtering support.
    This is useful for showing a simple "history" view in the UI.
    
    Args:
        limit: Maximum number of results to return
        search: Search term to filter by invoice_file or bank_file names
        date_from: Filter reconciliations created on or after this date (YYYY-MM-DD)
        date_to: Filter reconciliations created on or before this date (YYYY-MM-DD)
        min_matches: Minimum match count filter
        max_matches: Maximum match count filter
    """
    # Guardrail on limit so a bad client cannot request millions of rows
    safe_limit = max(1, min(int(limit), 500))

    results = db_manager.execute_query(query, params)

    # Build query with filters
    query = """
        SELECT
            id,
            invoice_file,
            bank_file,
            total_invoice_rows,
            total_bank_rows,
            match_count,
            only_in_invoices_count,
            only_in_bank_count,
            invoice_file_date,
            bank_file_date,
            created_at
        FROM reconciliations
        WHERE 1=1
    """
    params = []
    
    # Search filter
    if search:
        query += " AND (invoice_file LIKE ? OR bank_file LIKE ?)"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])
    
    # Date range filters
    if date_from:
        query += " AND DATE(created_at) >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND DATE(created_at) <= ?"
        params.append(date_to)
    
    # Match count filters
    if min_matches is not None:
        query += " AND match_count >= ?"
        params.append(min_matches)
    
    if max_matches is not None:
        query += " AND match_count <= ?"
        params.append(max_matches)
    
    # Order and limit
    query += " ORDER BY datetime(created_at) DESC, id DESC LIMIT ?"
    params.append(safe_limit)
    
    rows = [dict(r) for r in cur.fetchall()]
    
    # Cache result (shorter TTL if search/filters are used)
    cache_ttl = 60 if (search or date_from or date_to or min_matches or max_matches) else CACHE_TTL_SECONDS
    cache_set(cache_key, rows, ttl=cache_ttl)
    
    return rows


def fetch_reconciliation_matches_for_export(reconciliation_id: int) -> List[Dict[str, Any]]:
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                rm.id AS match_id,
                rm.reconciliation_id,
                rm.invoice_id,
                rm.transaction_id,
                rm.match_score,
                rm.match_type,
                rm.status AS match_status,
                rm.amount_difference,
                rm.date_difference,
                rm.confidence_score,
                rm.notes,
                rm.created_by AS match_created_by,
                rm.created_at AS match_created_at,
                rm.updated_at AS match_updated_at,

                inv.id AS invoice_db_id,
                inv.file_upload_id AS invoice_file_upload_id,
                inv.invoice_number,
                inv.invoice_date,
                inv.reference AS invoice_reference,
                inv.vendor_name,
                inv.vat_number,
                inv.total_amount,
                inv.tax_amount,
                inv.total_vat_rate,
                inv.total_zero_rated,
                inv.total_gbp,
                inv.net_amount,
                inv.due_date,
                inv.status AS invoice_status,
                inv.invoice_file_path,
                inv.invoice_file_hash,
                inv.description AS invoice_description,
                inv.confidence_score AS invoice_confidence_score,
                inv.created_at AS invoice_created_at,

                bt.id AS bank_transaction_db_id,
                bt.file_upload_id AS bank_file_upload_id,
                bt.transaction_date,
                bt.description AS bank_description,
                bt.amount AS bank_amount,
                bt.balance AS bank_balance,
                bt.transaction_type,
                bt.reference_number,
                bt.account_number,
                bt.category AS bank_category,
                bt.created_at AS bank_created_at
            FROM reconciliation_matches rm
            LEFT JOIN invoices inv ON rm.invoice_id = inv.id
            LEFT JOIN bank_transactions bt ON rm.transaction_id = bt.id
            WHERE rm.reconciliation_id = ?
            ORDER BY rm.match_score DESC, rm.id ASC
            """,
            (reconciliation_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def validate_manual_match_quality(
    invoice_data: Dict[str, Any],
    bank_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate the quality of a manual match and generate warnings for suspicious matches.
    
    Returns:
        Dictionary with:
        - is_valid: bool (True if match should be allowed, False if critical issues)
        - warnings: List[str] (warnings about potential issues)
        - errors: List[str] (critical errors that should block the match)
    """
    warnings = []
    errors = []
    thresholds = MANUAL_MATCH_WARNING_THRESHOLDS
    
    invoice_amount = float(invoice_data.get("amount", 0.0))
    bank_amount = float(bank_data.get("amount", 0.0))
    invoice_desc = invoice_data.get("description", "")
    bank_desc = bank_data.get("description", "")
    invoice_date = invoice_data.get("date")
    bank_date = bank_data.get("date")
    invoice_vendor = invoice_data.get("vendor_name")
    bank_vendor = bank_data.get("vendor_name")
    invoice_currency = invoice_data.get("currency")
    bank_currency = bank_data.get("currency")
    
    # 1. Amount validation
    if invoice_amount > 0 and bank_amount > 0:
        amount_diff = abs(invoice_amount - bank_amount)
        amount_diff_pct = (amount_diff / max(invoice_amount, bank_amount)) * 100
        
        # Critical: Very large amount difference (>50%)
        if amount_diff_pct > 50:
            errors.append(
                f"Very large amount difference: {amount_diff_pct:.1f}% "
                f"({invoice_amount} vs {bank_amount})"
            )
        # Warning: Significant amount difference
        elif amount_diff_pct > thresholds["amount_diff_percentage"]:
            warnings.append(
                f"Significant amount difference: {amount_diff_pct:.1f}% "
                f"({invoice_amount} vs {bank_amount})"
            )
        # Warning: Large absolute difference
        elif amount_diff > thresholds["amount_diff_absolute"]:
            warnings.append(
                f"Large absolute amount difference: {amount_diff:.2f} "
                f"({invoice_amount} vs {bank_amount})"
            )
    
    # 2. Date validation
    if invoice_date and bank_date:
        date_diff = _date_distance_days(invoice_date, bank_date)
        if date_diff is not None:
            if date_diff > thresholds["date_diff_days"] * 2:  # Critical: >2x threshold
                errors.append(
                    f"Very large date difference: {date_diff} days "
                    f"({invoice_date} vs {bank_date})"
                )
            elif date_diff > thresholds["date_diff_days"]:
                warnings.append(
                    f"Large date difference: {date_diff} days "
                    f"({invoice_date} vs {bank_date})"
                )
    
    # 3. Description similarity validation
    if invoice_desc and bank_desc:
        desc_sim = _description_similarity(invoice_desc, bank_desc)
        if desc_sim < thresholds["description_similarity"]:
            warnings.append(
                f"Low description similarity: {desc_sim:.1%} "
                f"(Invoice: '{invoice_desc[:50]}...' vs Bank: '{bank_desc[:50]}...')"
            )
    
    # 4. Vendor name validation
    if thresholds["vendor_mismatch_warning"] and invoice_vendor and bank_vendor:
        vendor_sim = _vendor_name_similarity(invoice_vendor, bank_vendor)
        if vendor_sim < 0.5:  # Less than 50% similarity
            warnings.append(
                f"Vendor name mismatch: '{invoice_vendor}' vs '{bank_vendor}' "
                f"(similarity: {vendor_sim:.1%})"
            )
    
    # 5. Currency validation
    if thresholds["currency_mismatch_warning"] and invoice_currency and bank_currency:
        if invoice_currency != bank_currency:
            warnings.append(
                f"Currency mismatch: {invoice_currency} vs {bank_currency}. "
                f"Ensure amounts are in the same currency or conversion is enabled."
            )
    
    # 6. Invoice number validation (if both have invoice numbers)
    invoice_inv_num = invoice_data.get("invoice_number")
    bank_inv_num = bank_data.get("invoice_number")
    if invoice_inv_num and bank_inv_num:
        inv_num_match = _invoice_number_match(invoice_inv_num, bank_inv_num)
        if inv_num_match < 0.5:  # Invoice numbers don't match
            warnings.append(
                f"Invoice number mismatch: '{invoice_inv_num}' vs '{bank_inv_num}'"
            )
    
    # Determine if match is valid (no critical errors)
    is_valid = len(errors) == 0
    
    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "errors": errors,
        "validation_score": len(warnings) + len(errors) * 2  # Weight errors more
    }


def delete_reconciliation(reconciliation_id: int) -> tuple[bool, str]:
    """
    Delete a reconciliation and all its associated matches.
    
    Returns:
        Tuple of (success, error_message)
    """
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        try:
            # Check if reconciliation exists
            cur.execute("SELECT id FROM reconciliations WHERE id = ?", (reconciliation_id,))
            if not cur.fetchone():
                return False, f"Reconciliation {reconciliation_id} not found"
            
            # Delete all matches first (foreign key constraint)
            cur.execute("DELETE FROM reconciliation_matches WHERE reconciliation_id = ?", (reconciliation_id,))
            matches_deleted = cur.rowcount
            
            # Delete reconciliation
            cur.execute("DELETE FROM reconciliations WHERE id = ?", (reconciliation_id,))
            
            # Invalidate cache
            cache_clear()
            cache_key = f"matches_{reconciliation_id}"
            with _cache_lock:
                if cache_key in _cache:
                    del _cache[cache_key]
            
            logger.info(
                f"Reconciliation {reconciliation_id} deleted",
                context={
                    "reconciliation_id": reconciliation_id,
                    "matches_deleted": matches_deleted
                }
            )
            
            return True, None
        except Exception as e:
            conn.rollback()
            error_msg = f"Error deleting reconciliation {reconciliation_id}: {str(e)}"
            logger.error("Error deleting reconciliation", context={"reconciliation_id": reconciliation_id}, error=e)
            return False, error_msg


# === File parsing helpers ===

def ocr_image_to_lines(file_bytes: bytes) -> List[str]:
    """
    ENHANCED OCR for invoices and bank statements - optimized for both scanned documents and photos.
    - Handles photos with shadows, glare, and poor lighting
    - Multiple preprocessing techniques for better accuracy
    - Tries multiple PSM modes for optimal results
    - Processes with progress updates for large images
    """
    print("Processing image with OCR...")
    start_time = time.time()
    
    image = Image.open(io.BytesIO(file_bytes))
    original_format = image.format

    # Step 1: Convert to RGB if needed (handles RGBA, P, etc.)
    if image.mode != 'RGB':
        rgb_image = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'RGBA':
            rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        else:
            rgb_image.paste(image)
        image = rgb_image

    # Step 2: Convert to grayscale for OCR
    image = image.convert("L")
    
    # Step 3: Enhance image quality for photos (reduce shadows, improve contrast)
    # Apply slight denoising to reduce noise from camera photos
    image = image.filter(ImageFilter.MedianFilter(size=3))  # Light denoising
    
    # Enhance contrast - critical for photos with poor lighting
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.3)  # Increase contrast by 30%
    
    # Enhance sharpness - helps with slightly blurred photos
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.2)  # Increase sharpness by 20%
    
    # Apply autocontrast to normalize brightness
    image = ImageOps.autocontrast(image, cutoff=2)  # 2% cutoff for better results

    # Step 4: Upscale small images – Tesseract generally works better with larger text
    # But don't upscale too much for large images (memory optimization)
    min_width = 1500
    max_width = 3000  # Don't upscale beyond this for performance
    original_width = image.width
    original_height = image.height
    
    if image.width < min_width:
        scale = min_width / float(image.width)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
        print(f"  Upscaled image from {original_width}x{original_height} to {image.width}x{image.height}")
    elif image.width > max_width:
        # Downscale very large images for faster processing
        scale = max_width / float(image.width)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
        print(f"  Downscaled large image from {original_width}x{original_height} to {image.width}x{image.height} for faster processing")

    # Step 5: Try multiple OCR configurations for best results
    # Primary: PSM 6 (uniform block of text) - best for invoices/statements
    # Fallback: PSM 4 (single column) if PSM 6 gives poor results
    # Using --oem 3 (LSTM neural nets) for better accuracy
    
    primary_config = r"--oem 3 --psm 6 -l eng"
    fallback_config = r"--oem 3 --psm 4 -l eng"  # Single column text
    
    print("  Running OCR with optimized settings for invoices/statements...")
    
    # Get OCR text with confidence scores
    ocr_data = pytesseract.image_to_data(image, config=primary_config, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(image, config=primary_config)
    
    # Calculate average confidence score
    confidences = [int(conf) for conf in ocr_data['conf'] if int(conf) > 0]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    
    print(f"  OCR Confidence: {avg_confidence:.1f}% (from {len(confidences)} words)")
    
    # Check if we got reasonable results (at least some text extracted)
    lines_primary = [line.strip() for line in text.splitlines() if line.strip()]
    
    # If primary mode extracted very little text (< 3 lines), try fallback mode
    if len(lines_primary) < 3 and len(lines_primary) > 0:
        print(f"  Primary OCR extracted {len(lines_primary)} lines, trying alternative mode...")
        text_fallback = pytesseract.image_to_string(image, config=fallback_config)
        lines_fallback = [line.strip() for line in text_fallback.splitlines() if line.strip()]
        # Use whichever mode extracted more lines
        if len(lines_fallback) > len(lines_primary):
            text = text_fallback
            lines_primary = lines_fallback
            # Recalculate confidence for fallback mode
            ocr_data_fallback = pytesseract.image_to_data(image, config=fallback_config, output_type=pytesseract.Output.DICT)
            confidences_fallback = [int(conf) for conf in ocr_data_fallback['conf'] if int(conf) > 0]
            if confidences_fallback:
                avg_confidence = sum(confidences_fallback) / len(confidences_fallback)
                print(f"  Fallback mode extracted {len(lines_fallback)} lines (using this result)")
                print(f"  Fallback OCR Confidence: {avg_confidence:.1f}%")

    ocr_time = time.time() - start_time
    lines = lines_primary
    
    # Quality validation
    quality_warnings = []
    if avg_confidence < 60:
        quality_warnings.append(f"Low OCR confidence ({avg_confidence:.1f}%) - results may be inaccurate")
    elif avg_confidence < 80:
        quality_warnings.append(f"Moderate OCR confidence ({avg_confidence:.1f}%) - review recommended")
    
    if len(lines) < 3:
        quality_warnings.append(f"Very few lines extracted ({len(lines)}) - document may be image-based or corrupted")
    
    print(f"✓ OCR completed in {ocr_time:.2f} seconds, extracted {len(lines)} lines")
    
    # Log quality indicators
    if len(lines) > 0:
        avg_line_length = sum(len(line) for line in lines) / len(lines)
        print(f"  Average line length: {avg_line_length:.1f} characters")
    
    # Log quality warnings
    if quality_warnings:
        print(f"  ⚠ Quality warnings:")
        for warning in quality_warnings:
            print(f"    - {warning}")
        logger.warning(
            "OCR quality warnings",
            context={
                "confidence": avg_confidence,
                "lines_extracted": len(lines),
                "warnings": quality_warnings
            }
        )
    
    print()  # Empty line for readability
    
    return lines


def pdf_to_lines(file_bytes: bytes) -> List[str]:
    """
    OPTIMIZED PDF text extraction for large PDFs (50+ pages, 1000+ transactions).
    - Processes pages in batches with progress updates
    - Handles corrupted or malformed PDFs by skipping problematic pages
    - Memory-efficient for large files
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        
        if total_pages == 0:
            print("Warning: PDF has no pages.")
            return []
        
        print(f"Processing PDF with {total_pages} pages...")
        
        all_text = ""
        pages_processed = 0
        progress_interval = max(1, total_pages // 10)  # Update every 10%
        
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
                all_text += page_text + "\n"
                pages_processed += 1
                
                # Progress update for large PDFs
                if total_pages > 10 and (i + 1) % progress_interval == 0:
                    progress = (i + 1) / total_pages * 100 if total_pages > 0 else 0.0
                    print(f"  PDF Progress: {progress:.0f}% ({i + 1}/{total_pages} pages processed)")
                    
            except Exception as e:
                # Skip problematic pages (e.g., corrupted character maps)
                print(f"Warning: Failed to extract text from page {i+1}: {e}")
                continue
        
        if pages_processed == 0:
            print("Warning: Could not extract text from any PDF pages. PDF may be corrupted or image-based.")
            return []
        
        print(f"✓ Extracted text from {pages_processed}/{total_pages} pages")
        
        lines = [line.strip() for line in all_text.splitlines() if line.strip()]
        print(f"✓ Extracted {len(lines)} text lines from PDF\n")
        return lines
    except Exception as e:
        # If PDF reading fails entirely, return empty list
        print(f"Error reading PDF: {e}")
        return []


def pdf_to_pages_lines(file_bytes: bytes) -> List[List[str]]:
    """Extract text lines per PDF page.
    Returns a list where each item is the list of non-empty stripped lines for that page.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_lines: List[List[str]] = []

        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
            pages_lines.append(lines)

        return pages_lines
    except Exception as e:
        print(f"Error reading PDF (page-wise): {e}")
        return []


def _split_invoice_sections(lines: List[str]) -> List[List[str]]:
    """Split a single invoice page into sections (e.g., TAX INVOICE / VAT INVOICE / PAYMENT ADVICE).
    This helps when a single page contains multiple invoice-like blocks.
    """
    if not lines:
        return []

    headers = ["tax invoice", "vat invoice", "payment advice"]
    split_idxs: List[int] = []
    for i, ln in enumerate(lines):
        low = ln.strip().lower()
        if any(h in low for h in headers):
            split_idxs.append(i)

    if not split_idxs:
        return [lines]

    split_idxs = sorted(set(split_idxs))
    if split_idxs[0] != 0:
        split_idxs = [0] + split_idxs

    sections: List[List[str]] = []
    for idx, start in enumerate(split_idxs):
        end = split_idxs[idx + 1] if idx + 1 < len(split_idxs) else len(lines)
        chunk = [ln for ln in lines[start:end] if ln.strip()]
        if chunk:
            sections.append(chunk)

    return sections


def detect_currency_from_text(text: str) -> str:
    """
    Detect currency symbol from text with improved accuracy.
    Prioritizes actual currency symbols over text patterns.
    Returns the most common currency symbol found, or None if not detected.
    
    Note: For multiple currencies, use detect_all_currencies_from_text() instead.
    """
    if not text or len(text.strip()) == 0:
        return None
    
    # Common currency symbols and their patterns (prioritize symbols)
    currency_patterns = {
        '$': [
            r'\$',  # Dollar symbol (highest priority)
            r'USD', r'US\$', r'\$\s*\d', r'\d+\s*\$',  # USD patterns
            r'dollars?', r'dollar\s+amount',
        ],
        '£': [
            r'£',  # Pound symbol (highest priority)
            r'GBP', r'£\s*\d', r'\d+\s*£',  # GBP patterns
            r'pounds?', r'pound\s+sterling',
        ],
        '€': [
            r'€',  # Euro symbol (highest priority)
            r'EUR', r'€\s*\d', r'\d+\s*€',  # EUR patterns
            r'euros?', r'euro\s+amount',
        ],
        '₹': [
            r'₹',  # Rupee symbol (highest priority)
            r'Rs\.', r'Rs\s', r'INR', r'₹\s*\d', r'\d+\s*₹',  # INR patterns
            r'rupees?', r'rupee\s+amount',
        ],
        '¥': [
            r'¥',  # Yen symbol
            r'JPY', r'¥\s*\d', r'\d+\s*¥',
            r'yen',
        ],
        'A$': [
            r'A\$',  # Australian Dollar
            r'AUD', r'A\$\s*\d',
        ],
        'C$': [
            r'C\$',  # Canadian Dollar
            r'CAD', r'C\$\s*\d',
        ],
    }
    
    currency_scores = {}
    text_lower = text.lower()
    
    # First pass: Look for currency symbols (higher weight)
    for currency, patterns in currency_patterns.items():
        score = 0
        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, text, re.IGNORECASE)
            # Symbol patterns get higher weight (first 2-3 patterns)
            if i < 3:
                score += len(matches) * 10  # High weight for symbols
            else:
                score += len(matches) * 1   # Lower weight for text patterns
        if score > 0:
            currency_scores[currency] = score
    
    if currency_scores:
        # Return the currency with highest score
        detected = max(currency_scores.items(), key=lambda x: x[1])[0]
        print(f"  ✓ Currency detected: {detected} (score: {currency_scores[detected]}, matches: {currency_scores[detected]//10})")
        return detected
    
    # If no currency detected, return None (don't default to ₹)
    # Only print if text is substantial (to avoid spam)
    if len(text) > 100:
        print(f"  ⚠ No currency detected in text (length: {len(text)} chars)")
    return None


def detect_all_currencies_from_text(text: str) -> Dict[str, int]:
    """
    Detect ALL currencies present in text and return their counts.
    Useful for files with mixed currencies.
    
    Returns:
        Dictionary mapping currency symbols to their occurrence counts
    """
    if not text or len(text.strip()) == 0:
        return {}
    
    # Same currency patterns as detect_currency_from_text
    currency_patterns = {
        '$': [r'\$', r'USD', r'US\$', r'\$\s*\d', r'\d+\s*\$', r'dollars?'],
        '£': [r'£', r'GBP', r'£\s*\d', r'\d+\s*£', r'pounds?'],
        '€': [r'€', r'EUR', r'€\s*\d', r'\d+\s*€', r'euros?'],
        '₹': [r'₹', r'Rs\.', r'Rs\s', r'INR', r'₹\s*\d', r'\d+\s*₹', r'rupees?'],
        '¥': [r'¥', r'JPY', r'¥\s*\d', r'\d+\s*¥', r'yen'],
        'A$': [r'A\$', r'AUD', r'A\$\s*\d'],
        'C$': [r'C\$', r'CAD', r'C\$\s*\d'],
    }
    
    currency_counts = {}
    
    for currency, patterns in currency_patterns.items():
        total_matches = 0
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            total_matches += len(matches)
        if total_matches > 0:
            currency_counts[currency] = total_matches
    
    return currency_counts


# === Currency Conversion Support ===
# Basic exchange rates (can be updated from external API in production)
# Rates are relative to USD (1 USD = X of other currency)
# Note: These are approximate rates - for production, use real-time exchange rate API
CURRENCY_EXCHANGE_RATES = {
    'USD': 1.0,      # Base currency
    '$': 1.0,        # USD
    '₹': 83.0,       # INR (approximate)
    'INR': 83.0,
    '£': 0.79,       # GBP (approximate)
    'GBP': 0.79,
    '€': 0.92,       # EUR (approximate)
    'EUR': 0.92,
    '¥': 150.0,      # JPY (approximate)
    'JPY': 150.0,
    'A$': 1.52,      # AUD (approximate)
    'AUD': 1.52,
    'C$': 1.35,      # CAD (approximate)
    'CAD': 1.35,
}

# Enable/disable currency conversion (set via environment)
ENABLE_CURRENCY_CONVERSION = os.environ.get("ENABLE_CURRENCY_CONVERSION", "0") == "1"

# === Manual Match Validation Configuration ===
# Thresholds for warning about suspicious manual matches
MANUAL_MATCH_WARNING_THRESHOLDS = {
    "amount_diff_percentage": float(os.environ.get("MANUAL_MATCH_AMOUNT_DIFF_PCT", "10.0")),  # 10% difference
    "amount_diff_absolute": float(os.environ.get("MANUAL_MATCH_AMOUNT_DIFF_ABS", "100.0")),  # ₹100 absolute difference
    "date_diff_days": int(os.environ.get("MANUAL_MATCH_DATE_DIFF_DAYS", "30")),  # 30 days difference
    "description_similarity": float(os.environ.get("MANUAL_MATCH_DESC_SIM", "0.3")),  # 30% similarity minimum
    "vendor_mismatch_warning": True,  # Warn if vendor names don't match
    "currency_mismatch_warning": True,  # Warn if currencies don't match
}

# === Transaction Deduplication Configuration ===
# Enable/disable automatic duplicate detection and removal
ENABLE_DEDUPLICATION = os.environ.get("ENABLE_DEDUPLICATION", "1") == "1"

# Tolerance for considering transactions as duplicates
# Two transactions are considered duplicates if:
# - Amount difference < DEDUP_AMOUNT_TOLERANCE
# - Description similarity > DEDUP_DESC_SIMILARITY
# - Date difference < DEDUP_DATE_TOLERANCE_DAYS
DEDUP_AMOUNT_TOLERANCE = float(os.environ.get("DEDUP_AMOUNT_TOLERANCE", "0.01"))  # 1 cent
DEDUP_DESC_SIMILARITY = float(os.environ.get("DEDUP_DESC_SIMILARITY", "0.95"))  # 95% similar
DEDUP_DATE_TOLERANCE_DAYS = int(os.environ.get("DEDUP_DATE_TOLERANCE_DAYS", "0"))  # Same day


def convert_currency(amount: float, from_currency: str, to_currency: str) -> float:
    """
    Convert amount from one currency to another using exchange rates.
    
    Args:
        amount: Amount to convert
        from_currency: Source currency symbol
        to_currency: Target currency symbol
    
    Returns:
        Converted amount, or original amount if conversion not possible
    """
    if not ENABLE_CURRENCY_CONVERSION:
        return amount
    
    if from_currency == to_currency:
        return amount
    
    # Normalize currency symbols
    from_curr = from_currency.upper() if len(from_currency) > 1 else from_currency
    to_curr = to_currency.upper() if len(to_currency) > 1 else to_currency
    
    # Get exchange rates
    from_rate = CURRENCY_EXCHANGE_RATES.get(from_currency) or CURRENCY_EXCHANGE_RATES.get(from_curr)
    to_rate = CURRENCY_EXCHANGE_RATES.get(to_currency) or CURRENCY_EXCHANGE_RATES.get(to_curr)
    
    if not from_rate or not to_rate:
        logger.warning(
            f"Currency conversion not available",
            context={
                "from_currency": from_currency,
                "to_currency": to_currency,
                "amount": amount
            }
        )
        return amount  # Return original if conversion not possible
    
    # Convert via USD: from_currency -> USD -> to_currency
    usd_amount = amount / from_rate
    converted_amount = usd_amount * to_rate
    
    return converted_amount


def detect_primary_currency_with_mixed_support(
    invoice_currencies: List[str],
    bank_currencies: List[str]
) -> tuple[str, Dict[str, Any]]:
    """
    Detect primary currency with support for mixed currencies.
    Returns primary currency and statistics about currency distribution.
    
    Args:
        invoice_currencies: List of currencies from invoice transactions
        bank_currencies: List of currencies from bank transactions
    
    Returns:
        Tuple of (primary_currency, currency_stats)
    """
    from collections import Counter
    
    all_currencies = invoice_currencies + bank_currencies
    valid_currencies = [c for c in all_currencies if c]
    
    if not valid_currencies:
        return '₹', {"distribution": {}, "mixed": False, "warning": "No currencies detected"}
    
    currency_counts = Counter(valid_currencies)
    total_count = len(valid_currencies)
    
    # Get most common currency
    primary_currency, primary_count = currency_counts.most_common(1)[0]
    primary_percentage = (primary_count / total_count) * 100 if total_count > 0 else 0.0
    
    # Check if mixed currencies (more than one currency with significant presence)
    mixed_threshold = 0.15  # 15% threshold
    significant_currencies = [
        (curr, count) for curr, count in currency_counts.items()
        if total_count > 0 and (count / total_count) >= mixed_threshold
    ]
    is_mixed = len(significant_currencies) > 1
    
    stats = {
        "distribution": dict(currency_counts),
        "primary_percentage": round(primary_percentage, 2),
        "mixed": is_mixed,
        "significant_currencies": [curr for curr, _ in significant_currencies],
        "total_transactions": total_count
    }
    
    if is_mixed:
        logger.warning(
            "Mixed currencies detected in reconciliation",
            context=stats
        )
    
    return primary_currency, stats


def parse_transactions_from_lines(
    lines: List[str], source: str
) -> List[Transaction]:
    """
    Parse transactions from OCR/PDF text lines with enhanced extraction.
    
    For invoices:
    - Extracts vendor/client names
    - Extracts invoice numbers
    - Handles invoice totals vs line items
    - Detects currency from text
    
    For bank statements:
    - Extracts payment descriptions
    - Extracts vendor names from descriptions
    - Extracts invoice numbers from descriptions
    - Detects currency from text
    """
    txs: List[Transaction] = []
    
    # Detect currency from all lines combined
    all_text = " ".join(lines)
    detected_currency = detect_currency_from_text(all_text)
    
    if detected_currency:
        print(f"  Currency detected in {source} file: {detected_currency}")
    else:
        print(f"  No currency detected in {source} file, will use default or detect from other files")
    
    # Extract invoice metadata (vendor name, invoice number, invoice date) from all lines
    vendor_name = None
    invoice_number = None
    invoice_date = None

    def _extract_invoice_structured_fields(invoice_lines: List[str], currency: str | None) -> Dict[str, Any]:
        """Best-effort structured extraction for invoice header, totals, and line-items."""
        text = "\n".join([l for l in invoice_lines if l])
        lower_text = text.lower()

        def _find_first(patterns: List[str]) -> str | None:
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
                if m:
                    val = (m.group(1) if m.groups() else m.group(0)).strip()
                    return val
            return None

        def _try_get_date_from_obj(obj):
            import re

            if obj is None:
                return None

            if isinstance(obj, dict):
                for k in (
                    "invoice_date",
                    "invoiceDate",
                    "due_date",
                    "dueDate",
                    "transaction_date",
                    "transactionDate",
                    "posting_date",
                    "postingDate",
                    "value_date",
                    "valueDate",
                    "date",
                    "Date",
                    "statement_period_start",
                    "statement_period_end",
                ):
                    v = obj.get(k)
                    if v is None:
                        continue
                    nv = _normalize_date_value(v)
                    if nv and (not re.search(r"invalid", str(nv), re.IGNORECASE)):
                        return nv

                # Search in "statements" -> "1" -> "transactions" -> "1", "2", etc. (bank statement format)
                statements = obj.get("statements")
                if isinstance(statements, dict):
                    for stmt_key, stmt_val in statements.items():
                        if isinstance(stmt_val, dict):
                            # Check statement_info for dates
                            stmt_info = stmt_val.get("statement_info")
                            if isinstance(stmt_info, dict):
                                got = _try_get_date_from_obj(stmt_info)
                                if got:
                                    return got
                            # Check transactions
                            txns = stmt_val.get("transactions")
                            if isinstance(txns, dict):
                                for tx_key, tx_val in txns.items():
                                    if isinstance(tx_val, dict):
                                        got = _try_get_date_from_obj(tx_val)
                                        if got:
                                            return got

                # Search in "uploads" -> "1", "2", etc. (invoice format)
                uploads = obj.get("uploads")
                if isinstance(uploads, dict):
                    for upl_key, upl_val in uploads.items():
                        if isinstance(upl_val, dict):
                            got = _try_get_date_from_obj(upl_val)
                            if got:
                                return got

                # Common nested shapes
                for list_key in ("records", "transactions", "invoices"):
                    v = obj.get(list_key)
                    if isinstance(v, list):
                        for it in v:
                            got = _try_get_date_from_obj(it)
                            if got:
                                return got

                er = obj.get("extracted_records")
                if isinstance(er, dict):
                    for list_key in ("records", "transactions", "invoices"):
                        v = er.get(list_key)
                        if isinstance(v, list):
                            for it in v:
                                got = _try_get_date_from_obj(it)
                                if got:
                                    return got

                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        got = _try_get_date_from_obj(v)
                        if got:
                            return got

            if isinstance(obj, list):
                for it in obj:
                    got = _try_get_date_from_obj(it)
                    if got:
                        return got

            return None

        def _derive_invoice_date(row: Dict[str, Any]) -> str | None:
            import json
            import re

            existing = _normalize_date_value(row.get("invoice_date"))
            if existing and (not re.search(r"invalid", str(existing), re.IGNORECASE)):
                return existing

            extracted_raw = row.get("invoice_extracted_data")
            if extracted_raw:
                try:
                    extracted_obj = json.loads(extracted_raw) if isinstance(extracted_raw, str) else extracted_raw
                except Exception:
                    extracted_obj = extracted_raw
                got = _try_get_date_from_obj(extracted_obj)
                if got:
                    return got

            upload_id = row.get("invoice_upload_id")
            if upload_id:
                try:
                    meta_row = cur.execute(
                        "SELECT metadata FROM file_uploads WHERE id = ? LIMIT 1",
                        (upload_id,),
                    ).fetchone()
                    meta_val = None
                    if meta_row:
                        meta_val = meta_row.get("metadata") if isinstance(meta_row, dict) else meta_row[0]
                    if meta_val:
                        try:
                            meta_obj = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                        except Exception:
                            meta_obj = meta_val
                        got = _try_get_date_from_obj(meta_obj)
                        if got:
                            return got
                except Exception:
                    pass

            return None

        def _derive_bank_date(row: Dict[str, Any]) -> str | None:
            import json
            import re

            existing = _normalize_date_value(row.get("bank_date"))
            if existing and (not re.search(r"invalid", str(existing), re.IGNORECASE)):
                return existing

            raw = row.get("bank_raw_data")
            if raw:
                try:
                    obj = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    obj = raw
                got = _try_get_date_from_obj(obj)
                if got:
                    return got

            upload_id = row.get("bank_upload_id")
            if upload_id:
                try:
                    meta_row = cur.execute(
                        "SELECT metadata FROM file_uploads WHERE id = ? LIMIT 1",
                        (upload_id,),
                    ).fetchone()
                    meta_val = None
                    if meta_row:
                        meta_val = meta_row.get("metadata") if isinstance(meta_row, dict) else meta_row[0]
                    if meta_val:
                        try:
                            meta_obj = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                        except Exception:
                            meta_obj = meta_val
                        got = _try_get_date_from_obj(meta_obj)
                        if got:
                            return got
                except Exception:
                    pass

            return None

        def _parse_money(s: str) -> float | None:
            if not s:
                return None
            try:
                return float(str(s).replace(",", "").strip())
            except Exception:
                return None

        # Header fields
        extracted: Dict[str, Any] = {
            "invoice_date": _find_first([
                r"\binvoice\s*date\b\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b",
                r"\binvoice\s*date\b\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
            ]),
            "invoice_number": _find_first([
                r"\binvoice\s*number\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
                r"\binvoice\s*(?:no\.?|#)\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
            ]),
            "reference": _find_first([
                r"\breference\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\s\-/]{1,})\b",
            ]),
            "vat_number": _find_first([
                r"\bvat\s*number\b\s*[:\-]?\s*([A-Za-z0-9]{6,})\b",
                r"\bvat\s*no\.?\b\s*[:\-]?\s*([A-Za-z0-9]{6,})\b",
            ]),
        }

        # OCR/PDF often splits label and value across lines, e.g.:
        # "Invoice Number" (line) then "INV-0111" (next line)
        # or "Invoice No:" (line) then "UA01INV202400577" (next line)
        if not extracted.get("invoice_number"):
            label_re = re.compile(r"\binvoice\s*(?:number|no\.?|#)\b", re.IGNORECASE)
            for i, raw in enumerate(invoice_lines):
                line = (raw or "").strip()
                if not line:
                    continue
                low = line.lower()
                if "invoice date" in low:
                    continue
                if not label_re.search(line):
                    continue

                # 1) Try same-line value after ':'
                same_line = re.search(
                    r"\binvoice\s*(?:number|no\.?|#)\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
                    line,
                    re.IGNORECASE,
                )
                if same_line:
                    extracted["invoice_number"] = same_line.group(1).strip().upper()
                    break

                # 2) Otherwise pick next non-empty line as candidate value
                for j in range(i + 1, min(i + 4, len(invoice_lines))):
                    nxt = (invoice_lines[j] or "").strip()
                    if not nxt:
                        continue
                    nxt_low = nxt.lower()
                    if "invoice" in nxt_low and ("date" in nxt_low or "number" in nxt_low or "no" in nxt_low):
                        continue
                    # Avoid dates being mistaken as invoice numbers
                    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", nxt) or re.search(r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", nxt):
                        continue
                    mval = re.search(r"\b([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b", nxt)
                    if mval:
                        extracted["invoice_number"] = mval.group(1).strip().upper()
                        break
                if extracted.get("invoice_number"):
                    break

        # Totals (subtotal, total vat, total zero rated, total payable)
        totals: Dict[str, float] = {}
        for line in invoice_lines:
            if not line:
                continue
            lower = line.lower()
            if not re.search(r"\d", line):
                continue

            def _extract_last_number() -> float | None:
                nums = re.findall(r"[-+]?\d[\d,]*\.?\d*", line)
                if not nums:
                    return None
                # Prefer last numeric token (often the amount at end of line)
                return _parse_money(nums[-1])

            amt = _extract_last_number()
            if amt is None:
                continue

            if "subtotal" in lower:
                totals["subtotal"] = amt
            elif "total vat" in lower:
                totals["total_vat"] = amt
            elif "total zero rated" in lower:
                totals["total_zero_rated"] = amt
            elif "total gbp" in lower or "grand total" in lower or "amount due" in lower or "invoice total" in lower:
                totals["total"] = amt

        extracted["totals"] = totals
        if currency:
            extracted["currency"] = currency

        # Line items (Description, Quantity, Unit Price, VAT, Amount)
        # Best-effort: detect rows that look like: <desc> <qty> <unit_price> <vat> <amount>
        items: List[Dict[str, Any]] = []
        row_re = re.compile(
            r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<unit>\d+(?:\.\d+)?)\s+(?P<vat>(?:zero\s*rated|\d{1,2}%))\s+(?P<amt>\d[\d,]*\.\d{2})\s*$",
            re.IGNORECASE,
        )
        for line in invoice_lines:
            raw = (line or "").strip()
            if not raw:
                continue
            if raw.lower().startswith("description"):
                continue
            if any(k in raw.lower() for k in ["subtotal", "total vat", "total gbp", "total zero rated", "invoice number", "invoice date", "vat number", "reference"]):
                continue
            m = row_re.match(raw)
            if not m:
                continue
            items.append(
                {
                    "description": m.group("desc").strip(),
                    "quantity": _parse_money(m.group("qty")),
                    "unit_price": _parse_money(m.group("unit")),
                    "vat": m.group("vat").strip(),
                    "amount_gbp": _parse_money(m.group("amt")),
                }
            )
        extracted["line_items"] = items

        # Normalize some strings
        if extracted.get("reference"):
            extracted["reference"] = str(extracted["reference"]).strip()
        if extracted.get("invoice_number"):
            extracted["invoice_number"] = str(extracted["invoice_number"]).strip().upper()
        if extracted.get("vat_number"):
            extracted["vat_number"] = str(extracted["vat_number"]).strip()

        extracted["source_text_contains_tax_invoice"] = "tax invoice" in lower_text
        return extracted

    def _extract_reference_id(text: str) -> str | None:
        if not text:
            return None
        m = re.search(
            r"(?:transaction\s*id|txn\s*id|reference|ref\.?|booking\s*(?:ref|id)|order\s*id|invoice\s*(?:no|number|#)?)[\s:]*([A-Za-z0-9\-]{4,})",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip().upper()
        return None

    document_subtype = None
    lower_all = all_text.lower()
    if "payment advice" in lower_all:
        document_subtype = "payment_advice"
    elif "vat invoice" in lower_all:
        document_subtype = "vat_invoice"
    elif "tax invoice" in lower_all:
        document_subtype = "tax_invoice"
    
    if source == "invoice":
        # Look for vendor/client name patterns
        for line in lines:
            lower = line.lower()
            # Patterns: "Client:", "Vendor:", "To:", "Bill To:", "Customer:"
            vendor_patterns = [
                r"(?:client|vendor|customer|bill\s+to|to)[\s:]+([A-Za-z0-9\s&.,\-]+)",
                r"^([A-Za-z0-9\s&.,\-]+)\s+(?:pvt|ltd|limited|inc|incorporated|llc)",
            ]
            for pattern in vendor_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    vendor_name = match.group(1).strip()
                    # Clean up common suffixes
                    vendor_name = re.sub(r'\s+(pvt|ltd|limited|inc|incorporated|llc)\.?$', '', vendor_name, flags=re.IGNORECASE).strip()
                    break
        
        # Look for invoice number patterns
        for line in lines:
            # Patterns: "Invoice No:", "INV-", "Invoice #", "Invoice Number:"
            inv_patterns = [
                r"\binvoice\s*(?:number|no\.?|#)?\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
                r"\binvoice\s*number\b\s*[:\-]?\s*(\d{4,})\b",
                r"\bINV\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
                r"\bINV[-/]?[A-Za-z0-9\-\/]{3,}\b",
            ]
            for pattern in inv_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    invoice_number = (match.group(1) if match.groups() else match.group(0)).strip().upper()
                    break
        
        # Look for invoice date in header
        for line in lines:
            # Pattern: "Date: DD-MMM-YYYY" or similar
            date_match = re.search(r"(?:date|dated?)[\s:]*(\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})", line, re.IGNORECASE)
            if date_match:
                invoice_date = date_match.group(1)
                break

        best_total = None
        best_total_weight = -1
        best_total_line = None
        for line in lines:
            lower = line.lower()
            weight = 0
            # Avoid VAT-only totals or informational totals winning over payable total
            if "total vat" in lower or ("vat" in lower and re.search(r"\btotal\b", lower)):
                weight = 1
            elif "total zero rated" in lower or "zero rated" in lower and re.search(r"\btotal\b", lower):
                weight = 1
            elif "subtotal" in lower:
                weight = 1
            if "invoice total" in lower:
                weight = 4
            elif "amount due" in lower or "total due" in lower:
                weight = 4
            elif "grand total" in lower:
                weight = 4
            elif "total gbp" in lower or "total gdp" in lower:
                weight = 4
            elif re.search(r"\btotal\b", lower):
                weight = 2
            if weight == 0:
                continue

            amounts: List[float] = []
            if detected_currency and detected_currency in line:
                cur_re = re.compile(rf"{re.escape(detected_currency)}\s*([0-9,]+\.?[0-9]*)")
                for a in cur_re.findall(line):
                    try:
                        amounts.append(float(a.replace(",", "")))
                    except ValueError:
                        continue
            if not amounts:
                for ns in re.findall(r"[-+]?\d[\d,]*\.?\d*", line):
                    try:
                        val = float(ns.replace(",", ""))
                    except ValueError:
                        continue
                    if 1900 <= val <= 2100 and ns.isdigit():
                        continue
                    if val >= MIN_TRANSACTION_AMOUNT:
                        amounts.append(val)

            if not amounts:
                continue
            candidate_total = max(amounts)
            if weight > best_total_weight or (weight == best_total_weight and (best_total is None or candidate_total > best_total)):
                best_total_weight = weight
                best_total = candidate_total
                best_total_line = line.strip()

        if best_total is not None:
            ref_id = _extract_reference_id(all_text)
            structured_fields = _extract_invoice_structured_fields(lines, detected_currency)
            # Prefer explicit header fields if available
            header_invoice_no = structured_fields.get("invoice_number")
            header_invoice_date = structured_fields.get("invoice_date")
            header_ref = structured_fields.get("reference")
            if header_invoice_no and not invoice_number:
                invoice_number = str(header_invoice_no).strip().upper()
            if header_invoice_date and not invoice_date:
                invoice_date = str(header_invoice_date).strip()
            if header_ref and not ref_id:
                ref_id = str(header_ref).strip()[:255]

            tx = Transaction(
                    source=source,
                    description=best_total_line or "Total",
                    amount=float(best_total),
                    date=invoice_date,
                    vendor_name=vendor_name,
                    invoice_number=invoice_number,
                    currency=detected_currency,
                    reference_id=ref_id,
                    direction=None,
                    document_subtype=document_subtype,
                )
            try:
                setattr(tx, "extracted_fields", structured_fields)
            except Exception:
                pass
            return [tx]

    # Date pattern like "29 Feb 2024" or "29 Feb 2025"
    date_prefix_re = re.compile(r"^\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b")
    
    # Pattern for DD/MM/YYYY format (common in UK/invoices)
    date_dd_mm_yyyy_pattern = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b")
    
    # Pattern for DD-MMM-YYYY or DD-Mon-YYYY at start of line
    date_pattern_start = re.compile(r"^(\d{1,2}[-/]\w{3}[-/]\d{4})\b", re.IGNORECASE)

    revolut_table_mode = False

    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue

        lower = raw_line.lower()

        # Extra noise filtering for bank PDFs / images
        if any(keyword in lower for keyword in BANK_NOISE_KEYWORDS):
            continue

        # Revolut Business statements often have a table with columns:
        # Date | Description | Money out | Money in | Balance
        # The header row can be present once, and subsequent rows contain 3 amounts.
        if source == "bank":
            if ("money out" in lower and "money in" in lower and "balance" in lower):
                revolut_table_mode = True
                continue

        # Initialize variables for this line
        direction = None
        amount: float | None = None
        extracted_balance = None
        
        # For bank statements, try to extract balance from the amounts
        if source == "bank" and detected_currency and detected_currency in raw_line and date_prefix_re.match(raw_line):
            cur_re = re.compile(rf"{re.escape(detected_currency)}\s*([0-9,]+\.?[0-9]*)")
            money_vals: List[float] = []
            for a in cur_re.findall(raw_line):
                try:
                    money_vals.append(float(a.replace(",", "")))
                except ValueError:
                    continue

            # Revolut table rows: last 3 currency amounts are usually money out, money in, balance.
            if revolut_table_mode and len(money_vals) >= 3:
                money_out = money_vals[-3]
                money_in = money_vals[-2]
                balance = money_vals[-1]  # Extract balance

                if abs(money_out) >= MIN_TRANSACTION_AMOUNT and abs(money_in) < MIN_TRANSACTION_AMOUNT:
                    amount = float(money_out)
                    direction = "debit"
                elif abs(money_in) >= MIN_TRANSACTION_AMOUNT and abs(money_out) < MIN_TRANSACTION_AMOUNT:
                    amount = float(money_in)
                    direction = "credit"
                elif abs(money_out) >= MIN_TRANSACTION_AMOUNT and abs(money_in) >= MIN_TRANSACTION_AMOUNT:
                    # Rare, but pick the larger magnitude as the effective movement.
                    if abs(money_out) >= abs(money_in):
                        amount = float(money_out)
                        direction = "debit"
                    else:
                        amount = float(money_in)
                        direction = "credit"
                
                # Store the balance for later use
                extracted_balance = float(balance)
            elif len(money_vals) >= 2:
                # Generic bank parsing when currency amounts appear in line.
                # Prefer the second-to-last amount (often the movement) over last amount (often balance).
                amount = float(money_vals[-2])
                # If there are 3+ amounts, the last one might be balance
                if len(money_vals) >= 3:
                    extracted_balance = float(money_vals[-1])
                else:
                    extracted_balance = None

        if amount is None:
            num_strings = re.findall(r"[-+]?\d[\d,]*\.?\d*", raw_line)
            numbers: List[float] = []
            for ns in num_strings:
                try:
                    val = float(ns.replace(",", ""))
                except ValueError:
                    continue

                # Skip years (1900-2100) - these are likely dates, not amounts
                if 1900 <= val <= 2100 and ns.isdigit():
                    continue
                
                # Skip invoice IDs and other non-amount numbers:
                # - If it's part of a pattern like INV-101, REF-123, etc.
                # - If it's too small to be a real transaction amount
                # - If it's likely a date component
                
                # Check if this number is part of an invoice ID or reference pattern
                context_patterns = [
                    r'INV[-/]?[0-9]+',
                    r'REF[-/]?[0-9]+',
                    r'INVOICE[-/]?[0-9]+',
                    r'ORDER[-/]?[0-9]+',
                    r'TXN[-/]?[0-9]+',
                    r'TRANS[-/]?[0-9]+'
                ]
                
                is_part_of_id = False
                for pattern in context_patterns:
                    if re.search(pattern, raw_line, re.IGNORECASE):
                        # Check if this number appears right after the pattern
                        pattern_with_num = pattern.replace('[0-9]+', ns)
                        if re.search(pattern_with_num, raw_line, re.IGNORECASE):
                            is_part_of_id = True
                            break
                
                if is_part_of_id:
                    continue
                
                # Additional check: if this looks like a date component, skip it
                # when it appears in date contexts
                if val <= 31:
                    # Check if it's part of a date pattern
                    date_patterns = [
                        r'\b{0}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{{4}}'.format(ns),
                        r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+{0}\s+\d{{4}}'.format(ns),
                        r'\b{0}[/-]\d{{1,2}}[/-]\d{{4}}'.format(ns),
                        r'\b\d{{1,2}}[/-]{0}[/-]\d{{4}}'.format(ns),
                        r'\b{0}[-/]\w{{3}}[-/]\d{{4}}'.format(ns),  # DD-MMM-YYYY
                        r'\b\w{{3}}[-/]{0}[-/]\d{{4}}'.format(ns),   # MMM-DD-YYYY
                    ]
                    
                    is_date_component = False
                    for date_pattern in date_patterns:
                        if re.search(date_pattern, raw_line, re.IGNORECASE):
                            is_date_component = True
                            break
                    
                    # Also check if this number appears with month names in the line
                    if any(month in raw_line.lower() for month in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']):
                        # Look for patterns like "01-Jan-2025" or "Jan-01-2025"
                        if re.search(r'\b{0}[-/]\w{{3}}[-/]\d{{4}}\b|\b\w{{3}}[-/]{0}[-/]\d{{4}}\b'.format(ns), raw_line, re.IGNORECASE):
                            is_date_component = True
                        elif re.search(r'\b(?:date|dated?)\s*[:]?\s*.*{0}'.format(ns), raw_line, re.IGNORECASE):
                            is_date_component = True
                    
                    if is_date_component:
                        continue  # Skip date components
                
                # Skip very small values that are likely not real transaction amounts
                if val < MIN_TRANSACTION_AMOUNT:
                    continue
                
                numbers.append(val)

            if not numbers:
                continue

        # Choose amount:
        # - if the line looks like a real transaction (has a date prefix + keyword),
        #   and we have >=2 numbers, use the second last value as amount.
        has_date_prefix = bool(date_prefix_re.match(raw_line))
        has_txn_keyword = any(k in lower for k in TIDE_TRANSACTION_KEYWORDS)

        if amount is None:
            if has_date_prefix and has_txn_keyword and len(numbers) >= 2:
                amount = numbers[-2]
            elif source == "bank" and has_date_prefix and len(numbers) >= 2:
                amount = numbers[-2]
            else:
                amount = numbers[-1]

        # Ignore very small values that are likely noise or non‑monetary
        if amount is None or abs(amount) < MIN_TRANSACTION_AMOUNT:
            continue

        # Date detection with multiple patterns
        date_token = None
        tokens = raw_line.replace(",", " ").split()
        
        # Pattern 1: ISO style (YYYY-MM-DD)
        for t in tokens:
            if len(t) == 10 and t[4] == "-" and t[7] == "-":
                date_token = t
                break
        
        # Pattern 2: DD-MMM-YYYY or DD-Mon-YYYY (e.g., "01-Jan-2025")
        if not date_token:
            date_pattern_dd_mmm_yyyy = re.compile(r"\b(\d{1,2}[-/]\w{3}[-/]\d{4})\b", re.IGNORECASE)
            match = date_pattern_dd_mmm_yyyy.search(raw_line)
            if match:
                date_token = match.group(1)
        
        # Pattern 3: DD-MM-YYYY or DD/MM/YYYY (prioritize this for invoice dates)
        if not date_token:
            match = date_dd_mm_yyyy_pattern.search(raw_line)
            if match:
                date_token = match.group(1)
                # Ensure proper format (use / as separator for consistency)
                date_token = date_token.replace("-", "/")
        
        # Pattern 4: Extract date from "Date: DD-MMM-YYYY" or similar patterns
        if not date_token:
            date_colon_pattern = re.compile(r"(?:date|dated?)[\s:]*(\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})", re.IGNORECASE)
            match = date_colon_pattern.search(raw_line)
            if match:
                date_token = match.group(1)
        
        # Pattern 5: Tide style "29 Feb 2024" or "29 Feb 2025"
        if not date_token:
            m = date_prefix_re.match(raw_line)
            if m:
                date_token = m.group(1)

        # For invoices, use extracted metadata; for bank, extract from description
        final_vendor = vendor_name
        final_inv_num = invoice_number
        final_date = date_token or invoice_date

        # For invoices that contain multiple invoice rows (e.g. INV-101, INV-102...),
        # extract invoice number per line so each transaction carries its own invoice_number.
        if source == "invoice":
            inv_num_patterns = [
                r"\b(INV[-/]?[A-Za-z0-9\-]+)\b",
                r"(?:invoice\s*(?:no|number|#)?[\s:]*)\b([A-Za-z0-9\-]+)\b",
            ]
            for pattern in inv_num_patterns:
                inv_num_match = re.search(pattern, raw_line, re.IGNORECASE)
                if inv_num_match:
                    extracted = inv_num_match.group(1).strip().upper()
                    if len(extracted) >= 3:
                        final_inv_num = extracted
                        break
        
        # For bank statements, try to extract vendor name and invoice number from description
        if source == "bank":
            # Extract vendor name from bank description 
            # Pattern 1: "CARLSBERG MARSTONS BREWING COMPANY / ref: KA POLEBROOK"
            # Pattern 2: "Payment received from ABC Pvt Ltd"
            # Pattern 3: Vendor name at start before "/ ref:" or "ref:"
            vendor_patterns = [
                r"^([A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc|company|brewing|wholesale|group|holdings|enterprises|traders|solutions|services|systems))\s*/?\s*(?:ref|reference)",
                r"(?:from|to|payment\s+(?:to|from)|paid\s+to|paid\s+by|received\s+from)[\s:]+([A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc|company|group|holdings))",
                r"^([A-Z][A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc|company|brewing|wholesale|group|holdings|enterprises))(?:\s+/|\s+ref|$)",
                r"([A-Z][A-Za-z0-9\s&.,\-]{3,}(?:\s+(?:pvt|ltd|limited|inc|incorporated|llc|company|group|holdings))?)",  # More flexible pattern
            ]
            
            for pattern in vendor_patterns:
                vendor_match = re.search(pattern, raw_line, re.IGNORECASE)
                if vendor_match:
                    final_vendor = vendor_match.group(1).strip()
                    # Clean up but keep important parts
                    final_vendor = re.sub(r'\s+', ' ', final_vendor)  # Normalize spaces
                    # Don't remove company suffixes, just clean
                    if len(final_vendor) >= 3:  # Minimum length check
                        break

            # Extract invoice number from bank description
            # Look for patterns like "ref: INV-123" or "INV-123" or invoice numbers in ref
            inv_num_patterns = [
                r"(?:ref|reference|invoice\s*(?:no|number|#)?)[\s:]+(INV[-/]?[A-Za-z0-9\-]+|[A-Z]{2,}[-/]?[0-9]+)",
                r"(INV[-/]?[A-Za-z0-9\-]+)",
                r"\b([A-Z]{2,}[-/]?\d{3,})\b",  # Pattern like "KA1234" or "INV-1234" (reduced from 4+ to 3+ digits)
                r"\b([A-Z]{1,2}[-/]?\d{4,})\b",  # Pattern like "A1234" or "AB-1234"
                r"(?:invoice|inv|bill|order)[\s#:]+([A-Za-z0-9\-]+)",  # More flexible invoice number extraction
            ]

            for pattern in inv_num_patterns:
                inv_num_match = re.search(pattern, raw_line, re.IGNORECASE)
                if inv_num_match:
                    final_inv_num = inv_num_match.group(1).strip().upper()
                    # Clean up
                    final_inv_num = re.sub(r'^REF[:]?:\s*', '', final_inv_num, flags=re.IGNORECASE)
                    if len(final_inv_num) >= 3:  # Minimum length
                        break

        ref_id = _extract_reference_id(raw_line)
        
        txs.append(
            Transaction(
                source=source,
                description=raw_line,
                amount=float(amount),
                date=final_date,
                vendor_name=final_vendor,
                invoice_number=final_inv_num,
                currency=detected_currency,
                reference_id=ref_id,
                direction=direction,
                document_subtype=document_subtype,
                balance=extracted_balance,
            )
        )

    return txs


def deduplicate_transactions(transactions: List[Transaction]) -> tuple[List[Transaction], Dict[str, Any]]:
    """
    Remove duplicate transactions from a list.
    
    Two transactions are considered duplicates if:
    - Amount difference < DEDUP_AMOUNT_TOLERANCE
    - Description similarity > DEDUP_DESC_SIMILARITY
    - Date difference < DEDUP_DATE_TOLERANCE_DAYS (if both have dates)
    - Same currency (if both have currencies)
    
    Args:
        transactions: List of transactions to deduplicate
    
    Returns:
        Tuple of (deduplicated_transactions, stats_dict)
    """
    if not ENABLE_DEDUPLICATION or len(transactions) <= 1:
        return transactions, {
            "original_count": len(transactions),
            "deduplicated_count": len(transactions),
            "duplicates_removed": 0
        }
    
    original_count = len(transactions)
    unique_transactions: List[Transaction] = []
    seen_indices: set[int] = set()
    duplicates_removed = 0
    
    for i, tx1 in enumerate(transactions):
        if i in seen_indices:
            continue
        
        is_duplicate = False
        
        # Check against all previously seen unique transactions
        for j, tx2 in enumerate(unique_transactions):
            # Check amount similarity
            amount_diff = abs(tx1.amount - tx2.amount)
            if amount_diff > DEDUP_AMOUNT_TOLERANCE:
                continue
            
            # Check description similarity
            desc_sim = _description_similarity(tx1.description, tx2.description)
            if desc_sim < DEDUP_DESC_SIMILARITY:
                continue
            
            # Check date similarity (if both have dates)
            if tx1.date and tx2.date:
                date_diff = _date_distance_days(tx1.date, tx2.date)
                if date_diff is not None and date_diff > DEDUP_DATE_TOLERANCE_DAYS:
                    continue
            
            # Check currency match (if both have currencies)
            if tx1.currency and tx2.currency:
                if tx1.currency != tx2.currency:
                    continue
            
            # Check vendor name match (if both have vendor names)
            if tx1.vendor_name and tx2.vendor_name:
                vendor_sim = _vendor_name_similarity(tx1.vendor_name, tx2.vendor_name)
                if vendor_sim < 0.9:  # Very high threshold for vendor match
                    continue
            
            # Check invoice number match (if both have invoice numbers)
            if tx1.invoice_number and tx2.invoice_number:
                inv_num_match = _invoice_number_match(tx1.invoice_number, tx2.invoice_number)
                if inv_num_match < 0.9:  # Very high threshold for invoice number match
                    continue
            
            # This is a duplicate
            is_duplicate = True
            duplicates_removed += 1
            seen_indices.add(i)
            break
        
        if not is_duplicate:
            unique_transactions.append(tx1)
    
    stats = {
        "original_count": original_count,
        "deduplicated_count": len(unique_transactions),
        "duplicates_removed": duplicates_removed,
        "deduplication_rate": round((duplicates_removed / original_count * 100) if original_count > 0 else 0, 2)
    }
    
    if duplicates_removed > 0:
        logger.info(
            f"Deduplication removed {duplicates_removed} duplicate transactions",
            context=stats
        )
    
    return unique_transactions, stats


def excel_to_transactions(file_bytes: bytes, source: str) -> List[Transaction]:
    """
    Parse Excel file (.xlsx or .xls) and extract transactions.
    Tries to auto-detect columns for date, description, invoice number, and amount.
    
    For invoices:
    - Prefers "Invoice Total" or "Total" column over other amount columns
    - Extracts invoice numbers from "Invoice No" column
    - Extracts vendor name from headers or description
    
    For bank statements:
    - Detects "Paid in" and "Paid out" columns
    - Extracts vendor names from description/details columns
    """
    try:
        # Read Excel file
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        
        # Guardrail: avoid accidentally processing extremely large sheets
        if len(df) > MAX_EXCEL_ROWS:
            raise UserInputError(
                f"Excel file has too many rows ({len(df)}). "
                f"Maximum allowed is {MAX_EXCEL_ROWS} rows. "
                "Please split the file into smaller parts before uploading."
            )
        
        # Check if dataframe is empty or has no columns
        if df.empty or len(df.columns) == 0:
            print("Excel file is empty or has no columns")
            return []
        
        # Convert column names to lowercase for matching
        original_cols = df.columns.tolist()
        df.columns = [str(col).lower().strip() for col in df.columns]
        
        # Try to find columns - prioritize invoice-specific columns
        date_col = None
        desc_col = None
        amount_col = None
        inv_num_col = None
        vendor_name_val = None
        
        # First pass: Look for invoice-specific columns
        for col in df.columns:
            col_lower = str(col).lower()
            
            # Date column
            if date_col is None and any(x in col_lower for x in ["date", "txn date", "value date", "transaction date"]):
                date_col = col
            
            # Description column
            if desc_col is None and any(x in col_lower for x in ["description", "details", "narration", "particulars", "payee", "merchant", "transaction type"]):
                desc_col = col
            
            # Invoice number column
            if inv_num_col is None and any(x in col_lower for x in ["invoice no", "invoice number", "invoice#", "inv no", "inv number"]):
                inv_num_col = col
        
        # Amount column - prioritize invoice total for invoices
        for col in df.columns:
            col_lower = str(col).lower()
            if source == "invoice":
                # For invoices, prioritize "invoice total" or "total"
                if any(x in col_lower for x in ["invoice total", "total", "invoice amount", "total amount", "grand total"]):
                    amount_col = col
                    break
            else:
                # For bank statements, look for paid in/out
                if any(x in col_lower for x in ["paid in", "paid out", "amount", "amt", "value", "debit", "credit"]):
                    amount_col = col
                    break
        
        # Fallback: If amount column not found, try to find numeric columns
        if amount_col is None:
            for col in df.columns:
                if df[col].dtype in ['float64', 'int64']:
                    amount_col = col
                    break
        
        # Extract vendor name from sheet name or first few rows (if invoice)
        if source == "invoice":
            # Try to get vendor name from sheet name or first row
            try:
                # Check if there's a company name in the first few rows
                for idx in range(min(5, len(df))):
                    for col in df.columns:
                        cell_val = str(df.iloc[idx][col]) if not pd.isna(df.iloc[idx][col]) else ""
                        if any(keyword in cell_val.lower() for keyword in ["pvt", "ltd", "limited", "inc", "company", "wholesale"]):
                            vendor_match = re.search(r"([A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc|wholesale))", cell_val, re.IGNORECASE)
                            if vendor_match:
                                vendor_name_val = vendor_match.group(1).strip()
                                break
                    if vendor_name_val:
                        break
            except:
                pass
        
        # Detect currency from all cell values
        all_text = " ".join([str(val) for row in df.head(20).values for val in row if pd.notna(val)])
        detected_currency = detect_currency_from_text(all_text)
        
        txs: List[Transaction] = []
        
        for _, row in df.iterrows():
            # Get amount
            if amount_col is None:
                continue
            
            try:
                raw_amount = row[amount_col]
                if pd.isna(raw_amount):
                    continue
                
                # Convert to float, handling strings with commas/currency symbols
                amount_str = str(raw_amount).replace(",", "").replace("₹", "").replace("$", "").replace("£", "").strip()
                amount = float(amount_str)
            except (ValueError, TypeError):
                continue
            
            # Skip very small amounts (likely noise)
            if abs(amount) < MIN_TRANSACTION_AMOUNT:
                continue
            
            # Get description
            desc_val = ""
            if desc_col and desc_col in df.columns:
                desc_val = str(row[desc_col]) if not pd.isna(row[desc_col]) else ""
            
            # Get invoice number
            inv_num_val = None
            if inv_num_col and inv_num_col in df.columns:
                inv_num_cell = row[inv_num_col]
                if not pd.isna(inv_num_cell):
                    inv_num_val = str(inv_num_cell).strip().upper()
            
            # If invoice number not in separate column, try to extract from description
            if not inv_num_val and desc_val:
                inv_num_match = re.search(
                    r"\binvoice\s*(?:number|no\.?|#)?\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
                    desc_val,
                    re.IGNORECASE,
                )
                if inv_num_match:
                    inv_num_val = inv_num_match.group(1).strip().upper()
                else:
                    inv_num_match = re.search(r"\bINV[-/]?[A-Za-z0-9\-\/]{3,}\b", desc_val, re.IGNORECASE)
                    if inv_num_match:
                        inv_num_val = inv_num_match.group(0).strip().upper()
            
            # Extract vendor name from description if not already found
            vendor_name_from_desc = vendor_name_val
            if not vendor_name_from_desc and desc_val:
                vendor_match = re.search(r"([A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc|wholesale|company|brewing))", desc_val, re.IGNORECASE)
                if vendor_match:
                    vendor_name_from_desc = vendor_match.group(1).strip()
                    vendor_name_from_desc = re.sub(r'\s+(pvt|ltd|limited|inc|incorporated|llc)\.?$', '', vendor_name_from_desc, flags=re.IGNORECASE).strip()
            
            # Get date - handle DD/MM/YYYY format
            date_val = None
            if date_col and date_col in df.columns:
                date_cell = row[date_col]
                if not pd.isna(date_cell):
                    # Try to convert pandas Timestamp to string
                    if isinstance(date_cell, pd.Timestamp):
                        date_val = date_cell.strftime("%d/%m/%Y")  # Use DD/MM/YYYY format for UK
                    else:
                        date_str = str(date_cell)
                        # Try to parse DD/MM/YYYY format
                        date_match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", date_str)
                        if date_match:
                            date_val = date_match.group(1).replace("-", "/")
                        else:
                            date_val = date_str
            
            txs.append(
                Transaction(
                    source=source,
                    description=desc_val or (f"Invoice {inv_num_val}" if inv_num_val else ""),
                    amount=amount,
                    date=date_val,
                    vendor_name=vendor_name_from_desc,
                    invoice_number=inv_num_val,
                    currency=detected_currency,
                )
            )
        
        return txs
    except Exception as e:
        # If Excel parsing fails, return empty list
        print(f"Error parsing Excel file: {e}")
        return []


def csv_to_transactions(file_bytes: bytes, source: str) -> List[Transaction]:
    """
    Parse bank CSV with headers like: date, description, amount.
    """
    text = file_bytes.decode("utf-8", errors="ignore")
    
    # Detect currency from CSV text
    detected_currency = detect_currency_from_text(text)
    
    reader = csv.DictReader(io.StringIO(text))  # type: ignore[arg-type]

    # Try to map common header names
    fieldnames = [f.lower() for f in (reader.fieldnames or [])]

    def find_col(candidates: List[str]) -> str | None:
        for name in fieldnames:
            for cand in candidates:
                if cand in name:
                    return name
        return None

    date_col = find_col(["date", "txn date", "value date"])
    desc_col = find_col(["description", "details", "narration"])
    amount_col = find_col(["amount", "amt", "value"])

    txs: List[Transaction] = []
    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > MAX_CSV_ROWS:
            raise UserInputError(
                f"CSV file has too many rows ({row_count}). "
                f"Maximum allowed is {MAX_CSV_ROWS} rows. "
                "Please split the file into smaller parts before uploading."
            )
        try:
            raw_amount = row[amount_col] if amount_col else None  # type: ignore[index]
        except Exception:
            raw_amount = None

        if not raw_amount:
            continue

        try:
            amount = float(
                str(raw_amount)
                .replace(",", "")
                .replace("₹", "")
                .replace("$", "")
                .strip()
            )
        except ValueError:
            continue

        date_val = row[date_col] if date_col and row.get(date_col) else None  # type: ignore[index]
        desc_val = row[desc_col] if desc_col and row.get(desc_col) else ""  # type: ignore[index]

        # Try to extract vendor name and invoice number from CSV description
        vendor_name_val = None
        invoice_number_val = None
        
        if desc_val:
            # Extract vendor name
            vendor_match = re.search(r"(?:from|to|payment\s+(?:to|from)|client|vendor)[\s:]+([A-Za-z0-9\s&.,\-]+(?:pvt|ltd|limited|inc|incorporated|llc)?)", str(desc_val), re.IGNORECASE)
            if vendor_match:
                vendor_name_val = vendor_match.group(1).strip()
                vendor_name_val = re.sub(r'\s+(pvt|ltd|limited|inc|incorporated|llc)\.?$', '', vendor_name_val, flags=re.IGNORECASE).strip()
            
            # Extract invoice number
            inv_num_match = re.search(r"(INV[-/]?[A-Za-z0-9\-]+|[A-Z]{2,}[-/]?[0-9]+)", str(desc_val), re.IGNORECASE)
            if inv_num_match:
                invoice_number_val = inv_num_match.group(1).strip().upper()
        
        txs.append(
            Transaction(
                source=source,
                description=str(desc_val),
                amount=amount,
                date=str(date_val) if date_val else None,
                vendor_name=vendor_name_val,
                invoice_number=invoice_number_val,
                currency=detected_currency,
            )
        )

    return txs


def _normalize_text(text: str | None) -> str:
    """
    Normalise free‑text descriptions for more robust matching.

    - lowercase
    - remove currency symbols / punctuation
    - drop very short tokens
    - drop very long numeric tokens (likely account / reference numbers)
    - remove date prefixes like "Date:" for better matching
    """
    if not text:
        return ""

    s = str(text).lower()

    # Remove obvious symbols and common prefixes
    s = s.replace("₹", "").replace("$", "").replace("£", "")
    
    # Remove date prefixes like "date:", "dated:" etc.
    s = re.sub(r"^(date|dated?)[\s:]*", "", s)

    # Keep only letters, numbers and whitespace
    s = re.sub(r"[^a-z0-9\s]", " ", s)

    tokens: List[str] = []
    for tok in s.split():
        # Remove very short tokens like "of", "to", "in"
        if len(tok) <= 2:
            continue
        # Remove long pure numbers (likely account / reference numbers)
        # But keep shorter numbers as they might be invoice numbers
        if tok.isdigit() and len(tok) > 8:
            continue
        tokens.append(tok)

    return " ".join(tokens)


def _extract_key_terms(text: str | None) -> set[str]:
    """
    Extract key terms from text for better matching.
    Returns a set of meaningful words/numbers.
    """
    if not text:
        return set()
    
    normalized = _normalize_text(text)
    if not normalized:
        return set()
    
    # Split into terms and filter meaningful ones
    terms = set()
    for term in normalized.split():
        if len(term) >= 3:  # Minimum 3 characters
            terms.add(term)
        # Also include short numeric terms (like invoice numbers)
        elif term.isdigit() and len(term) >= 3:
            terms.add(term)
    
    return terms


def _description_similarity(a: str | None, b: str | None) -> float:
    """
    Enhanced fuzzy similarity (0–1) with multiple strategies:
    1. Sequence similarity (standard)
    2. Key term overlap (Jaccard similarity)
    3. Substring matching for invoice numbers/references
    
    Returns a weighted combination for better matching.
    """
    if not a or not b:
        return 0.0
    
    na = _normalize_text(a)
    nb = _normalize_text(b)
    
    if not na or not nb:
        return 0.0
    
    # Strategy 1: Sequence similarity (40% weight)
    seq_sim = SequenceMatcher(None, na, nb).ratio()
    
    # Strategy 2: Key term overlap using Jaccard similarity (40% weight)
    terms_a = _extract_key_terms(a)
    terms_b = _extract_key_terms(b)
    
    if terms_a and terms_b:
        intersection = terms_a.intersection(terms_b)
        union = terms_a.union(terms_b)
        jaccard_sim = len(intersection) / len(union) if union else 0.0
    else:
        jaccard_sim = 0.0
    
    # Strategy 3: Check for common significant substrings (20% weight)
    # Extract potential invoice numbers, IDs, or reference codes
    substring_sim = 0.0
    if len(na) >= 4 and len(nb) >= 4:
        # Check if any significant substring (4+ chars) appears in both
        for i in range(len(na) - 3):
            substr = na[i:i+4]
            if substr in nb and len(substr.strip()) >= 3:
                substring_sim = max(substring_sim, min(len(substr) / max(len(na), len(nb)), 1.0))
                break
    
    # Weighted combination for better accuracy - adjusted weights for better matching
    # Increased weight on key terms (Jaccard) as it's more reliable for matching
    combined_sim = (seq_sim * 0.35) + (jaccard_sim * 0.45) + (substring_sim * 0.20)
    
    return min(1.0, combined_sim)


def _parse_date_safe(value: str | None) -> datetime | None:
    """
    Try multiple common date formats; return None if parsing fails.
    Supports formats like: YYYY-MM-DD, DD-MM-YYYY, DD-MMM-YYYY, DD/MM/YYYY, etc.
    """
    if not value:
        return None
    
    # Clean the date string
    value = value.strip()
    
    # List of date formats to try (prioritize DD/MM/YYYY for UK/invoices)
    date_formats = [
        "%d/%m/%Y",           # DD/MM/YYYY: 04/05/2024 (UK format - prioritize)
        "%d-%m-%Y",           # DD-MM-YYYY: 15-01-2025
        "%d/%m/%y",           # DD/MM/YY: 04/05/24
        "%d %b %Y",           # DD MMM YYYY: 29 Feb 2024 (Tide format)
        "%d-%b-%Y",           # DD-MMM-YYYY: 15-Jan-2025
        "%d/%b/%Y",           # DD/MMM/YYYY: 15/Jan/2025
        "%Y-%m-%d",           # ISO: 2025-01-15
        "%Y/%m/%d",           # YYYY/MM/DD: 2025/01/15
        "%d-%m-%y",           # DD-MM-YY: 15-01-25
        "%d %B %Y",           # DD Month YYYY: 15 January 2025
        "%d-%B-%Y",           # DD-Month-YYYY: 15-January-2025
        "%d/%B/%Y",           # DD/Month/YYYY: 15/January/2025
        "%Y-%m-%d %H:%M:%S",  # With time
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    
    return None


def _date_distance_days(a: str | None, b: str | None) -> int | None:
    """
    Absolute difference in days between two dates.
    Returns None if either date cannot be parsed.
    """
    da = _parse_date_safe(a)
    db = _parse_date_safe(b)
    if not da or not db:
        return None
    return abs((da - db).days)


def _vendor_name_similarity(vendor1: str | None, vendor2: str | None) -> float:
    """
    Calculate similarity between vendor names.
    Returns 1.0 for exact match, 0.0 for no match.
    """
    if not vendor1 or not vendor2:
        return 0.0
    
    # Normalize vendor names
    def normalize_vendor(name: str) -> str:
        name = name.lower().strip()
        # Remove common suffixes
        name = re.sub(r'\s+(pvt|ltd|limited|inc|incorporated|llc)\.?$', '', name)
        # Remove special characters
        name = re.sub(r'[^a-z0-9\s]', '', name)
        return name.strip()
    
    norm1 = normalize_vendor(vendor1)
    norm2 = normalize_vendor(vendor2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # Exact match
    if norm1 == norm2:
        return 1.0
    
    # Check if one contains the other (e.g., "ABC Pvt Ltd" vs "ABC")
    if norm1 in norm2 or norm2 in norm1:
        return 0.9
    
    # Check for significant word overlap (e.g., "ABC Company" vs "ABC Ltd")
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if len(words1) > 0 and len(words2) > 0:
        common_words = words1.intersection(words2)
        # If more than 50% words match, it's likely the same vendor
        if len(common_words) >= min(len(words1), len(words2)) * 0.5:
            return 0.85
    
    # Fuzzy match
    return SequenceMatcher(None, norm1, norm2).ratio()


def _invoice_number_match(inv_num1: str | None, inv_num2: str | None) -> float:
    """
    Check if invoice numbers match.
    Returns 1.0 for exact match, 0.0 otherwise.
    """
    if not inv_num1 or not inv_num2:
        return 0.0
    
    # Normalize invoice numbers (uppercase, remove spaces/dashes)
    norm1 = re.sub(r'[\s\-]', '', inv_num1.upper())
    norm2 = re.sub(r'[\s\-]', '', inv_num2.upper())
    
    if norm1 == norm2:
        return 1.0
    
    # Check if one contains the other
    if norm1 in norm2 or norm2 in norm1:
        return 0.9
    
    # Check for partial match (e.g., "INV-123" vs "INV123" or "INV-00123")
    # Remove all non-alphanumeric and compare
    norm1_clean = re.sub(r'[^A-Z0-9]', '', norm1)
    norm2_clean = re.sub(r'[^A-Z0-9]', '', norm2)
    if norm1_clean == norm2_clean:
        return 0.95  # Same invoice number, different formatting
    
    # Check if one contains the other after cleaning
    if norm1_clean in norm2_clean or norm2_clean in norm1_clean:
        return 0.85  # Partial match
    
    return 0.0


def _compute_match_features(inv: Transaction, bank: Transaction, primary_currency: str = None) -> Dict[str, float | int | None]:
    """
    Enhanced feature vector with vendor name and invoice number matching.
    This is what you would feed into an ML model later if you train one.
    
    Enhanced with currency conversion support for mixed currency scenarios.
    
    Args:
        inv: Invoice transaction
        bank: Bank transaction
        primary_currency: Primary currency for reconciliation (used for conversion)
    """
    # Handle currency conversion if currencies differ and conversion is enabled
    inv_amount = inv.amount
    bank_amount = bank.amount
    
    if ENABLE_CURRENCY_CONVERSION and primary_currency:
        # Convert both amounts to primary currency for comparison
        if inv.currency and inv.currency != primary_currency:
            inv_amount = convert_currency(inv.amount, inv.currency, primary_currency)
        if bank.currency and bank.currency != primary_currency:
            bank_amount = convert_currency(bank.amount, bank.currency, primary_currency)
    
    # Amount difference (absolute) - using converted amounts if applicable
    amount_diff = abs(inv_amount - bank_amount)
    desc_sim = _description_similarity(inv.description, bank.description)
    date_diff_days = _date_distance_days(inv.date, bank.date)
    
    # Vendor name matching
    vendor_sim = _vendor_name_similarity(inv.vendor_name, bank.vendor_name)
    
    # Invoice number matching
    inv_num_match = _invoice_number_match(inv.invoice_number, bank.invoice_number)

    ref_match = 0.0
    if inv.reference_id and bank.reference_id:
        ref_match = 1.0 if _invoice_number_match(inv.reference_id, bank.reference_id) > 0.5 else 0.0
    
    # Additional features for better matching (using converted amounts)
    amount_match_exact = 1.0 if amount_diff < 0.01 else 0.0
    amount_match_close = 1.0 if amount_diff < abs(inv_amount) * 0.01 else 0.0  # Within 1%
    amount_ratio = min(abs(inv_amount), abs(bank_amount)) / max(abs(inv_amount), abs(bank_amount)) if max(abs(inv_amount), abs(bank_amount)) > 0 else 0.0

    return {
        "amount_diff": amount_diff,
        "description_similarity": desc_sim,
        "date_diff_days": date_diff_days,
        "amount_match_exact": amount_match_exact,
        "amount_match_close": amount_match_close,
        "amount_ratio": amount_ratio,
        "vendor_similarity": vendor_sim,
        "invoice_number_match": inv_num_match,
        "reference_id_match": ref_match,
    }


def _rule_based_match_score(features: Dict[str, float | int | None]) -> float:
    """
    Highly optimized scoring function targeting 90%+ accuracy.
    - Uses vendor name and invoice number matching (CRITICAL for accuracy)
    - Multi-factor analysis with weighted components
    - Emphasizes exact matches and strong partial matches
    """
    amount_diff = float(features["amount_diff"] or 0.0)
    desc_sim = float(features["description_similarity"] or 0.0)
    date_diff_days = features["date_diff_days"]
    amount_match_exact = float(features.get("amount_match_exact", 0.0) or 0.0)
    amount_match_close = float(features.get("amount_match_close", 0.0) or 0.0)
    amount_ratio = float(features.get("amount_ratio", 0.0) or 0.0)
    vendor_sim = float(features.get("vendor_similarity", 0.0) or 0.0)
    inv_num_match = float(features.get("invoice_number_match", 0.0) or 0.0)
    ref_match = float(features.get("reference_id_match", 0.0) or 0.0)

    score = 0.0

    # Component 1: Invoice Number Match (HIGHEST PRIORITY - 25% weight)
    # If invoice numbers match, it's almost certainly a match
    if inv_num_match > 0.5:
        score += 0.25  # Strong signal
        # If invoice number matches, lower threshold for other factors
        if amount_match_exact > 0.5:
            score += 0.20  # Invoice number + exact amount = very strong match
        elif amount_match_close > 0.5:
            score += 0.15  # Invoice number + close amount = strong match

    # Component 2: Vendor Name Match (20% weight) - Very important
    if vendor_sim >= 0.9:
        score += 0.20  # Excellent vendor match
    elif vendor_sim >= 0.7:
        score += 0.15  # Good vendor match
    elif vendor_sim >= 0.5:
        score += 0.10  # Fair vendor match
    elif vendor_sim > 0.0:
        score += vendor_sim * 0.15  # Proportional

    # Component 3: Amount matching (25% of total weight) - Most important
    if amount_match_exact > 0.5:
        score += 0.25  # Exact amount match - critical
    elif amount_match_close > 0.5:
        score += 0.20  # Very close amount (<1% difference)
    elif amount_diff < 1.0:
        score += 0.18  # Within ₹1
    elif amount_diff < 5.0:
        score += 0.15  # Within ₹5
    elif amount_diff < 10.0:
        score += 0.12  # Within ₹10
    elif amount_ratio > 0.98:  # 98%+ ratio match
        score += 0.20
    elif amount_ratio > 0.95:  # 95%+ ratio match
        score += 0.15
    elif amount_ratio > 0.90:  # 90%+ ratio match
        score += 0.12

    # Component 4: Description similarity (15% of total weight)
    if desc_sim >= 0.9:
        score += 0.15  # Excellent match
    elif desc_sim >= 0.8:
        score += 0.12  # Very good match
    elif desc_sim >= 0.7:
        score += 0.10  # Good match
    elif desc_sim >= 0.6:
        score += 0.08  # Fair match
    elif desc_sim >= 0.5:
        score += 0.06  # Moderate match
    elif desc_sim >= 0.4:
        score += 0.04  # Weak match
    else:
        score += desc_sim * 0.10  # Proportional for lower similarities

    # Component 5: Date matching (15% of total weight) - More lenient for better matching
    if date_diff_days is not None:
        if date_diff_days == 0:
            score += 0.15  # Same day - perfect
        elif date_diff_days <= 1:
            score += 0.13  # ±1 day
        elif date_diff_days <= 3:
            score += 0.11  # ±3 days (increased from 0.10)
        elif date_diff_days <= 7:
            score += 0.09  # Within a week (increased from 0.08)
        elif date_diff_days <= 15:
            score += 0.07  # Within 2 weeks (increased from 0.05)
        elif date_diff_days <= 30:
            score += 0.05  # Within a month (increased from 0.03)
        elif date_diff_days <= 60:
            score += 0.03  # Within 2 months (new - more lenient)
    else:
        # No date info available - don't penalize if other factors are strong
        if inv_num_match > 0.5 or vendor_sim > 0.7:
            score += 0.10  # Strong invoice number or vendor match (increased from 0.08)
        elif amount_match_exact > 0.5 and desc_sim > 0.7:
            score += 0.08  # Strong amount + description (increased from 0.06)

    # Bonus: Perfect combination bonuses
    if ref_match > 0.5:
        score += 0.18

    if inv_num_match > 0.5 and amount_match_exact > 0.5:
        score += 0.15  # Invoice number + exact amount = perfect match
    elif inv_num_match > 0.5 and vendor_sim > 0.7:
        score += 0.12  # Invoice number + vendor match
    elif vendor_sim > 0.8 and amount_match_exact > 0.5:
        score += 0.10  # Vendor + exact amount
    elif amount_match_exact > 0.5 and desc_sim > 0.85:
        score += 0.08  # Perfect amount + excellent description
    elif amount_match_exact > 0.5 and desc_sim > 0.70:
        score += 0.06  # Perfect amount + good description

    # Clamp between 0 and 1
    return max(0.0, min(1.0, score))


def _ml_match_score(features: Dict[str, float | int | None]) -> float | None:
    """
    If a trained ML model (model.pkl) is available, use it to compute
    a probability score (0–1). Otherwise, return None.
    
    Enhanced with:
    - Better error handling and logging
    - Model validation before prediction
    - Automatic feature count detection
    - Detailed error tracking
    """
    if MODEL is None:
        return None

    try:
        # Validate model is still usable
        if not hasattr(MODEL, 'predict_proba'):
            print(f"⚠ ML model missing predict_proba method - using rule-based scoring")
            return None
        
        # Use all available features for ML model
        # Try to use enhanced features if available, fallback to basic features
        amount_diff = float(features["amount_diff"] or 0.0)
        desc_sim = float(features["description_similarity"] or 0.0)
        date_diff_days = float(features["date_diff_days"] or 0.0)
        amount_match_exact = float(features.get("amount_match_exact", 0.0) or 0.0)
        amount_match_close = float(features.get("amount_match_close", 0.0) or 0.0)
        amount_ratio = float(features.get("amount_ratio", 0.0) or 0.0)
        vendor_sim = float(features.get("vendor_similarity", 0.0) or 0.0)
        inv_num_match = float(features.get("invoice_number_match", 0.0) or 0.0)
        ref_match = float(features.get("reference_id_match", 0.0) or 0.0)
        
        # Determine which feature set to use based on model's expected features
        # Priority: Use MODEL_FEATURE_COUNT if known, otherwise try 8 features first
        proba_array = None
        error_8_features = None
        error_3_features = None
        
        # Try with 9 features first (newer model)
        if MODEL_FEATURE_COUNT is None or MODEL_FEATURE_COUNT == 9:
            try:
                X = [[
                    amount_diff,
                    desc_sim,
                    date_diff_days,
                    amount_match_exact,
                    amount_match_close,
                    amount_ratio,
                    vendor_sim,
                    inv_num_match,
                    ref_match,
                ]]
                proba_array = MODEL.predict_proba(X)[0]
            except (ValueError, IndexError, AttributeError) as e:
                error_8_features = str(e)
                # Will try 8 features next

        # Fallback to 8 features (older enhanced model)
        if proba_array is None:
            try:
                X = [[
                    amount_diff,
                    desc_sim,
                    date_diff_days,
                    amount_match_exact,
                    amount_match_close,
                    amount_ratio,
                    vendor_sim,
                    inv_num_match,
                ]]
                proba_array = MODEL.predict_proba(X)[0]
            except (ValueError, IndexError, AttributeError) as e:
                error_8_features = str(e)
                # Will try 3 features next
        
        # Fallback to 3 basic features (very old model)
        if proba_array is None:
            try:
                X = [[amount_diff, desc_sim, date_diff_days]]
                proba_array = MODEL.predict_proba(X)[0]
            except (ValueError, IndexError, AttributeError) as e:
                error_3_features = str(e)
                # Both attempts failed - log detailed error
                print(f"⚠ ML model prediction failed with both feature sets:")
                if MODEL_FEATURE_COUNT == 9:
                    print("  Tried 9, 8, then 3 features")
                else:
                    print("  Tried 8, then 3 features")
                if error_8_features:
                    print(f"  8-feature error: {error_8_features}")
                if error_3_features:
                    print(f"  3-feature error: {error_3_features}")
                return None
        
        # Handle different array shapes:
        # - Binary classifier: [prob_class_0, prob_class_1] -> use [1]
        # - Single class: [prob_class_0] -> use [0] or return None
        if len(proba_array) >= 2:
            # Binary classification: return probability of class 1 (match)
            score = float(proba_array[1])
            # Validate score is in expected range
            if not (0.0 <= score <= 1.0):
                print(f"⚠ ML model returned invalid score {score} (expected 0-1), using rule-based")
                return None
            return score
        elif len(proba_array) == 1:
            # Single class model - this shouldn't happen but handle it gracefully
            score = float(proba_array[0])
            if not (0.0 <= score <= 1.0):
                print(f"⚠ ML model returned invalid score {score} (expected 0-1), using rule-based")
                return None
            return score
        else:
            # Empty array or unexpected shape
            print(f"⚠ ML model returned empty/invalid probability array, using rule-based")
            return None
    except Exception as e:
        # Log the error for debugging, then fall back to rule-based score
        error_traceback = traceback.format_exc()
        print(f"⚠ ML model prediction error: {e}")
        if app.debug:
            print(f"  Traceback: {error_traceback}")
        return None


def estimate_time_from_file_sizes(
    invoice_file_sizes: List[int], bank_file_size: int,
    invoice_file_types: List[str], bank_file_type: str
) -> Dict[str, Any]:
    """
    Estimate processing time based on FILE SIZES (before parsing).
    This gives users an early estimate before processing starts.
    
    Returns:
        {
            "estimated_parsing_time": float (seconds),
            "estimated_transactions": {"invoice": int, "bank": int},
            "estimated_reconciliation_time": float (seconds),
            "total_estimated_time": float (seconds),
            "formatted_time": str
        }
    """
    # Empirical data: transactions per MB by file type
    # PDF: ~50-100 transactions per MB (varies by density)
    # Excel: ~500-1000 transactions per MB (more structured)
    # CSV: ~1000-2000 transactions per MB (very dense)
    # Images: ~10-30 transactions per MB (OCR dependent)
    
    total_invoice_size_mb = sum(invoice_file_sizes) / (1024 * 1024)
    bank_size_mb = bank_file_size / (1024 * 1024)
    
    # Estimate transactions based on file type
    invoice_tx_estimates = []
    for i, (size_mb, file_type) in enumerate(zip([s / (1024 * 1024) for s in invoice_file_sizes], invoice_file_types)):
        if file_type in ['.xlsx', '.xls']:
            # Excel: very dense, ~800 transactions per MB
            tx_estimate = int(size_mb * 800)
        elif file_type == '.csv':
            # CSV: very dense, ~1500 transactions per MB
            tx_estimate = int(size_mb * 1500)
        elif file_type == '.pdf':
            # PDF: moderate density, ~80 transactions per MB
            tx_estimate = int(size_mb * 80)
        else:
            # Images: low density, ~20 transactions per MB (OCR)
            tx_estimate = int(size_mb * 20)
        invoice_tx_estimates.append(tx_estimate)
    
    total_invoice_tx_estimate = sum(invoice_tx_estimates)
    
    # Estimate bank transactions
    if bank_file_type in ['.xlsx', '.xls']:
        bank_tx_estimate = int(bank_size_mb * 800)
    elif bank_file_type == '.csv':
        bank_tx_estimate = int(bank_size_mb * 1500)
    elif bank_file_type == '.pdf':
        bank_tx_estimate = int(bank_size_mb * 80)
    else:
        bank_tx_estimate = int(bank_size_mb * 20)
    
    # Estimate parsing time (seconds)
    # PDF: ~0.5 seconds per MB
    # Excel: ~0.2 seconds per MB
    # CSV: ~0.1 seconds per MB
    # Images: ~5 seconds per MB (OCR is slow)
    
    invoice_parsing_time = 0
    for size_mb, file_type in zip([s / (1024 * 1024) for s in invoice_file_sizes], invoice_file_types):
        if file_type in ['.xlsx', '.xls']:
            invoice_parsing_time += size_mb * 0.2
        elif file_type == '.csv':
            invoice_parsing_time += size_mb * 0.1
        elif file_type == '.pdf':
            invoice_parsing_time += size_mb * 0.5
        else:
            invoice_parsing_time += size_mb * 5.0
    
    if bank_file_type in ['.xlsx', '.xls']:
        bank_parsing_time = bank_size_mb * 0.2
    elif bank_file_type == '.csv':
        bank_parsing_time = bank_size_mb * 0.1
    elif bank_file_type == '.pdf':
        bank_parsing_time = bank_size_mb * 0.5
    else:
        bank_parsing_time = bank_size_mb * 5.0
    
    total_parsing_time = invoice_parsing_time + bank_parsing_time
    
    # Estimate reconciliation time based on estimated transaction counts
    estimated_recon_time = estimate_reconciliation_time(
        total_invoice_tx_estimate, bank_tx_estimate
    )
    
    # Total estimated time
    total_estimated_time = total_parsing_time + estimated_recon_time
    
    # Format time
    if total_estimated_time < 60:
        formatted_time = f"{total_estimated_time:.1f} seconds"
    else:
        minutes = int(total_estimated_time // 60)
        seconds = int(total_estimated_time % 60)
        formatted_time = f"{minutes} minute{'s' if minutes != 1 else ''} {seconds} second{'s' if seconds != 1 else ''}"
    
    return {
        "estimated_parsing_time": round(total_parsing_time, 2),
        "estimated_transactions": {
            "invoice": total_invoice_tx_estimate,
            "bank": bank_tx_estimate
        },
        "estimated_reconciliation_time": round(estimated_recon_time, 2),
        "total_estimated_time": round(total_estimated_time, 2),
        "total_estimated_time_formatted": formatted_time
    }


def estimate_reconciliation_time(
    invoice_txs_count: int, bank_txs_count: int
) -> float:
    """
    Estimate reconciliation time in seconds based on transaction counts.
    Uses empirical data: ~0.001 seconds per transaction pair comparison.
    For large datasets, adds overhead for sorting and matching.
    
    This is called AFTER parsing files, so we have accurate transaction counts.
    """
    # Base time for setup and initialization
    base_time = 0.5
    
    # Time per transaction pair comparison
    # For N invoices and M bank transactions, we do N*M comparisons
    total_comparisons = invoice_txs_count * bank_txs_count
    
    # Average time per comparison (empirical: ~0.0003 to 0.001 seconds)
    # This includes feature computation, similarity calculation, etc.
    time_per_comparison = 0.0006
    
    # Estimated time for comparisons
    comparison_time = total_comparisons * time_per_comparison
    
    # Additional overhead for sorting candidates (O(N*M log(N*M)))
    if total_comparisons > 0:
        sorting_overhead = (invoice_txs_count + bank_txs_count) * 0.0002
        # For very large datasets, add logarithmic overhead
        if total_comparisons > 10000:
            sorting_overhead += (total_comparisons / 10000) * 0.5
    else:
        sorting_overhead = 0
    
    # Total estimated time
    estimated_time = base_time + comparison_time + sorting_overhead
    
    # Add buffer for large datasets (25% extra for safety margin)
    if estimated_time > 10:
        estimated_time *= 1.25
    elif estimated_time > 60:
        # For very large datasets, add more buffer
        estimated_time *= 1.3
    
    # Minimum time is 1 second
    estimated_time = max(1.0, estimated_time)
    
    return estimated_time


def reconcile_transactions(
    invoice_txs: List[Transaction], bank_txs: List[Transaction], primary_currency: str = '₹'
) -> ReconciliationResult:
    """
    OPTIMIZED reconciliation for large datasets (1000+ transactions):
    - Uses amount-based indexing for fast filtering (O(1) lookup)
    - Early exit strategies to skip unnecessary comparisons
    - Progress logging for large datasets
    - Batch processing with progress updates
    - Optimized for 2-minute completion even with 10000+ transactions
    - Uses detected currency for display
    """
    matches: List[Dict[str, Any]] = []
    only_in_invoices: List[Dict[str, Any]] = []
    only_in_bank: List[Dict[str, Any]] = []

    total_invoices = len(invoice_txs)
    total_bank = len(bank_txs)
    total_comparisons = total_invoices * total_bank
    
    print(f"\n{'='*60}")
    print(f"Starting OPTIMIZED Reconciliation")
    print(f"{'='*60}")
    print(f"Invoice transactions: {total_invoices}")
    print(f"Bank transactions: {total_bank}")
    print(f"Total possible comparisons: {total_comparisons:,}")
    print(f"Currency: {primary_currency}")
    print(f"{'='*60}\n")

    # Separate thresholds for ML‑based vs rule‑based scores.
    ML_THRESHOLD = 0.40
    RULE_THRESHOLD = 0.35

    # OPTIMIZATION 1: Pre-index bank transactions by exact amount (2 decimals) for fast lookup
    # We use absolute amounts to allow matching credit/debit sign differences.
    bank_by_amount: Dict[int, List[int]] = {}  # amount_cents -> list of bank indices
    for bank_idx, bank in enumerate(bank_txs):
        try:
            amount_cents = int(round(abs(float(bank.amount)) * 100))
        except Exception:
            continue
        if amount_cents not in bank_by_amount:
            bank_by_amount[amount_cents] = []
        bank_by_amount[amount_cents].append(bank_idx)
    
    print(f"✓ Indexed {total_bank} bank transactions by amount ranges")
    print(f"  Created {len(bank_by_amount)} amount buckets\n")

    # OPTIMIZATION 2: Collect candidates with progress tracking
    all_candidates: List[tuple[int, int, float]] = []  # (invoice_idx, bank_idx, score)
    
    # Progress tracking
    progress_interval = max(1, total_invoices // 20)  # Update every 5%
    comparisons_done = 0
    candidates_found = 0
    start_time = time.time()
    
    print("Processing invoice transactions...")
    for inv_idx, inv in enumerate(invoice_txs):
        # Progress update
        if inv_idx % progress_interval == 0 or inv_idx == total_invoices - 1:
            elapsed = time.time() - start_time
            progress = (inv_idx + 1) / total_invoices * 100 if total_invoices > 0 else 0.0
            rate = comparisons_done / elapsed if elapsed > 0 else 0
            remaining = (total_invoices - inv_idx - 1) * total_bank / rate if rate > 0 else 0
            print(f"  Progress: {progress:.1f}% ({inv_idx + 1}/{total_invoices} invoices) | "
                  f"Comparisons: {comparisons_done:,} | "
                  f"Candidates: {candidates_found} | "
                  f"Time: {elapsed:.1f}s | "
                  f"Est. remaining: {remaining:.1f}s")
        
        # Exact-amount matching: only compare candidates with the same 2-decimal amount
        try:
            inv_amount_cents = int(round(abs(float(inv.amount)) * 100))
        except Exception:
            continue

        candidate_bank_indices = set(bank_by_amount.get(inv_amount_cents, []))
        
        # If no candidates in amount range, skip this invoice (will be unmatched)
        if not candidate_bank_indices:
            continue
        
        # OPTIMIZATION 4: Process only relevant bank transactions
        for bank_idx in candidate_bank_indices:
            bank = bank_txs[bank_idx]
            comparisons_done += 1
            
            # Quick exact amount check (2 decimals, using absolute values)
            try:
                if int(round(abs(float(inv.amount)) * 100)) != int(round(abs(float(bank.amount)) * 100)):
                    continue
            except Exception:
                continue

            # Amount-only exact match: treat as a valid candidate regardless of vendor/date similarity.
            # This ensures same-amount invoice+bank rows can reconcile even when descriptions differ.
            all_candidates.append((inv_idx, bank_idx, 1.0))
            candidates_found += 1
            continue
            
            # Compute features only for amount-matched pairs (with currency conversion support)
            features = _compute_match_features(inv, bank, primary_currency)

            # Prefer ML model if loaded, else rule-based score
            ml_score = _ml_match_score(features)
            if ml_score is not None:
                score = ml_score
                threshold = ML_THRESHOLD
            else:
                score = _rule_based_match_score(features)
                threshold = RULE_THRESHOLD

            # Store candidate if above threshold
            if score >= threshold:
                all_candidates.append((inv_idx, bank_idx, score))
                candidates_found += 1
                
                # Log high-quality matches immediately (use detected currency)
                if score >= 0.8:
                    print(f"  ✓ High-quality match found: Invoice #{inv_idx+1} ↔ Bank #{bank_idx+1} "
                          f"(Score: {score:.2f}, Amount: {primary_currency}{inv.amount:.2f})")
    
    elapsed = time.time() - start_time
    print(f"\n✓ Candidate collection completed in {elapsed:.2f} seconds")
    print(f"  Total comparisons made: {comparisons_done:,} (reduced from {total_comparisons:,})")
    if total_comparisons > 0:
        print(f"  Reduction: {((1 - comparisons_done/total_comparisons) * 100):.1f}%")
    else:
        print(f"  Reduction: N/A (no comparisons needed)")
    print(f"  Candidates found: {candidates_found}\n")
    
    # STEP 2: Sort candidates by score (highest first)
    print("Sorting candidates by match score...")
    sort_start = time.time()
    all_candidates.sort(key=lambda x: x[2], reverse=True)
    sort_time = time.time() - sort_start
    print(f"✓ Sorted {len(all_candidates)} candidates in {sort_time:.2f} seconds\n")
    
    # STEP 3: Greedy assignment with progress tracking
    print("Assigning matches (greedy algorithm)...")
    assign_start = time.time()
    used_bank_indices: set[int] = set()
    matched_invoice_indices: set[int] = set()
    matches_assigned = 0
    
    for idx, (inv_idx, bank_idx, score) in enumerate(all_candidates):
        # Skip if either invoice or bank already matched
        if inv_idx in matched_invoice_indices or bank_idx in used_bank_indices:
            continue
        
        # This is a good match - assign it
        inv = invoice_txs[inv_idx]
        bank = bank_txs[bank_idx]

        # Ensure reference_id is present in output for invoices
        if not inv.reference_id:
            if inv.invoice_number:
                inv.reference_id = inv.invoice_number
            elif inv.description:
                inv.reference_id = inv.description[:255]

        invoice_ref = inv.invoice_number or inv.reference_id

        matches.append(
            {
                "reference": invoice_ref,
                "invoice": asdict(inv),
                "bank": asdict(bank),
                "match_score": score,
            }
        )
        used_bank_indices.add(bank_idx)
        matched_invoice_indices.add(inv_idx)
        matches_assigned += 1
        
        # Log every 10th match or high-score matches (with currency)
        if matches_assigned % 10 == 0 or score >= 0.85:
            print(f"  ✓ Match #{matches_assigned}: Invoice #{inv_idx+1} ↔ Bank #{bank_idx+1} "
                  f"(Score: {score:.2f}, Amount: {primary_currency}{inv.amount:.2f})")
    
    assign_time = time.time() - assign_start
    print(f"✓ Assigned {matches_assigned} matches in {assign_time:.2f} seconds\n")
    
    # STEP 4: Find unmatched invoices
    print("Identifying unmatched transactions...")
    for inv_idx, inv in enumerate(invoice_txs):
        if inv_idx not in matched_invoice_indices:
            only_in_invoices.append(asdict(inv))

    # STEP 5: Find unmatched bank transactions
    for bank_idx, bank in enumerate(bank_txs):
        if bank_idx not in used_bank_indices:
            only_in_bank.append(asdict(bank))
    
    total_time = time.time() - start_time
    print(f"{'='*60}")
    print(f"Reconciliation COMPLETED in {total_time:.2f} seconds")
    print(f"{'='*60}")
    print(f"Currency used: {primary_currency}")
    print(f"✓ Matches found: {len(matches)}")
    print(f"✓ Unmatched invoices: {len(only_in_invoices)}")
    print(f"✓ Unmatched bank transactions: {len(only_in_bank)}")
    invoice_match_rate = (len(matches)/total_invoices*100) if total_invoices > 0 else 0.0
    bank_match_rate = (len(matches)/total_bank*100) if total_bank > 0 else 0.0
    print(f"✓ Match rate: {invoice_match_rate:.1f}% (invoices)")
    print(f"✓ Match rate: {bank_match_rate:.1f}% (bank)")
    print(f"{'='*60}\n")

    return ReconciliationResult(
        matches=matches,
        only_in_invoices=only_in_invoices,
        only_in_bank=only_in_bank,
    )


# === API endpoints ===


@app.route("/api/reconcile", methods=["POST"])
@limiter.limit(RATE_LIMITS.get("/api/reconcile", "10 per minute"))
def api_reconcile():
    """
    Accept files with flexible combinations:
    - Multiple invoices + One bank statement
    - One invoice + Multiple bank statements  
    - Multiple invoices + Multiple bank statements
    - One invoice + One bank statement
    
    Supports: PDF, Excel, CSV, Images
    Auto-detects currency from files
    
    Optional query parameter:
    - progress_id: If provided, progress will be tracked and can be queried via /api/progress/<progress_id>
    """
    start_time = time.time()
    request_id = f"req_{int(time.time() * 1000)}"
    progress_id = request.args.get("progress_id", request_id)
    
    try:
        # Initialize progress tracking
        set_progress(progress_id, "processing", 0.0, "Starting reconciliation...")
        
        logger.info(
            "Reconciliation request received",
            context={
                "request_id": request_id,
                "progress_id": progress_id,
                "invoice_files_count": len(request.files.getlist("invoice")),
                "bank_files_count": len(request.files.getlist("bank")),
                "client_ip": get_remote_address()
            }
        )
        invoice_files = request.files.getlist("invoice")
        bank_files = request.files.getlist("bank")  # Support multiple bank files

        if not invoice_files or not bank_files:
            return (
                jsonify({"error": "Please upload at least one 'invoice' and one 'bank' file."}),
                400,
            )

        # Basic input validation: maximum number of files
        if len(invoice_files) > MAX_INVOICE_FILES:
            return (
                jsonify(
                    {
                        "error": f"Too many invoice files uploaded. "
                        f"Maximum allowed is {MAX_INVOICE_FILES} files per request."
                    }
                ),
                400,
            )

        if len(bank_files) > MAX_INVOICE_FILES:  # Use same limit for bank files
            return (
                jsonify(
                    {
                        "error": f"Too many bank files uploaded. "
                        f"Maximum allowed is {MAX_INVOICE_FILES} files per request."
                    }
                ),
                400,
            )

        # Validate all invoice files (with size checks)
        for invoice_file in invoice_files:
            ok, err_msg = _validate_uploaded_file(
                invoice_file, INVOICE_ALLOWED_EXTENSIONS, INVOICE_ALLOWED_MIMETYPES, check_size=True
            )
            if not ok:
                logger.warning(
                    "Invoice file validation failed",
                    context={"request_id": request_id, "file_name": invoice_file.filename, "error": err_msg}
                )
                return jsonify({"error": f"Invoice file '{invoice_file.filename}': {err_msg}"}), 400

        # Validate all bank files (with size checks)
        for bank_file in bank_files:
            ok, err_msg = _validate_uploaded_file(
                bank_file, BANK_ALLOWED_EXTENSIONS, BANK_ALLOWED_MIMETYPES, check_size=True
            )
            if not ok:
                logger.warning(
                    "Bank file validation failed",
                    context={"request_id": request_id, "file_name": bank_file.filename, "error": err_msg}
                )
                return jsonify({"error": f"Bank file '{bank_file.filename}': {err_msg}"}), 400

        # PRE-PROCESSING: Get file sizes and validate total size (BEFORE parsing)
        invoice_file_sizes = []
        invoice_file_types = []
        for invoice_file in invoice_files:
            invoice_file.seek(0, 2)  # Seek to end
            file_size = invoice_file.tell()
            invoice_file.seek(0)  # Reset to beginning
            invoice_file_sizes.append(file_size)
            invoice_name = invoice_file.filename or "invoice"
            _, ext = os.path.splitext(invoice_name.lower())
            invoice_file_types.append(ext)
        
        bank_file_sizes = []
        bank_file_types = []
        total_bank_size = 0
        for bank_file in bank_files:
            bank_file.seek(0, 2)  # Seek to end
            file_size = bank_file.tell()
            bank_file.seek(0)  # Reset to beginning
            bank_file_sizes.append(file_size)
            total_bank_size += file_size
            bank_name = bank_file.filename or "bank"
            _, bank_ext = os.path.splitext(bank_name.lower())
            bank_file_types.append(bank_ext)
        
        # Validate total file size (memory protection)
        all_file_sizes = invoice_file_sizes + bank_file_sizes
        ok, err_msg = _validate_total_file_size(all_file_sizes)
        if not ok:
            logger.warning(
                "Total file size validation failed",
                context={
                    "request_id": request_id,
                    "total_size_mb": sum(all_file_sizes) / (1024 * 1024),
                    "max_size_mb": MAX_TOTAL_SIZE_MB
                }
            )
            return jsonify({"error": err_msg}), 400
        
        # Estimate memory usage and warn if high
        all_file_types = invoice_file_types + bank_file_types
        estimated_memory_mb = _estimate_memory_usage(all_file_sizes, all_file_types)
        if estimated_memory_mb > MAX_MEMORY_USAGE_MB:
            logger.warning(
                "High memory usage estimated",
                context={
                    "request_id": request_id,
                    "estimated_memory_mb": round(estimated_memory_mb, 2),
                    "max_memory_mb": MAX_MEMORY_USAGE_MB
                }
            )
            return jsonify({
                "error": f"Estimated memory usage ({estimated_memory_mb:.2f} MB) exceeds "
                        f"maximum allowed ({MAX_MEMORY_USAGE_MB} MB). Please reduce file sizes."
            }), 400
        elif estimated_memory_mb > MAX_MEMORY_USAGE_MB * 0.8:  # Warn at 80% of limit
            logger.info(
                "High memory usage estimated (warning threshold)",
                context={
                    "request_id": request_id,
                    "estimated_memory_mb": round(estimated_memory_mb, 2),
                    "max_memory_mb": MAX_MEMORY_USAGE_MB
                }
            )
        
        # Calculate pre-processing estimate (use average bank file type for estimation)
        avg_bank_ext = bank_file_types[0] if bank_file_types else '.pdf'
        pre_estimate = estimate_time_from_file_sizes(
            invoice_file_sizes, total_bank_size,
            invoice_file_types, avg_bank_ext
        )
        
        print(f"\n{'='*60}")
        print(f"PRE-PROCESSING TIME ESTIMATE (Based on File Sizes)")
        print(f"{'='*60}")
        print(f"Invoice files: {len(invoice_files)} file(s), Total size: {sum(invoice_file_sizes)/(1024*1024):.2f} MB")
        print(f"Bank files: {len(bank_files)} file(s), Total size: {total_bank_size/(1024*1024):.2f} MB")
        print(f"Estimated transactions: {pre_estimate['estimated_transactions']['invoice']} invoices, {pre_estimate['estimated_transactions']['bank']} bank")
        print(f"Estimated parsing time: {pre_estimate['estimated_parsing_time']:.2f} seconds")
        print(f"Estimated reconciliation time: {pre_estimate['estimated_reconciliation_time']:.2f} seconds")
        print(f"TOTAL ESTIMATED TIME: {pre_estimate['total_estimated_time_formatted']}")
        print(f"{'='*60}\n")

        # --- Invoices: allow multiple files ---
        all_invoice_txs: List[Transaction] = []
        all_invoice_lines: List[str] = []
        all_invoice_file_names: List[str] = []
        invoice_files_data: List[Dict[str, Any]] = []  # Store file data for saving
        invoice_extractions_data: Dict[str, List[Dict[str, Any]]] = {}  # base_file_name -> list of extracted invoice json

        # Process each invoice file
        for invoice_file in invoice_files:
            try:
                # Reset file pointer to beginning
                invoice_file.seek(0)
                invoice_bytes = invoice_file.read()
                invoice_name = invoice_file.filename or "invoice"
                invoice_name_lower = invoice_name.lower()
                
                # Store file data for later saving (so UI invoice uploads are stored in invoices table)
                if invoice_name_lower.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tif', '.tiff', '.xlsx', '.xls')):
                    invoice_files_data.append({
                        'file_bytes': invoice_bytes,
                        'file_name': invoice_name
                    })

                # Validate each invoice file type
                ok, err_msg = _validate_uploaded_file(
                    invoice_file, INVOICE_ALLOWED_EXTENSIONS, INVOICE_ALLOWED_MIMETYPES
                )
                if not ok:
                    return jsonify({"error": f"Invoice file '{invoice_name}': {err_msg}"}), 400

                if invoice_name_lower.endswith((".xlsx", ".xls")):
                    # Excel file
                    invoice_txs = excel_to_transactions(invoice_bytes, source="invoice")
                    invoice_lines = [f"{tx.date or ''} {tx.description} {tx.amount}" for tx in invoice_txs]
                elif invoice_name_lower.endswith(".pdf"):
                    # Multi-invoice PDFs are common: extract per page and split sections
                    # so a single PDF can yield multiple invoice transactions.
                    pages_lines = pdf_to_pages_lines(invoice_bytes)
                    invoice_txs = []
                    invoice_lines = []
                    base_file_name = invoice_name
                    if base_file_name not in invoice_extractions_data:
                        invoice_extractions_data[base_file_name] = []
                    for page_index, page_lines in enumerate(pages_lines):
                        if not page_lines:
                            continue
                        for section_index, section_lines in enumerate(_split_invoice_sections(page_lines)):
                            if not section_lines:
                                continue
                            txs = parse_transactions_from_lines(section_lines, source="invoice")
                            for tx in txs:
                                tx.file_name = f"{invoice_name}#page={page_index + 1}"
                            invoice_txs.extend(txs)
                            invoice_lines.extend(section_lines)

                            invoice_extractions_data[base_file_name].append(
                                {
                                    "parent_file_name": invoice_name,
                                    "original_filename": invoice_name,
                                    "page_no": page_index + 1,
                                    "section_no": section_index + 1,
                                    "lines": section_lines,
                                    "extracted_fields": getattr(txs[0], "extracted_fields", None) if txs else None,
                                    "transactions": [
                                        {
                                            "source": t.source,
                                            "description": t.description,
                                            "amount": t.amount,
                                            "date": t.date,
                                            "vendor_name": t.vendor_name,
                                            "invoice_number": t.invoice_number,
                                            "currency": t.currency,
                                            "file_name": getattr(t, "file_name", None),
                                            "extracted_fields": getattr(t, "extracted_fields", None),
                                        }
                                        for t in txs
                                    ],
                                }
                            )
                else:
                    # Image file
                    invoice_lines = ocr_image_to_lines(invoice_bytes)
                    invoice_txs = parse_transactions_from_lines(
                        invoice_lines, source="invoice"
                    )

                # Ensure invoice reference_id is always populated
                for tx in invoice_txs:
                    if tx.source == "invoice" and not tx.reference_id:
                        if tx.invoice_number:
                            tx.reference_id = tx.invoice_number
                        elif tx.description:
                            tx.reference_id = tx.description[:255]

                for tx in invoice_txs:
                    if not tx.file_name:
                        tx.file_name = invoice_name

                # Add transactions from this invoice file
                # Note: We keep all transactions even if duplicates exist
                # The matching algorithm will handle them correctly
                all_invoice_txs.extend(invoice_txs)
                all_invoice_lines.extend(invoice_lines)
                all_invoice_file_names.extend([invoice_name] * len(invoice_txs))
                
                # Debug: Print info about processed invoice
                invoice_currencies_in_file = [tx.currency for tx in invoice_txs if tx.currency]
                if invoice_currencies_in_file:
                    from collections import Counter
                    file_currency_counts = Counter(invoice_currencies_in_file)
                    most_common = file_currency_counts.most_common(1)[0]
                    print(f"Processed invoice file: {invoice_name}, Transactions: {len(invoice_txs)}, Currency: {most_common[0]} ({most_common[1]} transactions)")
                else:
                    print(f"Processed invoice file: {invoice_name}, Transactions: {len(invoice_txs)}, Currency: Not detected")
            except Exception as e:
                error_msg = f"Error processing invoice file '{invoice_file.filename or 'unknown'}': {str(e)}"
                print(error_msg)
                return jsonify({"error": error_msg}), 400

        # --- Bank: allow multiple files (CSV, Excel, PDF or image) ---
        all_bank_txs: List[Transaction] = []
        all_bank_lines: List[str] = []
        all_bank_file_names: List[str] = []
        
        # Detect currency from all files (use most common)
        all_currencies: List[str] = []
        
        # Initialize primary_currency with default
        primary_currency = '₹'  # Default currency
        
        # Process each bank file
        for bank_file in bank_files:
            try:
                # Reset file pointer to beginning
                bank_file.seek(0)
                bank_bytes = bank_file.read()
                bank_name = bank_file.filename or "bank"
                bank_name_lower = bank_name.lower()

                if bank_name_lower.endswith((".xlsx", ".xls")):
                    # Excel file
                    bank_txs = excel_to_transactions(bank_bytes, source="bank")
                    bank_lines = [f"{tx.date or ''} {tx.description} {tx.amount}" for tx in bank_txs]
                elif bank_name_lower.endswith(".csv"):
                    bank_txs = csv_to_transactions(bank_bytes, source="bank")
                    bank_lines = [f"{tx.date or ''} {tx.description} {tx.amount}" for tx in bank_txs]
                elif bank_name_lower.endswith(".pdf"):
                    bank_lines = pdf_to_lines(bank_bytes)
                    bank_txs = parse_transactions_from_lines(bank_lines, source="bank")
                else:
                    # Image file
                    bank_lines = ocr_image_to_lines(bank_bytes)
                    bank_txs = parse_transactions_from_lines(bank_lines, source="bank")

                # Attach bank statement owner/company name (header) to each transaction
                bank_owner = _extract_bank_owner_name(bank_lines)
                if bank_owner:
                    for tx in bank_txs:
                        if tx.source == "bank":
                            tx.owner_name = bank_owner

                # Collect currencies from bank transactions
                bank_currencies_in_file = []
                for tx in bank_txs:
                    if tx.currency:
                        all_currencies.append(tx.currency)
                        bank_currencies_in_file.append(tx.currency)
                
                if bank_currencies_in_file:
                    from collections import Counter
                    file_currency_counts = Counter(bank_currencies_in_file)
                    most_common = file_currency_counts.most_common(1)[0]
                    print(f"    Currency in {bank_name}: {most_common[0]} ({most_common[1]} transactions)")
                else:
                    print(f"    No currency detected in {bank_name}")
                
                # Add transactions from this bank file
                all_bank_txs.extend(bank_txs)
                all_bank_lines.extend(bank_lines)
                all_bank_file_names.extend([bank_name] * len(bank_txs))
                
                # Debug: Print info about processed bank file
                print(f"Processed bank file: {bank_name}, Transactions: {len(bank_txs)}")
            except Exception as e:
                error_msg = f"Error processing bank file '{bank_file.filename or 'unknown'}': {str(e)}"
                logger.error(
                    "Error processing bank file",
                    context={
                        "request_id": request_id,
                        "file_name": bank_file.filename,
                        "file_type": bank_file.content_type
                    },
                    error=e
                )
                return jsonify({"error": error_msg}), 400
        
        # Apply deduplication if enabled
        if ENABLE_DEDUPLICATION:
            print(f"\n{'='*60}")
            print(f"TRANSACTION DEDUPLICATION")
            print(f"{'='*60}")
            
            # Deduplicate invoice transactions
            all_invoice_txs, invoice_dedup_stats = deduplicate_transactions(all_invoice_txs)
            print(f"Invoice transactions: {invoice_dedup_stats['original_count']} -> {invoice_dedup_stats['deduplicated_count']} "
                  f"({invoice_dedup_stats['duplicates_removed']} duplicates removed)")
            
            # Deduplicate bank transactions
            all_bank_txs, bank_dedup_stats = deduplicate_transactions(all_bank_txs)
            print(f"Bank transactions: {bank_dedup_stats['original_count']} -> {bank_dedup_stats['deduplicated_count']} "
                  f"({bank_dedup_stats['duplicates_removed']} duplicates removed)")
            print(f"{'='*60}\n")
        
        # Determine primary currency with enhanced mixed currency support
        invoice_currencies = [tx.currency for tx in all_invoice_txs if tx.currency]
        bank_currencies = [tx.currency for tx in all_bank_txs if tx.currency]
        all_currencies.extend(invoice_currencies)
        
        print(f"\nCurrency detection summary:")
        print(f"  Invoice currencies found: {len(invoice_currencies)} transactions")
        print(f"  Bank currencies found: {len(bank_currencies)} transactions")
        
        # Use enhanced currency detection with mixed currency support
        primary_currency, currency_stats = detect_primary_currency_with_mixed_support(
            invoice_currencies, bank_currencies
        )
        
        print(f"  Currency distribution: {currency_stats['distribution']}")
        print(f"  Primary currency: {primary_currency} ({currency_stats['primary_percentage']}% of transactions)")
        
        if currency_stats['mixed']:
            print(f"  ⚠ WARNING: Mixed currencies detected!")
            print(f"  Significant currencies: {', '.join(currency_stats['significant_currencies'])}")
            print(f"  Note: Reconciliation will use {primary_currency} as primary currency")
            if ENABLE_CURRENCY_CONVERSION:
                print(f"  Currency conversion is ENABLED - amounts will be converted for matching")
            else:
                print(f"  ⚠ Currency conversion is DISABLED - only same-currency matches will be found")
        else:
            print(f"  ✓ Single currency detected: {primary_currency}")
        
        print(f"  Final currency for reconciliation: {primary_currency}\n")

        # Store in DB (all transactions in a tabular format)
        store_transactions(
            all_invoice_txs, all_bank_txs, all_invoice_file_names, all_bank_file_names
        )

        # Debug: Print summary before reconciliation
        print(f"\n{'='*60}")
        print(f"FILE PROCESSING SUMMARY")
        print(f"{'='*60}")
        print(f"Total invoice transactions: {len(all_invoice_txs)} from {len(invoice_files)} file(s)")
        print(f"Total bank transactions: {len(all_bank_txs)} from {len(bank_files)} file(s)")
        print(f"Primary currency: {primary_currency}")
        
        # Estimate reconciliation time before starting
        estimated_time = estimate_reconciliation_time(
            len(all_invoice_txs), len(all_bank_txs)
        )
        estimated_time_formatted = f"{estimated_time:.2f} seconds"
        if estimated_time >= 60:
            minutes = int(estimated_time // 60)
            seconds = int(estimated_time % 60)
            estimated_time_formatted = f"{minutes} minute{'s' if minutes != 1 else ''} {seconds} second{'s' if seconds != 1 else ''}"
        
        print(f"Estimated reconciliation time: {estimated_time_formatted}")
        print(f"Starting reconciliation at {time.strftime('%Y-%m-%d %H:%M:%S')}...")
        print(f"{'='*60}\n")

        # Extract dates from transactions for storing in reconciliation record
        # Get the earliest date from invoice transactions (or most common date)
        invoice_file_date = None
        if all_invoice_txs:
            invoice_dates = [tx.date for tx in all_invoice_txs if tx.date]
            if invoice_dates:
                # Use the earliest date, or if multiple dates exist, use the most common one
                # For simplicity, use the earliest date
                parsed_dates = []
                for date_str in invoice_dates:
                    parsed = _parse_date_safe(date_str)
                    if parsed:
                        parsed_dates.append((parsed, date_str))
                if parsed_dates:
                    # Sort by date and get the earliest
                    parsed_dates.sort(key=lambda x: x[0])
                    invoice_file_date = parsed_dates[0][1]
        
        # Get the earliest date from bank transactions
        bank_file_date = None
        if all_bank_txs:
            bank_dates = [tx.date for tx in all_bank_txs if tx.date]
            if bank_dates:
                parsed_dates = []
                for date_str in bank_dates:
                    parsed = _parse_date_safe(date_str)
                    if parsed:
                        parsed_dates.append((parsed, date_str))
                if parsed_dates:
                    # Sort by date and get the earliest
                    parsed_dates.sort(key=lambda x: x[0])
                    bank_file_date = parsed_dates[0][1]

        # Update progress: File processing complete
        set_progress(progress_id, "processing", 0.5, "Files processed, starting reconciliation...")
        
        # Reconcile all invoice transactions against all bank statements
        # This now uses global matching optimized for multiple invoices and multiple bank files
        reconcile_start = time.time()
        result = reconcile_transactions(all_invoice_txs, all_bank_txs, primary_currency)
        reconcile_time = time.time() - reconcile_start
        
        # Update progress: Reconciliation complete
        set_progress(progress_id, "processing", 0.9, "Reconciliation complete, saving results...")
        
        # Log reconciliation completion with structured logging
        logger.info(
            "Reconciliation completed successfully",
            context={
                "request_id": request_id,
                "reconciliation_time_seconds": round(reconcile_time, 2),
                "matches_count": len(result.matches),
                "unmatched_invoices": len(result.only_in_invoices),
                "unmatched_bank": len(result.only_in_bank),
                "total_invoices": len(all_invoice_txs),
                "total_bank": len(all_bank_txs),
                "currency": primary_currency
            }
        )
        
        # Debug: Print reconciliation results
        print(f"Reconciliation completed in {reconcile_time:.2f} seconds")
        print(f"Matches found: {len(result.matches)}")
        print(f"Unmatched invoices: {len(result.only_in_invoices)}")
        print(f"Unmatched bank: {len(result.only_in_bank)}")

        # Get unique bank file names for storage
        unique_bank_files = ", ".join(sorted(set(all_bank_file_names))) if all_bank_file_names else "bank"

        # Store reconciliation summary + matched pairs
        reconciliation_id = store_reconciliation_summary(
            all_invoice_file_names,
            unique_bank_files,
            result,
            total_invoice_rows=len(all_invoice_txs),
            total_bank_rows=len(all_bank_txs),
            invoice_file_date=invoice_file_date,
            bank_file_date=bank_file_date,
            invoice_files_data=invoice_files_data,
            invoice_extractions_data=invoice_extractions_data,
        )

        # Optionally trigger automatic background model retraining
        try:
            maybe_trigger_auto_train(len(result.matches))
        except Exception as e:
            # Never fail the main request because of auto‑train issues
            print(f"Auto‑train: error while scheduling retrain: {e}")

        # Basic accuracy metrics (as percentages)
        match_count = len(result.matches)
        invoice_rows = len(all_invoice_txs)
        bank_rows = len(all_bank_txs)
        accuracy_invoice = (
            match_count / invoice_rows * 100 if invoice_rows > 0 else 0.0
        )
        accuracy_bank = match_count / bank_rows * 100 if bank_rows > 0 else 0.0

        # Calculate processing time
        end_time = time.time()
        processing_time = end_time - start_time
        processing_time_formatted = f"{processing_time:.2f} seconds"
        if processing_time >= 60:
            minutes = int(processing_time // 60)
            seconds = int(processing_time % 60)
            processing_time_formatted = f"{minutes} minute{'s' if minutes != 1 else ''} {seconds} second{'s' if seconds != 1 else ''}"

        print(f"Total processing time: {processing_time_formatted}")
        print(f"Reconciliation completed at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Returning response with {len(result.matches)} matches, {len(result.only_in_invoices)} unmatched invoices, {len(result.only_in_bank)} unmatched bank transactions")

        # Update progress: Complete
        set_progress(
            progress_id,
            "completed",
            1.0,
            "Reconciliation completed successfully",
            {
                "reconciliation_id": reconciliation_id,
                "matches": len(result.matches),
                "processing_time": processing_time
            }
        )

        return jsonify(
            {
                # For multiple invoices/bank files, this is the concatenation of lines
                # from all uploaded files.
                "invoice_lines": all_invoice_lines,
                "bank_lines": all_bank_lines,
                "currency": primary_currency,  # Detected currency
                "counts": {
                    "invoice_rows": len(all_invoice_txs),
                    "bank_rows": len(all_bank_txs),
                },
                "pre_processing_estimate": {
                    "estimated_parsing_time": pre_estimate["estimated_parsing_time"],
                    "estimated_transactions": pre_estimate["estimated_transactions"],
                    "estimated_reconciliation_time": pre_estimate["estimated_reconciliation_time"],
                    "total_estimated_time": pre_estimate["total_estimated_time"],
                    "total_estimated_time_formatted": pre_estimate["total_estimated_time_formatted"],
                },
                "reconciliation": {
                    "reconciliation_id": reconciliation_id,
                    "matches": result.matches,
                    "only_in_invoices": result.only_in_invoices,
                    "only_in_bank": result.only_in_bank,
                    "accuracy": {
                        "invoice_match_percentage": accuracy_invoice,
                        "bank_match_percentage": accuracy_bank,
                    },
                    "estimated_time_seconds": round(estimated_time, 2),
                    "estimated_time_formatted": estimated_time_formatted,
                    "processing_time_seconds": round(processing_time, 2),
                    "processing_time_formatted": processing_time_formatted,
                    "progress_id": progress_id,  # Return progress_id for tracking
                },
            }
        )
    except UserInputError as e:
        # Validation / size / format errors that user can fix
        set_progress(progress_id, "error", 0.0, f"Validation error: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # Make sure frontend always gets JSON, even on server errors
        error_traceback = traceback.format_exc()
        
        # Log error with structured logging
        logger.error(
            "Error in reconciliation endpoint",
            context={
                "request_id": request_id if 'request_id' in locals() else None,
                "endpoint": "/api/reconcile",
                "processing_time": round(time.time() - start_time, 2) if 'start_time' in locals() else None
            },
            error=e
        )
        
        print(f"Error in /api/reconcile: {e}")
        if app.debug:
            print(error_traceback)
        
        # Update progress: Error
        set_progress(progress_id, "error", 0.0, f"Error: {str(e)}")
        
        # Calculate processing time even on error
        end_time = time.time()
        processing_time = end_time - start_time
        return (
            jsonify(
                {
                    "error": "Internal server error while processing files.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                    "processing_time_seconds": round(processing_time, 2),
                    "progress_id": progress_id,
                }
            ),
            500,
        )


@app.route("/api/reconciliations", methods=["GET"])
@limiter.limit(RATE_LIMITS.get("/api/reconciliations", "30 per minute"))
def api_list_reconciliations():
    """
    Enhanced history endpoint with search and filter support:
    Returns a list of reconciliation runs from the SQLite database.

    Query parameters:
      - limit (int, default 50, max 500): Maximum number of results
      - search (str): Search term to filter by invoice_file or bank_file names
      - date_from (str, YYYY-MM-DD): Filter reconciliations created on or after this date
      - date_to (str, YYYY-MM-DD): Filter reconciliations created on or before this date
      - min_matches (int): Minimum match count filter
      - max_matches (int): Maximum match count filter
    
    Example: /api/reconciliations?search=invoice&date_from=2024-01-01&min_matches=10
    """
    try:
        # Read and validate query parameters
        raw_limit = request.args.get("limit", "50")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 50
        
        search = request.args.get("search", "").strip() or None
        date_from = request.args.get("date_from", "").strip() or None
        date_to = request.args.get("date_to", "").strip() or None
        
        min_matches = request.args.get("min_matches")
        min_matches = int(min_matches) if min_matches else None
        
        max_matches = request.args.get("max_matches")
        max_matches = int(max_matches) if max_matches else None

        items = fetch_recent_reconciliations(
            limit=limit,
            search=search,
            date_from=date_from,
            date_to=date_to,
            min_matches=min_matches,
            max_matches=max_matches
        )

        return jsonify(
            {
                "reconciliations": items,
                "count": len(items),
                "filters_applied": {
                    "search": search,
                    "date_from": date_from,
                    "date_to": date_to,
                    "min_matches": min_matches,
                    "max_matches": max_matches
                }
            }
        )
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in /api/reconciliations: {e}")
        print(error_traceback)
        return (
            jsonify(
                {
                    "error": "Internal server error while fetching reconciliation history.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/reconciliations/<int:reconciliation_id>", methods=["DELETE"])
@limiter.limit(RATE_LIMITS.get("/api/reconciliations", "30 per minute"))
def api_delete_reconciliation(reconciliation_id: int):
    """
    Delete a reconciliation and all its associated matches.
    
    This is a destructive operation and cannot be undone.
    """
    try:
        success, error_msg = delete_reconciliation(reconciliation_id)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Reconciliation {reconciliation_id} deleted successfully"
            })
        else:
            return jsonify({"error": error_msg}), 404 if "not found" in error_msg.lower() else 500
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(
            "Error deleting reconciliation",
            context={"reconciliation_id": reconciliation_id},
            error=e
        )
        return (
            jsonify(
                {
                    "error": "Internal server error while deleting reconciliation.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


def fetch_reconciliation_matches(reconciliation_id: int) -> List[Dict[str, Any]]:
    """
    Return all matches for a specific reconciliation ID.
    Enhanced with caching for better performance.
    """
    # Check cache first
    cache_key = f"matches_{reconciliation_id}"
    cached_result = cache_get(cache_key)
    if cached_result is not None:
        return cached_result
    
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                rm.id,
                rm.reconciliation_id,
                inv.description AS invoice_description,
                inv.total_amount AS invoice_amount,
                inv.invoice_date AS invoice_date,
                inv.vendor_name AS invoice_vendor_name,
                inv.invoice_number AS invoice_invoice_number,
                inv.invoice_number AS invoice_number,
                inv.extracted_data AS invoice_extracted_data,
                inv.file_upload_id AS invoice_upload_id,
                bt.description AS bank_description,
                bt.amount AS bank_amount,
                bt.transaction_date AS bank_date,
                bt.raw_data AS bank_raw_data,
                bt.file_upload_id AS bank_upload_id,
                '' AS bank_vendor_name,
                '' AS bank_invoice_number,
                rm.match_score AS match_score,
                CASE WHEN rm.match_type = 'manual' THEN 1 ELSE 0 END AS is_manual_match,
                rm.invoice_id,
                rm.transaction_id,
                inv.invoice_file_path AS invoice_file_path,
                inv.id AS invoice_file_id
            FROM reconciliation_matches rm
            LEFT JOIN invoices inv ON rm.invoice_id = inv.id
            LEFT JOIN bank_transactions bt ON rm.transaction_id = bt.id
            WHERE rm.reconciliation_id = ?
            ORDER BY rm.match_score DESC, rm.id ASC
            """,
            (reconciliation_id,),
        )

        rows = [dict(r) for r in cur.fetchall()]

        def _normalize_date_value(val):
            if val is None:
                return None
            # datetime/date objects
            try:
                iso = val.isoformat  # type: ignore[attr-defined]
                if callable(iso):
                    return iso()
            except Exception:
                pass
            # strings
            try:
                s = str(val).strip()
            except Exception:
                return None
            if not s:
                return None
            try:
                dt = _parse_date_safe(s)
                if dt:
                    return dt.date().isoformat()
            except Exception:
                pass
            # leave as-is if cannot parse
            return s

        def _try_get_invoice_number_from_obj(obj):
            import re

            if obj is None:
                return None

            if isinstance(obj, dict):
                # Common keys
                for k in (
                    "invoice_number",
                    "invoiceNumber",
                    "invoice_no",
                    "invoiceNo",
                    "number",
                    "InvoiceNumber",
                    "Invoice No",
                    "Invoice Number",
                ):
                    v = obj.get(k)
                    if isinstance(v, str):
                        s = v.strip()
                        if s and re.search(r"\d", s):
                            return s

                # Nested: invoices list
                invs = obj.get("invoices")
                if isinstance(invs, list):
                    for it in invs:
                        got = _try_get_invoice_number_from_obj(it)
                        if got:
                            return got

                # Other nested containers
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        got = _try_get_invoice_number_from_obj(v)
                        if got:
                            return got

            if isinstance(obj, list):
                for it in obj:
                    got = _try_get_invoice_number_from_obj(it)
                    if got:
                        return got

            return None

        def _derive_invoice_number(row: Dict[str, Any]) -> str | None:
            import json
            import re

            existing = (row.get("invoice_number") or row.get("invoice_invoice_number") or "").strip()
            if existing and re.search(r"\d", existing):
                return existing

            # 1) invoices.extracted_data
            extracted_raw = row.get("invoice_extracted_data")
            if extracted_raw:
                try:
                    extracted_obj = json.loads(extracted_raw) if isinstance(extracted_raw, str) else extracted_raw
                except Exception:
                    extracted_obj = extracted_raw
                got = _try_get_invoice_number_from_obj(extracted_obj)
                if got:
                    return got

            # 2) file_uploads.metadata (parent JSON)
            upload_id = row.get("invoice_upload_id")
            if upload_id:
                try:
                    meta_row = cur.execute(
                        "SELECT metadata FROM file_uploads WHERE id = ? LIMIT 1",
                        (upload_id,),
                    ).fetchone()
                    meta_val = None
                    if meta_row:
                        meta_val = meta_row.get("metadata") if isinstance(meta_row, dict) else meta_row[0]
                    if meta_val:
                        try:
                            meta_obj = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                        except Exception:
                            meta_obj = meta_val
                        got = _try_get_invoice_number_from_obj(meta_obj)
                        if got:
                            return got
                except Exception:
                    pass

            return None

        # Fill invoice_number if blank using stored JSON
        for r in rows:
            derived = _derive_invoice_number(r)
            if derived:
                r["invoice_number"] = derived
                r["invoice_invoice_number"] = derived

            # Normalize/derive dates
            invd = _derive_invoice_date(r)
            if invd:
                r["invoice_date"] = invd
            else:
                r["invoice_date"] = _normalize_date_value(r.get("invoice_date"))

            bd = _derive_bank_date(r)
            if bd:
                r["bank_date"] = bd
            else:
                r["bank_date"] = _normalize_date_value(r.get("bank_date"))

    # Cache result
    cache_set(cache_key, rows)
    
    return rows


@app.route("/api/reconciliations/<int:reconciliation_id>/matches", methods=["GET"])
@limiter.limit(RATE_LIMITS.get("/api/reconciliations/<int:reconciliation_id>/matches", "60 per minute"))
def api_get_reconciliation_matches(reconciliation_id: int):
    """
    Get all matches for a specific reconciliation ID with pagination and filtering.
    
    Query parameters:
      - page (int, default 1): Page number
      - limit (int, default 50, max 1000): Items per page
      - min_score (float): Minimum match score (0.0 to 1.0)
      - max_score (float): Maximum match score (0.0 to 1.0)
      - min_amount (float): Minimum amount filter
      - max_amount (float): Maximum amount filter
      - date_from (str, YYYY-MM-DD): Filter by date from
      - date_to (str, YYYY-MM-DD): Filter by date to
      - vendor (str): Filter by vendor name
      - manual_only (bool): Show only manual matches
      - auto_only (bool): Show only automatic matches
    """
    try:
        # Get query parameters
        page = int(request.args.get("page", 1))
        limit = min(int(request.args.get("limit", 50)), 1000)
        min_score = request.args.get("min_score")
        max_score = request.args.get("max_score")
        min_amount = request.args.get("min_amount")
        max_amount = request.args.get("max_amount")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        vendor = request.args.get("vendor")
        manual_only = request.args.get("manual_only", "false").lower() == "true"
        auto_only = request.args.get("auto_only", "false").lower() == "true"
        
        # Build query with filters
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT
                    rm.id,
                    rm.reconciliation_id,
                    inv.description AS invoice_description,
                    inv.total_amount AS invoice_amount,
                    inv.invoice_date AS invoice_date,
                    inv.vendor_name AS invoice_vendor_name,
                    inv.invoice_number AS invoice_invoice_number,
                    inv.invoice_number AS invoice_number,
                    inv.extracted_data AS invoice_extracted_data,
                    inv.file_upload_id AS invoice_upload_id,
                    bt.description AS bank_description,
                    bt.amount AS bank_amount,
                    bt.transaction_date AS bank_date,
                    bt.raw_data AS bank_raw_data,
                    bt.file_upload_id AS bank_upload_id,
                    '' AS bank_vendor_name,
                    '' AS bank_invoice_number,
                    rm.match_score AS match_score,
                    CASE WHEN rm.match_type = 'manual' THEN 1 ELSE 0 END AS is_manual_match,
                    rm.invoice_id,
                    rm.transaction_id,
                    inv.invoice_file_path AS invoice_file_path,
                    inv.id AS invoice_file_id
                FROM reconciliation_matches rm
                LEFT JOIN invoices inv ON rm.invoice_id = inv.id
                LEFT JOIN bank_transactions bt ON rm.transaction_id = bt.id
                WHERE rm.reconciliation_id = ?
            """
            params = [reconciliation_id]
            
            # Add filters
            if min_score:
                query += " AND rm.match_score >= ?"
                params.append(float(min_score))
            if max_score:
                query += " AND rm.match_score <= ?"
                params.append(float(max_score))
            if min_amount:
                query += " AND (inv.total_amount >= ? OR bt.amount >= ?)"
                params.extend([float(min_amount), float(min_amount)])
            if max_amount:
                query += " AND (inv.total_amount <= ? OR bt.amount <= ?)"
                params.extend([float(max_amount), float(max_amount)])
            if date_from:
                query += " AND (inv.invoice_date >= ? OR bt.transaction_date >= ?)"
                params.extend([date_from, date_from])
            if date_to:
                query += " AND (inv.invoice_date <= ? OR bt.transaction_date <= ?)"
                params.extend([date_to, date_to])
            if vendor:
                query += " AND (inv.vendor_name LIKE ?)"
                vendor_pattern = f"%{vendor}%"
                params.extend([vendor_pattern])
            if manual_only:
                query += " AND rm.match_type = 'manual'"
            if auto_only:
                query += " AND rm.match_type <> 'manual'"
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM ({query}) AS q"
            cur.execute(count_query, params)
            count_row = cur.fetchone()
            if isinstance(count_row, dict):
                # MySQL DictCursor returns dict like {'COUNT(*)': 123}
                total_count = next(iter(count_row.values()), 0)
            else:
                total_count = count_row[0] if count_row else 0
            
            # Add ordering and pagination
            query += " ORDER BY rm.match_score DESC, rm.id ASC LIMIT ? OFFSET ?"
            offset = (page - 1) * limit
            params.extend([limit, offset])
            
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]

            # Derive missing invoice_number from stored JSON (same logic as fetch_reconciliation_matches)
            import json
            import re

            def _normalize_date_value(val):
                if val is None:
                    return None
                try:
                    iso = val.isoformat  # type: ignore[attr-defined]
                    if callable(iso):
                        return iso()
                except Exception:
                    pass
                try:
                    s = str(val).strip()
                except Exception:
                    return None
                if not s:
                    return None
                try:
                    dt = _parse_date_safe(s)
                    if dt:
                        return dt.date().isoformat()
                except Exception:
                    pass
                return s

            def _try_get_date_from_obj(obj):
                if obj is None:
                    return None

                if isinstance(obj, dict):
                    for k in (
                        "invoice_date",
                        "invoiceDate",
                        "due_date",
                        "dueDate",
                        "transaction_date",
                        "transactionDate",
                        "posting_date",
                        "postingDate",
                        "value_date",
                        "valueDate",
                        "date",
                        "Date",
                        "statement_period_start",
                        "statement_period_end",
                    ):
                        v = obj.get(k)
                        if v is None:
                            continue
                        nv = _normalize_date_value(v)
                        if nv:
                            return nv

                    # Search in "statements" -> "1" -> "transactions" -> "1", "2", etc. (bank statement format)
                    statements = obj.get("statements")
                    if isinstance(statements, dict):
                        for stmt_key, stmt_val in statements.items():
                            if isinstance(stmt_val, dict):
                                # Check statement_info for dates
                                stmt_info = stmt_val.get("statement_info")
                                if isinstance(stmt_info, dict):
                                    got = _try_get_date_from_obj(stmt_info)
                                    if got:
                                        return got
                                # Check transactions
                                txns = stmt_val.get("transactions")
                                if isinstance(txns, dict):
                                    for tx_key, tx_val in txns.items():
                                        if isinstance(tx_val, dict):
                                            got = _try_get_date_from_obj(tx_val)
                                            if got:
                                                return got

                    # Search in "uploads" -> "1", "2", etc. (invoice format)
                    uploads = obj.get("uploads")
                    if isinstance(uploads, dict):
                        for upl_key, upl_val in uploads.items():
                            if isinstance(upl_val, dict):
                                got = _try_get_date_from_obj(upl_val)
                                if got:
                                    return got

                    for list_key in ("records", "transactions", "invoices"):
                        v = obj.get(list_key)
                        if isinstance(v, list):
                            for it in v:
                                got = _try_get_date_from_obj(it)
                                if got:
                                    return got

                    er = obj.get("extracted_records")
                    if isinstance(er, dict):
                        for list_key in ("records", "transactions", "invoices"):
                            v = er.get(list_key)
                            if isinstance(v, list):
                                for it in v:
                                    got = _try_get_date_from_obj(it)
                                    if got:
                                        return got

                    for v in obj.values():
                        if isinstance(v, (dict, list)):
                            got = _try_get_date_from_obj(v)
                            if got:
                                return got

                if isinstance(obj, list):
                    for it in obj:
                        got = _try_get_date_from_obj(it)
                        if got:
                            return got

                return None

            def _try_get_invoice_number_from_obj(obj):
                if obj is None:
                    return None
                if isinstance(obj, dict):
                    for k in (
                        "invoice_number",
                        "invoiceNumber",
                        "invoice_no",
                        "invoiceNo",
                        "number",
                        "InvoiceNumber",
                        "Invoice No",
                        "Invoice Number",
                    ):
                        v = obj.get(k)
                        if isinstance(v, str):
                            s = v.strip()
                            if s and re.search(r"\d", s):
                                return s

                    invs = obj.get("invoices")
                    if isinstance(invs, list):
                        for it in invs:
                            got = _try_get_invoice_number_from_obj(it)
                            if got:
                                return got

                    for v in obj.values():
                        if isinstance(v, (dict, list)):
                            got = _try_get_invoice_number_from_obj(v)
                            if got:
                                return got

                if isinstance(obj, list):
                    for it in obj:
                        got = _try_get_invoice_number_from_obj(it)
                        if got:
                            return got
                return None

            for r in rows:
                existing = (r.get("invoice_number") or r.get("invoice_invoice_number") or "").strip()
                if existing and re.search(r"\d", existing):
                    continue

                extracted_raw = r.get("invoice_extracted_data")
                derived = None
                if extracted_raw:
                    try:
                        extracted_obj = json.loads(extracted_raw) if isinstance(extracted_raw, str) else extracted_raw
                    except Exception:
                        extracted_obj = extracted_raw
                    derived = _try_get_invoice_number_from_obj(extracted_obj)

                if (not derived) and r.get("invoice_upload_id"):
                    try:
                        meta_row = cur.execute(
                            "SELECT metadata FROM file_uploads WHERE id = ? LIMIT 1",
                            (r.get("invoice_upload_id"),),
                        ).fetchone()
                        meta_val = None
                        if meta_row:
                            meta_val = meta_row.get("metadata") if isinstance(meta_row, dict) else meta_row[0]
                        if meta_val:
                            try:
                                meta_obj = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                            except Exception:
                                meta_obj = meta_val
                            derived = _try_get_invoice_number_from_obj(meta_obj)
                    except Exception:
                        pass

                if derived:
                    r["invoice_number"] = derived
                    r["invoice_invoice_number"] = derived

            # Normalize/derive dates (invoice_date from JSON, bank_date normalize)
            for r in rows:
                invd = _normalize_date_value(r.get("invoice_date"))
                if not invd:
                    extracted_raw = r.get("invoice_extracted_data")
                    if extracted_raw:
                        try:
                            extracted_obj = json.loads(extracted_raw) if isinstance(extracted_raw, str) else extracted_raw
                        except Exception:
                            extracted_obj = extracted_raw
                        invd = _try_get_date_from_obj(extracted_obj)

                if (not invd) and r.get("invoice_upload_id"):
                    try:
                        meta_row = cur.execute(
                            "SELECT metadata FROM file_uploads WHERE id = ? LIMIT 1",
                            (r.get("invoice_upload_id"),),
                        ).fetchone()
                        meta_val = None
                        if meta_row:
                            meta_val = meta_row.get("metadata") if isinstance(meta_row, dict) else meta_row[0]
                        if meta_val:
                            try:
                                meta_obj = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                            except Exception:
                                meta_obj = meta_val
                            invd = _try_get_date_from_obj(meta_obj)
                    except Exception:
                        pass

                if invd:
                    r["invoice_date"] = invd
                else:
                    r["invoice_date"] = _normalize_date_value(r.get("invoice_date"))

                # Also derive bank_date from raw JSON if needed
                bd = _normalize_date_value(r.get("bank_date"))
                if not bd:
                    raw = r.get("bank_raw_data")
                    if raw:
                        try:
                            obj = json.loads(raw) if isinstance(raw, str) else raw
                        except Exception:
                            obj = raw
                        bd = _try_get_date_from_obj(obj)

                if (not bd) and r.get("bank_upload_id"):
                    try:
                        meta_row = cur.execute(
                            "SELECT metadata FROM file_uploads WHERE id = ? LIMIT 1",
                            (r.get("bank_upload_id"),),
                        ).fetchone()
                        meta_val = None
                        if meta_row:
                            meta_val = meta_row.get("metadata") if isinstance(meta_row, dict) else meta_row[0]
                        if meta_val:
                            try:
                                meta_obj = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                            except Exception:
                                meta_obj = meta_val
                            bd = _try_get_date_from_obj(meta_obj)
                    except Exception:
                        pass

                r["bank_date"] = bd or _normalize_date_value(r.get("bank_date"))
            
            return jsonify({
                "reconciliation_id": reconciliation_id,
                "matches": rows,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "pages": (total_count + limit - 1) // limit
                },
                "count": len(rows),
                "total_count": total_count
            })
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in /api/reconciliations/{reconciliation_id}/matches: {e}")
        print(error_traceback)
        return (
            jsonify(
                {
                    "error": "Internal server error while fetching matches.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/reconciliations/<int:reconciliation_id>/matches/search", methods=["GET"])
@limiter.limit("60 per minute")
def api_search_matches(reconciliation_id: int):
    """
    Search matches by description, vendor, or invoice number.
    
    Query parameters:
      - q (str, required): Search query
      - page (int, default 1): Page number
      - limit (int, default 50): Items per page
    """
    try:
        search_query = request.args.get("q", "").strip()
        if not search_query:
            return jsonify({"error": "Search query 'q' is required"}), 400
        
        page = int(request.args.get("page", 1))
        limit = min(int(request.args.get("limit", 50)), 1000)
        
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            search_pattern = f"%{search_query}%"
            query = """
                SELECT id, reconciliation_id, invoice_description, invoice_amount, invoice_date,
                       invoice_vendor_name, invoice_invoice_number, bank_description, bank_amount,
                       bank_date, bank_vendor_name, bank_invoice_number, match_score, is_manual_match
                FROM reconciliation_matches
                WHERE reconciliation_id = ? AND (
                    invoice_description LIKE ? OR
                    bank_description LIKE ? OR
                    invoice_vendor_name LIKE ? OR
                    bank_vendor_name LIKE ? OR
                    invoice_invoice_number LIKE ? OR
                    bank_invoice_number LIKE ?
                )
                ORDER BY match_score DESC, id ASC
                LIMIT ? OFFSET ?
            """
            
            offset = (page - 1) * limit
            cur.execute(
                query,
                (
                    reconciliation_id,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    limit,
                    offset,
                ),
            )
            rows = cur.fetchall()
            
            # Get total count
            count_query = """
                SELECT COUNT(*) FROM reconciliation_matches
                WHERE reconciliation_id = ? AND (
                    invoice_description LIKE ? OR
                    bank_description LIKE ? OR
                    invoice_vendor_name LIKE ? OR
                    bank_vendor_name LIKE ? OR
                    invoice_invoice_number LIKE ? OR
                    bank_invoice_number LIKE ?
                )
            """
            cur.execute(
                count_query,
                (
                    reconciliation_id,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                ),
            )
            total_count = cur.fetchone()[0]
            
            return jsonify({
                "reconciliation_id": reconciliation_id,
                "query": search_query,
                "matches": [dict(r) for r in rows],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "pages": (total_count + limit - 1) // limit
                },
                "count": len(rows)
            })
    except Exception as e:
        logger.error("Error searching matches", context={"reconciliation_id": reconciliation_id}, error=e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/reconciliations/<int:reconciliation_id>/json", methods=["GET"])
@limiter.limit("60 per minute")
def api_get_reconciliation_json(reconciliation_id: int):
    try:
        rebuild = request.args.get("rebuild", "0").lower() in {"1", "true", "yes"}
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            row = cur.execute(
                """
                SELECT id, name, description, reconciliation_date, status,
                       total_invoices, total_transactions, total_matches, total_amount_matched,
                       reference, reference_name, raw_json, created_at, updated_at
                FROM reconciliations
                WHERE id = ?
                """,
                (reconciliation_id,),
            ).fetchone()

        if not row:
            return jsonify({"error": "Reconciliation not found"}), 404

        rec = dict(row)
        raw = rec.get("raw_json")
        raw_obj = None
        if raw:
            try:
                raw_obj = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                raw_obj = raw

        if (raw_obj is None) and rebuild:
            try:
                matches_rows = fetch_reconciliation_matches_for_export(reconciliation_id)
                rebuilt = {
                    "schema": "hybrid_reconciliation_v1_rebuild",
                    "reconciliation_id": reconciliation_id,
                    "generated_at": datetime.now().isoformat(),
                    "source": "rebuild_from_db",
                    "results": {
                        "matches": matches_rows,
                        "summary": {
                            "total_matches": len(matches_rows),
                        },
                    },
                }
                db_manager.execute_update(
                    "UPDATE reconciliations SET raw_json = %s WHERE id = %s",
                    (json.dumps(rebuilt, ensure_ascii=False, default=str), reconciliation_id),
                )
                raw_obj = rebuilt
            except Exception as e:
                logger.warning(
                    "Failed to rebuild reconciliations.raw_json",
                    context={"reconciliation_id": reconciliation_id},
                    error=e,
                )

        rec["raw_json"] = raw_obj
        
        # Include manual entries in the results
        if raw_obj and isinstance(raw_obj, dict) and "results" in raw_obj:
            try:
                # Fetch manual entries for this reconciliation
                with db_manager.get_connection() as conn:
                    cur = conn.cursor()
                    
                    # Get manual invoice entries
                    cur.execute("""
                        SELECT id, description, amount, date, invoice_number, vendor_name, currency, created_at
                        FROM manual_invoice_entries 
                        WHERE reconciliation_id = ?
                        ORDER BY created_at DESC
                    """, (reconciliation_id,))
                    manual_invoices = [
                        {
                            "id": row[0],
                            "description": row[1],
                            "amount": row[2],
                            "date": row[3],
                            "invoice_number": row[4],
                            "vendor_name": row[5],
                            "currency": row[6],
                            "created_at": row[7],
                            "is_manual": True
                        }
                        for row in cur.fetchall()
                    ]
                    
                    # Get manual bank entries
                    cur.execute("""
                        SELECT id, description, amount, date, reference_id, currency, created_at
                        FROM manual_bank_entries 
                        WHERE reconciliation_id = ?
                        ORDER BY created_at DESC
                    """, (reconciliation_id,))
                    manual_banks = [
                        {
                            "id": row[0],
                            "description": row[1],
                            "amount": row[2],
                            "date": row[3],
                            "reference_id": row[4],
                            "currency": row[5],
                            "created_at": row[6],
                            "is_manual": True
                        }
                        for row in cur.fetchall()
                    ]
                    
                    # Merge manual entries into unmatched lists
                    results = raw_obj.get("results", {})
                    unmatched_invoices = results.get("unmatched_invoices", [])
                    unmatched_transactions = results.get("unmatched_transactions", [])
                    
                    # Add manual entries to the beginning of unmatched lists
                    results["unmatched_invoices"] = manual_invoices + unmatched_invoices
                    results["unmatched_transactions"] = manual_banks + unmatched_transactions
                    
                    # Update raw_json with merged data
                    rec["raw_json"] = raw_obj
                    
            except Exception as e:
                logger.warning(
                    "Failed to include manual entries in reconciliation results",
                    context={"reconciliation_id": reconciliation_id},
                    error=e,
                )

        return jsonify({
            "success": True,
            "reconciliation": rec,
        })
    except Exception as e:
        error_traceback = traceback.format_exc()
        return (
            jsonify(
                {
                    "error": "Internal server error while fetching reconciliation JSON.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/dashboard", methods=["GET"])
@limiter.limit("60 per minute")
def api_dashboard():
    """
    Get dashboard statistics and overview.
    
    Returns:
    - Total reconciliations
    - Total matches
    - Recent reconciliations
    - Statistics by date range
    """
    try:
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            
            # Total reconciliations
            total_reconciliations = cur.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0]
            
            # Total matches
            total_matches = cur.execute("SELECT COUNT(*) FROM reconciliation_matches").fetchone()[0]
            
            # Recent reconciliations (last 10)
            recent_reconciliations = cur.execute("""
                SELECT id, invoice_file, bank_file, match_count, created_at
                FROM reconciliations
                ORDER BY created_at DESC
                LIMIT 10
            """).fetchall()
            
            # Statistics by date (last 30 days)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            recent_stats = cur.execute("""
                SELECT 
                    COUNT(*) as count,
                    SUM(match_count) as total_matches,
                    AVG(match_count) as avg_matches
                FROM reconciliations
                WHERE created_at >= ?
            """, (thirty_days_ago,)).fetchone()
            
            # Match statistics
            match_stats = cur.execute("""
                SELECT 
                    AVG(match_score) as avg_score,
                    COUNT(CASE WHEN is_manual_match = 1 THEN 1 END) as manual_matches,
                    COUNT(CASE WHEN is_manual_match = 0 THEN 1 END) as auto_matches
                FROM reconciliation_matches
            """).fetchone()
            
            return jsonify({
                "statistics": {
                    "total_reconciliations": total_reconciliations,
                    "total_matches": total_matches,
                    "recent_30_days": {
                        "reconciliations": recent_stats[0] or 0,
                        "total_matches": recent_stats[1] or 0,
                        "avg_matches": round(recent_stats[2] or 0, 2)
                    },
                    "match_quality": {
                        "avg_score": round(match_stats[0] or 0, 3),
                        "manual_matches": match_stats[1] or 0,
                        "auto_matches": match_stats[2] or 0
                    }
                },
                "recent_reconciliations": [dict(r) for r in recent_reconciliations]
            })
    except Exception as e:
        logger.error("Error fetching dashboard data", error=e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/invoices/backfill-invoice-numbers", methods=["POST"])
@limiter.limit("10 per minute")
def api_backfill_invoice_numbers():
    try:
        payload = request.get_json(silent=True) or {}
        dry_run = str(payload.get("dry_run", "1")).lower() in {"1", "true", "yes"}
        limit = int(payload.get("limit", 50))
        offset = int(payload.get("offset", 0))

        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        from services.multi_invoice_processor import multi_invoice_processor

        def _extract_invoice_number_from_file(file_path: str) -> str | None:
            if not file_path:
                return None
            try:
                ext = os.path.splitext(file_path)[1].lower()
            except Exception:
                ext = ""

            try:
                if ext == ".pdf":
                    from PyPDF2 import PdfReader

                    with open(file_path, "rb") as f:
                        reader = PdfReader(f)
                        for page in reader.pages:
                            try:
                                txt = page.extract_text() or ""
                            except Exception:
                                txt = ""
                            inv_no = multi_invoice_processor._extract_invoice_number(txt)
                            if inv_no:
                                return inv_no
                    return None

                if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
                    from PIL import Image
                    import pytesseract

                    image = Image.open(file_path)
                    txt = pytesseract.image_to_string(image) or ""
                    return multi_invoice_processor._extract_invoice_number(txt)

                return None
            except Exception:
                return None

        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT id, invoice_number, invoice_file_path, extracted_data
                FROM invoices
                WHERE (invoice_number IS NULL OR TRIM(invoice_number) = '')
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

        candidates = [dict(r) for r in rows]
        preview: list[dict] = []
        updates: list[tuple[int, str]] = []

        for r in candidates:
            invoice_id = r.get("id")
            file_path = r.get("invoice_file_path")
            extracted_data = r.get("extracted_data")

            inv_no = None
            if extracted_data:
                try:
                    obj = json.loads(extracted_data) if isinstance(extracted_data, str) else extracted_data
                    inv_no = obj.get("invoice_number")
                    if not inv_no:
                        uploads = (obj.get("uploads") or {})
                        for _, u in uploads.items():
                            if isinstance(u, dict) and u.get("invoice_number"):
                                inv_no = u.get("invoice_number")
                                break
                except Exception:
                    inv_no = None

            if not inv_no:
                inv_no = _extract_invoice_number_from_file(file_path)

            if inv_no:
                inv_no_norm = str(inv_no).strip()
                if inv_no_norm:
                    updates.append((int(invoice_id), inv_no_norm))
                    preview.append({
                        "invoice_id": int(invoice_id),
                        "invoice_file_path": file_path,
                        "invoice_number": inv_no_norm,
                    })

        if (not dry_run) and updates:
            with db_manager.get_connection() as conn:
                cur = conn.cursor()
                for inv_id, inv_no_norm in updates:
                    cur.execute(
                        "UPDATE invoices SET invoice_number = ? WHERE id = ?",
                        (inv_no_norm, inv_id),
                    )
                conn.commit()

        return jsonify({
            "success": True,
            "dry_run": dry_run,
            "scanned": len(candidates),
            "found": len(updates),
            "updated": 0 if dry_run else len(updates),
            "preview": preview,
        })
    except Exception as e:
        error_traceback = traceback.format_exc()
        return (
            jsonify(
                {
                    "error": "Internal server error while backfilling invoice numbers.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/reconciliations/<int:reconciliation_id>/matches/bulk", methods=["POST"])
@limiter.limit("30 per minute")
def api_bulk_operations(reconciliation_id: int):
    """
    Perform bulk operations on matches.
    
    Request body:
    {
        "action": "delete" | "update_score" | "mark_manual" | "mark_auto",
        "match_ids": [1, 2, 3, ...],
        "data": {...}  # Optional data for update operations
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        action = data.get("action")
        match_ids = data.get("match_ids", [])
        
        if not action or not match_ids:
            return jsonify({"error": "action and match_ids are required"}), 400
        
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            
            # Verify all matches belong to this reconciliation
            placeholders = ",".join("?" * len(match_ids))
            params = match_ids + [reconciliation_id]
            verify_query = f"""
                SELECT COUNT(*) FROM reconciliation_matches
                WHERE id IN ({placeholders}) AND reconciliation_id = ?
            """
            valid_count = cur.execute(verify_query, params).fetchone()[0]
            
            if valid_count != len(match_ids):
                return jsonify({"error": "Some match IDs are invalid or don't belong to this reconciliation"}), 400
            
            affected = 0
            
            if action == "delete":
                delete_query = f"""
                    DELETE FROM reconciliation_matches
                    WHERE id IN ({placeholders}) AND reconciliation_id = ?
                """
                cur.execute(delete_query, params)
                affected = cur.rowcount
                
            elif action == "mark_manual":
                update_query = f"""
                    UPDATE reconciliation_matches
                    SET is_manual_match = 1
                    WHERE id IN ({placeholders}) AND reconciliation_id = ?
                """
                cur.execute(update_query, params)
                affected = cur.rowcount
                
            elif action == "mark_auto":
                update_query = f"""
                    UPDATE reconciliation_matches
                    SET is_manual_match = 0
                    WHERE id IN ({placeholders}) AND reconciliation_id = ?
                """
                cur.execute(update_query, params)
                affected = cur.rowcount
                
            elif action == "update_score":
                new_score = data.get("score")
                if new_score is None:
                    return jsonify({"error": "score is required for update_score action"}), 400
                
                update_query = f"""
                    UPDATE reconciliation_matches
                    SET match_score = ?
                    WHERE id IN ({placeholders}) AND reconciliation_id = ?
                """
                cur.execute(update_query, [new_score] + params)
                affected = cur.rowcount
            
            else:
                return jsonify({"error": f"Unknown action: {action}"}), 400
            
            # Clear cache
            cache_key = f"matches_{reconciliation_id}"
            cache_clear()
            
            return jsonify({
                "success": True,
                "action": action,
                "affected": affected,
                "message": f"Successfully {action} {affected} match(es)"
            })
    except Exception as e:
        logger.error("Error in bulk operation", context={"reconciliation_id": reconciliation_id}, error=e)
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    """Serve the single-page frontend."""
    return send_from_directory("static", "index.html")


@app.route("/api/progress/<progress_id>", methods=["GET"])
@limiter.limit("60 per minute")
def api_get_progress(progress_id: str):
    """
    Get progress status for a long-running operation.
    
    Returns:
        {
            "status": "pending" | "processing" | "completed" | "error",
            "progress": 0.0 to 1.0,
            "message": "Current status message",
            "timestamp": "ISO timestamp",
            "data": {...}  # Additional data (e.g., reconciliation_id when complete)
        }
    """
    progress = get_progress(progress_id)
    if progress is None:
        return jsonify({"error": "Progress ID not found"}), 404
    
    return jsonify(progress)


@app.route("/api/health", methods=["GET"])
@limiter.limit(RATE_LIMITS.get("/api/health", "120 per minute"))
def api_health():
    """
    Enhanced health check endpoint with ML model status.
    Returns model health information for debugging.
    """
    health_status = {
        "status": "ok",
        "message": "Server is running",
        "timestamp": datetime.now().isoformat(),
        "model": {
            "loaded": MODEL is not None,
            "path": MODEL_PATH,
            "exists": os.path.exists(MODEL_PATH),
            "feature_count": MODEL_FEATURE_COUNT,
            "load_error": MODEL_LOAD_ERROR,
        }
    }
    
    # Add validation status if model is loaded
    if MODEL is not None:
        is_valid, error_msg = _validate_ml_model(MODEL)
        health_status["model"]["valid"] = is_valid
        if not is_valid:
            health_status["model"]["validation_error"] = error_msg
    
    return jsonify(health_status)


@app.route("/api/check-tables", methods=["GET"])
@limiter.limit("60 per minute")
def api_check_tables():
    """Check table counts and recent records for both invoices and bank statements"""
    try:
        # Get counts from both MySQL tables
        bank_result = db_manager.execute_query('SELECT COUNT(*) as count FROM reconciliations WHERE source_file_hash IS NOT NULL OR type IS NOT NULL')
        invoice_result = db_manager.execute_query('SELECT COUNT(*) as count FROM invoices')
        
        bank_count = bank_result[0]['count'] if bank_result else 0
        invoice_count = invoice_result[0]['count'] if invoice_result else 0
        
        # Get recent records
        recent_bank = db_manager.execute_query(
            'SELECT id, source_file_name, date_utc, type, amount, created_at FROM reconciliations WHERE source_file_hash IS NOT NULL OR type IS NOT NULL ORDER BY id DESC LIMIT 5'
        )
        recent_invoices = db_manager.execute_query(
            'SELECT id, invoice_number, vendor_name, status, created_at FROM invoices ORDER BY id DESC LIMIT 5'
        )
        
        return jsonify({
            "success": True,
            "table_counts": {
                "reconciliations(bank_rows)": bank_count,
                "invoices": invoice_count,
            },
            "recent_bank_statements": recent_bank,
            "recent_invoices": recent_invoices
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Failed to check tables: {str(e)}"
        }), 500


@app.route("/api/invoice-image/<int:invoice_file_id>", methods=["GET"])
@limiter.limit(RATE_LIMITS.get("/api/invoice-image/<int:invoice_file_id>", "60 per minute"))
def api_get_invoice_image(invoice_file_id: int):
    """
    Serve invoice image file by invoice_file_id.
    Returns the invoice image file for viewing.
    """
    try:
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            # Backward compatible param name: invoice_file_id is treated as invoices.id
            row = cur.execute(
                "SELECT invoice_file_path, description FROM invoices WHERE id = ?",
                (invoice_file_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "Invoice file not found"}), 404

            file_path = row["invoice_file_path"] if isinstance(row, dict) else row[0]
            file_name = row["description"] if isinstance(row, dict) else row[1]
            if not file_path or not os.path.exists(file_path):
                return jsonify({"error": "Invoice file not found on disk"}), 404
        
        # Determine MIME type based on file extension
        ext = os.path.splitext(file_name)[1].lower()
        mimetype_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
            '.tif': 'image/tiff',
            '.tiff': 'image/tiff'
        }
        mimetype = mimetype_map.get(ext, 'application/octet-stream')
        
        return send_from_directory(
            os.path.dirname(file_path),
            os.path.basename(file_path),
            as_attachment=False,
            download_name=file_name or os.path.basename(file_path),
        )
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(
            "Error serving invoice image",
            context={"invoice_file_id": invoice_file_id},
            error=e
        )
        return (
            jsonify({
                "error": "Internal server error while serving invoice image.",
                "details": str(e),
                "traceback": error_traceback if app.debug else None,
            }),
            500,
        )


@app.route("/api/reconciliations/<int:reconciliation_id>/matches/export", methods=["GET"])
@limiter.limit(RATE_LIMITS.get("/api/reconciliations/<int:reconciliation_id>/matches/export", "20 per minute"))
def api_export_matches(reconciliation_id: int):
    """
    Export all matches for a reconciliation ID in multiple formats.
    
    Supported formats (via ?format= parameter):
    - csv (default): CSV file
    - xlsx: Excel file
    - pdf: PDF report
    
    Example: /api/reconciliations/1/matches/export?format=xlsx
    """
    try:
        # Get export format from query parameter (default: csv)
        export_format = request.args.get("format", "csv").lower()

        matches = fetch_reconciliation_matches_for_export(reconciliation_id)
        
        if not matches:
            return jsonify({"error": "No matches found for this reconciliation ID"}), 404

        headers = list(matches[0].keys())
        rows = [[m.get(h, "") for h in headers] for m in matches]
        
        # Export based on format
        if export_format == "xlsx":
            # Excel export
            output = io.BytesIO()
            df = pd.DataFrame(rows, columns=headers)
            
            # Create Excel writer
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Matches', index=False)
                
                # Auto-adjust column widths
                worksheet = writer.sheets['Matches']
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
            
            output.seek(0)
            return Response(
                output.read(),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f"attachment; filename=reconciliation_{reconciliation_id}_matches.xlsx"
                }
            )
        
        elif export_format == "pdf":
            try:
                # PDF export using ReportLab
                from reportlab.lib.pagesizes import A4
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib import colors
                from reportlab.lib.units import inch

                output = io.BytesIO()
                doc = SimpleDocTemplate(
                    output,
                    pagesize=A4,
                    leftMargin=36,
                    rightMargin=36,
                    topMargin=36,
                    bottomMargin=36,
                )
                
                # Create document content
                elements = []
                styles = getSampleStyleSheet()
                
                # Title
                title = Paragraph(f"Reconciliation Report - ID: {reconciliation_id}", styles['Title'])
                elements.append(title)
                elements.append(Spacer(1, 12))
                
                # Metadata
                metadata = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>Total Matches: {len(matches)}", styles['Normal'])
                elements.append(metadata)
                elements.append(Spacer(1, 12))

                for idx, match in enumerate(matches, start=1):
                    heading = Paragraph(
                        f"Match {idx} (match_id: {match.get('match_id', '')})",
                        styles['Heading2'],
                    )
                    elements.append(heading)
                    elements.append(Spacer(1, 6))

                    field_rows = []
                    for key in headers:
                        val = match.get(key, "")
                        if val is None:
                            val = ""
                        key_p = Paragraph(str(key), styles['BodyText'])
                        val_p = Paragraph(str(val), styles['BodyText'])
                        field_rows.append([key_p, val_p])

                    field_table = Table(
                        field_rows,
                        colWidths=[2.2 * inch, 4.8 * inch],
                        hAlign='LEFT',
                    )
                    field_table.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                    ]))
                    elements.append(field_table)
                    elements.append(Spacer(1, 12))

                    if idx < len(matches):
                        elements.append(PageBreak())
                
                # Build PDF
                doc.build(elements)
                
                output.seek(0)
                
                return Response(
                    output.getvalue(),
                    mimetype="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename=reconciliation_{reconciliation_id}_matches.pdf"
                    }
                )
            except ImportError as e:
                print(f"DEBUG: ReportLab import failed: {e}")
                # Fallback to text-based PDF if ReportLab is not available
                output = io.StringIO()
                output.write(f"Reconciliation Report - ID: {reconciliation_id}\n")
                output.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                output.write(f"Total Matches: {len(matches)}\n")
                output.write("=" * 100 + "\n\n")
                
                # Write table
                col_widths = [20, 12, 12, 20, 15, 20, 12, 12, 20, 15, 10, 10]
                output.write(" | ".join([h[:col_widths[i]] for i, h in enumerate(headers)]) + "\n")
                output.write("-" * 100 + "\n")
                
                for row in rows:
                    output.write(" | ".join([str(r)[:col_widths[i]] for i, r in enumerate(row)]) + "\n")
                
                return Response(
                    output.getvalue(),
                    mimetype="text/plain",
                    headers={
                        "Content-Disposition": f"attachment; filename=reconciliation_{reconciliation_id}_matches.txt"
                    }
                )
            except Exception as e:
                print(f"DEBUG: PDF generation failed: {e}")
                # Return error if PDF generation fails
                return jsonify({
                    "error": "PDF generation failed",
                    "details": str(e)
                }), 500
        
        else:
            # Default: CSV export
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)
            
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=reconciliation_{reconciliation_id}_matches.csv"
                }
            )
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in /api/reconciliations/{reconciliation_id}/matches/export: {e}")
        print(error_traceback)
        return (
            jsonify(
                {
                    "error": "Internal server error while exporting matches.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/reconciliations/<int:reconciliation_id>/matches/<int:match_id>", methods=["DELETE"])
@limiter.limit(RATE_LIMITS.get("/api/reconciliations/<int:reconciliation_id>/matches/<int:match_id>", "30 per minute"))
def api_delete_match(reconciliation_id: int, match_id: int):
    """
    Delete a match (manual or automatic) from reconciliation.
    
    This endpoint permanently removes a match between an invoice and bank transaction.
    After deletion, the transactions will appear in unmatched sections when reconciliation is re-run.
    
    Args:
        reconciliation_id: ID of the reconciliation
        match_id: ID of the match to delete
        
    Returns:
        JSON response with success status and match details
        
    Status Codes:
        200: Match deleted successfully
        404: Match not found
        500: Internal server error
    """
    try:
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            
            # Check if match exists and belongs to this reconciliation
            match_row = cur.execute(
                "SELECT is_manual_match FROM reconciliation_matches WHERE id = ? AND reconciliation_id = ?",
                (match_id, reconciliation_id),
            ).fetchone()
            
            if not match_row:
                return jsonify({"error": f"Match ID {match_id} not found for reconciliation {reconciliation_id}"}), 404
            
            # Delete the match
            cur.execute(
                "DELETE FROM reconciliation_matches WHERE id = ? AND reconciliation_id = ?",
                (match_id, reconciliation_id),
            )
            
            # Invalidate cache for this reconciliation's matches
            cache_key = f"matches_{reconciliation_id}"
            with _cache_lock:
                if cache_key in _cache:
                    del _cache[cache_key]
        
        match_type = "Manual" if match_row["is_manual_match"] else "Automatic"
        return jsonify({
            "success": True,
            "message": f"{match_type} match deleted successfully",
            "match_id": match_id,
            "reconciliation_id": reconciliation_id
        })
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in /api/reconciliations/{reconciliation_id}/matches/{match_id} DELETE: {e}")
        print(error_traceback)
        return (
            jsonify(
                {
                    "error": "Internal server error while deleting match.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/process-document", methods=["POST"])
@limiter.limit(RATE_LIMITS.get("/api/process-document", "20 per minute"))
def api_process_document():
    """
    Process a single document (invoice or bank statement) and return extracted transactions.
    Used for manual matching when user uploads a document to match with an unmatched transaction.
    
    Expected form data:
    - file: uploaded file (PDF, image, Excel, CSV)
    - document_type: "invoice" or "bank"
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        document_type = request.form.get('document_type', 'invoice').lower()
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if document_type not in ['invoice', 'bank']:
            return jsonify({"error": "document_type must be 'invoice' or 'bank'"}), 400
        
        # Validate file
        file_name_lower = file.filename.lower()
        if document_type == 'invoice':
            ok, err_msg = _validate_uploaded_file(
                file, INVOICE_ALLOWED_EXTENSIONS, INVOICE_ALLOWED_MIMETYPES
            )
        else:
            ok, err_msg = _validate_uploaded_file(
                file, BANK_ALLOWED_EXTENSIONS, BANK_ALLOWED_MIMETYPES
            )
        
        if not ok:
            return jsonify({"error": err_msg}), 400
        
        # Read file
        file.seek(0)
        file_bytes = file.read()
        
        # Process file based on type
        transactions = []
        if file_name_lower.endswith((".xlsx", ".xls")):
            transactions = excel_to_transactions(file_bytes, source=document_type)
        elif file_name_lower.endswith(".csv"):
            if document_type != 'bank':
                return jsonify({"error": "CSV files are only supported for bank statements"}), 400
            transactions = csv_to_transactions(file_bytes, source=document_type)
        elif file_name_lower.endswith(".pdf"):
            lines = pdf_to_lines(file_bytes)
            transactions = parse_transactions_from_lines(lines, source=document_type)
        else:
            # Image file
            lines = ocr_image_to_lines(file_bytes)
            transactions = parse_transactions_from_lines(lines, source=document_type)
        
        # Convert transactions to dict format
        transactions_list = [asdict(tx) for tx in transactions]
        
        return jsonify({
            "success": True,
            "document_type": document_type,
            "file_name": file.filename,
            "transactions": transactions_list,
            "transaction_count": len(transactions_list)
        })
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in /api/process-document: {e}")
        print(error_traceback)
        return (
            jsonify(
                {
                    "error": "Internal server error while processing document.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


@app.route("/api/reconciliations/<int:reconciliation_id>/manual-match", methods=["POST"])
@limiter.limit(RATE_LIMITS.get("/api/reconciliations/<int:reconciliation_id>/manual-match", "30 per minute"))
def api_create_manual_match(reconciliation_id: int):
    """
    Create a manual match between an unmatched invoice and an unmatched bank transaction.
    
    Enhanced with duplicate detection and validation.
    
    Expected JSON body:
    {
        "invoice_index": int,  # Index in only_in_invoices array
        "bank_index": int,     # Index in only_in_bank array
        "invoice": {...},      # Invoice transaction data
        "bank": {...}          # Bank transaction data
    }
    """
    try:
        data = request.get_json()
        if not data:
            print(f"Error: No JSON data provided for reconciliation {reconciliation_id}")
            return jsonify({"error": "No JSON data provided"}), 400
        
        invoice_data = data.get("invoice", {})
        bank_data = data.get("bank", {})
        
        # Log received data for debugging
        print(f"Received manual match request for reconciliation {reconciliation_id}")
        print(f"Invoice data keys: {list(invoice_data.keys()) if invoice_data else 'None'}")
        print(f"Bank data keys: {list(bank_data.keys()) if bank_data else 'None'}")
        
        if not invoice_data or not bank_data:
            print(f"Error: Missing invoice or bank data for reconciliation {reconciliation_id}")
            print(f"Invoice data: {invoice_data}")
            print(f"Bank data: {bank_data}")
            return jsonify({
                "error": "Both invoice and bank data are required",
                "details": {
                    "invoice_data_provided": bool(invoice_data),
                    "bank_data_provided": bool(bank_data)
                }
            }), 400
        
        # Validate reconciliation exists
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM reconciliations WHERE id = ?", (reconciliation_id,))
            if not cur.fetchone():
                return jsonify({"error": f"Reconciliation ID {reconciliation_id} not found"}), 404
            
            # Check for duplicate matches - prevent same invoice or bank from being matched twice
            # Convert amounts to float, handling None and string values
            try:
                invoice_amount = float(invoice_data.get("amount", 0.0) or 0.0)
            except (ValueError, TypeError):
                invoice_amount = 0.0
            
            try:
                bank_amount = float(bank_data.get("amount", 0.0) or 0.0)
            except (ValueError, TypeError):
                bank_amount = 0.0
            
            invoice_desc = invoice_data.get("description", "") or ""
            bank_desc = bank_data.get("description", "") or ""
            
            # Check if this invoice is already matched (similar amount and description)
            cur.execute(
                """
                SELECT id FROM reconciliation_matches 
                WHERE reconciliation_id = ? 
                AND ABS(invoice_amount - ?) < 0.01
                AND invoice_description = ?
                """,
                (reconciliation_id, invoice_amount, invoice_desc)
            )
            if cur.fetchone():
                return jsonify({
                    "error": "This invoice transaction is already matched. Please unmatch it first if you want to change the match."
                }), 400
            
            # Check if this bank transaction is already matched
            cur.execute(
                """
                SELECT id FROM reconciliation_matches 
                WHERE reconciliation_id = ? 
                AND ABS(bank_amount - ?) < 0.01
                AND bank_description = ?
                """,
                (reconciliation_id, bank_amount, bank_desc)
            )
            if cur.fetchone():
                return jsonify({
                    "error": "This bank transaction is already matched. Please unmatch it first if you want to change the match."
                }), 400

            # Attempt to link this manual match to a stored invoice file (for invoice preview)
            invoice_file_id = invoice_data.get("invoice_file_id")
            invoice_file_path = invoice_data.get("invoice_file_path")
            if not invoice_file_id:
                inv_file_name = invoice_data.get("file_name")
                if inv_file_name and isinstance(inv_file_name, str):
                    base_file_name = inv_file_name.split("#", 1)[0]
                    cur.execute(
                        """
                        SELECT id, invoice_file_path
                        FROM invoices
                        WHERE invoice_file_hash IS NOT NULL AND description = ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (base_file_name,),
                    )
                    file_row = cur.fetchone()
                    if file_row:
                        invoice_file_id = file_row[0]
                        invoice_file_path = file_row[1]

            invoice_id = invoice_data.get("id") or invoice_data.get("invoice_id")
            transaction_id = bank_data.get("id") or bank_data.get("transaction_id")

            invoice_reference_val = (
                invoice_data.get("invoice_number")
                or invoice_data.get("reference_id")
                or invoice_desc
            )
            
            # Insert manual match into database
            insert_query = """
                INSERT INTO reconciliation_matches (
                    reconciliation_id,
                    invoice_description, invoice_amount, invoice_date, invoice_vendor_name,
                    invoice_invoice_number, invoice_currency, invoice_reference_id, invoice_document_subtype,
                    bank_description, bank_amount, bank_date, bank_vendor_name, bank_invoice_number,
                    bank_currency, bank_reference_id, bank_direction, bank_document_subtype, bank_balance,
                    match_score, is_manual_match
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            cur.execute(insert_query, (
                reconciliation_id,
                invoice_desc,
                invoice_amount,
                invoice_data.get("date"),
                invoice_data.get("vendor_name"),
                invoice_data.get("invoice_number"),
                invoice_data.get("currency", ""),
                invoice_reference_val,
                invoice_data.get("document_subtype", ""),
                bank_desc,
                bank_amount,
                bank_data.get("date"),
                bank_data.get("vendor_name"),
                bank_data.get("invoice_number"),
                bank_data.get("currency", ""),
                bank_data.get("reference_id", ""),
                bank_data.get("direction"),
                bank_data.get("document_subtype", ""),
                bank_data.get("balance"),
                1.0,  # Manual matches get score of 1.0
                1,    # is_manual_match = 1
                    ))
            match_id = cur.lastrowid
            
            # Invalidate cache for this reconciliation's matches
            cache_key = f"matches_{reconciliation_id}"
            with _cache_lock:
                if cache_key in _cache:
                    del _cache[cache_key]
            
            # Return response with warnings if any
            response = {
                "success": True,
                "message": "Manual match created successfully",
                "match_id": match_id,
                "reconciliation_id": reconciliation_id
            }
            
            # Include warnings in response if validation found issues
            if validation_result["warnings"]:
                response["warnings"] = validation_result["warnings"]
                logger.warning(
                    "Manual match created with warnings",
                    context={
                        "reconciliation_id": reconciliation_id,
                        "match_id": match_id,
                        "warnings": validation_result["warnings"]
                    }
                )
            
            return jsonify(response)
    except pymysql.err.IntegrityError as e:
        return jsonify({"error": "Database error: This match may already exist"}), 400
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in /api/reconciliations/{reconciliation_id}/manual-match: {e}")
        print(error_traceback)
        return (
            jsonify(
                {
                    "error": "Internal server error while creating manual match.",
                    "details": str(e),
                    "traceback": error_traceback if app.debug else None,
                }
            ),
            500,
        )


# === API Versioning ===
from flask import Blueprint

# Create versioned blueprints
v1_bp = Blueprint('v1', __name__, url_prefix='/api/v1')

# Register v1 routes (for now, same as main routes)
# Future: Move routes to versioned blueprints

# === Webhook Endpoints ===
try:
    from services.webhook_service import register_webhook, unregister_webhook, list_webhooks, trigger_webhook
    
    @app.route("/api/webhooks", methods=["POST"])
    @limiter.limit("10 per minute")
    def api_register_webhook():
        # Register a webhook
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Request body is required"}), 400
            
            webhook_id = data.get("webhook_id")
            url = data.get("url")
            events = data.get("events", [])
            secret = data.get("secret")
            
            if not webhook_id or not url or not events:
                return jsonify({"error": "webhook_id, url, and events are required"}), 400
            
            if register_webhook(webhook_id, url, events, secret):
                return jsonify({"success": True, "message": "Webhook registered"})
            else:
                return jsonify({"error": "Failed to register webhook"}), 500
        except Exception as e:
            logger.error("Error registering webhook", error=e)
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/webhooks/<webhook_id>", methods=["DELETE"])
    @limiter.limit("10 per minute")
    def api_unregister_webhook(webhook_id: str):
        # Unregister a webhook
        try:
            if unregister_webhook(webhook_id):
                return jsonify({"success": True, "message": "Webhook unregistered"})
            else:
                return jsonify({"error": "Webhook not found"}), 404
        except Exception as e:
            logger.error("Error unregistering webhook", error=e)
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/webhooks", methods=["GET"])
    @limiter.limit("30 per minute")
    def api_list_webhooks():
        try:
            webhooks = list_webhooks()
            return jsonify({"webhooks": webhooks})
        except Exception as e:
            logger.error("Error listing webhooks", error=e)
            return jsonify({"error": str(e)}), 500
    
    print("* Webhook service registered")
except ImportError:
    print("* Webhook service not available (install requests package)")



@app.route("/api/reconciliations/<int:reconciliation_id>/manual-match", methods=["POST"])
@limiter.limit(RATE_LIMITS["/api/reconciliations/<int:reconciliation_id>/manual-match"])
def api_manual_match(reconciliation_id: int):
    """
    Manually match an invoice item with a bank item.
    Moves items from 'unmatched' lists to 'matches' list.
    """
    try:
        data = request.get_json()
        if not data:
             return jsonify({"error": "No data provided"}), 400
             
        invoice_index = data.get("invoice_index")
        bank_index = data.get("bank_index")
        
        # Verify indices are integers
        if not isinstance(invoice_index, int) or not isinstance(bank_index, int):
            return jsonify({"error": "Invalid indices"}), 400

        # 1. Fetch reconciliation raw_json
        rows = db_manager.execute_query(
            "SELECT id, raw_json FROM reconciliations WHERE id = ?",
            (reconciliation_id,)
        )
        
        # Fallback for MySQL syntax
        if not rows and db_manager.db_type == "mysql":
             rows = db_manager.execute_query(
                "SELECT id, raw_json FROM reconciliations WHERE id = %s",
                (reconciliation_id,)
            )
            
        if not rows:
            return jsonify({"error": "Reconciliation not found"}), 404
        
        row = rows[0]
        # Handle dict or tuple row
        raw_json_str = row["raw_json"] if isinstance(row, dict) else row[1]
        
        if not raw_json_str:
            return jsonify({"error": "Reconciliation data not available"}), 500
            
        try:
            recon_data = json.loads(raw_json_str)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid reconciliation data"}), 500
            
        results = recon_data.get("results", {})
        only_in_invoices = results.get("only_in_invoices", [])
        only_in_bank = results.get("only_in_bank", [])
        matches = results.get("matches", [])
        
        # 2. Validate indices
        if invoice_index < 0 or invoice_index >= len(only_in_invoices):
            return jsonify({"error": "Invoice index out of bounds"}), 400
        if bank_index < 0 or bank_index >= len(only_in_bank):
            return jsonify({"error": "Bank index out of bounds"}), 400
            
        invoice_item = only_in_invoices[invoice_index]
        bank_item = only_in_bank[bank_index]
        
        # 3. Create match object
        match_obj = {
            "invoice": invoice_item,
            "bank": bank_item,
            "match_score": 1.0,
            "is_manual_match": True,
            "timestamp": datetime.now().isoformat()
        }
        
        # 4. Update lists (append match, remove from unmatched)
        matches.append(match_obj)
        
        # Helper to remove item at index
        new_only_in_invoices = [item for i, item in enumerate(only_in_invoices) if i != invoice_index]
        new_only_in_bank = [item for i, item in enumerate(only_in_bank) if i != bank_index]
        
        # Update recon_data structure
        recon_data["results"]["matches"] = matches
        recon_data["results"]["only_in_invoices"] = new_only_in_invoices
        recon_data["results"]["only_in_bank"] = new_only_in_bank
        
        # Update summary stats
        summary = recon_data["results"].get("summary", {})
        summary["total_matches"] = len(matches)
        summary["total_unmatched_invoices"] = len(new_only_in_invoices)
        summary["total_unmatched_bank"] = len(new_only_in_bank)
        recon_data["results"]["summary"] = summary
        
        # 5. Insert into reconciliation_matches table
        inv_id = invoice_item.get("id") or invoice_item.get("invoice_id")
        bank_id = bank_item.get("id") or bank_item.get("transaction_id")
        
        # Normalize IDs
        try:
             if inv_id and str(inv_id).isdigit(): inv_id = int(inv_id)
             else: inv_id = None
        except: inv_id = None
        
        try:
             if bank_id and str(bank_id).isdigit(): bank_id = int(bank_id)
             else: bank_id = None
        except: bank_id = None

        match_data_json = json.dumps(match_obj, ensure_ascii=False, default=str)
        
        insert_sql = """
            INSERT INTO reconciliation_matches (
                reconciliation_id, invoice_id, transaction_id, match_score, is_manual_match, match_data
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (reconciliation_id, inv_id, bank_id, 1.0, 1, match_data_json)
        
        try:
             db_manager.execute_insert(insert_sql, params)
        except Exception:
             # Try MySQL syntax
             insert_sql_mysql = """
                INSERT INTO reconciliation_matches (
                    reconciliation_id, invoice_id, transaction_id, match_score, is_manual_match, match_data
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """
             db_manager.execute_insert(insert_sql_mysql, params)

        # 6. Save update to reconciliations table
        new_raw_json = json.dumps(recon_data, ensure_ascii=False, default=str)
        update_sql = "UPDATE reconciliations SET raw_json = ?, total_matches = COALESCE(total_matches, 0) + 1 WHERE id = ?"
        
        try:
            db_manager.execute_update(update_sql, (new_raw_json, reconciliation_id))
        except Exception:
            update_sql_mysql = "UPDATE reconciliations SET raw_json = %s, total_matches = COALESCE(total_matches, 0) + 1 WHERE id = %s"
            db_manager.execute_update(update_sql_mysql, (new_raw_json, reconciliation_id))

        return jsonify({"success": True})
            
    except Exception as e:
        logger.error(f"Error in manual match: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()

    # Debug flag should be controlled via environment:
    #   FLASK_DEBUG=1  -> debug mode ON
    #   FLASK_DEBUG=0  -> debug mode OFF (recommended for production)
    debug_flag = os.environ.get("FLASK_DEBUG", "1") == "1"

    # Port should be controlled via environment:
    #   PORT=5001 (default)
    # Some environments block binding to certain ports (WinError 10013).
    # If binding fails, try a small set of fallback ports.
    try:
        base_port = int(os.environ.get("PORT", "5001"))
    except Exception:
        base_port = 5001

    candidate_ports = [base_port]
    for p in (5002, 5003, 5050, 8000, 8080):
        if p not in candidate_ports:
            candidate_ports.append(p)

    # Probe ports first. This avoids Flask's debug reloader interfering with our
    # fallback logic and gives a clearer error when a port is blocked.
    import socket

    def _can_bind(host: str, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False
        finally:
            try:
                s.close()
            except Exception:
                pass

    host = "127.0.0.1"
    chosen_port = None
    for port in candidate_ports:
        if _can_bind(host, port):
            chosen_port = port
            break

    if chosen_port is None:
        raise OSError(f"No available port found in {candidate_ports}")

    print(f"\nStarting server on http://{host}:{chosen_port} (debug={debug_flag})\n")
    # Disable reloader so we don't lose control of exceptions / process flow.
    app.run(host=host, port=chosen_port, debug=debug_flag, use_reloader=False)

