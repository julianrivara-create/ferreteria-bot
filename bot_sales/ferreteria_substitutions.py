from __future__ import annotations

from typing import Any, Dict, List

from bot_sales.ferreteria_dimensions import extract_dimensions
from bot_sales.ferreteria_family_model import detect_product_family, get_family_rule
from bot_sales.knowledge.defaults import DEFAULT_SUBSTITUTE_RULES


def get_substitute_rules(knowledge: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    payload = (knowledge or {}).get("substitute_rules") or DEFAULT_SUBSTITUTE_RULES
    return list(payload.get("rules") or [])


def _group_for_family(family_id: str | None, knowledge: Dict[str, Any] | None = None) -> str:
    rule = get_family_rule(family_id, knowledge)
    return str(rule.get("substitute_group", family_id or "")).strip()


def is_safe_substitute(source_family: str | None, candidate: Dict[str, Any], dims: Dict[str, str], knowledge: Dict[str, Any] | None = None) -> bool:
    candidate_family = detect_product_family(candidate, knowledge)
    if not source_family or not candidate_family:
        return False

    source_group = _group_for_family(source_family, knowledge)
    candidate_group = _group_for_family(candidate_family, knowledge)
    source_rule = get_family_rule(source_family, knowledge)
    blocked_groups = set(source_rule.get("blocked_substitute_groups") or [])
    allowed_groups = set(source_rule.get("allowed_substitute_groups") or [])

    if candidate_group in blocked_groups:
        return False
    if candidate_family != source_family and candidate_group not in allowed_groups:
        return False

    product_text = " ".join(str(candidate.get(field) or "") for field in ("model", "name", "sku", "category"))
    product_dims = extract_dimensions(product_text)
    matched_rule = False
    for rule in get_substitute_rules(knowledge):
        if source_family not in (rule.get("source_families") or []):
            continue
        matched_rule = True
        if candidate_family not in (rule.get("allowed_targets") or []):
            return False
        for blocked_dimension in rule.get("blocked_dimension_mismatches") or []:
            requested_value = dims.get(blocked_dimension)
            candidate_value = product_dims.get(blocked_dimension)
            if requested_value and not candidate_value:
                return False
            if requested_value and candidate_value and requested_value != candidate_value:
                return False
        for required in rule.get("required_matching_dimensions") or []:
            requested_value = dims.get(required)
            candidate_value = product_dims.get(required)
            if requested_value and not candidate_value:
                return False
            if requested_value and candidate_value and requested_value != candidate_value:
                return False
    if not matched_rule:
        for axis in source_rule.get("compatibility_axes") or []:
            requested_value = dims.get(str(axis))
            if not requested_value:
                continue
            candidate_value = product_dims.get(str(axis))
            if not candidate_value:
                return False
            if candidate_value != requested_value:
                return False
    return True


def filter_safe_alternatives(
    source_family: str | None,
    candidates: List[Dict[str, Any]],
    dims: Dict[str, str],
    knowledge: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    safe = []
    seen = set()
    for candidate in candidates:
        sku = candidate.get("sku")
        if sku in seen:
            continue
        if is_safe_substitute(source_family, candidate, dims, knowledge=knowledge):
            safe.append(candidate)
            seen.add(sku)
    return safe
