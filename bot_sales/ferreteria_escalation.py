from __future__ import annotations

from typing import Any, Dict, List

from bot_sales.ferreteria_continuity import pending_items
from bot_sales.ferreteria_dimensions import extract_dimensions
from bot_sales.ferreteria_family_model import infer_families


MAX_CLARIFICATION_ATTEMPTS = 2
MAX_DISAMBIGUATION_RETRIES = 1

_RECOVERABLE_ISSUES = {
    "missing_dimensions",
    "variant_ambiguity",
    "weak_match",
    "category_fallback",
    "blocked_term",
}
_OPERATOR_ONLY_ISSUES = {
    "catalog_gap",
    "unknown_term",
}


def escalation_reason(item: Dict[str, Any]) -> str:
    issue_type = str(item.get("issue_type") or "")
    if issue_type in _OPERATOR_ONLY_ISSUES:
        return issue_type
    if int(item.get("clarification_attempts") or 0) >= MAX_CLARIFICATION_ATTEMPTS:
        return "clarification_attempts_exhausted"
    return issue_type or "recoverable_pending"


def assess_quote_recoverability(
    open_items: List[Dict[str, Any]],
    message: str,
    knowledge: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pending = pending_items(open_items)
    dims = extract_dimensions(message or "")
    families = infer_families(message or "", knowledge=knowledge)

    if not pending:
        return {
            "operator_required": False,
            "continue_clarifying": False,
            "reason": "",
            "recoverable_lines": [],
            "operator_only_lines": [],
            "prompt": None,
        }

    operator_only: List[Dict[str, Any]] = []
    recoverable: List[Dict[str, Any]] = []
    exhausted: List[Dict[str, Any]] = []

    for item in pending:
        issue_type = str(item.get("issue_type") or "")
        attempts = int(item.get("clarification_attempts") or 0)
        if attempts >= MAX_CLARIFICATION_ATTEMPTS:
            exhausted.append(item)
            continue
        if issue_type in _OPERATOR_ONLY_ISSUES:
            operator_only.append(item)
            continue
        if issue_type in _RECOVERABLE_ISSUES or item.get("family") or item.get("products") or item.get("missing_dimensions"):
            recoverable.append(item)
            continue
        operator_only.append(item)

    if exhausted:
        return {
            "operator_required": True,
            "continue_clarifying": False,
            "reason": "clarification_attempts_exhausted",
            "recoverable_lines": recoverable,
            "operator_only_lines": exhausted + operator_only,
            "prompt": None,
        }

    if operator_only and not recoverable and not dims and not families:
        return {
            "operator_required": True,
            "continue_clarifying": False,
            "reason": escalation_reason(operator_only[0]),
            "recoverable_lines": [],
            "operator_only_lines": operator_only,
            "prompt": None,
        }

    prompt = None
    if recoverable:
        if len(recoverable) == 1:
            item = recoverable[0]
            prompt = f"Para {item.get('original', item.get('normalized', 'ese item'))}: {item.get('clarification') or item.get('notes') or 'necesito un dato más.'}"
        else:
            names = ", ".join(
                item.get("original", item.get("normalized", "?")).capitalize()
                for item in recoverable[:3]
            )
            prompt = f"Todavía faltan definir estos items: {names}. Decime cuál seguimos primero."

    return {
        "operator_required": False,
        "continue_clarifying": bool(recoverable),
        "reason": "recoverable_pending" if recoverable else "operator_review_recommended",
        "recoverable_lines": recoverable,
        "operator_only_lines": operator_only,
        "prompt": prompt,
    }


def should_escalate_quote_case(
    open_items: List[Dict[str, Any]],
    message: str,
    attempts_by_line: Dict[str, int] | None = None,
    knowledge: Dict[str, Any] | None = None,
) -> bool:
    del attempts_by_line
    return bool(assess_quote_recoverability(open_items, message, knowledge=knowledge).get("operator_required"))
