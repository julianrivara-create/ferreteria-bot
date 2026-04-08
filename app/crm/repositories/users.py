from __future__ import annotations

from sqlalchemy.orm import Session

from app.crm.models import CRMUser
from app.crm.repositories.base import TenantRepository


class UserRepository(TenantRepository):
    def __init__(self, session: Session, tenant_id: str):
        super().__init__(session, tenant_id)

    def list(self) -> list[CRMUser]:
        return self.query(CRMUser, include_deleted=True).order_by(CRMUser.created_at.desc()).all()

    def get(self, user_id: str) -> CRMUser | None:
        return self.get_by_id(CRMUser, user_id, include_deleted=True)

    def get_by_email(self, email: str) -> CRMUser | None:
        return self.query(CRMUser, include_deleted=True).filter(CRMUser.email == email.lower().strip()).first()

    def create(self, payload: dict) -> CRMUser:
        user = CRMUser(tenant_id=self.tenant_id, **payload)
        self.session.add(user)
        self.session.flush()
        return user

    def update(self, user: CRMUser, payload: dict) -> CRMUser:
        for key, value in payload.items():
            setattr(user, key, value)
        self.session.flush()
        return user
