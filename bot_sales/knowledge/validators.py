"""Validation helpers for tenant-editable knowledge files."""

from __future__ import annotations

from typing import Any, Dict, List

from .defaults import ALLOWED_DIMENSIONS


class KnowledgeValidationError(ValueError):
    """Raised when tenant-editable knowledge is invalid."""


def _ensure_list(value: Any, field: str) -> List[Any]:
    if not isinstance(value, list):
        raise KnowledgeValidationError(f"{field} must be a list")
    return value


def _ensure_mapping(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise KnowledgeValidationError(f"{field} must be a mapping")
    return value


def _normalize_dimensions(values: Any, field: str) -> List[str]:
    dims = [str(x).strip() for x in _ensure_list(values, field) if str(x).strip()]
    unknown = [dim for dim in dims if dim not in ALLOWED_DIMENSIONS]
    if unknown:
        unique = ", ".join(sorted(set(unknown)))
        raise KnowledgeValidationError(f"{field} has unknown dimensions: {unique}")
    return dims


def validate_synonyms(payload: Dict[str, Any]) -> Dict[str, Any]:
    entries = _ensure_list(payload.get("entries", []), "entries")
    seen_terms = set()
    normalized = {"entries": []}
    for entry in entries:
        canonical = str(entry.get("canonical", "")).strip()
        if not canonical:
            raise KnowledgeValidationError("synonym entry missing canonical")
        aliases = [str(a).strip() for a in _ensure_list(entry.get("aliases", []), f"aliases for {canonical}") if str(a).strip()]
        misspellings = [str(a).strip() for a in _ensure_list(entry.get("misspellings", []), f"misspellings for {canonical}") if str(a).strip()]
        context_terms = [str(a).strip() for a in _ensure_list(entry.get("context_terms", []), f"context_terms for {canonical}") if str(a).strip()]
        if not aliases:
            raise KnowledgeValidationError(f"synonym entry '{canonical}' must have aliases")
        maps_dimensions = _ensure_mapping(entry.get("maps_dimensions", {}), f"maps_dimensions for {canonical}")
        for key in maps_dimensions:
            if key not in ALLOWED_DIMENSIONS:
                raise KnowledgeValidationError(f"synonym entry '{canonical}' has unknown dimension key '{key}'")
        for term in aliases + misspellings:
            low = term.lower()
            if low in seen_terms:
                raise KnowledgeValidationError(f"duplicate alias or misspelling: {term}")
            seen_terms.add(low)
        normalized["entries"].append(
            {
                "canonical": canonical,
                "family": str(entry.get("family", "")).strip() or canonical,
                "aliases": aliases,
                "misspellings": misspellings,
                "brand_generic": bool(entry.get("brand_generic", False)),
                "maps_dimensions": {str(k).strip(): str(v).strip() for k, v in maps_dimensions.items() if str(v).strip()},
                "context_terms": context_terms,
            }
        )
    return normalized


def validate_family_rules(payload: Dict[str, Any]) -> Dict[str, Any]:
    families = payload.get("families", {})
    if not isinstance(families, dict):
        raise KnowledgeValidationError("families must be a mapping")
    normalized: Dict[str, Any] = {"families": {}}
    for family, rule in families.items():
        if not isinstance(rule, dict):
            raise KnowledgeValidationError(f"family rule for {family} must be a mapping")
        allowed_categories = [str(x).strip() for x in _ensure_list(rule.get("allowed_categories", []), f"allowed_categories for {family}") if str(x).strip()]
        if not allowed_categories:
            continue  # catalog gap — no products assigned, skip silently
        required_dimensions = _normalize_dimensions(rule.get("required_dimensions", []), f"required_dimensions for {family}")
        optional_dimensions = _normalize_dimensions(rule.get("optional_dimensions", []), f"optional_dimensions for {family}")
        dimension_priority = _normalize_dimensions(rule.get("dimension_priority", []), f"dimension_priority for {family}")
        autopick_min_dimensions = _normalize_dimensions(rule.get("autopick_min_dimensions", []), f"autopick_min_dimensions for {family}")
        compatibility_axes = _normalize_dimensions(rule.get("compatibility_axes", []), f"compatibility_axes for {family}")
        blocked_conditions = []
        for index, condition in enumerate(_ensure_list(rule.get("blocked_autopick_conditions", []), f"blocked_autopick_conditions for {family}")):
            if not isinstance(condition, dict):
                raise KnowledgeValidationError(f"family '{family}' blocked_autopick_conditions[{index}] must be a mapping")
            if_missing = _normalize_dimensions(condition.get("if_missing", []), f"if_missing for {family}[{index}]")
            blocked_conditions.append(
                {
                    "if_missing": if_missing,
                    "reason": str(condition.get("reason", "")).strip() or "missing_dimensions",
                }
            )
        normalized["families"][family] = {
            "allowed_categories": allowed_categories,
            "match_terms": [str(x).strip() for x in _ensure_list(rule.get("match_terms", [family]), f"match_terms for {family}") if str(x).strip()],
            "required_dimensions": required_dimensions,
            "optional_dimensions": optional_dimensions,
            "dimension_priority": dimension_priority,
            "autopick_min_dimensions": autopick_min_dimensions,
            "blocked_autopick_conditions": blocked_conditions,
            "compatibility_axes": compatibility_axes,
            "presentation_rules": _ensure_mapping(rule.get("presentation_rules", {}), f"presentation_rules for {family}"),
            "substitute_group": str(rule.get("substitute_group", "")).strip() or family,
            "allowed_substitute_groups": [str(x).strip() for x in _ensure_list(rule.get("allowed_substitute_groups", []), f"allowed_substitute_groups for {family}") if str(x).strip()],
            "blocked_substitute_groups": [str(x).strip() for x in _ensure_list(rule.get("blocked_substitute_groups", []), f"blocked_substitute_groups for {family}") if str(x).strip()],
            "brand_generic_terms": [str(x).strip() for x in _ensure_list(rule.get("brand_generic_terms", []), f"brand_generic_terms for {family}") if str(x).strip()],
            "pack_sensitive": bool(rule.get("pack_sensitive", False)),
            "compatibility_sensitive": bool(rule.get("compatibility_sensitive", False)),
        }
    return normalized


def validate_clarification_rules(payload: Dict[str, Any], family_rules: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rules = payload.get("rules", {})
    if not isinstance(rules, dict):
        raise KnowledgeValidationError("rules must be a mapping")
    family_names = set((family_rules or {}).keys())
    normalized = {"rules": {}}
    for family, rule in rules.items():
        if family_names and family not in family_names:
            raise KnowledgeValidationError(f"clarification rule '{family}' does not exist in family rules")
        if not isinstance(rule, dict):
            raise KnowledgeValidationError(f"clarification rule '{family}' must be a mapping")
        prompt = str(rule.get("prompt", "")).strip()
        short_prompt = str(rule.get("short_prompt", "")).strip() or prompt
        if not prompt:
            raise KnowledgeValidationError(f"clarification rule '{family}' missing prompt")
        required_dimensions = _normalize_dimensions(rule.get("required_dimensions", []), f"required_dimensions for clarification {family}")
        question_order = _normalize_dimensions(rule.get("question_order", []), f"question_order for clarification {family}")
        stop_when_dimensions_present = _normalize_dimensions(rule.get("stop_when_dimensions_present", []), f"stop_when_dimensions_present for clarification {family}")
        blocked_if_missing = _normalize_dimensions(rule.get("blocked_if_missing", []), f"blocked_if_missing for clarification {family}")

        prompt_by_missing_dimensions = _ensure_mapping(rule.get("prompt_by_missing_dimensions", {}), f"prompt_by_missing_dimensions for {family}")
        for dim in prompt_by_missing_dimensions:
            if dim not in ALLOWED_DIMENSIONS:
                raise KnowledgeValidationError(f"clarification rule '{family}' has unknown prompt dimension '{dim}'")

        examples_by_dimension = _ensure_mapping(rule.get("examples_by_dimension", {}), f"examples_by_dimension for {family}")
        normalized_examples_by_dimension = {}
        for dim, values in examples_by_dimension.items():
            if dim not in ALLOWED_DIMENSIONS:
                raise KnowledgeValidationError(f"clarification rule '{family}' has unknown examples dimension '{dim}'")
            normalized_examples_by_dimension[dim] = [str(x).strip() for x in _ensure_list(values, f"examples_by_dimension[{dim}] for {family}") if str(x).strip()]

        normalized["rules"][family] = {
            "prompt": prompt,
            "short_prompt": short_prompt,
            "examples": [str(x).strip() for x in _ensure_list(rule.get("examples", []), f"examples for {family}") if str(x).strip()],
            "required_dimensions": required_dimensions,
            "question_order": question_order,
            "prompt_by_missing_dimensions": {str(k).strip(): str(v).strip() for k, v in prompt_by_missing_dimensions.items() if str(v).strip()},
            "examples_by_dimension": normalized_examples_by_dimension,
            "stop_when_dimensions_present": stop_when_dimensions_present,
            "blocked_if_missing": blocked_if_missing,
        }
    return normalized


def validate_blocked_terms(payload: Dict[str, Any]) -> Dict[str, Any]:
    terms = _ensure_list(payload.get("terms", []), "terms")
    seen = set()
    normalized = {"terms": []}
    for term in terms:
        text = str(term.get("term", "")).strip()
        reason = str(term.get("reason", "")).strip()
        if not text:
            raise KnowledgeValidationError("blocked term missing term")
        if not reason:
            raise KnowledgeValidationError(f"blocked term '{text}' missing reason")
        key = text.lower()
        if key in seen:
            raise KnowledgeValidationError(f"duplicate blocked term: {text}")
        seen.add(key)
        normalized["terms"].append({
            "term": text,
            "reason": reason,
            "redirect_prompt": str(term.get("redirect_prompt", "")).strip(),
            "family_hint": str(term.get("family_hint", "")).strip() or None,
            "block_if_no_dimensions": _normalize_dimensions(term.get("block_if_no_dimensions", []), f"block_if_no_dimensions for blocked term {text}"),
            "block_if_used_alone": bool(term.get("block_if_used_alone", False)),
        })
    return normalized


def validate_complementary_rules(payload: Dict[str, Any]) -> Dict[str, Any]:
    rules = payload.get("rules", {})
    if not isinstance(rules, dict):
        raise KnowledgeValidationError("rules must be a mapping")
    normalized = {"rules": {}}
    for source, rule in rules.items():
        targets = [str(x).strip() for x in _ensure_list(rule.get("targets", []), f"targets for {source}") if str(x).strip()]
        max_suggestions = int(rule.get("max_suggestions", len(targets) or 0))
        if max_suggestions < 0 or max_suggestions > 3:
            raise KnowledgeValidationError(f"complementary rule '{source}' has invalid max_suggestions")
        normalized["rules"][source] = {
            "targets": targets,
            "max_suggestions": max_suggestions,
            "required_source_status": str(rule.get("required_source_status", "resolved")).strip() or "resolved",
            "required_dimensions": _normalize_dimensions(rule.get("required_dimensions", []), f"required_dimensions for complementary {source}"),
            "blocked_when_missing": _normalize_dimensions(rule.get("blocked_when_missing", []), f"blocked_when_missing for complementary {source}"),
            "compatible_families": [str(x).strip() for x in _ensure_list(rule.get("compatible_families", []), f"compatible_families for {source}") if str(x).strip()],
        }
    return normalized


def validate_substitute_rules(payload: Dict[str, Any], family_rules: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rules = _ensure_list(payload.get("rules", []), "rules")
    family_names = set((family_rules or {}).keys())
    normalized = {"rules": []}
    seen_groups = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise KnowledgeValidationError(f"substitute_rules[{index}] must be a mapping")
        group_id = str(rule.get("group_id", "")).strip()
        if not group_id:
            raise KnowledgeValidationError(f"substitute_rules[{index}] missing group_id")
        if group_id in seen_groups:
            raise KnowledgeValidationError(f"duplicate substitute group_id: {group_id}")
        seen_groups.add(group_id)
        source_families = [str(x).strip() for x in _ensure_list(rule.get("source_families", []), f"source_families for {group_id}") if str(x).strip()]
        allowed_targets = [str(x).strip() for x in _ensure_list(rule.get("allowed_targets", []), f"allowed_targets for {group_id}") if str(x).strip()]
        if family_names:
            unknown_families = [fam for fam in source_families + allowed_targets if fam not in family_names]
            if unknown_families:
                unique = ", ".join(sorted(set(unknown_families)))
                raise KnowledgeValidationError(f"substitute rule '{group_id}' references unknown families: {unique}")
        normalized["rules"].append({
            "group_id": group_id,
            "source_families": source_families,
            "allowed_targets": allowed_targets,
            "required_matching_dimensions": _normalize_dimensions(rule.get("required_matching_dimensions", []), f"required_matching_dimensions for {group_id}"),
            "allowed_dimension_drift": _normalize_dimensions(rule.get("allowed_dimension_drift", []), f"allowed_dimension_drift for {group_id}"),
            "blocked_dimension_mismatches": _normalize_dimensions(rule.get("blocked_dimension_mismatches", []), f"blocked_dimension_mismatches for {group_id}"),
            "blocked_terms": [str(x).strip() for x in _ensure_list(rule.get("blocked_terms", []), f"blocked_terms for {group_id}") if str(x).strip()],
            "reason_template": str(rule.get("reason_template", "")).strip(),
        })
    return normalized


def validate_language_patterns(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "misspellings": _ensure_mapping(payload.get("misspellings", {}), "misspellings"),
        "regional_terms": _ensure_mapping(payload.get("regional_terms", {}), "regional_terms"),
        "brand_generics": _ensure_mapping(payload.get("brand_generics", {}), "brand_generics"),
        "abbreviations": _ensure_mapping(payload.get("abbreviations", {}), "abbreviations"),
        "surface_aliases": _ensure_mapping(payload.get("surface_aliases", {}), "surface_aliases"),
        "shorthand_dimension_patterns": [],
    }
    for index, pattern in enumerate(_ensure_list(payload.get("shorthand_dimension_patterns", []), "shorthand_dimension_patterns")):
        if not isinstance(pattern, dict):
            raise KnowledgeValidationError(f"shorthand_dimension_patterns[{index}] must be a mapping")
        regex = str(pattern.get("pattern", "")).strip()
        replacement = str(pattern.get("replacement", "")).strip()
        if not regex or not replacement:
            raise KnowledgeValidationError(f"shorthand_dimension_patterns[{index}] missing pattern or replacement")
        normalized["shorthand_dimension_patterns"].append({"pattern": regex, "replacement": replacement})
    return normalized


def validate_acceptance_patterns(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {}
    for key in ("accept_phrases", "reset_phrases", "merge_phrases", "new_quote_phrases"):
        values = [str(x).strip() for x in _ensure_list(payload.get(key, []), key) if str(x).strip()]
        if key == "accept_phrases" and not values:
            raise KnowledgeValidationError("accept_phrases must not be empty")
        normalized[key] = values
    return normalized


def validate_faqs(payload: Dict[str, Any]) -> Dict[str, Any]:
    entries = _ensure_list(payload.get("entries", []), "entries")
    seen = set()
    normalized = {"entries": []}
    for entry in entries:
        faq_id = str(entry.get("id", "")).strip()
        question = str(entry.get("question", "")).strip()
        answer = str(entry.get("answer", "")).strip()
        keywords = [str(x).strip() for x in _ensure_list(entry.get("keywords", []), f"keywords for {faq_id or question}") if str(x).strip()]
        if not faq_id:
            raise KnowledgeValidationError("FAQ entry missing id")
        if faq_id in seen:
            raise KnowledgeValidationError(f"duplicate FAQ id: {faq_id}")
        seen.add(faq_id)
        if not question or not answer or not keywords:
            raise KnowledgeValidationError(f"FAQ '{faq_id}' missing question, answer, or keywords")
        normalized["entries"].append({
            "id": faq_id,
            "question": question,
            "answer": answer,
            "keywords": keywords,
            "active": bool(entry.get("active", True)),
            "tags": [str(x).strip() for x in _ensure_list(entry.get("tags", []), f"tags for {faq_id}") if str(x).strip()],
        })
    return normalized
