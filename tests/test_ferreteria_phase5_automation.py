from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from flask import Flask

from app.api import admin_routes
from app.api.ferreteria_admin_routes import ferreteria_admin_api
from app.ui.ferreteria_admin_routes import ferreteria_admin_ui
from bot_sales.bot import SalesBot
from bot_sales.core.database import Database
from bot_sales.persistence.quote_store import QuoteStore
from bot_sales.services.quote_automation_service import QuoteAutomationService, QuoteAutomationError


ROOT = Path(__file__).resolve().parents[1]


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
    profile["paths"]["db"] = str(tmp_path / "ferreteria_phase5.db")
    profile["paths"]["policies"] = str(ROOT / "data" / "tenants" / "ferreteria" / "policies.md")
    return catalog, profile


def build_bot(tmp_path: Path) -> SalesBot:
    catalog, profile = _temp_catalog_and_profile(tmp_path)
    db = Database(
        db_file=str(tmp_path / "ferreteria_phase5.db"),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / "ferreteria_phase5.log"),
    )
    return SalesBot(db=db, api_key="", tenant_id="ferreteria", tenant_profile=profile)


@pytest.fixture()
def phase5_admin_client(tmp_path, monkeypatch):
    _, profile = _temp_catalog_and_profile(tmp_path)
    db_path = profile["paths"]["db"]

    monkeypatch.setattr(admin_routes.settings, "ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setattr("app.api.ferreteria_admin_routes._tenant_db_path", lambda: db_path)
    monkeypatch.setattr("app.api.ferreteria_admin_routes._tenant_profile", lambda: profile)

    app = Flask(__name__, template_folder=str(ROOT / "app" / "ui" / "templates"))
    app.register_blueprint(ferreteria_admin_api, url_prefix="/api/admin/ferreteria")
    app.register_blueprint(ferreteria_admin_ui)
    return app.test_client(), profile


def _service(profile: dict) -> QuoteAutomationService:
    store = QuoteStore(profile["paths"]["db"], tenant_id="ferreteria")
    return QuoteAutomationService(store, tenant_id="ferreteria", tenant_profile=profile)


def test_phase5_ready_for_followup_quote_becomes_eligible(tmp_path):
    bot = build_bot(tmp_path)
    try:
        bot.process_message("phase5_eligible", "Quiero silicona y teflon")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        # Force lines to resolved so automation eligibility check passes
        bot.quote_store.conn.execute(
            "UPDATE quote_lines SET line_status='resolved_high_confidence', selected_unit_price=5000, family_id='silicona', issue_type=NULL WHERE quote_id=?",
            (quote["id"],),
        )
        bot.quote_store.conn.commit()
        bot.quote_store.update_quote_header(
            quote["id"],
            status="ready_for_followup",
            channel="whatsapp",
            customer_ref="5491111111111",
        )
        refreshed = bot.quote_automation_service.refresh_quote_automation(quote["id"])
        assert refreshed["decision"]["eligible"] is True
        assert refreshed["quote"]["automation_state"] == "eligible_for_auto_followup"
    finally:
        bot.close()


def test_phase5_blocked_quote_is_not_automation_eligible(tmp_path):
    bot = build_bot(tmp_path)
    try:
        bot.process_message("phase5_blocked", "Necesito mecha")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        bot.quote_store.update_quote_header(
            quote["id"],
            status="ready_for_followup",
            channel="whatsapp",
            customer_ref="5491111111111",
        )
        refreshed = bot.quote_automation_service.refresh_quote_automation(quote["id"])
        assert refreshed["decision"]["eligible"] is False
        assert refreshed["quote"]["automation_state"] == "automation_blocked"
        assert refreshed["quote"]["automation_reason"] == "blocking_line_status"
    finally:
        bot.close()


def test_phase5_substitute_selected_quote_is_blocked(tmp_path):
    bot = build_bot(tmp_path)
    try:
        bot.process_message("phase5_substitute", "Quiero silicona y teflon")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        # Force lines to resolved so substitute flag is the only blocker
        bot.quote_store.conn.execute(
            "UPDATE quote_lines SET line_status='resolved_high_confidence', selected_unit_price=5000, family_id='silicona', issue_type=NULL WHERE quote_id=?",
            (quote["id"],),
        )
        bot.quote_store.conn.commit()
        bot.quote_store.conn.execute(
            "UPDATE quote_lines SET selected_via_substitute = 1 WHERE quote_id = ? AND line_number = 1",
            (quote["id"],),
        )
        bot.quote_store.conn.commit()
        bot.quote_store.update_quote_header(
            quote["id"],
            status="ready_for_followup",
            channel="whatsapp",
            customer_ref="5491111111111",
        )
        refreshed = bot.quote_automation_service.refresh_quote_automation(quote["id"])
        assert refreshed["quote"]["automation_state"] == "automation_blocked"
        assert refreshed["quote"]["automation_reason"] == "substitute_selected"
    finally:
        bot.close()


def test_phase5_send_auto_followup_success(tmp_path, monkeypatch):
    bot = build_bot(tmp_path)
    calls = []
    try:
        bot.process_message("phase5_send", "Quiero silicona y teflon")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        # Force lines to resolved so automation eligibility check passes
        bot.quote_store.conn.execute(
            "UPDATE quote_lines SET line_status='resolved_high_confidence', selected_unit_price=5000, family_id='silicona', issue_type=NULL WHERE quote_id=?",
            (quote["id"],),
        )
        bot.quote_store.conn.commit()
        bot.quote_store.update_quote_header(
            quote["id"],
            status="ready_for_followup",
            channel="whatsapp",
            customer_ref="5491111111111",
        )
        bot.quote_automation_service.refresh_quote_automation(quote["id"])

        monkeypatch.setattr(
            "app.services.channels.whatsapp_meta.WhatsAppMeta.send_reply",
            lambda to, text, tenant_id=None: calls.append((to, text, tenant_id)) or {"status": "sent"},
        )
        result = bot.quote_automation_service.send_quote_ready_followup(quote["id"], actor="tester")
        detail = result["quote"]
        assert detail["automation_state"] == "awaiting_customer_confirmation"
        assert detail["auto_followup_count"] == 1
        assert detail["last_auto_followup_at"]
        assert calls and calls[0][0] == "5491111111111"
        assert "presupuesto listo" in calls[0][1].lower()
        assert calls[0][2] == "ferreteria"
        assert any(event["event_type"] == "automation_followup_sent" for event in detail["events"])
    finally:
        bot.close()


def test_phase5_send_is_blocked_on_unsupported_channel(tmp_path):
    bot = build_bot(tmp_path)
    try:
        bot.process_message("phase5_cli", "Quiero silicona y teflon")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        bot.quote_store.update_quote_header(quote["id"], status="ready_for_followup", channel="cli")
        refreshed = bot.quote_automation_service.refresh_quote_automation(quote["id"])
        assert refreshed["quote"]["automation_state"] == "automation_blocked"
        assert refreshed["quote"]["automation_reason"] == "unsupported_channel"
        with pytest.raises(QuoteAutomationError):
            bot.quote_automation_service.send_quote_ready_followup(quote["id"], actor="tester")
    finally:
        bot.close()


def test_phase5_admin_api_and_ui_expose_automation_controls(phase5_admin_client, tmp_path, monkeypatch):
    client, profile = phase5_admin_client
    bot = build_bot(tmp_path)
    try:
        bot.process_message("phase5_admin", "Quiero silicona y teflon")
        quote = bot.quote_store.list_quotes(limit=20)[0]
        # Force lines to resolved so automation eligibility check passes
        bot.quote_store.conn.execute(
            "UPDATE quote_lines SET line_status='resolved_high_confidence', selected_unit_price=5000, family_id='silicona', issue_type=NULL WHERE quote_id=?",
            (quote["id"],),
        )
        bot.quote_store.conn.commit()
        bot.quote_store.update_quote_header(
            quote["id"],
            status="ready_for_followup",
            channel="whatsapp",
            customer_ref="5491111111111",
        )
        bot.quote_automation_service.refresh_quote_automation(quote["id"])
    finally:
        bot.close()

    quotes = client.get(
        "/api/admin/ferreteria/quotes?automation_state=eligible_for_auto_followup",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert quotes.status_code == 200
    payload = quotes.get_json()["quotes"]
    assert payload and payload[0]["automation_state"] == "eligible_for_auto_followup"

    evaluate = client.post(
        f"/api/admin/ferreteria/quotes/{quote['id']}/automation/evaluate",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer"},
    )
    assert evaluate.status_code == 200

    monkeypatch.setattr(
        "app.services.channels.whatsapp_meta.WhatsAppMeta.send_reply",
        lambda to, text, tenant_id=None: {"status": "sent"},
    )
    send = client.post(
        f"/api/admin/ferreteria/quotes/{quote['id']}/automation/send",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer"},
    )
    assert send.status_code == 200
    assert send.get_json()["quote"]["automation_state"] == "awaiting_customer_confirmation"

    reset = client.post(
        f"/api/admin/ferreteria/quotes/{quote['id']}/automation/reset",
        headers={"X-Admin-Token": "test-admin-token", "Content-Type": "application/json"},
        json={"operator": "reviewer"},
    )
    assert reset.status_code == 200
    assert reset.get_json()["quote"]["automation_state"] == "manual_only"

    page = client.get(
        f"/ops/ferreteria/quotes/{quote['id']}",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Automation" in body
    assert "Evaluate automation" in body
    assert "Send auto follow-up" in body
