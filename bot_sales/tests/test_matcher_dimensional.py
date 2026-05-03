"""
test_matcher_dimensional.py
===========================
Unit tests for dimensional scoring fixes (Fix A + Fix C + Fix D).

Fix A — Cross-unit penalty in _score_dimension_alignment:
  mm vs fraction (e.g. "8mm" vs "1/4") now penalises -4.0 per dimension,
  not -1.25.  This is critical to prevent "Acople 1 1/4" from beating
  "Broca 8mm" when searching for "mecha 8mm".

Fix C — Plural normalisation in _BASE_SPELLING_VARIANTS:
  "llaves" → "llave", "francesas" → "francesa".
  Prevents "llaves francesas?" from matching "Llaves Combinadas Ratchet".

Fix D — Question-mark stripping in parse_quote_items:
  Strips "?", "¿", "!" from item tokens so "llaves francesas?" is treated
  identically to "llaves francesas".
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_language import normalize_basic
from bot_sales.ferreteria_quote import (
    _score_dimension_alignment,
    _score_product,
    _SCORE_HIGH,
    parse_quote_items,
)

# ---------------------------------------------------------------------------
# Helpers — minimal mock product dicts (no DB required)
# ---------------------------------------------------------------------------

def _make_product(name: str, category: str = "Mechas y Brocas", sku: str = "") -> dict:
    return {"model": "", "name": name, "sku": sku, "category": category}


ACOPLE_1_14 = _make_product(
    "Acople para Broca 1 1/4 Rosca Gas 1/2 - Aliafor",
    category="Mechas y Brocas",
)
BROCA_8MM = _make_product(
    "Broca Acero Rapido 8 mm - Ezeta",
    category="Mechas y Brocas",
)
BROCA_6MM = _make_product(
    "Broca Acero Rapido 6 mm",
    category="Mechas y Brocas",
)
ADAPTADOR_LLAVE = _make_product(
    "Adaptador 3/8 para Llaves Combinadas Ratchet - Bahco",
    category="Herramientas Manuales",
)
LLAVE_FRANCESA = _make_product(
    "Llave Francesa Ajustable 10 pulg - Stanley",
    category="Herramientas Manuales",
)
TORNILLO_M6 = _make_product(
    "Tornillo M6 x 20 mm - Acero",
    category="Tornillos y Fijaciones",
)
TORNILLO_M8 = _make_product(
    "Tornillo M8 x 25 mm - Acero",
    category="Tornillos y Fijaciones",
)


# ---------------------------------------------------------------------------
# Fix A — Cross-unit penalty
# ---------------------------------------------------------------------------

class TestCrossUnitPenalty(unittest.TestCase):

    def test_acople_fraction_vs_mm_request_penalised_hard(self):
        """Acople 1 1/4 must score WELL below SCORE_HIGH for 'mecha 8mm' dims."""
        dims = {"diameter": "8mm", "size": "8mm"}
        score = _score_dimension_alignment(ACOPLE_1_14, dims)
        # Each of diameter + size triggers cross-unit → -4.0 each → -8.0 total
        self.assertLessEqual(score, -7.0, f"Expected <= -7.0, got {score}")

    def test_broca_8mm_exact_match_positive(self):
        """Broca 8mm must score positively when requesting 8mm."""
        dims = {"diameter": "8mm", "size": "8mm"}
        score = _score_dimension_alignment(BROCA_8MM, dims)
        self.assertGreater(score, 0.0, f"Expected > 0.0, got {score}")

    def test_same_unit_mismatch_soft_penalty(self):
        """6mm product vs 8mm request: same-unit mismatch, soft penalty only."""
        dims = {"diameter": "8mm", "size": "8mm"}
        score = _score_dimension_alignment(BROCA_6MM, dims)
        # Should be -1.25 per dim, not -4.0 (not a cross-unit mismatch)
        self.assertGreater(score, -3.0, f"Expected > -3.0, got {score}")
        self.assertLess(score, 0.0, f"Expected negative, got {score}")

    def test_no_dimensions_requested_zero_score(self):
        """No requested dims → alignment score must be 0.0 (no info)."""
        score = _score_dimension_alignment(BROCA_8MM, {})
        self.assertEqual(score, 0.0)

    def test_full_score_acople_below_score_high_for_mecha_8mm(self):
        """Full product score for acople vs 'mecha 8mm' must be below SCORE_HIGH."""
        families = ["mecha"]
        dims = {"diameter": "8mm", "size": "8mm"}
        score = _score_product(ACOPLE_1_14, "mecha 8mm", families, dims)
        self.assertLess(
            score, _SCORE_HIGH,
            f"Acople 1 1/4 scored {score} >= SCORE_HIGH ({_SCORE_HIGH}) — "
            "would be returned as a match for 'mecha 8mm'",
        )

    def test_full_score_broca_8mm_vs_mecha_8mm_beats_acople(self):
        """Broca 8mm must outrank Acople 1 1/4 for 'mecha 8mm' query."""
        families = ["mecha"]
        dims = {"diameter": "8mm", "size": "8mm"}
        score_acople = _score_product(ACOPLE_1_14, "mecha 8mm", families, dims)
        score_broca = _score_product(BROCA_8MM, "mecha 8mm", families, dims)
        self.assertGreater(
            score_broca, score_acople,
            f"Broca8mm score {score_broca} should beat Acople score {score_acople}",
        )

    def test_full_score_broca_no_dims_not_penalised(self):
        """Searching 'broca' without dims must still give brocas a positive score (regression)."""
        score = _score_product(BROCA_6MM, "broca", ["mecha"])
        self.assertGreater(score, 0.0, f"Broca without dims scored {score}, expected > 0")


# ---------------------------------------------------------------------------
# Fix C — Plural normalisation
# ---------------------------------------------------------------------------

class TestPluralNormalisation(unittest.TestCase):

    def test_llaves_normalised_to_llave(self):
        self.assertEqual(normalize_basic("llaves"), "llave")

    def test_francesas_normalised_to_francesa(self):
        self.assertEqual(normalize_basic("francesas"), "francesa")

    def test_mechas_already_normalised(self):
        self.assertEqual(normalize_basic("mechas"), "mecha")

    def test_phrase_llaves_francesas(self):
        result = normalize_basic("llaves francesas")
        self.assertIn("llave", result)
        self.assertIn("francesa", result)
        self.assertNotIn("llaves", result)
        self.assertNotIn("francesas", result)


# ---------------------------------------------------------------------------
# Fix D — Question-mark / punctuation stripping in parser
# ---------------------------------------------------------------------------

class TestQuestionMarkStripping(unittest.TestCase):

    def test_question_mark_stripped_from_token(self):
        """'llaves francesas?' must parse to the same token as 'llaves francesas'."""
        items_with_q = parse_quote_items("llaves francesas?")
        items_without_q = parse_quote_items("llaves francesas")
        self.assertEqual(len(items_with_q), 1)
        self.assertEqual(len(items_without_q), 1)
        # Normalised item text should be equal
        self.assertEqual(items_with_q[0]["normalized"], items_without_q[0]["normalized"])

    def test_inverted_question_mark_stripped(self):
        """'¿tienen llaves francesas?' must parse without punctuation."""
        items = parse_quote_items("¿tienen llaves francesas?")
        self.assertTrue(len(items) >= 1)
        raw = items[-1]["raw"]
        self.assertNotIn("?", raw)
        self.assertNotIn("¿", raw)

    def test_exclamation_stripped(self):
        """Trailing '!' must be stripped from item tokens."""
        items = parse_quote_items("mechas 8mm!")
        self.assertEqual(len(items), 1)
        self.assertNotIn("!", items[0]["raw"])


# ---------------------------------------------------------------------------
# Fix C+D combined — C06 regression prevention
# ---------------------------------------------------------------------------

class TestLlaveFrancesaIntegration(unittest.TestCase):

    def test_adaptador_llave_does_not_beat_llave_francesa_for_llave_request(self):
        """Adaptador para Llaves must score lower than Llave Francesa for 'llave francesa'."""
        score_adaptador = _score_product(ADAPTADOR_LLAVE, "llave francesa", ["llave"])
        score_francesa = _score_product(LLAVE_FRANCESA, "llave francesa", ["llave"])
        self.assertGreater(
            score_francesa, score_adaptador,
            f"Llave Francesa ({score_francesa}) should beat Adaptador ({score_adaptador})",
        )

    def test_query_with_plural_normalises_same_as_singular(self):
        """'llaves francesas' after normalisation matches same products as 'llave francesa'."""
        normalized_plural = normalize_basic("llaves francesas")
        normalized_singular = normalize_basic("llave francesa")
        self.assertEqual(normalized_plural, normalized_singular)


if __name__ == "__main__":
    unittest.main()
