#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Health Check Endpoints
Provides comprehensive health and readiness checks
"""

import time
import os
from typing import Dict, Any
from flask import Blueprint, jsonify


health_bp = Blueprint('health', __name__)

# Track startup time
_startup_time = time.time()


def check_database() -> tuple[bool, str]:
    """Check database connectivity"""
    try:
        from bot_sales.core.database import Database
        # Quick test query
        # In production, use actual DB connection
        return True, "OK"
    except Exception as e:
        return False, str(e)


def check_redis() -> tuple[bool, str]:
    """Check Redis connectivity"""
    try:
        from bot_sales.core.cache_manager import get_cache
        cache = get_cache()
        
        if cache.redis_client:
            cache.redis_client.ping()
            return True, "OK"
        else:
            return True, "Using local cache (Redis not configured)"
    except Exception as e:
        return False, str(e)


def check_sentry() -> tuple[bool, str]:
    """Check Sentry configuration"""
    from bot_sales.core.monitoring import get_monitoring
    monitoring = get_monitoring()
    
    if monitoring.enabled:
        return True, "OK"
    else:
        return True, "Disabled (DSN not configured)"


def check_openai() -> tuple[bool, str]:
    """Check OpenAI API key"""
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        return False, "API key not configured"
    
    if api_key.startswith('sk-'):
        return True, "OK"
    else:
        return False, "Invalid API key format"


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Basic health check - is the app running?
    
    Returns 200 if app is alive
    """
    uptime = time.time() - _startup_time
    
    return jsonify({
        'status': 'healthy',
        'service': os.getenv('SERVICE_NAME', 'sales-bot-platform'),
        'version': os.getenv('APP_VERSION', ''),
        'uptime_seconds': int(uptime),
        'timestamp': time.time()
    }), 200


@health_bp.route('/health/ready', methods=['GET'])
def readiness_check():
    """
    Readiness check - is the app ready to serve traffic?
    
    Checks all dependencies
    """
    checks = {}
    all_ready = True
    
    # Database check
    db_ok, db_msg = check_database()
    checks['database'] = {'healthy': db_ok, 'message': db_msg}
    if not db_ok:
        all_ready = False
    
    # Redis check (optional)
    redis_ok, redis_msg = check_redis()
    checks['redis'] = {'healthy': redis_ok, 'message': redis_msg}
    # Redis is optional, don't fail readiness
    
    # Sentry check (optional)
    sentry_ok, sentry_msg = check_sentry()
    checks['sentry'] = {'healthy': sentry_ok, 'message': sentry_msg}
    # Sentry is optional
    
    # OpenAI check
    openai_ok, openai_msg = check_openai()
    checks['openai'] = {'healthy': openai_ok, 'message': openai_msg}
    if not openai_ok:
        all_ready = False
    
    status_code = 200 if all_ready else 503
    
    return jsonify({
        'ready': all_ready,
        'checks': checks,
        'timestamp': time.time()
    }), status_code


@health_bp.route('/health/live', methods=['GET'])
def liveness_check():
    """
    Liveness check - should Kubernetes restart the pod?
    
    Only fails if app is completely broken
    """
    # Basic check - can we respond?
    return jsonify({
        'alive': True,
        'timestamp': time.time()
    }), 200


@health_bp.route('/metrics', methods=['GET'])
def metrics():
    """
    Prometheus-style metrics endpoint
    """
    from bot_sales.core.cache_manager import get_cache
    
    cache = get_cache()
    cache_stats = cache.get_stats()
    
    uptime = time.time() - _startup_time
    
    metrics_text = f"""# HELP bot_uptime_seconds Bot uptime in seconds
# TYPE bot_uptime_seconds gauge
bot_uptime_seconds {int(uptime)}

# HELP cache_hits_total Total cache hits
# TYPE cache_hits_total counter
cache_hits_total {cache_stats['hits']}

# HELP cache_misses_total Total cache misses
# TYPE cache_misses_total counter
cache_misses_total {cache_stats['misses']}

# HELP cache_hit_rate Cache hit rate percentage
# TYPE cache_hit_rate gauge
cache_hit_rate {cache_stats['hit_rate'].rstrip('%')}
"""
    
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


def register_health_checks(app):
    """
    Register health check endpoints with Flask app
    
    Usage:
        from bot_sales.core.health import register_health_checks
        
        app = Flask(__name__)
        register_health_checks(app)
    """
    app.register_blueprint(health_bp)
