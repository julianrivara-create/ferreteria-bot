from __future__ import annotations

import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import MessageDirection, UserRole
from app.crm.models import CRMConversation, CRMMessage, CRMWebhookEvent
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_contact(client, token: str, owner_user_id: str, *, name: str, phone: str, email: str) -> str:
    res = client.post(
        "/api/crm/contacts",
        json={
            "name": name,
            "phone": phone,
            "email": email,
            "source_channel": "whatsapp",
            "owner_user_id": owner_user_id,
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == 201
    return res.get_json()["id"]


def _create_deal(client, token: str, contact_id: str, stage_id: str, owner_user_id: str, *, title: str) -> str:
    res = client.post(
        "/api/crm/deals",
        json={
            "contact_id": contact_id,
            "title": title,
            "stage_id": stage_id,
            "owner_user_id": owner_user_id,
            "currency": "USD",
            "source_channel": "whatsapp",
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == 201
    return res.get_json()["id"]


def _create_task(client, token: str, contact_id: str, deal_id: str, assigned_user_id: str, *, title: str) -> str:
    res = client.post(
        "/api/crm/tasks",
        json={
            "title": title,
            "contact_id": contact_id,
            "deal_id": deal_id,
            "assigned_to_user_id": assigned_user_id,
            "priority": "medium",
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == 201
    return res.get_json()["id"]


def test_cross_tenant_access_deals_tasks_conversations_messages_is_blocked(client, session_factory):
    session = session_factory()
    try:
        _, admin_a, stage_a, token_a = seed_tenant_with_user(
            session, tenant_id="tenant-iso-a", user_id="admin-iso-a", role=UserRole.ADMIN
        )
        _, admin_b, stage_b, token_b = seed_tenant_with_user(
            session, tenant_id="tenant-iso-b", user_id="admin-iso-b", role=UserRole.ADMIN
        )
        session.commit()

        contact_a = _create_contact(
            client,
            token_a,
            admin_a.id,
            name="A Contact",
            phone="+14155550001",
            email="a-contact@iso.test",
        )
        contact_b = _create_contact(
            client,
            token_b,
            admin_b.id,
            name="B Contact",
            phone="+14155550002",
            email="b-contact@iso.test",
        )

        deal_a = _create_deal(client, token_a, contact_a, stage_a.id, admin_a.id, title="Deal A")
        deal_b = _create_deal(client, token_b, contact_b, stage_b.id, admin_b.id, title="Deal B")

        _ = _create_task(client, token_a, contact_a, deal_a, admin_a.id, title="Task A")
        task_b = _create_task(client, token_b, contact_b, deal_b, admin_b.id, title="Task B")

        conv_b = CRMConversation(tenant_id="tenant-iso-b", contact_id=contact_b, channel="whatsapp", external_id="conv-b")
        session.add(conv_b)
        session.flush()
        msg_b = CRMMessage(
            tenant_id="tenant-iso-b",
            conversation_id=conv_b.id,
            contact_id=contact_b,
            channel="whatsapp",
            direction=MessageDirection.INBOUND,
            body="hello from b",
        )
        session.add(msg_b)
        session.commit()

        list_deals_cross = client.get(f"/api/crm/deals?contact_id={contact_b}", headers=_auth_headers(token_a))
        assert list_deals_cross.status_code == 200
        assert list_deals_cross.get_json()["items"] == []

        patch_task_cross = client.patch(
            f"/api/crm/tasks/{task_b}",
            json={"status": "done"},
            headers=_auth_headers(token_a),
        )
        assert patch_task_cross.status_code == 404

        conv_messages_cross = client.get(f"/api/crm/conversations/{conv_b.id}/messages", headers=_auth_headers(token_a))
        assert conv_messages_cross.status_code == 200
        assert conv_messages_cross.get_json()["items"] == []

        global_messages_cross = client.get(f"/api/crm/messages?contact_id={contact_b}", headers=_auth_headers(token_a))
        assert global_messages_cross.status_code == 200
        assert global_messages_cross.get_json()["items"] == []

        contact_cross = client.get(f"/api/crm/contacts/{contact_b}", headers=_auth_headers(token_a))
        assert contact_cross.status_code == 404
    finally:
        session.close()


def test_reports_and_exports_are_tenant_scoped(client, session_factory):
    session = session_factory()
    try:
        _, admin_a, _, token_a = seed_tenant_with_user(session, tenant_id="tenant-rep-a", user_id="admin-rep-a", role=UserRole.ADMIN)
        _, admin_b, _, token_b = seed_tenant_with_user(session, tenant_id="tenant-rep-b", user_id="admin-rep-b", role=UserRole.ADMIN)
        session.commit()

        _create_contact(client, token_a, admin_a.id, name="Lead A", phone="+14155551001", email="lead-a@rep.test")
        _create_contact(client, token_b, admin_b.id, name="Lead B", phone="+14155551002", email="lead-b@rep.test")

        dashboard_a = client.get("/api/crm/reports/dashboard", headers=_auth_headers(token_a))
        assert dashboard_a.status_code == 200
        assert dashboard_a.get_json()["leads_created"] == 1

        dashboard_b = client.get("/api/crm/reports/dashboard", headers=_auth_headers(token_b))
        assert dashboard_b.status_code == 200
        assert dashboard_b.get_json()["leads_created"] == 1

        export_a = client.get("/api/crm/reports/export.csv", headers=_auth_headers(token_a))
        assert export_a.status_code == 200
        body = export_a.data.decode()
        assert "leads_created,1" in body
        assert "leads_created,2" not in body
    finally:
        session.close()


def test_soft_deleted_contacts_are_hidden_by_default(client, session_factory):
    session = session_factory()
    try:
        _, admin, _, token = seed_tenant_with_user(session, tenant_id="tenant-soft-delete", user_id="admin-soft-delete", role=UserRole.ADMIN)
        session.commit()

        contact_id = _create_contact(
            client,
            token,
            admin.id,
            name="Delete Me",
            phone="+14155552001",
            email="delete-me@iso.test",
        )

        delete_res = client.delete(f"/api/crm/contacts/{contact_id}", headers=_auth_headers(token))
        assert delete_res.status_code == 200

        list_res = client.get("/api/crm/contacts", headers=_auth_headers(token))
        assert list_res.status_code == 200
        ids = {row["id"] for row in list_res.get_json()["items"]}
        assert contact_id not in ids

        get_res = client.get(f"/api/crm/contacts/{contact_id}", headers=_auth_headers(token))
        assert get_res.status_code == 404
    finally:
        session.close()


def test_webhook_event_listing_is_tenant_scoped(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant_a, _, _, token_a = seed_tenant_with_user(session, tenant_id="tenant-webhook-a", user_id="owner-webhook-a", role=UserRole.OWNER)
        tenant_b, _, _, token_b = seed_tenant_with_user(session, tenant_id="tenant-webhook-b", user_id="owner-webhook-b", role=UserRole.OWNER)
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "tenant-webhook-secret")

        headers = {"Content-Type": "application/json", "X-CRM-Webhook-Token": "tenant-webhook-secret"}
        payload_a = {
            "tenant_id": tenant_a.id,
            "source": "bot",
            "event_id": "evt-a-1",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+14155553001",
            "body": "hello A",
        }
        payload_b = {
            "tenant_id": tenant_b.id,
            "source": "bot",
            "event_id": "evt-b-1",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+14155553002",
            "body": "hello B",
        }
        assert client.post("/api/crm/messages/webhook", json=payload_a, headers=headers).status_code == 200
        assert client.post("/api/crm/messages/webhook", json=payload_b, headers=headers).status_code == 200

        rows = session.query(CRMWebhookEvent).count()
        assert rows == 2

        list_a = client.get("/api/crm/messages/webhook-events", headers=_auth_headers(token_a))
        assert list_a.status_code == 200
        keys_a = {row["event_key"] for row in list_a.get_json()["items"]}
        assert keys_a == {"evt-a-1"}

        list_b = client.get("/api/crm/messages/webhook-events", headers=_auth_headers(token_b))
        assert list_b.status_code == 200
        keys_b = {row["event_key"] for row in list_b.get_json()["items"]}
        assert keys_b == {"evt-b-1"}
    finally:
        session.close()


def test_cross_tenant_segment_export_returns_not_found(client, session_factory):
    session = session_factory()
    try:
        _, admin_a, _, token_a = seed_tenant_with_user(session, tenant_id="tenant-seg-a", user_id="admin-seg-a", role=UserRole.ADMIN)
        _, admin_b, _, token_b = seed_tenant_with_user(session, tenant_id="tenant-seg-b", user_id="admin-seg-b", role=UserRole.ADMIN)
        session.commit()

        create_segment_b = client.post(
            "/api/crm/segments",
            json={"name": "inactive-14d", "filters": {"inactive_days": 14}},
            headers=_auth_headers(token_b),
        )
        assert create_segment_b.status_code == 201
        segment_b_id = create_segment_b.get_json()["id"]

        export_cross = client.get(f"/api/crm/segments/{segment_b_id}/export.csv", headers=_auth_headers(token_a))
        assert export_cross.status_code == 404

        # Owner/Admin only export check remains true for same tenant.
        export_self = client.get(f"/api/crm/segments/{segment_b_id}/export.csv", headers=_auth_headers(token_b))
        assert export_self.status_code == 200
    finally:
        session.close()
