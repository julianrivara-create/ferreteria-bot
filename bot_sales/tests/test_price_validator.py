"""
test_price_validator.py — Unit tests for R2 price validation module.

Zero LLM calls. Tests extract_prices_from_response, has_approximate_language,
and detect_hallucinated_prices in isolation.
"""
import pytest
from bot_sales.services.price_validator import (
    extract_prices_from_response,
    has_approximate_language,
    detect_hallucinated_prices,
)


class TestExtractPricesFromResponse:
    def test_extract_basic_dollar_sign(self):
        assert extract_prices_from_response("El precio es $12500") == [12500]

    def test_extract_ars_dot_format(self):
        """Argentine thousands-separator format."""
        assert extract_prices_from_response("Vale $12.500") == [12500]

    def test_extract_ars_comma_format(self):
        assert extract_prices_from_response("Cuesta $12,500") == [12500]

    def test_extract_with_space_after_dollar(self):
        assert extract_prices_from_response("Sale $ 12500") == [12500]

    def test_extract_with_currency_word_ars(self):
        assert extract_prices_from_response("El total es 12500 ARS") == [12500]

    def test_extract_with_currency_word_pesos(self):
        assert extract_prices_from_response("Son 12.500 pesos") == [12500]

    def test_extract_multiple_prices(self):
        result = extract_prices_from_response("El A cuesta $10000 y el B $15000")
        assert set(result) == {10000, 15000}

    def test_extract_range_prices(self):
        """Both values in 'entre $X y $Y' are extracted."""
        result = extract_prices_from_response("entre $10000 y $15000")
        assert set(result) == {10000, 15000}

    def test_extract_no_prices_returns_empty(self):
        assert extract_prices_from_response("No tenemos ese producto en stock") == []

    def test_extract_ignores_naked_numbers(self):
        """Bare numbers without $ or currency word are ignored."""
        assert extract_prices_from_response("Tenemos 12500 unidades disponibles") == []

    def test_extract_ignores_dimensions(self):
        """Dimensional values like 12mm should not be extracted."""
        assert extract_prices_from_response("Broca de 12mm de largo, 8mm de diámetro") == []

    def test_extract_ignores_small_values(self):
        """Values below 100 ARS are filtered as noise."""
        assert extract_prices_from_response("Solo $50 de descuento") == []

    def test_extract_deduplicates(self):
        """Same price mentioned twice appears once."""
        result = extract_prices_from_response("$12500 o bien $12.500")
        assert result == [12500]


class TestHasApproximateLanguage:
    def test_detects_alrededor_de(self):
        assert has_approximate_language("alrededor de $12000") is True

    def test_detects_aprox(self):
        assert has_approximate_language("aprox. $5000") is True

    def test_detects_aproximadamente(self):
        assert has_approximate_language("cuesta aproximadamente $8000") is True

    def test_detects_mas_o_menos(self):
        assert has_approximate_language("más o menos $6000") is True

    def test_no_approx_language(self):
        assert has_approximate_language("El precio es $12500") is False

    def test_no_approx_without_dollar(self):
        """Phrase without $ after it is not a match."""
        assert has_approximate_language("más o menos un mes de espera") is False


class TestDetectHallucinatedPrices:
    def test_exact_match_not_hallucinated(self):
        assert detect_hallucinated_prices("Cuesta $12500", [12500]) == []

    def test_within_5_percent_not_hallucinated(self):
        """$12500 vs catalog $12800 → 2.3% difference → not hallucinated."""
        assert detect_hallucinated_prices("Cuesta $12500", [12800]) == []

    def test_outside_5_percent_is_hallucinated(self):
        """$12500 vs catalog $14000 → 10.7% difference → hallucinated."""
        result = detect_hallucinated_prices("Cuesta $12500", [14000])
        assert result == [12500]

    def test_invented_price_is_hallucinated(self):
        """Price completely absent from catalog."""
        result = detect_hallucinated_prices("Vale $99000", [12500, 15000, 8000])
        assert result == [99000]

    def test_no_hallucination_when_no_prices_in_response(self):
        assert detect_hallucinated_prices("No hay stock de ese producto", [12500]) == []

    def test_empty_catalog_returns_empty(self):
        """When catalog is empty, cannot judge — return []."""
        assert detect_hallucinated_prices("El precio es $12500", []) == []

    def test_multiple_prices_one_hallucinated(self):
        """Mixed response: one valid, one hallucinated."""
        result = detect_hallucinated_prices(
            "El taladro $12500 y el martillo $99999", [12500, 8000]
        )
        assert result == [99999]

    def test_tolerance_boundary_exactly_5_percent(self):
        """Price exactly at 5% tolerance is NOT flagged."""
        # catalog=10000, price=10500 → exactly 5.0% → should pass
        assert detect_hallucinated_prices("$10500", [10000]) == []

    def test_tolerance_boundary_just_over_5_percent(self):
        """Price just over 5% tolerance IS flagged."""
        # catalog=10000, price=10501 → 5.01% → hallucinated
        result = detect_hallucinated_prices("$10501", [10000])
        assert result == [10501]
