from __future__ import annotations

import json
from pathlib import Path

from app.services.runtime_integrity import evaluate_runtime_integrity


ROOT = Path(__file__).resolve().parent.parent


def test_runtime_integrity_fails_in_production_without_explicit_database_url():
    report = evaluate_runtime_integrity(
        env={
            "ENVIRONMENT": "production",
            "SECRET_KEY": "super-secure-secret",
            "ADMIN_TOKEN": "super-secure-admin-token",
            "OPENAI_API_KEY": "sk-test",
            "CORS_ORIGINS": "https://ferreteria-bot-production.up.railway.app",
            "RAILWAY_SERVICE_NAME": "ferreteria-bot",
            "RAILWAY_PUBLIC_DOMAIN": "ferreteria-bot-production.up.railway.app",
        },
        repo_root=ROOT,
    )

    assert report["categories"]["env"]["status"] == "FAIL"
    details = json.dumps(report)
    assert "super-secure-admin-token" not in details
    assert "super-secure-secret" not in details


def test_runtime_integrity_flags_non_canonical_service_and_legacy_domain():
    report = evaluate_runtime_integrity(
        env={
            "ENVIRONMENT": "production",
            "DATABASE_URL": "sqlite:////app/data/finalprod.db",
            "SECRET_KEY": "super-secure-secret",
            "ADMIN_TOKEN": "super-secure-admin-token",
            "OPENAI_API_KEY": "sk-test",
            "CORS_ORIGINS": "https://ferreteria-bot-clean-production.up.railway.app,https://ferreteria-bot-production.up.railway.app",
            "RAILWAY_SERVICE_NAME": "ferreteria-bot-clean",
            "RAILWAY_PUBLIC_DOMAIN": "ferreteria-bot-production.up.railway.app",
            "RAILWAY_VOLUME_MOUNT_PATH": "/app/data",
        },
        repo_root=ROOT,
    )

    assert report["categories"]["service_role"]["status"] == "FAIL"
    assert report["categories"]["domains"]["status"] == "WARN"


def test_runtime_integrity_passes_required_runtime_assets_for_repo():
    report = evaluate_runtime_integrity(
        env={
            "ENVIRONMENT": "production",
            "DATABASE_URL": "sqlite:////app/data/finalprod.db",
            "SECRET_KEY": "super-secure-secret",
            "ADMIN_TOKEN": "super-secure-admin-token",
            "OPENAI_API_KEY": "sk-test",
            "CORS_ORIGINS": "https://ferreteria-bot-production.up.railway.app",
            "RAILWAY_SERVICE_NAME": "ferreteria-bot",
            "RAILWAY_PUBLIC_DOMAIN": "ferreteria-bot-production.up.railway.app",
            "RAILWAY_VOLUME_MOUNT_PATH": "/app/data",
        },
        repo_root=ROOT,
    )

    assert report["categories"]["data"]["status"] == "OK"
