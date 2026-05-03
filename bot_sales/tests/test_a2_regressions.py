"""
test_a2_regressions.py
======================
Regression tests for bugs introduced by A2 fixes and corrected in B1.

B1a — normalize_for_product_text (ferreteria_language.py):
  Product text uses a separate normalization that excludes "llaves"→"llave"
  and "francesas"→"francesa".  This prevents products like "Adaptador para
  Llaves Combinadas" from gaining a false "llave" token and scoring above
  SCORE_LOW against "llave francesa" queries.

  Regressions fixed:
    C12 — "llave francesa" was returning adaptadores (WARN post-A2)
    C22 — "lave francesa" typo was matching adaptadores via term scoring (WARN)

B1b — _families_without_para_context (ferreteria_quote.py):
  Strips single-word "para [family]" use-context before calling infer_families
  so that "para taladro" does not add 'taladro' to the requested families and
  give expensive drill products a +3 family-match bonus.

  Regression fixed:
    C29 — "necesito una mecha de 8mm para taladro" was returning taladros at
           $2.4M (WARN WORSE post-A2) because the cross-unit penalty (Fix A)
           correctly eliminated the old acople winner but the taladro family
           inclusion elevated drills to score +6.0.
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_language import normalize_basic, normalize_for_product_text
from bot_sales.ferreteria_quote import (
    _SCORE_LOW,
    _families_without_para_context,
    _score_product,
)
from bot_sales.ferreteria_dimensions import extract_dimensions
from bot_sales.ferreteria_language import normalize_live_language


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_product(name: str, category: str, sku: str = "") -> dict:
    return {"model": "", "name": name, "sku": sku, "category": category}


ADAPTADOR_LLAVE = _make_product(
    "Adaptador 3/8 para Llaves Combinadas Ratchet - Bahco",
    category="Herramientas Manuales",
)
LLAVE_FRANCESA = _make_product(
    "Llave Francesa Ajustable 10 pulg - Stanley",
    category="Herramientas Manuales",
)
BROCA_8MM = _make_product(
    "Broca Acero Rapido 8 mm - Ezeta",
    category="Mechas y Brocas",
)
TALADRO = _make_product(
    "Taladro Percutor 850W - DeWalt",
    category="Herramientas Electricas",
)
TORNILLO_MADERA = _make_product(
    "Tornillo para Madera 6x50 - Acero",
    category="Tornilleria y Fijaciones",
)


# ---------------------------------------------------------------------------
# B1a — Product-text normalization (C12 / C22)
# ---------------------------------------------------------------------------

class TestProductTextNormalization(unittest.TestCase):
    """normalize_for_product_text must preserve 'llaves'/'francesas' as plural."""

    def test_llaves_kept_plural_in_product_text(self):
        """'Llaves' in a product name must NOT become 'llave' in product-text scoring."""
        result = normalize_for_product_text("Adaptador para Llaves Combinadas Ratchet")
        self.assertIn("llaves", result,
                      "product text should keep 'llaves' plural to avoid false overlap")
        self.assertNotIn(" llave ", f" {result} ",
                         "singular 'llave' should not appear in place of 'llaves'")

    def test_francesas_kept_plural_in_product_text(self):
        """'Francesas' in a product name must NOT become 'francesa' in product text."""
        result = normalize_for_product_text("Llaves Francesas Set 6 piezas")
        self.assertIn("francesas", result)

    def test_mechas_still_normalized_in_product_text(self):
        """Category keywords like 'mechas'→'mecha' still apply (not excluded)."""
        result = normalize_for_product_text("Mechas y Brocas categoria")
        self.assertIn("mecha", result)
        self.assertNotIn("mechas", result)

    def test_brocas_still_normalized_in_product_text(self):
        result = normalize_for_product_text("Brocas Acero categoria")
        self.assertIn("broca", result)

    def test_query_normalization_unchanged(self):
        """normalize_basic still converts 'llaves'/'francesas' — Fix C intact."""
        self.assertEqual(normalize_basic("llaves"), "llave")
        self.assertEqual(normalize_basic("francesas"), "francesa")
        self.assertEqual(normalize_basic("llaves francesas"), "llave francesa")


class TestC12LlaveFrancesaAdaptadorFiltered(unittest.TestCase):
    """C12: 'llave francesa' must not return adaptadores above SCORE_LOW."""

    def _score(self, product: dict, query: str) -> float:
        nl = normalize_live_language(query)
        dims = extract_dimensions(nl)
        return _score_product(product, nl, requested_families=["llave"],
                              requested_dimensions=dims)

    def test_adaptador_llaves_below_score_low_for_llave_francesa(self):
        """Adaptador para Llaves must score below SCORE_LOW for 'llave francesa'."""
        score = self._score(ADAPTADOR_LLAVE, "llave francesa")
        self.assertLess(
            score, _SCORE_LOW,
            f"Adaptador scored {score} >= SCORE_LOW ({_SCORE_LOW}) — "
            "would appear in results for 'llave francesa' query",
        )

    def test_llave_francesa_above_score_low(self):
        """Llave Francesa must score well above SCORE_LOW."""
        score = self._score(LLAVE_FRANCESA, "llave francesa")
        self.assertGreater(score, _SCORE_LOW + 2,
                           f"Llave Francesa scored only {score}")

    def test_llave_francesa_beats_adaptador_by_wide_margin(self):
        """Pre-A2 margin restored: llave francesa should beat adaptador by >= 6 pts."""
        score_francesa = self._score(LLAVE_FRANCESA, "llave francesa")
        score_adaptador = self._score(ADAPTADOR_LLAVE, "llave francesa")
        margin = score_francesa - score_adaptador
        self.assertGreaterEqual(
            margin, 6.0,
            f"Margin too small: llave={score_francesa:.1f}, adaptador={score_adaptador:.1f}, "
            f"margin={margin:.1f} (want >= 6.0 to protect against many catalog adaptadores)",
        )


class TestC22TyPoLaveFrancesa(unittest.TestCase):
    """C22: 'lave francesa' typo — adaptadores must not score above SCORE_LOW via search terms."""

    def _score_vs_term(self, product: dict, term: str) -> float:
        dims = extract_dimensions(term)
        return _score_product(product, term, requested_families=["llave"],
                              requested_dimensions=dims)

    def test_adaptador_below_score_low_against_llave_francesa_term(self):
        """When scored against the search term 'llave francesa', adaptador must stay below SCORE_LOW.

        This is the key C22 mechanism: _score_product is called with max(score_vs_normalized,
        score_vs_term).  The normalized 'lave francesa' gave adaptador 0.0, but the synonym-
        expanded term 'llave francesa' was giving +6.0 post-A2.
        """
        score = self._score_vs_term(ADAPTADOR_LLAVE, "llave francesa")
        self.assertLess(
            score, _SCORE_LOW,
            f"Adaptador scored {score} >= SCORE_LOW against 'llave francesa' term — "
            "would pollute typo 'lave francesa' results",
        )

    def test_llave_francesa_high_against_term(self):
        score = self._score_vs_term(LLAVE_FRANCESA, "llave francesa")
        self.assertGreater(score, _SCORE_LOW + 3)


# ---------------------------------------------------------------------------
# B1b — Para-context family filter (C29)
# ---------------------------------------------------------------------------

class TestParaContextFamilyFilter(unittest.TestCase):
    """_families_without_para_context must strip use-context families correctly."""

    def _fams(self, query: str) -> list:
        nl = normalize_live_language(query)
        return _families_without_para_context(nl)

    # ── C29 key fix ──────────────────────────────────────────────────────────

    def test_c29_mecha_para_taladro_removes_taladro_family(self):
        """'para taladro' must not add taladro to the families gate."""
        fams = self._fams("necesito una mecha de 8mm para taladro")
        self.assertIn("mecha", fams,
                      "'mecha' must remain in families")
        self.assertNotIn("taladro", fams,
                         "'taladro' from 'para taladro' must be stripped")

    def test_c29_taladro_still_penalised_in_scoring(self):
        """Taladro product must score below SCORE_LOW for 'mecha de 8mm para taladro'."""
        nl = normalize_live_language("necesito una mecha de 8mm para taladro")
        fams = _families_without_para_context(nl)
        dims = extract_dimensions(nl)
        score_taladro = _score_product(TALADRO, nl, requested_families=fams,
                                       requested_dimensions=dims)
        score_broca = _score_product(BROCA_8MM, nl, requested_families=fams,
                                     requested_dimensions=dims)
        self.assertLess(
            score_taladro, _SCORE_LOW,
            f"Taladro scored {score_taladro} — should be below SCORE_LOW={_SCORE_LOW}",
        )
        self.assertGreater(
            score_broca, score_taladro,
            f"Broca ({score_broca:.1f}) should beat Taladro ({score_taladro:.1f})",
        )

    # ── No-regression checks ─────────────────────────────────────────────────

    def test_taladro_standalone_unchanged(self):
        """'necesito un taladro' — no 'para', families must include 'taladro'."""
        fams = self._fams("necesito un taladro")
        self.assertIn("taladro", fams)

    def test_mecha_standalone_unchanged(self):
        """'mecha 8mm' — no 'para', families must include 'mecha'."""
        fams = self._fams("mecha 8mm")
        self.assertIn("mecha", fams)

    def test_tornillo_para_madera_unchanged(self):
        """'tornillo para madera' — 'madera' is not a family; tornillo must stay."""
        fams = self._fams("tornillo para madera")
        self.assertIn("tornillo", fams)

    def test_amoladora_con_disco_para_metal_unchanged(self):
        """'amoladora con disco para metal' — 'metal' not a family; amoladora preserved."""
        fams = self._fams("amoladora con disco para metal")
        self.assertIn("amoladora", fams)

    def test_taladro_sin_mecha_not_affected(self):
        """'taladro sin mecha' has no 'para' — filter must not touch it."""
        nl = normalize_live_language("taladro sin mecha")
        fams_raw = _families_without_para_context(nl)
        # No "para" in text → result equals raw infer_families output unchanged.
        # We only assert taladro is present (pre-existing mecha detection is irrelevant here).
        self.assertIn("taladro", fams_raw)

    def test_para_una_obra_necesito_mechas_mecha_preserved(self):
        """'para una obra necesito mechas' — 'una' after para is not a family; mecha kept."""
        fams = self._fams("para una obra necesito mechas")
        self.assertIn("mecha", fams,
                      "'mecha' must survive even when 'para una' is in the text")

    def test_safety_fallback_no_empty_families(self):
        """If filtering would empty the list, fallback keeps the original."""
        # "destornillador philips para tornillos m8":
        # raw families=['tornillo'], filtered would be [] → fallback → ['tornillo']
        fams = self._fams("destornillador philips para tornillos m8")
        self.assertGreater(len(fams), 0,
                           "Safety fallback must never return empty families list")


if __name__ == "__main__":
    unittest.main()
