"""
DT-12 regression — "drywall" regional term mapped to "durlock".

Guards the fix in data/tenants/ferreteria/knowledge/language_patterns.yaml
that adds "drywall: durlock" to regional_terms so that item strings like
"tornillos para drywall" are normalized before extract_dimensions runs,
preventing the BLOCKED_TERMS guard from firing with "¿chapa, madera o durlock?".
"""
import unittest
from unittest.mock import MagicMock
from bot_sales.ferreteria_language import normalize_live_language
import bot_sales.ferreteria_quote as fq

_KNOWLEDGE = {
    "language_patterns": {
        "regional_terms": {"drywall": "durlock"},
    }
}

_TORNILLO_DURLOCK_PRODUCT = {
    "sku": "T-DRY-001",
    "name": "Tornillo Autoperforante para Durlock 3.5x25mm x100",
    "category": "Bulonería",
    "unit_price": 1500.0,
    "stock_qty": 50,
    "brand": "",
}


class TestDT12DrywallSynonym(unittest.TestCase):

    def test_drywall_normalized_to_durlock(self):
        result = normalize_live_language("tornillos para drywall", _KNOWLEDGE)
        self.assertIn("durlock", result, f"Expected 'durlock' in '{result}'")
        self.assertNotIn("drywall", result, f"'drywall' should be replaced in '{result}'")

    def test_drywall_normalization_preserves_rest_of_string(self):
        result = normalize_live_language("tornillos para drywall", _KNOWLEDGE)
        self.assertIn("tornillo", result)

    def test_without_knowledge_drywall_not_normalized(self):
        result = normalize_live_language("tornillos para drywall", None)
        self.assertIn("drywall", result, "Without knowledge, 'drywall' should remain unchanged")


class TestDT12ResolveNotBlocked(unittest.TestCase):
    """resolve_quote_item must NOT return blocked_by_missing_info for 'tornillos para drywall'
    when knowledge includes the drywall→durlock regional_term."""

    def _make_logic(self):
        logic = MagicMock()
        logic.buscar_stock.return_value = {
            "status": "found",
            "products": [_TORNILLO_DURLOCK_PRODUCT],
        }
        return logic

    def test_tornillos_drywall_not_blocked(self):
        parsed = {
            "raw": "1 caja de tornillos para drywall",
            "normalized": "tornillos para drywall",
            "qty": 1,
            "qty_explicit": True,
            "unit_hint": "caja",
            "line_id": "dt12test01",
        }
        item = fq.resolve_quote_item(parsed, self._make_logic(), knowledge=_KNOWLEDGE)
        self.assertNotEqual(
            item["status"], "blocked_by_missing_info",
            f"DT-12 regression: got blocked_by_missing_info. clarification='{item.get('clarification')}'"
        )

    def test_tornillos_drywall_without_fix_is_blocked(self):
        """Confirm baseline: without the knowledge fix, 'drywall' triggers the block."""
        parsed = {
            "raw": "1 caja de tornillos para drywall",
            "normalized": "tornillos para drywall",
            "qty": 1,
            "qty_explicit": True,
            "unit_hint": "caja",
            "line_id": "dt12test02",
        }
        item = fq.resolve_quote_item(parsed, self._make_logic(), knowledge=None)
        self.assertEqual(
            item["status"], "blocked_by_missing_info",
            "Without knowledge fix, tornillos+drywall should be blocked (confirms baseline)"
        )
