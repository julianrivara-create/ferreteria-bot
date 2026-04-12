from __future__ import annotations

import sys
import types
from pathlib import Path

from flask import Flask

if "cachetools" not in sys.modules:
    cachetools_stub = types.ModuleType("cachetools")

    class TTLCache(dict):
        def __init__(self, *args, **kwargs):
            super().__init__()

    cachetools_stub.TTLCache = TTLCache
    sys.modules["cachetools"] = cachetools_stub

from app.ui.ferreteria_training_routes import ferreteria_training_ui
from app.crm.services.rate_limiter import rate_limiter
from dashboard.app import dashboard_bp


ROOT = Path(__file__).resolve().parents[1]


def _build_app():
    app = Flask(__name__, template_folder=str(ROOT / "app" / "ui" / "templates"))
    app.secret_key = "test-secret"
    app.register_blueprint(ferreteria_training_ui)
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    return app


def _reset_rate_limiter_state():
    if hasattr(rate_limiter, "_memory") and hasattr(rate_limiter._memory, "_hits"):
        rate_limiter._memory._hits.clear()


def test_dashboard_login_rejects_external_next(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "super-test-password")
    _reset_rate_limiter_state()
    client = _build_app().test_client()

    resp = client.post(
        "/dashboard/login?next=https://evil.example/phish",
        data={"username": "admin", "password": "super-test-password"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard/")


def test_training_login_rejects_external_next(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "super-test-password")
    _reset_rate_limiter_state()
    client = _build_app().test_client()

    resp = client.post(
        "/ops/ferreteria/training/login?next=https://evil.example/phish",
        data={"password": "super-test-password"},
        environ_base={"REMOTE_ADDR": "127.0.0.2"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/ops/ferreteria/training")


def test_training_login_rate_limit_blocks_repeated_attempts(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "super-test-password")
    _reset_rate_limiter_state()
    client = _build_app().test_client()

    for _ in range(10):
        resp = client.post(
            "/ops/ferreteria/training/login",
            data={"password": "wrong-password"},
            environ_base={"REMOTE_ADDR": "127.0.0.3"},
            follow_redirects=False,
        )
        assert resp.status_code == 200

    blocked = client.post(
        "/ops/ferreteria/training/login",
        data={"password": "wrong-password"},
        environ_base={"REMOTE_ADDR": "127.0.0.3"},
        follow_redirects=False,
    )

    assert blocked.status_code == 429
    assert b"Demasiados intentos" in blocked.data


def test_dashboard_login_rate_limit_blocks_repeated_attempts(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "super-test-password")
    _reset_rate_limiter_state()
    client = _build_app().test_client()

    for _ in range(10):
        resp = client.post(
            "/dashboard/login",
            data={"username": "admin", "password": "wrong-password"},
            environ_base={"REMOTE_ADDR": "127.0.0.4"},
            follow_redirects=False,
        )
        assert resp.status_code == 200

    blocked = client.post(
        "/dashboard/login",
        data={"username": "admin", "password": "wrong-password"},
        environ_base={"REMOTE_ADDR": "127.0.0.4"},
        follow_redirects=False,
    )

    assert blocked.status_code == 429
    assert b"Demasiados intentos" in blocked.data


def test_dashboard_login_rate_limit_blocks_repeated_attempts_even_if_ip_changes(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "super-test-password")
    _reset_rate_limiter_state()
    client = _build_app().test_client()

    for i in range(10):
        resp = client.post(
            "/dashboard/login",
            data={"username": "admin", "password": "wrong-password"},
            environ_base={"REMOTE_ADDR": f"127.0.0.{10 + i}"},
            follow_redirects=False,
        )
        assert resp.status_code == 200

    blocked = client.post(
        "/dashboard/login",
        data={"username": "admin", "password": "wrong-password"},
        environ_base={"REMOTE_ADDR": "127.0.0.99"},
        follow_redirects=False,
    )

    assert blocked.status_code == 429
    assert b"Demasiados intentos" in blocked.data
