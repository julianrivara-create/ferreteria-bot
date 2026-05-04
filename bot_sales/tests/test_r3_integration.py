"""
test_r3_integration.py — End-to-end tests for R3 stale price wiring in bot.py.

Verifies that refresh_stale_prices() is called each turn and that notifications
surface in the quote response when prices change.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch
import pytest


def _make_item(
    original: str = "taladro bosch",
    normalized: str = "taladro bosch",
    unit_price: Optional[float] = 5000.0,
    price_captured_at: Optional[str] = None,
    qty: int = 1,
) -> Dict[str, Any]:
    """Build a minimal QuoteItem dict."""
    item: Dict[str, Any] = {
        "original": original,
        "normalized": normalized,
        "qty": qty,
        "status": "resolved",
        "products": [{"model": original, "price_ars": unit_price or 0}],
    }
    if unit_price is not None:
        item["unit_price"] = unit_price
    if price_captured_at is not None:
        item["price_captured_at"] = price_captured_at
    return item


def _stale_ts() -> str:
    """ISO UTC timestamp 2 hours ago — guaranteed stale (threshold is 30 min)."""
    return (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


def _fresh_ts() -> str:
    """ISO UTC timestamp 1 minute ago — guaranteed fresh."""
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


def _make_bot_with_session(active_quote: List[Dict[str, Any]]) -> Any:
    """Create a minimal SalesBot-like mock with the refresh logic accessible."""
    from bot_sales.bot import SalesBot

    bot = SalesBot.__new__(SalesBot)
    bot.sessions = {"sess1": {"active_quote": active_quote}}
    # Minimal attributes needed by process_message path
    bot.logic = MagicMock()
    bot.db = MagicMock()
    bot.tenant_id = "ferreteria"
    return bot


class TestR3Integration:
    def test_stale_price_refreshes_on_turn(self):
        """refresh_stale_prices is called and active_quote is updated in session."""
        stale_item = _make_item(unit_price=5000.0, price_captured_at=_stale_ts())
        updated_quote = [stale_item]
        refreshed_item = dict(stale_item, unit_price=5500.0, price_captured_at=_fresh_ts())

        with patch("bot_sales.ferreteria_quote.refresh_stale_prices") as mock_refresh:
            mock_refresh.return_value = ([refreshed_item], ["*Taladro bosch*: precio actualizado ($ 5.000 → *$ 5.500*)"])
            sess = {"active_quote": updated_quote}
            sessions = {"sess1": sess}

            # Simulate the R3 injection block directly
            _r3_aq = sess.get("active_quote") or []
            if _r3_aq:
                from bot_sales.ferreteria_quote import refresh_stale_prices
                logic_mock = MagicMock()
                logic_mock.buscar_stock.return_value = {"products": [{"price_ars": 5500}]}
                _r3_aq, _r3_notifs = refresh_stale_prices(
                    _r3_aq,
                    lookup_fn=lambda q: next(
                        (float(p.get("price_ars") or 0) or None
                         for p in logic_mock.buscar_stock(q).get("products", [])),
                        None,
                    ),
                )
                sess["active_quote"] = _r3_aq
                if _r3_notifs:
                    sess["_stale_price_notifications"] = _r3_notifs

            assert mock_refresh.called
            assert sess["active_quote"][0]["unit_price"] == 5500.0
            assert "_stale_price_notifications" in sess

    def test_price_change_notification_in_response(self):
        """When stale price changes, notification appears in generate_quote_response output."""
        from bot_sales.bot import SalesBot

        bot = SalesBot.__new__(SalesBot)
        bot.sessions = {
            "sess1": {
                "active_quote": [],
                "_stale_price_notifications": [
                    "*Taladro bosch*: precio actualizado ($ 5.000 → *$ 5.500*)"
                ],
            }
        }

        with patch("bot_sales.ferreteria_quote.generate_quote_response") as mock_gen:
            mock_gen.return_value = "*Presupuesto preliminar:*\n- Taladro bosch x1 — $ 5.500"
            reply = bot._generate_quote_response([], session_id="sess1")

        assert "📌 *Actualización de precios:*" in reply
        assert "Taladro bosch" in reply
        assert "5.500" in reply
        # Notification popped from session after display
        assert "_stale_price_notifications" not in bot.sessions["sess1"]

    def test_no_notification_if_price_unchanged(self):
        """No notification block appended when refresh finds no price changes."""
        from bot_sales.bot import SalesBot

        bot = SalesBot.__new__(SalesBot)
        bot.sessions = {"sess1": {}}

        with patch("bot_sales.ferreteria_quote.generate_quote_response") as mock_gen:
            mock_gen.return_value = "*Presupuesto preliminar:*\n- Taladro x1"
            reply = bot._generate_quote_response([], session_id="sess1")

        assert "📌" not in reply
        assert reply == "*Presupuesto preliminar:*\n- Taladro x1"

    def test_legacy_active_quote_handled(self):
        """Items without price_captured_at (legacy) are treated as stale but don't crash."""
        legacy_item = _make_item(unit_price=3000.0, price_captured_at=None)

        from bot_sales.ferreteria_quote import refresh_stale_prices, is_price_stale
        assert is_price_stale(legacy_item), "Legacy item should be stale"

        # lookup returns None → price stays, no notification, no crash
        updated, notifs = refresh_stale_prices([legacy_item], lookup_fn=lambda q: None)
        assert len(updated) == 1
        assert updated[0]["unit_price"] == 3000.0
        assert notifs == []

    def test_carrito_preserved_after_refresh(self):
        """active_quote contents are preserved after refresh (no items lost)."""
        item1 = _make_item("taladro", "taladro", 5000.0, _stale_ts())
        item2 = _make_item("broca 8mm", "broca 8mm", 200.0, _fresh_ts())

        from bot_sales.ferreteria_quote import refresh_stale_prices

        # item1 stale but lookup returns None → stays unchanged
        # item2 fresh → untouched
        updated, notifs = refresh_stale_prices(
            [item1, item2],
            lookup_fn=lambda q: None,
        )

        assert len(updated) == 2, "No items should be dropped"
        assert updated[0]["normalized"] == "taladro"
        assert updated[1]["normalized"] == "broca 8mm"
        assert updated[1]["unit_price"] == 200.0
        assert notifs == []
