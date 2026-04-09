from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
import yaml
from flask import Flask

from app.api import admin_routes
from app.api.ferreteria_admin_routes import ferreteria_admin_api
from bot_sales.bot import SalesBot
from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales.knowledge.validators import KnowledgeValidationError
from bot_sales.persistence.quote_store import QuoteStore


ROOT = Path(__file__).resolve().parents[1]


def _temp_catalog_and_profile(tmp_path: Path) -> tuple[Path, dict]:
    source_catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    catalog_dir = tmp_path / "tenant"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    catalog = catalog_dir / "catalog.csv"
    catalog.write_text(source_catalog.read_text(encoding="utf-8"), encoding="utf-8")

    profile = yaml.safe_load((ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8"))
    profile.setdefault("paths", {})
    profile["paths"]["catalog"] = str(catalog)
    profile["paths"]["db"] = str(tmp_path / "ferreteria_vnext.db")
    profile["paths"]["policies"] = str(ROOT / "data" / "tenants" / "ferreteria" / "policies.md")
    return catalog, profile


def build_vnext_bot(tmp_path: Path) -> SalesBot:
    catalog, profile = _temp_catalog_and_profile(tmp_path)
    from bot_sales.core.database import Database

    db = Database(
        db_file=str(tmp_path / "ferreteria_vnext.db"),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / "ferreteria_vnext.log"),
    )
    return SalesBot(db=db, api_key="", tenant_id="ferreteria", tenant_profile=profile)


def test_quote_persists_and_reload_survives_bot_restart(tmp_path):
    bot = build_vnext_bot(tmp_path)
    try:
        reply = bot.process_message("persist_1", "Quiero silicona y teflon")
        assert "Presupuesto" in reply
        persisted = bot.quote_service.load_active_quote("persist_1")
        assert persisted is not None
        assert len(persisted["items"]) == 2
    finally:
        bot.close()

    bot2 = build_vnext_bot(tmp_path)
    try:
        bot2.process_message("persist_1", "Agregale un taladro")
        persisted = bot2.quote_service.load_active_quote("persist_1")
        assert persisted is not None
        assert len(persisted["items"]) == 3
        names = " ".join(item.get("original", "").lower() for item in persisted["items"])
        assert "taladro" in names
    finally:
        bot2.close()


def test_reset_closes_persisted_quote(tmp_path):
    bot = build_vnext_bot(tmp_path)
    try:
        bot.process_message("persist_reset", "Quiero silicona y teflon")
        reply = bot.process_message("persist_reset", "nuevo presupuesto")
        assert "borrado" in reply.lower()
        assert bot.quote_service.load_active_quote("persist_reset") is None
        quotes = bot.quote_store.list_quotes(limit=20)
        assert any(q["status"] == "closed_cancelled" for q in quotes)
    finally:
        bot.close()


def test_acceptance_creates_review_requested_handoff(tmp_path, monkeypatch):
    bot = build_vnext_bot(tmp_path)
    calls = []

    def fake_send_email(self, to_email, subject, body, html_body=None):
        calls.append((to_email, subject))
        return {"status": "mock_sent"}

    monkeypatch.setenv("FERRETERIA_HANDOFF_EMAIL_TO", "ops@example.com")
    monkeypatch.setattr("bot_sales.integrations.email_client.EmailClient._send_email", fake_send_email)
    bot.handoff_service.alert_email = "ops@example.com"

    try:
        bot.process_message("accept_1", "Quiero silicona y teflon")
        reply = bot.process_message("accept_1", "Dale cerralo")
        assert "revisi" in reply.lower()
        quote = bot.quote_store.list_quotes(limit=20)[0]
        assert quote["status"] == "review_requested"
        detail = bot.quote_store.get_quote(quote["id"])
        assert any(h["destination_type"] == "admin_queue" for h in detail["handoffs"])
        assert any(h["destination_type"] == "email" for h in detail["handoffs"])
        assert calls
    finally:
        bot.close()


def test_acceptance_handoff_failure_rolls_back_quote_status_and_handoffs(tmp_path):
    bot = build_vnext_bot(tmp_path)

    def broken_create_review_handoff(quote_id, customer_ref):
        bot.quote_store.create_handoff(
            quote_id=quote_id,
            destination_type="admin_queue",
            destination_ref=customer_ref,
            status="queued",
        )
        raise RuntimeError("handoff boom")

    bot.handoff_service.create_review_handoff = broken_create_review_handoff

    try:
        bot.process_message("accept_txn", "Quiero silicona y teflon")
        with pytest.raises(RuntimeError, match="handoff boom"):
            bot.process_message("accept_txn", "Dale cerralo")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        assert quote["status"] in {"open", "waiting_customer_input"}  # depends on whether items resolved
        detail = bot.quote_store.get_quote(quote["id"])
        assert detail["handoffs"] == []
        assert not any(event["event_type"] == "quote_acceptance_requested" for event in detail["events"])
    finally:
        bot.close()


def test_acceptance_is_blocked_when_quote_has_pending_lines(tmp_path):
    bot = build_vnext_bot(tmp_path)
    try:
        bot.process_message("accept_block", "Necesito mecha")
        reply = bot.process_message("accept_block", "Dale cerralo")
        assert "antes de confirmar" in reply.lower()
        quote = bot.quote_store.list_quotes(limit=20)[0]
        assert quote["status"] == "waiting_customer_input"
    finally:
        bot.close()


def test_knowledge_loader_can_save_and_reload_synonyms(tmp_path):
    _, profile = _temp_catalog_and_profile(tmp_path)
    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    before = loader.get_domain("synonyms")
    payload = loader.get_domain("synonyms")
    payload["entries"].append({"canonical": "cinta aisladora", "family": "cable", "aliases": ["aisladora", "cinta aisladora"]})
    saved = loader.save_domain("synonyms", payload)
    loader.invalidate()
    after = loader.get_domain("synonyms")
    assert len(after["entries"]) == len(before["entries"]) + 1
    assert any(entry["canonical"] == "cinta aisladora" for entry in saved["entries"])


def test_knowledge_loader_save_creates_backup_and_invalid_payload_does_not_corrupt_domain(tmp_path):
    _, profile = _temp_catalog_and_profile(tmp_path)
    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    domain_path = Path(loader.get_paths()["synonyms"])
    backup_path = domain_path.with_name(f"{domain_path.name}.bak")

    first_payload = loader.get_domain("synonyms")
    first_payload["entries"].append({"canonical": "espatula", "family": "herramienta", "aliases": ["espatula"]})
    loader.save_domain("synonyms", first_payload)
    first_text = domain_path.read_text(encoding="utf-8")
    assert not backup_path.exists()

    second_payload = loader.get_domain("synonyms")
    second_payload["entries"].append({"canonical": "cinta papel", "family": "pintura", "aliases": ["cinta papel"]})
    loader.save_domain("synonyms", second_payload)

    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == first_text
    persisted = yaml.safe_load(domain_path.read_text(encoding="utf-8"))
    assert any(entry["canonical"] == "cinta papel" for entry in persisted["entries"])

    current_text = domain_path.read_text(encoding="utf-8")
    with pytest.raises(KnowledgeValidationError):
        loader.save_domain("synonyms", {"entries": [{"family": "cano"}]})
    assert domain_path.read_text(encoding="utf-8") == current_text


def test_bot_uses_edited_faq_without_restart(tmp_path):
    bot = build_vnext_bot(tmp_path)
    try:
        loader = bot.knowledge_loader
        payload = loader.get_domain("faqs")
        payload["entries"].append(
            {
                "id": "horarios_especiales",
                "question": "Abren los domingos?",
                "answer": "Los domingos atendemos de 9 a 13 hs.",
                "keywords": ["domingos", "abren domingo"],
                "active": True,
                "tags": ["horarios"],
            }
        )
        loader.save_domain("faqs", payload)
        reply = bot.process_message("faq_edit", "domingos")
        assert "domingo" in reply.lower()
        assert "9 a 13" in reply
    finally:
        bot.close()


@pytest.fixture()
def ferreteria_admin_client(tmp_path, monkeypatch):
    _, profile = _temp_catalog_and_profile(tmp_path)
    db_path = profile["paths"]["db"]

    monkeypatch.setattr(admin_routes.settings, "ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setattr("app.api.ferreteria_admin_routes._tenant_db_path", lambda: db_path)
    monkeypatch.setattr("app.api.ferreteria_admin_routes._tenant_profile", lambda: profile)

    app = Flask(__name__)
    app.register_blueprint(ferreteria_admin_api, url_prefix="/api/admin/ferreteria")
    return app.test_client(), profile


def test_admin_quotes_endpoint_lists_review_queue(tmp_path, ferreteria_admin_client):
    client, _ = ferreteria_admin_client
    bot = build_vnext_bot(tmp_path)
    try:
        bot.process_message("admin_queue", "Quiero silicona y teflon")
        bot.process_message("admin_queue", "Dale cerralo")
    finally:
        bot.close()

    resp = client.get("/api/admin/ferreteria/quotes", headers={"X-Admin-Token": "test-admin-token"})
    assert resp.status_code == 200
    quotes = resp.get_json()["quotes"]
    assert any(q["status"] == "review_requested" for q in quotes)


def test_admin_can_update_knowledge_domain(tmp_path, ferreteria_admin_client):
    client, profile = ferreteria_admin_client
    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    payload = loader.get_domain("synonyms")
    payload["entries"].append({"canonical": "llana", "family": "herramienta", "aliases": ["llana"]})

    resp = client.put(
        "/api/admin/ferreteria/knowledge/synonyms",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"data": payload, "changed_by": "tester", "change_reason": "pilot edit"},
    )
    assert resp.status_code == 200
    loader.invalidate()
    reloaded = loader.get_domain("synonyms")
    assert any(entry["canonical"] == "llana" for entry in reloaded["entries"])


def test_unresolved_terms_are_written_to_db_and_reviewable(tmp_path, ferreteria_admin_client):
    client, _ = ferreteria_admin_client
    bot = build_vnext_bot(tmp_path)
    try:
        bot.process_message("unresolved_db", "Necesito producto zzz-inexistente-abc")
        store = QuoteStore(str(tmp_path / "ferreteria_vnext.db"), tenant_id="ferreteria")
        unresolved = store.list_unresolved_terms(limit=20)
        assert unresolved
        unresolved_id = unresolved[0]["id"]
    finally:
        bot.close()

    resp = client.post(
        f"/api/admin/ferreteria/unresolved-terms/{unresolved_id}/review",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"review_status": "acknowledged", "resolution_note": "revisar catalogo"},
    )
    assert resp.status_code == 200


def test_quote_store_enforces_foreign_keys(tmp_path):
    bot = build_vnext_bot(tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            bot.quote_store.create_handoff(
                quote_id="missing_quote",
                destination_type="admin_queue",
                destination_ref="session-x",
                status="queued",
            )
    finally:
        bot.close()
