from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bot_sales.ferreteria_language import normalize_basic
from bot_sales.knowledge.defaults import DEFAULT_CLARIFICATION_RULES, DEFAULT_FAMILY_RULES


def get_family_rules(knowledge: Dict[str, Any] | None = None) -> Dict[str, Dict[str, Any]]:
    payload = ((knowledge or {}).get("families") or {}).get("families", DEFAULT_FAMILY_RULES)
    rules = {}
    for family_id, rule in payload.items():
        enriched = dict(rule)
        enriched["family_id"] = family_id
        rules[family_id] = enriched
    return rules


def get_family_rule(family_id: str | None, knowledge: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not family_id:
        return {}
    return dict(get_family_rules(knowledge).get(family_id) or {})


def get_clarification_rules(knowledge: Dict[str, Any] | None = None) -> Dict[str, Dict[str, Any]]:
    return dict(((knowledge or {}).get("clarifications") or {}).get("rules", DEFAULT_CLARIFICATION_RULES))


def infer_families(normalized_text: str, knowledge: Dict[str, Any] | None = None) -> List[str]:
    normalized = normalize_basic(normalized_text)
    scores: Dict[str, float] = {}
    for entry in ((knowledge or {}).get("synonyms") or {}).get("entries", []):
        family = str(entry.get("family") or "").strip()
        if not family:
            continue
        alias_bucket = [entry.get("canonical", "")] + list(entry.get("aliases") or []) + list(entry.get("misspellings") or [])
        if any(alias and re.search(rf"\b{re.escape(normalize_basic(str(alias)))}\b", normalized) for alias in alias_bucket):
            scores[family] = scores.get(family, 0.0) + 1.4
    for family_id, rule in get_family_rules(knowledge).items():
        score = 0.0
        for term in rule.get("match_terms") or [family_id]:
            if re.search(rf"\b{re.escape(normalize_basic(term))}\b", normalized):
                score += 1.0
        for term in rule.get("brand_generic_terms") or []:
            if re.search(rf"\b{re.escape(normalize_basic(term))}\b", normalized):
                score += 0.7
        if family_id in normalized:
            score += 0.5
        if score > 0:
            scores[family_id] = scores.get(family_id, 0.0) + score
    scored: List[tuple[float, str]] = [(score, family_id) for family_id, score in scores.items() if score > 0]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [family_id for _, family_id in scored]


def detect_product_family(product: Dict[str, Any], knowledge: Dict[str, Any] | None = None) -> Optional[str]:
    product_text = normalize_basic(
        " ".join(
            str(product.get(field) or "")
            for field in ("model", "name", "sku", "category")
        )
    )
    product_category = str(product.get("category") or "").strip()
    best_family = None
    best_score = 0.0
    for family_id, rule in get_family_rules(knowledge).items():
        score = 0.0
        if product_category and product_category in (rule.get("allowed_categories") or []):
            score += 1.0
        for term in rule.get("match_terms") or [family_id]:
            if term and normalize_basic(term) in product_text:
                score += 1.0
        if score > best_score:
            best_score = score
            best_family = family_id
    return best_family


def is_autopick_blocked(family_id: str | None, dims: Dict[str, str], knowledge: Dict[str, Any] | None = None) -> tuple[bool, List[str], str]:
    rule = get_family_rule(family_id, knowledge)
    if not rule:
        return False, [], ""
    missing = []
    for dim in list(rule.get("required_dimensions") or []) + list(rule.get("autopick_min_dimensions") or []):
        if dim not in missing and not dims.get(dim):
            missing.append(dim)
    for condition in rule.get("blocked_autopick_conditions") or []:
        if_missing = [dim for dim in condition.get("if_missing") or [] if not dims.get(dim)]
        if if_missing:
            for dim in if_missing:
                if dim not in missing:
                    missing.append(dim)
            return True, missing, str(condition.get("reason", "missing_dimensions"))
    return bool(missing), missing, "missing_dimensions" if missing else ""


def build_clarification_prompt(
    family_id: str | None,
    missing_dimensions: List[str],
    normalized_text: str,
    knowledge: Dict[str, Any] | None = None,
) -> str:
    rules = get_clarification_rules(knowledge)
    rule = dict(rules.get(family_id or "") or {})
    if rule:
        prompt_by_missing = rule.get("prompt_by_missing_dimensions") or {}
        question_order = list(rule.get("question_order") or [])
        for dim in question_order:
            if dim in missing_dimensions and prompt_by_missing.get(dim):
                return str(prompt_by_missing[dim])
        for dim in missing_dimensions:
            if prompt_by_missing.get(dim):
                return str(prompt_by_missing[dim])
        short_prompt = str(rule.get("short_prompt", "")).strip()
        if short_prompt:
            return short_prompt
        prompt = str(rule.get("prompt", "")).strip()
        if prompt:
            return prompt
    return f"decime mas detalles sobre '{normalized_text}' (medida, uso, material o tipo)"
