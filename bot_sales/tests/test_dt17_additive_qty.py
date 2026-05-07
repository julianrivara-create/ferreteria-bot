"""
test_dt17_additive_qty.py — Regression tests for DT-17 fix.

Bug: apply_additive silently deduplicated items when the same product already
existed in the cart, returning the cart unchanged (qty stayed at 1) instead of
incrementing. _process_compound_modify accepted the no-progress return as success.

Fix:
  - ferreteria_quote.py: apply_additive increments qty of existing line instead
    of filtering via dedup when the normalized name matches.
  - bot.py: _process_compound_modify checks for real progress (len change OR qty
    change) before marking success=True.

Run:
    pytest bot_sales/tests/test_dt17_additive_qty.py -v
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import (
    apply_additive,
    _increment_existing_line,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolved(
    normalized: str,
    unit_price: float = 29.0,
    qty: int = 1,
    line_id: str | None = None,
) -> Dict[str, Any]:
    lid = line_id or str(uuid.uuid4())
    return {
        "line_id": lid,
        "status": "resolved",
        "normalized": normalized,
        "original": normalized,
        "qty": qty,
        "qty_explicit": True,
        "unit_price": unit_price,
        "subtotal": round(unit_price * qty, 2),
        "products": [{"model": normalized, "sku": "SKU-TEST", "price_ars": int(unit_price)}],
        "pack_note": None,
    }


def _mock_additive_call(message: str, cart: list, resolved_item: Dict) -> list:
    """Run apply_additive with parse+resolve mocked to return *resolved_item*."""
    with patch("bot_sales.ferreteria_quote.parse_quote_items", return_value=[{"raw": "x", "qty": resolved_item["qty"]}]):
        with patch("bot_sales.ferreteria_quote.resolve_quote_item", return_value=resolved_item):
            return apply_additive(message, cart, logic=None)


# ---------------------------------------------------------------------------
# Unit tests for _increment_existing_line (pure helper)
# ---------------------------------------------------------------------------

class TestIncrementExistingLine:
    def test_increments_qty_and_recomputes_subtotal(self):
        line = _make_resolved("tornillo 3.5 x 25 mm", unit_price=29.0, qty=1)
        result = _increment_existing_line(line, 5)
        assert result["qty"] == 6
        assert result["subtotal"] == pytest.approx(6 * 29.0)
        assert result["qty_explicit"] is True

    def test_does_not_mutate_original(self):
        line = _make_resolved("tornillo 3.5 x 25 mm", unit_price=29.0, qty=1)
        _increment_existing_line(line, 5)
        assert line["qty"] == 1  # original untouched

    def test_skips_subtotal_when_pack_note_present(self):
        line = _make_resolved("tornillo caja x100", unit_price=290.0, qty=1)
        line["pack_note"] = "caja x100"
        result = _increment_existing_line(line, 2)
        assert result["qty"] == 3
        assert result.get("subtotal") == pytest.approx(1 * 290.0)  # unchanged

    def test_skips_subtotal_when_no_unit_price(self):
        line = _make_resolved("tornillo sin precio", unit_price=29.0, qty=1)
        line["unit_price"] = None
        line["subtotal"] = None
        result = _increment_existing_line(line, 3)
        assert result["qty"] == 4
        assert result["subtotal"] is None


# ---------------------------------------------------------------------------
# Unit tests for apply_additive (DT-17 cases)
# ---------------------------------------------------------------------------

class TestApplyAdditiveIncrements:
    """E1 — same product already in cart: qty increments instead of dedup."""

    def test_same_product_increments_qty(self):
        """E1: cart has 1×tornillo, user adds 5 → result must be qty=6."""
        cart = [_make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)]
        new_item = _make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=5)

        result = _mock_additive_call("Agregame 5 tornillos para drywal", cart, new_item)

        assert len(result) == 1, "No debe agregar línea nueva"
        assert result[0]["qty"] == 6, f"qty esperado 6, obtenido {result[0]['qty']}"
        assert result[0]["subtotal"] == pytest.approx(6 * 29.0)

    def test_same_product_subtotal_recomputed(self):
        """Subtotal de la línea existente se recalcula correctamente."""
        cart = [_make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)]
        new_item = _make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=5)

        result = _mock_additive_call("Agregame 5", cart, new_item)

        assert result[0]["subtotal"] == pytest.approx(174.0)  # 6 × $29

    def test_e6_qty_one_plus_one(self):
        """E6: 1 + add 1 → qty=2."""
        cart = [_make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)]
        new_item = _make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)

        result = _mock_additive_call("Agregame 1 tornillo", cart, new_item)

        assert result[0]["qty"] == 2
        assert result[0]["subtotal"] == pytest.approx(2 * 29.0)


class TestApplyAdditiveNewLine:
    """E2 — different product: new line is appended, existing line unchanged."""

    def test_different_product_appends_line(self):
        """E2: cart has tornillo, user adds mecha → 2 lines."""
        cart = [_make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)]
        new_item = _make_resolved("mecha 6 mm para hormigon", unit_price=45.0, qty=5)

        result = _mock_additive_call("Agregame 5 mechas 6mm para hormigon", cart, new_item)

        assert len(result) == 2, f"Esperadas 2 líneas, obtenidas {len(result)}"
        norms = [it["normalized"] for it in result]
        assert "tornillo 3.5 x 25 mm dry trompeta" in norms
        assert "mecha 6 mm para hormigon" in norms

    def test_existing_line_qty_unchanged_when_new_product(self):
        """La línea original no se modifica cuando el producto es distinto."""
        cart = [_make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)]
        new_item = _make_resolved("mecha 6 mm para hormigon", unit_price=45.0, qty=3)

        result = _mock_additive_call("Agregame 3 mechas", cart, new_item)

        tornillo = next(it for it in result if "tornillo" in it["normalized"])
        assert tornillo["qty"] == 1  # intacto


# ---------------------------------------------------------------------------
# Unit tests for the progress-check condition (_process_compound_modify fix)
# ---------------------------------------------------------------------------

class TestProgressCheckCondition:
    """Validates the exact boolean condition used in _process_compound_modify."""

    def _has_progress(self, updated: list, original: list) -> bool:
        return len(updated) != len(original) or any(
            a.get("qty") != b.get("qty") for a, b in zip(updated, original)
        )

    def test_no_progress_when_cart_unchanged(self):
        """apply_additive returning the same list must NOT be treated as success."""
        cart = [{"qty": 1, "normalized": "tornillo"}]
        unchanged = [{"qty": 1, "normalized": "tornillo"}]
        assert not self._has_progress(unchanged, cart)

    def test_progress_when_qty_changes(self):
        """Incrementing qty must be detected as progress."""
        cart = [{"qty": 1, "normalized": "tornillo"}]
        incremented = [{"qty": 6, "normalized": "tornillo"}]
        assert self._has_progress(incremented, cart)

    def test_progress_when_line_added(self):
        """Adding a new line must be detected as progress."""
        cart = [{"qty": 1, "normalized": "tornillo"}]
        with_new = [{"qty": 1, "normalized": "tornillo"}, {"qty": 5, "normalized": "mecha"}]
        assert self._has_progress(with_new, cart)

    def test_no_progress_empty_to_empty(self):
        assert not self._has_progress([], [])

    def test_after_fix_apply_additive_triggers_progress(self):
        """Integration: apply_additive + progress check — same product → progress detected."""
        cart = [_make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=1)]
        new_item = _make_resolved("tornillo 3.5 x 25 mm dry trompeta", unit_price=29.0, qty=5)

        result = _mock_additive_call("Agregame 5 tornillos", cart, new_item)

        assert self._has_progress(result, cart), (
            "El fix debe hacer que el progress-check detecte el cambio de qty"
        )
