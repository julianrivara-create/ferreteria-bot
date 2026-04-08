#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Monitoring Setup - Sentry Integration
Provides error tracking, performance monitoring, and release tracking
"""

import logging
import os
from typing import Optional, Dict, Any
from functools import wraps


class SentryMonitoring:
    """
    Sentry monitoring wrapper with graceful degradation
    """
    
    def __init__(self):
        self.enabled = False
        self.sentry_sdk = None
        self._init_sentry()
    
    def _init_sentry(self) -> None:
        """
        Initialize Sentry SDK if DSN is configured
        """
        sentry_dsn = os.getenv('SENTRY_DSN')
        environment = os.getenv('ENVIRONMENT', 'development')
        
        if not sentry_dsn:
            logging.info("Sentry DSN not configured - monitoring disabled")
            return
        
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
            
            # Configure logging integration
            sentry_logging = LoggingIntegration(
                level=logging.INFO,  # Capture info and above as breadcrumbs
                event_level=logging.ERROR  # Send errors as events
            )
            
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=environment,
                
                # Performance monitoring
                traces_sample_rate=0.1 if environment == 'production' else 1.0,
                
                # Release tracking
                release=os.getenv('RELEASE_VERSION', '1.0.0'),
                
                # Integrations
                integrations=[sentry_logging],
                
                # Send PII (set to False for GDPR compliance)
                send_default_pii=False,
                
                # Performance
                max_breadcrumbs=50,
                
                # Filter sensitive data
                before_send=self._filter_sensitive_data
            )
            
            self.sentry_sdk = sentry_sdk
            self.enabled = True
            logging.info(f"✅ Sentry monitoring enabled (environment: {environment})")
            
        except ImportError:
            logging.warning("sentry-sdk not installed - monitoring disabled. Install with: pip install sentry-sdk")
        except Exception as e:
            logging.error(f"Failed to initialize Sentry: {e}")
    
    def _filter_sensitive_data(self, event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Filter sensitive data before sending to Sentry
        """
        # Remove PII from request data
        if 'request' in event:
            if 'data' in event['request']:
                data = event['request']['data']
                if isinstance(data, dict):
                    # Mask sensitive fields
                    for field in ['email', 'phone', 'dni', 'password', 'token', 'api_key']:
                        if field in data:
                            data[field] = '[FILTERED]'
        
        return event
    
    def capture_exception(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Capture an exception with optional context
        
        Args:
            error: Exception to capture
            context: Additional context (user_id, session_id, etc.)
        """
        if not self.enabled:
            logging.error(f"Exception: {error}", exc_info=True)
            return
        
        try:
            if context:
                self.sentry_sdk.set_context("custom", context)
            
            self.sentry_sdk.capture_exception(error)
            logging.error(f"Exception sent to Sentry: {error}")
        except Exception as e:
            logging.error(f"Failed to send exception to Sentry: {e}")
    
    def capture_message(self, message: str, level: str = 'info', context: Optional[Dict[str, Any]] = None) -> None:
        """
        Capture a message
        
        Args:
            message: Message to capture
            level: Severity level ('debug', 'info', 'warning', 'error', 'fatal')
            context: Additional context
        """
        if not self.enabled:
            log_func = getattr(logging, level, logging.info)
            log_func(message)
            return
        
        try:
            if context:
                self.sentry_sdk.set_context("custom", context)
            
            self.sentry_sdk.capture_message(message, level=level)
        except Exception as e:
            logging.error(f"Failed to send message to Sentry: {e}")
    
    def set_user(self, user_id: str, email: Optional[str] = None, username: Optional[str] = None) -> None:
        """
        Set user context for tracking
        
        Args:
            user_id: User ID (anonymized if needed)
            email: User email (will be filtered if send_default_pii=False)
            username: Username
        """
        if not self.enabled:
            return
        
        try:
            self.sentry_sdk.set_user({
                "id": user_id,
                "email": email,
                "username": username
            })
        except Exception as e:
            logging.error(f"Failed to set user context: {e}")
    
    def start_transaction(self, operation: str, name: str) -> Any:
        """
        Start a performance transaction
        
        Args:
            operation: Operation type (e.g., 'http.server', 'db.query')
            name: Transaction name
            
        Returns:
            Transaction object or None
        """
        if not self.enabled:
            return None
        
        try:
            return self.sentry_sdk.start_transaction(op=operation, name=name)
        except Exception as e:
            logging.error(f"Failed to start transaction: {e}")
            return None
    
    def add_breadcrumb(self, message: str, category: str = "default", level: str = "info", data: Optional[Dict] = None) -> None:
        """
        Add a breadcrumb for context
        
        Args:
            message: Breadcrumb message
            category: Category (e.g., 'auth', 'navigation', 'api')
            level: Severity level
            data: Additional data
        """
        if not self.enabled:
            return
        
        try:
            self.sentry_sdk.add_breadcrumb(
                message=message,
                category=category,
                level=level,
                data=data or {}
            )
        except Exception as e:
            logging.error(f"Failed to add breadcrumb: {e}")


# Global monitoring instance
_monitoring = None


def get_monitoring() -> SentryMonitoring:
    """Get or create global monitoring instance"""
    global _monitoring
    if _monitoring is None:
        _monitoring = SentryMonitoring()
    return _monitoring


def track_errors(func):
    """
    Decorator to automatically track errors in functions
    
    Usage:
        @track_errors
        def my_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            monitoring = get_monitoring()
            monitoring.capture_exception(e, context={
                'function': func.__name__,
                'args': str(args)[:100],  # Truncate to avoid huge payloads
            })
            raise
    return wrapper


def track_performance(operation: str):
    """
    Decorator to track function performance
    
    Usage:
        @track_performance('api.call')
        def my_api_call():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            monitoring = get_monitoring()
            transaction = monitoring.start_transaction(
                operation=operation,
                name=f"{func.__module__}.{func.__name__}"
            )
            
            try:
                result = func(*args, **kwargs)
                if transaction:
                    transaction.set_status("ok")
                return result
            except Exception as e:
                if transaction:
                    transaction.set_status("internal_error")
                raise
            finally:
                if transaction:
                    transaction.finish()
        
        return wrapper
    return decorator


# Health check endpoint helper
def get_health_status() -> Dict[str, Any]:
    """
    Get application health status for monitoring
    
    Returns:
        Health status dict
    """
    return {
        "status": "healthy",
        "monitoring": {
            "sentry_enabled": get_monitoring().enabled
        },
        "version": os.getenv('RELEASE_VERSION', '1.0.0'),
        "environment": os.getenv('ENVIRONMENT', 'development')
    }
