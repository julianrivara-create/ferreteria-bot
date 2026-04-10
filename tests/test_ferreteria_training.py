from __future__ import annotations

from pathlib import Path
import sqlite3
from unittest.mock import MagicMock

import pytest
import yaml
from flask import Flask

from app.api import admin_routes
from app.api.ferreteria_training_routes import ferreteria_training_api
from app.ui.ferreteria_training_routes import ferreteria_training_ui
from bot_sales.bot import SalesBot
from bot_sales.core.database import Database
from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales.persistence.quote_store import QuoteStore
from bot_sales.training.demo_bootstrap import bootstrap_training_demo
from bot_sales.training.store import TrainingStore


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"


def _temp_catalog_and_profile(tmp_path: Path) -> tuple[Path, dict]:
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
    profile["paths"]["db"] = str(tmp_path / "ferreteria_training.db")
    profile["paths"]["policies"] = str(ROOT / "data" / "tenants" / "ferreteria" / "policies.md")
    return catalog, profile


@pytest.fixture()
def training_client(tmp_path, monkeypatch):
    _, profile = _temp_catalog_and_profile(tmp_path)
    db_path = profile["paths"]["db"]

    monkeypatch.setattr(admin_routes.settings, "ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setattr("app.api.ferreteria_training_routes._tenant_db_path", lambda: db_path)
    monkeypatch.setattr("app.api.ferreteria_training_routes._tenant_profile", lambda: profile)

    app = Flask(__name__, template_folder=str(ROOT / "app" / "ui" / "templates"))
    app.register_blueprint(ferreteria_training_api, url_prefix="/api/admin/ferreteria")
    app.register_blueprint(ferreteria_training_ui)
    return app.test_client(), profile


def test_training_session_and_message_persistence_are_isolated_from_quotes(training_client):
    client, profile = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    assert create.status_code == 201
    session_id = create.get_json()["session"]["id"]
    assert session_id.startswith("training:")

    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Quiero silicona y teflon"},
    )
    assert send.status_code == 200
    payload = send.get_json()
    assert payload["message"]["route_source"] == "deterministic"
    assert payload["message"]["total_tokens"] == 0

    detail = client.get(
        f"/api/admin/ferreteria/training/sessions/{session_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert detail.status_code == 200
    session = detail.get_json()["session"]
    assert len(session["messages"]) == 2

    quote_store = QuoteStore(profile["paths"]["db"], tenant_id="ferreteria")
    try:
        assert quote_store.list_quotes(limit=20) == []
    finally:
        quote_store.close()


def test_sandbox_acceptance_does_not_trigger_handoffs_or_email(tmp_path, monkeypatch):
    _, profile = _temp_catalog_and_profile(tmp_path)
    handoff_calls = []
    email_calls = []

    def track_handoff(self, quote_id, customer_ref):
        handoff_calls.append((quote_id, customer_ref))

    def track_email(self, to_email, subject, body, html_body=None):
        email_calls.append((to_email, subject))
        return {"status": "mock_sent"}

    monkeypatch.setenv("FERRETERIA_HANDOFF_EMAIL_TO", "ops@example.com")
    monkeypatch.setattr("bot_sales.services.handoff_service.HandoffService.create_review_handoff", track_handoff)
    monkeypatch.setattr("bot_sales.integrations.email_client.EmailClient._send_email", track_email)
    db = Database(
        db_file=str(tmp_path / "sandbox_runtime.db"),
        catalog_csv=profile["paths"]["catalog"],
        log_path=str(tmp_path / "sandbox_runtime.log"),
    )
    bot = SalesBot(db=db, api_key="", tenant_id="ferreteria", tenant_profile=profile, sandbox_mode=True)

    try:
        opened = bot.process_message("sandbox_accept", "Quiero silicona y teflon")
        assert "presupuesto" in opened.lower()
        accepted_quote_id = bot._accept_quote_for_review(
            "sandbox_accept",
            "Dale cerralo",
            "✓ Perfecto. Lo dejo pedido para revisión interna.",
        )
        assert accepted_quote_id
        detail = bot.quote_store.get_quote(accepted_quote_id)
        assert detail is not None
        assert detail["status"] == "review_requested"
        assert detail["handoffs"] == []
    finally:
        bot.close()
    assert handoff_calls == []
    assert email_calls == []


def test_training_chat_reset_uses_bot_reset_session(training_client, monkeypatch):
    client, _ = training_client
    fake_bot = MagicMock()

    monkeypatch.setattr("bot_sales.core.tenancy.tenant_manager.get_bot", lambda tenant_id: fake_bot)

    resp = client.post(
        "/ops/ferreteria/training/api/chat-reset",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"session_id": "training_test_reset"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    fake_bot.reset_session.assert_called_once_with("training_test_reset")


def test_sandbox_human_handoff_path_does_not_call_external_handoff_logic(training_client, monkeypatch):
    client, _ = training_client
    handoff_calls = []

    def fail_if_called(self, razon, contacto, nombre=None, resumen=None):
        handoff_calls.append((razon, contacto))
        raise AssertionError("sandbox should not call derivar_humano")

    monkeypatch.setattr("bot_sales.core.business_logic.BusinessLogic.derivar_humano", fail_if_called)
    monkeypatch.setattr("bot_sales.bot.SalesBot._try_ferreteria_pre_route", lambda self, session_id, user_message: None)
    monkeypatch.setattr(
        "bot_sales.bot.SalesBot._run_sales_intelligence",
        lambda self, session_id, user_message: {
            "human_handoff": {"enabled": True, "reason": "manual escalation"},
            "reply_text": "Te paso con un asesor para continuar.",
        },
    )

    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    sent = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito ayuda de un asesor"},
    )
    assert sent.status_code == 200
    assert sent.get_json()["message"]["route_source"] == "model_assisted"
    assert handoff_calls == []


def test_sandbox_unresolved_messages_do_not_write_shared_log(training_client, tmp_path, monkeypatch):
    client, _ = training_client
    shared_log = tmp_path / "shared_unresolved.jsonl"
    monkeypatch.setenv("FERRETERIA_UNRESOLVED_LOG", str(shared_log))

    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    sent = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito mecha"},
    )
    assert sent.status_code == 200
    assert sent.get_json()["message"]["route_source"] == "deterministic"
    assert not shared_log.exists() or shared_log.read_text(encoding="utf-8").strip() == ""


def test_review_suggestion_approval_and_apply_updates_knowledge(training_client):
    client, profile = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito caño pvc"},
    )
    bot_message_id = send.get_json()["message"]["id"]

    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "expected_answer": "Deberia entender cano pvc como cano",
            "what_was_wrong": "Le falta sinonimo",
            "created_by": "tester",
        },
    )
    assert review.status_code == 200
    review_id = review.get_json()["review"]["id"]

    suggestion = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/suggestions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "domain": "synonym",
            "summary": "Agregar alias comun",
            "suggested_payload": {
                "canonical": "caño pvc",
                "family": "cano",
                "aliases": ["cano pvc", "caño pvc"],
            },
            "created_by": "tester",
        },
    )
    assert suggestion.status_code == 201
    suggestion_id = suggestion.get_json()["suggestion"]["id"]

    approve = client.post(
        f"/api/admin/ferreteria/training/suggestions/{suggestion_id}/approve",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"reason": "sentido comun", "operator": "reviewer"},
    )
    assert approve.status_code == 200
    assert approve.get_json()["suggestion"]["status"] == "approved"

    apply = client.post(
        f"/api/admin/ferreteria/training/suggestions/{suggestion_id}/apply",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"reason": "activar cambio", "operator": "reviewer"},
    )
    assert apply.status_code == 200
    assert apply.get_json()["suggestion"]["status"] == "applied"

    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    loader.invalidate()
    synonyms = loader.get_domain("synonyms")
    assert any(entry["canonical"] == "caño pvc" for entry in synonyms["entries"])


def test_training_usage_and_token_ceiling(monkeypatch, training_client):
    client, profile = training_client

    def fake_send_message(self, messages, functions=None):
        return {
            "role": "assistant",
            "content": "Respuesta de evaluacion",
            "meta": {
                "response_mode": "openai",
                "used_fallback": False,
                "model": "gpt-4o-mini",
                "prompt_tokens": 40,
                "completion_tokens": 20,
                "total_tokens": 60,
                "latency_ms": 12,
            },
        }

    monkeypatch.setattr("bot_sales.core.chatgpt.ChatGPTClient.send_message", fake_send_message)
    monkeypatch.setattr("bot_sales.bot.SalesBot._try_ferreteria_pre_route", lambda self, session_id, user_message: None)
    monkeypatch.setattr("bot_sales.bot.SalesBot._run_sales_intelligence", lambda self, session_id, user_message: None)

    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "token_ceiling": 50, "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]

    blocked = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Hola, te queria consultar algo"},
    )
    assert blocked.status_code == 400
    assert "ceiling" in blocked.get_json()["error"].lower()

    detail = client.get(
        f"/api/admin/ferreteria/training/sessions/{session_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert detail.get_json()["session"]["status"] == "limit_reached"

    create_ok = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_ok = create_ok.get_json()["session"]["id"]
    sent = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_ok}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Hola, te queria consultar algo"},
    )
    assert sent.status_code == 200
    assert sent.get_json()["message"]["total_tokens"] == 60
    assert sent.get_json()["message"]["route_source"] == "model_assisted"

    usage = client.get(
        "/api/admin/ferreteria/training/usage",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert usage.status_code == 200
    assert usage.get_json()["daily"][0]["total_tokens"] >= 60
    assert any(row["model_name"] == "gpt-4o-mini" for row in usage.get_json()["model_distribution"])


def test_training_case_export_and_ui_routes(training_client):
    client, profile = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Quiero silicona"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "correct",
            "expected_answer": "Ok",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]
    export = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/export-regression",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "tester"},
    )
    assert export.status_code == 201
    assert export.get_json()["export"]["fixture_name"].startswith("training_case_")

    case_detail = client.get(
        f"/api/admin/ferreteria/training/cases/{review_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert case_detail.status_code == 200
    assert case_detail.get_json()["case"]["exports"]

    candidate = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/regression-candidate",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "tester"},
    )
    assert candidate.status_code == 201
    assert candidate.get_json()["candidate"]["status"] == "draft"

    unauth = client.get("/ops/ferreteria/training")
    assert unauth.status_code == 302
    auth = client.get("/ops/ferreteria/training", headers={"X-Admin-Token": "test-admin-token"})
    assert auth.status_code == 200
    assert "Hablar con el bot".encode() in auth.data
    sandbox = client.get("/ops/ferreteria/training/sandbox", headers={"X-Admin-Token": "test-admin-token"})
    assert sandbox.status_code == 200
    assert "Paso B. Enseñarle qué tendría que haber hecho".encode() in sandbox.data
    case_page = client.get(
        f"/ops/ferreteria/training/cases/{review_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert case_page.status_code == 200
    assert "Ajustar la corrección recomendada".encode() in case_page.data
    assert "¿Qué tipo de problema hubo acá?".encode() in case_page.data


def test_training_sandbox_ui_can_review_any_assistant_message(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]

    first = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Quiero silicona"},
    )
    first_message_id = first.get_json()["message"]["id"]
    second = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Quiero teflon"},
    )
    assert second.status_code == 200

    page = client.get(
        f"/ops/ferreteria/training/sandbox?session_id={session_id}&review_message_id={first_message_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert page.status_code == 200
    assert "Esto estuvo mal".encode() in page.data
    assert f'name="bot_message_id" value="{first_message_id}"'.encode() in page.data
    assert "Respuesta elegida del bot".encode() in page.data
    assert "¿Qué estuvo mal?".encode() in page.data


def test_training_home_simple_review_creates_recommended_draft(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito canio pvc"},
    )
    bot_message_id = send.get_json()["message"]["id"]

    saved = client.post(
        "/ops/ferreteria/training",
        headers={"X-Admin-Token": "test-admin-token"},
        data={
            "action": "save_simple_review",
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "simple_choice": "understand_term",
            "simple_what_was_wrong": "No reconoció una forma real de pedir el producto.",
            "simple_first_step": "Primero tendría que haber entendido que hablaba de caño pvc.",
            "simple_expected_answer": "Debería entenderlo como caño pvc y seguir el flujo normal.",
            "simple_family": "cano",
            "simple_canonical_product": "caño pvc",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 302
    assert "saved_suggestion_id=" in saved.headers["Location"]

    home = client.get(saved.headers["Location"], headers={"X-Admin-Token": "test-admin-token"})
    assert home.status_code == 200
    assert "Cambio en preparación".encode() in home.data

    suggestions = client.get(
        "/api/admin/ferreteria/training/suggestions",
        headers={"X-Admin-Token": "test-admin-token"},
    ).get_json()["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["domain"] == "synonym"
    assert suggestions[0]["status"] == "draft"


def test_training_case_detail_guides_problem_type_and_human_readable_suggestion_review(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito mecha"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "failure_tag": "should_have_asked_clarification",
            "expected_answer": "Deberia pedir material y medida",
            "what_was_wrong": "Le falto una pregunta",
            "missing_clarification": "Preguntar para que superficie es",
            "suggested_family": "mecha",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]

    case_page = client.get(
        f"/ops/ferreteria/training/cases/{review_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert case_page.status_code == 200
    assert "¿Qué tipo de problema hubo acá?".encode() in case_page.data
    assert "Corrección recomendada".encode() in case_page.data
    assert "Tendría que haber pedido una aclaración".encode() in case_page.data
    assert "Antes de guardar este borrador".encode() in case_page.data
    assert "Primera acción esperada".encode() in case_page.data

    created = client.post(
        f"/ops/ferreteria/training/cases/{review_id}",
        headers={"X-Admin-Token": "test-admin-token"},
        data={
            "action": "create_suggestion",
            "problem_type": "should_have_asked_clarification",
            "domain": "",
            "summary": "La pregunta inicial tiene que ser mas clara",
            "source_message": "Necesito mecha",
            "repeated_term": "mecha",
            "family": "mecha",
            "clarification_short_prompt": "¿Para madera, metal o pared?",
            "clarification_prompt": "¿La necesitás para madera, metal, pared o cerámica?",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert "Qué cambia".encode() in created.data
    assert "Área afectada".encode() in created.data
    assert "En qué fijarse".encode() in created.data
    assert "Cambiar la primera pregunta".encode() in created.data
    assert "Antes".encode() in created.data
    assert "Después".encode() in created.data
    assert "Detalle técnico".encode() in created.data


def test_training_workflow_views_show_action_oriented_statuses(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    first = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito cano pvc"},
    )
    first_message_id = first.get_json()["message"]["id"]
    second = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito mecha"},
    )
    assert second.status_code == 200

    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": first_message_id,
            "review_label": "incorrect",
            "expected_answer": "Deberia reconocer cano pvc",
            "what_was_wrong": "Falta sinonimo",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]
    created_suggestion = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/suggestions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "domain": "synonym",
            "summary": "Agregar termino comun",
            "suggested_payload": {
                "canonical": "caño pvc",
                "family": "cano",
                "aliases": ["cano pvc"],
            },
            "created_by": "tester",
        },
    )
    assert created_suggestion.status_code == 201

    session_history = client.get(
        "/ops/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert session_history.status_code == 200
    assert "Avance de revisión".encode() in session_history.data
    assert "pendiente".encode() in session_history.data

    cases_page = client.get(
        "/ops/ferreteria/training/cases",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert cases_page.status_code == 200
    assert "Casos sin propuesta".encode() in cases_page.data
    assert "Propuesta en borrador".encode() in cases_page.data

    queue_page = client.get(
        "/ops/ferreteria/training/suggestions",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert queue_page.status_code == 200
    assert "Cambios listos".encode() in queue_page.data
    assert "No hay cambios listos para activar".encode() in queue_page.data

    draft_queue = client.get(
        "/ops/ferreteria/training/suggestions?queue=draft",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert draft_queue.status_code == 200
    assert "Historial de cambios".encode() in draft_queue.data
    assert "Corrección de término".encode() in draft_queue.data


def test_training_workflow_home_and_regression_next_actions(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito termofusion"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "failure_tag": "did_not_understand_term",
            "expected_answer": "Deberia reconocer el termino",
            "what_was_wrong": "No entendio la palabra",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]
    candidate = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/regression-candidate",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "tester"},
    )
    assert candidate.status_code == 201

    home = client.get("/ops/ferreteria/training", headers={"X-Admin-Token": "test-admin-token"})
    assert home.status_code == 200
    assert "Hablar con el bot".encode() in home.data
    assert "Paso B. Enseñarle qué tendría que haber hecho".encode() in home.data
    assert "Guardar como cambio en preparación".encode() in home.data
    assert "Paso C. Cambios listos".encode() in home.data
    assert "Más herramientas".encode() in home.data

    case_page = client.get(
        f"/ops/ferreteria/training/cases/{review_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert case_page.status_code == 200
    assert "Caso futuro listo para exportar".encode() in case_page.data
    assert "Cobertura actual".encode() in case_page.data
    assert "Usá corrección + caso futuro".encode() in case_page.data


def test_training_structured_review_support_is_persisted_and_displayed(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito canio pvc"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "failure_tag": "did_not_understand_term",
            "failure_detail_tag": "misspelling_or_regional_term",
            "expected_behavior_tag": "understand_term",
            "clarification_dimension": "material",
            "expected_answer": "Deberia entender canio pvc como caño pvc",
            "what_was_wrong": "No reconocio el termino regional",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]

    case_page = client.get(
        f"/ops/ferreteria/training/cases/{review_id}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert case_page.status_code == 200
    assert "Motivo específico".encode() in case_page.data
    assert "Era una forma regional o mal escrita".encode() in case_page.data
    assert "Entender bien cómo lo pidió el cliente".encode() in case_page.data
    assert "Primer dato: Material o tipo de superficie".encode() in case_page.data
    assert "Corregir cómo entiende un término".encode() in case_page.data


def test_training_demo_bootstrap_exports_isolated_snapshots(tmp_path):
    manifest = bootstrap_training_demo(tmp_path / "training_demo")

    snapshot_dir = Path(manifest["snapshot_dir"])
    assert snapshot_dir.exists()
    assert Path(manifest["db_path"]).exists()
    assert Path(manifest["index_path"]).exists()
    assert Path(manifest["walkthrough_path"]).exists()

    index_html = Path(manifest["index_path"]).read_text(encoding="utf-8")
    assert "Interfaz de entrenamiento Ferretería" in index_html
    assert "Hablar con el bot" in index_html
    assert "Detalle de borrador" in index_html

    workflow_html = (snapshot_dir / "01_workflow_home.html").read_text(encoding="utf-8")
    assert "Hablar con el bot" in workflow_html
    assert "Paso B. Enseñarle qué tendría que haber hecho" in workflow_html
    assert "Paso C. Cambios listos" in workflow_html

    sandbox_html = (snapshot_dir / "02_sandbox_review.html").read_text(encoding="utf-8")
    assert "Hablar con el bot" in sandbox_html
    assert "Esto estuvo mal" in sandbox_html
    assert "Guardar como cambio en preparación" in sandbox_html

    case_html = (snapshot_dir / "04_case_regression.html").read_text(encoding="utf-8")
    assert "Caso futuro listo para exportar" in case_html
    assert "Cobertura actual" in case_html

    suggestion_html = (snapshot_dir / "05_suggestion_draft.html").read_text(encoding="utf-8")
    assert "Qué cambia" in suggestion_html
    assert "Área afectada" in suggestion_html
    assert "Detalle técnico" in suggestion_html


def test_training_operator_docs_exist_and_cover_core_topics():
    guide = DOCS_DIR / "guia_operativa_entrenamiento_ferreteria.md"
    faq = DOCS_DIR / "faq_entrenamiento_ferreteria.md"
    assert guide.exists()
    assert faq.exists()

    guide_text = guide.read_text(encoding="utf-8")
    faq_text = faq.read_text(encoding="utf-8")

    assert "## Qué es esta herramienta" in guide_text
    assert "## El flujo principal: A → B → C" in guide_text
    assert "## Qué significan los estados de un cambio" in guide_text
    assert "## ¿Esta herramienta cambia el bot automáticamente?" in faq_text
    assert "## ¿Cuál es la diferencia entre aprobar y activar?" in faq_text


def test_phase3_domains_and_state_transitions(training_client):
    client, profile = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito mecha"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "expected_answer": "Deberia pedir material y medida",
            "what_was_wrong": "Falta comportamiento estructurado",
            "missing_clarification": "Preguntar superficie",
            "suggested_family": "mecha",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]

    family_rule = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/suggestions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "domain": "family_rule",
            "summary": "Hacer mas estricta la familia mecha",
            "suggested_payload": {
                "family": "mecha_fina_test",
                "allowed_categories": ["accesorios"],
                "match_terms": ["mecha fina test"],
                "required_dimensions": ["material"],
            },
            "created_by": "tester",
        },
    )
    assert family_rule.status_code == 201

    language_pattern = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/suggestions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "domain": "language_pattern",
            "summary": "Agregar sinonimo regional",
            "suggested_payload": {
                "section": "regional_terms",
                "key": "canio",
                "value": "cano",
            },
            "created_by": "tester",
        },
    )
    assert language_pattern.status_code == 201
    suggestion_id = language_pattern.get_json()["suggestion"]["id"]

    reject = client.post(
        f"/api/admin/ferreteria/training/suggestions/{suggestion_id}/reject",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "No usar esta variante"},
    )
    assert reject.status_code == 200
    assert reject.get_json()["suggestion"]["status"] == "rejected"

    apply_rejected = client.post(
        f"/api/admin/ferreteria/training/suggestions/{suggestion_id}/apply",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "No deberia aplicar"},
    )
    assert apply_rejected.status_code == 400

    approve_rejected = client.post(
        f"/api/admin/ferreteria/training/suggestions/{suggestion_id}/approve",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "No deberia reaprobar"},
    )
    assert approve_rejected.status_code == 400

    draft_apply = client.post(
        f"/api/admin/ferreteria/training/suggestions/{family_rule.get_json()['suggestion']['id']}/apply",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "Draft no aplica"},
    )
    assert draft_apply.status_code == 400

    substitute_rule = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/suggestions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "domain": "substitute_rule",
            "summary": "Crear regla de sustitucion de prueba",
            "suggested_payload": {
                "group_id": "phase3_test_group",
                "source_families": ["mecha"],
                "allowed_targets": ["mecha"],
                "required_matching_dimensions": ["size"],
                "allowed_dimension_drift": [],
                "blocked_dimension_mismatches": ["material"],
                "blocked_terms": [],
                "reason_template": "Mantener compatibilidad",
            },
            "created_by": "tester",
        },
    )
    assert substitute_rule.status_code == 201
    substitute_id = substitute_rule.get_json()["suggestion"]["id"]

    approve = client.post(
        f"/api/admin/ferreteria/training/suggestions/{substitute_id}/approve",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "Regla valida"},
    )
    assert approve.status_code == 200

    reject_approved = client.post(
        f"/api/admin/ferreteria/training/suggestions/{substitute_id}/reject",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "No deberia rechazar aprobado"},
    )
    assert reject_approved.status_code == 400

    applied = client.post(
        f"/api/admin/ferreteria/training/suggestions/{substitute_id}/apply",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "Activar"},
    )
    assert applied.status_code == 200

    reapply = client.post(
        f"/api/admin/ferreteria/training/suggestions/{substitute_id}/apply",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer", "reason": "No deberia reaplicar"},
    )
    assert reapply.status_code == 400

    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    loader.invalidate()
    rules = loader.get_domain("substitute_rules")
    assert any(rule["group_id"] == "phase3_test_group" for rule in rules["rules"])


def test_invalid_suggestion_payload_is_rejected_early(training_client):
    client, _ = training_client
    create = client.post(
        "/api/admin/ferreteria/training/sessions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"mode_profile": "cheap", "operator": "tester"},
    )
    session_id = create.get_json()["session"]["id"]
    send = client.post(
        f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"message": "Necesito cano pvc"},
    )
    bot_message_id = send.get_json()["message"]["id"]
    review = client.post(
        "/api/admin/ferreteria/training/reviews",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "session_id": session_id,
            "bot_message_id": bot_message_id,
            "review_label": "incorrect",
            "expected_answer": "Falta correccion",
            "created_by": "tester",
        },
    )
    review_id = review.get_json()["review"]["id"]

    invalid = client.post(
        f"/api/admin/ferreteria/training/reviews/{review_id}/suggestions",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={
            "domain": "family_rule",
            "summary": "Payload invalido",
            "suggested_payload": {
                "family": "bad_family_only",
            },
            "created_by": "tester",
        },
    )
    assert invalid.status_code == 400
    assert "allowed_categories" in invalid.get_json()["error"]


def test_training_store_enforces_foreign_keys(training_client):
    _, profile = training_client
    store = TrainingStore(profile["paths"]["db"], tenant_id="ferreteria")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.add_approval(
                "missing_suggestion",
                action="approve",
                acted_by="tester",
                reason="should fail",
                before={"status": "draft"},
                after={"status": "approved"},
            )
    finally:
        store.close()
