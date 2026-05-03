from __future__ import annotations

import re
from typing import Any, Dict

from bot_sales.knowledge.defaults import DEFAULT_LANGUAGE_PATTERNS


_ACCENT_MAP = str.maketrans({
    "á": "a",
    "é": "e",
    "í": "i",
    "ó": "o",
    "ú": "u",
    "ä": "a",
    "ë": "e",
    "ï": "i",
    "ö": "o",
    "ü": "u",
    "ñ": "n",
})

_BASE_SPELLING_VARIANTS: Dict[str, str] = {
    "teflon": "teflon",
    "teflones": "teflon",
    "silicon": "silicona",
    "siliconas": "silicona",
    "tornillos": "tornillo",
    "tarugos": "tarugo",
    "tacos": "taco",
    "selladores": "sellador",
    "brocas": "broca",
    "mechas": "mecha",
    "caños": "cano",
    # Fix C: plural normalization for llave/francesa (query side only — see below)
    "llaves": "llave",
    "francesas": "francesa",
}

# Subset of _BASE_SPELLING_VARIANTS safe for product-text normalization.
# Intentionally excludes "llaves"→"llave" and "francesas"→"francesa" because
# normalising those in product text causes false partial-match bonuses:
# "Adaptador para Llaves Combinadas" would gain the "llave" token and score
# +3 word-overlap against a "llave francesa" query, collapsing a pre-A2
# 8-point margin down to 2 points and putting adaptadores above SCORE_LOW.
_PRODUCT_SPELLING_VARIANTS: Dict[str, str] = {
    k: v for k, v in _BASE_SPELLING_VARIANTS.items()
    if k not in ("llaves", "francesas")
}


def get_language_patterns(knowledge: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = (knowledge or {}).get("language_patterns") or {}
    return {
        "misspellings": dict(DEFAULT_LANGUAGE_PATTERNS.get("misspellings", {})) | dict(payload.get("misspellings", {})),
        "regional_terms": dict(DEFAULT_LANGUAGE_PATTERNS.get("regional_terms", {})) | dict(payload.get("regional_terms", {})),
        "brand_generics": dict(DEFAULT_LANGUAGE_PATTERNS.get("brand_generics", {})) | dict(payload.get("brand_generics", {})),
        "abbreviations": dict(DEFAULT_LANGUAGE_PATTERNS.get("abbreviations", {})) | dict(payload.get("abbreviations", {})),
        "surface_aliases": dict(DEFAULT_LANGUAGE_PATTERNS.get("surface_aliases", {})) | dict(payload.get("surface_aliases", {})),
        "shorthand_dimension_patterns": list(DEFAULT_LANGUAGE_PATTERNS.get("shorthand_dimension_patterns", []))
        + list(payload.get("shorthand_dimension_patterns", [])),
    }


def normalize_basic(text: str) -> str:
    normalized = text.lower().translate(_ACCENT_MAP)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for variant, canonical in _BASE_SPELLING_VARIANTS.items():
        normalized = re.sub(rf"\b{re.escape(variant)}\b", canonical, normalized)
    return normalized


def normalize_for_product_text(text: str) -> str:
    """Normalize product catalog text for word-overlap scoring.

    Like normalize_basic but uses _PRODUCT_SPELLING_VARIANTS, which excludes
    "llaves"→"llave" and "francesas"→"francesa".  This keeps plural forms intact
    in product names so that products like "Adaptador para Llaves Combinadas" do
    NOT gain a false "llave" token that would match user queries for "llave francesa".

    Used only in _product_text() for scoring; normalize_basic still applies the full
    set of variants to user queries (Fix C intended behaviour is preserved).
    """
    normalized = text.lower().translate(_ACCENT_MAP)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for variant, canonical in _PRODUCT_SPELLING_VARIANTS.items():
        normalized = re.sub(rf"\b{re.escape(variant)}\b", canonical, normalized)
    return normalized


def _replace_terms(text: str, mapping: Dict[str, str]) -> str:
    updated = text
    for source, target in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if not source or not target:
            continue
        updated = re.sub(rf"\b{re.escape(normalize_basic(source))}\b", normalize_basic(target), updated)
    return updated


def normalize_live_language(text: str, knowledge: Dict[str, Any] | None = None) -> str:
    normalized = normalize_basic(text)
    patterns = get_language_patterns(knowledge)
    for mapping_key in ("misspellings", "regional_terms", "abbreviations", "brand_generics"):
        normalized = _replace_terms(normalized, patterns.get(mapping_key, {}))
    for pattern in patterns.get("shorthand_dimension_patterns", []):
        regex = str(pattern.get("pattern", "")).strip()
        replacement = str(pattern.get("replacement", "")).strip()
        if regex and replacement:
            normalized = re.sub(regex, replacement, normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def expand_family_terms(text: str, knowledge: Dict[str, Any] | None = None) -> str:
    normalized = normalize_live_language(text, knowledge=knowledge)
    patterns = get_language_patterns(knowledge)
    return _replace_terms(normalized, patterns.get("surface_aliases", {}))
