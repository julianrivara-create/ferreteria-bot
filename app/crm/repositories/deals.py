from __future__ import annotations

from typing import Any

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.crm.models import CRMDeal
from app.crm.repositories.base import TenantRepository


class DealRepository(TenantRepository):
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
    ) -> tuple[list[CRMDeal], int]:
        query = self.query(CRMDeal)

        if stage_id := filters.get("stage_id"):
            query = query.filter(CRMDeal.stage_id == stage_id)
        if status := filters.get("status"):
            query = query.filter(CRMDeal.status == status)
        if owner_user_id := filters.get("owner_user_id"):
            query = query.filter(CRMDeal.owner_user_id == owner_user_id)
        if contact_id := filters.get("contact_id"):
            query = query.filter(CRMDeal.contact_id == contact_id)

        total = query.count()
        order_col = getattr(CRMDeal, sort_by, CRMDeal.created_at)
        order_fn = desc if sort_dir.lower() == "desc" else asc
        rows = (
            query.order_by(order_fn(order_col))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total

    def get(self, deal_id: str) -> CRMDeal | None:
        return self.get_by_id(CRMDeal, deal_id)

    def create(self, payload: dict[str, Any]) -> CRMDeal:
        deal = CRMDeal(tenant_id=self.tenant_id, **payload)
        self.session.add(deal)
        self.session.flush()
        return deal

    def update(self, deal: CRMDeal, payload: dict[str, Any]) -> CRMDeal:
        for key, value in payload.items():
            setattr(deal, key, value)
        self.session.flush()
        return deal
