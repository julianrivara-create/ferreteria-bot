from __future__ import annotations

import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import UserRole
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_contact_phone_must_be_e164(client, session_factory):
    session = session_factory()
    try:
        _, user, _, token = seed_tenant_with_user(
            session,
            tenant_id="tenant-integrity-phone",
            user_id="admin-integrity-phone",
            role=UserRole.ADMIN,
        )
        session.commit()

        res = client.post(
            "/api/crm/contacts",
            json={
                "name": "Invalid Phone",
                "phone": "12345",
                "email": "invalid-phone@test.dev",
                "owner_user_id": user.id,
                "source_channel": "web",
            },
            headers=_auth_headers(token),
        )
        assert res.status_code == 422
    finally:
        session.close()


def test_closed_deal_cannot_transition_without_reopen(client, session_factory):
    session = session_factory()
    try:
        _, user, stage, token = seed_tenant_with_user(
            session,
            tenant_id="tenant-integrity-stage",
            user_id="owner-integrity-stage",
            role=UserRole.OWNER,
        )
        session.commit()

        contact = client.post(
            "/api/crm/contacts",
            json={
                "name": "Stage Lead",
                "phone": "+14155559501",
                "email": "stage-lead@test.dev",
                "owner_user_id": user.id,
                "source_channel": "web",
            },
            headers=_auth_headers(token),
        )
        assert contact.status_code == 201
        contact_id = contact.get_json()["id"]

        deal = client.post(
            "/api/crm/deals",
            json={
                "contact_id": contact_id,
                "title": "Stage Deal",
                "stage_id": stage.id,
                "owner_user_id": user.id,
                "currency": "USD",
                "source_channel": "whatsapp",
            },
            headers=_auth_headers(token),
        )
        assert deal.status_code == 201
        deal_id = deal.get_json()["id"]

        won = client.patch(
            f"/api/crm/deals/{deal_id}",
            json={"status": "won"},
            headers=_auth_headers(token),
        )
        assert won.status_code == 200

        invalid = client.patch(
            f"/api/crm/deals/{deal_id}",
            json={"status": "open"},
            headers=_auth_headers(token),
        )
        assert invalid.status_code == 409

        reopened = client.patch(
            f"/api/crm/deals/{deal_id}",
            json={"status": "open", "reopen": True},
            headers=_auth_headers(token),
        )
        assert reopened.status_code == 200
    finally:
        session.close()


def test_webhook_phone_normalization_dedupes_contact(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, owner_token = seed_tenant_with_user(
            session,
            tenant_id="tenant-integrity-webhook",
            user_id="owner-integrity-webhook",
            role=UserRole.OWNER,
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "webhook-secret")

        payload_a = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-norm-1",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+1 (415) 555-9900",
            "body": "first",
        }
        payload_b = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-norm-2",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "1-415-555-9900",
            "body": "second",
        }

        headers = {"Content-Type": "application/json", "X-CRM-Webhook-Token": "webhook-secret"}
        first = client.post("/api/crm/messages/webhook", json=payload_a, headers=headers)
        second = client.post("/api/crm/messages/webhook", json=payload_b, headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200

        contacts = client.get("/api/crm/contacts", headers={"Authorization": f"Bearer {owner_token}"})
        assert contacts.status_code == 200
        assert contacts.get_json()["pagination"]["total"] == 1
    finally:
        session.close()
