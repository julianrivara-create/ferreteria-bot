from __future__ import annotations

from typing import Any

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.orm import Session

from app.crm.models import CRMContact, CRMContactTag, CRMTag
from app.crm.repositories.base import TenantRepository


class ContactRepository(TenantRepository):
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
    ) -> tuple[list[CRMContact], int]:
        query = self.query(CRMContact)

        if tag := filters.get("tag"):
            query = query.join(
                CRMContactTag,
                and_(
                    CRMContactTag.tenant_id == CRMContact.tenant_id,
                    CRMContactTag.contact_id == CRMContact.id,
                ),
            ).join(
                CRMTag,
                and_(CRMTag.tenant_id == CRMContactTag.tenant_id, CRMTag.id == CRMContactTag.tag_id),
            ).filter(CRMTag.name == tag)

        if stage := filters.get("stage"):
            query = query.filter(CRMContact.metadata_json["stage"].astext == stage)

        if last_activity_after := filters.get("last_activity_after"):
            query = query.filter(CRMContact.last_activity_at >= last_activity_after)

        if min_score := filters.get("min_score"):
            query = query.filter(CRMContact.score >= int(min_score))

        if search := filters.get("search"):
            pattern = f"%{str(search).lower()}%"
            query = query.filter(
                or_(
                    func.lower(CRMContact.name).like(pattern),
                    func.lower(CRMContact.email).like(pattern),
                    CRMContact.phone.like(f"%{search}%"),
                )
            )

        total = query.count()

        order_col = getattr(CRMContact, sort_by, CRMContact.created_at)
        order_fn = desc if sort_dir.lower() == "desc" else asc

        rows = (
            query.order_by(order_fn(order_col))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return rows, total

    def get(self, contact_id: str) -> CRMContact | None:
        return self.get_by_id(CRMContact, contact_id)

    def create(self, payload: dict[str, Any]) -> CRMContact:
        contact = CRMContact(tenant_id=self.tenant_id, **payload)
        self.session.add(contact)
        self.session.flush()
        return contact

    def update(self, contact: CRMContact, payload: dict[str, Any]) -> CRMContact:
        for key, value in payload.items():
            setattr(contact, key, value)
        self.session.flush()
        return contact

    def soft_delete(self, contact: CRMContact, deleted_at):
        contact.deleted_at = deleted_at
        self.session.flush()

    def list_tags(self, contact_id: str) -> list[CRMTag]:
        return (
            self.session.query(CRMTag)
            .join(
                CRMContactTag,
                and_(CRMContactTag.tenant_id == CRMTag.tenant_id, CRMContactTag.tag_id == CRMTag.id),
            )
            .filter(
                CRMContactTag.tenant_id == self.tenant_id,
                CRMContactTag.contact_id == contact_id,
            )
            .all()
        )

    def set_tags(self, contact_id: str, tag_ids: list[str]) -> None:
        self.session.query(CRMContactTag).filter(
            CRMContactTag.tenant_id == self.tenant_id,
            CRMContactTag.contact_id == contact_id,
        ).delete()

        for tag_id in tag_ids:
            self.session.add(CRMContactTag(tenant_id=self.tenant_id, contact_id=contact_id, tag_id=tag_id))

        self.session.flush()
