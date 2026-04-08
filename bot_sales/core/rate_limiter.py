#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rate Limiting Module
Protects API from abuse with configurable limits
"""

import time
import logging
from typing import Dict, Optional
from functools import wraps
from flask import request, jsonify


class RateLimiter:
    """
    Simple in-memory rate limiter
    Production: Use Redis for distributed rate limiting
    """
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
        self.requests = {}  # {client_id: [(timestamp, count)]}
    
    def _get_client_id(self) -> str:
        """Get client identifier from request"""
        # Try user ID first
        if hasattr(request, 'user') and request.user:
            return f"user:{request.user.get('user_id', 'unknown')}"
        
        # Fallback to IP
        return f"ip:{request.remote_addr}"
    
    def _cleanup_old_requests(self, client_id: str) -> None:
        """Remove requests older than window"""
        if client_id not in self.requests:
            return
        
        current_time = time.time()
        cutoff_time = current_time - self.window_size
        
        self.requests[client_id] = [
            (ts, count) for ts, count in self.requests[client_id]
            if ts > cutoff_time
        ]
    
    def is_allowed(self, client_id: Optional[str] = None) -> tuple[bool, Dict]:
        """
        Check if request is allowed
        
        Returns:
            (is_allowed, info_dict)
        """
        if client_id is None:
            client_id = self._get_client_id()
        
        current_time = time.time()
        
        # Cleanup old requests
        self._cleanup_old_requests(client_id)
        
        # Count requests in window
        if client_id not in self.requests:
            self.requests[client_id] = []
        
        request_count = sum(count for _, count in self.requests[client_id])
        
        # Check limit
        if request_count >= self.requests_per_minute:
            # Calculate reset time
            oldest_request = self.requests[client_id][0][0] if self.requests[client_id] else current_time
            reset_time = oldest_request + self.window_size
            retry_after = int(reset_time - current_time)
            
            return False, {
                'limit': self.requests_per_minute,
                'remaining': 0,
                'reset': reset_time,
                'retry_after': retry_after
            }
        
        # Allow request
        self.requests[client_id].append((current_time, 1))
        
        return True, {
            'limit': self.requests_per_minute,
            'remaining': self.requests_per_minute - request_count - 1,
            'reset': current_time + self.window_size
        }


# Global rate limiter
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter"""
    global _rate_limiter
    if _rate_limiter is None:
        import os
        limit = int(os.getenv('RATE_LIMIT_PER_MINUTE', 60))
        _rate_limiter = RateLimiter(requests_per_minute=limit)
    return _rate_limiter


def rate_limit(requests_per_minute: Optional[int] = None):
    """
    Decorator for rate limiting Flask routes
    
    Usage:
        @app.route('/api/search')
        @rate_limit(30)  # 30 requests per minute
        def search():
            return results
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            
            # Override default limit if specified
            if requests_per_minute:
                limiter.requests_per_minute = requests_per_minute
            
            allowed, info = limiter.is_allowed()
            
            if not allowed:
                response = jsonify({
                    'error': 'Rate limit exceeded',
                    'retry_after': info['retry_after']
                })
                response.status_code = 429
                response.headers['X-RateLimit-Limit'] = str(info['limit'])
                response.headers['X-RateLimit-Remaining'] = '0'
                response.headers['X-RateLimit-Reset'] = str(int(info['reset']))
                response.headers['Retry-After'] = str(info['retry_after'])
                return response
            
            # Add rate limit headers
            response = func(*args, **kwargs)
            
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(info['limit'])
                response.headers['X-RateLimit-Remaining'] = str(info['remaining'])
                response.headers['X-RateLimit-Reset'] = str(int(info['reset']))
            
            return response
        
        return wrapper
    return decorator
