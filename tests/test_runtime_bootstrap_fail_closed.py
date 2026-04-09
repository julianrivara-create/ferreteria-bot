from __future__ import annotations

import pytest

import app.main as app_main


class _FakeSettings:
    def __init__(self, *, production: bool):
        self.SECRET_KEY = "test-secret"
        self.ADMIN_TOKEN = "secure-admin-token"
        self._production = production

    @property
    def is_production(self) -> bool:
        return self._production

    @property
    def cors_origins(self) -> list[str]:
        return []

    @staticmethod
    def is_secret_configured(value: str | None) -> bool:
        return bool(value)


def test_create_app_fails_closed_in_production_when_bootstrap_breaks(monkeypatch):
    monkeypatch.setattr(app_main, "get_settings", lambda: _FakeSettings(production=True))
    monkeypatch.setattr(app_main, "configure_logging", lambda: None)
    monkeypatch.setattr(app_main, "start_mep_rate_scheduler", lambda: None)
    monkeypatch.setattr(app_main, "start_holds_scheduler", lambda: None)

    def _boom():
        raise RuntimeError("bootstrap exploded")

    monkeypatch.setattr("app.services.runtime_bootstrap.ensure_runtime_bootstrap", _boom)

    with pytest.raises(ValueError, match="Runtime bootstrap failed in production"):
        app_main.create_app()


def test_create_app_stays_up_in_development_when_bootstrap_breaks(monkeypatch):
    monkeypatch.setattr(app_main, "get_settings", lambda: _FakeSettings(production=False))
    monkeypatch.setattr(app_main, "configure_logging", lambda: None)
    monkeypatch.setattr(app_main, "start_mep_rate_scheduler", lambda: None)
    monkeypatch.setattr(app_main, "start_holds_scheduler", lambda: None)

    def _boom():
        raise RuntimeError("bootstrap exploded")

    monkeypatch.setattr("app.services.runtime_bootstrap.ensure_runtime_bootstrap", _boom)

    app = app_main.create_app()

    assert app is not None
