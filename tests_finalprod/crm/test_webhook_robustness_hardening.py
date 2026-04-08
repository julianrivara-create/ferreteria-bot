from __future__ import annotations

import hashlib
import json

import pytest

import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import AutomationTrigger, UserRole
from app.crm.models import CRMAutomation, CRMDeal, CRMDealEvent, CRMMessage, CRMTask, CRMWebhookEvent
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _token_headers(secret: str) -> dict:
    return {"Content-Type": "application/json", "X-CRM-Webhook-Token": secret}


def _signature_headers(secret: str, payload: dict) -> tuple[dict, str]:
    raw = json.dumps(payload, separators=(",", ":"))
    digest = hashlib.sha256(secret.encode("utf-8") + b"." + raw.encode("utf-8")).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-CRM-Signature": f"sha256={digest}",
    }
    return headers, raw


def test_webhook_idempotency_prevents_duplicate_effects_with_automation(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, owner, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-hook-hard",
            user_id="owner-hook-hard",
            role=UserRole.OWNER,
        )
        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="inbound-followup",
                trigger_type=AutomationTrigger.MESSAGE_RECEIVED,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={},
                actions_json=[{"type": "create_task", "title": "Call back", "due_in_minutes": 30}],
                created_by_user_id=owner.id,
            )
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "hook-secret")

        payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-idem-001",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+14155555001",
            "name": "Lead Idempotent",
            "body": "need price",
            "external_message_id": "msg-idem-1",
        }

        first = client.post("/api/crm/messages/webhook", json=payload, headers=_token_headers("hook-secret"))
        assert first.status_code == 200
        assert first.get_json()["created"] is True

        second = client.post("/api/crm/messages/webhook", json=payload, headers=_token_headers("hook-secret"))
        assert second.status_code == 200
        assert second.get_json()["created"] is False
        assert second.get_json()["status"] == "duplicate"

        assert session.query(CRMWebhookEvent).filter(CRMWebhookEvent.tenant_id == tenant.id).count() == 1
        assert session.query(CRMMessage).filter(CRMMessage.tenant_id == tenant.id).count() == 1
        assert session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id).count() == 1
    finally:
        session.close()


def test_out_of_order_quote_event_upserts_deal(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-hook-ooo",
            user_id="owner-hook-ooo",
            role=UserRole.OWNER,
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "hook-secret")

        payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-quote-before-deal",
            "event_type": "quote_sent",
            "channel": "whatsapp",
            "phone": "+14155555002",
            "body": "quote sent",
            "product_model": "Herramienta 15 Pro",
            "amount_estimated": 1299,
        }

        res = client.post("/api/crm/messages/webhook", json=payload, headers=_token_headers("hook-secret"))
        assert res.status_code == 200
        body = res.get_json()
        assert body["created"] is True
        assert body["result"]["deal_id"] is not None

        res_dup = client.post("/api/crm/messages/webhook", json=payload, headers=_token_headers("hook-secret"))
        assert res_dup.status_code == 200
        assert res_dup.get_json()["created"] is False

        assert session.query(CRMDeal).filter(CRMDeal.tenant_id == tenant.id).count() == 1
        assert session.query(CRMMessage).filter(CRMMessage.tenant_id == tenant.id).count() == 1
        assert session.query(CRMDealEvent).filter(CRMDealEvent.tenant_id == tenant.id).count() == 1
    finally:
        session.close()


def test_webhook_rejects_invalid_signature(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-hook-signature",
            user_id="owner-hook-signature",
            role=UserRole.OWNER,
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "hook-secret")

        payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-signature-1",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+14155555003",
            "body": "hello",
        }
        raw = json.dumps(payload, separators=(",", ":"))
        headers = {"Content-Type": "application/json", "X-CRM-Signature": "sha256=invalid"}

        res = client.post("/api/crm/messages/webhook", data=raw, headers=headers)
        assert res.status_code == 401
    finally:
        session.close()


def test_webhook_accepts_valid_hmac_signature(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-hook-valid-signature",
            user_id="owner-hook-valid-signature",
            role=UserRole.OWNER,
        )
        tenant.webhook_auth_mode = "hmac"
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "hook-secret")

        payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-signature-ok",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+14155555004",
            "body": "hello signed",
        }
        headers, raw = _signature_headers("hook-secret", payload)

        res = client.post("/api/crm/messages/webhook", data=raw, headers=headers)
        assert res.status_code == 200
        assert res.get_json()["created"] is True
    finally:
        session.close()


def test_failed_webhook_event_can_be_replayed_by_owner(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, owner, _, owner_token = seed_tenant_with_user(
            session,
            tenant_id="tenant-hook-replay",
            user_id="owner-hook-replay",
            role=UserRole.OWNER,
        )
        _, _, _, sales_token = seed_tenant_with_user(
            session,
            tenant_id="tenant-hook-replay",
            user_id="sales-hook-replay",
            role=UserRole.SALES,
        )
        session.commit()

        failed_row = CRMWebhookEvent(
            tenant_id=tenant.id,
            source="bot",
            event_type="inbound_message",
            event_key="evt-failed-1",
            payload={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-failed-1",
                "event_type": "inbound_message",
                "channel": "whatsapp",
                "phone": "+14155555005",
                "body": "retry me",
            },
            status="failed",
            error_message="simulated",
        )
        session.add(failed_row)
        session.commit()

        replay_forbidden = client.post(
            f"/api/crm/messages/webhook-events/{failed_row.id}/replay",
            headers=_auth_headers(sales_token),
        )
        assert replay_forbidden.status_code == 403

        replay_ok = client.post(
            f"/api/crm/messages/webhook-events/{failed_row.id}/replay",
            headers=_auth_headers(owner_token),
        )
        assert replay_ok.status_code == 200
        assert replay_ok.get_json()["status"] == "processed"

        session.expire_all()
        refreshed = session.query(CRMWebhookEvent).filter(CRMWebhookEvent.id == failed_row.id).first()
        assert refreshed is not None
        assert refreshed.status == "processed"
    finally:
        session.close()
