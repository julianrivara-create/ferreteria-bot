"""
Anti-hallucination tests for SalesFlowManager._build_offer_options.

Regression guard for audit bug R1 (flow_manager.py:486-487):
  offer_a_price = f"USD {int(budget*0.9)}"  — price invented from user budget.

Client priority #1: the bot must NEVER invent prices. Tolerance zero.

Fast tests (no LLM) — run on every commit:
    pytest bot_sales/tests/test_flow_manager_no_hallucination.py -v
"""

import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.planning.flow_manager import SalesFlowManager


# ── Helpers ───────────────────────────────────────────────────────────────────

_PRICE_PATTERN = re.compile(r"USD\s*\d[\d.,]*|\$\s*\d[\d.,]*", re.IGNORECASE)

_NOW = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)


def _has_invented_price(text: str) -> bool:
    """Returns True if reply_text contains any price-like token."""
    return bool(_PRICE_PATTERN.search(text))


# ── Unit tests: _build_offer_options ─────────────────────────────────────────

class TestBuildOfferOptionsNoPriceHallucination(unittest.TestCase):
    """
    Direct unit tests of the static method that previously hallucinated prices.
    These tests exercise the exact path identified in the R1 audit.
    """

    def _call(self, *, budget_value: float = 0.0, variant: str = "A",
              objection_type: str | None = None) -> list:
        entities = {
            "product_family": "Herramientas",
            "model": "martillo Stanley",
            "storage": "500g",
            "condition": "disponible",
        }
        if budget_value:
            entities["budget_value"] = budget_value
        return SalesFlowManager._build_offer_options(
            entities=entities,
            variant=variant,
            objection_type=objection_type,
        )

    def test_budget_only_no_hallucinated_price(self):
        """R1 core regression: budget present → offers must have price=None."""
        offers = self._call(budget_value=50_000.0)
        self.assertEqual(len(offers), 2)
        for offer in offers:
            self.assertIsNone(
                offer.price,
                f"Hallucinated price detected: {offer.price!r} "
                f"(budget=50000 must NOT generate '{offer.price}')",
            )

    def test_no_budget_no_hallucinated_price(self):
        """Without budget the price was already None — must stay None."""
        offers = self._call(budget_value=0.0)
        for offer in offers:
            self.assertIsNone(offer.price)

    def test_large_budget_no_hallucinated_price(self):
        """High budget (100k+) triggered handoff AND hallucinated price — verify only handoff triggers."""
        offers = self._call(budget_value=150_000.0)
        for offer in offers:
            self.assertIsNone(
                offer.price,
                f"Large budget must not produce hallucinated price: {offer.price!r}",
            )

    def test_price_objection_variant_no_hallucinated_price(self):
        """PRICE_OBJECTION objection type + budget → still no invented price."""
        offers = self._call(budget_value=30_000.0, objection_type="PRICE_OBJECTION", variant="B")
        for offer in offers:
            self.assertIsNone(offer.price)

    def test_offers_still_have_product_config(self):
        """Sanity: removing price must not break product_config in offers."""
        offers = self._call(budget_value=50_000.0)
        for offer in offers:
            self.assertIn("martillo Stanley", offer.product_config)


# ── Integration tests: full process_input path ───────────────────────────────

class TestProcessInputNoPriceHallucination(unittest.TestCase):
    """
    End-to-end tests through SalesFlowManager.process_input (deterministic path,
    no model_responder). Verifies reply_text never contains invented prices.
    """

    def setUp(self):
        self.manager = SalesFlowManager()

    def _process(self, session_id: str, message: str) -> dict:
        return self.manager.process_input(session_id, message, now=_NOW)

    def test_budget_message_no_invented_usd_price(self):
        """
        R1 core regression: 'tengo $50.000' must not produce 'USD 45000' in reply.
        The old code would compute int(50000 * 0.9) = 45000.
        """
        out = self._process("r1_budget", "tengo $50.000 de presupuesto para herramientas")
        reply = out["reply_text"]
        self.assertFalse(
            _has_invented_price(reply),
            f"R1 REGRESSION: reply contains invented price — {reply[:400]}",
        )

    def test_budget_with_specific_product_no_invented_price(self):
        """Budget + product → reply must not contain prices derived from budget math."""
        out = self._process(
            "r1_budget_prod",
            "necesito un martillo Stanley, tengo hasta $30.000",
        )
        reply = out["reply_text"]
        self.assertFalse(
            _has_invented_price(reply),
            f"R1 REGRESSION: reply with budget+product contains invented price — {reply[:400]}",
        )

    def test_recommended_offers_have_no_price(self):
        """Offers in the contract must have price=None — not computed from budget."""
        out = self._process("r1_offers", "quiero una amoladora, tengo $80.000")
        offers = out.get("recommended_offer", [])
        for offer in offers:
            self.assertIsNone(
                offer.get("price"),
                f"RecommendedOffer.price must be None, got {offer.get('price')!r}",
            )

    def test_handoff_path_also_no_invented_price(self):
        """
        High-value ready-to-pay: handoff triggers AND price must not be hallucinated.
        Both conditions were true before the fix — handoff text appeared but offer prices
        could still leak into recommended_offer.
        """
        # First message: qualify with product
        self._process("r1_hv", "quiero una compresor de aire")
        # Second message: signal ready to pay + large budget
        out = self._process("r1_hv", "listo para pagar hoy, tengo $150.000")
        reply = out["reply_text"]
        offers = out.get("recommended_offer", [])

        self.assertFalse(
            _has_invented_price(reply),
            f"Handoff path: invented price in reply — {reply[:400]}",
        )
        for offer in offers:
            self.assertIsNone(
                offer.get("price"),
                f"Handoff path: invented price in offer — {offer}",
            )


if __name__ == "__main__":
    unittest.main()
