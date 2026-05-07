"""
DT-15 — Regression: "Atención: se vende por x N" hallucinated from product name.

The catalog has no pack/presentation column. The former _detect_pack() was
running a regex on the product name and falsely matching dimensional notation
("3.5 x 25 mm") as a pack-size indicator.

All tests here are fast (no LLM, no catalog).

Run:
    PYTHONPATH=. python3 -m pytest bot_sales/tests/test_dt15_pack_note.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import generate_quote_response


def _make_resolved_item(model: str, unit_price: float = 150.0, qty: int = 1) -> dict:
    return {
        "original": model.lower(),
        "normalized": model.lower(),
        "qty": qty,
        "qty_explicit": qty > 1,
        "unit_hint": None,
        "status": "resolved",
        "products": [{"model": model, "sku": "SKU-001", "price_ars": int(unit_price)}],
        "unit_price": unit_price,
        "price_captured_at": None,
        "subtotal": round(unit_price * qty, 2),
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


class TestDT15PackNoteHallucination(unittest.TestCase):

    def test_tornillo_dimensional_name_no_pack_message(self):
        """'3.5 x 25 mm' must not produce 'se vende por x 25'."""
        item = _make_resolved_item(
            'Tornillo 3.5 x 25 mm 6 x 1" Punta Aguja Dry Trompeta - Perfecto'
        )
        result = generate_quote_response([item])
        self.assertNotIn("se vende por", result)
        self.assertNotIn("Atención", result)

    def test_tornillo_x25_no_pack_message(self):
        """Any 'x NN' dimensional pattern must not trigger a pack warning."""
        item = _make_resolved_item("Tornillo 4.2 x 16 mm Autoperforante")
        result = generate_quote_response([item])
        self.assertNotIn("se vende por", result)
        self.assertNotIn("Atención", result)

    def test_pack_note_none_subtotal_computed(self):
        """With pack_note=None, subtotal should appear in the quote line."""
        item = _make_resolved_item("Tornillo 3.5 x 25 mm", unit_price=150.0, qty=2)
        result = generate_quote_response([item])
        self.assertIn("300", result)

    def test_item_with_explicit_pack_note_still_shows(self):
        """An item that already carries a pack_note (from a future real source)
        should still render the Atención line — the display path is preserved."""
        item = _make_resolved_item("Tuerca M8", unit_price=5.0, qty=1)
        item["pack_note"] = "caja x50"
        item["subtotal"] = None
        result = generate_quote_response([item])
        self.assertIn("Atención", result)
        self.assertIn("caja x50", result)


if __name__ == "__main__":
    unittest.main()
