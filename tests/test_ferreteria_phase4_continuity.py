from pathlib import Path

import yaml

from bot_sales.bot import SalesBot
from bot_sales.core.database import Database


ROOT = Path(__file__).resolve().parents[1]


def build_bot(tmp_path: Path, db_name: str = "phase4.db") -> SalesBot:
    catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    profile = yaml.safe_load((ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8"))
    db = Database(
        db_file=str(tmp_path / db_name),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / f"{db_name}.log"),
    )
    return SalesBot(db=db, api_key="", tenant_id="ferreteria", tenant_profile=profile)


def test_phase4_followup_after_reload_preserves_line_context(tmp_path):
    bot = build_bot(tmp_path, "phase4_reload.db")
    try:
        first = bot.process_message("phase4_reload", "Necesito mecha")
        assert "falta información clave" in first.lower()
    finally:
        bot.close()

    bot2 = build_bot(tmp_path, "phase4_reload.db")
    try:
        second = bot2.process_message("phase4_reload", "8mm para madera")
        assert "mecha madera 8mm" in second.lower()
        active = bot2.sessions["phase4_reload"]["active_quote"]
        assert active[0]["status"] == "resolved"
        assert active[0]["family"] == "mecha"
        assert active[0]["last_targeted_dimension"] in {"size", "material"}
    finally:
        bot2.close()


def test_phase4_partial_followup_updates_only_targeted_blocked_line(tmp_path):
    bot = build_bot(tmp_path, "phase4_targeting.db")
    try:
        opened = bot.process_message("phase4_target", "Necesito mecha y broca widia")
        assert "broca widia" in opened.lower()
        reply = bot.process_message("phase4_target", "para madera 8mm")
        assert "mecha madera 8mm" in reply.lower()
        assert "broca widia" in reply.lower()
        active = bot.sessions["phase4_target"]["active_quote"]
        mecha = next(item for item in active if item.get("family") == "mecha")
        broca = next(item for item in active if item.get("family") == "broca")
        assert mecha["status"] == "resolved"
        assert broca["status"] == "blocked_by_missing_info"
        assert "size" in (broca.get("missing_dimensions") or [])
    finally:
        bot.close()


def test_phase4_recoverable_followup_stays_deterministic_and_skips_sales_intelligence(tmp_path, monkeypatch):
    bot = build_bot(tmp_path, "phase4_recoverable.db")
    try:
        bot.process_message("phase4_recoverable", "Necesito mecha")

        def fail_if_called(self, session_id, user_message):
            raise AssertionError("recoverable continuation should not call sales intelligence")

        monkeypatch.setattr(SalesBot, "_run_sales_intelligence", fail_if_called)
        reply = bot.process_message("phase4_recoverable", "8mm para madera")
        assert "mecha madera 8mm" in reply.lower()
        assert bot.get_last_turn_meta("phase4_recoverable")["route_source"] == "deterministic"
    finally:
        bot.close()


def test_phase4_operator_only_case_escalates_after_repeated_failed_followups(tmp_path, monkeypatch):
    bot = build_bot(tmp_path, "phase4_escalate.db")
    try:
        bot.process_message("phase4_escalate", "Necesito electroválvula industrial 3/4")

        monkeypatch.setattr(
            SalesBot,
            "_run_sales_intelligence",
            lambda self, session_id, user_message: {
                "human_handoff": {"enabled": True, "reason": "catalog_gap"},
                "reply_text": "Te paso con un asesor para revisar ese caso fuera de catálogo.",
            },
        )
        reply = bot.process_message("phase4_escalate", "de bronce")
        assert "asesor" in reply.lower()
        assert bot.get_last_turn_meta("phase4_escalate")["route_source"] == "model_assisted"
        active = bot.sessions["phase4_escalate"]["active_quote"]
        assert active[0]["clarification_attempts"] >= 1
        assert active[0]["issue_type"] == "unknown_term"
    finally:
        bot.close()


def test_phase4_additive_request_preserves_pending_blocked_line(tmp_path):
    bot = build_bot(tmp_path, "phase4_additive.db")
    try:
        opened = bot.process_message("phase4_additive", "Necesito mecha")
        assert "mecha" in opened.lower()
        reply = bot.process_message("phase4_additive", "agregale teflon")
        assert "teflon" in reply.lower()
        active = bot.sessions["phase4_additive"]["active_quote"]
        assert len(active) == 2
        mecha = next(item for item in active if item.get("family") == "mecha")
        teflon = next(item for item in active if item.get("family") == "teflon")
        assert mecha["status"] == "blocked_by_missing_info"
        assert teflon["status"] == "resolved"
    finally:
        bot.close()
