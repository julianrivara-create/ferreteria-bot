from __future__ import annotations

from pathlib import Path

import yaml

from bot_sales.persistence.quote_store import QuoteStore
from bot_sales.services.quote_automation_service import QuoteAutomationError, QuoteAutomationService


ROOT = Path(__file__).resolve().parents[1]


def _tenant_profile() -> dict:
    return yaml.safe_load((ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8"))


def main() -> int:
    profile = _tenant_profile()
    db_path = str(ROOT / "data" / "ferreteria.db")
    store = QuoteStore(db_path, tenant_id="ferreteria")
    service = QuoteAutomationService(store, tenant_id="ferreteria", tenant_profile=profile)
    try:
        quotes = service.list_eligible_quotes(limit=100)
        sent = 0
        failed = 0
        for quote in quotes:
            try:
                service.send_quote_ready_followup(quote["id"], actor="phase5_runner")
                sent += 1
            except QuoteAutomationError:
                failed += 1
        print(f"eligible={len(quotes)} sent={sent} failed={failed}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
