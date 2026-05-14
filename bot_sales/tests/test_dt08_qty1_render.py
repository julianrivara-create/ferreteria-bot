"""
DT-08 — Render qty=1 redundante.

When qty=1, unit_price == subtotal, so "$Y/u → $Y" is noise. Collapse to "$Y".
For qty>1, keep the full "$Y/u → *total*" format.

Run:
    PYTHONPATH=. python3 -m pytest bot_sales/tests/test_dt08_qty1_render.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import generate_quote_response


def _make_resolved_item(model: str, unit_price: float, qty: int) -> dict:
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
        "family": "martillo",
        "missing_dimensions": [],
        "issue_type": None,
        "dimensions": {},
        "selected_via_substitute": False,
    }


class TestDT08Qty1Render(unittest.TestCase):

    def test_qty1_omits_unit_arrow_total(self):
        item = _make_resolved_item("Martillo Stanley 16oz", unit_price=8500.0, qty=1)
        result = generate_quote_response([item])
        self.assertNotIn("/u →", result)
        self.assertIn("1 × Martillo Stanley 16oz", result)
        # the single price still appears bold
        self.assertIn("8.500", result)

    def test_qty2_keeps_unit_arrow_total(self):
        item = _make_resolved_item("Martillo Stanley 16oz", unit_price=8500.0, qty=2)
        result = generate_quote_response([item])
        self.assertIn("/u →", result)
        self.assertIn("2 × Martillo Stanley 16oz", result)
        self.assertIn("8.500/u", result)
        self.assertIn("17.000", result)

    def test_qty5_keeps_full_format(self):
        item = _make_resolved_item("Tornillo 4.2 x 16 mm", unit_price=120.0, qty=5)
        result = generate_quote_response([item])
        self.assertIn("5 × Tornillo 4.2 x 16 mm", result)
        self.assertIn("120/u →", result)
        self.assertIn("600", result)


if __name__ == "__main__":
    unittest.main()
