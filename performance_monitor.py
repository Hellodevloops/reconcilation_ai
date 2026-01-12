"""
Step 11: Performance Monitoring and Metrics Collection

Features:
- Track API response times
- Monitor reconciliation performance
- Collect system metrics
- Performance dashboard data
"""

import time
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import os

from app import DB_PATH


METRICS_DB_PATH = os.path.join(os.path.dirname(__file__), "performance_metrics.db")


def init_metrics_db():
    """Initialize metrics database."""
    conn = sqlite3.connect(METRICS_DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            response_time_ms REAL NOT NULL,
            status_code INTEGER,
            request_size_bytes INTEGER,
            response_size_bytes INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_count INTEGER NOT NULL,
            bank_count INTEGER NOT NULL,
            match_count INTEGER NOT NULL,
            processing_time_seconds REAL NOT NULL,
            ocr_time_seconds REAL,
            reconciliation_time_seconds REAL,
            total_time_seconds REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp ON api_metrics(timestamp);
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_reconciliation_metrics_timestamp ON reconciliation_metrics(timestamp);
    """)
    
    conn.commit()
    conn.close()


def record_api_metric(
    endpoint: str,
    method: str,
    response_time_ms: float,
    status_code: int,
    request_size_bytes: int = 0,
    response_size_bytes: int = 0
):
    """Record an API call metric."""
    init_metrics_db()
    
    conn = sqlite3.connect(METRICS_DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO api_metrics 
        (endpoint, method, response_time_ms, status_code, request_size_bytes, response_size_bytes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (endpoint, method, response_time_ms, status_code, request_size_bytes, response_size_bytes))
    
    conn.commit()
    conn.close()


def record_reconciliation_metric(
    invoice_count: int,
    bank_count: int,
    match_count: int,
    processing_time_seconds: float,
    ocr_time_seconds: Optional[float] = None,
    reconciliation_time_seconds: Optional[float] = None,
    total_time_seconds: float = 0
):
    """Record a reconciliation performance metric."""
    init_metrics_db()
    
    conn = sqlite3.connect(METRICS_DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO reconciliation_metrics
        (invoice_count, bank_count, match_count, processing_time_seconds, 
         ocr_time_seconds, reconciliation_time_seconds, total_time_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (invoice_count, bank_count, match_count, processing_time_seconds,
          ocr_time_seconds, reconciliation_time_seconds, total_time_seconds))
    
    conn.commit()
    conn.close()


def get_api_metrics(hours: int = 24) -> Dict[str, Any]:
    """Get API performance metrics for the last N hours."""
    init_metrics_db()
    
    conn = sqlite3.connect(METRICS_DB_PATH)
    cur = conn.cursor()
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # Get overall stats
    cur.execute("""
        SELECT 
            COUNT(*) as total_requests,
            AVG(response_time_ms) as avg_response_time,
            MIN(response_time_ms) as min_response_time,
            MAX(response_time_ms) as max_response_time,
            AVG(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) * 100 as error_rate
        FROM api_metrics
        WHERE timestamp >= ?
    """, (cutoff_time.isoformat(),))
    
    row = cur.fetchone()
    overall_stats = {
        "total_requests": row[0] or 0,
        "avg_response_time_ms": round(row[1] or 0, 2),
        "min_response_time_ms": round(row[2] or 0, 2),
        "max_response_time_ms": round(row[3] or 0, 2),
        "error_rate_percent": round(row[4] or 0, 2)
    }
    
    # Get per-endpoint stats
    cur.execute("""
        SELECT 
            endpoint,
            method,
            COUNT(*) as count,
            AVG(response_time_ms) as avg_time,
            AVG(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) * 100 as error_rate
        FROM api_metrics
        WHERE timestamp >= ?
        GROUP BY endpoint, method
        ORDER BY count DESC
    """, (cutoff_time.isoformat(),))
    
    endpoint_stats = []
    for row in cur.fetchall():
        endpoint_stats.append({
            "endpoint": row[0],
            "method": row[1],
            "count": row[2],
            "avg_response_time_ms": round(row[3] or 0, 2),
            "error_rate_percent": round(row[4] or 0, 2)
        })
    
    conn.close()
    
    return {
        "period_hours": hours,
        "overall": overall_stats,
        "by_endpoint": endpoint_stats
    }


def get_reconciliation_metrics(hours: int = 24) -> Dict[str, Any]:
    """Get reconciliation performance metrics for the last N hours."""
    init_metrics_db()
    
    conn = sqlite3.connect(METRICS_DB_PATH)
    cur = conn.cursor()
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    cur.execute("""
        SELECT 
            COUNT(*) as total_reconciliations,
            AVG(invoice_count) as avg_invoices,
            AVG(bank_count) as avg_bank_transactions,
            AVG(match_count) as avg_matches,
            AVG(total_time_seconds) as avg_total_time,
            AVG(ocr_time_seconds) as avg_ocr_time,
            AVG(reconciliation_time_seconds) as avg_reconciliation_time,
            MIN(total_time_seconds) as min_time,
            MAX(total_time_seconds) as max_time
        FROM reconciliation_metrics
        WHERE timestamp >= ?
    """, (cutoff_time.isoformat(),))
    
    row = cur.fetchone()
    
    metrics = {
        "period_hours": hours,
        "total_reconciliations": row[0] or 0,
        "avg_invoices": round(row[1] or 0, 2),
        "avg_bank_transactions": round(row[2] or 0, 2),
        "avg_matches": round(row[3] or 0, 2),
        "avg_total_time_seconds": round(row[4] or 0, 2),
        "avg_ocr_time_seconds": round(row[5] or 0, 2) if row[5] else None,
        "avg_reconciliation_time_seconds": round(row[6] or 0, 2) if row[6] else None,
        "min_time_seconds": round(row[7] or 0, 2),
        "max_time_seconds": round(row[8] or 0, 2)
    }
    
    conn.close()
    return metrics


def get_performance_summary() -> Dict[str, Any]:
    """Get overall performance summary."""
    api_metrics = get_api_metrics(24)
    recon_metrics = get_reconciliation_metrics(24)
    
    return {
        "api_performance": api_metrics,
        "reconciliation_performance": recon_metrics,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python performance_monitor.py summary        - Show performance summary")
        print("  python performance_monitor.py api [hours]   - Show API metrics (default 24 hours)")
        print("  python performance_monitor.py recon [hours]  - Show reconciliation metrics (default 24 hours)")
        sys.exit(1)
    
    command = sys.argv[1]
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    
    if command == "summary":
        summary = get_performance_summary()
        print(json.dumps(summary, indent=2))
    
    elif command == "api":
        metrics = get_api_metrics(hours)
        print(json.dumps(metrics, indent=2))
    
    elif command == "recon":
        metrics = get_reconciliation_metrics(hours)
        print(json.dumps(metrics, indent=2))
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


