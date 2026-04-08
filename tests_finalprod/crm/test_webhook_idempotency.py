import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import UserRole
from app.crm.models import CRMMessage, CRMWebhookEvent
from tests.crm.utils import seed_tenant_with_user


def test_inbound_webhook_idempotency(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session, tenant_id="tenant-hook", user_id="owner-hook", role=UserRole.OWNER
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "test-webhook-secret")

        payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-001",
            "event_type": "inbound_message",
            "channel": "whatsapp",
            "phone": "+5491166660001",
            "name": "Webhook Contact",
            "body": "Hola, quiero precio",
            "external_message_id": "wa-msg-001",
        }
        headers = {
            "Content-Type": "application/json",
            "X-CRM-Webhook-Token": "test-webhook-secret",
        }

        first = client.post("/api/crm/messages/webhook", json=payload, headers=headers)
        assert first.status_code == 200
        first_body = first.get_json()
        assert first_body["created"] is True

        second = client.post("/api/crm/messages/webhook", json=payload, headers=headers)
        assert second.status_code == 200
        second_body = second.get_json()
        assert second_body["created"] is False

        message_count = session.query(CRMMessage).filter(CRMMessage.tenant_id == tenant.id).count()
        webhook_count = session.query(CRMWebhookEvent).filter(CRMWebhookEvent.tenant_id == tenant.id).count()
        assert message_count == 1
        assert webhook_count == 1
    finally:
        session.close()
