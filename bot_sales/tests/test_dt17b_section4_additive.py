"""
test_dt17b_section4_additive.py — Regression tests for DT-17b fix.

Bug: When TI classified a message like "Si. Agregame 5 tornillos" as
quote_modify with references_existing_quote=True, the code hit section 4
and called apply_clarification unconditionally. apply_clarification ignores
explicit qty in the text, so the cart kept qty=1.

Path:
  _try_ferreteria_intent_route:
    intent=quote_modify, _is_clarification_via_llm=True → falls to pre_route
  _try_ferreteria_pre_route:
    Section 3: looks_like_additive("Si. Agregame 5 ...") → False (^ anchor) → skip
    Section 4: _refs_existing=True, _f1_pending=[] → guard added at 4.1:
      _ADDITIVE_INLINE_RE.search(text) detects "Agregame" → apply_additive → qty=6

Fix: bot.py section 4.1 — before apply_clarification, intercept messages that
contain an additive verb anywhere in the text and route to apply_additive.
If apply_additive makes real progress (qty change or new line), return that
response. Otherwise fall through to apply_clarification as before.

Run:
    pytest bot_sales/tests/test_dt17b_section4_additive.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.bot import _ADDITIVE_INLINE_RE


# ---------------------------------------------------------------------------
# Unit tests for _ADDITIVE_INLINE_RE — the detector used in section 4.1
# ---------------------------------------------------------------------------

class TestAdditiveInlineRE:
    """Verify _ADDITIVE_INLINE_RE catches additive verbs anywhere in the text."""

    def test_detects_agregame_with_prefix(self):
        """Core DT-17b case: 'Si. Agregame 5 tornillos'."""
        m = _ADDITIVE_INLINE_RE.search("Si. Agregame 5 tornillos para drywal")
        assert m is not None
        assert m.start() > 0  # prefix exists before verb

    def test_detects_agregame_at_start(self):
        """Pure additive — start-of-string match (section 3 handles this, 4.1 is safety net)."""
        m = _ADDITIVE_INLINE_RE.search("Agregame 5 mechas 6mm")
        assert m is not None
        assert m.start() == 0

    def test_detects_tambien_dame_with_prefix(self):
        m = _ADDITIVE_INLINE_RE.search("dale. también dame una mecha 8mm")
        assert m is not None
        assert m.start() > 0

    def test_detects_sumame_with_prefix(self):
        m = _ADDITIVE_INLINE_RE.search("ok. sumame 3 tornillos")
        assert m is not None
        assert m.start() > 0

    def test_no_match_pure_acceptance(self):
        """'Si, dale' is acceptance — no additive verb."""
        assert _ADDITIVE_INLINE_RE.search("Si, dale") is None

    def test_no_match_product_search(self):
        assert _ADDITIVE_INLINE_RE.search("una caja de tornillos para drywal") is None

    def test_additive_part_extraction(self):
        """The extracted additive_part must start at the verb, not at the prefix."""
        text = "Si. Agregame 5 tornillos para drywal"
        m = _ADDITIVE_INLINE_RE.search(text)
        additive_part = text[m.start():].strip()
        assert additive_part.lower().startswith("agregame")
        assert "5" in additive_part
        assert "tornillos" in additive_part


# ---------------------------------------------------------------------------
# Integration: progress-check logic (same pattern used in section 4.1 guard)
# ---------------------------------------------------------------------------

class TestSection41ProgressCheck:
    """Verify the progress check is structurally correct for section 4.1."""

    def _has_progress(self, updated, original):
        return len(updated) != len(original) or any(
            a.get("qty") != b.get("qty") for a, b in zip(updated, original)
        )

    def test_no_progress_when_unchanged(self):
        cart = [{"qty": 1, "normalized": "tornillo"}]
        assert not self._has_progress(cart, cart)

    def test_progress_detected_on_qty_change(self):
        original = [{"qty": 1, "normalized": "tornillo"}]
        updated = [{"qty": 6, "normalized": "tornillo"}]
        assert self._has_progress(updated, original)

    def test_progress_detected_on_new_line(self):
        original = [{"qty": 1, "normalized": "tornillo"}]
        updated = [{"qty": 1, "normalized": "tornillo"}, {"qty": 5, "normalized": "mecha"}]
        assert self._has_progress(updated, original)


# ---------------------------------------------------------------------------
# Smoke: end-to-end additive flow via apply_additive (no DB, mocked resolve)
# ---------------------------------------------------------------------------

class TestSection41EndToEnd:
    """
    Simulate the section 4.1 path:
    text="Si. Agregame 5 tornillos para drywal", open_quote=[resolved_tornillo qty=1].
    After guard extracts additive_part and calls apply_additive → qty must be 6.
    """

    def test_extracted_additive_part_increments_qty(self):
        from unittest.mock import patch
        from bot_sales.ferreteria_quote import apply_additive

        # Existing resolved cart item (qty=1)
        cart = [{
            "line_id": "L1",
            "status": "resolved",
            "normalized": "tornillo 3.5 x 25 mm dry trompeta",
            "original": "tornillo 3.5 x 25 mm dry trompeta",
            "qty": 1,
            "qty_explicit": True,
            "unit_price": 29.0,
            "subtotal": 29.0,
            "products": [{"model": "Tornillo 3.5 x 25 mm Dry Trompeta", "sku": "SKU-T", "price_ars": 29}],
            "pack_note": None,
        }]

        # Simulate section 4.1 extraction
        text = "Si. Agregame 5 tornillos para drywal"
        m = _ADDITIVE_INLINE_RE.search(text)
        assert m is not None
        additive_part = text[m.start():].strip()

        # Mock resolve to return same product with qty=5
        resolved_new = {
            "line_id": "L2",
            "status": "resolved",
            "normalized": "tornillo 3.5 x 25 mm dry trompeta",
            "qty": 5,
            "unit_price": 29.0,
            "subtotal": 145.0,
            "products": [{"model": "Tornillo 3.5 x 25 mm Dry Trompeta", "sku": "SKU-T", "price_ars": 29}],
        }
        with patch("bot_sales.ferreteria_quote.parse_quote_items", return_value=[{"raw": "x", "qty": 5}]):
            with patch("bot_sales.ferreteria_quote.resolve_quote_item", return_value=resolved_new):
                result = apply_additive(additive_part, cart, logic=None)

        assert len(result) == 1, "No debe agregar línea nueva — mismo producto"
        assert result[0]["qty"] == 6, f"Esperado qty=6, obtenido {result[0]['qty']}"
        assert result[0]["subtotal"] == pytest.approx(6 * 29.0)

    def test_progress_check_passes_after_increment(self):
        """After apply_additive increments qty, the section 4.1 progress check must pass."""
        from unittest.mock import patch
        from bot_sales.ferreteria_quote import apply_additive

        cart = [{
            "line_id": "L1",
            "status": "resolved",
            "normalized": "tornillo 3.5 x 25 mm dry trompeta",
            "qty": 1,
            "unit_price": 29.0,
            "subtotal": 29.0,
        }]

        text = "Si. Agregame 5 tornillos para drywal"
        m = _ADDITIVE_INLINE_RE.search(text)
        additive_part = text[m.start():].strip()

        resolved_new = {
            "line_id": "L2",
            "status": "resolved",
            "normalized": "tornillo 3.5 x 25 mm dry trompeta",
            "qty": 5,
            "unit_price": 29.0,
            "subtotal": 145.0,
        }
        with patch("bot_sales.ferreteria_quote.parse_quote_items", return_value=[{"raw": "x", "qty": 5}]):
            with patch("bot_sales.ferreteria_quote.resolve_quote_item", return_value=resolved_new):
                updated = apply_additive(additive_part, cart, logic=None)

        has_progress = len(updated) != len(cart) or any(
            a.get("qty") != b.get("qty") for a, b in zip(updated, cart)
        )
        assert has_progress, "El progress check de section 4.1 debe detectar el cambio de qty"
