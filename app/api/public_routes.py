
from flask import Blueprint, request, jsonify
from app.db.session import SessionLocal
from app.db.models import Product
from app.services.bot_core import BotCore
from app.services.catalog_service import CatalogService
from app.core.config import get_settings

import structlog
import unicodedata
import re
import hmac

public_api = Blueprint('public_api', __name__)
logger = structlog.get_logger()
settings = get_settings()


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
    """Legacy single-tenant web chat endpoint. Uses BotCore."""
    import os
    data = request.json or {}
    user_message = data.get('message')

    # Require a stable per-visitor identifier — no shared anonymous sessions.
    user_id = (data.get('user') or data.get('session_id') or "").strip()
    if not user_id:
        return jsonify({'error': 'Missing user or session_id. Provide a stable per-visitor identifier.'}), 400

    if not user_message:
        return jsonify({'error': 'No message'}), 400

    # Tenant: from request body → X-Tenant-Id header → DEFAULT_TENANT_ID env var.
    # Callers should always pass tenant_id; the env fallback is for legacy deployments.
    tenant_id = (
        data.get('tenant_id')
        or request.headers.get('X-Tenant-Id')
        or os.getenv('DEFAULT_TENANT_ID', '')
    ).strip()
    if not tenant_id:
        return jsonify({'error': 'Missing tenant_id. Pass it in the request body, X-Tenant-Id header, or set DEFAULT_TENANT_ID env var.'}), 400

    response = BotCore.reply_with_meta('web', user_id, user_message, tenant_id=tenant_id)
    payload = {'content': response.get('content', ''), 'status': 'success'}
    if response.get("meta") is not None:
        payload["meta"] = response.get("meta")
    return jsonify(payload)

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
