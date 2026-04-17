from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.crm.domain.enums import DealStatus, TaskStatus
from app.crm.models import CRMDeal, CRMPipelineStage, CRMSLABreach, CRMTask
from app.crm.time import utc_now_naive


class SLAService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def check_stage_breaches(self) -> list[CRMSLABreach]:
        now = utc_now_naive()
        stages = (
            self.session.query(CRMPipelineStage)
            .filter(CRMPipelineStage.tenant_id == self.tenant_id, CRMPipelineStage.sla_hours.is_not(None))
            .all()
        )
        if not stages:
            return []

        stages_map = {s.id: s for s in stages}

        deals = (
            self.session.query(CRMDeal)
            .filter(
                CRMDeal.tenant_id == self.tenant_id,
                CRMDeal.deleted_at.is_(None),
                CRMDeal.status == DealStatus.OPEN,
                CRMDeal.stage_id.in_(list(stages_map.keys())),
            )
            .all()
        )

        breaches: list[CRMSLABreach] = []

        for deal in deals:
            stage = stages_map.get(deal.stage_id)
            if not stage or not stage.sla_hours:
                continue

            threshold = now - timedelta(hours=stage.sla_hours)
            if deal.updated_at > threshold:
                continue

            has_recent_task = (
                self.session.query(CRMTask)
                .filter(
                    CRMTask.tenant_id == self.tenant_id,
                    CRMTask.deal_id == deal.id,
                    CRMTask.created_at >= threshold,
                    CRMTask.deleted_at.is_(None),
                )
                .count()
            ) > 0
            if has_recent_task:
                continue

            existing = (
                self.session.query(CRMSLABreach)
                .filter(
                    CRMSLABreach.tenant_id == self.tenant_id,
                    CRMSLABreach.deal_id == deal.id,
                    CRMSLABreach.stage_id == deal.stage_id,
                    CRMSLABreach.status == "open",
                )
                .first()
            )
            if existing:
                breaches.append(existing)
                continue

            breach = CRMSLABreach(
                tenant_id=self.tenant_id,
                deal_id=deal.id,
                stage_id=deal.stage_id,
                threshold_hours=stage.sla_hours,
                metadata_json={"deal_updated_at": deal.updated_at.isoformat()},
            )
            self.session.add(breach)

            task = CRMTask(
                tenant_id=self.tenant_id,
                contact_id=deal.contact_id,
                deal_id=deal.id,
                assigned_to_user_id=deal.owner_user_id or "system",
                created_by_user_id="system",
                title=f"SLA breach follow-up ({stage.name})",
                description=f"Deal exceeded {stage.sla_hours}h without follow-up in stage {stage.name}.",
                status=TaskStatus.TODO,
                priority="high",
                due_at=now + timedelta(hours=1),
                reminder_at=now,
                metadata_json={"source": "sla_breach", "stage_id": stage.id},
            )
            self.session.add(task)

            breaches.append(breach)

        self.session.flush()
        return breaches

    def resolve_breach(self, breach_id: str) -> CRMSLABreach | None:
        breach = (
            self.session.query(CRMSLABreach)
            .filter(CRMSLABreach.tenant_id == self.tenant_id, CRMSLABreach.id == breach_id)
            .first()
        )
        if breach is None:
            return None
        breach.status = "resolved"
        breach.resolved_at = utc_now_naive()
        self.session.flush()
        return breach
