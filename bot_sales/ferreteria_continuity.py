from __future__ import annotations

from typing import Any, Dict, List, Optional

from bot_sales.ferreteria_dimensions import extract_dimensions
from bot_sales.ferreteria_family_model import infer_families
from bot_sales.ferreteria_language import normalize_basic


PENDING_STATUSES = {"ambiguous", "unresolved", "blocked_by_missing_info"}
_FRESH_REQUEST_WORDS = {"quiero", "necesito", "busco", "dame", "pasame", "presupuesto"}
_TARGET_MARGIN = 0.8


def pending_items(open_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [item for item in open_items if item.get("status") in PENDING_STATUSES]


def build_continuation_context(open_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    pending = pending_items(open_items)
    return {
        "pending_items": pending,
        "pending_line_ids": [item.get("line_id") for item in pending if item.get("line_id")],
        "pending_families": [item.get("family") for item in pending if item.get("family")],
    }


def classify_followup_message(
    message: str,
    open_items: List[Dict[str, Any]],
    knowledge: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pending = pending_items(open_items)
    normalized = normalize_basic(message or "")
    words = normalized.split()
    dims = extract_dimensions(normalized)
    families = infer_families(normalized, knowledge=knowledge)

    if not pending or not normalized:
        return {"kind": "none", "normalized": normalized, "dimensions": dims, "families": families}

    if words and words[0] in _FRESH_REQUEST_WORDS and not dims and not families:
        return {"kind": "none", "normalized": normalized, "dimensions": dims, "families": families}

    if len(words) > 12 and not dims and not families:
        return {"kind": "none", "normalized": normalized, "dimensions": dims, "families": families}

    if len(words) <= 8 or dims or families:
        return {"kind": "followup", "normalized": normalized, "dimensions": dims, "families": families}

    return {"kind": "none", "normalized": normalized, "dimensions": dims, "families": families}


def rank_target_lines(
    message: str,
    pending_items: List[Dict[str, Any]],
    knowledge: Dict[str, Any] | None = None,
    pending_target_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    from bot_sales import ferreteria_quote as fq

    normalized = normalize_basic(message or "")
    dims = extract_dimensions(normalized)
    families = infer_families(normalized, knowledge=knowledge)
    pending_target_ids = [line_id for line_id in (pending_target_ids or []) if line_id]
    msg_words = fq._match_words(normalized)
    ranked: List[Dict[str, Any]] = []

    for line in pending_items:
        score = 0.0
        line_id = line.get("line_id")
        line_family = str(line.get("family") or "").strip()
        line_dims = dict(line.get("dimensions") or {})
        line_missing = [dim for dim in (line.get("missing_dimensions") or []) if dim]
        line_words = fq._match_words(f"{line.get('normalized', '')} {line.get('original', '')}")
        overlap = msg_words & line_words

        if pending_target_ids and line_id in pending_target_ids:
            score += 4.0
        if line_family and line_family in families:
            score += 3.0
        if overlap:
            score += min(2.5, 0.8 * len(overlap))
        explicit_name = normalize_basic(str(line.get("original") or ""))
        if explicit_name and explicit_name in normalized:
            score += 2.5

        matched_missing: List[str] = []
        conflicting_dims: List[str] = []
        for key, value in dims.items():
            if key in line_missing:
                matched_missing.append(key)
                score += 2.2
            existing = line_dims.get(key)
            if existing and existing != value:
                conflicting_dims.append(key)
                score -= 1.0
            elif existing and existing == value:
                score += 0.6

        ranked.append(
            {
                "line": line,
                "score": score,
                "matched_missing": matched_missing,
                "conflicting_dimensions": conflicting_dims,
                "dimensions": dims,
                "families": families,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def choose_target_lines(
    message: str,
    open_items: List[Dict[str, Any]],
    knowledge: Dict[str, Any] | None = None,
    pending_target_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    pending = pending_items(open_items)
    ranked = rank_target_lines(message, pending, knowledge=knowledge, pending_target_ids=pending_target_ids)
    if not ranked:
        return {"status": "no_target", "ranked": ranked, "targets": []}

    positive = [entry for entry in ranked if entry["score"] > 0]
    if not positive:
        return {"status": "no_target", "ranked": ranked, "targets": []}

    matched_missing = [entry for entry in positive if entry["matched_missing"] and not entry["conflicting_dimensions"]]
    if len(matched_missing) == 1:
        return {"status": "targeted", "ranked": ranked, "targets": [matched_missing[0]["line"]]}

    if len(matched_missing) > 1:
        families = {str(entry["line"].get("family") or "") for entry in matched_missing}
        if len(families) == len(matched_missing) and len(families) > 1:
            return {"status": "multi_target", "ranked": ranked, "targets": [entry["line"] for entry in matched_missing]}

    best = positive[0]
    if len(positive) > 1 and (best["score"] - positive[1]["score"]) < _TARGET_MARGIN:
        ambiguous_targets = [entry["line"] for entry in positive[:2]]
        return {"status": "ambiguous", "ranked": ranked, "targets": ambiguous_targets}

    return {"status": "targeted", "ranked": ranked, "targets": [best["line"]]}


def merge_followup_dimensions(
    line: Dict[str, Any],
    message: str,
    knowledge: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_line = normalize_basic(str(line.get("normalized") or line.get("original") or ""))
    normalized_message = normalize_basic(message or "")
    line_family = str(line.get("family") or "").strip()
    if line_family and line_family not in normalized_message:
        merged_text = f"{normalized_line} {normalized_message}".strip()
    else:
        merged_text = normalized_message or normalized_line
    return {
        "raw": merged_text,
        "normalized": merged_text,
        "qty": line.get("qty", 1),
        "qty_explicit": line.get("qty_explicit", False),
        "unit_hint": line.get("unit_hint"),
        "line_id": line.get("line_id"),
    }


def _line_progressed(old_line: Dict[str, Any], new_line: Dict[str, Any]) -> bool:
    old_status = str(old_line.get("status") or "")
    new_status = str(new_line.get("status") or "")
    old_missing = list(old_line.get("missing_dimensions") or [])
    new_missing = list(new_line.get("missing_dimensions") or [])

    rank = {"resolved": 3, "ambiguous": 2, "blocked_by_missing_info": 1, "unresolved": 0}
    if rank.get(new_status, 0) > rank.get(old_status, 0):
        return True
    if len(new_missing) < len(old_missing):
        return True
    if old_status == "unresolved" and new_line.get("products"):
        return True
    return False


def _next_targeted_dimension(old_line: Dict[str, Any], message: str) -> Optional[str]:
    dims = extract_dimensions(message or "")
    old_missing = list(old_line.get("missing_dimensions") or [])
    for key in dims:
        if key in old_missing:
            return key
    return next(iter(dims.keys()), None) if dims else None


def apply_followup_to_open_quote(
    message: str,
    open_items: List[Dict[str, Any]],
    logic: Any,
    knowledge: Dict[str, Any] | None = None,
    pending_target_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from bot_sales import ferreteria_quote as fq

    classification = classify_followup_message(message, open_items, knowledge=knowledge)
    if classification.get("kind") != "followup":
        return {"status": "not_followup", "items": list(open_items)}

    chosen = choose_target_lines(message, open_items, knowledge=knowledge, pending_target_ids=pending_target_ids)
    if chosen["status"] == "no_target":
        return {"status": "no_target", "items": list(open_items), "ranked": chosen["ranked"]}
    if chosen["status"] == "ambiguous":
        prompt = fq.needs_disambiguation(message, chosen["targets"])
        return {
            "status": "needs_disambiguation",
            "items": list(open_items),
            "prompt": prompt,
            "candidate_target_ids": [line.get("line_id") for line in chosen["targets"] if line.get("line_id")],
        }

    target_ids = {line.get("line_id") for line in chosen["targets"] if line.get("line_id")}
    updated_items: List[Dict[str, Any]] = []
    improved_line_ids: List[str] = []
    for line in open_items:
        if line.get("line_id") not in target_ids:
            updated_items.append(line)
            continue

        merged = merge_followup_dimensions(line, message, knowledge=knowledge)
        new_line = fq.resolve_quote_item(merged, logic, knowledge=knowledge)
        progressed = _line_progressed(line, new_line)
        attempts = int(line.get("clarification_attempts") or 0)
        new_line["clarification_attempts"] = 0 if progressed else attempts + 1
        new_line["last_targeted_dimension"] = _next_targeted_dimension(line, message)
        if progressed:
            improved_line_ids.append(str(line.get("line_id")))
            updated_items.append(new_line)
        else:
            preserved = dict(line)
            preserved["clarification_attempts"] = attempts + 1
            preserved["last_targeted_dimension"] = new_line.get("last_targeted_dimension")
            updated_items.append(preserved)

    return {
        "status": "updated" if improved_line_ids else "no_progress",
        "items": updated_items,
        "target_line_ids": list(target_ids),
        "improved_line_ids": improved_line_ids,
    }


def summarize_remaining_blockers(open_items: List[Dict[str, Any]]) -> str:
    pending = pending_items(open_items)
    if not pending:
        return ""
    if len(pending) == 1:
        item = pending[0]
        return f"Para {item.get('original', item.get('normalized', 'ese item'))}: {item.get('clarification') or item.get('notes') or 'necesito un dato más.'}"
    names = ", ".join(item.get("original", item.get("normalized", "?")).capitalize() for item in pending[:3])
    return f"Todavía faltan definir estos items: {names}."
