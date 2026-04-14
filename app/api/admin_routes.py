
from flask import Blueprint, jsonify, request
from app.core.config import get_settings
from functools import wraps
from app.db.session import SessionLocal
from app.db.models import IdempotencyKey, Product
import structlog
import hmac

admin = Blueprint('admin', __name__)
settings = get_settings()
logger = structlog.get_logger()

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not settings.is_secret_configured(settings.ADMIN_TOKEN):
            logger.error("admin_token_not_configured")
            return jsonify({"error": "Admin token not configured"}), 503

        token = request.headers.get("X-Admin-Token") or ""
        if not hmac.compare_digest(token, settings.ADMIN_TOKEN):
            return jsonify({"error": "Unauthorized", "hint": "Use X-Admin-Token header"}), 401
        return f(*args, **kwargs)
    return wrapper

@admin.route('/cache/clear', methods=['POST'])
@admin_required
def clear_cache():
    # Placeholder for clearer reddis if implemented
    return jsonify({"status": "cleared"}), 200

@admin.route('/idempotency/cleanup', methods=['POST'])
@admin_required
def cleanup_idempotency():
    session = SessionLocal()
    try:
        deleted = session.query(IdempotencyKey).filter(IdempotencyKey.status == 'COMPLETED').delete()
        session.commit()
        return jsonify({"deleted": deleted}), 200
    finally:
        session.close()


@admin.route('/stock/sync-sheet', methods=['POST'])
@admin_required
def sync_sheet():
    """
    Strict Sheet Sync Endpoint
    POST only. Requires X-Admin-Token.
    """
    from app.services.stock_sheet_sync import StockSheetSync
    
    # Check config
    if not settings.GOOGLE_SHEETS_SPREADSHEET_ID:
        return jsonify({"status": "error", "message": "Missing GOOGLE_SHEETS_SPREADSHEET_ID"}), 500
    tenant_id = (request.args.get("tenant_id") or settings.DEFAULT_TENANT_ID or "").strip()
    if not tenant_id:
        return jsonify({"status": "error", "message": "Missing tenant_id or DEFAULT_TENANT_ID"}), 400
        
    try:
        syncer = StockSheetSync(
            spreadsheet_id=settings.GOOGLE_SHEETS_SPREADSHEET_ID,
            service_account_json=settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON,
            service_account_path=settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_PATH,
            tenant_id=tenant_id,
        )
        
        session = SessionLocal()
        try:
            result = syncer.sync_to_database(session, tenant_id=tenant_id)
            status_code = 200 if result.get('status') == 'ok' else 400
            return jsonify(result), status_code
        finally:
            session.close()

    except Exception as e:
        logger.error("admin_sync_error", error=str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@admin.route('/products/fix-model-names', methods=['POST'])
@admin_required
def fix_model_names():
    """
    Audit and fix incorrect product model names.
    Compares model field with SKU prefixes to identify mismatches.
    """
    session = SessionLocal()
    
    try:
        # Get all active products
        products = session.query(Product).filter(Product.active == True).all()
        
        # Group by model
        models = {}
        for p in products:
            if p.model not in models:
                models[p.model] = []
            models[p.model].append(p.sku)
        
        # Identify issues
        issues = []
        
        for model, skus in models.items():
            # Check for common mismatches
            if "17" in model and any(sku.startswith("IPH13") for sku in skus):
                issues.append({
                    'current': model,
                    'correct': model.replace("17", "13"),
                    'affected_skus': [s for s in skus if s.startswith("IPH13")]
                })
            
            if "16" in model and any(sku.startswith("IPH15") for sku in skus):
                issues.append({
                    'current': model,
                    'correct': model.replace("16", "15"),
                    'affected_skus': [s for s in skus if s.startswith("IPH15")]
                })
            
            if "15" in model and any(sku.startswith("IPH14") for sku in skus):
                issues.append({
                    'current': model,
                    'correct': model.replace("15", "14"),
                    'affected_skus': [s for s in skus if s.startswith("IPH14")]
                })
        
        if not issues:
            return jsonify({
                "status": "success",
                "message": "No issues found",
                "fixes_applied": 0
            }), 200
        
        # Apply fixes
        fixes_applied = []
        
        for issue in issues:
            updated = session.query(Product).filter(
                Product.model == issue['current']
            ).update({
                'model': issue['correct']
            }, synchronize_session=False)
            
            fixes_applied.append({
                'from': issue['current'],
                'to': issue['correct'],
                'records_updated': updated
            })
            
            logger.info("model_name_fixed", 
                       old_model=issue['current'],
                       new_model=issue['correct'],
                       records=updated)
        
        session.commit()
        
        return jsonify({
            "status": "success",
            "message": f"Fixed {len(fixes_applied)} model names",
            "fixes": fixes_applied
        }), 200
        
    except Exception as e:
        session.rollback()
        logger.error("fix_model_names_error", error=str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
