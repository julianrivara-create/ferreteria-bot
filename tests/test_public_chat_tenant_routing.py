from __future__ import annotations

from flask import Flask
from unittest.mock import MagicMock

from app.api import public_routes
from app.api.public_routes import public_api


def _tenant_runtime():
    tenant = MagicMock()
    tenant.id = "ferreteria"
    tenant.get_slug.return_value = "ferreteria"

    bot = MagicMock()
    bot.process_message.return_value = "Respuesta tenant-aware"
    bot.get_last_turn_meta.return_value = {"route_source": "deterministic"}

    manager = MagicMock()
    manager.get_tenant.return_value = tenant
    manager.get_tenant_by_slug.return_value = tenant
    manager.get_bot.return_value = bot
    return tenant, bot, manager


def _build_client():
    app = Flask(__name__)
    app.register_blueprint(public_api, url_prefix="/api")
    return app.test_client()


def test_public_chat_rate_limit_adds_headers_and_blocks_excess(monkeypatch):
    client = _build_client()
    _, _, manager = _tenant_runtime()

    monkeypatch.setattr(public_routes, "_get_tenant_manager", lambda: manager)
    monkeypatch.setattr(public_routes.settings, "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", 2, raising=False)
    public_routes._reset_public_chat_rate_limiter()

    headers = {"X-Forwarded-For": "203.0.113.10"}
    payload = {
        "message": "Hola",
        "user": "visitor-42",
        "tenant_id": "ferreteria",
    }

    first = client.post("/api/chat", json=payload, headers=headers)
    second = client.post("/api/chat", json=payload, headers=headers)
    third = client.post("/api/chat", json=payload, headers=headers)

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert first.headers["X-RateLimit-Remaining"] == "1"

    assert second.status_code == 200
    assert second.headers["X-RateLimit-Remaining"] == "0"

    assert third.status_code == 429
    assert third.get_json()["error"] == "Rate limit exceeded"
    assert third.headers["X-RateLimit-Limit"] == "2"
    assert third.headers["X-RateLimit-Remaining"] == "0"
    assert int(third.headers["Retry-After"]) >= 1


def test_public_chat_prefers_tenant_runtime_and_namespaces_web_session(monkeypatch):
    client = _build_client()

    _, bot, manager = _tenant_runtime()

    monkeypatch.setattr(public_routes, "_get_tenant_manager", lambda: manager)
    monkeypatch.setattr(public_routes.settings, "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", 60, raising=False)
    public_routes._reset_public_chat_rate_limiter()

    resp = client.post(
        "/api/chat",
        json={
            "message": "Hola",
            "user": "visitor-42",
            "tenant_id": "ferreteria",
        },
        headers={"X-Forwarded-For": "203.0.113.11"},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["content"] == "Respuesta tenant-aware"
    assert payload["tenant"] == "ferreteria"
    assert payload["meta"]["route_source"] == "deterministic"
    assert resp.headers["X-RateLimit-Limit"] == "60"
    manager.get_bot.assert_called_once_with("ferreteria")
    bot.process_message.assert_called_once_with("web_visitor-42", "Hola")


def test_public_chat_returns_404_for_unknown_tenant(monkeypatch):
    client = _build_client()

    manager = MagicMock()
    manager.get_tenant.return_value = None
    manager.get_tenant_by_slug.return_value = None

    monkeypatch.setattr(public_routes, "_get_tenant_manager", lambda: manager)
    monkeypatch.setattr(public_routes.settings, "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", 60, raising=False)
    public_routes._reset_public_chat_rate_limiter()

    resp = client.post(
        "/api/chat",
        json={
            "message": "Hola",
            "user": "visitor-42",
            "tenant_id": "desconocido",
        },
        headers={"X-Forwarded-For": "203.0.113.12"},
    )

    assert resp.status_code == 404
    assert "Unknown tenant_id" in resp.get_json()["error"]
    assert resp.headers["X-RateLimit-Limit"] == "60"
