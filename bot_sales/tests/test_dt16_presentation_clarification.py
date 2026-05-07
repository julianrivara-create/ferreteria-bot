"""
DT-16: qty clarification when a presentation/container word is detected.

Bug: "una caja de tornillos para drywall" → qty=1 ($29), deceiving the client
     who expected a box of N screws.  The catalog has no pack/presentation column
     so the bot cannot know N; it must ask instead of quoting blindly.

Fix:
  ferreteria_quote.py:
  - _PRESENTATION_BLOCK_WORDS constant (caja/cajas/rollo/rollos/lata/latas/bolsa/bolsas)
  - resolve_quote_item: guard fires when unit_hint ∈ _PRESENTATION_BLOCK_WORDS
    → status=blocked_by_missing_info, issue_type=qty_presentation
  - apply_clarification: when issue_type==qty_presentation, extract qty from
    client answer via _extract_qty_from_phrase and clear unit_hint before
    re-resolution so the guard does not re-trigger.

Run:
    pytest bot_sales/tests/test_dt16_presentation_clarification.py -v
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import bot_sales.ferreteria_quote as fq

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_KNOWLEDGE = {
    "language_patterns": {
        "regional_terms": {"drywall": "durlock"},
    }
}

_TORNILLO_PRODUCT = {
    "sku": "T-DRY-001",
    "model": "Tornillo Durlock 3.5x25mm",
    "name": "Tornillo Durlock 3.5x25mm",
    "category": "Bulonería",
    "price_ars": 29,
    "stock_qty": 500,
}

_CABLE_PRODUCT = {
    "sku": "CAB-001",
    "model": "Cable unipolar 2.5mm obra",
    "name": "Cable unipolar 2.5mm obra",
    "category": "Electricidad",
    "price_ars": 150,
    "stock_qty": 100,
}


def _make_logic(product: Dict[str, Any] = _TORNILLO_PRODUCT) -> MagicMock:
    logic = MagicMock()
    logic.buscar_stock.return_value = {"status": "found", "products": [product]}
    return logic


def _parsed(raw: str, normalized: str, qty: int, qty_explicit: bool, unit_hint) -> Dict[str, Any]:
    return {
        "raw": raw,
        "normalized": normalized,
        "qty": qty,
        "qty_explicit": qty_explicit,
        "unit_hint": unit_hint,
        "line_id": uuid.uuid4().hex[:8],
    }


def _blocked_item(
    unit_hint: str = "caja",
    normalized: str = "tornillos durlock",
    qty: int = 1,
) -> Dict[str, Any]:
    """Pre-built blocked_by_missing_info item as resolve_quote_item produces for DT-16."""
    lid = uuid.uuid4().hex[:8]
    return {
        "line_id": lid,
        "original": f"una {unit_hint} de {normalized}",
        "normalized": normalized,
        "qty": qty,
        "qty_explicit": True,
        "unit_hint": unit_hint,
        "status": "blocked_by_missing_info",
        "products": [],
        "unit_price": None,
        "subtotal": None,
        "pack_note": None,
        "clarification": "¿Cuántas unidades necesitás?",
        "notes": "Presentación detectada sin cantidad de unidades explícita.",
        "complementary": [],
        "family": "tornillo",
        "missing_dimensions": [],
        "issue_type": "qty_presentation",
        "dimensions": {"use": "durlock"},
        "selected_via_substitute": False,
    }


# ---------------------------------------------------------------------------
# a) "una caja de tornillos" → blocked with qty_presentation
# ---------------------------------------------------------------------------

class TestCajaBlocksQtyPresentation:

    def test_status_is_blocked(self):
        parsed = _parsed(
            raw="una caja de tornillos para drywall",
            normalized="tornillos para drywall",
            qty=1,
            qty_explicit=True,
            unit_hint="caja",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["status"] == "blocked_by_missing_info"

    def test_issue_type_is_qty_presentation(self):
        parsed = _parsed(
            raw="una caja de tornillos para drywall",
            normalized="tornillos para drywall",
            qty=1,
            qty_explicit=True,
            unit_hint="caja",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["issue_type"] == "qty_presentation"

    def test_clarification_asks_for_units(self):
        parsed = _parsed(
            raw="una caja de tornillos para drywall",
            normalized="tornillos para drywall",
            qty=1,
            qty_explicit=True,
            unit_hint="caja",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item.get("clarification") == "¿Cuántas unidades necesitás?"

    def test_cajas_plural_also_blocks(self):
        parsed = _parsed(
            raw="3 cajas de tornillos para drywall",
            normalized="tornillos para drywall",
            qty=3,
            qty_explicit=True,
            unit_hint="cajas",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["issue_type"] == "qty_presentation"


# ---------------------------------------------------------------------------
# b) "2 rollos de cinta" → blocked igual
# ---------------------------------------------------------------------------

class TestRollosBlocksQtyPresentation:

    def test_rollo_blocks(self):
        parsed = _parsed(
            raw="un rollo de cinta teflon",
            normalized="cinta teflon",
            qty=1,
            qty_explicit=True,
            unit_hint="rollo",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["status"] == "blocked_by_missing_info"
        assert item["issue_type"] == "qty_presentation"

    def test_rollos_plural_blocks(self):
        parsed = _parsed(
            raw="2 rollos de cinta",
            normalized="cinta",
            qty=2,
            qty_explicit=True,
            unit_hint="rollos",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["issue_type"] == "qty_presentation"

    def test_lata_blocks(self):
        parsed = _parsed(
            raw="una lata de pintura",
            normalized="pintura",
            qty=1,
            qty_explicit=True,
            unit_hint="lata",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["issue_type"] == "qty_presentation"

    def test_bolsa_blocks(self):
        parsed = _parsed(
            raw="una bolsa de tarugos",
            normalized="tarugos",
            qty=1,
            qty_explicit=True,
            unit_hint="bolsa",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["issue_type"] == "qty_presentation"


# ---------------------------------------------------------------------------
# c) "5 tornillos para drywall" → explicit qty, no unit_hint → NOT blocked by DT-16
# ---------------------------------------------------------------------------

class TestExplicitQtyNoBlock:

    def test_explicit_qty_resolves(self):
        parsed = _parsed(
            raw="5 tornillos para drywall",
            normalized="tornillos para drywall",
            qty=5,
            qty_explicit=True,
            unit_hint=None,
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item.get("issue_type") != "qty_presentation"
        assert item["status"] == "resolved"
        assert item["qty"] == 5

    def test_subtotal_correct_for_five(self):
        parsed = _parsed(
            raw="5 tornillos para drywall",
            normalized="tornillos para drywall",
            qty=5,
            qty_explicit=True,
            unit_hint=None,
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item["subtotal"] == pytest.approx(5 * 29.0)


# ---------------------------------------------------------------------------
# d) "un metro de cable" → unit_hint="metro" NOT in block list → no DT-16 block
# ---------------------------------------------------------------------------

class TestMetroNoBlock:

    def test_metro_does_not_trigger_qty_presentation(self):
        # "metro" is a valid measure unit — the guard must not fire.
        # Cable may still be blocked for other reasons (missing size/use),
        # but issue_type must NOT be qty_presentation.
        parsed = _parsed(
            raw="un metro de cable",
            normalized="cable",
            qty=1,
            qty_explicit=True,
            unit_hint="metro",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(product=_CABLE_PRODUCT), knowledge=_KNOWLEDGE)
        assert item.get("issue_type") != "qty_presentation"

    def test_kg_does_not_trigger_qty_presentation(self):
        parsed = _parsed(
            raw="2 kg de tornillos",
            normalized="tornillos",
            qty=2,
            qty_explicit=True,
            unit_hint="kg",
        )
        item = fq.resolve_quote_item(parsed, _make_logic(), knowledge=_KNOWLEDGE)
        assert item.get("issue_type") != "qty_presentation"


# ---------------------------------------------------------------------------
# e) Client answers "100" after qty_presentation block → cart resolved with qty=100
# ---------------------------------------------------------------------------

class TestClarificationWithNumberResolves:

    def test_answer_100_sets_qty_and_resolves(self):
        blocked = _blocked_item(unit_hint="caja", normalized="tornillos durlock")
        updated_cart = fq.apply_clarification(
            "100", [blocked], _make_logic(), knowledge=_KNOWLEDGE
        )
        assert len(updated_cart) == 1
        item = updated_cart[0]
        assert item["status"] == "resolved", f"status={item['status']} clarif={item.get('clarification')}"
        assert item["qty"] == 100
        assert item["subtotal"] == pytest.approx(100 * 29.0)

    def test_answer_sets_qty_explicit(self):
        blocked = _blocked_item(unit_hint="caja", normalized="tornillos durlock")
        updated_cart = fq.apply_clarification(
            "50", [blocked], _make_logic(), knowledge=_KNOWLEDGE
        )
        item = updated_cart[0]
        assert item["qty_explicit"] is True

    def test_answer_clears_unit_hint_in_resolved_item(self):
        blocked = _blocked_item(unit_hint="caja", normalized="tornillos durlock")
        updated_cart = fq.apply_clarification(
            "10", [blocked], _make_logic(), knowledge=_KNOWLEDGE
        )
        item = updated_cart[0]
        # unit_hint must be cleared so re-resolution doesn't re-trigger the guard
        assert item.get("unit_hint") is None

    def test_non_numeric_answer_does_not_resolve(self):
        """If the client doesn't provide a number, the item stays blocked."""
        blocked = _blocked_item(unit_hint="caja", normalized="tornillos durlock")
        updated_cart = fq.apply_clarification(
            "necesito muchos", [blocked], _make_logic(), knowledge=_KNOWLEDGE
        )
        item = updated_cart[0]
        # Without a parseable qty, re-resolution uses qty=1 and unit_hint is preserved
        # → guard fires again → still blocked_by_missing_info
        assert item["status"] == "blocked_by_missing_info"
