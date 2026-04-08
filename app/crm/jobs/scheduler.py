from __future__ import annotations

import time
from datetime import datetime, timedelta

import schedule
from zoneinfo import ZoneInfo

from app.crm.domain.enums import AutomationTrigger
from app.crm.models import CRMAutomation, CRMContact, CRMDeal, CRMTenant
from app.crm.services.ab_variant_service import ABVariantService
from app.crm.services.automation_service import AutomationService
from app.crm.services.reporting_service import ReportingService
from app.crm.services.scoring_service import ScoringService
from app.crm.services.sla_service import SLAService
from app.db.session import SessionLocal


def _run_sla_scan() -> None:
    session = SessionLocal()
    try:
        tenant_ids = [row.id for row in session.query(CRMTenant).filter(CRMTenant.is_active.is_(True)).all()]
        for tenant_id in tenant_ids:
            SLAService(session, tenant_id).check_stage_breaches()
        session.commit()
    finally:
        session.close()


def _run_inactivity_automations() -> None:
    session = SessionLocal()
    try:
        tenants = session.query(CRMTenant).filter(CRMTenant.is_active.is_(True)).all()

        for tenant in tenants:
            automations = (
                session.query(CRMAutomation)
                .filter(
                    CRMAutomation.tenant_id == tenant.id,
                    CRMAutomation.enabled.is_(True),
                    CRMAutomation.trigger_type == AutomationTrigger.INACTIVITY_TIMER,
                )
                .all()
            )
            if not automations:
                continue

            minimum_minutes = min(int((a.conditions_json or {}).get("inactivity_minutes", 60)) for a in automations)
            threshold = datetime.utcnow() - timedelta(minutes=minimum_minutes)
            contacts = (
                session.query(CRMContact)
                .filter(
                    CRMContact.tenant_id == tenant.id,
                    CRMContact.deleted_at.is_(None),
                    CRMContact.last_activity_at.is_not(None),
                    CRMContact.last_activity_at <= threshold,
                )
                .limit(200)
                .all()
            )

            service = AutomationService(session, tenant.id)
            now = datetime.utcnow()
            for contact in contacts:
                inactivity_minutes = int(max(0, (now - contact.last_activity_at).total_seconds() // 60))
                trigger_event_key = (
                    f"inactivity:{contact.id}:{int(contact.last_activity_at.timestamp())}:{inactivity_minutes // 30}"
                )
                service.run_trigger(
                    AutomationTrigger.INACTIVITY_TIMER,
                    {
                        "contact_id": contact.id,
                        "channel": contact.source_channel,
                        "score": contact.score,
                        "tags": [],
                        "inactivity_minutes": inactivity_minutes,
                        "source": "scheduler",
                    },
                    trigger_event_id=trigger_event_key,
                    trigger_event_key=trigger_event_key,
                )

        session.commit()
    finally:
        session.close()


def _run_scoring_recompute() -> None:
    session = SessionLocal()
    try:
        tenant_ids = [row.id for row in session.query(CRMTenant).filter(CRMTenant.is_active.is_(True)).all()]
        for tenant_id in tenant_ids:
            scoring = ScoringService(session, tenant_id)
            deal_ids = [row.id for row in session.query(CRMDeal).filter(CRMDeal.tenant_id == tenant_id).all()]
            for deal_id in deal_ids:
                scoring.recompute_deal_score(deal_id)
        session.commit()
    finally:
        session.close()


def _run_daily_rollups() -> None:
    session = SessionLocal()
    try:
        tenants = session.query(CRMTenant).filter(CRMTenant.is_active.is_(True)).all()
        for tenant in tenants:
            tz = ZoneInfo(tenant.timezone or "UTC")
            local_now = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
            bucket_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            bucket_prev = bucket_local - timedelta(days=1)

            date_from = bucket_prev.replace(tzinfo=None)
            date_to = bucket_local.replace(tzinfo=None)

            service = ReportingService(session, tenant.id, tenant.timezone or "UTC")
            service.upsert_daily_rollup(bucket_date=bucket_prev.replace(tzinfo=None), date_from=date_from, date_to=date_to)

        session.commit()
    finally:
        session.close()


def _run_ab_autopromote() -> None:
    session = SessionLocal()
    try:
        tenants = session.query(CRMTenant).filter(CRMTenant.is_active.is_(True)).all()
        for tenant in tenants:
            ABVariantService(session, tenant.id).evaluate(apply=True)
        session.commit()
    finally:
        session.close()


def run_crm_scheduler() -> None:
    schedule.every(10).minutes.do(_run_sla_scan)
    schedule.every(5).minutes.do(_run_inactivity_automations)
    schedule.every(30).minutes.do(_run_scoring_recompute)
    schedule.every().day.at("00:10").do(_run_daily_rollups)
    schedule.every().day.at("00:20").do(_run_ab_autopromote)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    run_crm_scheduler()
