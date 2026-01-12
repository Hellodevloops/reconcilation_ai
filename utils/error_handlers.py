"""
Enhanced Error Handling System
Provides user-friendly error messages and structured error responses
"""

from flask import jsonify
from typing import Dict, Any, Optional
import traceback
import logging

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception class for API errors"""
    status_code = 500
    message = "An error occurred"
    
    def __init__(self, message: Optional[str] = None, status_code: Optional[int] = None, 
                 error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.message = message or self.message
        self.status_code = status_code or self.status_code
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response"""
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "status_code": self.status_code,
            "details": self.details
        }


class ValidationError(APIError):
    """Validation error (400)"""
    status_code = 400
    message = "Validation error"


class NotFoundError(APIError):
    """Resource not found (404)"""
    status_code = 404
    message = "Resource not found"


class UnauthorizedError(APIError):
    """Unauthorized access (401)"""
    status_code = 401
    message = "Unauthorized access"


class ForbiddenError(APIError):
    """Forbidden access (403)"""
    status_code = 403
    message = "Forbidden access"


class ConflictError(APIError):
    """Resource conflict (409)"""
    status_code = 409
    message = "Resource conflict"


class RateLimitError(APIError):
    """Rate limit exceeded (429)"""
    status_code = 429
    message = "Rate limit exceeded"


class InternalServerError(APIError):
    """Internal server error (500)"""
    status_code = 500
    message = "Internal server error"


def register_error_handlers(app):
    """Register error handlers with Flask app"""
    
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        """Handle custom API errors"""
        logger.error(
            f"API Error: {error.error_code}",
            extra={
                "error_code": error.error_code,
                "message": error.message,
                "status_code": error.status_code,
                "details": error.details
            }
        )
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 errors"""
        return jsonify({
            "error": True,
            "error_code": "NOT_FOUND",
            "message": "The requested resource was not found",
            "status_code": 404
        }), 404
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """Handle 405 errors"""
        return jsonify({
            "error": True,
            "error_code": "METHOD_NOT_ALLOWED",
            "message": "The requested method is not allowed for this endpoint",
            "status_code": 405
        }), 405
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal server error: {str(error)}", exc_info=True)
        return jsonify({
            "error": True,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred",
            "status_code": 500
        }), 500
    
    @app.errorhandler(Exception)
    def handle_generic_exception(error: Exception):
        """Handle all other exceptions"""
        logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
        return jsonify({
            "error": True,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "status_code": 500,
            "details": {
                "exception_type": type(error).__name__
            }
        }), 500

