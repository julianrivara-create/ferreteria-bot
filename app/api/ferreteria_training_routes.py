from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, jsonify, request

from app.api.admin_routes import admin_required
from app.api.ferreteria_admin_routes import _tenant_db_path, _tenant_profile
from app.crm.services.rate_limiter import rate_limiter
from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales.knowledge.validators import KnowledgeValidationError
from bot_sales.training.review_service import TrainingReviewService
from bot_sales.training.session_service import TrainingSessionService
from bot_sales.training.store import TrainingStore
from bot_sales.training.suggestion_service import TrainingSuggestionService


ferreteria_training_api = Blueprint("ferreteria_training_api", __name__)

# Rate limiting: max 30 training API calls per minute per IP to prevent brute-force.
_TRAINING_RATE_LIMIT = 30
_TRAINING_RATE_WINDOW = 60


def _training_rate_limit_check() -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    key = f"training_ip:{ip}"
    return rate_limiter.allow(key, limit=_TRAINING_RATE_LIMIT, window_seconds=_TRAINING_RATE_WINDOW)


ALLOWED_SUGGESTION_DOMAINS = {
    "synonym",
    "faq",
    "clarification_rule",
    "family_rule",
    "blocked_term",
    "complementary_rule",
    "substitute_rule",
    "language_pattern",
    "unresolved_term_mapping",
    "test_case_only",
}


def get_training_store() -> TrainingStore:
    return TrainingStore(_tenant_db_path(), tenant_id="ferreteria")


def get_training_services() -> tuple[TrainingStore, TrainingSessionService, TrainingReviewService, TrainingSuggestionService]:
    store = get_training_store()
    profile = _tenant_profile()
    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    return (
        store,
        TrainingSessionService(store, tenant_profile=profile, tenant_id="ferreteria"),
        TrainingReviewService(store),
        TrainingSuggestionService(store, loader),
    )


@ferreteria_training_api.before_request
def training_rate_limit():
    """Block brute-force attempts before they reach admin token validation."""
    if not _training_rate_limit_check():
        return jsonify({"error": "Rate limit exceeded. Max 30 requests/minute per IP."}), 429


def _operator_ref(payload: Dict[str, Any]) -> str | None:
    return request.headers.get("X-Admin-User") or payload.get("operator") or payload.get("created_by")


@ferreteria_training_api.route("/training/sessions", methods=["GET"])
@admin_required
def list_training_sessions():
    store, session_service, _, _ = get_training_services()
    try:
        sessions = session_service.list_sessions(
            status=request.args.get("status"),
            operator_id=request.args.get("operator"),
            mode_profile=request.args.get("mode_profile"),
            model_name=request.args.get("model_name"),
            limit=int(request.args.get("limit", 100)),
        )
        return jsonify({"sessions": sessions})
    finally:
        store.close()


@ferreteria_training_api.route("/training/sessions", methods=["POST"])
@admin_required
def create_training_session():
    payload = request.get_json(silent=True) or {}
    store, session_service, _, _ = get_training_services()
    try:
        session = session_service.create_session(
            operator_id=_operator_ref(payload),
            mode_profile=str(payload.get("mode_profile") or "cheap"),
            token_ceiling=payload.get("token_ceiling"),
        )
        return jsonify({"session": session}), 201
    finally:
        store.close()


@ferreteria_training_api.route("/training/sessions/<session_id>", methods=["GET"])
@admin_required
def get_training_session(session_id: str):
    store, session_service, _, _ = get_training_services()
    try:
        session = session_service.get_session(session_id)
        if not session:
            return jsonify({"error": "Training session not found"}), 404
        return jsonify({"session": session})
    finally:
        store.close()


@ferreteria_training_api.route("/training/sessions/<session_id>/messages", methods=["POST"])
@admin_required
def send_training_message(session_id: str):
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    store, session_service, _, _ = get_training_services()
    try:
        result = session_service.send_message(session_id, message)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/sessions/<session_id>/reset", methods=["POST"])
@admin_required
def reset_training_session(session_id: str):
    payload = request.get_json(silent=True) or {}
    store, session_service, _, _ = get_training_services()
    try:
        new_session = session_service.reset_session(session_id, operator_id=_operator_ref(payload))
        return jsonify({"session": new_session})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    finally:
        store.close()


@ferreteria_training_api.route("/training/sessions/<session_id>/close", methods=["POST"])
@admin_required
def close_training_session(session_id: str):
    store, session_service, _, _ = get_training_services()
    try:
        session = session_service.close_session(session_id)
        return jsonify({"session": session})
    finally:
        store.close()


@ferreteria_training_api.route("/training/cases", methods=["GET"])
@admin_required
def list_training_cases():
    store, _, review_service, _ = get_training_services()
    try:
        cases = review_service.list_cases(
            status=request.args.get("status"),
            review_label=request.args.get("review_label"),
            failure_tag=request.args.get("failure_tag"),
            domain=request.args.get("domain"),
            operator_id=request.args.get("operator"),
            suggested_family=request.args.get("family"),
            repeated_term=request.args.get("repeated_term"),
            limit=int(request.args.get("limit", 200)),
        )
        return jsonify({"cases": cases})
    finally:
        store.close()


@ferreteria_training_api.route("/training/cases/<review_id>", methods=["GET"])
@admin_required
def get_training_case(review_id: str):
    store, _, review_service, _ = get_training_services()
    try:
        detail = review_service.get_case_detail(review_id)
        if not detail:
            return jsonify({"error": "Training case not found"}), 404
        return jsonify({"case": detail})
    finally:
        store.close()


@ferreteria_training_api.route("/training/reviews", methods=["POST"])
@admin_required
def save_training_review():
    payload = request.get_json(silent=True) or {}
    if not payload.get("session_id") or not payload.get("bot_message_id") or not payload.get("review_label"):
        return jsonify({"error": "session_id, bot_message_id and review_label are required"}), 400
    store, _, review_service, _ = get_training_services()
    try:
        review = review_service.save_review(
            session_id=str(payload["session_id"]),
            bot_message_id=str(payload["bot_message_id"]),
            review_label=str(payload["review_label"]),
            failure_tag=payload.get("failure_tag"),
            failure_detail_tag=payload.get("failure_detail_tag"),
            expected_behavior_tag=payload.get("expected_behavior_tag"),
            clarification_dimension=payload.get("clarification_dimension"),
            expected_answer=payload.get("expected_answer"),
            what_was_wrong=payload.get("what_was_wrong"),
            missing_clarification=payload.get("missing_clarification"),
            suggested_family=payload.get("suggested_family"),
            suggested_canonical_product=payload.get("suggested_canonical_product"),
            operator_notes=payload.get("operator_notes"),
            created_by=_operator_ref(payload),
        )
        return jsonify({"review": review})
    finally:
        store.close()


@ferreteria_training_api.route("/training/reviews/<review_id>/suggestions", methods=["POST"])
@admin_required
def create_training_suggestion(review_id: str):
    payload = request.get_json(silent=True) or {}
    domain = str(payload.get("domain") or "").strip()
    if domain not in ALLOWED_SUGGESTION_DOMAINS:
        return jsonify({"error": "Invalid suggestion domain"}), 400
    suggested_payload = payload.get("suggested_payload")
    if not isinstance(suggested_payload, dict):
        return jsonify({"error": "suggested_payload must be an object"}), 400
    store, _, _, suggestion_service = get_training_services()
    try:
        suggestion = suggestion_service.create_suggestion(
            review_id=review_id,
            domain=domain,
            summary=payload.get("summary"),
            source_message=payload.get("source_message"),
            repeated_term=payload.get("repeated_term"),
            suggested_payload=suggested_payload,
            created_by=_operator_ref(payload),
        )
        return jsonify({"suggestion": suggestion}), 201
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/suggestions", methods=["GET"])
@admin_required
def list_training_suggestions():
    store, _, _, suggestion_service = get_training_services()
    try:
        suggestions = suggestion_service.list_suggestions(
            status=request.args.get("status"),
            domain=request.args.get("domain"),
            review_id=request.args.get("review_id"),
            created_by=request.args.get("operator"),
            repeated_term=request.args.get("repeated_term"),
            limit=int(request.args.get("limit", 200)),
        )
        return jsonify({"suggestions": suggestions})
    finally:
        store.close()


@ferreteria_training_api.route("/training/suggestions/<suggestion_id>", methods=["GET"])
@admin_required
def get_training_suggestion(suggestion_id: str):
    store, _, _, suggestion_service = get_training_services()
    try:
        suggestion = suggestion_service.get_suggestion(suggestion_id)
        if not suggestion:
            return jsonify({"error": "Suggestion not found"}), 404
        return jsonify({"suggestion": suggestion})
    finally:
        store.close()


@ferreteria_training_api.route("/training/suggestions/<suggestion_id>/approve", methods=["POST"])
@admin_required
def approve_training_suggestion(suggestion_id: str):
    payload = request.get_json(silent=True) or {}
    store, _, _, suggestion_service = get_training_services()
    try:
        suggestion = suggestion_service.approve(suggestion_id, acted_by=_operator_ref(payload), reason=payload.get("reason"))
        return jsonify({"suggestion": suggestion})
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/suggestions/<suggestion_id>/reject", methods=["POST"])
@admin_required
def reject_training_suggestion(suggestion_id: str):
    payload = request.get_json(silent=True) or {}
    store, _, _, suggestion_service = get_training_services()
    try:
        suggestion = suggestion_service.reject(suggestion_id, acted_by=_operator_ref(payload), reason=payload.get("reason"))
        return jsonify({"suggestion": suggestion})
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/suggestions/<suggestion_id>/apply", methods=["POST"])
@admin_required
def apply_training_suggestion(suggestion_id: str):
    payload = request.get_json(silent=True) or {}
    store, _, _, suggestion_service = get_training_services()
    try:
        suggestion = suggestion_service.apply(suggestion_id, acted_by=_operator_ref(payload), reason=payload.get("reason"))
        return jsonify({"suggestion": suggestion})
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/reviews/<review_id>/export-regression", methods=["POST"])
@admin_required
def export_training_regression(review_id: str):
    payload = request.get_json(silent=True) or {}
    store, _, _, suggestion_service = get_training_services()
    try:
        export = suggestion_service.export_regression_case(review_id, exported_by=_operator_ref(payload))
        return jsonify({"export": export}), 201
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/reviews/<review_id>/regression-candidate", methods=["POST"])
@admin_required
def create_training_regression_candidate(review_id: str):
    payload = request.get_json(silent=True) or {}
    store, _, _, suggestion_service = get_training_services()
    try:
        candidate = suggestion_service.create_regression_candidate(
            review_id,
            created_by=_operator_ref(payload),
            payload_override=payload.get("payload") if isinstance(payload.get("payload"), dict) else None,
            status=str(payload.get("status") or "draft"),
        )
        return jsonify({"candidate": candidate}), 201
    except KnowledgeValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/usage", methods=["GET"])
@admin_required
def get_training_usage():
    store = get_training_store()
    try:
        usage = {
            "session": store.list_usage(metric_scope="session", limit=int(request.args.get("limit", 50))),
            "daily": store.list_usage(metric_scope="daily", limit=31),
            "monthly": store.list_usage(metric_scope="monthly", limit=12),
            "model_distribution": store.list_model_usage(limit=20),
        }
        return jsonify(usage)
    finally:
        store.close()


@ferreteria_training_api.route("/training/unresolved-terms/suggest", methods=["POST"])
@admin_required
def suggest_from_unresolved_term():
    """Crea un borrador rápido desde un término no resuelto y lo devuelve al flujo principal."""
    payload = request.get_json(silent=True) or {}
    term = (payload.get("term") or "").strip()
    domain = str(payload.get("domain") or "synonym").strip() or "synonym"
    canonical = (payload.get("canonical") or term).strip()
    family = (payload.get("family") or "").strip()
    aliases_raw = payload.get("aliases", "")
    aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()] if aliases_raw else []
    summary = payload.get("summary") or f"Corrección de término no resuelto: {term!r}"
    operator = _operator_ref(payload)

    if not term:
        return jsonify({"error": "El campo 'term' es obligatorio"}), 400
    if domain not in {"synonym", "blocked_term", "language_pattern"}:
        return jsonify({"error": "Desde esta pantalla solo podés crear borradores rápidos de término, bloqueo o normalización de lenguaje."}), 400

    if domain == "blocked_term":
        suggested_payload: Dict[str, Any] = {
            "term": term,
            "reason": summary,
            "redirect_prompt": payload.get("redirect_prompt") or "¿Me contás un poco más para qué lo necesitás?",
            "family": family,
        }
    elif domain == "language_pattern":
        suggested_payload = {
            "section": payload.get("language_section") or "errores",
            "key": term,
            "value": canonical,
        }
    else:
        suggested_payload = {
            "canonical": canonical,
            "family": family,
            "aliases": [term] + [a for a in aliases if a != term],
            "misspellings": [],
            "brand_generic": False,
        }

    store, _, _, suggestion_service = get_training_services()
    try:
        orphan_review = store.create_orphan_review(
            term=term,
            context=summary,
            label="unknown_term",
            created_by=operator,
        )
        review_id = orphan_review["id"]
        suggestion = suggestion_service.create(
            review_id=review_id,
            domain=domain,
            summary=summary,
            source_message=term,
            repeated_term=term,
            suggested_payload=suggested_payload,
            created_by=operator,
        )
        return jsonify(
            {
                "review": orphan_review,
                "review_id": review_id,
                "case_url": f"/ops/ferreteria/training/cases/{review_id}",
                "suggestion": suggestion,
                "suggestion_url": f"/ops/ferreteria/training/suggestions/{suggestion['id']}",
            }
        ), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        store.close()


@ferreteria_training_api.route("/training/impact", methods=["GET"])
@admin_required
def get_training_impact():
    """Métricas de impacto: resumen de entrenamiento y comparativa antes/después de cada apply."""
    store = get_training_store()
    try:
        metrics = store.get_impact_metrics()
        metrics["impact_rows"] = store.get_impact_rows()
        return jsonify({"impact": metrics})
    finally:
        store.close()
