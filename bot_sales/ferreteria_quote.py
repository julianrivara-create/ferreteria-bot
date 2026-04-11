#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Phase 3 — Structural Safety Finalization
"""
Ferreteria Quote Builder  (Phase 2 — Corrective Pass)
======================================================
Centralises all Ferreteria-specific quoting logic.

Key improvements over Phase 1.5
---------------------------------
* Strict post-match scoring that rejects false positives from the loose
  database `any(token in haystack)` matcher.
* Category-family gate: a product from the wrong item family is rejected
  even when a token accidentally matches.
* Pack/unit safety: box/pack SKUs are flagged and never silently counted
  as individual units.
* Complementary suggestions: rule-based, catalog-grounded only.
* Acceptance detection and response generation with unresolved guard.
* Disambiguation (unchanged from Phase 1.5 — kept stable).
* Session guard (unchanged — kept stable).

Design constraints
------------------
* No NLP / LLM calls / external deps beyond stdlib and business_logic.
* Synonym map is explicit and human-curated.
* Scoring is conservative: prefer leaving items ambiguous over false
  certainty.
* Totals are only computed when qty + price + pack semantics are safe.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from bot_sales.ferreteria_dimensions import extract_dimensions, missing_required_dimensions
from bot_sales.ferreteria_family_model import (
    build_clarification_prompt,
    detect_product_family,
    get_family_rule,
    infer_families,
    is_autopick_blocked,
)
from bot_sales.ferreteria_language import normalize_basic, normalize_live_language
from bot_sales.ferreteria_substitutions import filter_safe_alternatives
from bot_sales.ferreteria_unresolved_log import log_unresolved_item as _log_unresolved
from bot_sales.knowledge.defaults import (
    DEFAULT_ACCEPTANCE_PATTERNS,
    DEFAULT_BLOCKED_TERMS,
    DEFAULT_CLARIFICATION_RULES,
    DEFAULT_COMPLEMENTARY_RULES,
    DEFAULT_FAMILY_RULES,
    DEFAULT_SYNONYM_ENTRIES,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

QuoteItem = Dict[str, Any]
# Fields:
#   original        raw text as user typed
#   normalized      after synonym expansion / accent strip
#   qty             requested quantity (int, default 1)
#   qty_explicit    True only when user wrote a number
#   unit_hint       optional unit word ("lata", "rollo", …)
#   status          "resolved" | "ambiguous" | "unresolved"
#   products        list of matched catalog product dicts (candidates)
#   unit_price      float | None
#   subtotal        float | None  — only when qty + price + pack safe
#   pack_note       str | None   — present when pack/unit mismatch detected
#   clarification   str | None   — short per-item clarification question
#   notes           str | None
#   complementary   list[str]    — grounded complementary search terms

# ---------------------------------------------------------------------------
# Accent / typo normalisation
# ---------------------------------------------------------------------------


def _knowledge_map(knowledge: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return knowledge or {}


def _synonym_entries(knowledge: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list((_knowledge_map(knowledge).get("synonyms") or {}).get("entries", DEFAULT_SYNONYM_ENTRIES))


def _family_rules(knowledge: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict((_knowledge_map(knowledge).get("families") or {}).get("families", DEFAULT_FAMILY_RULES))


def _clarification_rules(knowledge: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict((_knowledge_map(knowledge).get("clarifications") or {}).get("rules", DEFAULT_CLARIFICATION_RULES))


def _blocked_terms(knowledge: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list((_knowledge_map(knowledge).get("blocked_terms") or {}).get("terms", DEFAULT_BLOCKED_TERMS))


def _complementary_rules(knowledge: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict((_knowledge_map(knowledge).get("complementary") or {}).get("rules", DEFAULT_COMPLEMENTARY_RULES))


def _acceptance_patterns(knowledge: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    merged = dict(DEFAULT_ACCEPTANCE_PATTERNS)
    merged.update((_knowledge_map(knowledge).get("acceptance") or {}))
    return merged

def _normalize(text: str) -> str:
    return normalize_basic(text)


# ---------------------------------------------------------------------------
# Category-family gate
# ---------------------------------------------------------------------------
# Maps significant item keywords → the ONLY acceptable catalog categories.
# If the matched product's category is NOT in the set, the match is rejected.

_ITEM_FAMILY_MAP: Dict[str, set] = {
    "taladro":          {"Herramientas Electricas"},
    "amoladora":        {"Herramientas Electricas"},
    "atornillador":     {"Herramientas Electricas"},
    "mecha":            {"Herramientas Electricas", "Herramientas Manuales", "Accesorios"},
    "broca":            {"Herramientas Electricas", "Herramientas Manuales", "Accesorios"},
    "martillo":         {"Herramientas Manuales"},
    "destornillador":   {"Herramientas Manuales"},
    "llave":            {"Herramientas Manuales"},
    "tornillo":         {"Tornilleria"},
    "autoperforante":   {"Tornilleria"},
    "buloneria":        {"Tornilleria", "Fijaciones"},
    "tarugo":           {"Fijaciones"},
    "taco":             {"Fijaciones"},
    "fijacion":         {"Fijaciones"},
    "pintura":          {"Pintureria"},
    "latex":            {"Pintureria"},
    "esmalte":          {"Pintureria"},
    "rodillo":          {"Pintureria"},
    "pincel":           {"Pintureria"},
    "brocha":           {"Pintureria"},
    "bandeja":          {"Pintureria"},
    "silicona":         {"Plomeria"},
    "sellador":         {"Plomeria"},
    "teflon":           {"Plomeria"},
    "cano":             {"Plomeria"},
    "caño":             {"Plomeria"},
    "conexion":         {"Plomeria"},
    "guante":           {"Seguridad"},
    "casco":            {"Seguridad"},
    "lente":            {"Seguridad"},
    "cable":            {"Electricidad"},
    "interruptor":      {"Electricidad"},
    "toma":             {"Electricidad"},
}

# Category aliases the DB may return
_CATEGORY_ALIASES: Dict[str, str] = {
    "taladro":          "Herramientas Electricas",
    "amoladora":        "Herramientas Electricas",
    "atornillador":     "Herramientas Electricas",
    "martillo":         "Herramientas Manuales",
    "destornillador":   "Herramientas Manuales",
    "llave":            "Herramientas Manuales",
    "tornillo":         "Tornilleria",
    "autoperforante":   "Tornilleria",
    "tarugo":           "Fijaciones",
    "taco":             "Fijaciones",
    "fijacion":         "Fijaciones",
    "pintura":          "Pintureria",
    "latex":            "Pintureria",
    "esmalte":          "Pintureria",
    "rodillo":          "Pintureria",
    "pincel":           "Pintureria",
    "brocha":           "Pintureria",
    "silicona":         "Plomeria",
    "sellador":         "Plomeria",
    "teflon":           "Plomeria",
    "cano":             "Plomeria",
    "conexion":         "Plomeria",
    "guante":           "Seguridad",
    "mecha":            "Herramientas Electricas",
    "broca":            "Herramientas Electricas",
    "llave":            "Herramientas Manuales",
    "cable":            "Electricidad",
}


def _detect_category(normalized: str, knowledge: Optional[Dict[str, Any]] = None) -> Optional[str]:
    inferred_families = infer_families(normalized, knowledge=knowledge)
    for family in inferred_families:
        categories = (get_family_rule(family, knowledge).get("allowed_categories") or [])
        if categories:
            return categories[0]
    for token, cat in _CATEGORY_ALIASES.items():
        if token in normalized:
            return cat
    for family, rule in _family_rules(knowledge).items():
        if family in normalized:
            categories = rule.get("allowed_categories") or []
            if categories:
                return categories[0]
    return None


def _get_expected_families(normalized: str, knowledge: Optional[Dict[str, Any]] = None) -> set:
    """Return the union of acceptable categories for all item keywords found."""
    families: set = set()
    family_map = dict(_ITEM_FAMILY_MAP)
    for family, rule in _family_rules(knowledge).items():
        allowed = set(rule.get("allowed_categories") or [])
        if allowed:
            family_map[family] = allowed
    for keyword, cats in family_map.items():
        if keyword in normalized:
            families |= cats
    return families


# ---------------------------------------------------------------------------
# Pack / unit detection
# ---------------------------------------------------------------------------

# Patterns that indicate a packaged SKU (not sold per individual unit)
_PACK_RE = re.compile(
    r"\bx\s*(\d{2,})\b"           # "x100", "x 50"
    r"|caja\s+(?:de\s+)?\d+"      # "caja de 100"
    r"|\bpack\b"
    r"|\bbolsa\b"
    r"|\bkit\b"
    r"|\bset\b"
    r"|\blote\b",
    re.IGNORECASE,
)


def _detect_pack(product: Dict[str, Any]) -> Optional[str]:
    """
    If the product SKU/name is clearly a pack, return a human-readable
    description of the pack (e.g. "caja x100").  Otherwise return None.
    """
    name = _normalize(
        product.get("model") or product.get("name") or product.get("sku", "")
    )
    m = _PACK_RE.search(name)
    if not m:
        return None
    return m.group(0).strip()


def _pack_note(product: Dict[str, Any], requested_qty: int) -> Optional[str]:
    """
    Build a user-facing note when the SKU is a pack and the user asked
    for individual units. Returns None when pack semantics are safe
    (e.g. user asked for 0 or 1 which maps to buying one pack).
    """
    pack_desc = _detect_pack(product)
    if not pack_desc:
        return None
    # If user explicitly asked for more than 1, warn them
    if requested_qty > 1:
        return (
            f"Este artículo se vende en {pack_desc}. "
            f"¿Te sirve esa presentación o necesitás otra?"
        )
    # Single-item request + pack SKU: warn transparently
    return f"Este artículo se vende por {pack_desc}."


# ---------------------------------------------------------------------------
# Strict product scoring
# ---------------------------------------------------------------------------

_SIGNIFICANT_WORDS_MIN_LEN = 3

# Words that appear in many product names but carry no item-type information
_SCORE_STOP_WORDS = frozenset({
    "de", "para", "con", "una", "un", "el", "la", "los", "las",
    "por", "del", "al", "en", "y", "e", "o", "u", "a",
    "interior", "exterior", "blanco", "negro", "rojo", "azul",
    "grande", "chico", "mediano", "nuevo", "extra",
})


def _significant_words(text: str) -> set:
    return {
        w for w in text.split()
        if len(w) >= _SIGNIFICANT_WORDS_MIN_LEN and w not in _SCORE_STOP_WORDS
    }


def _product_text(product: Dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            str(product.get(field) or "")
            for field in ("model", "name", "sku", "category")
        )
    )


def _score_dimension_alignment(product: Dict[str, Any], requested_dimensions: Dict[str, str]) -> float:
    if not requested_dimensions:
        return 0.0
    product_dims = extract_dimensions(_product_text(product))
    score = 0.0
    for key, requested_value in requested_dimensions.items():
        product_value = product_dims.get(key)
        if not product_value:
            continue
        if product_value == requested_value:
            score += 1.5
        elif str(product_value) in str(requested_value) or str(requested_value) in str(product_value):
            score += 1.0
        else:
            score -= 1.25
    return score


def _score_product(
    product: Dict[str, Any],
    requested_normalized: str,
    requested_families: Optional[List[str]] = None,
    requested_dimensions: Optional[Dict[str, str]] = None,
    knowledge: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Return a confidence score 0–10 for how well this product matches
    the requested item.

    Scoring
    -------
    +5  for ≥50% significant-word overlap between product name and request
    +3  for ≥1 significant-word overlap (partial match)
    +3  for category-family alignment
    -8  HARD PENALTY for category-family mismatch (wrong item type)
    -3  if product name has zero overlap with request significant words
    """
    score = 0.0

    prod_name = _product_text(product)

    req_words = _significant_words(requested_normalized)
    name_words = _significant_words(prod_name)

    # Significant-word overlap
    if req_words:
        overlap = req_words & name_words
        ratio = len(overlap) / len(req_words)
        if ratio >= 0.5:
            score += 5.0
        elif overlap:
            score += 3.0
        else:
            score -= 3.0  # no overlap at all

    requested_families = requested_families or infer_families(requested_normalized, knowledge=knowledge)
    product_family = detect_product_family(product, knowledge=knowledge)
    if requested_families:
        if product_family in requested_families:
            score += 3.0
        else:
            score -= 8.0

    score += _score_dimension_alignment(product, requested_dimensions or {})

    return max(0.0, min(10.0, score))


# High-confidence threshold: product is auto-selected as resolved
_SCORE_HIGH = 5.0
# Plausible threshold: product is ambiguous (needs clarification)
_SCORE_LOW = 2.0

# ---------------------------------------------------------------------------
# Synonym / alias expansion
# ---------------------------------------------------------------------------

def _build_search_terms(normalized: str, knowledge: Optional[Dict[str, Any]] = None) -> List[str]:
    normalized = normalize_live_language(normalized, knowledge=knowledge)
    terms: List[str] = []
    for entry in _synonym_entries(knowledge):
        alias_bucket = [entry.get("canonical", "")] + list(entry.get("aliases") or []) + list(entry.get("misspellings") or [])
        if any(alias and _normalize(alias) in normalized for alias in alias_bucket):
            canonical = str(entry.get("canonical", "")).strip()
            if canonical and canonical not in terms:
                terms.append(canonical)
            for alias in alias_bucket:
                clean = _normalize(str(alias).strip())
                if clean and clean not in terms:
                    terms.append(clean)
    for family in infer_families(normalized, knowledge=knowledge):
        if family not in terms:
            terms.append(family)
    if normalized not in terms:
        terms.append(normalized)
    return terms


def _needs_variant_clarification(normalized: str, knowledge: Optional[Dict[str, Any]] = None) -> bool:
    families = infer_families(normalize_live_language(normalized, knowledge=knowledge), knowledge=knowledge)
    family = families[0] if families else None
    blocked, _, _ = is_autopick_blocked(family, extract_dimensions(normalized, get_family_rule(family, knowledge)), knowledge=knowledge)
    return blocked


# ---------------------------------------------------------------------------
# Complementary rules (rule-based, catalog-grounded only)
# ---------------------------------------------------------------------------
# Keys are item keywords; values are catalog search terms to try.
# A suggestion only appears if the complementary product is actually in stock.

def get_complementary_suggestions(
    resolved_items: List[QuoteItem], logic: Any, knowledge: Optional[Dict[str, Any]] = None
) -> List[str]:
    """
    Return a short list of catalog-verified complementary item names.
    Only includes items NOT already in the quote.
    """
    already_normalized = {it.get("normalized", "").lower() for it in resolved_items}
    suggestions: List[str] = []

    for item in resolved_items:
        if item["status"] != "resolved":
            continue
        norm = item.get("normalized", "")
        for keyword, rule in _complementary_rules(knowledge).items():
            if keyword not in norm:
                continue
            missing_dimensions = item.get("missing_dimensions") or []
            if any(dim in missing_dimensions for dim in (rule.get("blocked_when_missing") or [])):
                continue
            required_status = str(rule.get("required_source_status", "resolved")).strip()
            if required_status and item.get("status") != required_status:
                continue
            comp_terms = list(rule.get("targets") or [])
            max_suggestions = int(rule.get("max_suggestions", 3) or 3)
            for term in comp_terms:
                # Skip if already in quote
                if any(term in n for n in already_normalized):
                    continue
                # Verify catalog actually has it in stock
                result = logic.buscar_stock(term)
                if result.get("status") == "found":
                    prod = result["products"][0]
                    name = prod.get("model") or prod.get("name") or term
                    if name not in suggestions:
                        suggestions.append(name)
            if suggestions:
                return suggestions[:max_suggestions]
    return suggestions[:3]  # cap at 3


def get_cross_sell_suggestions(
    resolved_items: List[QuoteItem],
    logic: Any,
    cross_sell_rules: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Return catalog-verified cross-sell suggestions based on profile cross_sell_rules.

    For each resolved item, checks its product category against cross_sell_rules
    from profile.yaml. If a matching rule exists, searches the catalog for one
    representative product from each recommended category not already in the quote.
    Returns at most 2 suggestions total to avoid over-selling.
    """
    if not cross_sell_rules:
        return []

    already_categories = set()
    already_normalized = {it.get("normalized", "").lower() for it in resolved_items}

    # Collect categories already in the quote
    for item in resolved_items:
        products = item.get("products") or []
        for prod in products[:1]:
            cat = prod.get("category", "")
            if cat:
                already_categories.add(cat)

    suggestions: List[str] = []

    for item in resolved_items:
        if item.get("status") != "resolved":
            continue
        products = item.get("products") or []
        if not products:
            continue
        source_category = products[0].get("category", "")
        if not source_category:
            continue

        # Find matching cross-sell rule
        rule = next(
            (r for r in cross_sell_rules if r.get("source_category") == source_category),
            None,
        )
        if not rule:
            continue

        for rec_category in (rule.get("recommend_categories") or []):
            if rec_category in already_categories:
                continue
            # Find one representative product in this category from the catalog
            try:
                catalog_items = logic.db.find_by_category(rec_category)
            except Exception:
                continue
            if not catalog_items:
                continue
            # Pick the cheapest in-stock item from that category
            in_stock = [p for p in catalog_items if int(p.get("quantity", 0)) > 0]
            candidates = in_stock or catalog_items
            if not candidates:
                continue
            rep = min(candidates, key=lambda p: _parse_price(p) or float("inf"))
            name = rep.get("model") or rep.get("name") or rec_category
            if name and not any(name.lower() in n for n in already_normalized) and name not in suggestions:
                suggestions.append(name)
                already_categories.add(rec_category)  # don't suggest same category twice
            if len(suggestions) >= 2:
                return suggestions

    return suggestions


# ---------------------------------------------------------------------------
# Filler / stop words
# ---------------------------------------------------------------------------

_FILLER_RE = re.compile(
    r"^(?:quiero|necesito|busco|dame|pasame|paseme|"
    r"ten[eé]s|tienen|tene[sn]|"
    r"presupuesto\s+para|presupuesto|me\s+das|podes\s+darme)\s+",
    re.IGNORECASE,
)

_FILLER_WORDS = frozenset({
    "quiero", "necesito", "busco", "dame", "pasame", "paseme",
    "presupuesto", "para", "me", "que", "de", "del",
    "la", "el", "los", "las",
})

# ---------------------------------------------------------------------------
# Quantity extraction
# ---------------------------------------------------------------------------

_WORD_NUMBERS: Dict[str, int] = {
    "un": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

_QTY_RE = re.compile(
    r"^(?P<qty>\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
    r"(?P<unit>lata|latas|rollo|rollos|caja|cajas|metros?|m|bolsa|bolsas|kg|kilo|kilos|par|pares|u)?\s*"
    r"(?:de\s+)?(?P<rest>.+)$",
    re.IGNORECASE,
)


def _extract_qty_and_item(raw: str) -> Tuple[int, bool, Optional[str], str]:
    m = _QTY_RE.match(raw.strip())
    if not m:
        return 1, False, None, raw.strip()
    qty_str = m.group("qty").lower()
    qty = _WORD_NUMBERS.get(qty_str) or int(qty_str)
    unit = m.group("unit") or None
    item_text = m.group("rest").strip()
    if not item_text:
        return 1, False, None, raw.strip()
    return qty, True, unit, item_text


# ---------------------------------------------------------------------------
# Item splitting (parser)
# ---------------------------------------------------------------------------

def parse_quote_items(message: str) -> List[Dict[str, Any]]:
    """Split a multi-item message into parsed item dicts."""
    cleaned = _FILLER_RE.sub("", message.strip())
    normalized_full = _normalize(cleaned)
    parts = re.split(r"\s*(?:,|\by\b|\be\b|\+|/)\s*", normalized_full, flags=re.IGNORECASE)

    items: List[Dict[str, Any]] = []
    seen: set = set()

    for part in parts:
        token = part.strip(" .:;-")
        words = token.split()
        meaningful = [w for w in words if w not in _FILLER_WORDS]
        if not meaningful or len(token) < 2:
            continue
        if token in seen:
            continue
        seen.add(token)

        qty, qty_explicit, unit_hint, item_text = _extract_qty_and_item(token)
        items.append({
            "raw":          token,
            "normalized":   item_text.strip(),
            "qty":          qty,
            "qty_explicit": qty_explicit,
            "unit_hint":    unit_hint,
            "line_id":      uuid.uuid4().hex[:8],
        })

    return items


# ---------------------------------------------------------------------------
# Per-item resolution  (STRICT scored resolver)
# ---------------------------------------------------------------------------

def resolve_quote_item(parsed: Dict[str, Any], logic: Any, knowledge: Optional[Dict[str, Any]] = None) -> QuoteItem:
    """
    Resolve a single parsed item dict against the catalog using strict scoring.

    Steps
    -----
    1. Build ordered search terms (synonym-expanded).
    2. For each term, call buscar_stock and collect candidates.
    3. Score each candidate (word overlap + category-family gate).
    4. High-confidence score → resolved (with pack/unit check).
    5. Plausible score → ambiguous.
    6. Category fallback if nothing scored well → ambiguous (filtered).
    7. Nothing → unresolved.
    """
    raw        = parsed["raw"]
    normalized = normalize_live_language(parsed["normalized"], knowledge=knowledge)
    qty        = parsed["qty"]
    qty_explicit = parsed["qty_explicit"]
    unit_hint  = parsed.get("unit_hint")
    line_id    = parsed.get("line_id") or uuid.uuid4().hex[:8]

    families = infer_families(normalized, knowledge=knowledge)
    family = families[0] if families else None
    family_rule = get_family_rule(family, knowledge)
    dims = extract_dimensions(normalized, family_rule=family_rule)

    blocked_hit = None
    text_tokens = [tok for tok in re.findall(r"[a-z0-9/]+", normalized) if tok not in _FILLER_WORDS]
    for term in _blocked_terms(knowledge):
        blocked_term = _normalize(str(term.get("term", "")))
        if not blocked_term:
            continue
        contains_term = blocked_term == normalized or re.search(rf"\b{re.escape(blocked_term)}\b", normalized) is not None
        if not contains_term:
            continue
        used_alone = bool(term.get("block_if_used_alone")) and text_tokens == [blocked_term]
        matches_full = blocked_term == normalized
        missing_dims = [dim for dim in (term.get("block_if_no_dimensions") or []) if dim not in dims]
        if matches_full or used_alone or missing_dims:
            blocked_hit = term
            break
    if blocked_hit:
        item = {
            "line_id":      line_id,
            "original":     raw,
            "normalized":   normalized,
            "qty":          qty,
            "qty_explicit": qty_explicit,
            "unit_hint":    unit_hint,
            "status":       "blocked_by_missing_info",
            "products":     [],
            "unit_price":   None,
            "subtotal":     None,
            "pack_note":    None,
            "clarification": blocked_hit.get("redirect_prompt") or build_clarification_prompt(family, [], normalized, knowledge=knowledge),
            "notes":        blocked_hit.get("reason") or "Termino demasiado amplio para cotizar.",
            "complementary": [],
            "family":       blocked_hit.get("family_hint") or family,
            "missing_dimensions": blocked_hit.get("block_if_no_dimensions") or [],
            "issue_type":   "blocked_term",
            "dimensions":   dims,
            "selected_via_substitute": False,
        }
        _log_unresolved(item, reason=f"blocked_term term={normalized}")
        return item

    autopick_blocked, missing_dimensions, missing_reason = is_autopick_blocked(family, dims, knowledge=knowledge)

    search_terms = _build_search_terms(normalized, knowledge=knowledge)

    # --- Phase 2: family-aware scored stock search ---
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for term in search_terms:
        result = logic.buscar_stock(term)
        if result.get("status") != "found":
            continue
        for prod in result.get("products", [])[:5]:
            sc = max(
                _score_product(prod, normalized, requested_families=families, requested_dimensions=dims, knowledge=knowledge),
                _score_product(prod, term, requested_families=families, requested_dimensions=dims, knowledge=knowledge),
            )
            if sc >= _SCORE_LOW:
                scored.append((sc, prod))

    # Deduplicate by SKU, keeping highest score
    seen_skus: Dict[str, float] = {}
    deduped: List[Tuple[float, Dict[str, Any]]] = []
    for sc, prod in scored:
        sku = prod.get("sku", "")
        if sku not in seen_skus or sc > seen_skus[sku]:
            seen_skus[sku] = sc
            deduped = [(s, p) for s, p in deduped if p.get("sku") != sku]
            deduped.append((sc, prod))

    deduped.sort(key=lambda x: x[0], reverse=True)

    if deduped:
        best_score, best_product = deduped[0]
        if family in {"tarugo", "taco"} and any(term in normalized for term in ("fisher", "fischer")):
            autopick_blocked = False
            missing_dimensions = []
        if family in {"silicona", "teflon"} and best_score >= _SCORE_HIGH:
            autopick_blocked = False
            missing_dimensions = []
        safe_alts = filter_safe_alternatives(
            family,
            [
                p for sc, p in deduped[1:6]
                if sc >= _SCORE_LOW and p.get("sku") != best_product.get("sku")
            ],
            dims,
            knowledge=knowledge,
        )

        if best_score >= _SCORE_HIGH and not autopick_blocked:
            same_family_close = [
                p for sc, p in deduped[1:3]
                if sc >= (best_score - 0.4) and detect_product_family(p, knowledge=knowledge) == family
            ]
            if same_family_close:
                unit_price, _ = _compute_subtotal(best_product, qty)
                item = {
                    "line_id":      line_id,
                    "original":     raw,
                    "normalized":   normalized,
                    "qty":          qty,
                    "qty_explicit": qty_explicit,
                    "unit_hint":    unit_hint,
                    "status":       "ambiguous",
                    "products":     [best_product] + safe_alts[:2],
                    "unit_price":   unit_price,
                    "subtotal":     None,
                    "pack_note":    None,
                    "clarification": _ambiguity_clarification(normalized, family or best_product.get("category", ""), missing_dimensions, knowledge=knowledge),
                    "notes":        "Hay más de una variante plausible dentro de la misma familia.",
                    "complementary": [],
                    "family":       family,
                    "missing_dimensions": missing_dimensions,
                    "issue_type":   "variant_ambiguity",
                    "dimensions":   dims,
                    "selected_via_substitute": False,
                }
                _log_unresolved(item, reason=f"variant_ambiguity score={best_score:.2f}")
                return item

            # High confidence — check pack semantics
            pack = _pack_note(best_product, qty)
            unit_price, subtotal = _compute_subtotal(best_product, qty)
            if pack:
                # Pack/unit mismatch — cannot safely compute subtotal
                subtotal = None
            return {
                "line_id":      line_id,
                "original":     raw,
                "normalized":   normalized,
                "qty":          qty,
                "qty_explicit": qty_explicit,
                "unit_hint":    unit_hint,
                "status":       "resolved",
                "products":     [best_product] + safe_alts[:2],
                "unit_price":   unit_price,
                "subtotal":     subtotal,
                "pack_note":    pack,
                "clarification": None,
                "notes":        None,
                "complementary": [],
                "family":       family or detect_product_family(best_product, knowledge=knowledge),
                "missing_dimensions": [],
                "issue_type":   None,
                "dimensions":   dims,
                "selected_via_substitute": False,
            }

        if autopick_blocked:
            item = {
                "line_id":      line_id,
                "original":     raw,
                "normalized":   normalized,
                "qty":          qty,
                "qty_explicit": qty_explicit,
                "unit_hint":    unit_hint,
                "status":       "blocked_by_missing_info",
                "products":     [best_product] + safe_alts[:2],
                "unit_price":   None,
                "subtotal":     None,
                "pack_note":    None,
                "clarification": _ambiguity_clarification(normalized, family or best_product.get("category", ""), missing_dimensions, knowledge=knowledge),
                "notes":        "Falta una dimensión clave para elegir una variante segura.",
                "complementary": [],
                "family":       family,
                "missing_dimensions": missing_dimensions,
                "issue_type":   "missing_dimensions",
                "dimensions":   dims,
                "selected_via_substitute": False,
            }
            _log_unresolved(item, reason=f"blocked_missing_dimensions family={family or 'unknown'} reason={missing_reason}")
            return item

        # Plausible — ambiguous
        unit_price, _ = _compute_subtotal(best_product, qty)
        item = {
            "line_id":      line_id,
            "original":     raw,
            "normalized":   normalized,
            "qty":          qty,
            "qty_explicit": qty_explicit,
            "unit_hint":    unit_hint,
            "status":       "ambiguous",
            "products":     [best_product] + safe_alts[:2],
            "unit_price":   unit_price,
            "subtotal":     None,           # no subtotal for ambiguous
            "pack_note":    None,
            "clarification": _ambiguity_clarification(normalized, family or best_product.get("category", ""), missing_dimensions, knowledge=knowledge),
            "notes":        "Encontre opciones relacionadas. Confirma el tipo exacto.",
            "complementary": [],
            "family":       family or detect_product_family(best_product, knowledge=knowledge),
            "missing_dimensions": missing_dimensions,
            "issue_type":   "weak_match",
            "dimensions":   dims,
            "selected_via_substitute": False,
        }
        _log_unresolved(item, reason=f"weak_match score={best_score:.2f}")
        return item

    # --- Phase 2: filtered category fallback ---
    category = _detect_category(normalized, knowledge=knowledge)
    if category:
        cat_result = logic.buscar_por_categoria(category)
        if cat_result.get("status") == "found":
            # Filter to only products that have any significant-word overlap
            cat_prods = cat_result.get("products", [])
            filtered = [
                p for p in cat_prods
                if _score_product(
                    p,
                    normalized,
                    requested_families=families,
                    requested_dimensions=dims,
                    knowledge=knowledge,
                ) >= _SCORE_LOW
            ]
            if filtered:
                safe_filtered = filter_safe_alternatives(family, filtered, dims, knowledge=knowledge)
                item = {
                    "line_id":      line_id,
                    "original":     raw,
                    "normalized":   normalized,
                    "qty":          qty,
                    "qty_explicit": qty_explicit,
                    "unit_hint":    unit_hint,
                    "status":       "blocked_by_missing_info" if autopick_blocked else "ambiguous",
                    "products":     safe_filtered[:2] or filtered[:2],
                    "unit_price":   None,
                    "subtotal":     None,
                    "pack_note":    None,
                    "clarification": _ambiguity_clarification(normalized, family or category, missing_dimensions, knowledge=knowledge),
                    "notes":        f"Opciones en categoria {category}",
                    "complementary": [],
                    "family":       family,
                    "missing_dimensions": missing_dimensions,
                    "issue_type":   "category_fallback",
                    "dimensions":   dims,
                    "selected_via_substitute": False,
                }
                _log_unresolved(item, reason=f"category_fallback category={category}")
                return item

    if family and autopick_blocked:
        item = {
            "line_id":      line_id,
            "original":     raw,
            "normalized":   normalized,
            "qty":          qty,
            "qty_explicit": qty_explicit,
            "unit_hint":    unit_hint,
            "status":       "blocked_by_missing_info",
            "products":     [],
            "unit_price":   None,
            "subtotal":     None,
            "pack_note":    None,
            "clarification": _ambiguity_clarification(normalized, family, missing_dimensions, knowledge=knowledge),
            "notes":        "Conozco la familia, pero falta una dimensión clave para cotizar bien.",
            "complementary": [],
            "family":       family,
            "missing_dimensions": missing_dimensions,
            "issue_type":   "missing_dimensions",
            "dimensions":   dims,
            "selected_via_substitute": False,
        }
        _log_unresolved(item, reason=f"missing_dimensions family={family}")
        return item

    # --- Unresolved ---
    item = {
        "line_id":      line_id,
        "original":     raw,
        "normalized":   normalized,
        "qty":          qty,
        "qty_explicit": qty_explicit,
        "unit_hint":    unit_hint,
        "status":       "unresolved",
        "products":     [],
        "unit_price":   None,
        "subtotal":     None,
        "pack_note":    None,
        "clarification": _ambiguity_clarification(normalized, family or "", missing_dimensions, knowledge=knowledge),
        "notes":        "No encontre una coincidencia clara en el catalogo.",
        "complementary": [],
        "family":       family,
        "missing_dimensions": missing_dimensions,
        "issue_type":   "catalog_gap" if family else "unknown_term",
        "dimensions":   dims,
        "selected_via_substitute": False,
    }
    _log_unresolved(item, reason="no_match_after_scored_search")
    return item


# ---------------------------------------------------------------------------
# Ambiguity clarification prompts
# ---------------------------------------------------------------------------

def _ambiguity_clarification(
    normalized: str,
    category_or_family: str,
    missing_dimensions: Optional[List[str]] = None,
    knowledge: Optional[Dict[str, Any]] = None,
) -> str:
    family = category_or_family if category_or_family in _family_rules(knowledge) else None
    if not family:
        inferred = infer_families(normalized, knowledge=knowledge)
        family = inferred[0] if inferred else None
    return build_clarification_prompt(family, missing_dimensions or [], normalized, knowledge=knowledge)


# ---------------------------------------------------------------------------
# Price / subtotal helpers
# ---------------------------------------------------------------------------

def _parse_price(product: Dict[str, Any]) -> Optional[float]:
    for field in ("price_ars", "price", "precio"):
        val = product.get(field)
        if val is not None:
            try:
                return float(str(val).replace("$", "").replace(".", "").replace(",", ".").strip())
            except (ValueError, TypeError):
                pass
    return None


def _compute_subtotal(
    product: Optional[Dict[str, Any]], qty: int
) -> Tuple[Optional[float], Optional[float]]:
    if not product:
        return None, None
    price = _parse_price(product)
    if price is None:
        return None, None
    return price, round(price * qty, 2)


def _format_price(value: Optional[float]) -> str:
    if value is None:
        return "precio a confirmar"
    if value == int(value):
        return f"${int(value):,}".replace(",", ".")
    return f"${value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Acceptance detection
# ---------------------------------------------------------------------------

def _match_known_phrase(message: str, phrases: List[str]) -> bool:
    norm = _normalize(message.strip())
    return any(_normalize(phrase) in norm for phrase in phrases if phrase)


def looks_like_acceptance(message: str, knowledge: Optional[Dict[str, Any]] = None) -> bool:
    """Return True if the message is accepting/confirming the current quote."""
    patterns = _acceptance_patterns(knowledge)
    return _match_known_phrase(message, patterns.get("accept_phrases", []))


def generate_acceptance_response(active_quote: List[QuoteItem], knowledge: Optional[Dict[str, Any]] = None) -> str:
    """
    Return the acceptance reply.
    Only block acceptance when items have missing critical info (blocked_by_missing_info).
    Ambiguous/unresolved items are passed through — the ops team resolves them during review.
    """
    pending = [it for it in active_quote if it["status"] in ("blocked_by_missing_info",)]
    if pending:
        names = [it["original"].capitalize() for it in pending]
        block = "\n".join(f"  - {n}" for n in names)
        return (
            "Antes de confirmar hay ítems que necesitan aclaración:\n"
            f"{block}\n\n"
            "Cuando los definamos, lo paso a revisión del equipo para seguimiento."
        )

    return (
        "✓ *Recibimos tu pedido para revisión.*\n\n"
        "Nuestro equipo va a revisar disponibilidad final, presentación y entrega.\n"
        "Te vamos a contactar para continuar el seguimiento.\n\n"
        "Todavía no es una venta confirmada."
    )


# ---------------------------------------------------------------------------
# Broad-request reply
# ---------------------------------------------------------------------------

BROAD_REQUEST_REPLY = (
    "Para armarte un presupuesto util y no hacerte comprar de mas, necesito los materiales o rubros que buscas.\n\n"
    "Podes pasarme la lista completa o decirme que rubros necesitas:\n"
    "  caños, conexiones, selladores, fijaciones, sanitarios,\n"
    "  grifería, pintura, herramientas, electricidad, u otros.\n\n"
    "Si queres, lo armamos por rubros y te lo ordeno para avanzar mas rapido."
)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

_POWER_TOOL_FAMILIES = {"taladro", "amoladora", "atornillador"}
_PRECISION_FAMILIES = {"tornillo", "tarugo", "taco", "fijacion", "mecha", "broca"}
_USE_CASE_FAMILIES = {"silicona", "sellador", "teflon", "cano", "conexion"}


def _resolved_family_set(items: List[QuoteItem]) -> set[str]:
    return {
        str(item.get("family") or "").strip().lower()
        for item in items
        if str(item.get("family") or "").strip()
    }


def _pending_quote_items(items: List[QuoteItem]) -> List[QuoteItem]:
    return [
        item
        for item in items
        if item.get("status") in {"ambiguous", "unresolved", "blocked_by_missing_info"}
    ]


def _quote_intro_line(items: List[QuoteItem]) -> str:
    pending = _pending_quote_items(items)
    if not pending and len(items) == 1:
        return "Te arme una opcion base para avanzar sin vueltas."
    if not pending:
        return "Te arme una base bastante cerrada para que ya tengas numero y opcion concreta."
    if any(item.get("status") == "resolved" for item in items):
        return "Te arme una primera base y te marco donde conviene afinar para no cotizarte mal."
    return "Te ordene el pedido y te marco lo que falta definir para recomendarte bien."


def _quote_next_step_line(items: List[QuoteItem]) -> str:
    pending = _pending_quote_items(items)
    families = _resolved_family_set(items)
    if pending:
        if families & _PRECISION_FAMILIES:
            return "Si me confirmas superficie, medida o material, te digo cual conviene y te lo dejo fino."
        if families & _USE_CASE_FAMILIES:
            return "Si me decis uso y medida, te confirmo la opcion correcta y te lo cierro bien."
        return "Si me respondes eso, te lo dejo afinado enseguida."
    if families & _POWER_TOOL_FAMILIES:
        return "Si queres, te digo si esta base conviene mas para hogar, obra o uso seguido."
    return "Si queres, te lo dejo asi o lo ajusto por precio, uso o marca."


def generate_quote_response(
    resolved_items: List[QuoteItem],
    complementary: Optional[List[str]] = None,
    header: str = "*Presupuesto:*",
) -> str:
    """Compact quote format: one line per item, clear total at the bottom."""
    lines: List[str] = [header, ""]
    pending_questions: List[str] = []
    grand_total: float = 0.0

    for item in resolved_items:
        status      = item["status"]
        original    = item["original"].capitalize()
        qty         = int(item.get("qty") or 1)
        unit_price  = item.get("unit_price")
        subtotal    = item.get("subtotal")
        products    = item.get("products") or []
        pack_note   = item.get("pack_note")
        clarif      = item.get("clarification") or item.get("notes") or ""

        if status == "resolved" and products:
            best = products[0]
            name = best.get("model") or best.get("name") or best.get("sku", "Producto")
            if subtotal is not None and not pack_note:
                price_part = f"{_format_price(unit_price)}/u → *{_format_price(subtotal)}*"
                grand_total += subtotal
            elif unit_price is not None:
                price_part = f"*{_format_price(unit_price)}*"
                grand_total += unit_price * qty
            else:
                price_part = "precio a confirmar"
            lines.append(f"✅ {qty} × {name} — {price_part}")
            if pack_note:
                lines.append(f"   ↳ ⚠️ {pack_note}")
            # Show one alternative if available
            if len(products) > 1:
                alt = products[1]
                alt_name = alt.get("model") or alt.get("name") or ""
                alt_price = _parse_price(alt)
                if alt_name and alt_name != name:
                    lines.append(
                        f"   ↳ También: {alt_name}"
                        + (f" · {_format_price(alt_price)}" if alt_price else "")
                    )

        elif status == "ambiguous" and products:
            lines.append(f"❓ {original} — ¿cuál de estos?")
            for j, p in enumerate(products[:3], start=1):
                pname = p.get("model") or p.get("name") or ""
                pprice = _parse_price(p)
                lines.append(
                    f"   {chr(64 + j)}) {pname}"
                    + (f" · {_format_price(pprice)}" if pprice else "")
                )
            if clarif:
                pending_questions.append(f"• {original}: {clarif}")

        elif status == "blocked_by_missing_info":
            detail = clarif or "necesito más detalle"
            lines.append(f"⚠️ {original} — {detail}")
            if clarif:
                pending_questions.append(f"• {original}: {clarif}")

        else:  # unresolved
            lines.append(f"❌ {original} — no lo encontré en el catálogo")

    # Separator + total
    lines.append("")
    lines.append("──────────────────")
    resolved_count = sum(1 for it in resolved_items if it["status"] == "resolved")
    total_count    = len(resolved_items)
    if grand_total > 0:
        label = (
            f"*Total parcial ({resolved_count}/{total_count})*"
            if resolved_count < total_count
            else "*Total*"
        )
        lines.append(f"{label}: {_format_price(grand_total)}")

    # Pending questions
    if pending_questions:
        lines.append("")
        lines.append("Necesito confirmar:")
        lines.extend(pending_questions)
        lines.append("")
        lines.append("Respondé y te actualizo el total. 🛠️")
    elif grand_total > 0:
        lines.append("")
        lines.append("Válido 24hs · ¿Confirmás?")

    # Complementary suggestions
    if complementary:
        lines.append("")
        lines.append("También suelen llevar:")
        for c in complementary:
            lines.append(f"  • {c}")

    return "\n".join(lines).strip()


def _resolved_snapshot_lines(open_items: List[QuoteItem], *, limit: int = 3) -> List[str]:
    snapshot: List[str] = []
    for item in open_items:
        if item.get("status") != "resolved":
            continue
        products = item.get("products") or []
        if not products:
            continue
        product = products[0]
        name = product.get("model") or product.get("name") or product.get("sku", "Producto")
        qty = int(item.get("qty") or 1)
        qty_prefix = f"{qty} x " if qty > 1 else ""
        snapshot.append(f"- **{qty_prefix}{name}** | {_format_price(item.get('subtotal') or item.get('unit_price'))}")
        if len(snapshot) >= limit:
            break
    return snapshot


def _focus_resolved_item(open_items: List[QuoteItem]) -> Optional[QuoteItem]:
    resolved = [
        item for item in open_items
        if item.get("status") == "resolved" and (item.get("products") or [])
    ]
    return resolved[-1] if resolved else None


def _cheapest_alternative(item: QuoteItem) -> Optional[Dict[str, Any]]:
    products = item.get("products") or []
    if len(products) <= 1:
        return None
    primary_name = products[0].get("model") or products[0].get("name") or products[0].get("sku", "")
    candidates = []
    for product in products[1:]:
        name = product.get("model") or product.get("name") or product.get("sku", "")
        if name and name != primary_name:
            candidates.append(product)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda product: _parse_price(product) if _parse_price(product) is not None else float("inf"),
    )


def _sales_use_phrase(sales_preferences: Optional[Dict[str, Any]] = None) -> str:
    prefs = sales_preferences or {}
    use_case = str(prefs.get("use_case") or "").strip().lower()
    mapping = {
        "hogar": "para hogar",
        "obra": "para obra",
        "taller": "para taller",
        "profesional": "para uso profesional",
        "mantenimiento": "para mantenimiento",
    }
    return mapping.get(use_case, "")


def _budget_fits(price: Optional[float], budget_cap: Optional[int]) -> bool:
    if budget_cap is None or price is None:
        return True
    return price <= budget_cap


def _format_budget(budget_cap: int) -> str:
    return f"${budget_cap:,}".replace(",", ".")


def generate_sales_guidance_response(
    open_items: List[QuoteItem],
    *,
    mode: str,
    sales_preferences: Optional[Dict[str, Any]] = None,
) -> str:
    focus_item = _focus_resolved_item(open_items)
    snapshot = _resolved_snapshot_lines(open_items)
    snapshot_count = len(snapshot)
    if not focus_item or not snapshot:
        if mode == "price":
            return (
                "Entiendo. Para cuidar el numero sin errarle, decime en que item queres bajar costo "
                "o pasame un presupuesto tope y te lo rearmo."
            )
        if mode == "comparison":
            return (
                "Para compararlo bien necesito tener una opcion concreta arriba de la mesa. "
                "Decime que item queres revisar y si priorizas precio, uso o marca."
            )
        return (
            "Te puedo recomendar mejor si primero dejamos una opcion concreta en el presupuesto. "
            "Decime que producto queres revisar y lo vemos."
        )

    prefs = sales_preferences or {}
    budget_cap: Optional[int] = prefs.get("budget_cap")
    decision_style: str = str(prefs.get("decision_style") or "").strip().lower()

    primary = (focus_item.get("products") or [None])[0] or {}
    primary_name = primary.get("model") or primary.get("name") or primary.get("sku", "Producto")
    primary_price_val = _parse_price(primary) if primary else focus_item.get("unit_price")
    primary_price = _format_price(primary_price_val)
    alt = _cheapest_alternative(focus_item)
    alt_name = alt.get("model") or alt.get("name") or alt.get("sku", "") if alt else ""
    alt_price_val = _parse_price(alt) if alt else None
    alt_price = _format_price(alt_price_val) if alt else ""
    use_phrase = _sales_use_phrase(sales_preferences)

    if mode == "price":
        lines = [
            "Entiendo, vamos a cuidar el numero sin mandarte a algo que despues no te sirva.",
            "",
            "Hoy tenes armado esto:",
            *snapshot,
            "",
        ]
        if budget_cap is not None:
            lines.append(f"Con un tope de {_format_budget(budget_cap)}, te rearmo la base sin perder de vista el uso.")
        if snapshot_count > 1:
            if budget_cap is None:
                lines.append(
                    "Si queres bajar presupuesto, decime en cual item queres ajustar primero y te digo donde tiene mas sentido ahorrar."
                )
                lines.append(
                    "Tambien me sirve si me pasas un presupuesto tope y te rearmo la base sin perder de vista el uso."
                )
            return "\n".join(lines).strip()
        if alt and alt_name:
            alt_fits = _budget_fits(alt_price_val, budget_cap)
            primary_fits = _budget_fits(primary_price_val, budget_cap)
            if budget_cap is not None and alt_fits and not primary_fits:
                lines.append(
                    f"Con tu tope de {_format_budget(budget_cap)}, la opcion que entra es **{alt_name}** ({alt_price})."
                )
                lines.append("Si queres, te actualizo el presupuesto con esa variante.")
            else:
                lines.append(
                    f"Si queres bajar presupuesto, la primera variante a revisar seria **{alt_name}** ({alt_price}) "
                    f"en lugar de **{primary_name}** ({primary_price})."
                )
                lines.append("Si queres, te actualizo el presupuesto con esa variante.")
        else:
            lines.append(
                f"Sobre **{primary_name}** ({primary_price}), hoy no te voy a inventar una alternativa mas barata si no la tengo clara."
            )
            if budget_cap is None:
                lines.append(
                    "Si queres, decime si priorizas precio, rendimiento o marca, o pasame un presupuesto tope, y te lo ajusto."
                )
        return "\n".join(lines).strip()

    if mode == "comparison":
        lines = [
            "Hoy lo compararia asi:",
            "",
            *snapshot,
            "",
        ]
        if snapshot_count > 1:
            lines.append(
                "Si queres comparar en serio, decime que item queres revisar y si priorizas precio, duracion o marca."
            )
            return "\n".join(lines).strip()
        if alt and alt_name:
            if decision_style == "price":
                lines.append(f"- Priorizando precio: **{alt_name}** ({alt_price})")
                lines.append(f"- Si el rendimiento es lo primero: **{primary_name}** ({primary_price})")
            elif decision_style == "quality":
                lines.append(f"- Priorizando rendimiento: **{primary_name}** ({primary_price})")
                lines.append(f"- Si queres cuidar mas el numero: **{alt_name}** ({alt_price})")
            else:
                lines.append(f"- Para mirar una variante mas accesible: **{alt_name}** ({alt_price})")
                lines.append(f"- Para seguir con la base ya armada: **{primary_name}** ({primary_price})")
            if budget_cap is not None:
                fits = _budget_fits(alt_price_val, budget_cap) or _budget_fits(primary_price_val, budget_cap)
                if fits:
                    winner = alt_name if _budget_fits(alt_price_val, budget_cap) else primary_name
                    lines.append(f"Con tu tope de {_format_budget(budget_cap)}, la que entra es **{winner}**.")
            lines.append("Si queres, te actualizo el presupuesto con la opcion que elijas.")
        else:
            lines.append(
                "Hoy no tengo una segunda variante clara dentro de ese mismo item para compararte sin inventar."
            )
            lines.append(
                "Si queres comparar en serio, decime si priorizas precio, duracion o marca y te busco una alternativa real."
            )
        return "\n".join(lines).strip()

    # mode == "recommendation"
    lines = [
        "Por lo que me venis contando, yo arrancaria con esta base:",
        "",
        *snapshot,
        "",
    ]
    if snapshot_count > 1:
        if use_phrase:
            lines.append(f"Como base, el conjunto me cierra {use_phrase}.")
        else:
            lines.append("Como base, el conjunto esta bien armado para avanzar sin vueltas.")
        if budget_cap is not None:
            lines.append(f"Si queres ajustarlo a tu tope de {_format_budget(budget_cap)}, decime cual item querés revisar.")
        else:
            lines.append(
                "Si me decis que parte del trabajo queres priorizar, te digo donde conviene gastar y donde conviene ahorrar."
            )
        return "\n".join(lines).strip()

    # Single item recommendation — apply decision_style and budget_cap
    if decision_style == "price" and alt and alt_name:
        # User prefers price → lead with the cheaper option
        lines.append(f"Si priorizas precio, arrancaria con **{alt_name}** ({alt_price}).")
        if use_phrase:
            lines.append(f"Cumple bien {use_phrase} sin pasarte de presupuesto.")
        lines.append(f"Si despues el rendimiento importa mas, **{primary_name}** ({primary_price}) es el siguiente escalon.")
    elif decision_style == "quality":
        # User prefers quality → lead with the primary (best) option
        lines.append(f"Priorizando rendimiento, yo me quedaria con **{primary_name}** ({primary_price}).")
        if use_phrase:
            lines.append(f"Para {use_phrase.replace('para ', '')} es el que mejor aguanta el uso.")
        if alt and alt_name:
            lines.append(f"Si el presupuesto aprieta, **{alt_name}** ({alt_price}) es la alternativa.")
    elif budget_cap is not None and alt and alt_name and _budget_fits(alt_price_val, budget_cap) and not _budget_fits(primary_price_val, budget_cap):
        # Has budget cap and only the alt fits → recommend the alt
        lines.append(f"Con tu tope de {_format_budget(budget_cap)}, la opcion que te recomiendo es **{alt_name}** ({alt_price}).")
        if use_phrase:
            lines.append(f"Cumple bien {use_phrase}.")
    else:
        if use_phrase:
            lines.append(f"Como punto de partida, me gusta {use_phrase}.")
        else:
            lines.append(
                f"Como base, **{primary_name}** ({primary_price}) me parece una opcion logica para avanzar sin vueltas."
            )
        if alt and alt_name:
            lines.append(f"Si queres comparar o cuidar mas el numero, tambien revisaria **{alt_name}** ({alt_price}).")
    if not use_phrase:
        lines.append("Si me decis si es para hogar, obra o uso mas seguido, te digo cual conviene mas.")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Multi-turn helpers
# ---------------------------------------------------------------------------

_RESET_PHRASES = frozenset({
    "nuevo presupuesto", "empecemos de nuevo", "empezar de nuevo",
    "borrar presupuesto", "limpiar presupuesto", "cancelar presupuesto",
    "reset", "nueva cotizacion", "empezar otra vez", "olvidate",
    "borra eso", "arranquemos otra vez", "empezamos de nuevo",
})

_ADDITIVE_RE = re.compile(
    r"^(?:agrega|agregale|suma|sumale|añadi|añadile|tambien\s+necesito|"
    r"tambien\s+quiero|agrega\s+tambien|y\s+tambien|y\s+ademas)\b",
    re.IGNORECASE,
)


def looks_like_reset(message: str, knowledge: Optional[Dict[str, Any]] = None) -> bool:
    patterns = _acceptance_patterns(knowledge)
    phrases = patterns.get("reset_phrases") or list(_RESET_PHRASES)
    return _match_known_phrase(message, phrases)


def looks_like_additive(message: str) -> bool:
    return bool(_ADDITIVE_RE.match(message.strip()))


def looks_like_clarification(message: str, open_items: List[QuoteItem]) -> bool:
    if not open_items:
        return False
    pending = [it for it in open_items if it["status"] in ("ambiguous", "unresolved", "blocked_by_missing_info")]
    if not pending:
        return False
    norm = _normalize(message.strip())
    words = norm.split()
    if len(words) > 9:
        return False
    fresh_verbs = {"quiero", "necesito", "busco", "dame", "pasame", "presupuesto"}
    if words and words[0] in fresh_verbs:
        return False
    if re.search(r"\b(y|e)\b.+\b(y|e)\b", norm):
        return False
    return True


def needs_disambiguation(message: str, open_items: List[QuoteItem]) -> Optional[str]:
    pending = [it for it in open_items if it["status"] in ("ambiguous", "unresolved", "blocked_by_missing_info")]
    if len(pending) <= 1:
        return None
    norm_msg = _normalize(message)
    for item in pending:
        item_norm = item.get("normalized", "")
        key_words = [w for w in item_norm.split() if w not in _FILLER_WORDS and len(w) > 2]
        if any(w in norm_msg for w in key_words):
            return None
    names = [it.get("original", it.get("normalized", "?")).capitalize() for it in pending[:3]]
    if len(names) == 2:
        return f"¿Eso es para {names[0]} o para {names[1]}?"
    last = names[-1]
    rest = ", ".join(names[:-1])
    return f"¿A cuál item se refiere: {rest} o {last}?"


# ---------------------------------------------------------------------------
# Distinctive tokens for targeted matching
# ---------------------------------------------------------------------------

# Words that carry discriminating signal (size, material, color, type, presentation).
# These receive a 1.5× score boost in _match_to_line.
_DISTINCTIVE_TOKENS: frozenset = frozenset({
    # sizes / specs
    "8mm", "10mm", "13mm", "6mm", "4mm", "12mm", "1/2", "3/4", "1/4",
    "280ml", "480ml", "300ml", "850w", "750w", "500w", "1200w",
    # materials
    "madera", "metal", "hormigon", "plastico", "acero", "inox", "hierro",
    # colors
    "blanca", "blanco", "negro", "negra", "roja", "rojo",
    "transparente", "color", "gris", "verde",
    # product type / presentation
    "neutra", "acida", "acetica", "acrilico", "acrilica", "sanitario", "sanitaria",
    "rollo", "caja", "lata", "bolsa",
    "percutor", "angular", "de impacto",
    # use
    "interior", "exterior", "sanitario", "electrico",
})
_DISTINCTIVE_BOOST = 1.5
_MARGIN_MIN = 0.2   # below this delta, disambiguation is required
_EXACT_DISTINCTIVE_BONUS = 0.45
_LINE_MATCH_IGNORE = _FILLER_WORDS | _SCORE_STOP_WORDS


def _word_weight(word: str) -> float:
    """Return scoring weight for a word (distinctive tokens score higher)."""
    return _DISTINCTIVE_BOOST if word in _DISTINCTIVE_TOKENS else 1.0


def _match_words(text: str) -> set[str]:
    """
    Token set used only for line targeting.

    Unlike _significant_words(), this keeps exact distinctive tokens even when
    they would normally be treated as broad words elsewhere (for example color
    or use markers like "blanca", "sanitaria", "interior").
    """
    tokens = re.findall(r"[a-z0-9/]+", _normalize(text))
    keep: set[str] = set()
    for token in tokens:
        if token in _DISTINCTIVE_TOKENS:
            keep.add(token)
            continue
        if token in _LINE_MATCH_IGNORE:
            continue
        if len(token) >= 3:
            keep.add(token)
    return keep


def _match_to_line(
    message: str,
    lines: List[QuoteItem],
    min_overlap: float = 0.3,
    min_margin: float = _MARGIN_MIN,
) -> Optional[QuoteItem]:
    """
    Return the best-matching QuoteItem.

    Scoring
    -------
    * Significant-word overlap between message and each line's text.
    * Distinctive tokens (size, material, color, etc.) receive 1.5× weight.
    * If the margin between the best and second-best score is < min_margin
      AND both are above the threshold, returns None so the caller can ask
      a disambiguation question instead of guessing.
    """
    norm_msg = _normalize(message)
    msg_words = _match_words(norm_msg)
    if not msg_words:
        return None

    prepared: List[Tuple[QuoteItem, set[str]]] = []
    for line in lines:
        line_text = line.get("normalized", "") + " " + line.get("original", "")
        line_words = _match_words(line_text)
        if not line_words:
            continue
        prepared.append((line, line_words))

    if not prepared:
        return None

    scored: List[tuple] = []
    all_line_words = [line_words for _, line_words in prepared]
    for idx, (line, line_words) in enumerate(prepared):
        overlap_words = msg_words & line_words

        # Weighted overlap
        weighted_overlap = sum(_word_weight(w) for w in overlap_words)
        weighted_total = sum(_word_weight(w) for w in line_words)
        score = weighted_overlap / weighted_total if weighted_total > 0 else 0.0

        distinctive_overlap = overlap_words & _DISTINCTIVE_TOKENS
        if distinctive_overlap:
            other_words = set().union(*(words for j, words in enumerate(all_line_words) if j != idx))
            unique_distinctive = [tok for tok in distinctive_overlap if tok not in other_words]
            if unique_distinctive:
                score += _EXACT_DISTINCTIVE_BONUS * len(unique_distinctive)

        scored.append((score, line))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_line = scored[0]

    if best_score < min_overlap:
        return None

    # Margin check: if two lines are nearly equally matched, refuse to guess
    if len(scored) > 1:
        second_score = scored[1][0]
        if second_score >= min_overlap and (best_score - second_score) < min_margin:
            return None  # caller should invoke needs_disambiguation

    return best_line


def apply_clarification(
    clarification_text: str,
    open_items: List[QuoteItem],
    logic: Any,
    target_line_id: Optional[str] = None,
    knowledge: Optional[Dict[str, Any]] = None,
) -> List[QuoteItem]:
    """
    Apply a clarification to the best matching pending line.

    If `target_line_id` is provided (from pending_clarification_target stored
    in session), update that specific line regardless of content matching.
    Otherwise, use _match_to_line against pending lines.
    """
    norm_clar = _normalize(clarification_text)
    clar_dims = extract_dimensions(clarification_text)
    pending = [it for it in open_items if it["status"] in ("ambiguous", "unresolved", "blocked_by_missing_info")]
    if not pending:
        return list(open_items)

    # Determine target line
    target: Optional[QuoteItem] = None
    if target_line_id:
        target = next((it for it in pending if it.get("line_id") == target_line_id), None)
    if target is None:
        target = _match_to_line(clarification_text, pending)
    if target is None and len(pending) == 1:
        target = pending[0]
    if target is None:
        return list(open_items)  # needs_disambiguation should have been called first

    target_id = target.get("line_id")
    target_norm = _normalize(target.get("normalized", ""))
    if norm_clar.startswith(target_norm):
        combined = norm_clar
    elif target_norm and target_norm in norm_clar.split():
        combined = norm_clar
    else:
        combined = f"{target_norm} {norm_clar}".strip()
    candidate = {
        "raw":          combined,
        "normalized":   combined,
        "qty":          target.get("qty", 1),
        "qty_explicit": target.get("qty_explicit", False),
        "unit_hint":    target.get("unit_hint"),
        "line_id":      target_id,          # preserve identity
    }
    new_item = resolve_quote_item(candidate, logic, knowledge=knowledge)
    old_status = target["status"]
    improved = (
        (old_status in ("unresolved", "blocked_by_missing_info") and new_item["status"] in ("resolved", "ambiguous", "blocked_by_missing_info"))
        or (old_status == "ambiguous" and new_item["status"] in ("resolved", "blocked_by_missing_info"))
    )
    if len(new_item.get("missing_dimensions") or []) < len(target.get("missing_dimensions") or []):
        improved = True
    attempts = int(target.get("clarification_attempts") or 0)
    next_dim = None
    for key in clar_dims:
        if key in (target.get("missing_dimensions") or []):
            next_dim = key
            break
    if next_dim is None and clar_dims:
        next_dim = next(iter(clar_dims.keys()))

    updated = []
    for it in open_items:
        if it.get("line_id") == target_id:
            if improved:
                new_item["clarification_attempts"] = 0
                new_item["last_targeted_dimension"] = next_dim
                updated.append(new_item)
            else:
                preserved = dict(it)
                preserved["clarification_attempts"] = attempts + 1
                preserved["last_targeted_dimension"] = next_dim
                updated.append(preserved)
        else:
            updated.append(it)
    return updated


# ---------------------------------------------------------------------------
# Quantity-increment helpers
# ---------------------------------------------------------------------------

_INCREMENT_RE = re.compile(
    r"^(?P<qty>\d+|uno?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)?\s*"
    r"(?:mas|más|otro|otra|igual|del mismo|de lo mismo)\s*(?:de\s+)?(?P<item>.*)$",
    re.IGNORECASE,
)


def _is_increment_request(stripped: str) -> Tuple[Optional[int], Optional[str]]:
    """
    If the stripped additive text looks like a quantity increment
    ("otro teflón", "2 más", "dos más de silicona"), return (qty, item_hint).
    Otherwise return (None, None).
    """
    norm = _normalize(stripped)
    m = _INCREMENT_RE.match(norm)
    if not m:
        return None, None
    qty_str = (m.group("qty") or "1").lower()
    qty = _WORD_NUMBERS.get(qty_str) or (int(qty_str) if qty_str.isdigit() else 1)
    item_hint = (m.group("item") or "").strip() or None
    return qty, item_hint


def apply_additive(
    message: str, open_items: List[QuoteItem], logic: Any, knowledge: Optional[Dict[str, Any]] = None
) -> List[QuoteItem]:
    """
    Apply an additive request.

    1. Strip the additive verb prefix.
    2. Check for quantity-increment patterns (otro X, 2 más, etc.).
       - If the increment clearly refers to an existing resolved line,
         increment that line's qty and recompute subtotal.
    3. Otherwise parse as new items and append.
    """
    stripped = _ADDITIVE_RE.sub("", message.strip()).strip()
    if not stripped:
        return open_items

    inc_qty, item_hint = _is_increment_request(stripped)
    if inc_qty is not None:
        # Try to find the matching existing line
        resolved_lines = [it for it in open_items if it["status"] == "resolved"]
        target: Optional[QuoteItem] = None
        if item_hint:
            target = _match_to_line(item_hint, resolved_lines)
        elif len(resolved_lines) == 1:
            target = resolved_lines[0]  # only one resolved — safe to increment
        elif resolved_lines:
            # "del mismo" / "otro igual" — use last resolved line
            target = resolved_lines[-1]

        if target is not None:
            new_qty = target.get("qty", 1) + inc_qty
            updated_line = dict(target)
            updated_line["qty"] = new_qty
            updated_line["qty_explicit"] = True
            unit_price = updated_line.get("unit_price")
            if unit_price is not None and not updated_line.get("pack_note"):
                updated_line["subtotal"] = round(unit_price * new_qty, 2)
            return [
                updated_line if it.get("line_id") == target.get("line_id") else it
                for it in open_items
            ]

    # Not an increment — parse as new items and append
    new_parsed = parse_quote_items(stripped)
    new_resolved = [resolve_quote_item(p, logic, knowledge=knowledge) for p in new_parsed]
    existing_ids = {it.get("line_id") for it in open_items if it.get("line_id")}
    existing_norms = {it.get("normalized", "").lower() for it in open_items}
    to_add = [
        it for it in new_resolved
        if it.get("normalized", "").lower() not in existing_norms
        and it.get("line_id") not in existing_ids
    ]
    return list(open_items) + to_add


def generate_updated_quote_response(
    resolved_items: List[QuoteItem],
    complementary: Optional[List[str]] = None,
) -> str:
    return generate_quote_response(
        resolved_items,
        complementary=complementary,
        header="*Actualice el presupuesto preliminar:*",
    )


def session_guard_response(open_items: List[QuoteItem]) -> str:
    body = generate_quote_response(open_items)
    suffix = (
        "\n\nPodes:\n"
        "- Aclarar alguno de los items pendientes\n"
        "- Decir *agregale* para sumar mas productos\n"
        "- Sacá un item: *sacá el teflón*\n"
        "- Reemplazá un item: *cambiá el taladro por amoladora*\n"
        "- Decir *nuevo presupuesto* para empezar de cero\n"
        "- Decir *dale cerralo* para aceptar el presupuesto"
    )
    return body + suffix


# ---------------------------------------------------------------------------
# Remove operations
# ---------------------------------------------------------------------------

_REMOVE_RE = re.compile(
    r"^(?:saca|sacá|sacame|quita|quitá|quitame|elimina|eliminá|borra|"
    r"borrá|saque|quite|elimine|deja sin|dejá sin|sin el|sin la)\s+"
    r"(?:el|la|los|las|un|una)?\s*",
    re.IGNORECASE,
)


def looks_like_remove(message: str) -> bool:
    return bool(_REMOVE_RE.match(_normalize(message.strip())))


def apply_remove(
    message: str, open_items: List[QuoteItem]
) -> Tuple[List[QuoteItem], str]:
    """
    Remove a line from the quote by identity match.
    Returns (updated_items, status_message).
    """
    norm = _normalize(message.strip())
    stripped = _REMOVE_RE.sub("", norm).strip()
    if not stripped:
        return list(open_items), "¿Qué item querés quitar? Decime el nombre."

    target = _match_to_line(stripped, open_items)
    if target is None:
        return list(open_items), (
            f"No encontré '{stripped}' en el presupuesto. "
            "Verificá el nombre o decime exactamente cuál."
        )

    removed_name = target.get("original", stripped).capitalize()
    updated = [it for it in open_items if it.get("line_id") != target.get("line_id")]
    return updated, f"Saqué *{removed_name}* del presupuesto."


# ---------------------------------------------------------------------------
# Replace operations
# ---------------------------------------------------------------------------

_REPLACE_RE = re.compile(
    r"^(?:cambia|cambiá|reemplaza|reemplazá|mejor pone|mejor pon|en vez de|best)\s+"
    r"(?:el|la|los|las|un|una)?\s*(?P<from>[\w\s]+?)\s+"
    r"(?:por|por un|por una|en vez de)\s+"
    r"(?:el|la|los|las|un|una)?\s*(?P<to>[\w\s]+)$",
    re.IGNORECASE,
)


def looks_like_replace(message: str) -> bool:
    return bool(_REPLACE_RE.match(_normalize(message.strip())))


def apply_replace(
    message: str, open_items: List[QuoteItem], logic: Any, knowledge: Optional[Dict[str, Any]] = None
) -> Tuple[List[QuoteItem], str]:
    """
    Replace one quote line with another item.
    Returns (updated_items, status_message).
    """
    norm = _normalize(message.strip())
    m = _REPLACE_RE.match(norm)
    if not m:
        return list(open_items), (
            "No entendi el reemplazo. Decime: *cambiá [item] por [otro item]*."
        )

    from_text = m.group("from").strip()
    to_text = m.group("to").strip()

    target = _match_to_line(from_text, open_items)
    if target is None:
        return list(open_items), (
            f"No encontré '{from_text}' en el presupuesto."
        )

    # Resolve the replacement item, preserving line_id so totals update cleanly
    new_parsed: Dict[str, Any] = {
        "raw":          to_text,
        "normalized":   to_text,
        "qty":          target.get("qty", 1),
        "qty_explicit": target.get("qty_explicit", False),
        "unit_hint":    target.get("unit_hint"),
        "line_id":      target.get("line_id"),
    }
    new_item = resolve_quote_item(new_parsed, logic, knowledge=knowledge)

    old_name = target.get("original", from_text).capitalize()
    new_name = new_item.get("original", to_text).capitalize()
    updated = [
        new_item if it.get("line_id") == target.get("line_id") else it
        for it in open_items
    ]
    status = f"Reemplacé *{old_name}* por *{new_name}*."
    if new_item["status"] != "resolved":
        status += f" Necesita aclaración: {new_item.get('clarification', '')}"
    return updated, status


# ---------------------------------------------------------------------------
# Merge-vs-replace decision helpers
# ---------------------------------------------------------------------------

MERGE_VS_REPLACE_QUESTION = (
    "Ya tenés un presupuesto abierto. ¿Lo sumo al actual o arrancamos uno nuevo?\n"
    "  • *sumalo* — agrego los nuevos items al actual\n"
    "  • *nuevo* — empezamos de cero"
)


def looks_like_merge_answer(text: str, knowledge: Optional[Dict[str, Any]] = None) -> bool:
    patterns = _acceptance_patterns(knowledge)
    phrases = patterns.get("merge_phrases") or []
    return _match_known_phrase(text, phrases)


def looks_like_new_answer(text: str, knowledge: Optional[Dict[str, Any]] = None) -> bool:
    patterns = _acceptance_patterns(knowledge)
    phrases = patterns.get("new_quote_phrases") or []
    return _match_known_phrase(text, phrases)
