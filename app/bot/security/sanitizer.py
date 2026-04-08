#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Input Sanitization Module
Prevents XSS, SQL injection, and other security issues
"""

import re
import html
from typing import Any, Optional
import logging


class InputSanitizer:
    """
    Comprehensive input sanitization for security
    """
    
    # Dangerous patterns
    SQL_INJECTION_PATTERNS = [
        r"(\bunion\b.*\bselect\b)",
        r"(\bselect\b.*\bfrom\b)",
        r"(\binsert\b.*\binto\b)",
        r"(\bupdate\b.*\bset\b)",
        r"(\bdelete\b.*\bfrom\b)",
        r"(\bdrop\b.*\btable\b)",
        r"(;.*--)",
        r"(\/\*.*\*\/)",
    ]
    
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
        r"onclick\s*=",
        r"<iframe[^>]*>",
    ]
    
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\./\.\./",
        r"\.\./\.\./\.\./",
        r"\.\.\\",
    ]
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """
        Escape HTML to prevent XSS
        
        Args:
            text: Input text
            
        Returns:
            HTML-escaped text
        """
        if not text:
            return ""
        return html.escape(str(text))
    
    @staticmethod
    def sanitize_sql(text: str) -> str:
        """
        Basic SQL injection sanitization
        Note: Always use parameterized queries as primary defense
        
        Args:
            text: Input text
            
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # This is NOT asubstitute for parameterized queries!
        # Just an additional layer
        sanitized = str(text)
        
        # Remove common SQL injection patterns
        for pattern in InputSanitizer.SQL_INJECTION_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                logging.warning(f"Potential SQL injection detected: {pattern}")
                sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @staticmethod
    def detect_xss(text: str) -> bool:
        """
        Detect potential XSS attacks
        
        Args:
            text: Input text
            
        Returns:
            True if XSS detected
        """
        if not text:
            return False
        
        text_lower = str(text).lower()
        
        for pattern in InputSanitizer.XSS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logging.warning(f"Potential XSS detected: {pattern}")
                return True
        
        return False
    
    @staticmethod
    def sanitize_path(path: str) -> str:
        """
        Prevent path traversal attacks
        
        Args:
            path: File path
            
        Returns:
            Sanitized path
        """
        if not path:
            return ""
        
        sanitized = str(path)
        
        # Remove path traversal attempts
        for pattern in InputSanitizer.PATH_TRAVERSAL_PATTERNS:
            sanitized = re.sub(pattern, "", sanitized)
        
        # Remove leading/trailing slashes
        sanitized = sanitized.strip("/\\")
        
        return sanitized
    
    @staticmethod
    def sanitize_user_input(text: str, max_length: int = 10000) -> str:
        """
        General purpose user input sanitization
        
        Args:
            text: User input
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # Truncate
        sanitized = str(text)[:max_length]
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())
        
        # HTML escape for safety
        sanitized = html.escape(sanitized)
        
        return sanitized.strip()
    
    @staticmethod
    def sanitize_email(email: str) -> Optional[str]:
        """
        Sanitize and validate email
        
        Args:
            email: Email address
            
        Returns:
            Sanitized email or None if invalid
        """
        if not email:
            return None
        
        # Basic sanitization
        email = str(email).strip().lower()
        
        # Validate format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            logging.warning(f"Invalid email format: {email}")
            return None
        
        # Check for suspicious patterns
        if InputSanitizer.detect_xss(email):
            logging.error(f"XSS attempt in email: {email}")
            return None
        
        return email
    
    @staticmethod
    def sanitize_phone(phone: str) -> str:
        """
        Sanitize phone number (keep only digits and +)
        
        Args:
            phone: Phone number
            
        Returns:
            Sanitized phone
        """
        if not phone:
            return ""
        
        # Keep only digits, +, -, (, )
        sanitized = re.sub(r'[^\d+\-()]', '', str(phone))
        
        return sanitized
    
    @staticmethod
    def sanitize_dict(data: dict, max_depth: int = 5) -> dict:
        """
        Recursively sanitize all string values in a dictionary
        
        Args:
            data: Dictionary to sanitize
            max_depth: Maximum recursion depth
            
        Returns:
            Sanitized dictionary
        """
        if max_depth <= 0:
            return data
        
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = InputSanitizer.sanitize_user_input(value)
            elif isinstance(value, dict):
                result[key] = InputSanitizer.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                result[key] = [
                    InputSanitizer.sanitize_user_input(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        
        return result


def sanitize_input(value: Any) -> Any:
    """
    Convenience function for quick sanitization
    
    Args:
        value: Input value
        
    Returns:
        Sanitized value
    """
    if isinstance(value, str):
        return InputSanitizer.sanitize_user_input(value)
    elif isinstance(value, dict):
        return InputSanitizer.sanitize_dict(value)
    else:
        return value
