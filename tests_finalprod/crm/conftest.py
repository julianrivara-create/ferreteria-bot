import os
import warnings

import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import close_all_sessions, sessionmaker

# Ensure app settings can initialize.
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
os.environ.setdefault("SECRET_KEY", "ferreteria-tests-secret-key-at-least-32-bytes")
os.environ.setdefault("CRM_JWT_SECRET", "ferreteria-tests-crm-jwt-secret-at-least-32-bytes")
os.environ.setdefault("CRM_WEBHOOK_SECRET", "ferreteria-tests-webhook-secret-at-least-32-bytes")

warnings.filterwarnings(
    "ignore",
    message=r"unclosed database in <sqlite3\.Connection object.*",
    category=ResourceWarning,
)

import app.crm.models  # noqa: F401
import app.crm.api.auth as crm_auth_module
import app.crm.api.routes as crm_routes_module
from app.crm.api.routes import crm_api
import app.api.console_routes as console_routes_module
from app.api.console_routes import console_api
from app.crm.db import CRMBase


@pytest.fixture
def session_factory(monkeypatch, tmp_path):
    db_path = tmp_path / "crm_test.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    CRMBase.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(crm_routes_module, "SessionLocal", Session)
    monkeypatch.setattr(crm_auth_module, "SessionLocal", Session)
    monkeypatch.setattr(console_routes_module, "SessionLocal", Session)

    yield Session

    close_all_sessions()
    CRMBase.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def app(session_factory):
    flask_app = Flask(__name__)
    flask_app.config.update(TESTING=True)
    flask_app.register_blueprint(crm_api, url_prefix="/api/crm")
    flask_app.register_blueprint(console_api, url_prefix="/api/console")
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client
