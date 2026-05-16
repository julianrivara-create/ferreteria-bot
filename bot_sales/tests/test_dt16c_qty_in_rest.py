"""
test_dt16c_qty_in_rest.py — DT-16c regression tests.

Bug: "una caja de 50 tornillos" → bot asked "¿cuántas unidades?" because the
parser left qty=1 + unit_hint="caja", tripping the DT-16 presentation guard.

Fix: when the outer presentation word is followed by an explicit number, the
inner number is treated as the real qty and the presentation unit_hint is
dropped (so the DT-16 guard does not fire).

Scope:
  - "una caja de 50 tornillos" → qty=50, no clarification.
  - "un rollo de 100 metros de cable" → qty=100, no clarification.
  - "una caja de tornillos" (no number) → still asks qty (DT-16 intact).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import (
    _PRESENTATION_BLOCK_WORDS,
    _extract_qty_and_item,
    parse_quote_items,
)


class TestExtractQtyFromRestWithNumber:
    """Unit-level: _extract_qty_and_item should pull the number out of the rest."""

    def test_caja_with_explicit_count(self):
        qty, explicit, unit, rest = _extract_qty_and_item("una caja de 50 tornillos")
        assert qty == 50
        assert explicit is True
        assert unit is None, "presentation unit_hint must be dropped when count is explicit"
        assert rest == "tornillos"

    def test_rollo_with_metros(self):
        qty, explicit, unit, rest = _extract_qty_and_item("un rollo de 100 metros de cable")
        assert qty == 100
        assert explicit is True
        # inner unit "metros" is NOT a presentation block word — fine to keep.
        assert unit == "metros"
        assert rest == "cable"

    def test_bolsa_with_count(self):
        qty, _, unit, rest = _extract_qty_and_item("una bolsa de 50 clavos")
        assert qty == 50
        assert unit is None
        assert rest == "clavos"

    def test_lata_with_count(self):
        qty, _, unit, rest = _extract_qty_and_item("una lata de 4 litros de pintura")
        # "litros" is not in the regex unit alternation, so it lands in rest.
        # The number 4 IS extracted as qty.
        assert qty == 4
        assert unit is None

    def test_presentation_without_number_still_blocks(self):
        """DT-16 behaviour intact when no count is present."""
        qty, explicit, unit, rest = _extract_qty_and_item("una caja de tornillos")
        assert qty == 1
        assert unit == "caja"
        assert unit.lower() in _PRESENTATION_BLOCK_WORDS, (
            "unit_hint must remain a presentation word so DT-16 guard fires"
        )
        assert rest == "tornillos"


class TestParseQuoteItemsIntegration:
    """End-to-end through parse_quote_items: qty propagates onto the parsed dict."""

    def test_caja_50_tornillos_parses_qty_50(self):
        items = parse_quote_items("una caja de 50 tornillos para drywall")
        assert len(items) == 1
        assert items[0]["qty"] == 50
        assert items[0]["qty_explicit"] is True
        assert items[0]["unit_hint"] is None
        assert "tornillo" in items[0]["normalized"]

    def test_rollo_100_metros_cable_parses_qty_100(self):
        items = parse_quote_items("un rollo de 100 metros de cable")
        assert len(items) == 1
        assert items[0]["qty"] == 100
        assert items[0]["normalized"] == "cable"

    def test_caja_de_tornillos_still_triggers_presentation_path(self):
        items = parse_quote_items("una caja de tornillos")
        assert len(items) == 1
        assert items[0]["unit_hint"] == "caja"
