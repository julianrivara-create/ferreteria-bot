from __future__ import annotations

from typing import Any, Dict, List, Optional


SAFE_FAMILY_ALLOWLIST = {
    "silicona",
    "teflon",
    "cano",
    "pintura",
    "rodillo",
    "guante",
    "tornillo",
    "tarugo",
    "taco",
    "mecha",
    "broca",
}

BLOCKING_LINE_STATUSES = {"ambiguous", "unresolved", "blocked_by_missing_info"}
OPERATOR_ONLY_ISSUES = {"catalog_gap", "unknown_term"}
HUMAN_REVIEW_STATUSES = {"review_requested", "under_internal_review", "revision_requested"}
MANUAL_ONLY_STATUSES = {"open", "waiting_customer_input", "closed_completed", "closed_cancelled"}
MAX_AUTOMATION_LINES = 3


def is_family_automation_safe(family_id: str | None, knowledge: Dict[str, Any] | None = None) -> bool:
    family = str(family_id or "").strip()
    if not family:
        return False
    family_rule = (((knowledge or {}).get("families") or {}).get("families") or {}).get(family) or {}
    profile = str(family_rule.get("automation_profile") or "").strip().lower()
    if profile == "safe_followup":
        return True
    if profile == "manual_only":
        return False
    return family in SAFE_FAMILY_ALLOWLIST


def build_automation_risk_flags(quote: Dict[str, Any], items: List[Dict[str, Any]], knowledge: Dict[str, Any] | None = None) -> List[str]:
    flags: List[str] = []
    status = str(quote.get("status") or "")
    channel = str(quote.get("channel") or "")

    if status in HUMAN_REVIEW_STATUSES:
        flags.append("human_review_status")
    elif status in MANUAL_ONLY_STATUSES:
        flags.append("not_ready_for_followup")

    if not items:
        flags.append("no_quote_lines")
    if len(items) > MAX_AUTOMATION_LINES:
        flags.append("line_count_exceeded")
    if channel != "whatsapp":
        flags.append("unsupported_channel")
    if not str(quote.get("customer_ref") or "").strip():
        flags.append("missing_customer_ref")
    if int(quote.get("auto_followup_count") or 0) > 0 or quote.get("last_auto_followup_at"):
        flags.append("already_followed_up")

    for item in items:
        line_status = str(item.get("status") or "")
        if line_status in BLOCKING_LINE_STATUSES:
            flags.append("blocking_line_status")
        issue_type = str(item.get("issue_type") or "")
        if issue_type in OPERATOR_ONLY_ISSUES:
            flags.append(f"operator_only:{issue_type}")
        if int(item.get("clarification_attempts") or 0) >= 2:
            flags.append("clarification_attempts_exhausted")
        if item.get("selected_via_substitute"):
            flags.append("substitute_selected")
        if item.get("pack_note"):
            flags.append("presentation_confirmation_required")
        if item.get("unit_price") is None:
            flags.append("missing_unit_price")
        if not is_family_automation_safe(item.get("family"), knowledge=knowledge):
            flags.append(f"unsafe_family:{item.get('family') or 'unknown'}")

    deduped: List[str] = []
    for flag in flags:
        if flag not in deduped:
            deduped.append(flag)
    return deduped


def build_quote_ready_followup(quote: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    line_count = len(items)
    total = quote.get("resolved_total_amount")
    total_text = f" Total estimado: ${int(total):,}.".replace(",", ".") if isinstance(total, int) else ""
    lines_text = "1 item" if line_count == 1 else f"{line_count} items"
    return (
        f"Hola. Ya tenemos tu presupuesto listo para {lines_text}.{total_text}\n\n"
        "Si querés seguir, respondé con una de estas opciones:\n"
        "- Confirmo\n"
        "- Quiero cambiar algo\n"
        "- Quiero agregar otro item"
    )


def evaluate_quote_automation(
    quote: Dict[str, Any],
    items: List[Dict[str, Any]],
    knowledge: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status = str(quote.get("status") or "")
    risk_flags = build_automation_risk_flags(quote, items, knowledge=knowledge)
    followup_type = "quote_ready_followup"

    if status in MANUAL_ONLY_STATUSES:
        reason = "not_ready_for_followup"
        return {
            "eligible": False,
            "automation_state": "manual_only",
            "blocked_reason": reason,
            "followup_type": None,
            "risk_flags": risk_flags,
            "decision_summary": "Quote is not in a follow-up-ready state.",
            "ready_for_send": False,
        }

    if status in HUMAN_REVIEW_STATUSES:
        reason = "human_review_required"
        return {
            "eligible": False,
            "automation_state": "automation_blocked",
            "blocked_reason": reason,
            "followup_type": None,
            "risk_flags": risk_flags,
            "decision_summary": "Quote is still inside a human-review path.",
            "ready_for_send": False,
        }

    if status != "ready_for_followup":
        reason = "unsupported_quote_status"
        return {
            "eligible": False,
            "automation_state": "manual_only",
            "blocked_reason": reason,
            "followup_type": None,
            "risk_flags": risk_flags,
            "decision_summary": "Quote is not eligible for automation in its current status.",
            "ready_for_send": False,
        }

    blocking_flags = [flag for flag in risk_flags if flag != "not_ready_for_followup"]
    if blocking_flags:
        reason = blocking_flags[0]
        return {
            "eligible": False,
            "automation_state": "automation_blocked",
            "blocked_reason": reason,
            "followup_type": None,
            "risk_flags": risk_flags,
            "decision_summary": "Automation blocked due to quote/channel/risk conditions.",
            "ready_for_send": False,
        }

    return {
        "eligible": True,
        "automation_state": "eligible_for_auto_followup",
        "blocked_reason": None,
        "followup_type": followup_type,
        "risk_flags": [],
        "decision_summary": "Quote is clean and ready for the standard safe follow-up.",
        "ready_for_send": True,
    }
