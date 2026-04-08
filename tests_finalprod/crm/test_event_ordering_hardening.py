from __future__ import annotations

from datetime import datetime

import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import DealStatus, UserRole
from app.crm.models import CRMContact, CRMConversation, CRMDeal, CRMDealEvent, CRMPipelineStage
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _token_headers(secret: str) -> dict:
    return {"Content-Type": "application/json", "X-CRM-Webhook-Token": secret}


def test_out_of_order_outbound_message_does_not_reduce_last_activity_at(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, _, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-order-activity",
            user_id="owner-order-activity",
            role=UserRole.OWNER,
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "order-secret")
        headers = _token_headers("order-secret")

        first = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-order-newest",
                "event_type": "inbound_message",
                "channel": "web",
                "phone": "+14155550100",
                "body": "hola",
                "occurred_at": "2026-02-17T12:00:00Z",
            },
            headers=headers,
        )
        assert first.status_code == 200

        second = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-order-older",
                "event_type": "outbound_message",
                "channel": "web",
                "phone": "+14155550100",
                "body": "respuesta vieja",
                "occurred_at": "2026-02-17T10:00:00Z",
            },
            headers=headers,
        )
        assert second.status_code == 200

        session.expire_all()
        contact = (
            session.query(CRMContact)
            .filter(CRMContact.tenant_id == tenant.id, CRMContact.phone == "+14155550100")
            .first()
        )
        conversation = (
            session.query(CRMConversation)
            .filter(CRMConversation.tenant_id == tenant.id, CRMConversation.contact_id == contact.id)
            .first()
        )
        assert contact is not None
        assert conversation is not None
        assert contact.last_activity_at == datetime(2026, 2, 17, 12, 0, 0)
        assert conversation.last_message_at == datetime(2026, 2, 17, 12, 0, 0)
    finally:
        session.close()


def test_stale_stage_change_webhook_does_not_revert_stage(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, owner, stage_new, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-order-stale-hook",
            user_id="owner-order-stale-hook",
            role=UserRole.OWNER,
        )
        stage_quoted = CRMPipelineStage(
            id=f"{tenant.id}-stage-quoted",
            tenant_id=tenant.id,
            name="Quoted",
            position=2,
            color="#f59e0b",
        )
        session.add(stage_quoted)
        session.flush()

        contact = CRMContact(
            tenant_id=tenant.id,
            name="Stale Hook Lead",
            phone="+14155550101",
            email="stale-hook@test.dev",
            source_channel="web",
            owner_user_id=owner.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        deal = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage_quoted.id,
            owner_user_id=owner.id,
            title="Deal stale webhook",
            status=DealStatus.OPEN,
            score=0,
            currency="USD",
            source_channel="web",
            last_activity_at=datetime(2026, 2, 17, 12, 0, 0),
            last_stage_changed_at=datetime(2026, 2, 17, 12, 0, 0),
            metadata_json={},
        )
        session.add(deal)
        contact.primary_deal_id = deal.id
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "order-secret")
        res = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-stage-stale-hook",
                "event_type": "stage_changed",
                "deal_id": deal.id,
                "stage_id": stage_new.id,
                "channel": "web",
                "phone": contact.phone,
                "body": "old stage change",
                "occurred_at": "2026-02-17T11:00:00Z",
            },
            headers=_token_headers("order-secret"),
        )
        assert res.status_code == 200

        session.expire_all()
        refreshed_deal = session.query(CRMDeal).filter(CRMDeal.id == deal.id).first()
        assert refreshed_deal is not None
        assert refreshed_deal.stage_id == stage_quoted.id

        stale_rows = (
            session.query(CRMDealEvent)
            .filter(
                CRMDealEvent.tenant_id == tenant.id,
                CRMDealEvent.deal_id == deal.id,
                CRMDealEvent.event_type == "STALE",
            )
            .all()
        )
        assert len(stale_rows) >= 1
    finally:
        session.close()


def test_stale_stage_change_api_handler_does_not_revert_stage(client, session_factory):
    session = session_factory()
    try:
        tenant, owner, stage_new, token = seed_tenant_with_user(
            session,
            tenant_id="tenant-order-stale-api",
            user_id="owner-order-stale-api",
            role=UserRole.OWNER,
        )
        stage_quoted = CRMPipelineStage(
            id=f"{tenant.id}-stage-quoted",
            tenant_id=tenant.id,
            name="Quoted",
            position=2,
            color="#f59e0b",
        )
        session.add(stage_quoted)
        session.commit()

        contact = client.post(
            "/api/crm/contacts",
            json={
                "name": "Stale API Lead",
                "phone": "+14155550102",
                "email": "stale-api@test.dev",
                "source_channel": "web",
                "owner_user_id": owner.id,
            },
            headers=_auth_headers(token),
        )
        assert contact.status_code == 201
        contact_id = contact.get_json()["id"]

        deal = client.post(
            "/api/crm/deals",
            json={
                "contact_id": contact_id,
                "title": "API stale deal",
                "stage_id": stage_new.id,
                "owner_user_id": owner.id,
                "currency": "USD",
                "source_channel": "web",
            },
            headers=_auth_headers(token),
        )
        assert deal.status_code == 201
        deal_id = deal.get_json()["id"]

        promote = client.patch(
            f"/api/crm/deals/{deal_id}",
            json={
                "stage_id": stage_quoted.id,
                "occurred_at": "2026-02-17T12:00:00Z",
                "stage_reason": "forward",
            },
            headers=_auth_headers(token),
        )
        assert promote.status_code == 200
        assert promote.get_json()["stage_id"] == stage_quoted.id

        stale = client.patch(
            f"/api/crm/deals/{deal_id}",
            json={
                "stage_id": stage_new.id,
                "occurred_at": "2026-02-17T11:00:00Z",
                "stage_reason": "old-message",
            },
            headers=_auth_headers(token),
        )
        assert stale.status_code == 200
        assert stale.get_json()["stage_id"] == stage_quoted.id

        stale_rows = (
            session.query(CRMDealEvent)
            .filter(
                CRMDealEvent.tenant_id == tenant.id,
                CRMDealEvent.deal_id == deal_id,
                CRMDealEvent.event_type == "STALE",
            )
            .all()
        )
        assert len(stale_rows) >= 1
    finally:
        session.close()


def test_stale_event_does_not_change_primary_deal_id(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, owner, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-order-primary",
            user_id="owner-order-primary",
            role=UserRole.OWNER,
        )

        contact = CRMContact(
            tenant_id=tenant.id,
            name="Primary Lead",
            phone="+14155550103",
            email="primary@test.dev",
            source_channel="web",
            owner_user_id=owner.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        primary = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Primary",
            status=DealStatus.OPEN,
            currency="USD",
            source_channel="web",
            last_activity_at=datetime(2026, 2, 17, 12, 0, 0),
            last_stage_changed_at=datetime(2026, 2, 17, 12, 0, 0),
            metadata_json={},
        )
        secondary = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Secondary",
            status=DealStatus.OPEN,
            currency="USD",
            source_channel="web",
            last_activity_at=datetime(2026, 2, 17, 11, 0, 0),
            last_stage_changed_at=datetime(2026, 2, 17, 11, 0, 0),
            metadata_json={},
        )
        session.add_all([primary, secondary])
        session.flush()
        contact.primary_deal_id = primary.id
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "order-secret")
        res = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-primary-stale",
                "event_type": "quote_sent",
                "deal_id": secondary.id,
                "channel": "web",
                "phone": contact.phone,
                "body": "older quote event",
                "occurred_at": "2026-02-17T10:00:00Z",
            },
            headers=_token_headers("order-secret"),
        )
        assert res.status_code == 200

        session.expire_all()
        refreshed_contact = session.query(CRMContact).filter(CRMContact.id == contact.id).first()
        refreshed_secondary = session.query(CRMDeal).filter(CRMDeal.id == secondary.id).first()
        assert refreshed_contact is not None
        assert refreshed_secondary is not None
        assert refreshed_contact.primary_deal_id == primary.id
        assert refreshed_secondary.last_activity_at == datetime(2026, 2, 17, 11, 0, 0)
    finally:
        session.close()
