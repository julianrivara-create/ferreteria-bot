from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from flask import Flask

from app.api import admin_routes
from app.api.ferreteria_training_routes import ferreteria_training_api
from app.ui.ferreteria_training_routes import ferreteria_training_ui


ROOT = Path(__file__).resolve().parents[1]


def _temp_catalog_and_profile(tmp_path: Path) -> dict:
    source_catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    catalog_dir = tmp_path / "tenant"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    catalog = catalog_dir / "catalog.csv"
    catalog.write_text(source_catalog.read_text(encoding="utf-8"), encoding="utf-8")

    knowledge_dir = catalog_dir / "knowledge"
    source_knowledge = ROOT / "data" / "tenants" / "ferreteria" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    for source_file in source_knowledge.glob("*.yaml"):
        (knowledge_dir / source_file.name).write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")

    profile = yaml.safe_load((ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8"))
    profile.setdefault("paths", {})
    profile["paths"]["catalog"] = str(catalog)
    profile["paths"]["db"] = str(tmp_path / "ferreteria_training_smoke.db")
    profile["paths"]["policies"] = str(ROOT / "data" / "tenants" / "ferreteria" / "policies.md")
    return profile


@pytest.fixture()
def smoke_client(tmp_path, monkeypatch):
    profile = _temp_catalog_and_profile(tmp_path)
    db_path = profile["paths"]["db"]

    monkeypatch.setattr(admin_routes.settings, "ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setattr("app.api.ferreteria_training_routes._tenant_db_path", lambda: db_path)
    monkeypatch.setattr("app.api.ferreteria_training_routes._tenant_profile", lambda: profile)

    app = Flask(__name__, template_folder=str(ROOT / "app" / "ui" / "templates"))
    app.register_blueprint(ferreteria_training_api, url_prefix="/api/admin/ferreteria")
    app.register_blueprint(ferreteria_training_ui)
    return app.test_client()


def test_help_page_surfaces_docs_and_demo_commands(smoke_client):
    resp = smoke_client.get("/ops/ferreteria/training/help", headers={"X-Admin-Token": "test-admin-token"})
    assert resp.status_code == 200
    assert "Cómo usar la herramienta".encode() in resp.data
    assert "Recorrido recomendado".encode() in resp.data
    assert "python3 scripts/bootstrap_training_demo.py".encode() in resp.data


def test_unresolved_terms_quick_draft_returns_main_flow_links(smoke_client):
    resp = smoke_client.post(
        "/api/admin/ferreteria/training/unresolved-terms/suggest",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "term": "taco fisher",
            "canonical": "taco fischer",
            "family": "fijaciones",
            "aliases": "taco fisher, taco plástico",
            "summary": "Corregir un término repetido desde el atajo",
        },
    )
    assert resp.status_code == 201
    payload = resp.get_json()
    assert payload["review_id"]
    assert payload["case_url"].startswith("/ops/ferreteria/training/cases/")
    assert payload["suggestion_url"].startswith("/ops/ferreteria/training/suggestions/")


def test_home_workspace_uses_simple_teaching_copy(smoke_client):
    create = smoke_client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = smoke_client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito canio pvc"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = smoke_client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "failure_tag": "did_not_understand_term",
            "expected_behavior_tag": "understand_term",
            "expected_answer": "Debería entender canio pvc como caño pvc",
            "what_was_wrong": "No reconoció el término regional",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]
    home_page = smoke_client.get(
        f"/ops/ferreteria/training?session_id={session_id}&review_message_id={bot_message_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert home_page.status_code == 200
    assert "Hablar con el bot".encode() in home_page.data
    assert "Esto estuvo mal".encode() in home_page.data
    assert "Guardar como cambio en preparación".encode() in home_page.data
    assert "Opciones avanzadas".encode() in home_page.data
    assert "Paso C. Cambios listos".encode() in home_page.data
