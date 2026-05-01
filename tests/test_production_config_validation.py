from __future__ import annotations

import pytest

import app.core.config as config_module


def _reset_config_state() -> None:
    config_module._settings = None
    config_module._warnings_emitted = False


def test_production_requires_explicit_database_url(monkeypatch):
    _reset_config_state()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "super-secure-secret")
    monkeypatch.setenv("ADMIN_TOKEN", "super-secure-admin-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORS_ORIGINS", "https://ferreteria-bot-production.up.railway.app")
    monkeypatch.delenv("ALLOW_LEGACY_FALLBACK", raising=False)

    settings = config_module.Settings(_env_file=None)
    with pytest.raises(ValueError, match="DATABASE_URL must be set explicitly in production"):
        config_module._emit_security_warnings(settings)


def test_production_accepts_explicit_database_url(monkeypatch):
    _reset_config_state()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////app/data/finalprod.db")
    monkeypatch.setenv("SECRET_KEY", "super-secure-secret")
    monkeypatch.setenv("ADMIN_TOKEN", "super-secure-admin-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORS_ORIGINS", "https://ferreteria-bot-production.up.railway.app")
    monkeypatch.delenv("ALLOW_LEGACY_FALLBACK", raising=False)

    settings = config_module.Settings(_env_file=None)
    config_module._emit_security_warnings(settings)
