"""
Unit tests for bot_sales.services.search_validator.

No LLM calls — all tests run at commit time.

Active validators tested: V1 (weight), V2 (drill diameter), V3 (fastener length),
V6 (wattage). V4/V5/V7/V8/V9 removed (B25) — TurnInterpreter handles those cases.

Run:
    pytest bot_sales/tests/test_search_validator.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.services.search_validator import (
    validate_query_specs,
    validate_search_match,
)


def _should_block(text: str) -> bool:
    valid, _ = validate_query_specs(text)
    return not valid


def _should_pass(text: str) -> bool:
    valid, _ = validate_query_specs(text)
    return valid


def _l2_blocks(text: str, products: list) -> bool:
    valid, _ = validate_search_match(text, products)
    return not valid


def _l2_passes(text: str, products: list) -> bool:
    valid, _ = validate_search_match(text, products)
    return valid


# ─── Fake product helpers ──────────────────────────────────────────────────────

def _product(model: str, color: str = "") -> dict:
    return {"sku": "TST001", "model": model, "name": model, "color": color,
            "price_ars": 10000, "available": 5}


class TestLevel1ShouldBlock(unittest.TestCase):
    """L1 validators — queries that MUST be blocked."""

    # V1: weight impossible for tool type
    def test_v1_martillo_500kg(self):
        self.assertTrue(_should_block("tienen martillos Stanley de 500kg?"))

    def test_v1_martillo_explicit_heavy(self):
        self.assertTrue(_should_block("martillo de 100kg"))

    def test_v1_destornillador_30kg(self):
        self.assertTrue(_should_block("destornillador 30kg philips"))

    def test_v1_broca_50kg(self):
        self.assertTrue(_should_block("broca 50kg para concreto"))

    def test_v1_alicate_20kg(self):
        self.assertTrue(_should_block("alicate de 20 kilos"))

    # V2: drill diameter impossible
    def test_v2_broca_500mm(self):
        self.assertTrue(_should_block("broca 500mm de diámetro"))

    def test_v2_mecha_200mm(self):
        self.assertTrue(_should_block("mecha 200mm madera"))

    # V3: fastener length impossible
    def test_v3_tornillo_5_metros(self):
        self.assertTrue(_should_block("tornillo de 5 metros de largo"))

    def test_v3_clavo_2000mm(self):
        self.assertTrue(_should_block("clavo 2000mm"))

    # V6: wattage impossible for electric tool family
    def test_v6_taladro_5000w(self):
        self.assertTrue(_should_block("taladro de 5000W"))

    def test_v6_amoladora_3000w(self):
        self.assertTrue(_should_block("amoladora 3000W"))

    def test_v6_lijadora_2000w(self):
        self.assertTrue(_should_block("lijadora 2000W"))

    def test_v6_sierra_circular_4000w(self):
        self.assertTrue(_should_block("sierra circular 4000W"))


class TestLevel1ShouldPass(unittest.TestCase):
    """L1 validators — legitimate queries that must NOT be blocked."""

    def test_pass_martillo_stanley_no_spec(self):
        self.assertTrue(_should_pass("martillo Stanley"))

    def test_pass_martillo_500g_grams_ok(self):
        """500g is a real hammer weight — must NOT block."""
        self.assertTrue(_should_pass("martillo 500g carpintero"))

    def test_pass_martillo_2kg_ok(self):
        """2kg is within limits for hammer."""
        self.assertTrue(_should_pass("martillo 2kg demolición"))

    def test_pass_destornillador_200g(self):
        self.assertTrue(_should_pass("destornillador philips 200g"))

    def test_pass_broca_8mm(self):
        """8mm diameter — well within limits."""
        self.assertTrue(_should_pass("broca 8mm concreto"))

    def test_pass_tornillo_100mm(self):
        """100mm screws are common."""
        self.assertTrue(_should_pass("tornillo 100mm para deck"))

    def test_pass_plain_search(self):
        self.assertTrue(_should_pass("necesito 10 mechas 6mm para hormigon"))

    # V6: legitimate wattages that must NOT be blocked
    def test_v6_pass_taladro_1500w(self):
        self.assertTrue(_should_pass("taladro 1500W percutor"))

    def test_v6_pass_amoladora_1200w(self):
        self.assertTrue(_should_pass("amoladora 1200W 4.5 pulgadas"))

    def test_v6_pass_soldadora_4000w(self):
        """Soldadoras industriales pueden llegar a 5000W — 4000W es válido."""
        self.assertTrue(_should_pass("soldadora 4000W MIG"))

    def test_v6_pass_taladro_sin_watts(self):
        """Query sin especificación de potencia — no debe bloquearse."""
        self.assertTrue(_should_pass("necesito un taladro"))

    def test_v6_pass_sierra_sola_no_circular(self):
        """'sierra' sin 'circular' no aplica el límite de sierra circular."""
        self.assertTrue(_should_pass("sierra 3000W para madera"))


class TestLevel2ShouldBlock(unittest.TestCase):
    """L2 validators — product lists that don't match spec claims."""

    def test_l2_weight_mismatch_no_500kg_in_products(self):
        """User claims 500kg hammer, products are ~1kg — must block."""
        products = [
            _product("Martillo Carpintero 500 g - Stanley"),
            _product("Martillo Galponero 1.2 kg - Bahco"),
        ]
        self.assertTrue(_l2_blocks("martillo Stanley 500kg", products))

    def test_l2_weight_mismatch_tool_keyword_present(self):
        """Weight claim + tool keyword + no matching product weight → block."""
        products = [_product("Broca 8mm Cobalto - Dewalt")]
        self.assertTrue(_l2_blocks("broca de 50kg para hormigón", products))


class TestLevel2ShouldPass(unittest.TestCase):
    """L2 validators — cases that must NOT be blocked."""

    def test_l2_pass_no_spec_claim(self):
        """No weight claimed → pass."""
        products = [_product("Martillo Stanley 16oz"), _product("Martillo Bahco")]
        self.assertTrue(_l2_passes("martillo Stanley", products))

    def test_l2_pass_weight_matches_product(self):
        """User claims 500g, product says '500 g' — within 3× → pass."""
        products = [_product("Martillo Carpintero 500 g - Stanley")]
        self.assertTrue(_l2_passes("martillo 500g carpintero", products))

    def test_l2_pass_weight_within_3x(self):
        """User claims 1kg, product says 1.5kg (within 3×) → pass."""
        products = [_product("Martillo 1.5 kg Demolición - Irimo")]
        self.assertTrue(_l2_passes("martillo 1kg demolición", products))

    def test_l2_pass_empty_products_list(self):
        """No products returned → L2 passes (L1 or catalog already handled it)."""
        self.assertTrue(_l2_passes("martillo 500kg", []))

    def test_l2_pass_no_tool_keyword_with_weight(self):
        """Weight mentioned but no tool keyword (e.g. paint) → not a tool spec → pass."""
        products = [_product("Pintura Látex Blanco 20 kg - Alba")]
        self.assertTrue(_l2_passes("pintura 20kg blanca", products))


if __name__ == "__main__":
    unittest.main()
