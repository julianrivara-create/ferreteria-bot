from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session


@dataclass
class PaginatedResult:
    items: list[Any]
    total: int
    page: int
    page_size: int


class TenantRepository:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def _tenant_column(self, model: Any):
        if not hasattr(model, "tenant_id"):
            raise ValueError(f"{model} is not tenant-scoped")
        return getattr(model, "tenant_id")

    def query(self, model: Any, *, include_deleted: bool = False):
        tenant_col = self._tenant_column(model)
        query = self.session.query(model).filter(tenant_col == self.tenant_id)

        # Soft-deleted rows are hidden by default for safety.
        if not include_deleted and hasattr(model, "deleted_at"):
            query = query.filter(getattr(model, "deleted_at").is_(None))

        return query

    def get_by_id(self, model: Any, row_id: str, *, include_deleted: bool = False):
        if not hasattr(model, "id"):
            raise ValueError(f"{model} does not expose id")
        return self.query(model, include_deleted=include_deleted).filter(getattr(model, "id") == row_id).first()

    def assert_tenant(self, row: Any) -> None:
        row_tenant = getattr(row, "tenant_id", None)
        if row_tenant and row_tenant != self.tenant_id:
            raise ValueError("Cross-tenant access denied")

    def _safe_order_column(self, model: Any, sort_by: str):
        return getattr(model, sort_by, getattr(model, "created_at"))

    def _apply_pagination(
        self,
        query,
        *,
        model: Any,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
    ) -> PaginatedResult:
        total_count = query.count()
        order_col = self._safe_order_column(model, sort_by)
        order_fn = desc if sort_dir.lower() == "desc" else asc
        paged = query.order_by(order_fn(order_col)).offset((page - 1) * page_size).limit(page_size).all()
        return PaginatedResult(items=paged, total=total_count, page=page, page_size=page_size)
