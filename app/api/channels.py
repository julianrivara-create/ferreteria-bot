
from flask import Blueprint, request, jsonify
from app.core.security import verify_meta_signature
from app.services.channels.whatsapp_meta import WhatsAppMeta
from app.services.channels.instagram_meta import InstagramMeta
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.models import IdempotencyKey
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
import structlog
import hmac
import time

_last_idempotency_cleanup: float = 0.0
_CLEANUP_INTERVAL_SECONDS = 3600  # run at most once per hour

# Lazy import to avoid circular dep at module load time
def _get_tenant_manager():
    from bot_sales.core.tenancy import tenant_manager
    return tenant_manager

logger = structlog.get_logger()
settings = get_settings()
channels = Blueprint('channels', __name__)

@channels.route('/meta', methods=['GET'])
def meta_verify():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token') or ""
    challenge = request.args.get('hub.challenge')
    if not settings.is_secret_configured(settings.META_VERIFY_TOKEN):
        logger.error("meta_verify_token_not_configured")
        return jsonify({"error": "Meta verify token not configured"}), 503
    if mode == 'subscribe' and hmac.compare_digest(token, settings.META_VERIFY_TOKEN):
        return challenge, 200
    return jsonify({"error": "Verification failed"}), 403

def _maybe_cleanup_idempotency_keys():
    """Purge expired idempotency keys at most once per hour (in-process scheduling)."""
    global _last_idempotency_cleanup
    now = time.time()
    if now - _last_idempotency_cleanup < _CLEANUP_INTERVAL_SECONDS:
        return
    _last_idempotency_cleanup = now
    cutoff = datetime.utcnow() - timedelta(days=7)
    sess = SessionLocal()
    try:
        deleted = (
            sess.query(IdempotencyKey)
            .filter(IdempotencyKey.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        sess.commit()
        if deleted:
            logger.info("idempotency_keys_purged", count=deleted)
    except Exception as exc:
        sess.rollback()
        logger.error("idempotency_cleanup_error", error=str(exc))
    finally:
        sess.close()


@channels.route('/meta', methods=['POST'])
@verify_meta_signature
def meta_webhook():
    data = request.get_json(silent=True) or {}
    if 'entry' not in data: return jsonify({"status": "ignored"}), 200

    _maybe_cleanup_idempotency_keys()

    session = SessionLocal()
    try:
        for entry in data.get('entry', []):
            changes = entry.get('changes', [])
            for change in changes:
                value = change.get('value', {})
                if 'messages' in value: # WhatsApp
                    phone_number_id = value.get('metadata', {}).get('phone_number_id', '')
                    tenant = _get_tenant_manager().get_tenant_by_phone_number_id(phone_number_id)
                    if not tenant:
                        logger.warning("whatsapp_unknown_phone_number_id", phone_number_id=phone_number_id)
                        continue
                    tenant_id = tenant.id
                    for msg in value.get('messages', []):
                        if handle_idempotency(session, f"wa:{msg.get('id')}"):
                            WhatsAppMeta.handle_inbound(msg, value, tenant_id=tenant_id)
                elif 'messaging' in value:  # Instagram
                    ig_page_id = entry.get('id', '')
                    ig_tenant = _get_tenant_manager().get_tenant_by_ig_page_id(ig_page_id) if ig_page_id else None
                    if not ig_tenant:
                        logger.warning("instagram_unknown_page_id", ig_page_id=ig_page_id)
                        continue
                    ig_tenant_id = ig_tenant.id
                    for event in value.get('messaging', []):
                        if handle_idempotency(session, f"ig:{event.get('message',{}).get('mid')}"):
                            InstagramMeta.handle_inbound(event, tenant_id=ig_tenant_id)
        return jsonify({"status": "processed"}), 200
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def handle_idempotency(session, key):
    if not key or "None" in key: return False
    try:
        session.add(IdempotencyKey(key=key, status='COMPLETED', created_at=datetime.utcnow()))
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False
