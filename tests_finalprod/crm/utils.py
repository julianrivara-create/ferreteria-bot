from __future__ import annotations

from app.crm.domain.enums import UserRole
from app.crm.models import CRMPipelineStage, CRMTenant, CRMUser
from app.crm.services.auth_service import CRMAuthService


def seed_tenant_with_user(session, *, tenant_id: str, user_id: str, role: UserRole = UserRole.ADMIN):
    tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
    if tenant is None:
        tenant = CRMTenant(
            id=tenant_id,
            business_name=f"{tenant_id}-biz",
            timezone="UTC",
            currency="USD",
            channels=["whatsapp", "web"],
            integration_settings={},
            pipeline_config=[],
            is_active=True,
        )
        session.add(tenant)

    user = CRMUser(
        id=user_id,
        tenant_id=tenant_id,
        full_name=f"{user_id}-name",
        email=f"{user_id}@example.com",
        phone="+5491100000000",
        role=role,
        password_hash=CRMAuthService().hash_password("secret1234"),
        is_active=True,
    )
    session.add(user)

    stage = session.query(CRMPipelineStage).filter(CRMPipelineStage.id == f"{tenant_id}-stage-new").first()
    if stage is None:
        stage = CRMPipelineStage(
            id=f"{tenant_id}-stage-new",
            tenant_id=tenant_id,
            name="New",
            position=1,
            color="#64748b",
            is_won=False,
            is_lost=False,
            sla_hours=48,
        )
        session.add(stage)
    session.flush()

    token = CRMAuthService().issue_token(user)
    return tenant, user, stage, token
