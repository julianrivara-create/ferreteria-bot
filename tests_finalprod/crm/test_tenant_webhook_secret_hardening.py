from __future__ import annotations

import hashlib
import json

from app.crm.domain.enums import UserRole
from tests.crm.utils import seed_tenant_with_user


def _signature_headers(secret: str, payload: dict) -> tuple[dict, str]:
    raw = json.dumps(payload, separators=(",", ":"))
    digest = hashlib.sha256(secret.encode("utf-8") + b"." + raw.encode("utf-8")).hexdigest()
    return {"Content-Type": "application/json", "X-CRM-Signature": f"sha256={digest}"}, raw


def test_webhook_prefers_tenant_secret_over_global_fallback(client, session_factory, monkeypatch):
    import app.crm.api.routes as crm_routes_module

    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-secret-scope",
            user_id="owner-secret-scope",
            role=UserRole.OWNER,
        )
        tenant.webhook_auth_mode = "hmac"
        tenant.integration_settings = {"crm_webhook_secret": "tenant-secret"}
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "global-secret")

        bad_payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-tenant-secret-bad",
            "event_type": "inbound_message",
            "channel": "web",
            "phone": "+14155557007",
            "body": "wrong secret",
        }
        bad_headers, bad_raw = _signature_headers("global-secret", bad_payload)
        bad = client.post("/api/crm/messages/webhook", data=bad_raw, headers=bad_headers)
        assert bad.status_code == 401

        good_payload = {
            "tenant_id": tenant.id,
            "source": "bot",
            "event_id": "evt-tenant-secret-good",
            "event_type": "inbound_message",
            "channel": "web",
            "phone": "+14155557008",
            "body": "right secret",
        }
        good_headers, good_raw = _signature_headers("tenant-secret", good_payload)
        good = client.post("/api/crm/messages/webhook", data=good_raw, headers=good_headers)
        assert good.status_code == 200
        assert good.get_json()["auth_method"] == "hmac"
    finally:
        session.close()
