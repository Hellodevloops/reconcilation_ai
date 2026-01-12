"""
Step 14: Security Enhancements and Input Sanitization

Features:
- Input sanitization utilities
- SQL injection prevention
- XSS prevention
- File validation enhancements
- Security headers
"""

import re
import html
from typing import Any, Optional
from pathlib import Path


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and other attacks.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed_file"
    
    # Remove path components
    filename = Path(filename).name
    
    # Remove dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:255-len(ext)-1] + '.' + ext if ext else name[:255]
    
    # Ensure it's not empty
    if not filename or filename.strip() == '':
        filename = "unnamed_file"
    
    return filename


def sanitize_text_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize text input to prevent XSS and other attacks.
    
    Args:
        text: Input text
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # HTML escape to prevent XSS
    text = html.escape(text)
    
    return text


def validate_sql_safe(value: Any) -> bool:
    """
    Check if a value is safe for SQL (parameterized queries should be used).
    This is a basic check - always use parameterized queries!
    
    Args:
        value: Value to check
        
    Returns:
        True if appears safe (but still use parameterized queries!)
    """
    if value is None:
        return True
    
    value_str = str(value)
    
    # Check for SQL injection patterns
    dangerous_patterns = [
        r"';?\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|EXEC|EXECUTE)",
        r"';?\s*--",
        r"';?\s*/\*",
        r"UNION\s+SELECT",
        r"OR\s+1\s*=\s*1",
        r"OR\s+'1'\s*=\s*'1'"
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, value_str, re.IGNORECASE):
            return False
    
    return True


def sanitize_json_input(data: Any) -> Any:
    """
    Recursively sanitize JSON data.
    
    Args:
        data: JSON data (dict, list, or primitive)
        
    Returns:
        Sanitized data
    """
    if isinstance(data, dict):
        return {k: sanitize_json_input(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json_input(item) for item in data]
    elif isinstance(data, str):
        return sanitize_text_input(data)
    else:
        return data


def validate_file_extension(filename: str, allowed_extensions: list) -> bool:
    """
    Validate file extension against allowed list.
    
    Args:
        filename: File name
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.png'])
        
    Returns:
        True if extension is allowed
    """
    if not filename:
        return False
    
    ext = Path(filename).suffix.lower()
    return ext in [e.lower() for e in allowed_extensions]


def validate_file_path(path: str, base_dir: str) -> bool:
    """
    Validate that a file path is within the base directory (prevent directory traversal).
    
    Args:
        path: File path to validate
        base_dir: Base directory
        
    Returns:
        True if path is safe
    """
    try:
        resolved_path = Path(path).resolve()
        base_path = Path(base_dir).resolve()
        return str(resolved_path).startswith(str(base_path))
    except:
        return False


def generate_security_headers() -> dict:
    """
    Generate security headers for HTTP responses.
    
    Returns:
        Dictionary of security headers
    """
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin"
    }


def is_safe_filename(filename: str) -> bool:
    """
    Check if filename is safe (no directory traversal, no dangerous characters).
    
    Args:
        filename: Filename to check
        
    Returns:
        True if safe
    """
    if not filename:
        return False
    
    # Check for directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    
    # Check for dangerous characters
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*']
    if any(char in filename for char in dangerous_chars):
        return False
    
    # Check length
    if len(filename) > 255:
        return False
    
    return True


if __name__ == "__main__":
    # Test the security functions
    print("Testing security functions...")
    
    # Test filename sanitization
    test_filenames = [
        "../../etc/passwd",
        "file<script>.pdf",
        "normal_file.pdf",
        "file with spaces.pdf",
        "file" * 100 + ".pdf"
    ]
    
    print("\nFilename Sanitization:")
    for filename in test_filenames:
        sanitized = sanitize_filename(filename)
        print(f"  '{filename}' -> '{sanitized}'")
    
    # Test text sanitization
    test_texts = [
        "<script>alert('XSS')</script>",
        "Normal text",
        "Text with 'quotes' and \"double quotes\""
    ]
    
    print("\nText Sanitization:")
    for text in test_texts:
        sanitized = sanitize_text_input(text)
        print(f"  '{text}' -> '{sanitized}'")
    
    # Test SQL safety
    test_sql = [
        "normal_value",
        "'; DROP TABLE users; --",
        "OR 1=1"
    ]
    
    print("\nSQL Safety Check:")
    for sql in test_sql:
        safe = validate_sql_safe(sql)
        print(f"  '{sql}' -> Safe: {safe}")
    
    print("\n✓ Security function tests complete")


