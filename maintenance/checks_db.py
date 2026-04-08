import os
import time
import psycopg2
from urllib.parse import urlparse, urlunparse
from .logging_config import logger


def _normalize_db_url(db_url):
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    # Railway can expose the host with uppercase service name; normalize for psycopg2 resolver.
    db_url = db_url.replace("Postgres.railway.internal", "postgres.railway.internal")
    return db_url


def _fallback_public_db_url(db_url):
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


def _connect_with_fallback(db_url):
    try:
        return psycopg2.connect(db_url, connect_timeout=5), db_url, False
    except Exception as exc:
        message = str(exc)
        if "could not translate host name" not in message:
            raise
        fallback = _fallback_public_db_url(db_url)
        if not fallback:
            raise
        logger.warning("DB internal host resolution failed; retrying with public Railway Postgres host")
        return psycopg2.connect(fallback, connect_timeout=5), fallback, True


def check_db(db_url_env_key):
    """Checks Database connectivity via SELECT 1."""
    db_url = os.environ.get(db_url_env_key)
    if not db_url:
        return {
            "type": "db",
            "ok": False,
            "error": f"Env var {db_url_env_key} not set"
        }
    
    conn = None
    try:
        start = time.time()
        # Ensure timeout for connection attempt
        normalized_url = _normalize_db_url(db_url)
        conn, resolved_url, used_fallback = _connect_with_fallback(normalized_url)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        
        duration = int((time.time() - start) * 1000)
        payload = {
            "type": "db",
            "ok": True,
            "latency_ms": duration
        }
        if used_fallback:
            payload["via_public_host"] = True
        return payload
    except Exception as e:
        return {
            "type": "db",
            "ok": False,
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()
