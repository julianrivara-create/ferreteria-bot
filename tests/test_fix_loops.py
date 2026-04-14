from pathlib import Path
import yaml
import pytest
from bot_sales.bot import SalesBot
from bot_sales.core.database import Database

ROOT = Path(__file__).resolve().parents[1]

def build_bot(tmp_path: Path, db_name: str = "fix_loops.db") -> SalesBot:
    catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    profile = yaml.safe_load((ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8"))
    db = Database(
        db_file=str(tmp_path / db_name),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / f"{db_name}.log"),
    )
    return SalesBot(db=db, api_key="", tenant_id="ferreteria", tenant_profile=profile, sandbox_mode=True)

def test_intent_hijacking_filtered(tmp_path):
    bot = build_bot(tmp_path, "intent_filter.db")
    try:
        # 1. Start with a greeting
        bot.process_message("user123", "Hola")
        
        # 2. Ask for stock
        response = bot.process_message("user123", "Tenes stock?")
        
        # Verify no item was added to session
        active_quote = bot.sessions.get("user123", {}).get("active_quote", [])
        assert len(active_quote) == 0, f"Quote should be empty, but got items: {[it.get('original') for it in active_quote]}"
        
        # 3. Ask "Hacer un pedido"
        response2 = bot.process_message("user123", "Quiero hacer un pedido")
        active_quote2 = bot.sessions.get("user123", {}).get("active_quote", [])
        assert len(active_quote2) == 0, "Hacer un pedido should not be parsed as a product"
        
    finally:
        bot.close()

def test_disambiguation_option_selection(tmp_path):
    bot = build_bot(tmp_path, "disambiguation_select.db")
    try:
        # 1. Request an item that is known to be ambiguous or needs clarification
        # 'taladro' often has multiple entries
        response = bot.process_message("user456", "Necesito taladro")
        
        # Should be ambiguous or blocked by missing info
        active_quote = bot.sessions["user456"]["active_quote"]
        assert len(active_quote) == 1
        line_id = active_quote[0]["line_id"]
        assert active_quote[0]["status"] in {"ambiguous", "blocked_by_missing_info"}
        
        # 2. Select option A
        response_a = bot.process_message("user456", "A")
        
        # Verify it resolved
        active_quote_new = bot.sessions["user456"]["active_quote"]
        assert active_quote_new[0]["status"] == "resolved"
        assert active_quote_new[0]["line_id"] == line_id
        assert len(active_quote_new[0]["products"]) == 1
        
    finally:
        bot.close()

def test_selection_with_phrase_el_primero(tmp_path):
    bot = build_bot(tmp_path, "ordinal_select.db")
    try:
        bot.process_message("user789", "Necesito taladro")
        
        # Select "el primero"
        bot.process_message("user789", "el primero")
        
        active_quote = bot.sessions["user789"]["active_quote"]
        assert active_quote[0]["status"] == "resolved"
        
    finally:
        bot.close()
