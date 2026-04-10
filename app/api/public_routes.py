
from collections import defaultdict, deque
from flask import Blueprint, request, jsonify, make_response
from app.db.session import SessionLocal
from app.db.models import Product
from app.services.bot_core import BotCore
from app.services.catalog_service import CatalogService
from app.core.config import get_settings

import structlog
import unicodedata
import re
import hmac
import math
import time
from threading import Lock

public_api = Blueprint('public_api', __name__)
logger = structlog.get_logger()
settings = get_settings()
_public_chat_rate_limiter = None
_public_chat_rate_limiter_guard = Lock()


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window limiter for public chat."""

    def __init__(self, requests_per_minute: int, window_seconds: int = 60):
        self.limit = max(1, int(requests_per_minute))
        self.window_seconds = window_seconds
        self._requests = defaultdict(deque)
        self._lock = Lock()

    def check(self, client_id: str, *, now: float | None = None) -> tuple[bool, dict]:
        current_time = time.time() if now is None else now
        cutoff = current_time - self.window_seconds

        with self._lock:
            bucket = self._requests[client_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.limit:
                reset = bucket[0] + self.window_seconds
                retry_after = max(1, math.ceil(reset - current_time))
                return False, {
                    "limit": self.limit,
                    "remaining": 0,
                    "reset": reset,
                    "retry_after": retry_after,
                }

            bucket.append(current_time)
            reset = bucket[0] + self.window_seconds
            return True, {
                "limit": self.limit,
                "remaining": max(0, self.limit - len(bucket)),
                "reset": reset,
                "retry_after": max(0, math.ceil(reset - current_time)),
            }


def _get_public_chat_rate_limiter() -> SlidingWindowRateLimiter:
    global _public_chat_rate_limiter
    limit = max(1, int(getattr(settings, "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", 60)))
    with _public_chat_rate_limiter_guard:
        if _public_chat_rate_limiter is None or _public_chat_rate_limiter.limit != limit:
            _public_chat_rate_limiter = SlidingWindowRateLimiter(limit)
        return _public_chat_rate_limiter


def _reset_public_chat_rate_limiter() -> None:
    global _public_chat_rate_limiter
    with _public_chat_rate_limiter_guard:
        _public_chat_rate_limiter = None


def _get_request_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return (request.headers.get("X-Real-IP") or request.remote_addr or "unknown").strip() or "unknown"


def _attach_public_chat_rate_limit_headers(response, info: dict):
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(max(0, info["remaining"]))
    response.headers["X-RateLimit-Reset"] = str(int(info["reset"]))
    response.headers["Retry-After"] = str(max(0, info["retry_after"]))
    return response


def _json_response(payload: dict, status: int, *, rate_limit_info: dict | None = None):
    response = make_response(jsonify(payload), status)
    if rate_limit_info is not None:
        _attach_public_chat_rate_limit_headers(response, rate_limit_info)
    return response


def _get_tenant_manager():
    from bot_sales.core.tenancy import tenant_manager

    return tenant_manager


def _resolve_runtime_tenant(tenant_ref: str):
    tenant_ref = (tenant_ref or "").strip()
    if not tenant_ref:
        return None

    manager = _get_tenant_manager()
    return manager.get_tenant(tenant_ref) or manager.get_tenant_by_slug(tenant_ref)


def _diag_authorized() -> bool:
    token = request.headers.get("X-Admin-Token") or ""
    if not settings.is_secret_configured(settings.ADMIN_TOKEN):
        logger.error("admin_token_not_configured")
        return False
    return hmac.compare_digest(token, settings.ADMIN_TOKEN)

@public_api.route('/stock/batch', methods=['POST'])
def get_stock_batch():
    """
    Robust batch endpoint:
    - Returns ALL requested SKUs (0 if missing)
    - Requires tenant_id to prevent cross-tenant data leaks.
    """
    data = request.get_json(silent=True) or {}
    skus = data.get('skus', [])
    tenant_id = (data.get('tenant_id') or request.headers.get('X-Tenant-Id') or "").strip()

    if not skus: return jsonify({}), 200
    if not tenant_id:
        return jsonify({"error": "Missing tenant_id"}), 400

    result = {sku: 0 for sku in skus} # Default 0
    session = SessionLocal()
    try:
        products = (
            session.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.sku.in_(skus))
            .all()
        )
        for p in products:
            result[p.sku] = p.available_qty
        return jsonify(result), 200
    except Exception as e:
        logger.error("batch_endpoint_error", error=str(e))
        return jsonify({"error": "batch_endpoint_error", "data": result}), 500
    finally:
        session.close()

@public_api.route('/chat', methods=['POST'])
def web_chat():
    """Tenant-aware web chat endpoint with legacy fallback."""
    import os
    data = request.json or {}
    user_message = data.get('message')
    allowed, rate_limit_info = _get_public_chat_rate_limiter().check(f"ip:{_get_request_ip()}")

    if not allowed:
        return _json_response(
            {
                "error": "Rate limit exceeded",
                "retry_after": rate_limit_info["retry_after"],
            },
            429,
            rate_limit_info=rate_limit_info,
        )

    # Require a stable per-visitor identifier — no shared anonymous sessions.
    user_id = (data.get('user') or data.get('session_id') or "").strip()
    if not user_id:
        return _json_response(
            {'error': 'Missing user or session_id. Provide a stable per-visitor identifier.'},
            400,
            rate_limit_info=rate_limit_info,
        )

    if not user_message:
        return _json_response({'error': 'No message'}, 400, rate_limit_info=rate_limit_info)

    # Tenant: from request body → X-Tenant-Id header → DEFAULT_TENANT_ID env var.
    # Callers should always pass tenant_id; the env fallback is for legacy deployments.
    tenant_id = (
        data.get('tenant_id')
        or request.headers.get('X-Tenant-Id')
        or os.getenv('DEFAULT_TENANT_ID', '')
    ).strip()
    if not tenant_id:
        return _json_response(
            {'error': 'Missing tenant_id. Pass it in the request body, X-Tenant-Id header, or set DEFAULT_TENANT_ID env var.'},
            400,
            rate_limit_info=rate_limit_info,
        )

    tenant = _resolve_runtime_tenant(tenant_id)
    if not tenant:
        return _json_response(
            {'error': f'Unknown tenant_id: {tenant_id}'},
            404,
            rate_limit_info=rate_limit_info,
        )

    session_id = f"web_{user_id}"
    payload = {'status': 'success', 'tenant': tenant.get_slug()}

    try:
        bot = _get_tenant_manager().get_bot(tenant.id)
        payload['content'] = bot.process_message(
            session_id,
            user_message,
            channel="web",
            customer_ref=str(user_id),
        )
        if hasattr(bot, "get_last_turn_meta"):
            meta = bot.get_last_turn_meta(session_id)
            if meta:
                payload["meta"] = meta
        return _json_response(payload, 200, rate_limit_info=rate_limit_info)
    except Exception as exc:
        logger.warning(
            "tenant_web_chat_failed_using_legacy",
            tenant_id=tenant.id,
            error=str(exc),
        )

    response = BotCore.reply_with_meta('web', user_id, user_message, tenant_id=tenant.id)
    payload['content'] = response.get('content', '')
    if response.get("meta") is not None:
        payload["meta"] = response.get("meta")
    return _json_response(payload, 200, rate_limit_info=rate_limit_info)

@public_api.route('/health', methods=['GET'])
def api_health():
    """
    API Health check alias
    """
    return jsonify({'status': 'healthy'})

# Initialize Service (Singleton-ish)
catalog_service = CatalogService()

@public_api.route('/catalog', methods=['GET'])
def get_catalog():
    """
    Return full product catalog from Google Sheets (Real Stock).
    Bypasses Postgres to ensure availability.
    Mapped to: /api/catalog
    """
    try:
        data = catalog_service.get_catalog()
        return jsonify(data), 200
    except Exception as e:
        logger.error("catalog_sheet_error", error=str(e))
        return jsonify({'error': f'Failed to load catalog: {str(e)}'}), 500

@public_api.route('/diag', methods=['GET'])
def get_diag():
    """Diagnostic endpoint to see which sheet is being used"""
    if not _diag_authorized():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        # We need to peek into catalog_service
        # This is a bit hacky but for debugging it's essential
        sheet = catalog_service.client.open_by_key(catalog_service.spreadsheet_id)
        all_ws = [w.title for w in sheet.worksheets()]
        
        # Try to get the cached catalog to see what's inside
        current_data = catalog_service.get_catalog()
        
        return jsonify({
            'target_worksheet': catalog_service.worksheet_name,
            'all_worksheets': all_ws,
            'item_count': len(current_data),
        }), 200
    except Exception as e:
         return jsonify({'error': str(e)}), 500

# Alias for legacy compatibility if needed, pointing to same logic
@public_api.route('/products', methods=['GET'])
def get_products_alias():
    return get_catalog()

@public_api.route('/catalog/grouped', methods=['GET'])
def get_catalog_grouped():
    """
    Return products grouped by model from Google Sheets
    """
    category_filter = request.args.get('category')
    
    try:
        # 1. Fetch from Sheets (Cached)
        products = catalog_service.get_catalog()
        
        # 2. Filter & Group
        grouped = {}
        for p in products:
            # Type safety
            cat = str(p.get('category', 'Others')).strip()
            p_model = p.get('name', 'Unknown')
            
            # Case-insensitive category filter
            if category_filter:
                if cat.lower() != category_filter.lower():
                    continue
                
            key = (cat, p_model)
            if key not in grouped:
                grouped[key] = {
                    'model': p_model,
                    'category': cat,
                    'min_price': p.get('price_ars', 0),
                    'variants': []
                }
            
            # Track min price
            if p.get('price_ars', 0) < grouped[key]['min_price']:
                grouped[key]['min_price'] = p['price_ars']
            
            grouped[key]['variants'].append(p)
        
        return jsonify(list(grouped.values())), 200
        
    except Exception as e:
        logger.error("catalog_grouped_error", error=str(e))
        return jsonify({'error': 'Failed to load grouped catalog'}), 500

@public_api.route('/catalog/variant', methods=['GET'])
def get_catalog_variant():
    """Get single variant by SKU from Sheets"""
    sku = request.args.get('sku')
    if not sku: return jsonify({'error': 'SKU required'}), 400
    
    try:
        products = catalog_service.get_catalog()
        # Find exact match
        target = next((p for p in products if str(p.get('sku')) == sku), None)
        
        if not target:
            return jsonify({'error': 'Product not found'}), 404
            
        return jsonify(target), 200
    except Exception as e:
        logger.error("catalog_variant_error", error=str(e))
        return jsonify({'error': 'Failed to load variant'}), 500

# Helper: Slugify (matches JS logic)
def slugify(text):
    if not text: return ""
    try:
        text = str(text)
        text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
        text = text.lower()
        text = re.sub(r'[\u0300-\u036f]', '', text)
        text = re.sub(r'\s+', '-', text)
        text = re.sub(r'[^a-z0-9-]', '', text)
        return text
    except Exception:
        return ""

@public_api.route('/catalog/detail', methods=['GET'])
def get_catalog_detail():
    """
    Get product details by slug from Sheets
    """
    slug = request.args.get('slug')
    if not slug: return jsonify({'error': 'Slug required'}), 400

    try:
        products = catalog_service.get_catalog()
        
        target_model = None
        target_p = None
        
        # Find match by slugifying 'name' (which acts as model)
        for p in products:
            p_model = p.get('name', '')
            p_slug = slugify(p_model)
            # 1. Exact match
            if p_slug == slug:
                target_model = p_model
                target_p = p
                break
            # 2. Fuzzy match (contains) as fallback
            if slug in p_slug or p_slug in slug:
                target_model = p_model
                target_p = p
                # Continue loop to see if there's a better exact match, 
                # but keep this as a strong candidate.
        
        if not target_model:
            return jsonify({'error': 'Product not found', 'requested_slug': slug}), 404
            
        # Get all variants for this model
        variants = [p for p in products if p.get('name') == target_model]
        
        if not variants:
             return jsonify({'error': 'No variants found'}), 404

        min_price = min((v.get('price_ars', 0) for v in variants), default=0)
        
        result = {
            'model': target_model,
            'category': target_p.get('category', 'Others'),
            'description': target_p.get('description', ''), # If existing
            'min_price': min_price,
            'variants': variants
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error("catalog_detail_error", error=str(e), slug=str(slug))
        return jsonify({'error': 'Failed to load product details'}), 500
