from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from app.crm.domain.enums import UserRole
from app.crm.models import CRMPipelineStage, CRMTenant, CRMUser
from app.crm.services.auth_service import CRMAuthService
from app.db.models import Base
from app.db.session import SessionLocal, engine
from app.crm.db import CRMBase
import app.crm.models  # noqa: F401  # ensure CRM models are registered


logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
TENANTS_INDEX = ROOT / "tenants.yaml"


DEFAULT_STAGES = [
    {"name": "NEW", "position": 1, "is_won": False, "is_lost": False, "color": "#3b82f6"},
    {"name": "QUALIFIED", "position": 2, "is_won": False, "is_lost": False, "color": "#06b6d4"},
    {"name": "QUOTED", "position": 3, "is_won": False, "is_lost": False, "color": "#f59e0b"},
    {"name": "NEGOTIATING", "position": 4, "is_won": False, "is_lost": False, "color": "#f97316"},
    {"name": "WON", "position": 5, "is_won": True, "is_lost": False, "color": "#22c55e"},
    {"name": "LOST", "position": 6, "is_won": False, "is_lost": True, "color": "#ef4444"},
    {"name": "NURTURE", "position": 7, "is_won": False, "is_lost": False, "color": "#8b5cf6"},
]


def _load_tenants_index() -> list[dict[str, Any]]:
    if not TENANTS_INDEX.exists():
        return []
    raw = yaml.safe_load(TENANTS_INDEX.read_text(encoding="utf-8")) or {}
    tenants = raw.get("tenants", [])
    if not isinstance(tenants, list):
        return []
    return [t for t in tenants if isinstance(t, dict)]


def _admin_email_for_slug(slug: str) -> str:
    slug_clean = (slug or "tenant").strip().lower().replace(" ", "-")
    return f"admin+{slug_clean}@salesbot.local"


def ensure_runtime_bootstrap() -> dict[str, Any]:
    """Ensure DB schema + CRM tenants/users for local and staging runs.

    This is idempotent and safe to call at startup.
    """
    Base.metadata.create_all(bind=engine)
    CRMBase.metadata.create_all(bind=engine)

    tenants = _load_tenants_index()
    if not tenants:
        logger.warning("runtime_bootstrap_no_tenants_index")
        return {"tenants_processed": 0, "admins_created": 0}

    auth = CRMAuthService()
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        raise ValueError("ADMIN_PASSWORD env var REQUIRED. Aborting bootstrap.")
    password_hash = auth.hash_password(admin_password)

    processed = 0
    admins_created = 0
    with SessionLocal() as session:
        for entry in tenants:
            tenant_id = str(entry.get("id") or entry.get("slug") or "").strip()
            slug = str(entry.get("slug") or tenant_id).strip()
            business_name = str(entry.get("name") or slug or tenant_id).strip() or "Tenant"
            if not tenant_id:
                continue

            # Read supported channels from tenants.yaml; fall back to web only
            configured_channels = entry.get("supported_channels") or ["web"]
            if isinstance(configured_channels, str):
                configured_channels = [configured_channels]

            tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
            if tenant is None:
                tenant = CRMTenant(
                    id=tenant_id,
                    business_name=business_name,
                    currency="ARS",
                    channels=configured_channels,
                    integration_settings={},
                    pipeline_config=[],
                )
                session.add(tenant)
            else:
                tenant.business_name = business_name
                if not tenant.currency:
                    tenant.currency = "ARS"
                if not tenant.channels:
                    tenant.channels = configured_channels

            # Ensure pipeline stages
            existing_stage_count = (
                session.query(CRMPipelineStage)
                .filter(CRMPipelineStage.tenant_id == tenant_id)
                .count()
            )
            if existing_stage_count == 0:
                for stage in DEFAULT_STAGES:
                    session.add(
                        CRMPipelineStage(
                            tenant_id=tenant_id,
                            name=stage["name"],
                            position=stage["position"],
                            is_won=stage["is_won"],
                            is_lost=stage["is_lost"],
                            color=stage["color"],
                        )
                    )

            # Ensure tenant admin user
            admin_email = _admin_email_for_slug(slug)
            admin_user = (
                session.query(CRMUser)
                .filter(CRMUser.tenant_id == tenant_id, CRMUser.email == admin_email)
                .first()
            )
            if admin_user is None:
                admin_user = CRMUser(
                    tenant_id=tenant_id,
                    full_name=f"Admin {business_name}",
                    email=admin_email,
                    role=UserRole.ADMIN,
                    password_hash=password_hash,
                    is_active=True,
                )
                session.add(admin_user)
                admins_created += 1
            else:
                # Keep bootstrap deterministic across runs/sessions.
                admin_user.password_hash = password_hash
                admin_user.is_active = True
                if not admin_user.full_name:
                    admin_user.full_name = f"Admin {business_name}"
            processed += 1

        session.commit()

    return {"tenants_processed": processed, "admins_created": admins_created}
