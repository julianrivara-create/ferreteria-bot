from __future__ import annotations

from typing import Any

from flask import g, has_request_context, request
from sqlalchemy.orm import Session

from app.crm.models import CRMAuditLog


class AuditService:
    def __init__(self, session: Session, tenant_id: str, actor_user_id: str | None):
        self.session = session
        self.tenant_id = tenant_id
        self.actor_user_id = actor_user_id

    def log(
        self,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> CRMAuditLog:
        resolved_request_id = request_id or self._resolve_request_id()
        row = CRMAuditLog(
            tenant_id=self.tenant_id,
            actor_user_id=self.actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_data=before_data,
            after_data=after_data,
            metadata_json=metadata_json or {},
            request_id=resolved_request_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    @staticmethod
    def _resolve_request_id() -> str | None:
        if not has_request_context():
            return None
        if getattr(g, "request_id", None):
            return g.request_id
        return request.headers.get("X-Request-Id")
