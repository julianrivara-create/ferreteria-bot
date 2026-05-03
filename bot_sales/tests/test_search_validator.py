"""
Unit tests for bot_sales.services.search_validator.

No LLM calls — all tests run at commit time.

Run:
    pytest bot_sales/tests/test_search_validator.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.services.search_validator import validate_query_specs, validate_search_match


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
        self.assertTrue(_should_block("tienen martillos Stanley dorados de 500kg?"))

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

    # V4: precious color on metal hand tool (segment-based)
    def test_v4_martillo_dorado(self):
        self.assertTrue(_should_block("martillo dorado Stanley"))

    def test_v4_destornillador_rosa(self):
        self.assertTrue(_should_block("destornillador rosa philips"))

    def test_v4_alicate_turquesa(self):
        self.assertTrue(_should_block("alicate turquesa 8 pulgadas"))

    def test_v4_maza_oro(self):
        self.assertTrue(_should_block("maza de oro para demolición"))

    # V5: storage spec on hardware
    def test_v5_martillo_32gb(self):
        self.assertTrue(_should_block("martillo 32GB"))

    def test_v5_broca_1tb(self):
        self.assertTrue(_should_block("broca 1TB punta cobalto"))


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

    def test_pass_tornillo_dorado(self):
        """tornillo is NOT in V4 tool list — dorado screws are valid."""
        self.assertTrue(_should_pass("tornillo dorado para madera"))

    def test_pass_llave_dorada(self):
        """llave excluded from V4 — golden finish keys exist."""
        self.assertTrue(_should_pass("llave dorada de 13mm"))

    def test_pass_tornillo_dorado_para_martillo(self):
        """Segment check: 'dorado' is in tornillo segment, martillo is in other segment."""
        self.assertTrue(_should_pass("tornillo dorado para martillo de fibra"))

    def test_pass_alicate_mango_lila(self):
        """lila not in PRECIOUS_COLORS — plastic handles can be lilac."""
        self.assertTrue(_should_pass("alicate con mango lila ergonómico"))

    def test_pass_alicate_mango_morado(self):
        """morado not in PRECIOUS_COLORS — same reason."""
        self.assertTrue(_should_pass("alicate mango morado antideslizante"))

    def test_pass_bisagra_dorada(self):
        """bisagra not in V4 tool list — golden hinges are standard."""
        self.assertTrue(_should_pass("bisagra dorada 3 pulgadas"))

    def test_pass_tornillo_100mm(self):
        """100mm screws are common."""
        self.assertTrue(_should_pass("tornillo 100mm para deck"))

    def test_pass_plain_search(self):
        self.assertTrue(_should_pass("necesito 10 mechas 6mm para hormigon"))


class TestLevel2ShouldBlock(unittest.TestCase):
    """L2 validators — product lists that don't match spec claims."""

    def test_l2_weight_mismatch_no_500kg_in_products(self):
        """User claims 500kg hammer, products are ~1kg — must block."""
        products = [
            _product("Martillo Carpintero 500 g - Stanley"),
            _product("Martillo Galponero 1.2 kg - Bahco"),
        ]
        self.assertTrue(_l2_blocks("martillo Stanley 500kg", products))

    def test_l2_color_mismatch_dorado_not_in_products(self):
        """User claims dorado, no product has dorado — must block."""
        products = [
            _product("Martillo Carpintero Negro - Stanley"),
            _product("Martillo Galponero Mango Rojo - Bahco"),
        ]
        self.assertTrue(_l2_blocks("martillo dorado Stanley", products))

    def test_l2_weight_mismatch_tool_keyword_present(self):
        """Weight claim + tool keyword + no matching product weight → block."""
        products = [_product("Broca 8mm Cobalto - Dewalt")]
        self.assertTrue(_l2_blocks("broca de 50kg para hormigón", products))


class TestLevel2ShouldPass(unittest.TestCase):
    """L2 validators — cases that must NOT be blocked."""

    def test_l2_pass_no_spec_claim(self):
        """No weight or unusual color claimed → pass."""
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

    def test_l2_pass_color_in_product(self):
        """User claims dorado, product has 'dorado' → pass."""
        products = [_product("Bisagra Dorada 3 pulgadas - Impo")]
        self.assertTrue(_l2_passes("bisagra dorada 3 pulgadas", products))

    def test_l2_pass_empty_products_list(self):
        """No products returned → L2 passes (L1 or catalog already handled it)."""
        self.assertTrue(_l2_passes("martillo 500kg", []))

    def test_l2_pass_no_tool_keyword_with_weight(self):
        """Weight mentioned but no tool keyword (e.g. paint) → not a tool spec → pass."""
        products = [_product("Pintura Látex Blanco 20 kg - Alba")]
        self.assertTrue(_l2_passes("pintura 20kg blanca", products))


if __name__ == "__main__":
    unittest.main()
