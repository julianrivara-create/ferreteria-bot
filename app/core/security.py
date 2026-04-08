
import hashlib
import hmac
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta, timezone
from app.db.session import SessionLocal
from app.db.models import IdempotencyKey
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()


def _is_configured_secret(value: str) -> bool:
    return settings.is_secret_configured(value)


def _parse_mp_signature(raw_header: str):
    """
    Parse MercadoPago x-signature header (e.g. "ts=...,v1=...").
    Returns (ts, v1) or (None, None) if invalid.
    """
    if not raw_header:
        return None, None
    try:
        parts = {}
        for part in raw_header.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            parts[key.strip()] = value.strip()
        return parts.get("ts"), parts.get("v1")
    except Exception:
        return None, None


def _mp_expected_signatures(secret: str, ts: str, payload: str):
    data_id = request.args.get("data.id")
    request_id = request.headers.get("x-request-id") or request.headers.get("X-Request-Id")
    manifests = []

    if data_id and request_id:
        manifests.append(f"id:{data_id};request-id:{request_id};ts:{ts};")
    if data_id:
        manifests.append(f"id:{data_id};ts:{ts};")
    manifests.append(f"{ts}.{payload}")

    return [
        hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        for manifest in manifests
    ]


def verify_mp_signature(f):
    """Validate MercadoPago webhook signature (fail-closed when secret is configured)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        secret = settings.MERCADOPAGO_WEBHOOK_SECRET
        if not _is_configured_secret(secret):
            logger.error("mp_webhook_secret_not_configured")
            return jsonify({"error": "MercadoPago webhook secret not configured"}), 503

        raw_signature = request.headers.get("x-signature") or request.headers.get("x-webhook-signature")
        ts, provided_sig = _parse_mp_signature(raw_signature)
        if not ts or not provided_sig:
            return jsonify({"error": "Missing or invalid MercadoPago signature"}), 401

        try:
            ts_int = int(ts)
            if ts_int > 10**11:  # milliseconds
                ts_int = ts_int // 1000
            now_ts = int(datetime.now(timezone.utc).timestamp())
            if abs(now_ts - ts_int) > 300:
                return jsonify({"error": "Stale MercadoPago signature timestamp"}), 401
        except Exception:
            return jsonify({"error": "Invalid MercadoPago signature timestamp"}), 401

        payload = request.get_data(as_text=True) or ""
        expected = _mp_expected_signatures(secret, ts, payload)
        if not any(hmac.compare_digest(provided_sig, candidate) for candidate in expected):
            logger.warning("invalid_mp_signature", request_id=request.headers.get("X-Request-Id"))
            return jsonify({"error": "Invalid MercadoPago signature"}), 401

        return f(*args, **kwargs)
    return wrapper

def verify_meta_signature(f):
    """Validates Meta Webhook Signature with HMAC — fail-closed."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # P2: Fail-closed. If META_APP_SECRET is not configured the endpoint
        # is not safe to expose; reject all requests rather than allow bypass.
        if not settings.META_APP_SECRET:
            logger.error("meta_app_secret_not_configured_rejecting_webhook")
            return jsonify({"error": "Webhook not configured"}), 503

        signature = request.headers.get("X-Hub-Signature-256")
        if not signature:
            return jsonify({"error": "No signature"}), 403
        try:
            expected = "sha256=" + hmac.new(
                settings.META_APP_SECRET.encode(),
                request.get_data(),
                hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return jsonify({"error": "Invalid signature"}), 403
        except Exception as e:
            logger.error("signature_error", error=str(e))
            return jsonify({"error": "Signature check failed"}), 403
        return f(*args, **kwargs)
    return wrapper

def idempotent_webhook(f):
    """Idempotency Middleware using DB"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        payload = request.get_json(silent=True) or {}
        topic = str(payload.get("type") or payload.get("topic") or "").strip().lower()
        entity_id = str(payload.get("data", {}).get("id") or "").strip()
        event_id = str(payload.get("id") or payload.get("event_id") or request.headers.get("X-Event-Id") or "").strip()
        action = str(payload.get("action") or "").strip().lower()

        if not entity_id and not event_id:
            return f(*args, **kwargs)

        key_parts = [topic or "unknown"]
        if event_id:
            key_parts.append(f"evt:{event_id}")
        if entity_id:
            key_parts.append(f"entity:{entity_id}")
        if action:
            key_parts.append(f"act:{action}")
        key = "mp:" + ":".join(key_parts)
        session = SessionLocal()
        try:
            existing = session.query(IdempotencyKey).filter(IdempotencyKey.key == key).with_for_update().first()
            if existing:
                if existing.status == 'COMPLETED':
                    return jsonify(existing.response_json or {}), 200
                elif existing.status == 'PROCESSING':
                    # Check TTL (5 mins)
                    if existing.locked_until and existing.locked_until < datetime.utcnow():
                         existing.locked_until = datetime.utcnow() + timedelta(minutes=5)
                         session.commit()
                    else:
                         return jsonify({"error": "Processing"}), 409
            
            if not existing:
                new_key = IdempotencyKey(
                    key=key, status='PROCESSING',
                    created_at=datetime.utcnow(),
                    locked_until=datetime.utcnow() + timedelta(minutes=5)
                )
                session.add(new_key)
                session.commit()
            
            result = f(*args, **kwargs)
            
            # Extract response
            response_json = {}
            status_code = 200
            if isinstance(result, tuple):
                body, status_code = result
                if hasattr(body, 'get_json'): response_json = body.get_json()
                elif isinstance(body, dict): response_json = body
            elif hasattr(result, 'get_json'):
                response_json = result.get_json()
            elif isinstance(result, dict):
                response_json = result

            # Mark complete
            track = session.get(IdempotencyKey, key)
            if track:
                track.status = 'COMPLETED'
                track.completed_at = datetime.utcnow()
                track.response_json = response_json
                track.locked_until = None
                session.commit()
            
            return result
        except Exception as e:
            session.rollback()
            # Keep a failed marker instead of deleting the key to avoid race-induced duplicates.
            clean_sess = SessionLocal()
            try:
                k = clean_sess.get(IdempotencyKey, key)
                if k:
                    k.status = "FAILED"
                    k.completed_at = datetime.utcnow()
                    k.locked_until = None
                    clean_sess.commit()
            finally:
                clean_sess.close()
            raise e
        finally:
            session.close()
    return wrapper
