from __future__ import annotations

from sqlalchemy.orm import Session

from app.crm.models import CRMPlaybook


class PlaybookService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def list(self, objection_key: str | None = None, channel: str | None = None) -> list[CRMPlaybook]:
        query = self.session.query(CRMPlaybook).filter(CRMPlaybook.tenant_id == self.tenant_id)
        if objection_key:
            query = query.filter(CRMPlaybook.objection_key == objection_key)
        if channel:
            query = query.filter(CRMPlaybook.channel == channel)
        return query.order_by(CRMPlaybook.created_at.desc()).all()

    def get(self, playbook_id: str) -> CRMPlaybook | None:
        return (
            self.session.query(CRMPlaybook)
            .filter(CRMPlaybook.tenant_id == self.tenant_id, CRMPlaybook.id == playbook_id)
            .first()
        )

    def create(self, payload: dict) -> CRMPlaybook:
        row = CRMPlaybook(tenant_id=self.tenant_id, **payload)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: CRMPlaybook, payload: dict) -> CRMPlaybook:
        for key, value in payload.items():
            setattr(row, key, value)
        self.session.flush()
        return row
