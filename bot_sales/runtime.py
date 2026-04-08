"""Helpers to run this workspace as a single-business ferreteria bot."""

from __future__ import annotations

import os
from typing import Optional

from .core.tenancy import TenantConfig, tenant_manager


DEFAULT_TENANT_SLUG = "ferreteria"


def resolve_runtime_tenant_id(explicit: Optional[str] = None) -> str:
    """Resolve the tenant to use for CLI/WhatsApp runtime."""
    requested = (explicit or os.getenv("BOT_TENANT_ID") or "").strip()

    if requested:
        tenant = tenant_manager.get_tenant(requested) or tenant_manager.get_tenant_by_slug(requested)
        if tenant:
            return tenant.id
        raise ValueError(f"Tenant no encontrado: {requested}")

    ferreteria = tenant_manager.get_tenant(DEFAULT_TENANT_SLUG) or tenant_manager.get_tenant_by_slug(DEFAULT_TENANT_SLUG)
    if ferreteria:
        return ferreteria.id

    default_tenant = tenant_manager.get_default_tenant()
    if default_tenant:
        return default_tenant.id

    raise RuntimeError("No hay tenants configurados en tenants.yaml")


def get_runtime_tenant(explicit: Optional[str] = None) -> TenantConfig:
    tenant_id = resolve_runtime_tenant_id(explicit)
    tenant = tenant_manager.get_tenant(tenant_id)
    if not tenant:
        raise RuntimeError(f"No se pudo cargar el tenant runtime: {tenant_id}")
    return tenant


def get_runtime_bot(explicit: Optional[str] = None):
    tenant_id = resolve_runtime_tenant_id(explicit)
    return tenant_manager.get_bot(tenant_id)
