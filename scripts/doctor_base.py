#!/usr/bin/env python3
"""Operational doctor for the base multi-bot workspace.

Checks:
- WSGI boots in Final Production mode (not legacy fallback)
- Core endpoints respond
- CRM auth works with seeded tenant admin
- Tenant index/profile/catalog consistency
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_tenant import main as validate_tenant_main  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.crm.models import CRMTenant, CRMUser  # noqa: E402
from wsgi import app  # noqa: E402


def _check(condition: bool, label: str, detail: str = "") -> Tuple[bool, str, str]:
    return condition, label, detail


def _resolve_login_target() -> Dict[str, str]:
    admin_password = os.getenv("CRM_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD") or "ADMIN_PASSWORD_ENV"
    with SessionLocal() as session:
        # Use an existing seeded admin first (most reliable).
        user = session.query(CRMUser).order_by(CRMUser.created_at.asc()).first()
        if user:
            return {
                "tenant_id": str(user.tenant_id),
                "email": str(user.email),
                "password": admin_password,
            }

        tenant = session.query(CRMTenant).order_by(CRMTenant.created_at.asc()).first()
        if tenant:
            slug = str(tenant.id)
            return {
                "tenant_id": slug,
                "email": f"admin+{slug}@salesbot.local",
                "password": admin_password,
            }
    return {"tenant_id": "default_tenant", "email": "admin+default_tenant@salesbot.local", "password": admin_password}


def run_doctor() -> int:
    results: List[Tuple[bool, str, str]] = []

    required_blueprints = {"crm_api", "crm_ui", "dashboard", "storefront_tenant_api"}
    active_blueprints = set(app.blueprints.keys())
    final_mode_ok = required_blueprints.issubset(active_blueprints)
    results.append(
        _check(
            final_mode_ok,
            "WSGI final mode",
            f"blueprints={sorted(active_blueprints)}",
        )
    )

    client = app.test_client()
    for path in ("/health", "/crm/login", "/dashboard/login", "/api/t/ferreteria/products"):
        resp = client.get(path)
        results.append(_check(resp.status_code == 200, f"GET {path}", f"status={resp.status_code}"))

    login_payload = _resolve_login_target()
    login_resp = client.post("/api/crm/auth/login", json=login_payload)
    login_json: Dict[str, Any] = login_resp.get_json(silent=True) or {}
    token = login_json.get("access_token")
    results.append(
        _check(
            login_resp.status_code == 200 and bool(token),
            "POST /api/crm/auth/login",
            f"status={login_resp.status_code}",
        )
    )

    if token:
        contacts = client.get("/api/crm/contacts", headers={"Authorization": f"Bearer {token}"})
        results.append(_check(contacts.status_code == 200, "GET /api/crm/contacts", f"status={contacts.status_code}"))
    else:
        results.append(_check(False, "GET /api/crm/contacts", "skipped (no token)"))

    # Reuse existing validator logic (raises SystemExit on failure)
    tenant_ok = True
    try:
        validate_tenant_main()
    except SystemExit as exc:
        tenant_ok = exc.code == 0
    results.append(_check(tenant_ok, "Tenant index/profile validation", "scripts/validate_tenant.py"))

    failures = 0
    for ok, label, detail in results:
        print(f"[{'OK' if ok else 'FAIL'}] {label} - {detail}")
        if not ok:
            failures += 1

    summary = {"checks": len(results), "failed": failures, "passed": len(results) - failures}
    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_doctor())
