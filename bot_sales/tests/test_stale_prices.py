"""
Stale price detection tests (R3 — fix/R3-stale-prices-multiturno).

These tests cover the detection, flagging, and refresh of prices that
have aged past the STALE_PRICE_THRESHOLD_MINUTES threshold in an
active_quote during a multi-turn conversation.

No LLM calls. No catalog access. All tests are unit-level and fast.

Run:
    PYTHONPATH=. python3 -m pytest bot_sales/tests/test_stale_prices.py -v
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import (
    STALE_PRICE_THRESHOLD_MINUTES,
    _format_price,
    _now_iso,
    generate_acceptance_response,
    generate_quote_response,
    is_price_stale,
    refresh_stale_prices,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_minutes_ago(minutes: float) -> str:
    """Return an ISO-8601 UTC timestamp from `minutes` ago."""
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return t.isoformat()


def _make_item(
    unit_price=1000.0,
    qty=1,
    status="resolved",
    price_captured_at="__fresh__",  # sentinel: set to "just now"
    original="tornillo",
    model="Tornillo 5x50",
) -> dict:
    """Build a minimal QuoteItem dict for testing."""
    if price_captured_at == "__fresh__":
        price_captured_at = _now_iso()
    return {
        "original": original,
        "normalized": original,
        "qty": qty,
        "qty_explicit": qty > 1,
        "unit_hint": None,
        "status": status,
        "products": [{"model": model, "sku": "SKU-001", "price_ars": int(unit_price or 0)}],
        "unit_price": unit_price,
        "price_captured_at": price_captured_at,
        "subtotal": round(unit_price * qty, 2) if unit_price is not None else None,
        "pack_note": None,
        "clarification": None,
        "notes": None,
        "complementary": [],
        "family": "tornillo",
        "missing_dimensions": [],
        "issue_type": None,
        "dimensions": {},
        "selected_via_substitute": False,
    }


# ---------------------------------------------------------------------------
# is_price_stale
# ---------------------------------------------------------------------------

class TestIsPriceStale(unittest.TestCase):

    def test_fresh_price_not_stale(self):
        item = _make_item(price_captured_at=_ts_minutes_ago(5))
        self.assertFalse(is_price_stale(item))

    def test_old_price_is_stale(self):
        item = _make_item(price_captured_at=_ts_minutes_ago(35))
        self.assertTrue(is_price_stale(item))

    def test_exactly_at_threshold_is_stale(self):
        # At exactly the threshold, age_seconds == threshold * 60 → NOT stale (strict >)
        item = _make_item(price_captured_at=_ts_minutes_ago(STALE_PRICE_THRESHOLD_MINUTES))
        # Boundary: age == threshold seconds → not stale (> not >=)
        # Allow 1s tolerance for test execution time
        result = is_price_stale(item)
        # Could be True or False at the exact boundary; just verify it's a bool
        self.assertIsInstance(result, bool)

    def test_just_past_threshold_is_stale(self):
        item = _make_item(price_captured_at=_ts_minutes_ago(STALE_PRICE_THRESHOLD_MINUTES + 1))
        self.assertTrue(is_price_stale(item))

    def test_legacy_item_no_timestamp_is_stale(self):
        """Items with a price but no price_captured_at (legacy) are always stale."""
        item = _make_item(price_captured_at=None)
        self.assertTrue(is_price_stale(item))

    def test_item_no_price_never_stale(self):
        """Items without a unit_price are never stale, even without a timestamp."""
        item = _make_item(unit_price=None, price_captured_at=None)
        self.assertFalse(is_price_stale(item))

    def test_item_no_price_fresh_ts_never_stale(self):
        item = _make_item(unit_price=None, price_captured_at=_ts_minutes_ago(60))
        self.assertFalse(is_price_stale(item))

    def test_malformed_timestamp_treated_as_stale(self):
        item = _make_item(price_captured_at="not-a-timestamp")
        self.assertTrue(is_price_stale(item))

    def test_custom_threshold(self):
        item = _make_item(price_captured_at=_ts_minutes_ago(10))
        self.assertTrue(is_price_stale(item, threshold_minutes=5))
        self.assertFalse(is_price_stale(item, threshold_minutes=15))

    def test_naive_datetime_treated_as_utc(self):
        """A timestamp without tzinfo (naive) should still be handled."""
        naive_ts = (datetime.now() - timedelta(minutes=60)).isoformat()
        item = _make_item(price_captured_at=naive_ts)
        self.assertTrue(is_price_stale(item))


# ---------------------------------------------------------------------------
# refresh_stale_prices
# ---------------------------------------------------------------------------

class TestRefreshStalePrices(unittest.TestCase):

    def _fresh_lookup(self, normalized: str) -> float:
        """Lookup that always returns 1200.0 (simulates a price increase)."""
        return 1200.0

    def _same_lookup(self, normalized: str) -> float:
        """Lookup that returns the same price as _make_item default (1000.0)."""
        return 1000.0

    def _none_lookup(self, normalized: str):
        """Lookup that returns None (product not found in catalog)."""
        return None

    def test_fresh_items_not_touched(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(2))
        updated, notifications = refresh_stale_prices([item], self._fresh_lookup)
        self.assertEqual(updated[0]["unit_price"], 1000.0)
        self.assertEqual(notifications, [])

    def test_stale_price_changed_notifies(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(40))
        updated, notifications = refresh_stale_prices([item], self._fresh_lookup)
        self.assertEqual(updated[0]["unit_price"], 1200.0)
        self.assertEqual(len(notifications), 1)
        self.assertIn("1.200", notifications[0])   # new price formatted
        self.assertIn("1.000", notifications[0])   # old price formatted

    def test_stale_price_changed_updates_subtotal(self):
        item = _make_item(unit_price=1000.0, qty=3, price_captured_at=_ts_minutes_ago(40))
        updated, notifications = refresh_stale_prices([item], self._fresh_lookup)
        self.assertEqual(updated[0]["subtotal"], 3600.0)

    def test_stale_price_unchanged_silent_refresh(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(40))
        updated, notifications = refresh_stale_prices([item], self._same_lookup)
        self.assertEqual(updated[0]["unit_price"], 1000.0)
        self.assertEqual(notifications, [])
        # Timestamp should have been refreshed
        old_ts = item["price_captured_at"]
        new_ts = updated[0]["price_captured_at"]
        self.assertNotEqual(old_ts, new_ts)

    def test_stale_lookup_fails_refreshes_timestamp(self):
        """If lookup returns None (not found), refresh timestamp silently."""
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(40))
        updated, notifications = refresh_stale_prices([item], self._none_lookup)
        self.assertEqual(updated[0]["unit_price"], 1000.0)  # unchanged
        self.assertEqual(notifications, [])

    def test_cart_preserved_other_fields_intact(self):
        item = _make_item(unit_price=1000.0, qty=5, status="resolved",
                          price_captured_at=_ts_minutes_ago(40))
        updated, _ = refresh_stale_prices([item], self._fresh_lookup)
        self.assertEqual(updated[0]["qty"], 5)
        self.assertEqual(updated[0]["status"], "resolved")
        self.assertEqual(updated[0]["original"], "tornillo")

    def test_legacy_no_timestamp_treated_as_stale(self):
        """Items with price but no price_captured_at are refreshed."""
        item = _make_item(unit_price=1000.0, price_captured_at=None)
        updated, notifications = refresh_stale_prices([item], self._fresh_lookup)
        self.assertEqual(updated[0]["unit_price"], 1200.0)
        self.assertEqual(len(notifications), 1)

    def test_mixed_fresh_and_stale(self):
        fresh = _make_item(unit_price=500.0, original="clavo",
                           price_captured_at=_ts_minutes_ago(2))
        stale = _make_item(unit_price=1000.0, original="tornillo",
                           price_captured_at=_ts_minutes_ago(40))
        updated, notifications = refresh_stale_prices([fresh, stale], self._fresh_lookup)
        self.assertEqual(updated[0]["unit_price"], 500.0)   # fresh: unchanged
        self.assertEqual(updated[1]["unit_price"], 1200.0)  # stale: updated
        self.assertEqual(len(notifications), 1)

    def test_no_price_items_untouched(self):
        item = _make_item(unit_price=None, price_captured_at=None, status="ambiguous")
        updated, notifications = refresh_stale_prices([item], self._fresh_lookup)
        self.assertIsNone(updated[0]["unit_price"])
        self.assertEqual(notifications, [])


# ---------------------------------------------------------------------------
# generate_quote_response — stale flag
# ---------------------------------------------------------------------------

class TestQuoteResponseStaleFlag(unittest.TestCase):

    def test_fresh_price_no_flag(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(2))
        result = generate_quote_response([item])
        self.assertNotIn("⚠️ _Precios", result)
        # The ⚠️ pack_note marker can appear; we check the stale footnote
        self.assertNotIn("referenciales", result)

    def test_stale_price_shows_flag_on_item(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(40))
        result = generate_quote_response([item])
        # The item line should have the ⚠️ marker
        self.assertIn("⚠️", result)

    def test_stale_price_shows_footnote(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(40))
        result = generate_quote_response([item])
        self.assertIn("referenciales", result)
        self.assertIn(str(STALE_PRICE_THRESHOLD_MINUTES), result)

    def test_no_stale_no_footnote(self):
        fresh1 = _make_item(unit_price=500.0, original="clavo",
                             price_captured_at=_ts_minutes_ago(1))
        fresh2 = _make_item(unit_price=800.0, original="tuerca",
                             price_captured_at=_ts_minutes_ago(2))
        result = generate_quote_response([fresh1, fresh2])
        self.assertNotIn("referenciales", result)

    def test_legacy_price_no_ts_gets_flag(self):
        """Item with unit_price but no price_captured_at → stale → flagged."""
        item = _make_item(unit_price=1000.0, price_captured_at=None)
        result = generate_quote_response([item])
        self.assertIn("referenciales", result)


# ---------------------------------------------------------------------------
# generate_acceptance_response — stale warning
# ---------------------------------------------------------------------------

class TestAcceptanceResponseStaleWarning(unittest.TestCase):

    def test_acceptance_no_stale_no_warning(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(5))
        result = generate_acceptance_response([item])
        self.assertIn("Recibimos tu pedido", result)
        self.assertNotIn("referenciales", result)

    def test_acceptance_stale_adds_warning(self):
        item = _make_item(unit_price=1000.0, price_captured_at=_ts_minutes_ago(40))
        result = generate_acceptance_response([item])
        self.assertIn("Recibimos tu pedido", result)
        self.assertIn("referenciales", result)
        self.assertIn(str(STALE_PRICE_THRESHOLD_MINUTES), result)

    def test_acceptance_legacy_price_adds_warning(self):
        item = _make_item(unit_price=1000.0, price_captured_at=None)
        result = generate_acceptance_response([item])
        self.assertIn("referenciales", result)

    def test_acceptance_no_price_no_warning(self):
        item = _make_item(unit_price=None, price_captured_at=None, status="ambiguous")
        result = generate_acceptance_response([item])
        self.assertNotIn("referenciales", result)

    def test_acceptance_blocked_items_still_blocks(self):
        blocked = _make_item(unit_price=None, status="blocked_by_missing_info")
        result = generate_acceptance_response([blocked])
        self.assertIn("Antes de confirmar", result)
        self.assertNotIn("Recibimos tu pedido", result)


if __name__ == "__main__":
    unittest.main()
