from __future__ import annotations

import yaml
from flask import Blueprint, redirect, render_template, request, url_for

from app.api.admin_routes import admin_required
from app.api.ferreteria_admin_routes import (
    ALLOWED_KNOWLEDGE_DOMAINS,
    get_knowledge_loader,
    get_quote_automation_service,
    get_quote_store,
)
from bot_sales.knowledge.validators import KnowledgeValidationError
from bot_sales.persistence.quote_store import utc_now_iso
from bot_sales.services.quote_automation_service import QuoteAutomationError


ferreteria_admin_ui = Blueprint(
    "ferreteria_admin_ui",
    __name__,
    template_folder="templates",
)


@ferreteria_admin_ui.route("/ops/ferreteria")
@admin_required
def ferreteria_ops_home():
    return redirect(url_for("ferreteria_admin_ui.ferreteria_quotes_page"))


@ferreteria_admin_ui.route("/ops/ferreteria/quotes", methods=["GET"])
@admin_required
def ferreteria_quotes_page():
    store = get_quote_store()
    automation_states = request.args.getlist("automation_state") or None
    quotes = store.list_quotes(
        statuses=["review_requested", "under_internal_review", "revision_requested", "ready_for_followup"],
        automation_states=automation_states,
        limit=100,
    )
    return render_template("ferreteria_admin/quotes.html", quotes=quotes, automation_states=automation_states or [])


@ferreteria_admin_ui.route("/ops/ferreteria/quotes/<quote_id>", methods=["GET", "POST"])
@admin_required
def ferreteria_quote_detail_page(quote_id: str):
    store = get_quote_store()
    if request.method == "POST":
        action = request.form.get("action")
        operator = request.headers.get("X-Admin-User") or request.form.get("operator") or "operator"
        automation_service = get_quote_automation_service()
        if action == "status":
            status = request.form.get("status", "").strip()
            fields = {"status": status}
            if status.startswith("closed_"):
                fields["closed_at"] = utc_now_iso()
            store.update_quote_header(quote_id, **fields)
            store.append_event(quote_id, "quote_status_changed", "operator", actor_ref=operator, payload={"status": status})
            try:
                automation_service.refresh_quote_automation(quote_id, actor=operator)
            except QuoteAutomationError:
                pass
        elif action == "claim":
            quote = store.get_quote(quote_id) or {}
            queue_handoff = next((h for h in quote.get("handoffs", []) if h.get("destination_type") == "admin_queue"), None)
            if queue_handoff:
                store.update_handoff(queue_handoff["id"], status="claimed", claimed_by=operator, claimed_at=utc_now_iso())
            store.update_quote_header(quote_id, status="under_internal_review")
            store.append_event(quote_id, "operator_claimed", "operator", actor_ref=operator, payload={})
            try:
                automation_service.refresh_quote_automation(quote_id, actor=operator)
            except QuoteAutomationError:
                pass
        elif action == "note":
            note = request.form.get("note", "").strip()
            if note:
                store.append_event(quote_id, "operator_note", "operator", actor_ref=operator, payload={"note": note})
        elif action == "automation_evaluate":
            automation_service.refresh_quote_automation(quote_id, actor=operator)
        elif action == "automation_send":
            automation_service.send_quote_ready_followup(quote_id, actor=operator)
        elif action == "automation_block":
            reason = request.form.get("automation_reason", "").strip() or "operator_blocked"
            automation_service.block_automation(quote_id, reason=reason, actor=operator)
        elif action == "automation_reset":
            automation_service.reset_automation(quote_id, actor=operator)
        return redirect(url_for("ferreteria_admin_ui.ferreteria_quote_detail_page", quote_id=quote_id))

    quote = store.get_quote(quote_id)
    return render_template("ferreteria_admin/quote_detail.html", quote=quote)


@ferreteria_admin_ui.route("/ops/ferreteria/unresolved-terms", methods=["GET", "POST"])
@admin_required
def ferreteria_unresolved_terms_page():
    store = get_quote_store()
    if request.method == "POST":
        unresolved_id = request.form.get("unresolved_id", "").strip()
        if unresolved_id:
            store.review_unresolved_term(
                unresolved_id,
                review_status=request.form.get("review_status", "acknowledged"),
                reviewed_by=request.headers.get("X-Admin-User") or request.form.get("reviewed_by"),
                resolution_note=request.form.get("resolution_note"),
                linked_knowledge_domain=request.form.get("linked_knowledge_domain"),
                linked_knowledge_key=request.form.get("linked_knowledge_key"),
            )
        return redirect(url_for("ferreteria_admin_ui.ferreteria_unresolved_terms_page"))

    items = store.list_unresolved_terms(limit=200)
    return render_template("ferreteria_admin/unresolved_terms.html", items=items)


@ferreteria_admin_ui.route("/ops/ferreteria/knowledge/<domain>", methods=["GET", "POST"])
@admin_required
def ferreteria_knowledge_page(domain: str):
    if domain not in ALLOWED_KNOWLEDGE_DOMAINS:
        return "Unknown knowledge domain", 404

    loader = get_knowledge_loader()
    error = None
    if request.method == "POST":
        raw_payload = request.form.get("payload", "")
        changed_by = request.headers.get("X-Admin-User") or request.form.get("changed_by")
        change_reason = request.form.get("change_reason")
        try:
            payload = yaml.safe_load(raw_payload) or {}
            before = loader.get_domain(domain)
            validated = loader.save_domain(domain, payload)
            store = get_quote_store()
            store.record_knowledge_change(
                domain=domain,
                entity_key=domain,
                action="update",
                before=before,
                after=validated,
                changed_by=changed_by,
                change_reason=change_reason,
            )
            return redirect(url_for("ferreteria_admin_ui.ferreteria_knowledge_page", domain=domain))
        except (KnowledgeValidationError, yaml.YAMLError) as exc:
            error = str(exc)

    payload = loader.get_domain(domain)
    payload_yaml = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return render_template(
        "ferreteria_admin/knowledge_editor.html",
        domain=domain,
        payload_yaml=payload_yaml,
        error=error,
        domains=sorted(ALLOWED_KNOWLEDGE_DOMAINS),
    )


@ferreteria_admin_ui.route("/ops/ferreteria/knowledge/synonyms", methods=["GET", "POST"])
@admin_required
def ferreteria_synonyms_page():
    return ferreteria_knowledge_page("synonyms")


@ferreteria_admin_ui.route("/ops/ferreteria/knowledge/clarifications", methods=["GET", "POST"])
@admin_required
def ferreteria_clarifications_page():
    return ferreteria_knowledge_page("clarifications")


@ferreteria_admin_ui.route("/ops/ferreteria/knowledge/faqs", methods=["GET", "POST"])
@admin_required
def ferreteria_faqs_page():
    return ferreteria_knowledge_page("faqs")
