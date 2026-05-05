"""
Pre-LLM search validation for impossible specs and spec mismatches.

Level 1 (validate_query_specs): Detects physically impossible specs in the
original user message BEFORE querying the catalog. Returns no_match early,
preventing the LLM from ever seeing real products for absurd queries.

Level 2 (validate_search_match): After catalog search returns products,
verifies that explicit spec claims in the user message are satisfied by at
least one product. If no product matches the claimed spec, converts the
result to no_match before the LLM sees the product list.

Level 3: Structured logging of every block/filter for calibration.

Both functions operate on the ORIGINAL user message (from session context),
NOT on the LLM-extracted "modelo" arg, which may silently drop impossible
specs like "500kg" or "dorado".

Active validators:
  V1 — weight impossible for known hand-tool type
  V2 — drill/bit diameter impossible
  V3 — fastener length impossible
  V6 — wattage impossible for known electric tool family

Removed (TurnInterpreter now handles these via LLM-first routing):
  V4 — precious color on metal hand tool (B25)
  V5 — digital storage spec on physical hardware (B25)
  V7 — impossible adjective combinations (B25)
  V8 — negotiation intent → intent=escalate, escalation_reason='negotiation' (B25)
  V9 — ambiguous query → intent=product_search search_mode='browse' (B25)
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Hand tools with realistic max weights (kg).
# Tuples are (frozenset_of_keywords, max_kg).
_TOOL_WEIGHT_LIMITS: List[Tuple[frozenset, float]] = [
    (frozenset({"martillo", "maza", "mazo"}), 5.0),
    (frozenset({"destornillador", "desarmador"}), 0.8),
    (frozenset({"broca", "mecha", "fresa"}), 0.5),
    (frozenset({"alicate", "pinza", "tenaza"}), 2.0),
    (frozenset({"sierra", "serrucho"}), 3.0),
    (frozenset({"cincel", "formón", "formon"}), 0.5),
    (frozenset({"cutter", "trincheta"}), 0.3),
]

# Max realistic drill/bit diameter (mm).
_DRILL_MAX_MM = 60.0
_DRILL_KWS = frozenset({"broca", "mecha", "fresa"})

# Max realistic fastener length (mm).
_FASTENER_MAX_MM = 800.0
_FASTENER_KWS = frozenset({
    "tornillo", "clavo", "perno", "esparrago", "espárrago"
})

# Max realistic wattage per electric tool family.
# Tuples are (frozenset_of_keywords, max_watts).
# "sierra circular" is handled separately in V6 (two-word match).
_TOOL_WATT_LIMITS: List[Tuple[frozenset, int]] = [
    (frozenset({"taladro"}), 2000),
    (frozenset({"amoladora", "esmeriladora"}), 2500),
    (frozenset({"lijadora"}), 1500),
    (frozenset({"aspiradora"}), 2500),
    (frozenset({"soldadora"}), 5000),
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _has_word(text: str, keywords: frozenset) -> bool:
    """
    True if any keyword appears as a whole word (or its Spanish plural) in text.
    Handles common Spanish inflection: "martillo" matches "martillos",
    "broca" matches "brocas", "mecha" matches "mechas".
    Uses optional trailing 's' which covers the most common plural form.
    """
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"s?\b", text, re.IGNORECASE):
            return True
    return False


def _extract_weight_kg(text: str) -> Optional[float]:
    """
    Extract the first weight mentioned in text, normalized to kg.
    Recognises: "500kg", "500 kg", "500 kilos", "500 kilogramos",
                "0.5 toneladas", "500 gramos", "500g" (as grams).
    Returns None if no weight found.
    """
    tl = text.lower()
    patterns = [
        # Tons → multiply by 1000
        (r"([\d.,]+)\s*(?:toneladas?|ton\.?)\b", 1000.0),
        # Kilograms
        (r"([\d.,]+)\s*(?:kilogramos?|kilos?|kg)\b", 1.0),
        # Grams → divide by 1000
        (r"([\d.,]+)\s*(?:gramos?)\b", 0.001),
        # Bare "g" only when preceded by a digit and not part of a longer word
        (r"([\d.,]+)\s*g\b", 0.001),
    ]
    for pat, factor in patterns:
        m = re.search(pat, tl)
        if m:
            try:
                return float(m.group(1).replace(",", ".")) * factor
            except ValueError:
                pass
    return None


def _extract_mm_value(text: str) -> Optional[float]:
    """
    Extract the first measurement in text, normalized to mm.
    Recognises: "500mm", "50 cm", "5 metros".
    """
    tl = text.lower()
    patterns = [
        (r"([\d.,]+)\s*(?:metros?|mts?\.?)\b", 1000.0),
        (r"([\d.,]+)\s*cm\b", 10.0),
        (r"([\d.,]+)\s*mm\b", 1.0),
    ]
    for pat, factor in patterns:
        m = re.search(pat, tl)
        if m:
            try:
                return float(m.group(1).replace(",", ".")) * factor
            except ValueError:
                pass
    return None


def _extract_watts(text: str) -> Optional[int]:
    """
    Extract the first wattage mentioned in text.
    Recognises: "5000W", "5000 W", "5000w", "5000 watts", "5000 vatios".
    Applied to lowercased text internally.
    Returns None if no wattage found.
    """
    tl = text.lower()
    m = re.search(r"(\d+)\s*(?:watts?|vatios?|w)\b", tl)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


# ─── Level 1: Impossible spec detection ───────────────────────────────────────

def validate_query_specs(text: str) -> Tuple[bool, Optional[str]]:
    """
    Level 1 — detect physically impossible specs in user message.

    Runs BEFORE the catalog search. Operates on the original user message,
    not on LLM-extracted args.

    Returns:
        (True, None)           — query looks valid, proceed normally.
        (False, reason_str)    — impossible spec detected; return no_match.
    """
    if not text:
        return True, None

    # V1: Weight impossible for a known tool type
    weight_kg = _extract_weight_kg(text)
    if weight_kg is not None:
        for tool_kws, max_kg in _TOOL_WEIGHT_LIMITS:
            if _has_word(text, tool_kws) and weight_kg > max_kg:
                reason = (
                    f"peso {weight_kg}kg imposible para "
                    f"{'/'.join(sorted(tool_kws))} (máx ~{max_kg}kg)"
                )
                logger.info(
                    "search_validator.L1.weight_impossible query=%r reason=%s",
                    text, reason,
                )
                return False, reason

    # V2: Drill/bit diameter impossible
    if _has_word(text, _DRILL_KWS):
        mm = _extract_mm_value(text)
        if mm is not None and mm > _DRILL_MAX_MM:
            reason = f"diámetro {mm}mm imposible para broca/mecha (máx ~{_DRILL_MAX_MM}mm)"
            logger.info(
                "search_validator.L1.drill_diameter query=%r reason=%s",
                text, reason,
            )
            return False, reason

    # V3: Fastener length impossible
    if _has_word(text, _FASTENER_KWS):
        mm = _extract_mm_value(text)
        if mm is not None and mm > _FASTENER_MAX_MM:
            reason = f"longitud {mm}mm imposible para fijación (máx ~{_FASTENER_MAX_MM}mm)"
            logger.info(
                "search_validator.L1.fastener_length query=%r reason=%s",
                text, reason,
            )
            return False, reason

    # V6: Wattage impossible for known electric tool family
    watts = _extract_watts(text)
    if watts is not None:
        for tool_kws, max_watts in _TOOL_WATT_LIMITS:
            if _has_word(text, tool_kws) and watts > max_watts:
                family_name = "/".join(sorted(tool_kws))
                reason = (
                    f"potencia {watts}W imposible para {family_name} "
                    f"(máx ~{max_watts}W)"
                )
                logger.info(
                    "search_validator.L1.watts_impossible query=%r reason=%s",
                    text, reason,
                )
                return False, reason
        # "sierra circular" requires both words to avoid matching manual saws
        tl = text.lower()
        if (re.search(r"\bsierra\b", tl) and re.search(r"\bcircular\b", tl)
                and watts > 2500):
            reason = f"potencia {watts}W imposible para sierra circular (máx ~2500W)"
            logger.info(
                "search_validator.L1.watts_impossible query=%r reason=%s",
                text, reason,
            )
            return False, reason

    return True, None


# ─── Level 2: Post-search spec mismatch detection ─────────────────────────────

def _product_matches_weight(product: Dict[str, Any], claimed_kg: float) -> bool:
    """True if the product's model name mentions a weight within 3× of claimed_kg."""
    model = (product.get("model") or product.get("name") or "").lower()
    # Same patterns as _extract_weight_kg but applied to product name
    patterns = [
        (r"([\d.,]+)\s*(?:kilogramos?|kilos?|kg)\b", 1.0),
        (r"([\d.,]+)\s*(?:gramos?)\b", 0.001),
        (r"([\d.,]+)\s*g\b", 0.001),
        (r"([\d.,]+)\s*(?:toneladas?|ton\.?)\b", 1000.0),
    ]
    for pat, factor in patterns:
        m = re.search(pat, model)
        if m:
            try:
                val = float(m.group(1).replace(",", ".")) * factor
                if claimed_kg / 3.0 <= val <= claimed_kg * 3.0:
                    return True
            except ValueError:
                pass
    return False


def validate_search_match(
    text: str, products: List[Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """
    Level 2 — verify spec claims in user message against returned products.

    Runs AFTER catalog search returns status="found". Operates on the original
    user message (same as Level 1).

    Logic:
      - If the user claimed a specific weight AND no product mentions a
        compatible weight → filter all products → return (False, reason).

    Returns:
        (True, None)           — products are consistent with the query.
        (False, reason_str)    — no product satisfies a critical spec claim.
    """
    if not text or not products:
        return True, None

    # Check weight claim
    claimed_kg = _extract_weight_kg(text)
    if claimed_kg is not None:
        # Only apply if a tool keyword is present (avoids triggering on paint
        # "20kg de pintura" where weight is a quantity, not a spec).
        all_tool_kws = frozenset().union(
            *[kws for kws, _ in _TOOL_WEIGHT_LIMITS], _DRILL_KWS
        )
        if _has_word(text, all_tool_kws):
            if not any(_product_matches_weight(p, claimed_kg) for p in products):
                reason = (
                    f"ningún producto coincide con el peso solicitado "
                    f"({claimed_kg}kg) — {len(products)} producto(s) descartado(s)"
                )
                logger.info(
                    "search_validator.L2.weight_mismatch query=%r "
                    "claimed_kg=%.3f products=%d",
                    text, claimed_kg, len(products),
                )
                return False, reason

    return True, None
