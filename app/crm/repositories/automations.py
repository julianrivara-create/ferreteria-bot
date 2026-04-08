from __future__ import annotations

from sqlalchemy.orm import Session

from app.crm.domain.enums import AutomationTrigger
from app.crm.models import CRMAutomation, CRMAutomationRun
from app.crm.repositories.base import TenantRepository


class AutomationRepository(TenantRepository):
    def __init__(self, session: Session, tenant_id: str):
        super().__init__(session, tenant_id)

    def list(self) -> list[CRMAutomation]:
        return self.query(CRMAutomation, include_deleted=True).order_by(CRMAutomation.created_at.desc()).all()

    def list_for_trigger(self, trigger: AutomationTrigger | str) -> list[CRMAutomation]:
        return self.query(CRMAutomation, include_deleted=True).filter(
            CRMAutomation.trigger_type == trigger,
            CRMAutomation.enabled.is_(True),
        ).all()

    def get(self, automation_id: str) -> CRMAutomation | None:
        return self.get_by_id(CRMAutomation, automation_id, include_deleted=True)

    def list_runs(self, *, automation_id: str | None = None, limit: int = 100) -> list[CRMAutomationRun]:
        query = self.query(CRMAutomationRun, include_deleted=True).order_by(CRMAutomationRun.executed_at.desc())
        if automation_id:
            query = query.filter(CRMAutomationRun.automation_id == automation_id)
        return query.limit(limit).all()

    def create(self, payload: dict) -> CRMAutomation:
        automation = CRMAutomation(tenant_id=self.tenant_id, **payload)
        self.session.add(automation)
        self.session.flush()
        return automation

    def update(self, automation: CRMAutomation, payload: dict) -> CRMAutomation:
        for key, value in payload.items():
            setattr(automation, key, value)
        self.session.flush()
        return automation

    def add_run(self, payload: dict) -> CRMAutomationRun:
        row = CRMAutomationRun(tenant_id=self.tenant_id, **payload)
        self.session.add(row)
        self.session.flush()
        return row
