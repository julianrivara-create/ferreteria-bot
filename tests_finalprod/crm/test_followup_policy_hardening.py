from __future__ import annotations

from datetime import datetime, timedelta

import app.crm.api.routes as crm_routes_module
import app.crm.services.automation_service as automation_module
from app.crm.domain.enums import AutomationTrigger, DealStatus, TaskStatus, UserRole
from app.crm.models import (
    CRMAutomation,
    CRMContact,
    CRMConversation,
    CRMDeal,
    CRMMessageEvent,
    CRMOutboundDraft,
    CRMTask,
)
from app.crm.services.automation_service import AutomationService
from tests.crm.utils import seed_tenant_with_user


def _token_headers(secret: str) -> dict:
    return {"Content-Type": "application/json", "X-CRM-Webhook-Token": secret}


def test_followup_scheduled_during_quiet_hours_is_shifted_to_next_allowed_time(session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, owner, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-followup-quiet",
            user_id="owner-followup-quiet",
            role=UserRole.OWNER,
        )
        tenant.timezone = "America/Argentina/Buenos_Aires"
        tenant.quiet_hours_start = "22:00"
        tenant.quiet_hours_end = "08:00"
        tenant.followup_min_interval_minutes = 60

        contact = CRMContact(
            tenant_id=tenant.id,
            name="Quiet Lead",
            phone="+14155556010",
            email="quiet@test.dev",
            source_channel="web",
            owner_user_id=owner.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        conversation = CRMConversation(
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel="web",
            external_id="conv-quiet",
            started_at=datetime(2026, 2, 17, 3, 0, 0),
            last_message_at=datetime(2026, 2, 17, 3, 0, 0),
            metadata_json={},
        )
        session.add(conversation)
        session.flush()

        deal = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Quiet Deal",
            status=DealStatus.OPEN,
            score=0,
            currency="USD",
            source_channel="web",
            metadata_json={},
        )
        session.add(deal)
        session.flush()

        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="quiet-followup",
                trigger_type=AutomationTrigger.QUOTE_SENT,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={},
                actions_json=[
                    {
                        "type": "schedule_outbound_draft",
                        "body": "Seguimiento",
                        "schedule_in_minutes": 0,
                        "is_followup": True,
                    }
                ],
                created_by_user_id=owner.id,
            )
        )
        session.commit()

        class FixedDateTime(datetime):
            @classmethod
            def utcnow(cls):
                # 03:30 UTC => 00:30 local (America/Argentina/Buenos_Aires), inside quiet hours.
                return datetime(2026, 2, 17, 3, 30, 0)

        monkeypatch.setattr(automation_module, "datetime", FixedDateTime)

        runs = AutomationService(session, tenant.id).run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "conversation_id": conversation.id,
                "deal_id": deal.id,
                "channel": "web",
                "owner_user_id": owner.id,
            },
            trigger_event_id="evt-quiet-1",
            trigger_event_key="evt-quiet-1",
        )
        session.commit()

        assert len(runs) == 1
        draft = (
            session.query(CRMOutboundDraft)
            .filter(CRMOutboundDraft.tenant_id == tenant.id, CRMOutboundDraft.conversation_id == conversation.id)
            .first()
        )
        assert draft is not None
        assert draft.scheduled_for == datetime(2026, 2, 17, 11, 0, 0)
    finally:
        session.close()


def test_followup_cooldown_prevents_duplicate_scheduling(session_factory):
    session = session_factory()
    try:
        tenant, owner, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-followup-cooldown",
            user_id="owner-followup-cooldown",
            role=UserRole.OWNER,
        )
        tenant.followup_min_interval_minutes = 180

        contact = CRMContact(
            tenant_id=tenant.id,
            name="Cooldown Lead",
            phone="+14155556011",
            email="cooldown@test.dev",
            source_channel="web",
            owner_user_id=owner.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        conversation = CRMConversation(
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel="web",
            external_id="conv-cooldown",
            metadata_json={},
        )
        session.add(conversation)
        session.flush()

        deal = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Cooldown Deal",
            status=DealStatus.OPEN,
            score=0,
            currency="USD",
            source_channel="web",
            metadata_json={},
        )
        session.add(deal)
        session.flush()

        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="cooldown-followup",
                trigger_type=AutomationTrigger.QUOTE_SENT,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={},
                actions_json=[{"type": "schedule_outbound_draft", "body": "Seguimiento", "schedule_in_minutes": 0}],
                created_by_user_id=owner.id,
            )
        )
        session.commit()

        service = AutomationService(session, tenant.id)
        first = service.run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "conversation_id": conversation.id,
                "deal_id": deal.id,
                "channel": "web",
                "owner_user_id": owner.id,
            },
            trigger_event_id="evt-cooldown-1",
            trigger_event_key="evt-cooldown-1",
        )
        session.commit()
        second = service.run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "conversation_id": conversation.id,
                "deal_id": deal.id,
                "channel": "web",
                "owner_user_id": owner.id,
            },
            trigger_event_id="evt-cooldown-2",
            trigger_event_key="evt-cooldown-2",
        )
        session.commit()

        drafts = (
            session.query(CRMOutboundDraft)
            .filter(CRMOutboundDraft.tenant_id == tenant.id, CRMOutboundDraft.conversation_id == conversation.id)
            .all()
        )
        assert len(first) == 1
        assert len(second) == 1
        assert len(drafts) == 1
        assert second[0].result_payload["actions"][0]["status"] == "suppressed_by_cooldown"
    finally:
        session.close()


def test_text_reply_stops_future_followups(client, session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, owner, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-followup-stop",
            user_id="owner-followup-stop",
            role=UserRole.OWNER,
        )
        contact = CRMContact(
            tenant_id=tenant.id,
            name="Stop Lead",
            phone="+14155556012",
            email="stop@test.dev",
            source_channel="web",
            owner_user_id=owner.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        conversation = CRMConversation(
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel="web",
            external_id="conv-stop",
            metadata_json={},
        )
        session.add(conversation)
        session.flush()

        deal = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Stop Deal",
            status=DealStatus.OPEN,
            score=0,
            currency="USD",
            source_channel="web",
            metadata_json={},
        )
        session.add(deal)
        session.flush()

        session.add(
            CRMOutboundDraft(
                tenant_id=tenant.id,
                contact_id=contact.id,
                conversation_id=conversation.id,
                channel="web",
                body="followup pending",
                scheduled_for=None,
                status="scheduled",
                metadata_json={"kind": "followup"},
            )
        )
        session.add(
            CRMTask(
                tenant_id=tenant.id,
                contact_id=contact.id,
                deal_id=deal.id,
                assigned_to_user_id=owner.id,
                created_by_user_id=owner.id,
                title="Follow-up task",
                status=TaskStatus.TODO,
                priority="medium",
                metadata_json={"kind": "followup"},
            )
        )
        session.commit()

        monkeypatch.setattr(crm_routes_module.settings, "CRM_WEBHOOK_SECRET", "followup-secret")
        headers = _token_headers("followup-secret")

        reaction = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-stop-reaction",
                "event_type": "inbound_message",
                "channel": "web",
                "phone": contact.phone,
                "body": "👍",
                "message_subtype": "reaction",
                "occurred_at": "2026-02-17T12:00:00Z",
            },
            headers=headers,
        )
        assert reaction.status_code == 200

        session.expire_all()
        draft_after_reaction = (
            session.query(CRMOutboundDraft)
            .filter(CRMOutboundDraft.tenant_id == tenant.id, CRMOutboundDraft.conversation_id == conversation.id)
            .first()
        )
        task_after_reaction = (
            session.query(CRMTask)
            .filter(CRMTask.tenant_id == tenant.id, CRMTask.contact_id == contact.id)
            .first()
        )
        assert draft_after_reaction is not None
        assert task_after_reaction is not None
        assert draft_after_reaction.status == "scheduled"
        assert task_after_reaction.status == TaskStatus.TODO

        text = client.post(
            "/api/crm/messages/webhook",
            json={
                "tenant_id": tenant.id,
                "source": "bot",
                "event_id": "evt-stop-text",
                "event_type": "inbound_message",
                "channel": "web",
                "phone": contact.phone,
                "body": "Dale, te respondo ahora",
                "occurred_at": "2026-02-17T12:05:00Z",
            },
            headers=headers,
        )
        assert text.status_code == 200

        session.expire_all()
        draft_after_text = (
            session.query(CRMOutboundDraft)
            .filter(CRMOutboundDraft.tenant_id == tenant.id, CRMOutboundDraft.conversation_id == conversation.id)
            .first()
        )
        task_after_text = (
            session.query(CRMTask)
            .filter(CRMTask.tenant_id == tenant.id, CRMTask.contact_id == contact.id)
            .first()
        )
        stop_event = (
            session.query(CRMMessageEvent)
            .filter(
                CRMMessageEvent.tenant_id == tenant.id,
                CRMMessageEvent.conversation_id == conversation.id,
                CRMMessageEvent.event_type == "followup_stop_decision",
            )
            .order_by(CRMMessageEvent.created_at.desc())
            .first()
        )
        assert draft_after_text is not None
        assert task_after_text is not None
        assert stop_event is not None
        assert draft_after_text.status == "canceled"
        assert task_after_text.status == TaskStatus.CANCELED
        assert (stop_event.payload or {}).get("reason") == "text_reply"
    finally:
        session.close()
