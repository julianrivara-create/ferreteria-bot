"""DT-13: fuzzy matching para regional_terms — cubre typos frecuentes sin tocar
otros vocabularios (catálogo, _USE_TERMS, _MATERIAL_TERMS, _SURFACE_TERMS).
"""

import pytest
from bot_sales.ferreteria_language import normalize_live_language


def _knowledge(regional_terms: dict) -> dict:
    return {"language_patterns": {"regional_terms": regional_terms}}


_DRYWALL_KNOWLEDGE = _knowledge({"drywall": "durlock"})


def test_typo_drywal_resolves_to_durlock():
    """Caso del bug original: 'drywal' (typo, falta una 'l') resuelve a 'durlock'."""
    result = normalize_live_language("una caja de tornillos para drywal", _DRYWALL_KNOWLEDGE)
    assert "durlock" in result
    assert "drywal" not in result


def test_typo_mehca_resolves_to_target():
    """Transposición de letras (h↔c): 'mehca' fuzzy-matchea la key 'mecha'."""
    k = _knowledge({"mecha": "broca"})
    result = normalize_live_language("una mehca de 8mm para madera", k)
    assert "broca" in result
    assert "mehca" not in result


def test_typo_short_token_not_fuzzy():
    """Tokens de 3 chars quedan fuera del fuzzy para evitar falsos positivos.

    'can' vs 'cano' tiene JaroWinkler=0.94 — sin la guarda de longitud mínima
    provocaría sustituciones ridículas. El guard _FUZZY_MIN_TOKEN_LEN=4 lo previene.
    """
    k = _knowledge({"cano": "tuberia"})
    result = normalize_live_language("un can de pvc", k)
    assert "tuberia" not in result
    assert "can" in result


def test_exact_match_still_works():
    """Sanity: la ruta exacta sigue funcionando sin interferencia del fuzzy pass."""
    result = normalize_live_language("tornillos para drywall", _DRYWALL_KNOWLEDGE)
    assert "durlock" in result
    assert "drywall" not in result


def test_no_false_positive_unrelated_word():
    """Palabras comunes del catálogo no deben matchear keys de regional_terms."""
    result = normalize_live_language("quiero un tornillo para madera", _DRYWALL_KNOWLEDGE)
    assert "durlock" not in result
    assert "tornillo" in result


def test_ambiguous_match_returns_unchanged():
    """Dos candidatos igualmente cercanos al typo → guarda de ambigüedad bloquea la sustitución."""
    k = _knowledge({"drywala": "value_a", "drywalb": "value_b"})
    result = normalize_live_language("tornillos para drywal", k)
    assert "value_a" not in result
    assert "value_b" not in result
    assert "drywal" in result
