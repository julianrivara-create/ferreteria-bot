#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unified WSGI entrypoint.

Priority:
1. Final Production stack (`app.main`) with CRM/API/worker-ready architecture.
2. Multi-tenant storefront + dashboard extensions from sales-bot-platform.
3. Safe fallback to legacy runtime (`wsgi_legacy`) if Final stack init fails.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, redirect, request, send_from_directory


logger = logging.getLogger(__name__)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _legacy_fallback_allowed() -> bool:
    """Legacy fallback is allowed only in dev/local/test environments (or if explicitly enabled)."""
    explicit = os.getenv("ALLOW_LEGACY_FALLBACK")
    if explicit is not None:
        return _is_truthy(explicit)
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    return environment in {"development", "dev", "local", "test"}


def _attach_runtime_identity(app: Flask, runtime_stack: str) -> None:
    app.config["RUNTIME_STACK"] = runtime_stack

    @app.after_request
    def _add_runtime_stack_header(response):
        response.headers.setdefault("X-Runtime-Stack", runtime_stack)
        return response


def _register_multitenant_extensions(app: Flask) -> None:
    """Attach tenant-aware UI/API routes to an existing Flask app."""
    from bot_sales.config import BASE_DIR
    from bot_sales.connectors.storefront_tenant_api import storefront_tenant_bp
    from dashboard.app import dashboard_bp

    # Tenant-aware dashboard (kept separate from /crm UI)
    if "dashboard" not in app.blueprints:
        app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    # Tenant-aware storefront API (/api/t/<tenant_slug>/...)
    if "storefront_tenant_api" not in app.blueprints:
        app.register_blueprint(storefront_tenant_bp)

    website_dir = os.path.join(BASE_DIR, "website")
    static_dir = os.path.join(BASE_DIR, "static")

    @app.get("/website/<path:asset_path>")
    def website_assets(asset_path: str):
        return send_from_directory(website_dir, asset_path)

    @app.get("/widget_v2.html")
    @app.get("/static/widget_v2.html")
    def widget_v2():
        return send_from_directory(static_dir, "widget_v2.html")

    @app.get("/t/<tenant_slug>")
    def tenant_storefront(tenant_slug: str):
        return redirect(f"/website/index.html?tenant={tenant_slug}")

    @app.get("/t/<tenant_slug>/product")
    def tenant_product(tenant_slug: str):
        model = request.args.get("model", "")
        target = f"/website/product.html?tenant={tenant_slug}"
        if model:
            target += f"&model={model}"
        return redirect(target)


def _create_final_app() -> Flask:
    """Create Final Production app and extend it with multi-tenant routes."""
    from app.main import create_app as create_final_stack_app
    from app.services.runtime_bootstrap import ensure_runtime_bootstrap

    app = create_final_stack_app()
    try:
        result = ensure_runtime_bootstrap()
        logger.info(
            "runtime_bootstrap_ok tenants_processed=%s admins_created=%s",
            result.get("tenants_processed"),
            result.get("admins_created"),
        )
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("runtime_bootstrap_failed error=%s", exc)

    _register_multitenant_extensions(app)
    _attach_runtime_identity(app, "final")
    logger.info("wsgi_mode=final_production_with_multitenant_extensions")
    return app


def _create_legacy_app() -> Flask:
    from wsgi_legacy import create_app as create_legacy_stack_app

    app = create_legacy_stack_app()
    _attach_runtime_identity(app, "legacy")
    logger.warning("wsgi_mode=legacy_fallback")
    return app


try:
    app = _create_final_app()
except Exception as exc:
    if _legacy_fallback_allowed():
        logger.exception("final_stack_init_failed_using_legacy_fallback error=%s", exc)
        app = _create_legacy_app()
    else:
        logger.exception("final_stack_init_failed_no_legacy_fallback error=%s", exc)
        raise


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
