from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

import psycopg2

from .logging_config import logger


def resolve_db_url(tenant_cfg: dict) -> str:
    key = tenant_cfg.get("db_url_env_key") or "DATABASE_URL"
    db_url = (os.environ.get(key) or "").strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url.replace("Postgres.railway.internal", "postgres.railway.internal")


def fallback_public_db_url(db_url: str) -> str | None:
    public_host = (os.environ.get("RAILWAY_SERVICE_POSTGRES_URL") or "").strip()
    if not public_host:
        return None

    parsed = urlparse(db_url)
    if not parsed.scheme or not parsed.path:
        return None

    auth = ""
    if parsed.username:
        auth = parsed.username
        if parsed.password is not None:
            auth += f":{parsed.password}"
        auth += "@"

    port = f":{parsed.port}" if parsed.port else ""
    query = parsed.query or ""
    if "sslmode=" not in query:
        query = f"{query}&sslmode=require" if query else "sslmode=require"

    return urlunparse((parsed.scheme, f"{auth}{public_host}{port}", parsed.path, parsed.params, query, parsed.fragment))


def connect_db(db_url: str):
    try:
        return psycopg2.connect(db_url, connect_timeout=5)
    except Exception as exc:
        if "could not translate host name" not in str(exc):
            raise
        fallback = fallback_public_db_url(db_url)
        if not fallback:
            raise
        logger.warning("DB internal host resolution failed; retrying with public Railway Postgres host")
        return psycopg2.connect(fallback, connect_timeout=5)

