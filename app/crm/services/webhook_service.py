from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.crm.repositories.webhooks import WebhookEventRepository


class WebhookIngestionService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = WebhookEventRepository(session, tenant_id)

    def ingest(
        self,
        *,
        source: str,
        event_type: str,
        event_key: str,
        payload: dict,
        handler: Callable[[dict], dict | None],
    ) -> tuple[bool, dict]:
        row, created = self.repo.record_once(source=source, event_type=event_type, event_key=event_key, payload=payload)
        if not created:
            return False, {"status": "duplicate", "id": row.id}

        try:
            result = handler(payload) or {}
            self.repo.mark_processed(row)
            return True, {"status": "processed", "id": row.id, **result}
        except Exception as exc:  # pragma: no cover - defensive branch
            self.repo.mark_failed(row, str(exc))
            raise
