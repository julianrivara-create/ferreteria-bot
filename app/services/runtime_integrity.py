from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.config import (
    CANONICAL_RAILWAY_SERVICE,
    DEFAULT_DATABASE_URL,
    is_secret_value_configured,
    is_truthy,
)


RUNTIME_REQUIRED_FILES = (
    "tenants.yaml",
    "config/catalog.csv",
    "config/policies.md",
    "data/tenants/ferreteria/catalog.csv",
    "data/tenants/ferreteria/policies.md",
)

STATUS_ORDER = {"OK": 0, "WARN": 1, "FAIL": 2}


def _max_status(*statuses: str) -> str:
    return max(statuses, key=lambda status: STATUS_ORDER.get(status, 0), default="OK")


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _category(name: str, checks: list[dict[str, str]]) -> dict[str, Any]:
    status = _max_status(*(check["status"] for check in checks)) if checks else "OK"
    return {"status": status, "checks": checks}


def _explicit_database_url(env: dict[str, str]) -> str:
    value = (env.get("DATABASE_URL") or "").strip()
    if value:
        return value
    fallback = (env.get("_SETTINGS_DATABASE_URL") or "").strip()
    if fallback and fallback != DEFAULT_DATABASE_URL:
        return fallback
    return ""


def _sqlite_runtime_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    path = database_url[len("sqlite:///") :]
    if not path:
        return None
    if path.startswith("/"):
        return Path(path)
    return Path("/app") / path


def evaluate_runtime_integrity(
    *,
    env: dict[str, str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    current_env = dict(os.environ if env is None else env)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    environment = (current_env.get("ENVIRONMENT") or current_env.get("RAILWAY_ENVIRONMENT") or "development").strip().lower()
    production = environment in {"production", "prod"}

    database_url = _explicit_database_url(current_env)
    volume_mount = Path((current_env.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()) if current_env.get("RAILWAY_VOLUME_MOUNT_PATH") else None
    service_name = (current_env.get("RAILWAY_SERVICE_NAME") or "").strip()
    public_domain = (current_env.get("RAILWAY_PUBLIC_DOMAIN") or "").strip()
    cors_origins = [origin.strip() for origin in (current_env.get("CORS_ORIGINS") or "").split(",") if origin.strip()]

    env_checks = [
        _check(
            "DATABASE_URL explicit",
            "FAIL" if production and not database_url else "OK",
            "configured explicitly" if database_url else "missing explicit DATABASE_URL in production",
        ),
        _check(
            "SECRET_KEY",
            "FAIL" if production and not is_secret_value_configured(current_env.get("SECRET_KEY")) else "OK",
            "configured" if is_secret_value_configured(current_env.get("SECRET_KEY")) else "missing or insecure",
        ),
        _check(
            "ADMIN_TOKEN",
            "FAIL" if production and not is_secret_value_configured(current_env.get("ADMIN_TOKEN")) else "OK",
            "configured" if is_secret_value_configured(current_env.get("ADMIN_TOKEN")) else "missing or insecure",
        ),
        _check(
            "OPENAI_API_KEY",
            "WARN" if production and not is_secret_value_configured(current_env.get("OPENAI_API_KEY")) else "OK",
            "configured" if is_secret_value_configured(current_env.get("OPENAI_API_KEY")) else "missing or insecure",
        ),
        _check(
            "ALLOW_LEGACY_FALLBACK",
            "FAIL" if production and is_truthy(current_env.get("ALLOW_LEGACY_FALLBACK")) else "OK",
            "disabled" if not is_truthy(current_env.get("ALLOW_LEGACY_FALLBACK")) else "enabled in production",
        ),
    ]

    data_checks: list[dict[str, str]] = []
    if database_url:
        if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
            data_checks.append(_check("Database backend", "OK", "Postgres configured"))
        elif database_url.startswith("sqlite:"):
            sqlite_path = _sqlite_runtime_path(database_url)
            if not sqlite_path:
                data_checks.append(_check("Database backend", "FAIL", "sqlite path could not be resolved"))
            elif production and volume_mount:
                try:
                    sqlite_path.relative_to(volume_mount)
                    data_checks.append(_check("Database backend", "OK", f"SQLite on Railway volume ({volume_mount})"))
                except ValueError:
                    data_checks.append(
                        _check(
                            "Database backend",
                            "FAIL",
                            f"SQLite path {sqlite_path} is outside Railway volume {volume_mount}",
                        )
                    )
            elif production and not volume_mount:
                data_checks.append(
                    _check(
                        "Database backend",
                        "WARN",
                        f"SQLite configured at {sqlite_path} without RAILWAY_VOLUME_MOUNT_PATH",
                    )
                )
            else:
                data_checks.append(_check("Database backend", "OK", f"SQLite configured at {sqlite_path}"))
        else:
            data_checks.append(_check("Database backend", "WARN", "Unrecognized database scheme"))
    else:
        data_checks.append(_check("Database backend", "FAIL" if production else "WARN", "DATABASE_URL not configured"))

    for relative_path in RUNTIME_REQUIRED_FILES:
        exists = (root / relative_path).exists()
        data_checks.append(
            _check(
                f"Runtime asset {relative_path}",
                "OK" if exists else "FAIL",
                "present" if exists else "missing from repo/runtime image",
            )
        )

    service_role_checks = [
        _check(
            "Canonical Railway service",
            "FAIL" if service_name and service_name != CANONICAL_RAILWAY_SERVICE else "OK",
            service_name or "not running inside Railway",
        ),
        _check(
            "Railway public domain",
            "WARN" if production and not public_domain else "OK",
            public_domain or "missing",
        ),
    ]

    domains_checks: list[dict[str, str]] = []
    if production:
        domains_checks.append(
            _check(
                "CORS_ORIGINS configured",
                "WARN" if not cors_origins else "OK",
                ", ".join(cors_origins) if cors_origins else "empty in production",
            )
        )
        domains_checks.append(
            _check(
                "Legacy clean domain not referenced",
                "WARN" if any("ferreteria-bot-clean" in origin for origin in cors_origins) else "OK",
                "found legacy clean domain in CORS" if any("ferreteria-bot-clean" in origin for origin in cors_origins) else "clean",
            )
        )
        if public_domain and cors_origins:
            expected_origin = public_domain if public_domain.startswith("http") else f"https://{public_domain}"
            domains_checks.append(
                _check(
                    "Canonical public domain allowed by CORS",
                    "WARN" if expected_origin not in cors_origins else "OK",
                    expected_origin,
                )
            )
    else:
        domains_checks.append(_check("CORS review", "OK", "skipped outside production"))

    categories = {
        "env": _category("env", env_checks),
        "data": _category("data", data_checks),
        "service_role": _category("service_role", service_role_checks),
        "domains": _category("domains", domains_checks),
    }

    overall_status = _max_status(*(category["status"] for category in categories.values()))
    return {
        "environment": environment,
        "overall_status": overall_status,
        "canonical_service": CANONICAL_RAILWAY_SERVICE,
        "categories": categories,
    }
