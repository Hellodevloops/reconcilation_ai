"""
Configuration Management
Centralized configuration for the application
"""

import os
from dotenv import load_dotenv

load_dotenv()

# === Tesseract OCR Configuration ===
TESSERACT_CMD = os.environ.get("TESSERACT_CMD")

# === Database Configuration ===
DB_TYPE = os.environ.get("DB_TYPE", "mysql")  # mysql or sqlite

# MySQL Configuration
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "reconciliation")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))

# SQLite Configuration (fallback)
DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "reconcile.db")
)

# Database connection string
def get_database_url():
    """Get database connection URL based on DB_TYPE"""
    if DB_TYPE == "mysql":
        return f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    else:
        return f"sqlite:///{DB_PATH}"

# === File Storage Configuration ===
UPLOAD_FOLDER = os.environ.get(
    "UPLOAD_FOLDER",
    os.path.join(os.path.dirname(__file__), "uploads")
)
INVOICE_FOLDER = os.environ.get(
    "INVOICE_FOLDER", 
    os.path.join(UPLOAD_FOLDER, "invoices")
)

# === File Upload Limits ===
MAX_INVOICE_FILES = int(os.environ.get("MAX_INVOICE_FILES", "10"))
MAX_BANK_FILES = int(os.environ.get("MAX_BANK_FILES", "10"))

# === Rate Limiting ===
DEFAULT_RATE_LIMIT = os.environ.get("RATE_LIMIT", "30 per minute")

RATE_LIMITS = {
    "/api/reconcile": "10 per minute",
    "/api/reconciliations": "60 per minute",
    "/api/reconciliations/<int:reconciliation_id>/matches": "60 per minute",
    "/api/reconciliations/<int:reconciliation_id>": "30 per minute",
}

# === Excel/CSV Limits ===
MAX_EXCEL_ROWS = int(os.environ.get("MAX_EXCEL_ROWS", "50000"))
MAX_CSV_ROWS = int(os.environ.get("MAX_CSV_ROWS", "50000"))

# === File Size Limits ===
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "100"))  # 100 MB default
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

MAX_TOTAL_SIZE_MB = int(os.environ.get("MAX_TOTAL_SIZE_MB", "500"))  # 500 MB default
MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024

# === Memory Limits ===
MAX_MEMORY_USAGE_MB = int(os.environ.get("MAX_MEMORY_USAGE_MB", "2000"))  # 2 GB default

# === Caching Configuration ===
ENABLE_CACHING = os.environ.get("ENABLE_CACHING", "1") == "1"
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))  # 5 minutes default

# === Transaction Processing ===
MIN_TRANSACTION_AMOUNT = 1.0

# === Bank Statement Keywords ===
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

TIDE_TRANSACTION_KEYWORDS = [
    "domestic transfer",
    "card transaction",
    "direct debit",
    "internal book transfer",
]

# === File Type Validation ===
INVOICE_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".xlsx", ".xls"}
BANK_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}

INVOICE_ALLOWED_MIMETYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

BANK_ALLOWED_MIMETYPES = INVOICE_ALLOWED_MIMETYPES.union({
    "text/csv",
    "application/csv",
})

# === Security Configuration ===
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
CORS_ENABLED = os.environ.get("CORS_ENABLED", "1") == "1"

# === ML Model Configuration ===
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

# === Auto-Training Configuration ===
AUTO_TRAIN_MIN_NEW_MATCHES = int(os.environ.get("AUTO_TRAIN_MIN_NEW_MATCHES", "50"))
AUTO_TRAIN_MIN_INTERVAL_SECONDS = int(os.environ.get("AUTO_TRAIN_MIN_INTERVAL_SECONDS", "900"))  # 15 minutes
AUTO_TRAIN_ENABLED = os.environ.get("AUTO_TRAIN_ENABLED", "1") == "1"

# === Currency Configuration ===
ENABLE_CURRENCY_CONVERSION = os.environ.get("ENABLE_CURRENCY_CONVERSION", "0") == "1"

# === Manual Match Configuration ===
MANUAL_MATCH_WARNING_THRESHOLDS = {
    "amount_diff_percent": 5.0,  # 5% difference
    "date_diff_days": 30,  # 30 days difference
    "description_similarity": 0.5,  # 50% similarity
}

# === Deduplication Configuration ===
ENABLE_DEDUPLICATION = os.environ.get("ENABLE_DEDUPLICATION", "1") == "1"
DEDUP_AMOUNT_TOLERANCE = float(os.environ.get("DEDUP_AMOUNT_TOLERANCE", "0.01"))  # 1 cent
DEDUP_DESC_SIMILARITY = float(os.environ.get("DEDUP_DESC_SIMILARITY", "0.95"))  # 95% similar
DEDUP_DATE_TOLERANCE_DAYS = int(os.environ.get("DEDUP_DATE_TOLERANCE_DAYS", "0"))  # Same day

# === Flask Configuration ===
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5001"))

# === Redis Configuration (for Celery) ===
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# === Pagination Defaults ===
DEFAULT_PAGE_SIZE = int(os.environ.get("DEFAULT_PAGE_SIZE", "50"))
MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", "1000"))

