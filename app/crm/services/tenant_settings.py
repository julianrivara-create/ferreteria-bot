from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.crm.models import CRMTenant


_SENSITIVE_INTEGRATION_SETTING_KEYS = frozenset({"crm_webhook_secret"})


def clone_integration_settings(tenant: CRMTenant | None) -> dict[str, Any]:
    return dict((tenant.integration_settings or {}) if tenant else {})


def redact_integration_settings(value: dict[str, Any] | None) -> dict[str, Any]:
    redacted = dict(value or {})
    for key in _SENSITIVE_INTEGRATION_SETTING_KEYS:
        if key in redacted:
            secret = str(redacted.get(key) or "").strip()
            redacted[key] = {"configured": bool(secret)}
    return redacted


def merge_integration_settings(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(incoming or {}).items():
        if key in _SENSITIVE_INTEGRATION_SETTING_KEYS:
            if value is None:
                merged.pop(key, None)
                continue
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    merged.pop(key, None)
                    continue
                merged[key] = cleaned
                continue
        merged[key] = value
    return merged


def get_tenant_crm_webhook_secret(tenant: CRMTenant | None) -> str:
    settings = get_settings()
    integration = clone_integration_settings(tenant)
    tenant_secret = str(integration.get("crm_webhook_secret") or "").strip()
    if tenant_secret:
        return tenant_secret

    if settings.is_production:
        return ""

    return str(settings.CRM_WEBHOOK_SECRET or "").strip()
