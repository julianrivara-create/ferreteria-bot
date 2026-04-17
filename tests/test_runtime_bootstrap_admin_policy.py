from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.crm.models  # noqa: F401
import app.services.runtime_bootstrap as runtime_bootstrap
from app.crm.domain.enums import UserRole
from app.crm.models import CRMUser
from app.crm.services.auth_service import CRMAuthService
from app.db.models import Base
from app.crm.db import CRMBase


class _FakeSettings:
    def __init__(self, *, production: bool):
        self._production = production

    @property
    def is_production(self) -> bool:
        return self._production


def _configure_bootstrap_env(monkeypatch, tmp_path: Path, *, production: bool):
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    CRMBase.metadata.create_all(bind=engine)

    tenants_file = tmp_path / "tenants.yaml"
    tenants_file.write_text(
        "tenants:\n"
        "  - id: ferreteria\n"
        "    slug: ferreteria\n"
        "    name: Ferreteria Central\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime_bootstrap, "engine", engine)
    monkeypatch.setattr(runtime_bootstrap, "SessionLocal", Session)
    monkeypatch.setattr(runtime_bootstrap, "TENANTS_INDEX", tenants_file)
    monkeypatch.setattr(runtime_bootstrap, "get_settings", lambda: _FakeSettings(production=production))

    return Session, engine


def test_runtime_bootstrap_skips_default_admin_creation_in_production(monkeypatch, tmp_path):
    Session, engine = _configure_bootstrap_env(monkeypatch, tmp_path, production=True)
    try:
        monkeypatch.delenv("BOOTSTRAP_CREATE_DEFAULT_ADMIN", raising=False)
        monkeypatch.delenv("BOOTSTRAP_RESET_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        result = runtime_bootstrap.ensure_runtime_bootstrap()

        with Session() as session:
            users = session.query(CRMUser).all()

        assert result["admins_created"] == 0
        assert result["admins_skipped"] == 1
        assert users == []
    finally:
        engine.dispose()


def test_runtime_bootstrap_does_not_reset_existing_admin_password_without_explicit_flag(monkeypatch, tmp_path):
    Session, engine = _configure_bootstrap_env(monkeypatch, tmp_path, production=False)
    try:
        monkeypatch.setenv("BOOTSTRAP_CREATE_DEFAULT_ADMIN", "true")
        monkeypatch.delenv("BOOTSTRAP_RESET_ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("ADMIN_PASSWORD", "new-password-123")

        with Session() as session:
            user = CRMUser(
                tenant_id="ferreteria",
                full_name="Admin Ferreteria",
                email="admin+ferreteria@salesbot.local",
                password_hash=CRMAuthService().hash_password("original-password-123"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(user)
            session.commit()
            original_hash = user.password_hash

        result = runtime_bootstrap.ensure_runtime_bootstrap()

        with Session() as session:
            persisted = session.query(CRMUser).filter(CRMUser.email == "admin+ferreteria@salesbot.local").one()

        assert result["admins_created"] == 0
        assert result["admins_password_reset"] == 0
        assert persisted.password_hash == original_hash
    finally:
        engine.dispose()
