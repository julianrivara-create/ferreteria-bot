from __future__ import annotations

import hashlib
import json
import logging

import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import UserRole
from app.crm.models import CRMAuditLog
from tests.crm.utils import seed_tenant_with_user


def _token_headers(secret: str) -> dict:
    return {"Content-Type": "application/json", "X-CRM-Webhook-Token": secret}


def _signature_headers(secret: str, payload: dict) -> tuple[dict, str]:
    raw = json.dumps(payload, separators=(",", ":"))
    digest = hashlib.sha256(secret.encode("utf-8") + b"." + raw.encode("utf-8")).hexdigest()
    return {"Content-Type": "application/json", "X-CRM-Signature": f"sha256={digest}"}, raw


def test_webhook_auth_mode_token_accepts_token_and_rejects_signature_only(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auth-token",
            user_id="owner-auth-token",
            role=UserRole.OWNER,
        )
        tenant.webhook_auth_mode = "token"
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "auth-secret")

        token_ok = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-auth-token-ok",
                "event_type": "inbound_message",
                "channel": "web",
                "phone": "+14155557001",
                "body": "hola token",
            },
            headers=_token_headers("auth-secret"),
        )
        assert token_ok.status_code == 200
        assert token_ok.get_json()["auth_method"] == "token"
        token_ok.close()

        bad_payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-auth-token-signature-reject",
            "event_type": "inbound_message",
            "channel": "web",
            "phone": "+14155557002",
            "body": "hola sign",
        }
        sign_headers, raw = _signature_headers("auth-secret", bad_payload)
        sign_reject = client.post("/api/crm/messages/webhook", data=raw, headers=sign_headers)
        assert sign_reject.status_code == 401
        sign_reject.close()

        audit = (
            session.query(CRMAuditLog)
            .filter(
                CRMAuditLog.tenant_id == tenant.id,
                CRMAuditLog.entity_type == "webhook",
                CRMAuditLog.action == "auth_rejected",
            )
            .order_by(CRMAuditLog.created_at.desc())
            .first()
        )
        assert audit is not None
        assert (audit.metadata_json or {}).get("reason") == "token_required"
    finally:
        session.close()


def test_webhook_auth_mode_hmac_accepts_signature_and_rejects_token_only(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auth-hmac",
            user_id="owner-auth-hmac",
            role=UserRole.OWNER,
        )
        tenant.webhook_auth_mode = "hmac"
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "auth-secret")

        token_reject = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-auth-hmac-token-reject",
                "event_type": "inbound_message",
                "channel": "web",
                "phone": "+14155557003",
                "body": "hola token",
            },
            headers=_token_headers("auth-secret"),
        )
        assert token_reject.status_code == 401
        token_reject.close()

        good_payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-auth-hmac-ok",
            "event_type": "inbound_message",
            "channel": "web",
            "phone": "+14155557004",
            "body": "hola sign",
        }
        sign_headers, raw = _signature_headers("auth-secret", good_payload)
        sign_ok = client.post("/api/crm/messages/webhook", data=raw, headers=sign_headers)
        assert sign_ok.status_code == 200
        assert sign_ok.get_json()["auth_method"] == "hmac"
        sign_ok.close()

        audit = (
            session.query(CRMAuditLog)
            .filter(
                CRMAuditLog.tenant_id == tenant.id,
                CRMAuditLog.entity_type == "webhook",
                CRMAuditLog.action == "auth_rejected",
            )
            .order_by(CRMAuditLog.created_at.desc())
            .first()
        )
        assert audit is not None
        assert (audit.metadata_json or {}).get("reason") == "hmac_required"
    finally:
        session.close()


def test_webhook_auth_mode_both_accepts_either_and_logs_weaker_token_warning(
    client,
    session_factory,
    monkeypatch,
    caplog,
):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auth-both",
            user_id="owner-auth-both",
            role=UserRole.OWNER,
        )
        tenant.webhook_auth_mode = "both"
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "auth-secret")

        caplog.set_level(logging.WARNING, logger="app.crm.api.routes")

        token_ok = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-auth-both-token",
                "event_type": "inbound_message",
                "channel": "web",
                "phone": "+14155557005",
                "body": "token path",
            },
            headers=_token_headers("auth-secret"),
        )
        assert token_ok.status_code == 200
        assert token_ok.get_json()["auth_method"] == "token"
        token_ok.close()

        token_warnings = [
            rec
            for rec in caplog.records
            if rec.name == "app.crm.api.routes" and "webhook_auth_weaker_method_used" in rec.getMessage()
        ]
        assert len(token_warnings) >= 1

        good_payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-auth-both-hmac",
            "event_type": "inbound_message",
            "channel": "web",
            "phone": "+14155557006",
            "body": "hmac path",
        }
        sign_headers, raw = _signature_headers("auth-secret", good_payload)
        sign_ok = client.post("/api/crm/messages/webhook", data=raw, headers=sign_headers)
        assert sign_ok.status_code == 200
        assert sign_ok.get_json()["auth_method"] == "hmac"
        sign_ok.close()
    finally:
        session.close()
