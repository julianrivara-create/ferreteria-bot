"""
test_dt17b_consolidate_same_line.py — Regression tests for DT-17b (same-line consolidation).

Bug: apply_additive built existing_norms from the cart item's normalized query phrase
(e.g. "caja de tornillo durlock") and compared it against the new item's normalized phrase
(e.g. "tornillo para durlock"). Even though both resolve to the same catalog product
(same SKU), the two query phrases differ → new_norm not in existing_norms → a NEW line
was appended instead of incrementing the existing one.

Fix (ferreteria_quote.py): after the normalized-phrase check, add a SKU-based fallback.
If the primary SKU of the new resolved item matches the primary SKU of an existing cart
item, increment that line instead of appending a new one.

Run:
    pytest bot_sales/tests/test_dt17b_consolidate_same_line.py -v
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_language import normalize_live_language
from bot_sales.ferreteria_quote import apply_additive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lang_knowledge() -> Dict[str, Any]:
    """Load the ferreteria language_patterns so normalize_live_language expands
    'drywal' → 'durlock', etc. — exactly as in production."""
    import yaml
    lp_path = (
        Path(__file__).parent.parent.parent
        / "data/tenants/ferreteria/knowledge/language_patterns.yaml"
    )
    if lp_path.exists():
        with lp_path.open() as f:
            return {"language_patterns": yaml.safe_load(f)}
    return {}


def _resolved_item(
    query: str,
    sku: str,
    model: str,
    unit_price: float,
    qty: int,
    line_id: str | None = None,
    knowledge: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a cart item that mirrors what resolve_quote_item produces for *query*."""
    lid = line_id or uuid.uuid4().hex[:8]
    normalized = normalize_live_language(query, knowledge=knowledge)
    return {
        "line_id": lid,
        "status": "resolved",
        "normalized": normalized,
        "original": query,
        "qty": qty,
        "qty_explicit": True,
        "unit_price": unit_price,
        "subtotal": round(unit_price * qty, 2),
        "products": [{"model": model, "sku": sku, "price_ars": int(unit_price)}],
        "pack_note": None,
    }


# ---------------------------------------------------------------------------
# Test 1 — same product, different query phrase → must consolidate to 1 line
# ---------------------------------------------------------------------------

class TestAdditiveSameProductConsolidates:
    """DT-17b core case: cart has qty=1 of a tornillo resolved via one phrase;
    additive uses a different phrase but resolves to the same SKU → qty=6, 1 line."""

    def test_additive_same_product_consolidates_to_single_line(self):
        knowledge = _lang_knowledge()

        # T1: user said "una caja de tornillos drywal" → cart line with qty=1
        cart = [
            _resolved_item(
                query="caja de tornillos drywal",
                sku="TOR-3525-DRY",
                model="Tornillo 3.5 x 25 mm Dry Trompeta",
                unit_price=29.0,
                qty=1,
                line_id="L1",
                knowledge=knowledge,
            )
        ]

        # T2: user says "Agregame 5 tornillos para drywal" → resolves to same SKU, qty=5
        resolved_additive = _resolved_item(
            query="tornillos para drywal",
            sku="TOR-3525-DRY",       # same SKU — same catalog product
            model="Tornillo 3.5 x 25 mm Dry Trompeta",
            unit_price=29.0,
            qty=5,
            line_id="L2",
            knowledge=knowledge,
        )

        # Confirm the query phrases normalize differently (this is the root-cause condition)
        assert cart[0]["normalized"] != resolved_additive["normalized"], (
            "Pre-condition: normalized phrases must differ to exercise the SKU-fallback path"
        )

        with patch(
            "bot_sales.ferreteria_quote.parse_quote_items",
            return_value=[{"raw": "tornillos para drywal", "qty": 5}],
        ):
            with patch(
                "bot_sales.ferreteria_quote.resolve_quote_item",
                return_value=resolved_additive,
            ):
                result = apply_additive(
                    "Agregame 5 tornillos para drywal", cart, logic=None, knowledge=knowledge
                )

        assert len(result) == 1, (
            f"Debe haber 1 línea en el carrito (mismo producto), hay {len(result)}"
        )
        assert result[0]["qty"] == 6, (
            f"qty esperado 6 (1+5), obtenido {result[0]['qty']}"
        )
        assert result[0]["subtotal"] == pytest.approx(6 * 29.0), (
            "Subtotal debe ser 6 × $29"
        )


# ---------------------------------------------------------------------------
# Test 2 — two distinct products keep separate lines
# ---------------------------------------------------------------------------

class TestAdditiveTwoDistinctProductsKeepSeparateLines:
    """When the additive resolves to a DIFFERENT SKU, a new line is appended."""

    def test_additive_two_distinct_products_keep_separate_lines(self):
        knowledge = _lang_knowledge()

        # Cart already has tornillos (SKU-A)
        cart = [
            _resolved_item(
                query="caja de tornillos drywal",
                sku="TOR-3525-DRY",
                model="Tornillo 3.5 x 25 mm Dry Trompeta",
                unit_price=29.0,
                qty=1,
                line_id="L1",
                knowledge=knowledge,
            )
        ]

        # Additive resolves to mechas (SKU-B) — different product
        resolved_mecha = _resolved_item(
            query="mecha 8mm para hormigon",
            sku="MECHA-8MM-HOR",     # different SKU
            model="Mecha Broca 8mm Hormigon",
            unit_price=45.0,
            qty=3,
            line_id="L2",
            knowledge=knowledge,
        )

        with patch(
            "bot_sales.ferreteria_quote.parse_quote_items",
            return_value=[{"raw": "mecha 8mm para hormigon", "qty": 3}],
        ):
            with patch(
                "bot_sales.ferreteria_quote.resolve_quote_item",
                return_value=resolved_mecha,
            ):
                result = apply_additive(
                    "Agregame 3 mechas 8mm para hormigon", cart, logic=None, knowledge=knowledge
                )

        assert len(result) == 2, (
            f"Deben haber 2 líneas (productos distintos), hay {len(result)}"
        )
        skus = {it["products"][0]["sku"] for it in result}
        assert "TOR-3525-DRY" in skus, "Tornillo debe seguir en el carrito"
        assert "MECHA-8MM-HOR" in skus, "Mecha debe agregarse como línea nueva"

        # Original tornillo line must be unchanged
        tornillo = next(it for it in result if it["products"][0]["sku"] == "TOR-3525-DRY")
        assert tornillo["qty"] == 1, "La línea de tornillos no debe ser modificada"
