# NOTE: Estos tests fallan contra main hasta que los fixes
# D1 (family_rules), D2 (synonyms), D3 (scoring), D4 (find_matches)
# estén mergeados. No son regresión.
"""
test_matcher_base.py
====================
Unit tests for the 8 known matcher false positives documented in PENDIENTES.md.

Unlike demo_test_suite.py (keyword presence), these tests assert on product
IDENTITY: the category and name of each returned product must match the search
intent — not merely share a token with the query.

Root causes (unfixed on main):
  Bug 1 — find_matches() uses OR-any logic (any single token hits = match)
  Bug 2 — buscar_stock() never calls _score_product()
  Bug 3 — buscar_stock() never calls validate_query_specs()

Run:
    PYTHONPATH=. pytest bot_sales/tests/test_matcher_base.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Ferreteria catalog path — real data, no mocking
_CATALOG_CSV = (
    Path(__file__).parent.parent.parent
    / "data" / "tenants" / "ferreteria" / "catalog.csv"
)


# ---------------------------------------------------------------------------
# Fixture — real DB, BusinessLogic stub (no LLM / FAQHandler / etc.)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def logic(tmp_path_factory):
    """
    BusinessLogic instance backed by the real ferreteria catalog.

    Uses BusinessLogic.__new__ to bypass __init__ (which pulls in FAQHandler,
    BundleManager, EmailClient, etc.). Only self.db is wired — sufficient for
    buscar_stock and _normalize_model.

    No API key → vector search is disabled; find_matches_hybrid falls back to
    keyword-only search, which is exactly what we want to stress-test here.
    """
    from bot_sales.core.database import Database
    from bot_sales.core.business_logic import BusinessLogic

    db_dir = tmp_path_factory.mktemp("matcher_base_db")
    db = Database(
        str(db_dir / "catalog.db"),
        str(_CATALOG_CSV),
        str(db_dir / "test.log"),
        api_key="",  # no vector search
    )
    engine = BusinessLogic.__new__(BusinessLogic)
    engine.db = db
    return engine


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _names(result: dict) -> list[str]:
    return [p["name"] for p in result.get("products", [])]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestMatcherBaseFalsePositives:
    """
    Eight queries that currently return wrong products on main.

    Each test captures what CORRECT behavior looks like so that:
      - the test FAILS on main   (wrong products or missing results)
      - the test PASSES after D1-D4 are merged (right products, right score)
    """

    # ── Case 1 ──────────────────────────────────────────────────────────────

    def test_destornillador_philips_no_cerraduras(self, logic):
        """
        'destornillador philips' must return actual screwdrivers only.

        Bug on main (Bug 1): OR-any logic makes 'philips' match Philips-brand
        lamps and 'destornillador' matches 'Cerradura Cierre Gabinete
        Destornillador Para S9000 - Genrod' (a lock that needs a screwdriver to
        open, not a screwdriver itself).

        Expected after fix: only products whose name starts with 'Destornillador'
        or is a screwdriver kit (Juego/Set Destornilladores).
        """
        result = logic.buscar_stock("destornillador philips")
        assert result["status"] == "found", (
            f"Screwdrivers exist in catalog but got status='{result['status']}'. "
            "Possible plural/normalization issue."
        )

        for p in result["products"]:
            name_l = p["name"].lower()
            # Known false positive: cerradura (lock) that mentions a screwdriver
            assert not name_l.startswith("cerradura"), (
                f"Returned a cerradura (lock) for screwdriver query: {p['name']}\n"
                "Known false positive on main — Bug 1 (OR-any) + Bug 2 (no scoring)."
            )
            # Every returned product must be a screwdriver or screwdriver set
            assert "destornillador" in name_l, (
                f"Non-screwdriver product returned: {p['name']}\n"
                "After fix: only destornilladores should score above threshold."
            )

        # Positive guard: at least one actual destornillador must be present
        names_lower = [p["name"].lower() for p in result["products"]]
        assert any(n.startswith("destornillador") for n in names_lower), (
            "No product with name starting 'Destornillador' found. "
            "Catalog has Stanley/Bahco/Argentec screwdrivers — scoring must surface them."
        )

    # ── Case 2 ──────────────────────────────────────────────────────────────

    def test_mechas_8mm_bosch_no_acoples(self, logic):
        """
        '5 mechas 8mm Bosch' must return actual drill bits, not acoples.

        Bug on main: 'broca' token matches 'Acople para Broca 1 1/4 - Aliafor'
        (fitting for a drill bit, not a drill bit itself). 'bosch' also matches
        any Bosch accessory. Result: Acople Atornillador $210k, Acople Broca $57k
        appear before real brocas.

        Expected after fix: only brocas/mechas are returned; acoples are
        filtered by D3 (score below SCORE_LOW) or excluded by D4 (strict-AND).
        """
        result = logic.buscar_stock("5 mechas 8mm Bosch")
        assert result["status"] == "found", (
            f"Brocas Bosch exist in catalog (26+) but got status='{result['status']}'."
        )

        for p in result["products"]:
            name_l = p["name"].lower()
            assert not name_l.startswith("acople"), (
                f"Returned acople for mechas query: {p['name']}\n"
                "Known false positive on main — 'broca' token matches acople names."
            )
            assert not name_l.startswith("accesorio"), (
                f"Returned accesorio for mechas query: {p['name']}"
            )
            # Every product must be a broca/mecha (drill bit)
            assert any(kw in name_l for kw in ("broca", "mecha")), (
                f"Non-broca/mecha returned: {p['name']}\n"
                "After fix: only brocas and mechas should pass the score threshold."
            )

    # ── Case 3 ──────────────────────────────────────────────────────────────

    def test_taladros_returns_actual_drills(self, logic):
        """
        'taladros' must return actual drills, not adapters that mention taladro.

        Bug on main (Bug 2, plural): 'taladros' as a token does not match catalog
        names (which use singular 'taladro'), so D2's plural normalization is
        required. After D2, 'taladro' matches — but Bug 1 then also returns
        'Adaptador Taladro SDS' and 'Aparejo para Taladro Diamantado'.

        Expected after fix: only products that ARE taladros (drills / drill
        combos) are returned; adapters and aparejos are filtered out.
        """
        result = logic.buscar_stock("taladros")
        assert result["status"] == "found", (
            f"Taladros exist in catalog but got status='{result['status']}'.\n"
            "Likely Bug 2: 'taladros' plural not normalized to 'taladro' (D2 fix)."
        )

        for p in result["products"]:
            name_l = p["name"].lower()
            assert not name_l.startswith("adaptador"), (
                f"Returned adaptador for taladros query: {p['name']}\n"
                "Adaptadores reference taladros but are not drills."
            )
            assert not name_l.startswith("aparejo"), (
                f"Returned aparejo for taladros query: {p['name']}\n"
                "Aparejos (rigging/blocks) reference taladros but are not drills."
            )
            # Product must be an actual taladro or atornillador combo
            assert "taladro" in name_l or "atornillador" in name_l, (
                f"Non-taladro product returned: {p['name']}"
            )

    # ── Case 4 ──────────────────────────────────────────────────────────────

    def test_llaves_de_paso_no_adaptadores(self, logic):
        """
        'llaves de paso' must return shutoff valves, not combination-wrench adapters.

        Bug on main (Bug 1): 'de' (2 chars, threshold) is a token that appears
        in almost every Spanish product name as a substring. The OR-any check
        means almost the entire catalog matches. First alphabetical result is
        'Adaptador 3/8 para Llaves Combinadas Ratchet - Bahco'.

        Expected after fix: only products with 'paso' in their name (llaves de
        paso = shutoff valves in plumbing) should be returned.
        """
        result = logic.buscar_stock("llaves de paso")
        assert result["status"] == "found", (
            f"Llaves de paso exist in catalog but got status='{result['status']}'."
        )

        for p in result["products"]:
            name_l = p["name"].lower()
            assert not name_l.startswith("adaptador"), (
                f"Returned adaptador for llaves de paso query: {p['name']}\n"
                "Known false positive on main — OR-any 'de' token matches everything."
            )
            # Every result must have 'paso' in the name (shutoff valves)
            assert "paso" in name_l, (
                f"Returned product without 'paso' in name: {p['name']}\n"
                "After fix: only llave-de-paso plumbing valves should be returned."
            )

        # Positive: at least one Acqua System / Coes llave de paso
        assert any("paso" in p["name"].lower() for p in result["products"]), (
            "No actual llave de paso found. "
            "Catalog has Acqua System / Coes / Gloss paso valves."
        )

    # ── Case 5 ──────────────────────────────────────────────────────────────

    def test_sellador_siliconado_no_productos_siliconados_irrelevantes(self, logic):
        """
        'sellador siliconado' must return silicone sealants only.

        Bug on main (Bug 1): 'siliconado' token matches 'Abrillantador Siliconado',
        'Impermeabilizante Siliconado', 'Limpiador Siliconado', etc. — all have
        'siliconado' in name but are not sealants. 'Anteojo Puente Silicona'
        matches 'silicona' in the bot's LLM path.

        Expected after fix: only products that are both selladores AND siliconados
        (or contain silicona) — i.e., actual silicone sealant products.
        """
        result = logic.buscar_stock("sellador siliconado")
        assert result["status"] == "found", (
            f"Selladores siliconados exist in catalog but got status='{result['status']}'."
        )

        for p in result["products"]:
            name_l = p["name"].lower()
            # Must not return anteojos (safety glasses with silicone bridge)
            assert not name_l.startswith("anteojo"), (
                f"Returned safety glasses for sealant query: {p['name']}"
            )
            # Must not return polish/cleaners that are merely siliconados
            assert not name_l.startswith("abrillantador"), (
                f"Returned abrillantador for sellador query: {p['name']}"
            )
            assert not name_l.startswith("impermeabilizante"), (
                f"Returned impermeabilizante for sellador query: {p['name']}"
            )
            assert not name_l.startswith("limpiador"), (
                f"Returned limpiador for sellador query: {p['name']}"
            )
            # Every result must be a sellador
            assert "sellador" in name_l or "adhesivo" in name_l, (
                f"Returned non-sellador product: {p['name']}\n"
                "After fix: only selladores/adhesivos should score above threshold."
            )

    # ── Case 6 ──────────────────────────────────────────────────────────────

    def test_codos_90_grados_returns_codo_fittings(self, logic):
        """
        'codos 90 grados' must return elbow fittings, not abrazaderas with '90'
        in their size range.

        Bug on main (Bug 1): '90' token matches any abrazadera whose size range
        contains '90' (e.g. 'Abrazadera 12 mm Inoxidable 90-110'). These flood
        the results. Actual codo fittings ('Bronce codo HH 90 1/2') may be
        present but buried among hundreds of irrelevant results.

        After fix: only products with 'codo' in their name are returned.
        Catalog has: Bronce codo HH 90 1/2, Bronce codo MH 90 3/4, Alemite Codo 90°.
        """
        result = logic.buscar_stock("codos 90 grados")
        assert result["status"] != "no_match", (
            "Codo fittings exist in catalog but got no_match — false negative.\n"
            "Fix: add 'codo' to item_family_map.yaml (D1) and apply plural "
            "normalization 'codos'→'codo' (D2)."
        )
        products = result.get("products", [])
        assert len(products) > 0, "Expected at least one codo 90° fitting in results."

        for p in products:
            name_l = p["name"].lower()
            # Must not return abrazaderas (clamps) that happen to have '90' in range
            assert not name_l.startswith("abrazadera"), (
                f"Returned abrazadera for codos 90° query: {p['name']}\n"
                "Bug 1: '90' token matches abrazadera size ranges like '90-110'."
            )
            # Every result must be an actual codo fitting
            assert "codo" in name_l or "codillo" in name_l, (
                f"Returned non-codo product for 'codos 90 grados': {p['name']}\n"
                "After fix: only elbow fittings should pass the relevance threshold."
            )

    # ── Case 7 ──────────────────────────────────────────────────────────────

    def test_cuplas_returns_cupla_fittings_no_recuplast(self, logic):
        """
        'cuplas' must return cupla pipe fittings, not Recuplast paint products.

        Bug on main (Bug 1 + plural): 'cuplas' plural does not match 'cupla' in
        catalog (false negative). If D2 normalizes 'cuplas'→'cupla', Bug 1 then
        makes 'cupla' substring-match 'recuplast' (r-e-**cupla**-st), returning
        Sinteplast base-coat products as pipe fittings.

        Expected after fix:
          - status == "found" (D2: plural normalization)
          - No Recuplast products (D4: word-boundary or strict matching)
          - All returned products have 'cupla' as a standalone term in their name
        """
        result = logic.buscar_stock("cuplas")
        assert result["status"] == "found", (
            f"Cupla fittings exist in catalog but got status='{result['status']}'.\n"
            "Bug: 'cuplas' plural not normalized to 'cupla' — needs D2 fix."
        )

        for p in result["products"]:
            name_l = p["name"].lower()
            # Must not return Recuplast (paint product where 'cupla' is a substring)
            assert "recuplast" not in name_l, (
                f"Returned Recuplast for cuplas query: {p['name']}\n"
                "Bug 1: 'cupla' is a substring of 'recuplast' — needs D4 fix."
            )
            # Every result must be an actual cupla fitting
            assert "cupla" in name_l, (
                f"Returned non-cupla product: {p['name']}\n"
                "After fix: only products with 'cupla' in name should be returned."
            )

        # Positive: at least one Bronce cupla must be present
        assert any("cupla" in p["name"].lower() for p in result["products"]), (
            "No 'Bronce cupla' fitting found. "
            "Catalog has Bronce cupla 1/4, 1/8, 3/8, etc."
        )

    # ── Case 8 ──────────────────────────────────────────────────────────────

    def test_martillo_500kg_blocked_by_validator(self, logic):
        """
        'martillo Stanley 500kg' must be rejected before any DB search.

        Bug on main (Bug 3): search_validator.validate_query_specs() correctly
        detects an impossible weight (V1 rule: hammer max ~10 kg) but buscar_stock
        never calls it. The query proceeds to find_matches and returns Stanley
        hammers.

        Expected after D4 fix: buscar_stock calls validate_query_specs() at
        entry point; impossible spec → status='no_match' immediately.

        Note: validate_query_specs("martillo Stanley 500kg") already returns
        (False, reason) — the fix is wiring it into buscar_stock, not the rule.
        """
        result = logic.buscar_stock("martillo Stanley 500kg")
        assert result["status"] == "no_match", (
            f"Expected validator to block '500kg hammer' as impossible weight, "
            f"but got status='{result['status']}' with "
            f"{len(result.get('products', []))} product(s).\n"
            "Bug 3: buscar_stock does not call validate_query_specs().\n"
            "Fix: add validate_query_specs() call at the top of buscar_stock."
        )
