from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.crm.domain.enums import TaskStatus
from app.crm.models import CRMTask
from app.crm.repositories.base import TenantRepository


class TaskRepository(TenantRepository):
    def __init__(self, session: Session, tenant_id: str):
        super().__init__(session, tenant_id)

    def list(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
        filters: dict[str, Any],
    ) -> tuple[list[CRMTask], int]:
        query = self.query(CRMTask)

        if status := filters.get("status"):
            query = query.filter(CRMTask.status == status)
        if assigned_to := filters.get("assigned_to_user_id"):
            query = query.filter(CRMTask.assigned_to_user_id == assigned_to)
        if due_scope := filters.get("due_scope"):
            now = datetime.utcnow()
            if due_scope == "today":
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                query = query.filter(CRMTask.due_at >= start, CRMTask.due_at < end)
            elif due_scope == "overdue":
                query = query.filter(CRMTask.due_at < now, CRMTask.completed_at.is_(None), CRMTask.status != TaskStatus.DONE)

        total = query.count()
        order_col = getattr(CRMTask, sort_by, CRMTask.created_at)
        order_fn = desc if sort_dir.lower() == "desc" else asc
        rows = (
            query.order_by(order_fn(order_col))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total

    def get(self, task_id: str) -> CRMTask | None:
        return self.get_by_id(CRMTask, task_id)

    def create(self, payload: dict[str, Any]) -> CRMTask:
        task = CRMTask(tenant_id=self.tenant_id, **payload)
        self.session.add(task)
        self.session.flush()
        return task

    def update(self, task: CRMTask, payload: dict[str, Any]) -> CRMTask:
        for key, value in payload.items():
            setattr(task, key, value)
        self.session.flush()
        return task

    def bulk_mark_done(self, task_ids: list[str], completed_at: datetime) -> int:
        count = (
            self.session.query(CRMTask)
            .filter(
                CRMTask.tenant_id == self.tenant_id,
                CRMTask.id.in_(task_ids),
                CRMTask.deleted_at.is_(None),
            )
            .update({"status": "done", "completed_at": completed_at}, synchronize_session=False)
        )
        self.session.flush()
        return count
