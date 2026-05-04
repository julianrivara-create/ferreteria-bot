"""
Tests for buscar_alternativas() safety fix.

Verifies that the blind load_stock() fallback has been removed:
- When no similar products are found, return empty/none — never dump unrelated catalog items.
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_logic(find_matches_returns=None):
    """Build a BusinessLogic instance with a mocked DB."""
    from bot_sales.core.business_logic import BusinessLogic

    db = MagicMock()
    db.find_matches.return_value = find_matches_returns or []
    db.available_for_sku.return_value = 0
    # load_stock should never be called — we track this
    db.load_stock.return_value = [
        {"sku": "ACOPLE001", "model": "Acople 3/4", "price_ars": 630000, "stock_qty": 999},
        {"sku": "ADAPT002",  "model": "Adaptador SDS",  "price_ars": 57000,  "stock_qty": 500},
        {"sku": "RANDOM003", "model": "Random XYZ",     "price_ars": 12000,  "stock_qty": 300},
    ]
    logic = BusinessLogic.__new__(BusinessLogic)
    logic.db = db
    return logic, db


class TestAlternativesSafety:
    def test_no_match_returns_none_not_catalog_dump(self):
        """When find_matches returns nothing, result must be none — not a catalog dump."""
        logic, db = _make_logic(find_matches_returns=[])
        result = logic.buscar_alternativas("alicate stanley")
        assert result["status"] == "none"
        assert result["alternatives"] == []
        db.load_stock.assert_not_called()

    def test_inexistent_product_returns_none(self):
        """An inexistent product must return none, never unrelated items."""
        logic, db = _make_logic(find_matches_returns=[])
        result = logic.buscar_alternativas("martillo XYZ inexistente marca rara")
        assert result["status"] == "none"
        assert len(result["alternatives"]) == 0
        db.load_stock.assert_not_called()

    def test_no_in_stock_returns_none(self):
        """If find_matches returns items but all are out of stock, return none."""
        items = [
            {"sku": "DEST001", "model": "Destornillador Phillips 1", "price_ars": 5000, "stock_qty": 0},
            {"sku": "DEST002", "model": "Destornillador Phillips 2", "price_ars": 6000, "stock_qty": 0},
        ]
        logic, db = _make_logic(find_matches_returns=items)
        db.available_for_sku.return_value = 0  # all out of stock
        result = logic.buscar_alternativas("destornillador philips")
        assert result["status"] == "none"
        assert result["alternatives"] == []
        db.load_stock.assert_not_called()

    def test_with_real_match_returns_found(self):
        """Sanity: when find_matches returns in-stock items, return them."""
        items = [
            {"sku": "DEST003", "model": "Destornillador Phillips 3", "price_ars": 5500, "stock_qty": 10},
        ]
        logic, db = _make_logic(find_matches_returns=items)
        db.available_for_sku.return_value = 10

        result = logic.buscar_alternativas("destornillador philips")
        assert result["status"] == "found"
        assert len(result["alternatives"]) >= 1
        assert result["alternatives"][0]["sku"] == "DEST003"
        db.load_stock.assert_not_called()

    def test_returned_alternatives_are_subset_of_find_matches(self):
        """Alternatives must only contain items from find_matches, never from load_stock."""
        items = [
            {"sku": "MART001", "model": "Martillo 300g", "price_ars": 8000, "stock_qty": 5},
            {"sku": "MART002", "model": "Martillo 500g", "price_ars": 12000, "stock_qty": 3},
        ]
        logic, db = _make_logic(find_matches_returns=items)
        db.available_for_sku.side_effect = lambda sku: 5 if sku == "MART001" else 3

        result = logic.buscar_alternativas("martillo")
        skus = {a["sku"] for a in result["alternatives"]}
        assert skus.issubset({"MART001", "MART002"})
        assert "ACOPLE001" not in skus
        assert "ADAPT002" not in skus
        db.load_stock.assert_not_called()
