"""
Monitoring and Observability
Prometheus metrics and monitoring setup
"""

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

import logging

logger = logging.getLogger(__name__)

if PROMETHEUS_AVAILABLE:
    # Define metrics
    request_count = Counter(
        'http_requests_total',
        'Total HTTP requests',
        ['method', 'endpoint', 'status']
    )
    
    request_duration = Histogram(
        'http_request_duration_seconds',
        'HTTP request duration in seconds',
        ['method', 'endpoint']
    )
    
    active_reconciliations = Gauge(
        'active_reconciliations',
        'Number of active reconciliations'
    )
    
    ocr_processing_time = Histogram(
        'ocr_processing_seconds',
        'OCR processing time in seconds',
        ['file_type', 'source']
    )
    
    reconciliation_matches = Counter(
        'reconciliation_matches_total',
        'Total reconciliation matches',
        ['reconciliation_id']
    )
    
    database_query_time = Histogram(
        'database_query_seconds',
        'Database query time in seconds',
        ['query_type']
    )


def register_monitoring_routes(app):
    """Register monitoring routes with Flask app"""
    if not PROMETHEUS_AVAILABLE:
        logger.warning("Prometheus not available. Monitoring routes not registered.")
        return
    
    @app.route('/metrics', methods=['GET'])
    def metrics():
        """Prometheus metrics endpoint"""
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
    
    logger.info("✓ Monitoring routes registered at /metrics")


def track_request(method: str, endpoint: str, status: int, duration: float):
    """Track HTTP request metrics"""
    if PROMETHEUS_AVAILABLE:
        request_count.labels(method=method, endpoint=endpoint, status=status).inc()
        request_duration.labels(method=method, endpoint=endpoint).observe(duration)


def track_ocr_processing(file_type: str, source: str, duration: float):
    """Track OCR processing metrics"""
    if PROMETHEUS_AVAILABLE:
        ocr_processing_time.labels(file_type=file_type, source=source).observe(duration)


def track_reconciliation_match(reconciliation_id: int):
    """Track reconciliation match"""
    if PROMETHEUS_AVAILABLE:
        reconciliation_matches.labels(reconciliation_id=str(reconciliation_id)).inc()


def set_active_reconciliations(count: int):
    """Set active reconciliations gauge"""
    if PROMETHEUS_AVAILABLE:
        active_reconciliations.set(count)


def track_database_query(query_type: str, duration: float):
    """Track database query metrics"""
    if PROMETHEUS_AVAILABLE:
        database_query_time.labels(query_type=query_type).observe(duration)

