from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crm.models import CRMWebhookEvent
from app.crm.repositories.base import TenantRepository
from app.crm.time import utc_now_naive


class WebhookEventRepository(TenantRepository):
    def __init__(self, session: Session, tenant_id: str):
        super().__init__(session, tenant_id)

    def record_once(self, source: str, event_type: str, event_key: str, payload: dict) -> tuple[CRMWebhookEvent, bool]:
        now = utc_now_naive()
        row = CRMWebhookEvent(
            tenant_id=self.tenant_id,
            source=source,
            event_type=event_type,
            event_key=event_key,
            payload=payload,
            status="received",
            last_received_at=now,
        )
        self.session.add(row)
        try:
            self.session.flush()
            return row, True
        except IntegrityError:
            self.session.rollback()
            existing = (
                self.query(CRMWebhookEvent, include_deleted=True)
                .filter(
                    CRMWebhookEvent.source == source,
                    CRMWebhookEvent.event_type == event_type,
                    CRMWebhookEvent.event_key == event_key,
                )
                .first()
            )
            if existing is None:
                raise
            existing.duplicate_count = (existing.duplicate_count or 0) + 1
            existing.last_received_at = now
            existing.status = "duplicate"
            self.session.flush()
            return existing, False

    def mark_processed(self, row: CRMWebhookEvent) -> None:
        row.status = "processed"
        row.processed_at = utc_now_naive()
        row.error_message = None
        self.session.flush()

    def mark_failed(self, row: CRMWebhookEvent, error: str) -> None:
        row.status = "failed"
        row.processed_at = utc_now_naive()
        row.error_message = error[:1000]
        self.session.flush()

    def get(self, event_id: str) -> CRMWebhookEvent | None:
        return self.get_by_id(CRMWebhookEvent, event_id, include_deleted=True)

    def list(self, *, status: str | None = None, limit: int = 100) -> list[CRMWebhookEvent]:
        query = self.query(CRMWebhookEvent, include_deleted=True).order_by(CRMWebhookEvent.created_at.desc())
        if status:
            query = query.filter(CRMWebhookEvent.status == status)
        return query.limit(limit).all()
