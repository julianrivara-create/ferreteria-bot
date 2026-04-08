from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from app.api.admin_routes import admin_required
from bot_sales.core.tenancy import tenant_manager
from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales.knowledge.validators import KnowledgeValidationError
from bot_sales.persistence.quote_store import QuoteStore, utc_now_iso
from bot_sales.services.quote_automation_service import QuoteAutomationError, QuoteAutomationService


ferreteria_admin_api = Blueprint("ferreteria_admin_api", __name__)

ALLOWED_QUOTE_STATUSES = {
    "review_requested",
    "under_internal_review",
    "revision_requested",
    "ready_for_followup",
    "closed_completed",
    "closed_cancelled",
}

ALLOWED_KNOWLEDGE_DOMAINS = {
    "synonyms",
    "clarifications",
    "families",
    "blocked_terms",
    "complementary",
    "substitute_rules",
    "language_patterns",
    "acceptance",
    "faqs",
}


def _tenant_profile() -> Dict[str, Any]:
    tenant = tenant_manager.get_tenant_by_slug("ferreteria") or tenant_manager.get_tenant("ferreteria")
    return dict(getattr(tenant, "profile", {}) or {})


def _tenant_db_path() -> str:
    tenant = tenant_manager.get_tenant_by_slug("ferreteria") or tenant_manager.get_tenant("ferreteria")
    db_file = getattr(tenant, "db_file", "data/ferreteria.db")
    path = Path(db_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / db_file
    return str(path)


def get_quote_store() -> QuoteStore:
    return QuoteStore(_tenant_db_path(), tenant_id="ferreteria")


def get_knowledge_loader() -> KnowledgeLoader:
    return KnowledgeLoader(tenant_id="ferreteria", tenant_profile=_tenant_profile())


def get_quote_automation_service() -> QuoteAutomationService:
    return QuoteAutomationService(
        get_quote_store(),
        tenant_id="ferreteria",
        tenant_profile=_tenant_profile(),
    )


def _quote_payload(store: QuoteStore, quote_id: str) -> Dict[str, Any] | None:
    quote = store.get_quote(quote_id)
    if not quote:
        return None
    return quote


@ferreteria_admin_api.route("/quotes", methods=["GET"])
@admin_required
def list_quotes():
    statuses = request.args.getlist("status") or [
        "review_requested",
        "under_internal_review",
        "revision_requested",
        "ready_for_followup",
    ]
    automation_states = request.args.getlist("automation_state") or None
    store = get_quote_store()
    quotes = store.list_quotes(
        statuses=statuses,
        automation_states=automation_states,
        limit=int(request.args.get("limit", 100)),
    )
    return jsonify({"quotes": quotes})


@ferreteria_admin_api.route("/quotes/<quote_id>", methods=["GET"])
@admin_required
def get_quote_detail(quote_id: str):
    store = get_quote_store()
    quote = _quote_payload(store, quote_id)
    if not quote:
        return jsonify({"error": "Quote not found"}), 404
    return jsonify(quote)


@ferreteria_admin_api.route("/quotes/<quote_id>/status", methods=["POST"])
@admin_required
def update_quote_status(quote_id: str):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status") or "").strip()
    if status not in ALLOWED_QUOTE_STATUSES:
        return jsonify({"error": "Invalid status"}), 400

    store = get_quote_store()
    quote = _quote_payload(store, quote_id)
    if not quote:
        return jsonify({"error": "Quote not found"}), 404

    update_fields: Dict[str, Any] = {"status": status}
    if status.startswith("closed_"):
        update_fields["closed_at"] = utc_now_iso()
    store.update_quote_header(quote_id, **update_fields)
    operator = request.headers.get("X-Admin-User") or payload.get("operator")
    store.append_event(
        quote_id,
        "quote_status_changed",
        "operator",
        actor_ref=operator,
        payload={"status": status, "note": payload.get("note")},
    )
    try:
        get_quote_automation_service().refresh_quote_automation(quote_id, actor=operator or "operator")
    except QuoteAutomationError:
        pass
    return jsonify({"status": "ok", "quote": _quote_payload(store, quote_id)})


@ferreteria_admin_api.route("/quotes/<quote_id>/claim", methods=["POST"])
@admin_required
def claim_quote(quote_id: str):
    payload = request.get_json(silent=True) or {}
    operator = request.headers.get("X-Admin-User") or payload.get("operator") or "operator"
    store = get_quote_store()
    quote = _quote_payload(store, quote_id)
    if not quote:
        return jsonify({"error": "Quote not found"}), 404

    queue_handoff = next((h for h in quote.get("handoffs", []) if h.get("destination_type") == "admin_queue"), None)
    if queue_handoff:
        store.update_handoff(
            queue_handoff["id"],
            status="claimed",
            claimed_by=operator,
            claimed_at=utc_now_iso(),
        )
    store.update_quote_header(quote_id, status="under_internal_review")
    store.append_event(quote_id, "operator_claimed", "operator", actor_ref=operator, payload={})
    try:
        get_quote_automation_service().refresh_quote_automation(quote_id, actor=operator)
    except QuoteAutomationError:
        pass
    return jsonify({"status": "ok", "quote": _quote_payload(store, quote_id)})


@ferreteria_admin_api.route("/quotes/<quote_id>/note", methods=["POST"])
@admin_required
def add_quote_note(quote_id: str):
    payload = request.get_json(silent=True) or {}
    note = str(payload.get("note") or "").strip()
    if not note:
        return jsonify({"error": "note is required"}), 400
    store = get_quote_store()
    quote = _quote_payload(store, quote_id)
    if not quote:
        return jsonify({"error": "Quote not found"}), 404
    operator = request.headers.get("X-Admin-User") or payload.get("operator")
    store.append_event(quote_id, "operator_note", "operator", actor_ref=operator, payload={"note": note})
    return jsonify({"status": "ok"})


@ferreteria_admin_api.route("/unresolved-terms", methods=["GET"])
@admin_required
def list_unresolved_terms():
    store = get_quote_store()
    review_status = request.args.get("review_status")
    rows = store.list_unresolved_terms(review_status=review_status, limit=int(request.args.get("limit", 200)))
    return jsonify({"items": rows})


@ferreteria_admin_api.route("/unresolved-terms/<unresolved_id>/review", methods=["POST"])
@admin_required
def review_unresolved_term(unresolved_id: str):
    payload = request.get_json(silent=True) or {}
    review_status = str(payload.get("review_status") or "").strip()
    if not review_status:
        return jsonify({"error": "review_status is required"}), 400
    store = get_quote_store()
    store.review_unresolved_term(
        unresolved_id,
        review_status=review_status,
        reviewed_by=request.headers.get("X-Admin-User") or payload.get("reviewed_by"),
        resolution_note=payload.get("resolution_note"),
        linked_knowledge_domain=payload.get("linked_knowledge_domain"),
        linked_knowledge_key=payload.get("linked_knowledge_key"),
        inferred_family=payload.get("inferred_family"),
        missing_dimensions=payload.get("missing_dimensions"),
        issue_type=payload.get("issue_type"),
    )
    return jsonify({"status": "ok"})


@ferreteria_admin_api.route("/knowledge/<domain>", methods=["GET"])
@admin_required
def get_knowledge(domain: str):
    if domain not in ALLOWED_KNOWLEDGE_DOMAINS:
        return jsonify({"error": "Unknown knowledge domain"}), 404
    loader = get_knowledge_loader()
    return jsonify(loader.get_domain(domain))


@ferreteria_admin_api.route("/knowledge/<domain>", methods=["PUT"])
@admin_required
def update_knowledge(domain: str):
    if domain not in ALLOWED_KNOWLEDGE_DOMAINS:
        return jsonify({"error": "Unknown knowledge domain"}), 404

    payload = request.get_json(silent=True) or {}
    new_data = payload.get("data")
    if not isinstance(new_data, dict):
        return jsonify({"error": "data must be an object"}), 400

    loader = get_knowledge_loader()
    store = get_quote_store()
    before = loader.get_domain(domain)
    try:
        validated = loader.save_domain(domain, new_data)
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    changed_by = request.headers.get("X-Admin-User") or payload.get("changed_by")
    store.record_knowledge_change(
        domain=domain,
        entity_key=domain,
        action="update",
        before=before,
        after=validated,
        changed_by=changed_by,
        change_reason=payload.get("change_reason"),
    )
    return jsonify({"status": "ok", "data": validated})


@ferreteria_admin_api.route("/knowledge/reload", methods=["POST"])
@admin_required
def reload_knowledge():
    loader = get_knowledge_loader()
    loader.invalidate()
    return jsonify({"status": "reloaded", "paths": loader.get_paths()})


@ferreteria_admin_api.route("/quotes/<quote_id>/automation/evaluate", methods=["POST"])
@admin_required
def evaluate_quote_automation(quote_id: str):
    actor = request.headers.get("X-Admin-User") or (request.get_json(silent=True) or {}).get("operator") or "operator"
    try:
        result = get_quote_automation_service().refresh_quote_automation(quote_id, actor=actor)
    except QuoteAutomationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"status": "ok", "quote": result["quote"], "decision": result["decision"]})


@ferreteria_admin_api.route("/quotes/<quote_id>/automation/send", methods=["POST"])
@admin_required
def send_quote_automation(quote_id: str):
    actor = request.headers.get("X-Admin-User") or (request.get_json(silent=True) or {}).get("operator") or "operator"
    try:
        result = get_quote_automation_service().send_quote_ready_followup(quote_id, actor=actor)
    except QuoteAutomationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"status": "ok", "quote": result["quote"], "send_result": result["send_result"]})


@ferreteria_admin_api.route("/quotes/<quote_id>/automation/block", methods=["POST"])
@admin_required
def block_quote_automation(quote_id: str):
    payload = request.get_json(silent=True) or {}
    actor = request.headers.get("X-Admin-User") or payload.get("operator") or "operator"
    reason = str(payload.get("reason") or "").strip() or "operator_blocked"
    try:
        result = get_quote_automation_service().block_automation(quote_id, reason=reason, actor=actor)
    except QuoteAutomationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"status": "ok", "quote": result["quote"]})


@ferreteria_admin_api.route("/quotes/<quote_id>/automation/reset", methods=["POST"])
@admin_required
def reset_quote_automation(quote_id: str):
    actor = request.headers.get("X-Admin-User") or (request.get_json(silent=True) or {}).get("operator") or "operator"
    try:
        result = get_quote_automation_service().reset_automation(quote_id, actor=actor)
    except QuoteAutomationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"status": "ok", "quote": result["quote"]})
