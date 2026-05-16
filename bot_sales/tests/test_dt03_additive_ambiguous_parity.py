"""
test_dt03_additive_ambiguous_parity.py — DT-03 closure validation.

DT-03 (open since 2026-05-06) flagged that ``apply_additive`` "auto-pickea
primer match sin ofrecer opciones A/B/C", inconsistent with T1
(``product_search`` → ``resolve_quote_item`` → ambiguous render).

After DT-17 (commit 7e29d92), ``apply_additive`` resolves new items via the
same ``resolve_quote_item`` used by T1. When the resolver returns
``status="ambiguous"`` with multiple ``products``, ``apply_additive`` appends
the line as-is and ``generate_updated_quote_response`` renders the A/B/C
block via the ``ambiguous_data`` branch — the same renderer T1 hits.

These tests pin that parity so any future regression is caught.
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
    generate_quote_response,
    generate_updated_quote_response,
)


def _resolved(normalized: str, sku: str, unit_price: float = 100.0, qty: int = 1) -> Dict[str, Any]:
    return {
        "line_id": str(uuid.uuid4()),
        "status": "resolved",
        "normalized": normalized,
        "original": normalized,
        "qty": qty,
        "qty_explicit": True,
        "unit_price": unit_price,
        "subtotal": round(unit_price * qty, 2),
        "products": [{"model": normalized, "sku": sku, "price_ars": int(unit_price)}],
        "pack_note": None,
    }


def _ambiguous(normalized: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "line_id": str(uuid.uuid4()),
        "status": "ambiguous",
        "normalized": normalized,
        "original": normalized,
        "qty": 1,
        "qty_explicit": False,
        "unit_price": None,
        "subtotal": None,
        "products": products,
        "pack_note": None,
        "clarification": "¿Cuál?",
        "family": None,
    }


def _patched_additive(message: str, cart: list, new_item: Dict[str, Any]) -> list:
    with patch(
        "bot_sales.ferreteria_quote.parse_quote_items",
        return_value=[{"raw": message, "normalized": message, "qty": 1, "qty_explicit": False}],
    ):
        with patch("bot_sales.ferreteria_quote.resolve_quote_item", return_value=new_item):
            return apply_additive(message, cart, logic=None)


class TestAmbiguousAdditivePreservesOptions:
    """When resolve_quote_item returns ambiguous, apply_additive must NOT auto-pick."""

    def test_apply_additive_appends_ambiguous_item_with_all_products(self):
        amoladora_options = [
            {"model": "Amoladora Bosch GWS 7-115", "sku": "AM-BOSCH", "price_ars": 50000},
            {"model": "Amoladora Black & Decker G720", "sku": "AM-BD", "price_ars": 35000},
            {"model": "Amoladora Stanley STGS6115", "sku": "AM-STAN", "price_ars": 32000},
        ]
        cart = [_resolved("tornillo 3.5 x 25 mm", sku="TOR-DRY", unit_price=29.0, qty=1)]
        new_item = _ambiguous("amoladora", amoladora_options)

        result = _patched_additive("agregame una amoladora", cart, new_item)

        assert len(result) == 2, "ambiguous additive must append a new line, not merge"
        appended = result[1]
        assert appended["status"] == "ambiguous"
        assert len(appended["products"]) == 3, "all candidate products must be preserved"

    def test_render_exposes_all_ambiguous_options_as_letters(self):
        amoladora_options = [
            {"model": "Amoladora Bosch GWS 7-115", "sku": "AM-BOSCH", "price_ars": 50000},
            {"model": "Amoladora Black & Decker G720", "sku": "AM-BD", "price_ars": 35000},
            {"model": "Amoladora Stanley STGS6115", "sku": "AM-STAN", "price_ars": 32000},
        ]
        cart = [_resolved("tornillo 3.5 x 25 mm", sku="TOR-DRY", unit_price=29.0, qty=1)]
        new_item = _ambiguous("amoladora", amoladora_options)

        result = _patched_additive("agregame una amoladora", cart, new_item)
        rendered = generate_updated_quote_response(result)

        for letter in ("A)", "B)", "C)"):
            assert letter in rendered, f"option {letter} must be visible in additive render"
        assert "Bosch" in rendered
        assert "Black & Decker" in rendered or "Black" in rendered
        assert "Stanley" in rendered

    def test_t1_parity_same_ambiguous_item_renders_same_options(self):
        """Render produced by the additive path matches the render T1 produces
        when ``resolve_quote_item`` returns the same ambiguous item."""
        opts = [
            {"model": "Taladro Bosch GSB 13 RE", "sku": "TA-BOSCH", "price_ars": 90000},
            {"model": "Taladro Black & Decker HD400", "sku": "TA-BD", "price_ars": 60000},
        ]
        ambiguous_item = _ambiguous("taladro", opts)

        t1_render = generate_quote_response([ambiguous_item])

        cart = []
        additive_result = _patched_additive("agregame un taladro", cart, ambiguous_item)
        additive_render = generate_updated_quote_response(additive_result)

        for letter in ("A)", "B)"):
            assert letter in t1_render
            assert letter in additive_render
        for model_name in ("Bosch", "Black"):
            assert model_name in t1_render
            assert model_name in additive_render
