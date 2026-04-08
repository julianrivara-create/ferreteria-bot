from __future__ import annotations

from app.crm.domain.enums import AutomationTrigger, DealStatus
from app.crm.models import CRMAutomation, CRMAutomationRun, CRMContact, CRMDeal, CRMTask
from app.crm.services.automation_service import AutomationService
from tests.crm.utils import seed_tenant_with_user


def _seed_contact_and_deal(session, tenant_id: str, owner_user_id: str, stage_id: str):
    contact = CRMContact(
        tenant_id=tenant_id,
        name="Auto Lead",
        phone="+14155556001",
        email="auto-lead@test.dev",
        source_channel="whatsapp",
        owner_user_id=owner_user_id,
        status="lead",
        score=50,
        metadata_json={},
    )
    session.add(contact)
    session.flush()

    deal = CRMDeal(
        tenant_id=tenant_id,
        contact_id=contact.id,
        stage_id=stage_id,
        owner_user_id=owner_user_id,
        title="Auto Deal",
        status=DealStatus.OPEN,
        score=40,
        amount_estimated=1000,
        currency="USD",
        source_channel="whatsapp",
        metadata_json={},
    )
    session.add(deal)
    session.flush()
    return contact, deal


def test_automation_rule_event_idempotency(session_factory):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auto-idem",
            user_id="owner-auto-idem",
        )
        contact, deal = _seed_contact_and_deal(session, tenant.id, user.id, stage.id)

        automation = CRMAutomation(
            tenant_id=tenant.id,
            name="create-task-on-quote",
            trigger_type=AutomationTrigger.QUOTE_SENT,
            enabled=True,
            cooldown_minutes=0,
            conditions_json={},
            actions_json=[{"type": "create_task", "title": "Follow quote", "due_in_minutes": 10}],
            created_by_user_id=user.id,
        )
        session.add(automation)
        session.commit()

        service = AutomationService(session, tenant.id)
        event = {
            "contact_id": contact.id,
            "deal_id": deal.id,
            "channel": "whatsapp",
            "score": 50,
            "owner_user_id": user.id,
        }

        runs_first = service.run_trigger(
            AutomationTrigger.QUOTE_SENT,
            event,
            trigger_event_id="evt-auto-1",
            trigger_event_key="evt-auto-1",
        )
        session.commit()

        runs_second = service.run_trigger(
            AutomationTrigger.QUOTE_SENT,
            event,
            trigger_event_id="evt-auto-1",
            trigger_event_key="evt-auto-1",
        )
        session.commit()

        assert len(runs_first) == 1
        assert len(runs_second) == 0
        assert session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id, CRMTask.deal_id == deal.id).count() == 1
        assert session.query(CRMAutomationRun).filter(CRMAutomationRun.tenant_id == tenant.id).count() == 1
    finally:
        session.close()


def test_automation_dry_run_records_without_side_effects(session_factory):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auto-dry",
            user_id="owner-auto-dry",
        )
        contact, deal = _seed_contact_and_deal(session, tenant.id, user.id, stage.id)

        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="dry-run-rule",
                trigger_type=AutomationTrigger.QUOTE_SENT,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={},
                actions_json=[{"type": "create_task", "title": "Should not persist"}],
                created_by_user_id=user.id,
            )
        )
        session.commit()

        runs = AutomationService(session, tenant.id).run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "deal_id": deal.id,
                "channel": "whatsapp",
                "score": 10,
            },
            trigger_event_id="evt-dry-1",
            trigger_event_key="evt-dry-1",
            dry_run=True,
        )
        session.commit()

        assert len(runs) == 1
        assert runs[0].status == "dry_run"
        assert session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id).count() == 0
    finally:
        session.close()


def test_automation_loop_guard_skips_recursive_events(session_factory):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auto-loop",
            user_id="owner-auto-loop",
        )
        contact, deal = _seed_contact_and_deal(session, tenant.id, user.id, stage.id)

        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="loop-guard-rule",
                trigger_type=AutomationTrigger.STAGE_CHANGED,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={},
                actions_json=[{"type": "create_task", "title": "No loop"}],
                created_by_user_id=user.id,
            )
        )
        session.commit()

        runs = AutomationService(session, tenant.id).run_trigger(
            AutomationTrigger.STAGE_CHANGED,
            {
                "contact_id": contact.id,
                "deal_id": deal.id,
                "source": "automation",
                "automation_hop": 1,
            },
            trigger_event_id="evt-loop-1",
            trigger_event_key="evt-loop-1",
        )
        session.commit()

        assert runs == []
        assert session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id).count() == 0
    finally:
        session.close()


def test_automation_action_cap_throttles_execution(session_factory):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-auto-cap",
            user_id="owner-auto-cap",
        )
        tenant.integration_settings = {"max_automation_actions_per_minute": 1}
        contact, deal = _seed_contact_and_deal(session, tenant.id, user.id, stage.id)

        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="cap-rule",
                trigger_type=AutomationTrigger.QUOTE_SENT,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={},
                actions_json=[
                    {"type": "create_task", "title": "A"},
                    {"type": "create_reminder", "title": "B"},
                ],
                created_by_user_id=user.id,
            )
        )
        session.commit()

        runs = AutomationService(session, tenant.id).run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "deal_id": deal.id,
                "channel": "whatsapp",
                "score": 90,
            },
            trigger_event_id="evt-cap-1",
            trigger_event_key="evt-cap-1",
        )
        session.commit()

        assert len(runs) == 1
        assert runs[0].status == "throttled"
        assert session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id).count() == 0
    finally:
        session.close()
