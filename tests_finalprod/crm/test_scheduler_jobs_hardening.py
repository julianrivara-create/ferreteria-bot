from __future__ import annotations

from datetime import datetime, timedelta

import app.crm.jobs.scheduler as scheduler
from app.crm.domain.enums import AutomationTrigger, DealStatus
from app.crm.models import (
    CRMAutomation,
    CRMContact,
    CRMDailyKpiRollup,
    CRMDeal,
    CRMDealScoreEvent,
    CRMTask,
)
from tests.crm.utils import seed_tenant_with_user


def test_inactivity_job_is_idempotent(session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-sched-inactivity",
            user_id="owner-sched-inactivity",
        )
        session.add(
            CRMAutomation(
                tenant_id=tenant.id,
                name="inactivity-followup",
                trigger_type=AutomationTrigger.INACTIVITY_TIMER,
                enabled=True,
                cooldown_minutes=0,
                conditions_json={"inactivity_minutes": 60},
                actions_json=[{"type": "create_task", "title": "Follow up inactive"}],
                created_by_user_id=user.id,
            )
        )
        session.add(
            CRMContact(
                tenant_id=tenant.id,
                name="Inactive Lead",
                phone="+14155557001",
                email="inactive-lead@test.dev",
                source_channel="whatsapp",
                owner_user_id=user.id,
                status="lead",
                score=0,
                last_activity_at=datetime.utcnow() - timedelta(hours=2),
                metadata_json={},
            )
        )
        session.commit()

        monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
        scheduler._run_inactivity_automations()
        scheduler._run_inactivity_automations()

        assert session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id).count() == 1
    finally:
        session.close()


def test_scoring_recompute_job_corrects_deal_score(session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-sched-scoring",
            user_id="owner-sched-scoring",
        )
        contact = CRMContact(
            tenant_id=tenant.id,
            name="Scored Lead",
            phone="+14155557002",
            email="scored-lead@test.dev",
            source_channel="whatsapp",
            owner_user_id=user.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        deal = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=user.id,
            title="Scored Deal",
            status=DealStatus.OPEN,
            score=999,
            amount_estimated=100,
            currency="USD",
            source_channel="whatsapp",
            metadata_json={},
        )
        session.add(deal)
        session.flush()

        session.add(
            CRMDealScoreEvent(
                tenant_id=tenant.id,
                deal_id=deal.id,
                rule_id=None,
                signal_key="inbound_message",
                delta=10,
                previous_score=0,
                new_score=10,
                reason="plus",
                metadata_json={},
            )
        )
        session.add(
            CRMDealScoreEvent(
                tenant_id=tenant.id,
                deal_id=deal.id,
                rule_id=None,
                signal_key="no_reply",
                delta=-2,
                previous_score=10,
                new_score=8,
                reason="minus",
                metadata_json={},
            )
        )
        session.commit()

        monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
        scheduler._run_scoring_recompute()

        refreshed = session.query(CRMDeal).filter(CRMDeal.id == deal.id).first()
        assert refreshed is not None
        assert refreshed.score == 8
    finally:
        session.close()


def test_daily_rollup_job_is_idempotent(session_factory, monkeypatch):
    session = session_factory()
    try:
        tenant, user, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-sched-rollup",
            user_id="owner-sched-rollup",
        )
        tenant.timezone = "UTC"
        session.add(
            CRMContact(
                tenant_id=tenant.id,
                name="Rollup Lead",
                phone="+14155557003",
                email="rollup-lead@test.dev",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=0,
                metadata_json={},
            )
        )
        session.commit()

        monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
        scheduler._run_daily_rollups()
        scheduler._run_daily_rollups()

        assert session.query(CRMDailyKpiRollup).filter(CRMDailyKpiRollup.tenant_id == tenant.id).count() == 1
    finally:
        session.close()
