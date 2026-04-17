from __future__ import annotations

import ipaddress
import os
from functools import wraps

from flask import g, jsonify, request

from app.crm.domain.permissions import has_permission
from app.crm.models import CRMUser
from app.crm.services.auth_service import AuthError, CRMAuthService
from app.crm.services.rate_limiter import rate_limiter
from app.db.session import SessionLocal


auth_service = CRMAuthService()


def _extract_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip() or None


def _normalize_ip(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    candidate = raw_value.split(",", 1)[0].strip()
    if not candidate:
        return None
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _is_trusted_proxy(ip: str) -> bool:
    try:
        parsed = ipaddress.ip_address(ip)
        return not parsed.is_global
    except ValueError:
        return False


def _extract_forwarded_ip(header_value: str) -> str | None:
    candidates = [part.strip() for part in header_value.split(",") if part.strip()]
    if not candidates:
        return None

    raw_hops = (os.getenv("TRUSTED_PROXY_HOPS") or "").strip()
    if raw_hops:
        try:
            trusted_hops = max(1, int(raw_hops))
        except ValueError:
            trusted_hops = 1
    else:
        trusted_hops = 2 if os.getenv("RAILWAY_ENVIRONMENT") else 1

    for candidate in reversed(candidates[-trusted_hops:]):
        parsed = _normalize_ip(candidate)
        if parsed:
            return parsed
    return None


def _rate_limit_ip() -> str:
    remote = _normalize_ip(request.remote_addr or "")
    if remote and _is_trusted_proxy(remote):
        for header in (
            "CF-Connecting-IP",
            "True-Client-IP",
            "Fastly-Client-IP",
            "Fly-Client-IP",
            "X-Real-IP",
        ):
            parsed = _normalize_ip(request.headers.get(header))
            if parsed:
                return parsed

        forwarded = _extract_forwarded_ip(request.headers.get("X-Forwarded-For", ""))
        if forwarded:
            return forwarded

    fallback = remote
    return fallback or (request.remote_addr or "unknown")


def crm_auth_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({"error": "Missing bearer token"}), 401

        try:
            payload = auth_service.decode_token(token)
        except AuthError as exc:
            return jsonify({"error": str(exc)}), 401

        session = SessionLocal()
        try:
            user = (
                session.query(CRMUser)
                .filter(
                    CRMUser.id == payload.get("sub"),
                    CRMUser.tenant_id == payload.get("tenant_id"),
                    CRMUser.is_active.is_(True),
                )
                .first()
            )
        finally:
            session.close()

        if user is None:
            return jsonify({"error": "User not found or inactive"}), 401

        g.crm_claims = payload
        g.crm_user = {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "email": user.email,
            "full_name": user.full_name,
        }
        return func(*args, **kwargs)

    return wrapper


def permission_required(permission: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = getattr(g, "crm_user", None)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401

            if not has_permission(user["role"], permission):
                return jsonify({"error": "Forbidden", "required_permission": permission}), 403

            return func(*args, **kwargs)

        return wrapper

    return decorator


def rate_limited(limit: int, window_seconds: int):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{request.path}:{_rate_limit_ip()}"
            if not rate_limiter.allow(key=key, limit=limit, window_seconds=window_seconds):
                return jsonify({"error": "Rate limit exceeded"}), 429
            return func(*args, **kwargs)

        return wrapper

    return decorator


def parse_pagination_args() -> dict:
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    try:
        page_size = int(request.args.get("page_size", 25))
    except ValueError:
        page_size = 25

    page_size = min(max(1, page_size), 100)
    sort_by = request.args.get("sort_by", "created_at")
    sort_dir = request.args.get("sort_dir", "desc").lower()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"

    return {
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }
