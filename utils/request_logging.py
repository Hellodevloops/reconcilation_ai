"""
Request Logging Middleware
Logs all API requests with performance tracking
"""

import time
import logging
from functools import wraps
from flask import request, g
from typing import Callable, Any

logger = logging.getLogger(__name__)


def log_request_info():
    """Log incoming request information"""
    g.start_time = time.time()
    
    logger.info(
        "Request received",
        extra={
            "method": request.method,
            "path": request.path,
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
            "content_type": request.content_type,
            "content_length": request.content_length
        }
    )


def log_response_info(response):
    """Log response information and performance metrics"""
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "remote_addr": request.remote_addr
            }
        )
        
        # Add performance header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    return response


def log_request_decorator(func: Callable) -> Callable:
    """Decorator to log request/response for specific endpoints"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        # Log request
        logger.info(
            f"Endpoint called: {func.__name__}",
            extra={
                "endpoint": request.path,
                "method": request.method,
                "args": dict(kwargs)
            }
        )
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log successful response
            logger.info(
                f"Endpoint completed: {func.__name__}",
                extra={
                    "endpoint": request.path,
                    "duration_ms": round(duration * 1000, 2),
                    "status": "success"
                }
            )
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            
            # Log error
            logger.error(
                f"Endpoint error: {func.__name__}",
                extra={
                    "endpoint": request.path,
                    "duration_ms": round(duration * 1000, 2),
                    "error": str(e),
                    "status": "error"
                },
                exc_info=True
            )
            raise
    
    return wrapper


def register_request_logging(app):
    """Register request logging middleware with Flask app"""
    app.before_request(log_request_info)
    app.after_request(log_response_info)

