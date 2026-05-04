"""
R2: Post-response price validation against catalog.

Detects prices hallucinated by the LLM in free-text responses by comparing
against catalog prices observed during the current turn.

Two price sources are combined by the caller:
  Fuente A — sess["last_catalog_result"]["candidates"] (TurnInterpreter path)
  Fuente B — func_result["products"] from buscar_stock calls in _chat_with_functions loop

Only prices with $ prefix or ARS/pesos suffix are extracted — bare numbers,
dimensions (12mm), and quantities are intentionally ignored.
"""
import re
from typing import List, Optional

# Minimum price value (ARS) to process — filters noise like "$0.50" or
# numbers that happen to follow a $ in non-price contexts.
_MIN_PRICE = 100

# Approximation phrases that precede a $ price in Spanish.
# "alrededor de $12000", "aprox. $5000", "más o menos $8000", etc.
_APPROX_PATTERN = re.compile(
    r'\b(?:alrededor\s+de|aproximadamente|aprox\.?|m[aá]s\s+o\s+menos|unos|cerca\s+de)'
    r'\s*\$',
    re.IGNORECASE,
)


def _parse_ars_value(raw: str) -> Optional[int]:
    """
    Normalize an ARS price string to integer.

    Handles Argentine format (dots as thousands, comma as decimal):
      "12.500"  → 12500
      "12,500"  → 12500
      "12500"   → 12500
      "12.500,00" → 12500 (strips cents)

    Returns None if value < _MIN_PRICE or unparseable.
    """
    # Strip spaces, then remove dots and commas (used as separators in ARS)
    cleaned = raw.strip().replace(" ", "").replace(".", "").replace(",", "")
    try:
        val = int(cleaned)
        return val if val >= _MIN_PRICE else None
    except ValueError:
        return None


def extract_prices_from_response(text: str) -> List[int]:
    """
    Extract prices mentioned in LLM response text.

    Only captures:
      - $ prefix: $12500, $12.500, $12,500, $ 12.500
      - Currency suffix: 12500 ARS, 12.500 pesos

    Ignores:
      - Bare numbers without currency context ("12500")
      - Dimensions ("12mm de largo")
      - Quantities ("compré 50 unidades")

    Returns a deduplicated list of integer ARS prices.
    """
    prices: List[int] = []
    seen: set = set()

    # Pattern 1: $ prefix (Argentine peso notation)
    for m in re.finditer(r'\$\s*([\d][\d.,]*)', text):
        val = _parse_ars_value(m.group(1))
        if val is not None and val not in seen:
            prices.append(val)
            seen.add(val)

    # Pattern 2: ARS / pesos suffix
    for m in re.finditer(r'\b([\d][\d.,]*)\s+(?:ARS|pesos)\b', text, re.IGNORECASE):
        val = _parse_ars_value(m.group(1))
        if val is not None and val not in seen:
            prices.append(val)
            seen.add(val)

    return prices


def has_approximate_language(text: str) -> bool:
    """
    Returns True if the text contains approximation language immediately
    before a $ price (e.g. "alrededor de $12000", "aprox. $5000").
    """
    return bool(_APPROX_PATTERN.search(text))


def detect_hallucinated_prices(
    response: str,
    catalog_prices: List[int],
    tolerance_pct: float = 5.0,
) -> List[int]:
    """
    Compare prices mentioned in the LLM response against catalog prices.

    A price is considered hallucinated if NO catalog price exists within
    ±tolerance_pct% of the mentioned price.

    Returns [] when:
      - catalog_prices is empty (no data to compare against — cannot judge)
      - No prices are mentioned in the response

    Args:
        response: The LLM free-text response to validate.
        catalog_prices: All prices the LLM legitimately had access to this turn.
        tolerance_pct: Acceptable rounding tolerance (default 5%).

    Returns:
        List of prices from response that appear hallucinated.
    """
    if not catalog_prices:
        return []

    mentioned = extract_prices_from_response(response)
    if not mentioned:
        return []

    hallucinated = []
    for price in mentioned:
        matched = any(
            abs(price - cat_p) / cat_p <= tolerance_pct / 100.0
            for cat_p in catalog_prices
            if cat_p > 0
        )
        if not matched:
            hallucinated.append(price)

    return hallucinated
