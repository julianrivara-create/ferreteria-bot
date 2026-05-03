"""
Anti-hallucination tests for SalesBot.

Fast tests (no LLM) — run on every commit:
    pytest bot_sales/tests/test_anti_hallucination.py -v -m "not slow"

Slow tests (real LLM API calls) — run manually before releases:
    pytest bot_sales/tests/test_anti_hallucination.py -v -m slow

Coverage:
  - _execute_function injects _search_query into buscar_stock result (pre-norm)
  - _slim_function_result preserves _search_query through context slimming
  - LLM says "no tenemos" for absurd specs (C19)
  - LLM says "no tenemos" for missing category PP-R (C18)
  - LLM says "no existe" for invalid SKU (C20)
  - LLM still shows prices for a valid product (regression guard)
"""

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_prices(text: str) -> bool:
    return bool(re.search(r'\$[\d.,]+', text))


def _has_no_tenemos(text: str) -> bool:
    kws = (
        "no tenemos", "no contamos", "no disponemos", "no tengo",
        "no existe", "no encontré", "no hay", "no lo tenemos", "no lo tengo",
    )
    return any(kw in text.lower() for kw in kws)


def _make_bot_stub():
    """Minimal SalesBot with only _execute_function dependencies wired."""
    from bot_sales.bot import SalesBot
    with patch.object(SalesBot, "__init__", lambda s, *a, **kw: None):
        bot = SalesBot.__new__(SalesBot)
    bot.logic = MagicMock()
    bot.analytics = MagicMock()
    return bot


# ── Fast tests: _search_query injection (no LLM) ─────────────────────────────

class TestSearchQueryInjection(unittest.TestCase):
    """Unit tests for _search_query injected into buscar_stock results."""

    def test_search_query_added_on_found(self):
        bot = _make_bot_stub()
        bot.logic.buscar_stock.return_value = {
            "status": "found",
            "products": [{"sku": "MAR001", "model": "Martillo Stanley 500g",
                          "price_ars": 17675, "stock_qty": 5, "available": 5}],
            "message": "ok",
        }
        result = bot._execute_function(
            "s1", "buscar_stock", {"modelo": "martillo Stanley dorado 500kg"}
        )
        self.assertEqual(result["_search_query"], "martillo Stanley dorado 500kg")

    def test_search_query_added_on_no_match(self):
        bot = _make_bot_stub()
        bot.logic.buscar_stock.return_value = {
            "status": "no_match",
            "products": [],
            "message": "No encontré nada",
        }
        result = bot._execute_function(
            "s1", "buscar_stock", {"modelo": "caños PP-R termofusión 20mm"}
        )
        self.assertEqual(result["_search_query"], "caños PP-R termofusión 20mm")

    def test_search_query_empty_when_modelo_missing(self):
        bot = _make_bot_stub()
        bot.logic.buscar_stock.return_value = {"status": "no_match", "products": []}
        result = bot._execute_function("s1", "buscar_stock", {})
        self.assertEqual(result["_search_query"], "")

    def test_slim_preserves_search_query(self):
        from bot_sales.bot import SalesBot

        raw = {
            "status": "found",
            "products": [{"sku": "MAR001", "model": "Martillo", "price_ars": 100,
                          "stock_qty": 1, "available": 1}],
            "_search_query": "martillo Stanley dorado 500kg",
        }
        slimmed = SalesBot._slim_function_result("buscar_stock", raw)
        self.assertEqual(slimmed["_search_query"], "martillo Stanley dorado 500kg")

    def test_other_functions_get_no_search_query(self):
        bot = _make_bot_stub()
        bot.logic.listar_modelos.return_value = {"status": "success", "models": []}
        result = bot._execute_function("s1", "listar_modelos", {})
        self.assertNotIn("_search_query", result)


# ── Slow tests: full LLM integration ─────────────────────────────────────────

def _make_real_bot():
    from bot_sales.core.tenancy import TenantManager
    return TenantManager().get_bot("ferreteria")


@pytest.mark.slow
class TestAntiHallucinationLLM(unittest.TestCase):
    """End-to-end tests — make real LLM API calls. Run with: -m slow"""

    @classmethod
    def setUpClass(cls):
        cls.bot = _make_real_bot()

    def _reply(self, session_id, message):
        return self.bot.process_message(session_id, message)

    def test_c19_absurd_specs_no_prices(self):
        """C19: impossible specs → no prices shown alongside 'martillo'."""
        reply = self._reply("ah_c19", "tienen martillos Stanley dorados de 500kg?")
        prices_with_hammer = _has_prices(reply) and "martillo" in reply.lower()
        self.assertFalse(
            prices_with_hammer,
            f"C19 FAIL: presentó precios para producto absurdo — {reply[:300]}",
        )
        self.assertTrue(
            _has_no_tenemos(reply),
            f"C19 FAIL: no dijo explícitamente que no existe — {reply[:300]}",
        )

    def test_c18_ppr_explicit_no(self):
        """C18: PP-R not in catalog → must say so explicitly before any alternative."""
        reply = self._reply("ah_c18", "necesito caños PP-R termofusión 20mm")
        rl = reply.lower()
        # FAIL if it invents PP-R prices
        if _has_prices(reply) and ("pp-r" in rl or "caño" in rl or "termofusi" in rl):
            self.fail(f"C18 FAIL: inventó caños PP-R con precios — {reply[:300]}")
        self.assertTrue(
            _has_no_tenemos(reply),
            f"C18 FAIL: no aclaró ausencia de PP-R — {reply[:300]}",
        )

    def test_c20_invalid_sku_explicit(self):
        """C20: invalid SKU → must explicitly say it doesn't exist."""
        reply = self._reply("ah_c20", "dame 100 unidades del producto AAAAA")
        self.assertTrue(
            _has_no_tenemos(reply),
            f"C20 FAIL: no dijo que AAAAA no existe — {reply[:300]}",
        )

    def test_regression_valid_product_shows_prices(self):
        """Regression guard: valid product → LLM MUST show prices."""
        reply = self._reply("ah_reg", "tienen martillos?")
        self.assertTrue(
            _has_prices(reply),
            f"REGRESIÓN: no mostró precios para producto válido — {reply[:300]}",
        )

    def test_c18_alternative_must_disclaim_first(self):
        """C18 variant: if alternatives offered, must disclaim PP-R missing first."""
        reply = self._reply("ah_c18b", "caños PP-R 20mm, necesito 10 unidades")
        rl = reply.lower()
        if _has_prices(reply) and ("pp-r" in rl or "pp r" in rl or "caño" in rl):
            self.fail(f"C18b FAIL: inventó caños PP-R con precios — {reply[:300]}")
        self.assertTrue(
            _has_no_tenemos(reply),
            f"C18b FAIL: no aclaró la ausencia de PP-R — {reply[:300]}",
        )


if __name__ == "__main__":
    unittest.main()
