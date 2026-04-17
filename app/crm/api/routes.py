from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, Response, g, jsonify, request, stream_with_context
from pydantic import ValidationError
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.crm.api.auth import crm_auth_required, parse_pagination_args, permission_required, rate_limited
from app.crm.domain.enums import AutomationTrigger, DealStatus, MessageDirection, TaskStatus, UserRole
from app.crm.domain.permissions import Permission, has_permission
from app.crm.domain.schemas import (
    AssignmentRequest,
    AutomationCreate,
    AutomationUpdate,
    ContactCreate,
    ContactUpdate,
    DealCreate,
    InventorySignalCreate,
    DealUpdate,
    LoginRequest,
    NoteCreate,
    PlaybookCreate,
    PlaybookUpdate,
    ScoringRuleCreate,
    TagCreate,
    TaskCreate,
    TaskUpdate,
    TenantSettingsUpdate,
    UserCreate,
    UserUpdate,
    WhatsAppTemplateApproval,
    WhatsAppTemplateCreate,
    WhatsAppTemplateUpdate,
)
from app.crm.models import (
    CRMAutomation,
    CRMAutomationRun,
    CRMContact,
    CRMConversation,
    CRMDeal,
    CRMDealEvent,
    CRMLeadAssignmentRule,
    CRMMessage,
    CRMMessageEvent,
    CRMNote,
    CRMOrder,
    CRMOutboundDraft,
    CRMPipelineStage,
    CRMPlaybook,
    CRMSegment,
    CRMSLABreach,
    CRMScoringRule,
    CRMTag,
    CRMTask,
    CRMTaskEvent,
    CRMTenant,
    CRMUser,
    CRMWebhookEvent,
    CRMWhatsAppTemplate,
)
from app.crm.repositories.automations import AutomationRepository
from app.crm.repositories.contacts import ContactRepository
from app.crm.repositories.deals import DealRepository
from app.crm.repositories.tasks import TaskRepository
from app.crm.repositories.users import UserRepository
from app.crm.repositories.webhooks import WebhookEventRepository
from app.crm.services.assignment_service import AssignmentError, AssignmentService
from app.crm.services.ab_variant_service import ABVariantService, merge_sales_policy
from app.crm.services.audit_service import AuditService
from app.crm.services.auth_service import CRMAuthService
from app.crm.services.automation_service import AutomationService
from app.crm.services.clv_service import CLVService
from app.crm.services.inventory_signal_service import InventorySignalService
from app.crm.services.playbook_service import PlaybookService
from app.crm.services.reporting_service import ReportingService
from app.crm.services.scoring_service import ScoringService
from app.crm.services.tenant_settings import (
    get_tenant_crm_webhook_secret,
    merge_integration_settings,
    redact_integration_settings,
)
from app.crm.time import utc_now, utc_now_naive
from app.crm.services.sla_service import SLAService
from app.crm.services.webhook_service import WebhookIngestionService
from app.crm.services.whatsapp_template_service import WhatsAppTemplateService
from app.crm.services.normalization import normalize_email, normalize_phone_e164
from app.db.session import SessionLocal


crm_api = Blueprint("crm_api", __name__)
auth_service = CRMAuthService()
settings = get_settings()
logger = logging.getLogger(__name__)


def _json_error(message: str, status: int = 400) -> tuple[Response, int]:
    return jsonify({"error": message}), status


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _contact_to_dict(contact: CRMContact) -> dict[str, Any]:
    return {
        "id": contact.id,
        "tenant_id": contact.tenant_id,
        "name": contact.name,
        "phone": contact.phone,
        "email": contact.email,
        "source_channel": contact.source_channel,
        "status": contact.status,
        "score": contact.score,
        "owner_user_id": contact.owner_user_id,
        "primary_deal_id": contact.primary_deal_id,
        "last_activity_at": _serialize_datetime(contact.last_activity_at),
        "metadata": contact.metadata_json,
        "created_at": _serialize_datetime(contact.created_at),
        "updated_at": _serialize_datetime(contact.updated_at),
    }


def _deal_to_dict(deal: CRMDeal) -> dict[str, Any]:
    status = deal.status.value if hasattr(deal.status, "value") else str(deal.status)
    return {
        "id": deal.id,
        "tenant_id": deal.tenant_id,
        "contact_id": deal.contact_id,
        "stage_id": deal.stage_id,
        "owner_user_id": deal.owner_user_id,
        "title": deal.title,
        "status": status,
        "score": deal.score,
        "amount_estimated": deal.amount_estimated,
        "amount_final": deal.amount_final,
        "currency": deal.currency,
        "source_channel": deal.source_channel,
        "expected_close_at": _serialize_datetime(deal.expected_close_at),
        "closed_at": _serialize_datetime(deal.closed_at),
        "last_activity_at": _serialize_datetime(deal.last_activity_at),
        "last_stage_changed_at": _serialize_datetime(deal.last_stage_changed_at),
        "metadata": deal.metadata_json,
        "created_at": _serialize_datetime(deal.created_at),
        "updated_at": _serialize_datetime(deal.updated_at),
    }


def _task_to_dict(task: CRMTask) -> dict[str, Any]:
    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    return {
        "id": task.id,
        "tenant_id": task.tenant_id,
        "contact_id": task.contact_id,
        "deal_id": task.deal_id,
        "assigned_to_user_id": task.assigned_to_user_id,
        "created_by_user_id": task.created_by_user_id,
        "title": task.title,
        "description": task.description,
        "status": status,
        "priority": task.priority,
        "due_at": _serialize_datetime(task.due_at),
        "reminder_at": _serialize_datetime(task.reminder_at),
        "completed_at": _serialize_datetime(task.completed_at),
        "metadata": task.metadata_json,
        "created_at": _serialize_datetime(task.created_at),
        "updated_at": _serialize_datetime(task.updated_at),
    }


def _user_to_dict(user: CRMUser) -> dict[str, Any]:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": role,
        "is_active": user.is_active,
        "last_login_at": _serialize_datetime(user.last_login_at),
        "created_at": _serialize_datetime(user.created_at),
    }


def _parse_schema(schema_cls, data: dict):
    try:
        return schema_cls.model_validate(data)
    except ValidationError as exc:
        raise ValueError(exc.errors()) from exc


def _get_session() -> Session:
    return SessionLocal()


def _tenant_from_auth() -> str:
    user = getattr(g, "crm_user", None)
    if not user:
        raise RuntimeError("Missing authenticated user")
    return user["tenant_id"]


def _actor_user_id() -> str | None:
    user = getattr(g, "crm_user", None)
    return user["id"] if user else None


def _tenant_query(session: Session, tenant_id: str, model: Any, *, include_deleted: bool = False):
    if not hasattr(model, "tenant_id"):
        raise ValueError(f"{model} is not tenant scoped")
    query = session.query(model).filter(getattr(model, "tenant_id") == tenant_id)
    if not include_deleted and hasattr(model, "deleted_at"):
        query = query.filter(getattr(model, "deleted_at").is_(None))
    return query


def _map_metadata_field(payload: dict[str, Any]) -> dict[str, Any]:
    if "metadata" in payload:
        payload = {**payload}
        payload["metadata_json"] = payload.pop("metadata")
    return payload


def _sales_policy(session: Session, tenant_id: str) -> dict[str, Any]:
    tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
    integration = dict((tenant.integration_settings or {}) if tenant else {})
    sales_policy_raw = integration.get("sales_policy")
    if not isinstance(sales_policy_raw, dict):
        sales_policy_raw = {}
    policy = merge_sales_policy(sales_policy_raw)
    return policy


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_sales_intelligence(
    payload: dict[str, Any],
    *,
    ab_variant: str | None = None,
    variant_key: str | None = None,
    fallback_stage: str | None = None,
    fallback_intent: str | None = None,
) -> dict[str, Any]:
    raw = payload.get("sales_intelligence_v1")
    source = raw if isinstance(raw, dict) else {}
    missing_fields = source.get("missing_fields", payload.get("missing_fields", []))
    if not isinstance(missing_fields, list):
        missing_fields = []
    confidence = source.get("confidence", payload.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, _to_float(confidence, 0.0)))
    return {
        "schema": "sales_intelligence_v1",
        "intent": source.get("intent") or payload.get("intent") or fallback_intent,
        "stage": source.get("stage") or payload.get("stage") or fallback_stage,
        "missing_fields": missing_fields,
        "objection_type": source.get("objection_type") or payload.get("objection_type"),
        "confidence": confidence,
        "ab_variant": source.get("ab_variant") or payload.get("ab_variant") or ab_variant,
        "variant_key": source.get("variant_key") or payload.get("variant_key") or variant_key,
        "playbook_snippet": source.get("playbook_snippet") or payload.get("playbook_snippet"),
        "needs_handoff": bool(source.get("needs_handoff") or payload.get("needs_handoff")),
        "cta_type": source.get("cta_type") or payload.get("cta_type"),
    }


def _segment_key(channel: str | None, stage: str | None, objection_type: str | None) -> str:
    return f"{channel or 'unknown'}|{stage or 'unknown'}|{objection_type or 'NONE'}"


def _forced_ab_variant_from_policy(
    policy: dict[str, Any],
    *,
    channel: str | None,
    stage: str | None,
    objection_type: str | None,
) -> str | None:
    winners = policy.get("ab_winners")
    if not isinstance(winners, dict):
        return None
    chosen = winners.get(_segment_key(channel, stage, objection_type))
    if chosen in {"A", "B"}:
        return chosen
    return None


def _discount_guardrail_decision(
    *,
    policy: dict[str, Any],
    payload: dict[str, Any],
    sales_meta: dict[str, Any],
) -> dict[str, Any]:
    proposed = payload.get("proposed_discount_percent")
    if proposed is None:
        return {"evaluated": False}

    stage = str(sales_meta.get("stage") or payload.get("stage") or "QUALIFIED").upper()
    caps = policy.get("discount_caps_by_stage") if isinstance(policy.get("discount_caps_by_stage"), dict) else {}
    max_allowed = _to_float(caps.get(stage, 0), 0.0)

    high_intent_threshold = _to_float(policy.get("high_intent_handoff_threshold"), 80.0)
    score = _to_float(payload.get("score"), 0.0)
    is_high_intent = bool(payload.get("high_intent")) or score >= high_intent_threshold or (
        str(sales_meta.get("intent") or "") in {"HIGH_INTENT_SIGNAL", "BUYING_SIGNAL"}
    )

    low_stock_threshold = _to_int(policy.get("low_stock_threshold"), 3)
    stock_available = _to_int(payload.get("stock_available", payload.get("quantity_available", 0)), 0)
    is_low_stock = stock_available > 0 and stock_available <= low_stock_threshold
    if is_high_intent and is_low_stock:
        max_allowed = max(max_allowed, 8.0)

    proposed_value = _to_float(proposed, 0.0)
    blocked = proposed_value > max_allowed
    return {
        "evaluated": True,
        "proposed_discount_percent": round(proposed_value, 2),
        "max_allowed_discount_percent": round(max_allowed, 2),
        "blocked": blocked,
        "is_high_intent": is_high_intent,
        "is_low_stock": is_low_stock,
    }


def _is_owner_or_admin() -> bool:
    user = getattr(g, "crm_user", None) or {}
    return bool(
        has_permission(user.get("role"), Permission.SETTINGS_WRITE)
        and (user.get("role") in {UserRole.OWNER.value, UserRole.ADMIN.value})
    )


def _parse_occurred_at(value: Any, *, fallback: datetime | None = None) -> datetime:
    fallback_value = fallback or utc_now()
    if value is None:
        return fallback_value
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return fallback_value
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return fallback_value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _max_timestamp(current: datetime | None, candidate: datetime) -> datetime:
    candidate_utc = _parse_occurred_at(candidate)
    if current is None:
        return candidate_utc.replace(tzinfo=None)
    current_utc = _parse_occurred_at(current)
    if candidate_utc >= current_utc:
        return candidate_utc.replace(tzinfo=None)
    return current_utc.replace(tzinfo=None)


def _effective_deal_activity(deal: CRMDeal) -> datetime:
    if deal.last_activity_at:
        return _parse_occurred_at(deal.last_activity_at)
    if deal.last_stage_changed_at:
        return _parse_occurred_at(deal.last_stage_changed_at)
    if deal.updated_at:
        return _parse_occurred_at(deal.updated_at)
    if deal.created_at:
        return _parse_occurred_at(deal.created_at)
    return datetime.min.replace(tzinfo=timezone.utc)


def _refresh_primary_deal_id(
    session: Session,
    tenant_id: str,
    contact: CRMContact,
    *,
    event_occurred_at: datetime | None = None,
) -> None:
    deals = (
        _tenant_query(session, tenant_id, CRMDeal)
        .filter(CRMDeal.contact_id == contact.id, CRMDeal.status == DealStatus.OPEN)
        .all()
    )
    if not deals:
        return

    current_primary = None
    if contact.primary_deal_id:
        current_primary = next((d for d in deals if d.id == contact.primary_deal_id), None)

    if event_occurred_at and current_primary is not None:
        current_primary_activity = _effective_deal_activity(current_primary)
        if event_occurred_at < current_primary_activity:
            # Older events cannot displace an already newer primary deal.
            return

    selected = max(
        deals,
        key=lambda d: (
            _effective_deal_activity(d),
            _parse_occurred_at(d.updated_at) if d.updated_at else datetime.min.replace(tzinfo=timezone.utc),
            d.id,
        ),
    )
    contact.primary_deal_id = selected.id


def _webhook_auth_evaluation(secret: str, body: bytes) -> dict[str, Any]:
    signature_header = request.headers.get("X-CRM-Signature", "").strip()
    token_header = request.headers.get("X-CRM-Webhook-Token", "").strip()

    token_valid = bool(token_header) and hmac.compare_digest(token_header, secret)
    hmac_valid = False
    if signature_header:
        expected = hashlib.sha256(secret.encode("utf-8") + b"." + body).hexdigest()
        candidate = signature_header.removeprefix("sha256=")
        hmac_valid = hmac.compare_digest(candidate, expected)
    return {
        "token_header_present": bool(token_header),
        "signature_header_present": bool(signature_header),
        "token_valid": token_valid,
        "hmac_valid": hmac_valid,
    }


def _verify_webhook_auth(
    *,
    auth_mode: str,
    secret: str,
    body: bytes,
) -> tuple[bool, str | None, str | None, bool]:
    result = _webhook_auth_evaluation(secret, body)
    token_valid = bool(result["token_valid"])
    hmac_valid = bool(result["hmac_valid"])
    mode = (auth_mode or "token").strip().lower()

    if mode == "hmac":
        if hmac_valid:
            return True, "hmac", None, False
        reason = "hmac_required"
        return False, None, reason, False

    if mode == "both":
        if hmac_valid:
            return True, "hmac", None, False
        if token_valid:
            # Token is weaker than HMAC because it is static bearer material.
            return True, "token", None, True
        return False, None, "both_invalid", False

    # token-only default
    if token_valid:
        return True, "token", None, False
    return False, None, "token_required", False


def _encode_timeline_cursor(created_at: datetime, row_id: str) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def _decode_timeline_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        ts_raw, row_id = raw.split("|", 1)
        return datetime.fromisoformat(ts_raw), row_id
    except Exception:
        return None


def _paginate_payload(items: list[dict], total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@crm_api.route("/auth/login", methods=["POST"])
@rate_limited(limit=10, window_seconds=60)
def crm_login():
    payload = request.get_json(silent=True) or {}
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        return _json_error("tenant_id is required", 400)

    try:
        body = _parse_schema(LoginRequest, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        user = (
            session.query(CRMUser)
            .filter(
                CRMUser.tenant_id == tenant_id,
                CRMUser.email == body.email.lower().strip(),
                CRMUser.is_active.is_(True),
            )
            .first()
        )

        if user is None or not auth_service.verify_password(body.password, user.password_hash):
            return _json_error("Invalid credentials", 401)

        user.last_login_at = utc_now_naive()
        token = auth_service.issue_token(user)
        audit = AuditService(session, tenant_id=tenant_id, actor_user_id=user.id)
        audit.log(entity_type="auth", entity_id=user.id, action="login", metadata_json={"email": user.email})
        session.commit()
        return jsonify({"access_token": token, "user": _user_to_dict(user)})
    finally:
        session.close()


@crm_api.route("/auth/register-owner", methods=["POST"])
@rate_limited(limit=5, window_seconds=60)
def crm_register_owner():
    payload = request.get_json(silent=True) or {}
    tenant_id = payload.get("tenant_id")
    business_name = payload.get("business_name")
    full_name = payload.get("full_name")
    email = payload.get("email")
    password = payload.get("password")

    if not tenant_id or not business_name or not full_name or not email or not password:
        return _json_error("tenant_id, business_name, full_name, email and password are required", 400)
    if len(password) < 8:
        return _json_error("password must be at least 8 characters", 400)

    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        if tenant is None:
            tenant = CRMTenant(
                id=tenant_id,
                business_name=business_name,
                timezone=payload.get("timezone", "America/Argentina/Buenos_Aires"),
                currency=payload.get("currency", "USD"),
                channels=payload.get("channels", ["web", "instagram"]),
                integration_settings=merge_integration_settings({}, payload.get("integration_settings", {})),
                pipeline_config=[],
                quiet_hours_start=payload.get("quiet_hours_start", "22:00"),
                quiet_hours_end=payload.get("quiet_hours_end", "08:00"),
                followup_min_interval_minutes=int(payload.get("followup_min_interval_minutes", 60)),
                webhook_auth_mode=str(payload.get("webhook_auth_mode", "token")).lower(),
            )
            session.add(tenant)
            session.flush()

        users_count = session.query(CRMUser).filter(CRMUser.tenant_id == tenant_id).count()
        if users_count > 0:
            return _json_error("Tenant already initialized", 409)

        user = CRMUser(
            tenant_id=tenant_id,
            full_name=full_name,
            email=str(email).lower().strip(),
            phone=payload.get("phone"),
            role=UserRole.OWNER,
            password_hash=auth_service.hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()

        default_stages = [
            CRMPipelineStage(tenant_id=tenant_id, name="NEW", position=1, color="#64748b"),
            CRMPipelineStage(tenant_id=tenant_id, name="QUALIFIED", position=2, color="#2563eb"),
            CRMPipelineStage(tenant_id=tenant_id, name="QUOTED", position=3, color="#f59e0b"),
            CRMPipelineStage(tenant_id=tenant_id, name="NEGOTIATING", position=4, color="#f97316"),
            CRMPipelineStage(tenant_id=tenant_id, name="WON", position=5, color="#16a34a", is_won=True),
            CRMPipelineStage(tenant_id=tenant_id, name="LOST", position=6, color="#dc2626", is_lost=True),
            CRMPipelineStage(tenant_id=tenant_id, name="NURTURE", position=7, color="#334155"),
        ]
        session.add_all(default_stages)

        session.commit()
        token = auth_service.issue_token(user)
        return jsonify({"access_token": token, "user": _user_to_dict(user), "tenant_id": tenant_id}), 201
    finally:
        session.close()


@crm_api.route("/contacts", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def list_contacts():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()
    filters = {
        "tag": request.args.get("tag"),
        "last_activity_after": request.args.get("last_activity_after"),
        "min_score": request.args.get("min_score"),
        "stage": request.args.get("stage"),
        "search": request.args.get("search"),
    }

    session = _get_session()
    try:
        repo = ContactRepository(session, tenant_id)
        contacts, total = repo.list(
            page=pagination["page"],
            page_size=pagination["page_size"],
            sort_by=pagination["sort_by"],
            sort_dir=pagination["sort_dir"],
            filters=filters,
        )
        payload = _paginate_payload([_contact_to_dict(c) for c in contacts], total, pagination["page"], pagination["page_size"])
        return jsonify(payload)
    finally:
        session.close()


@crm_api.route("/contacts", methods=["POST"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def create_contact():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(ContactCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = ContactRepository(session, tenant_id)
        payload = _map_metadata_field(body.model_dump(exclude_none=True, exclude={"tags"}))
        contact = repo.create(payload)

        if body.tags:
            tags = _tenant_query(session, tenant_id, CRMTag, include_deleted=True).filter(CRMTag.name.in_(body.tags)).all()
            repo.set_tags(contact.id, [t.id for t in tags])

        audit = AuditService(session, tenant_id=tenant_id, actor_user_id=actor_id)
        audit.log(entity_type="contact", entity_id=contact.id, action="create", after_data=_contact_to_dict(contact))

        session.commit()
        return jsonify(_contact_to_dict(contact)), 201
    finally:
        session.close()


@crm_api.route("/contacts/<contact_id>", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def get_contact(contact_id: str):
    tenant_id = _tenant_from_auth()

    session = _get_session()
    try:
        repo = ContactRepository(session, tenant_id)
        contact = repo.get(contact_id)
        if contact is None:
            return _json_error("Contact not found", 404)

        deals = _tenant_query(session, tenant_id, CRMDeal).filter(CRMDeal.contact_id == contact_id).all()
        tasks = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.contact_id == contact_id).all()
        notes = (
            _tenant_query(session, tenant_id, CRMNote)
            .filter(CRMNote.contact_id == contact_id)
            .order_by(CRMNote.created_at.desc())
            .all()
        )
        conversations = (
            _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
            .filter(CRMConversation.contact_id == contact_id)
            .order_by(CRMConversation.last_message_at.desc())
            .all()
        )

        timeline_limit = min(100, max(1, int(request.args.get("timeline_limit", "30"))))
        cursor_token = request.args.get("timeline_cursor")
        cursor = _decode_timeline_cursor(cursor_token)
        timeline_rows: list[dict[str, Any]] = []

        if conversations:
            conv_ids = [c.id for c in conversations]
            messages_query = _tenant_query(session, tenant_id, CRMMessage, include_deleted=True).filter(
                CRMMessage.conversation_id.in_(conv_ids)
            )
            deal_events_query = _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True).filter(
                CRMDealEvent.deal_id.in_([d.id for d in deals] or [""])
            )
            task_events_query = _tenant_query(session, tenant_id, CRMTaskEvent, include_deleted=True).filter(
                CRMTaskEvent.task_id.in_([t.id for t in tasks] or [""])
            )

            if cursor:
                cursor_dt, cursor_id = cursor
                messages_query = messages_query.filter(
                    (CRMMessage.created_at < cursor_dt) | ((CRMMessage.created_at == cursor_dt) & (CRMMessage.id < cursor_id))
                )
                deal_events_query = deal_events_query.filter(
                    (CRMDealEvent.created_at < cursor_dt)
                    | ((CRMDealEvent.created_at == cursor_dt) & (CRMDealEvent.id < cursor_id))
                )
                task_events_query = task_events_query.filter(
                    (CRMTaskEvent.created_at < cursor_dt)
                    | ((CRMTaskEvent.created_at == cursor_dt) & (CRMTaskEvent.id < cursor_id))
                )

            messages = messages_query.order_by(CRMMessage.created_at.desc(), CRMMessage.id.desc()).limit(timeline_limit).all()
            deal_events = (
                deal_events_query.order_by(CRMDealEvent.created_at.desc(), CRMDealEvent.id.desc()).limit(timeline_limit).all()
            )
            task_events = (
                task_events_query.order_by(CRMTaskEvent.created_at.desc(), CRMTaskEvent.id.desc()).limit(timeline_limit).all()
            )

            for m in messages:
                timeline_rows.append(
                    {
                        "id": m.id,
                        "type": "message",
                        "conversation_id": m.conversation_id,
                        "direction": m.direction.value if hasattr(m.direction, "value") else str(m.direction),
                        "body": m.body,
                        "channel": m.channel,
                        "created_at": m.created_at,
                        "metadata": m.metadata_json,
                    }
                )
            for e in deal_events:
                timeline_rows.append(
                    {
                        "id": e.id,
                        "type": "deal_event",
                        "deal_id": e.deal_id,
                        "event_type": e.event_type,
                        "created_at": e.created_at,
                        "metadata": e.payload,
                    }
                )
            for e in task_events:
                timeline_rows.append(
                    {
                        "id": e.id,
                        "type": "task_event",
                        "task_id": e.task_id,
                        "event_type": e.event_type,
                        "created_at": e.created_at,
                        "metadata": e.payload,
                    }
                )

        timeline_rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
        timeline_rows = timeline_rows[:timeline_limit]
        next_cursor = None
        if timeline_rows:
            tail = timeline_rows[-1]
            next_cursor = _encode_timeline_cursor(tail["created_at"], tail["id"])

        return jsonify(
            {
                "contact": _contact_to_dict(contact),
                "deals": [_deal_to_dict(d) for d in deals],
                "tasks": [_task_to_dict(t) for t in tasks],
                "notes": [
                    {
                        "id": n.id,
                        "body": n.body,
                        "pinned": n.pinned,
                        "author_user_id": n.author_user_id,
                        "created_at": _serialize_datetime(n.created_at),
                    }
                    for n in notes
                ],
                "timeline": [
                    {
                        **{k: v for k, v in row.items() if k != "created_at"},
                        "created_at": _serialize_datetime(row["created_at"]),
                    }
                    for row in timeline_rows
                ],
                "timeline_next_cursor": next_cursor,
            }
        )
    finally:
        session.close()


@crm_api.route("/contacts/<contact_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def update_contact(contact_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(ContactUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = ContactRepository(session, tenant_id)
        contact = repo.get(contact_id)
        if contact is None:
            return _json_error("Contact not found", 404)

        before = _contact_to_dict(contact)
        patch = _map_metadata_field(body.model_dump(exclude_none=True))
        updated = repo.update(contact, patch)
        after = _contact_to_dict(updated)

        AuditService(session, tenant_id=tenant_id, actor_user_id=actor_id).log(
            entity_type="contact",
            entity_id=contact.id,
            action="update",
            before_data=before,
            after_data=after,
        )

        session.commit()
        return jsonify(after)
    finally:
        session.close()


@crm_api.route("/contacts/<contact_id>", methods=["DELETE"])
@crm_auth_required
@permission_required(Permission.CONTACTS_DELETE)
def delete_contact(contact_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()

    session = _get_session()
    try:
        repo = ContactRepository(session, tenant_id)
        contact = repo.get(contact_id)
        if contact is None:
            return _json_error("Contact not found", 404)

        before = _contact_to_dict(contact)
        repo.soft_delete(contact, utc_now_naive())
        AuditService(session, tenant_id, actor_id).log(
            entity_type="contact",
            entity_id=contact.id,
            action="delete",
            before_data=before,
        )
        session.commit()
        return jsonify({"status": "deleted"})
    finally:
        session.close()


@crm_api.route("/deals", methods=["GET"])
@crm_auth_required
@permission_required(Permission.DEALS_READ)
def list_deals():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()
    filters = {
        "stage_id": request.args.get("stage_id"),
        "status": request.args.get("status"),
        "owner_user_id": request.args.get("owner_user_id"),
        "contact_id": request.args.get("contact_id"),
    }

    session = _get_session()
    try:
        repo = DealRepository(session, tenant_id)
        deals, total = repo.list(
            page=pagination["page"],
            page_size=pagination["page_size"],
            sort_by=pagination["sort_by"],
            sort_dir=pagination["sort_dir"],
            filters=filters,
        )
        return jsonify(_paginate_payload([_deal_to_dict(d) for d in deals], total, pagination["page"], pagination["page_size"]))
    finally:
        session.close()


@crm_api.route("/deals/board", methods=["GET"])
@crm_auth_required
@permission_required(Permission.DEALS_READ)
def deals_board():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        stages = _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True).order_by(
            CRMPipelineStage.position.asc()
        ).all()
        deals = _tenant_query(session, tenant_id, CRMDeal).order_by(CRMDeal.updated_at.desc()).all()

        board: dict[str, list[dict]] = {stage.id: [] for stage in stages}
        for deal in deals:
            board.setdefault(deal.stage_id, []).append(_deal_to_dict(deal))

        return jsonify(
            {
                "stages": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "position": s.position,
                        "is_won": s.is_won,
                        "is_lost": s.is_lost,
                        "color": s.color,
                        "deals": board.get(s.id, []),
                    }
                    for s in stages
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/deals", methods=["POST"])
@crm_auth_required
@permission_required(Permission.DEALS_WRITE)
def create_deal():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(DealCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = DealRepository(session, tenant_id)
        payload_mapped = _map_metadata_field(body.model_dump(exclude_none=True))
        now_utc = utc_now()
        deal = repo.create(payload_mapped)
        deal.last_activity_at = _max_timestamp(deal.last_activity_at, now_utc)
        deal.last_stage_changed_at = _max_timestamp(deal.last_stage_changed_at, now_utc)

        contact = repo.query(CRMContact).filter(CRMContact.id == deal.contact_id).first()
        if contact:
            _refresh_primary_deal_id(session, tenant_id, contact, event_occurred_at=now_utc)

        session.add(
            CRMDealEvent(
                tenant_id=tenant_id,
                deal_id=deal.id,
                actor_user_id=actor_id,
                event_type="created",
                stage_reason="deal_created",
                payload={"stage_id": deal.stage_id, "status": str(deal.status), "occurred_at": now_utc.isoformat()},
                created_at=now_utc.replace(tzinfo=None),
            )
        )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="deal",
            entity_id=deal.id,
            action="create",
            after_data=_deal_to_dict(deal),
        )
        session.commit()
        return jsonify(_deal_to_dict(deal)), 201
    finally:
        session.close()


@crm_api.route("/deals/<deal_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.DEALS_WRITE)
def update_deal(deal_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(DealUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = DealRepository(session, tenant_id)
        deal = repo.get(deal_id)
        if deal is None:
            return _json_error("Deal not found", 404)

        occurred_at = _parse_occurred_at(body.occurred_at)
        occurred_at_naive = occurred_at.replace(tzinfo=None)
        stage_change_requested = bool(body.stage_id and body.stage_id != deal.stage_id)
        if stage_change_requested and not has_permission(g.crm_user["role"], Permission.DEALS_STAGE_CHANGE):
            return _json_error("Forbidden: missing stage change permission", 403)

        if stage_change_requested:
            stage_exists = (
                _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True)
                .filter(CRMPipelineStage.id == body.stage_id)
                .first()
            )
            if stage_exists is None:
                return _json_error("Invalid stage_id", 422)

        allow_reopen = bool(payload.get("reopen"))
        if deal.status in {DealStatus.WON, DealStatus.LOST} and (stage_change_requested or body.status == DealStatus.OPEN):
            if not allow_reopen:
                return _json_error("Invalid transition from closed deal without explicit reopen=true", 409)

        before = _deal_to_dict(deal)
        patch = _map_metadata_field(body.model_dump(exclude_none=True, exclude={"occurred_at"}))
        stage_change_stale = False
        if stage_change_requested:
            has_stage_history = (
                _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True)
                .filter(
                    CRMDealEvent.deal_id == deal.id,
                    CRMDealEvent.event_type == "stage_changed",
                )
                .first()
                is not None
            )
            if has_stage_history:
                last_stage_changed = _parse_occurred_at(deal.last_stage_changed_at or deal.created_at)
                if occurred_at < last_stage_changed:
                    stage_change_stale = True
                    patch.pop("stage_id", None)

        updated = repo.update(deal, patch)
        if stage_change_requested and not stage_change_stale:
            updated.last_stage_changed_at = _max_timestamp(updated.last_stage_changed_at, occurred_at)
            updated.last_activity_at = _max_timestamp(updated.last_activity_at, occurred_at)
        else:
            updated.last_activity_at = _max_timestamp(updated.last_activity_at, occurred_at)
        after = _deal_to_dict(updated)

        stage_reason = str(payload.get("stage_reason") or "api_stage_change")
        if stage_change_requested and stage_change_stale:
            session.add(
                CRMDealEvent(
                    tenant_id=tenant_id,
                    deal_id=deal.id,
                    actor_user_id=actor_id,
                    event_type="STALE",
                    stage_reason="stale_stage_change",
                    payload={
                        "from_stage": before["stage_id"],
                        "attempted_to_stage": body.stage_id,
                        "occurred_at": occurred_at.isoformat(),
                        "last_stage_changed_at": _parse_occurred_at(deal.last_stage_changed_at or deal.created_at).isoformat(),
                    },
                    created_at=occurred_at_naive,
                )
            )
        if stage_change_requested and not stage_change_stale:
            session.add(
                CRMDealEvent(
                    tenant_id=tenant_id,
                    deal_id=deal.id,
                    actor_user_id=actor_id,
                    event_type="stage_changed",
                    stage_reason=stage_reason,
                    payload={
                        "from_stage": before["stage_id"],
                        "to_stage": body.stage_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    created_at=occurred_at_naive,
                )
            )

            automation_service = AutomationService(session, tenant_id)
            automation_service.run_trigger(
                AutomationTrigger.STAGE_CHANGED,
                {
                    "deal_id": deal.id,
                    "contact_id": deal.contact_id,
                    "from_stage": before["stage_id"],
                    "stage": body.stage_id,
                    "score": deal.score,
                    "channel": deal.source_channel,
                    "actor_user_id": actor_id,
                    "source": "api",
                    "occurred_at": occurred_at.isoformat(),
                },
                trigger_event_id=f"stage:{deal.id}:{body.stage_id}",
                trigger_event_key=f"stage:{deal.id}:{before['stage_id']}:{body.stage_id}",
            )

            recent_cutoff = utc_now_naive() - timedelta(days=7)
            conv_ids = [
                row.id
                for row in _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
                .filter(CRMConversation.contact_id == deal.contact_id)
                .all()
            ]
            if conv_ids:
                (
                    _tenant_query(session, tenant_id, CRMMessageEvent, include_deleted=True)
                    .filter(
                        CRMMessageEvent.conversation_id.in_(conv_ids),
                        CRMMessageEvent.event_type == "salesbot_outbound",
                        CRMMessageEvent.created_at >= recent_cutoff,
                        (CRMMessageEvent.stage_progress_within_7d.is_(False))
                        | (CRMMessageEvent.stage_progress_within_7d.is_(None)),
                    )
                    .update({CRMMessageEvent.stage_progress_within_7d: True}, synchronize_session=False)
                )

        if body.status == DealStatus.WON:
            if not deal.closed_at:
                deal.closed_at = utc_now_naive()
        if body.status and body.status != before["status"]:
            session.add(
                CRMDealEvent(
                    tenant_id=tenant_id,
                    deal_id=deal.id,
                    actor_user_id=actor_id,
                    event_type="status_changed",
                    stage_reason=f"status:{str(body.status)}",
                    payload={"from_status": before["status"], "to_status": str(body.status)},
                )
            )
            if body.status in {DealStatus.WON, DealStatus.LOST}:
                conv_ids = [
                    row.id
                    for row in _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
                    .filter(CRMConversation.contact_id == deal.contact_id)
                    .all()
                ]
                if conv_ids:
                    (
                        _tenant_query(session, tenant_id, CRMMessageEvent, include_deleted=True)
                        .filter(
                            CRMMessageEvent.conversation_id.in_(conv_ids),
                            CRMMessageEvent.event_type == "salesbot_outbound",
                        )
                        .update(
                            {
                                CRMMessageEvent.final_outcome: (
                                    "won" if body.status == DealStatus.WON else "lost"
                                )
                            },
                            synchronize_session=False,
                        )
                    )
            scoring_signal = "deal_won" if body.status == DealStatus.WON else "deal_lost" if body.status == DealStatus.LOST else None
            if scoring_signal:
                ScoringService(session, tenant_id).apply_signal(
                    deal_id=deal.id,
                    signal_key=scoring_signal,
                    context={
                        "channel": deal.source_channel,
                        "score": deal.score,
                        "stage": deal.stage_id,
                    },
                )

        contact = repo.query(CRMContact).filter(CRMContact.id == deal.contact_id).first()
        if contact:
            contact.last_activity_at = _max_timestamp(contact.last_activity_at, occurred_at)
            _refresh_primary_deal_id(session, tenant_id, contact, event_occurred_at=occurred_at)

        AuditService(session, tenant_id, actor_id).log(
            entity_type="deal",
            entity_id=deal.id,
            action="update",
            before_data=before,
            after_data=after,
        )

        session.commit()
        return jsonify(after)
    finally:
        session.close()


@crm_api.route("/deals/<deal_id>/score-explain", methods=["GET"])
@crm_auth_required
@permission_required(Permission.DEALS_READ)
def explain_deal_score(deal_id: str):
    tenant_id = _tenant_from_auth()
    limit = min(200, max(1, int(request.args.get("limit", "50"))))
    session = _get_session()
    try:
        data = ScoringService(session, tenant_id).explain(deal_id, limit=limit)
        if not data.get("found"):
            return _json_error("Deal not found", 404)
        return jsonify(data)
    finally:
        session.close()


def _apply_segment_filters(query, filters: dict[str, Any]):
    if tag := filters.get("tag"):
        query = query.filter(CRMContact.metadata_json["tags"].astext.contains(tag))
    if min_score := filters.get("min_score"):
        query = query.filter(CRMContact.score >= int(min_score))
    if inactive_days := filters.get("inactive_days"):
        threshold = utc_now_naive() - timedelta(days=int(inactive_days))
        query = query.filter((CRMContact.last_activity_at.is_(None)) | (CRMContact.last_activity_at <= threshold))
    if search := filters.get("search"):
        pattern = f"%{search.lower()}%"
        query = query.filter(
            (func.lower(CRMContact.name).like(pattern))
            | (func.lower(CRMContact.email).like(pattern))
            | (CRMContact.phone.like(f"%{search}%"))
        )
    if product_model := filters.get("product_model"):
        query = query.filter(CRMContact.metadata_json["product_model"].astext == str(product_model))
    if stage := filters.get("stage"):
        query = query.filter(CRMContact.metadata_json["stage"].astext == str(stage))
    return query


@crm_api.route("/segments", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def list_segments():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMSegment, include_deleted=True).order_by(CRMSegment.created_at.desc()).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": row.id,
                        "name": row.name,
                        "description": row.description,
                        "filters": row.filters_json,
                        "last_exported_at": _serialize_datetime(row.last_exported_at),
                        "created_at": _serialize_datetime(row.created_at),
                    }
                    for row in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/segments", methods=["POST"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def create_segment():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return _json_error("name is required", 400)

    session = _get_session()
    try:
        row = CRMSegment(
            tenant_id=tenant_id,
            name=name,
            description=payload.get("description"),
            filters_json=payload.get("filters") or {},
            created_by_user_id=actor_id,
        )
        session.add(row)
        session.flush()

        AuditService(session, tenant_id, actor_id).log(
            entity_type="segment",
            entity_id=row.id,
            action="create",
            after_data={"name": row.name, "filters": row.filters_json},
        )
        session.commit()
        return jsonify({"id": row.id}), 201
    finally:
        session.close()


@crm_api.route("/segments/<segment_id>/export.csv", methods=["GET"])
@crm_auth_required
@permission_required(Permission.EXPORTS_RUN)
@rate_limited(limit=10, window_seconds=60)
def export_segment(segment_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    if not _is_owner_or_admin():
        return _json_error("Export is restricted to Owner/Admin", 403)

    session = _get_session()
    try:
        segment = _tenant_query(session, tenant_id, CRMSegment, include_deleted=True).filter(CRMSegment.id == segment_id).first()
        if segment is None:
            return _json_error("Segment not found", 404)

        filters_json = segment.filters_json or {}
        rows_count = _apply_segment_filters(_tenant_query(session, tenant_id, CRMContact), filters_json).count()
        segment.last_exported_at = utc_now_naive()
        AuditService(session, tenant_id, actor_id).log(
            entity_type="segment",
            entity_id=segment.id,
            action="export",
            metadata_json={"filters": filters_json, "rows": rows_count},
        )
        session.commit()

        def _stream_contacts():
            stream_session = _get_session()
            try:
                query = _apply_segment_filters(_tenant_query(stream_session, tenant_id, CRMContact), filters_json).order_by(
                    CRMContact.created_at.desc()
                )
                iterator = query.yield_per(200)
                yield "id,name,phone,email,score,last_activity_at\n"
                for row in iterator:
                    yield (
                        f"{row.id},{json.dumps(row.name)},{row.phone or ''},{row.email or ''},"
                        f"{row.score},{_serialize_datetime(row.last_activity_at) or ''}\n"
                    )
            finally:
                stream_session.close()

        return Response(
            stream_with_context(_stream_contacts()),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=segment_{segment.id}.csv"},
        )
    finally:
        session.close()


@crm_api.route("/tasks", methods=["GET"])
@crm_auth_required
@permission_required(Permission.TASKS_READ)
def list_tasks():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()
    filters = {
        "status": request.args.get("status"),
        "assigned_to_user_id": request.args.get("assigned_to_user_id"),
        "due_scope": request.args.get("due_scope"),
    }

    session = _get_session()
    try:
        repo = TaskRepository(session, tenant_id)
        tasks, total = repo.list(
            page=pagination["page"],
            page_size=pagination["page_size"],
            sort_by=pagination["sort_by"],
            sort_dir=pagination["sort_dir"],
            filters=filters,
        )
        return jsonify(_paginate_payload([_task_to_dict(t) for t in tasks], total, pagination["page"], pagination["page_size"]))
    finally:
        session.close()


@crm_api.route("/tasks", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_WRITE)
def create_task():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(TaskCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = TaskRepository(session, tenant_id)
        data = _map_metadata_field(body.model_dump(exclude_none=True))
        data["created_by_user_id"] = actor_id
        task = repo.create(data)
        session.add(
            CRMTaskEvent(
                tenant_id=tenant_id,
                task_id=task.id,
                actor_user_id=actor_id,
                event_type="created",
                payload={"status": str(task.status)},
            )
        )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id=task.id,
            action="create",
            after_data=_task_to_dict(task),
        )
        session.commit()
        return jsonify(_task_to_dict(task)), 201
    finally:
        session.close()


@crm_api.route("/tasks/<task_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.TASKS_WRITE)
def update_task(task_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(TaskUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = TaskRepository(session, tenant_id)
        task = repo.get(task_id)
        if task is None:
            return _json_error("Task not found", 404)

        before = _task_to_dict(task)
        patch = _map_metadata_field(body.model_dump(exclude_none=True))
        if patch.get("status") == TaskStatus.DONE and task.completed_at is None:
            patch["completed_at"] = utc_now_naive()
        updated = repo.update(task, patch)
        after = _task_to_dict(updated)

        event_type = "completed" if patch.get("status") == TaskStatus.DONE else "updated"
        session.add(
            CRMTaskEvent(
                tenant_id=tenant_id,
                task_id=task.id,
                actor_user_id=actor_id,
                event_type=event_type,
                payload={"before": before, "after": after},
            )
        )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id=task.id,
            action="update",
            before_data=before,
            after_data=after,
        )

        session.commit()
        return jsonify(after)
    finally:
        session.close()


@crm_api.route("/tasks/bulk-complete", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_BULK)
def bulk_complete_tasks():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids", [])
    if not isinstance(task_ids, list) or not task_ids:
        return _json_error("task_ids must be a non-empty list", 400)

    session = _get_session()
    try:
        repo = TaskRepository(session, tenant_id)
        now = utc_now_naive()
        count = repo.bulk_mark_done(task_ids, now)
        rows = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.id.in_(task_ids)).all()
        for row in rows:
            session.add(
                CRMTaskEvent(
                    tenant_id=tenant_id,
                    task_id=row.id,
                    actor_user_id=actor_id,
                    event_type="completed",
                    payload={"bulk": True},
                )
            )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id="bulk",
            action="bulk_update",
            metadata_json={"operation": "bulk_complete", "count": count, "task_ids": task_ids},
        )
        session.commit()
        return jsonify({"updated": count})
    finally:
        session.close()


@crm_api.route("/tasks/bulk-reassign", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_BULK)
def bulk_reassign_tasks():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids", [])
    user_id = payload.get("assigned_to_user_id")
    if not isinstance(task_ids, list) or not task_ids or not user_id:
        return _json_error("task_ids and assigned_to_user_id are required", 400)

    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.id.in_(task_ids)).all()
        for row in rows:
            row.assigned_to_user_id = user_id
            session.add(
                CRMTaskEvent(
                    tenant_id=tenant_id,
                    task_id=row.id,
                    actor_user_id=actor_id,
                    event_type="reassigned",
                    payload={"assigned_to_user_id": user_id, "bulk": True},
                )
            )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id="bulk",
            action="bulk_update",
            metadata_json={"operation": "bulk_reassign", "count": len(rows), "task_ids": task_ids, "assigned_to_user_id": user_id},
        )
        session.commit()
        return jsonify({"updated": len(rows)})
    finally:
        session.close()


@crm_api.route("/tasks/bulk-reschedule", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_BULK)
def bulk_reschedule_tasks():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids", [])
    due_at_raw = payload.get("due_at")
    if not isinstance(task_ids, list) or not task_ids or not due_at_raw:
        return _json_error("task_ids and due_at are required", 400)

    try:
        due_at = datetime.fromisoformat(str(due_at_raw))
    except ValueError:
        return _json_error("due_at must be ISO datetime", 422)

    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.id.in_(task_ids)).all()
        for row in rows:
            row.due_at = due_at
            session.add(
                CRMTaskEvent(
                    tenant_id=tenant_id,
                    task_id=row.id,
                    actor_user_id=actor_id,
                    event_type="rescheduled",
                    payload={"due_at": due_at.isoformat(), "bulk": True},
                )
            )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id="bulk",
            action="bulk_update",
            metadata_json={"operation": "bulk_reschedule", "count": len(rows), "task_ids": task_ids, "due_at": due_at.isoformat()},
        )
        session.commit()
        return jsonify({"updated": len(rows)})
    finally:
        session.close()


@crm_api.route("/conversations", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONVERSATIONS_READ)
def list_conversations():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()

    session = _get_session()
    try:
        query = _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)

        if channel := request.args.get("channel"):
            query = query.filter(CRMConversation.channel == channel)
        if contact_id := request.args.get("contact_id"):
            query = query.filter(CRMConversation.contact_id == contact_id)

        total = query.count()
        rows = (
            query.order_by(CRMConversation.last_message_at.desc())
            .offset((pagination["page"] - 1) * pagination["page_size"])
            .limit(pagination["page_size"])
            .all()
        )

        return jsonify(
            _paginate_payload(
                [
                    {
                        "id": c.id,
                        "tenant_id": c.tenant_id,
                        "contact_id": c.contact_id,
                        "channel": c.channel,
                        "external_id": c.external_id,
                        "started_at": _serialize_datetime(c.started_at),
                        "last_message_at": _serialize_datetime(c.last_message_at),
                        "is_open": c.is_open,
                        "metadata": c.metadata_json,
                    }
                    for c in rows
                ],
                total,
                pagination["page"],
                pagination["page_size"],
            )
        )
    finally:
        session.close()


@crm_api.route("/conversations/<conversation_id>/messages", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONVERSATIONS_READ)
def list_messages(conversation_id: str):
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()

    session = _get_session()
    try:
        query = _tenant_query(session, tenant_id, CRMMessage, include_deleted=True).filter(
            CRMMessage.conversation_id == conversation_id,
        )
        total = query.count()
        rows = (
            query.order_by(CRMMessage.created_at.desc())
            .offset((pagination["page"] - 1) * pagination["page_size"])
            .limit(pagination["page_size"])
            .all()
        )
        return jsonify(
            _paginate_payload(
                [
                    {
                        "id": m.id,
                        "conversation_id": m.conversation_id,
                        "contact_id": m.contact_id,
                        "direction": m.direction.value if hasattr(m.direction, "value") else str(m.direction),
                        "channel": m.channel,
                        "body": m.body,
                        "external_message_id": m.external_message_id,
                        "metadata": m.metadata_json,
                        "sent_at": _serialize_datetime(m.sent_at),
                        "created_at": _serialize_datetime(m.created_at),
                    }
                    for m in rows
                ],
                total,
                pagination["page"],
                pagination["page_size"],
            )
        )
    finally:
        session.close()


@crm_api.route("/messages", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONVERSATIONS_READ)
def list_messages_global():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()

    session = _get_session()
    try:
        query = _tenant_query(session, tenant_id, CRMMessage, include_deleted=True)
        if conversation_id := request.args.get("conversation_id"):
            query = query.filter(CRMMessage.conversation_id == conversation_id)
        if contact_id := request.args.get("contact_id"):
            query = query.filter(CRMMessage.contact_id == contact_id)
        if channel := request.args.get("channel"):
            query = query.filter(CRMMessage.channel == channel)

        total = query.count()
        rows = (
            query.order_by(CRMMessage.created_at.desc())
            .offset((pagination["page"] - 1) * pagination["page_size"])
            .limit(pagination["page_size"])
            .all()
        )

        return jsonify(
            _paginate_payload(
                [
                    {
                        "id": m.id,
                        "conversation_id": m.conversation_id,
                        "contact_id": m.contact_id,
                        "direction": m.direction.value if hasattr(m.direction, "value") else str(m.direction),
                        "channel": m.channel,
                        "body": m.body,
                        "external_message_id": m.external_message_id,
                        "created_at": _serialize_datetime(m.created_at),
                    }
                    for m in rows
                ],
                total,
                pagination["page"],
                pagination["page_size"],
            )
        )
    finally:
        session.close()


@crm_api.route("/conversations/<conversation_id>/messages", methods=["POST"])
@crm_auth_required
@permission_required(Permission.MESSAGES_WRITE)
def create_outbound_draft(conversation_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    body = payload.get("body")
    if not body:
        return _json_error("body is required", 400)

    session = _get_session()
    try:
        conv = _tenant_query(session, tenant_id, CRMConversation, include_deleted=True).filter(
            CRMConversation.id == conversation_id
        ).first()
        if conv is None:
            return _json_error("Conversation not found", 404)

        policy = _sales_policy(session, tenant_id)
        stage_at_send = payload.get("stage")
        objection_type = payload.get("objection_type")
        ab_variant = payload.get("ab_variant")
        variant_key = payload.get("variant_key")
        if not ab_variant:
            ab_variant, variant_key = _deterministic_ab_variant(
                tenant_id=tenant_id,
                contact_id=conv.contact_id,
                stage=stage_at_send,
                objection_type=objection_type,
            )
        if not variant_key:
            _, variant_key = _deterministic_ab_variant(
                tenant_id=tenant_id,
                contact_id=conv.contact_id,
                stage=stage_at_send,
                objection_type=objection_type,
            )
        forced_variant = _forced_ab_variant_from_policy(
            policy,
            channel=(payload.get("channel") or conv.channel),
            stage=stage_at_send,
            objection_type=objection_type,
        )
        if forced_variant:
            ab_variant = forced_variant

        sales_meta = _normalize_sales_intelligence(
            payload,
            ab_variant=ab_variant,
            variant_key=variant_key,
            fallback_stage=stage_at_send,
        )

        msg = CRMMessage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            contact_id=conv.contact_id,
            channel=payload.get("channel") or conv.channel,
            direction=MessageDirection.DRAFT,
            body=body,
            metadata_json={"created_by": actor_id, "source": "admin_panel", "sales_intelligence_v1": sales_meta},
            sent_at=None,
        )
        session.add(msg)
        session.flush()

        session.add(
            CRMMessageEvent(
                tenant_id=tenant_id,
                message_id=msg.id,
                conversation_id=conversation_id,
                event_type="salesbot_outbound",
                status="draft",
                ab_variant=ab_variant,
                variant_key=variant_key,
                objection_type=objection_type,
                stage_at_send=stage_at_send,
                replied_within_24h=False,
                stage_progress_within_7d=False,
                final_outcome=None,
                payload={
                    "source": "admin_panel",
                    "created_by": actor_id,
                    "variant_key": variant_key,
                    "sales_intelligence_v1": sales_meta,
                },
            )
        )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="message",
            entity_id=msg.id,
            action="create",
            after_data={"conversation_id": conversation_id, "direction": "draft"},
        )

        session.commit()
        return jsonify({"id": msg.id, "status": "draft", "conversation_id": conversation_id}), 201
    finally:
        session.close()


@crm_api.route("/notes", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def list_notes():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        query = session.query(CRMNote).filter(CRMNote.tenant_id == tenant_id, CRMNote.deleted_at.is_(None))
        if contact_id := request.args.get("contact_id"):
            query = query.filter(CRMNote.contact_id == contact_id)
        if deal_id := request.args.get("deal_id"):
            query = query.filter(CRMNote.deal_id == deal_id)

        rows = query.order_by(CRMNote.created_at.desc()).limit(200).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": n.id,
                        "contact_id": n.contact_id,
                        "deal_id": n.deal_id,
                        "author_user_id": n.author_user_id,
                        "body": n.body,
                        "pinned": n.pinned,
                        "created_at": _serialize_datetime(n.created_at),
                    }
                    for n in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/notes", methods=["POST"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def create_note():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(NoteCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        note = CRMNote(
            tenant_id=tenant_id,
            contact_id=body.contact_id,
            deal_id=body.deal_id,
            author_user_id=actor_id,
            body=body.body,
            pinned=body.pinned,
        )
        session.add(note)
        session.flush()

        AuditService(session, tenant_id, actor_id).log(
            entity_type="note",
            entity_id=note.id,
            action="create",
            after_data={"contact_id": note.contact_id, "deal_id": note.deal_id, "pinned": note.pinned},
        )

        session.commit()
        return jsonify({"id": note.id}), 201
    finally:
        session.close()


@crm_api.route("/tags", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def list_tags():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMTag, include_deleted=True).order_by(CRMTag.name.asc()).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "color": t.color,
                        "scope": t.scope.value if hasattr(t.scope, "value") else str(t.scope),
                    }
                    for t in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/tags", methods=["POST"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def create_tag():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(TagCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        row = CRMTag(
            tenant_id=tenant_id,
            name=body.name,
            color=body.color,
            scope=body.scope,
            created_by_user_id=actor_id,
        )
        session.add(row)
        session.flush()

        AuditService(session, tenant_id, actor_id).log(
            entity_type="tag",
            entity_id=row.id,
            action="create",
            after_data={"name": row.name, "scope": str(row.scope)},
        )
        session.commit()
        return jsonify({"id": row.id, "name": row.name}), 201
    finally:
        session.close()


@crm_api.route("/automations", methods=["GET"])
@crm_auth_required
@permission_required(Permission.AUTOMATIONS_READ)
def list_automations():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        rows = AutomationRepository(session, tenant_id).list()
        return jsonify(
            {
                "items": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "description": a.description,
                        "trigger_type": a.trigger_type.value if hasattr(a.trigger_type, "value") else str(a.trigger_type),
                        "enabled": a.enabled,
                        "cooldown_minutes": a.cooldown_minutes,
                        "conditions": a.conditions_json,
                        "actions": a.actions_json,
                        "last_run_at": _serialize_datetime(a.last_run_at),
                        "created_at": _serialize_datetime(a.created_at),
                    }
                    for a in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/automations", methods=["POST"])
@crm_auth_required
@permission_required(Permission.AUTOMATIONS_WRITE)
def create_automation():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(AutomationCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        max_automations = 200
        try:
            max_automations = int((tenant.integration_settings or {}).get("max_automations", 200)) if tenant else 200
        except (TypeError, ValueError):
            max_automations = 200
        current_count = _tenant_query(session, tenant_id, CRMAutomation, include_deleted=True).count()
        if current_count >= max_automations:
            return _json_error("Tenant automation limit reached", 409)

        automation = AutomationRepository(session, tenant_id).create(
            {
                **body.model_dump(),
                "created_by_user_id": actor_id,
            }
        )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="automation",
            entity_id=automation.id,
            action="create",
            after_data={"name": automation.name, "trigger_type": str(automation.trigger_type)},
        )
        session.commit()
        return jsonify({"id": automation.id}), 201
    finally:
        session.close()


@crm_api.route("/automations/evaluate", methods=["POST"])
@crm_auth_required
@permission_required(Permission.AUTOMATIONS_WRITE)
def evaluate_automation_dry_run():
    tenant_id = _tenant_from_auth()
    payload = request.get_json(silent=True) or {}
    trigger = payload.get("trigger_type")
    event = payload.get("event") or {}
    if not trigger or not isinstance(event, dict):
        return _json_error("trigger_type and event object are required", 400)

    session = _get_session()
    try:
        runs = AutomationService(session, tenant_id).run_trigger(
            trigger,
            event,
            trigger_event_id=payload.get("trigger_event_id"),
            trigger_event_key=payload.get("trigger_event_key"),
            dry_run=True,
        )
        session.commit()
        return jsonify(
            {
                "items": [
                    {
                        "automation_id": r.automation_id,
                        "status": r.status,
                        "actions_count": r.actions_count,
                        "result": r.result_payload,
                    }
                    for r in runs
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/automations/runs", methods=["GET"])
@crm_auth_required
@permission_required(Permission.AUTOMATIONS_READ)
def list_automation_runs():
    tenant_id = _tenant_from_auth()
    automation_id = request.args.get("automation_id")
    status = request.args.get("status")
    limit = min(200, max(1, int(request.args.get("limit", "100"))))

    session = _get_session()
    try:
        query = _tenant_query(session, tenant_id, CRMAutomationRun, include_deleted=True).order_by(
            CRMAutomationRun.executed_at.desc()
        )
        if automation_id:
            query = query.filter(CRMAutomationRun.automation_id == automation_id)
        if status:
            query = query.filter(CRMAutomationRun.status == status)
        rows = query.limit(limit).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": r.id,
                        "automation_id": r.automation_id,
                        "trigger_type": r.trigger_type,
                        "trigger_event_id": r.trigger_event_id,
                        "trigger_event_key": r.trigger_event_key,
                        "run_key": r.run_key,
                        "status": r.status,
                        "dry_run": r.dry_run,
                        "actions_count": r.actions_count,
                        "error_message": r.error_message,
                        "result": r.result_payload,
                        "executed_at": _serialize_datetime(r.executed_at),
                    }
                    for r in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/automations/<automation_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.AUTOMATIONS_WRITE)
def update_automation(automation_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(AutomationUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = AutomationRepository(session, tenant_id)
        automation = repo.get(automation_id)
        if automation is None:
            return _json_error("Automation not found", 404)

        before = {
            "name": automation.name,
            "enabled": automation.enabled,
            "conditions_json": automation.conditions_json,
            "actions_json": automation.actions_json,
        }
        repo.update(automation, body.model_dump(exclude_none=True))

        AuditService(session, tenant_id, actor_id).log(
            entity_type="automation",
            entity_id=automation.id,
            action="update",
            before_data=before,
            after_data={
                "name": automation.name,
                "enabled": automation.enabled,
                "conditions_json": automation.conditions_json,
                "actions_json": automation.actions_json,
            },
        )

        session.commit()
        return jsonify({"id": automation.id})
    finally:
        session.close()


@crm_api.route("/reports/dashboard", methods=["GET"])
@crm_auth_required
@permission_required(Permission.REPORTS_READ)
def report_dashboard():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        timezone_name = tenant.timezone if tenant else "UTC"

        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        parsed_from = datetime.fromisoformat(date_from) if date_from else None
        parsed_to = datetime.fromisoformat(date_to) if date_to else None

        data = ReportingService(session, tenant_id, timezone_name).dashboard(parsed_from, parsed_to)
        return jsonify(data)
    finally:
        session.close()


@crm_api.route("/reports/export.csv", methods=["GET"])
@crm_auth_required
@permission_required(Permission.EXPORTS_RUN)
@rate_limited(limit=15, window_seconds=60)
def report_export_csv():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    if not _is_owner_or_admin():
        return _json_error("Export is restricted to Owner/Admin", 403)

    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        timezone_name = tenant.timezone if tenant else "UTC"

        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        parsed_from = datetime.fromisoformat(date_from) if date_from else None
        parsed_to = datetime.fromisoformat(date_to) if date_to else None

        service = ReportingService(session, tenant_id, timezone_name)
        csv_chunks = list(service.stream_dashboard_csv(parsed_from, parsed_to))

        AuditService(session, tenant_id, actor_id).log(
            entity_type="report",
            entity_id="dashboard",
            action="export",
            metadata_json={
                "format": "csv",
                "date_from": date_from,
                "date_to": date_to,
                "filters": dict(request.args),
            },
        )
        session.commit()

        return Response(
            csv_chunks,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=crm_dashboard.csv"},
        )
    finally:
        session.close()


@crm_api.route("/reports/ab-variants", methods=["GET"])
@crm_auth_required
@permission_required(Permission.REPORTS_READ)
def report_ab_variants():
    tenant_id = _tenant_from_auth()
    channel_filter = request.args.get("channel")
    stage_filter = request.args.get("stage")
    objection_filter = request.args.get("objection_type")
    autopromote_requested = str(request.args.get("autopromote", "")).strip().lower() in {"1", "true", "yes"}
    session = _get_session()
    try:
        if autopromote_requested and not _is_owner_or_admin():
            return _json_error("Owner/Admin required for autopromote", 403)

        query = (
            _tenant_query(session, tenant_id, CRMMessageEvent, include_deleted=True)
            .join(
                CRMMessage,
                (CRMMessage.tenant_id == CRMMessageEvent.tenant_id) & (CRMMessage.id == CRMMessageEvent.message_id),
            )
            .with_entities(
                CRMMessage.channel,
                CRMMessageEvent.stage_at_send,
                CRMMessageEvent.objection_type,
                CRMMessageEvent.ab_variant,
                func.count(CRMMessageEvent.id).label("sent"),
                func.sum(case((CRMMessageEvent.replied_within_24h.is_(True), 1), else_=0)).label("reply_24h"),
                func.sum(case((CRMMessageEvent.stage_progress_within_7d.is_(True), 1), else_=0)).label(
                    "stage_progress_7d"
                ),
                func.sum(case((CRMMessageEvent.final_outcome == "won", 1), else_=0)).label("won"),
                func.sum(case((CRMMessageEvent.final_outcome == "lost", 1), else_=0)).label("lost"),
            )
            .filter(
                CRMMessageEvent.event_type == "salesbot_outbound",
                CRMMessageEvent.ab_variant.is_not(None),
            )
        )

        if channel_filter:
            query = query.filter(CRMMessage.channel == channel_filter)
        if stage_filter:
            query = query.filter(CRMMessageEvent.stage_at_send == stage_filter)
        if objection_filter:
            query = query.filter(CRMMessageEvent.objection_type == objection_filter)

        rows = (
            query.group_by(
                CRMMessage.channel,
                CRMMessageEvent.stage_at_send,
                CRMMessageEvent.objection_type,
                CRMMessageEvent.ab_variant,
            )
            .order_by(
                CRMMessage.channel.asc(),
                CRMMessageEvent.stage_at_send.asc(),
                CRMMessageEvent.objection_type.asc(),
                CRMMessageEvent.ab_variant.asc(),
            )
            .all()
        )

        segments: dict[tuple[str, str, str], dict[str, Any]] = {}
        for channel, stage_at_send, objection_type, ab_variant, sent, reply_24h, stage_progress_7d, won, lost in rows:
            sent = int(sent or 0)
            sent_safe = max(1, sent)
            segment_key = (channel or "unknown", stage_at_send or "unknown", objection_type or "NONE")
            segment = segments.setdefault(
                segment_key,
                {
                    "channel": segment_key[0],
                    "stage": segment_key[1],
                    "objection_type": segment_key[2],
                    "totals": {
                        "sent": 0,
                        "reply_24h": 0,
                        "stage_progress_7d": 0,
                        "won": 0,
                        "lost": 0,
                    },
                    "variants": [],
                },
            )
            segment["variants"].append(
                {
                    "variant": ab_variant,
                    "sent": sent,
                    "reply_24h": int(reply_24h or 0),
                    "stage_progress_7d": int(stage_progress_7d or 0),
                    "won": int(won or 0),
                    "lost": int(lost or 0),
                    "reply_24h_rate": round(float(reply_24h or 0) / sent_safe, 4),
                    "stage_progress_7d_rate": round(float(stage_progress_7d or 0) / sent_safe, 4),
                    "won_rate": round(float(won or 0) / sent_safe, 4),
                    "lost_rate": round(float(lost or 0) / sent_safe, 4),
                }
            )
            segment["totals"]["sent"] += sent
            segment["totals"]["reply_24h"] += int(reply_24h or 0)
            segment["totals"]["stage_progress_7d"] += int(stage_progress_7d or 0)
            segment["totals"]["won"] += int(won or 0)
            segment["totals"]["lost"] += int(lost or 0)

        items = []
        for key in sorted(segments.keys()):
            segment = segments[key]
            total_sent = max(1, int(segment["totals"]["sent"]))
            items.append(
                {
                    **segment,
                    "totals": {
                        **segment["totals"],
                        "reply_24h_rate": round(float(segment["totals"]["reply_24h"]) / total_sent, 4),
                        "stage_progress_7d_rate": round(float(segment["totals"]["stage_progress_7d"]) / total_sent, 4),
                        "won_rate": round(float(segment["totals"]["won"]) / total_sent, 4),
                        "lost_rate": round(float(segment["totals"]["lost"]) / total_sent, 4),
                    },
                }
            )

        ab_service = ABVariantService(session, tenant_id)
        autopromote = ab_service.evaluate(apply=autopromote_requested)
        if autopromote_requested:
            session.commit()

        return jsonify(
            {
                "filters": {
                    "channel": channel_filter,
                    "stage": stage_filter,
                    "objection_type": objection_filter,
                },
                "items": items,
                "autopromote": autopromote,
            }
        )
    finally:
        session.close()


@crm_api.route("/settings", methods=["GET"])
@crm_auth_required
@permission_required(Permission.SETTINGS_READ)
def get_settings_endpoint():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        if tenant is None:
            return _json_error("Tenant not found", 404)

        stages = (
            session.query(CRMPipelineStage)
            .filter(CRMPipelineStage.tenant_id == tenant_id)
            .order_by(CRMPipelineStage.position.asc())
            .all()
        )
        scoring_rules = (
            session.query(CRMScoringRule)
            .filter(CRMScoringRule.tenant_id == tenant_id)
            .order_by(CRMScoringRule.created_at.desc())
            .all()
        )
        integration_settings = redact_integration_settings(tenant.integration_settings or {})
        raw_policy = integration_settings.get("sales_policy")
        integration_settings["sales_policy"] = merge_sales_policy(raw_policy if isinstance(raw_policy, dict) else {})

        return jsonify(
            {
                "tenant": {
                    "id": tenant.id,
                    "business_name": tenant.business_name,
                    "timezone": tenant.timezone,
                    "currency": tenant.currency,
                    "channels": tenant.channels,
                    "integration_settings": integration_settings,
                    "data_retention_days": tenant.data_retention_days,
                    "quiet_hours_start": tenant.quiet_hours_start,
                    "quiet_hours_end": tenant.quiet_hours_end,
                    "followup_min_interval_minutes": tenant.followup_min_interval_minutes,
                    "webhook_auth_mode": tenant.webhook_auth_mode,
                },
                "pipeline_stages": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "position": s.position,
                        "is_won": s.is_won,
                        "is_lost": s.is_lost,
                        "sla_hours": s.sla_hours,
                        "color": s.color,
                    }
                    for s in stages
                ],
                "scoring_rules": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "signal_key": r.signal_key,
                        "points": r.points,
                        "enabled": r.enabled,
                        "conditions": r.conditions_json,
                    }
                    for r in scoring_rules
                ],
            }
        )
    finally:
        session.close()


@crm_api.route("/settings", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def update_settings_endpoint():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(TenantSettingsUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        if tenant is None:
            return _json_error("Tenant not found", 404)

        before = {
            "business_name": tenant.business_name,
            "timezone": tenant.timezone,
            "currency": tenant.currency,
            "channels": tenant.channels,
            "integration_settings": redact_integration_settings(tenant.integration_settings),
            "data_retention_days": tenant.data_retention_days,
            "quiet_hours_start": tenant.quiet_hours_start,
            "quiet_hours_end": tenant.quiet_hours_end,
            "followup_min_interval_minutes": tenant.followup_min_interval_minutes,
            "webhook_auth_mode": tenant.webhook_auth_mode,
        }

        for key, value in body.model_dump(exclude_none=True).items():
            if key == "integration_settings" and isinstance(value, dict):
                tmp = merge_integration_settings(tenant.integration_settings, value)
                raw_policy = tmp.get("sales_policy")
                tmp["sales_policy"] = merge_sales_policy(raw_policy if isinstance(raw_policy, dict) else {})
                value = tmp
            setattr(tenant, key, value)

        after = {
            "business_name": tenant.business_name,
            "timezone": tenant.timezone,
            "currency": tenant.currency,
            "channels": tenant.channels,
            "integration_settings": redact_integration_settings(tenant.integration_settings),
            "data_retention_days": tenant.data_retention_days,
            "quiet_hours_start": tenant.quiet_hours_start,
            "quiet_hours_end": tenant.quiet_hours_end,
            "followup_min_interval_minutes": tenant.followup_min_interval_minutes,
            "webhook_auth_mode": tenant.webhook_auth_mode,
        }

        AuditService(session, tenant_id, actor_id).log(
            entity_type="tenant_settings",
            entity_id=tenant_id,
            action="update",
            before_data=before,
            after_data=after,
        )

        session.commit()
        return jsonify({"status": "updated"})
    finally:
        session.close()


@crm_api.route("/settings/pipeline-stages", methods=["PUT"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def replace_pipeline_stages():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    stages = payload.get("stages", [])

    if not isinstance(stages, list) or not stages:
        return _json_error("stages must be a non-empty list", 400)

    session = _get_session()
    try:
        before = [
            {
                "id": s.id,
                "name": s.name,
                "position": s.position,
                "is_won": s.is_won,
                "is_lost": s.is_lost,
                "sla_hours": s.sla_hours,
                "color": s.color,
            }
            for s in _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True)
            .order_by(CRMPipelineStage.position.asc())
            .all()
        ]
        _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True).delete()
        rows = []
        for idx, stage in enumerate(stages, start=1):
            row = CRMPipelineStage(
                tenant_id=tenant_id,
                name=stage.get("name", f"Stage {idx}"),
                position=int(stage.get("position", idx)),
                is_won=bool(stage.get("is_won", False)),
                is_lost=bool(stage.get("is_lost", False)),
                sla_hours=stage.get("sla_hours"),
                color=stage.get("color", "#1f6feb"),
            )
            rows.append(row)
            session.add(row)

        after = [
            {
                "name": row.name,
                "position": row.position,
                "is_won": row.is_won,
                "is_lost": row.is_lost,
                "sla_hours": row.sla_hours,
                "color": row.color,
            }
            for row in rows
        ]
        AuditService(session, tenant_id, actor_id).log(
            entity_type="pipeline_stage",
            entity_id="bulk",
            action="bulk_update",
            before_data={"stages": before},
            after_data={"stages": after},
            metadata_json={"count": len(rows)},
        )

        session.commit()
        return jsonify({"status": "updated", "count": len(rows)})
    finally:
        session.close()


@crm_api.route("/settings/scoring-rules", methods=["POST"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def create_scoring_rule():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(ScoringRuleCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        row = CRMScoringRule(
            tenant_id=tenant_id,
            name=body.name,
            signal_key=body.signal_key,
            points=body.points,
            conditions_json=body.conditions_json,
            enabled=body.enabled,
        )
        session.add(row)
        session.flush()

        AuditService(session, tenant_id, actor_id).log(
            entity_type="scoring_rule",
            entity_id=row.id,
            action="create",
            after_data={"name": row.name, "signal_key": row.signal_key, "points": row.points},
        )
        session.commit()
        return jsonify({"id": row.id}), 201
    finally:
        session.close()


@crm_api.route("/settings/scoring-rules/<rule_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def update_scoring_rule(rule_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    session = _get_session()
    try:
        row = (
            session.query(CRMScoringRule)
            .filter(CRMScoringRule.tenant_id == tenant_id, CRMScoringRule.id == rule_id)
            .first()
        )
        if row is None:
            return _json_error("Scoring rule not found", 404)

        before = {"name": row.name, "signal_key": row.signal_key, "points": row.points, "enabled": row.enabled}
        for key in ("name", "signal_key", "points", "conditions_json", "enabled"):
            if key in payload:
                setattr(row, key, payload[key])

        after = {"name": row.name, "signal_key": row.signal_key, "points": row.points, "enabled": row.enabled}
        AuditService(session, tenant_id, actor_id).log(
            entity_type="scoring_rule",
            entity_id=row.id,
            action="update",
            before_data=before,
            after_data=after,
        )

        session.commit()
        return jsonify({"status": "updated"})
    finally:
        session.close()


@crm_api.route("/users", methods=["GET"])
@crm_auth_required
@permission_required(Permission.USERS_READ)
def list_users():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        rows = UserRepository(session, tenant_id).list()
        return jsonify({"items": [_user_to_dict(u) for u in rows]})
    finally:
        session.close()


@crm_api.route("/users", methods=["POST"])
@crm_auth_required
@permission_required(Permission.USERS_WRITE)
def create_user():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(UserCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = UserRepository(session, tenant_id)
        if repo.get_by_email(body.email):
            return _json_error("User already exists", 409)

        user = repo.create(
            {
                "full_name": body.full_name,
                "email": body.email.lower().strip(),
                "phone": body.phone,
                "role": body.role,
                "password_hash": auth_service.hash_password(body.password),
                "is_active": True,
            }
        )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="user",
            entity_id=user.id,
            action="create",
            after_data={"email": user.email, "role": str(user.role)},
        )

        session.commit()
        return jsonify(_user_to_dict(user)), 201
    finally:
        session.close()


@crm_api.route("/users/<user_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.USERS_ROLES)
def update_user(user_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        body = _parse_schema(UserUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        repo = UserRepository(session, tenant_id)
        user = repo.get(user_id)
        if user is None:
            return _json_error("User not found", 404)

        before = _user_to_dict(user)
        updated = repo.update(user, body.model_dump(exclude_none=True))
        after = _user_to_dict(updated)

        AuditService(session, tenant_id, actor_id).log(
            entity_type="user",
            entity_id=user.id,
            action="permission_change" if body.role else "update",
            before_data=before,
            after_data=after,
        )

        session.commit()
        return jsonify(after)
    finally:
        session.close()


@crm_api.route("/playbooks", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def list_playbooks():
    tenant_id = _tenant_from_auth()
    objection_key = request.args.get("objection_key")
    channel = request.args.get("channel")
    session = _get_session()
    try:
        rows = PlaybookService(session, tenant_id).list(objection_key=objection_key, channel=channel)
        return jsonify(
            {
                "items": [
                    {
                        "id": p.id,
                        "objection_key": p.objection_key,
                        "title": p.title,
                        "channel": p.channel,
                        "suggested_response": p.suggested_response,
                        "enabled": p.enabled,
                        "metadata": p.metadata_json,
                    }
                    for p in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/playbooks", methods=["POST"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def create_playbook():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(PlaybookCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        row = PlaybookService(session, tenant_id).create(
            {
                "objection_key": body.objection_key,
                "title": body.title,
                "channel": body.channel,
                "suggested_response": body.suggested_response,
                "enabled": body.enabled,
                "metadata_json": body.metadata,
            }
        )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="playbook",
            entity_id=row.id,
            action="create",
            after_data={"objection_key": row.objection_key, "title": row.title},
        )
        session.commit()
        return jsonify({"id": row.id}), 201
    finally:
        session.close()


@crm_api.route("/playbooks/<playbook_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.CONTACTS_WRITE)
def update_playbook(playbook_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(PlaybookUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        service = PlaybookService(session, tenant_id)
        row = service.get(playbook_id)
        if row is None:
            return _json_error("Playbook not found", 404)
        before = {
            "title": row.title,
            "suggested_response": row.suggested_response,
            "enabled": row.enabled,
            "channel": row.channel,
        }
        patch = body.model_dump(exclude_none=True)
        if "metadata" in patch:
            patch["metadata_json"] = patch.pop("metadata")
        service.update(row, patch)
        AuditService(session, tenant_id, actor_id).log(
            entity_type="playbook",
            entity_id=row.id,
            action="update",
            before_data=before,
            after_data={
                "title": row.title,
                "suggested_response": row.suggested_response,
                "enabled": row.enabled,
                "channel": row.channel,
            },
        )
        session.commit()
        return jsonify({"status": "updated"})
    finally:
        session.close()


@crm_api.route("/assignment/rules", methods=["GET"])
@crm_auth_required
@permission_required(Permission.SETTINGS_READ)
def list_assignment_rules():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        rows = (
            _tenant_query(session, tenant_id, CRMLeadAssignmentRule, include_deleted=True)
            .order_by(CRMLeadAssignmentRule.channel.asc(), CRMLeadAssignmentRule.sort_order.asc())
            .all()
        )
        return jsonify(
            {
                "items": [
                    {
                        "id": r.id,
                        "user_id": r.user_id,
                        "channel": r.channel,
                        "sort_order": r.sort_order,
                        "weight": r.weight,
                        "active": r.active,
                    }
                    for r in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/assignment/rules", methods=["PUT"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def replace_assignment_rules():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    rules = payload.get("rules", [])
    if not isinstance(rules, list):
        return _json_error("rules must be a list", 400)

    session = _get_session()
    try:
        before = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "channel": row.channel,
                "sort_order": row.sort_order,
                "weight": row.weight,
                "active": row.active,
            }
            for row in _tenant_query(session, tenant_id, CRMLeadAssignmentRule, include_deleted=True)
            .order_by(CRMLeadAssignmentRule.channel.asc(), CRMLeadAssignmentRule.sort_order.asc())
            .all()
        ]
        _tenant_query(session, tenant_id, CRMLeadAssignmentRule, include_deleted=True).delete()
        created = 0
        after: list[dict[str, Any]] = []
        for idx, rule in enumerate(rules, start=1):
            row = CRMLeadAssignmentRule(
                tenant_id=tenant_id,
                user_id=rule["user_id"],
                channel=rule.get("channel", "whatsapp"),
                sort_order=int(rule.get("sort_order", idx)),
                weight=int(rule.get("weight", 1)),
                active=bool(rule.get("active", True)),
            )
            session.add(row)
            created += 1
            after.append(
                {
                    "user_id": row.user_id,
                    "channel": row.channel,
                    "sort_order": row.sort_order,
                    "weight": row.weight,
                    "active": row.active,
                }
            )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="assignment_rule",
            entity_id="bulk",
            action="bulk_update",
            before_data={"rules": before},
            after_data={"rules": after},
            metadata_json={"count": created},
        )
        session.commit()
        return jsonify({"status": "updated", "count": created})
    finally:
        session.close()


@crm_api.route("/assignment/assign-lead", methods=["POST"])
@crm_auth_required
@permission_required(Permission.DEALS_WRITE)
def assign_lead():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(AssignmentRequest, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        service = AssignmentService(session, tenant_id)
        try:
            user = service.assign_lead(
                contact_id=body.contact_id,
                deal_id=body.deal_id,
                channel=body.channel,
                preferred_user_id=body.preferred_user_id,
            )
        except AssignmentError as exc:
            return _json_error(str(exc), 409)

        AuditService(session, tenant_id, actor_id).log(
            entity_type="assignment",
            entity_id=body.contact_id,
            action="update",
            metadata_json={"assigned_user_id": user.id, "channel": body.channel, "deal_id": body.deal_id},
        )
        session.commit()
        return jsonify({"contact_id": body.contact_id, "assigned_user": _user_to_dict(user)})
    finally:
        session.close()


@crm_api.route("/sla/check", methods=["POST"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def run_sla_check():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    session = _get_session()
    try:
        breaches = SLAService(session, tenant_id).check_stage_breaches()
        AuditService(session, tenant_id, actor_id).log(
            entity_type="sla",
            entity_id="check",
            action="update",
            metadata_json={"breaches": len(breaches)},
        )
        session.commit()
        return jsonify({"breaches_detected": len(breaches), "breach_ids": [b.id for b in breaches]})
    finally:
        session.close()


@crm_api.route("/sla/breaches", methods=["GET"])
@crm_auth_required
@permission_required(Permission.TASKS_READ)
def list_sla_breaches():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        query = _tenant_query(session, tenant_id, CRMSLABreach, include_deleted=True)
        if status := request.args.get("status"):
            query = query.filter(CRMSLABreach.status == status)
        rows = query.order_by(CRMSLABreach.breached_at.desc()).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": b.id,
                        "deal_id": b.deal_id,
                        "stage_id": b.stage_id,
                        "threshold_hours": b.threshold_hours,
                        "status": b.status,
                        "breached_at": _serialize_datetime(b.breached_at),
                        "resolved_at": _serialize_datetime(b.resolved_at),
                        "metadata": b.metadata_json,
                    }
                    for b in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/sla/breaches/<breach_id>/resolve", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_WRITE)
def resolve_sla_breach(breach_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    session = _get_session()
    try:
        breach = SLAService(session, tenant_id).resolve_breach(breach_id)
        if breach is None:
            return _json_error("Breach not found", 404)
        AuditService(session, tenant_id, actor_id).log(
            entity_type="sla_breach",
            entity_id=breach.id,
            action="update",
            metadata_json={"status": "resolved"},
        )
        session.commit()
        return jsonify({"status": "resolved", "id": breach.id})
    finally:
        session.close()


@crm_api.route("/whatsapp/templates", methods=["GET"])
@crm_auth_required
@permission_required(Permission.MESSAGES_WRITE)
def list_whatsapp_templates():
    tenant_id = _tenant_from_auth()
    status = request.args.get("status")
    session = _get_session()
    try:
        rows = WhatsAppTemplateService(session, tenant_id).list(status=status)
        return jsonify(
            {
                "items": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "category": t.category,
                        "language": t.language,
                        "body_template": t.body_template,
                        "variables": t.variables_json,
                        "status": t.status,
                        "version": t.current_version,
                        "approved_by_user_id": t.approved_by_user_id,
                        "approved_at": _serialize_datetime(t.approved_at),
                    }
                    for t in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/whatsapp/templates", methods=["POST"])
@crm_auth_required
@permission_required(Permission.MESSAGES_WRITE)
def create_whatsapp_template():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(WhatsAppTemplateCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        row = WhatsAppTemplateService(session, tenant_id).create(body.model_dump(), actor_id)
        AuditService(session, tenant_id, actor_id).log(
            entity_type="whatsapp_template",
            entity_id=row.id,
            action="create",
            after_data={"name": row.name, "status": row.status},
        )
        session.commit()
        return jsonify({"id": row.id}), 201
    finally:
        session.close()


@crm_api.route("/whatsapp/templates/<template_id>", methods=["PATCH"])
@crm_auth_required
@permission_required(Permission.MESSAGES_WRITE)
def update_whatsapp_template(template_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(WhatsAppTemplateUpdate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        service = WhatsAppTemplateService(session, tenant_id)
        row = service.get(template_id)
        if row is None:
            return _json_error("Template not found", 404)
        before = {"status": row.status, "version": row.current_version}
        service.update(row, body.model_dump(exclude_none=True), actor_id)
        AuditService(session, tenant_id, actor_id).log(
            entity_type="whatsapp_template",
            entity_id=row.id,
            action="update",
            before_data=before,
            after_data={"status": row.status, "version": row.current_version},
        )
        session.commit()
        return jsonify({"id": row.id, "status": row.status, "version": row.current_version})
    finally:
        session.close()


@crm_api.route("/whatsapp/templates/<template_id>/approve", methods=["POST"])
@crm_auth_required
@permission_required(Permission.USERS_ROLES)
def approve_whatsapp_template(template_id: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(WhatsAppTemplateApproval, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        row = WhatsAppTemplateService(session, tenant_id).approve(
            template_id=template_id,
            decision=body.decision,
            reviewer_user_id=actor_id,
            comment=body.comment,
        )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="whatsapp_template",
            entity_id=row.id,
            action="permission_change",
            metadata_json={"decision": body.decision, "comment": body.comment},
        )
        session.commit()
        return jsonify({"id": row.id, "status": row.status})
    finally:
        session.close()


@crm_api.route("/inventory/signals", methods=["POST"])
@crm_auth_required
@permission_required(Permission.DEALS_WRITE)
def process_inventory_signal():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    try:
        body = _parse_schema(InventorySignalCreate, payload)
    except ValueError as exc:
        return _json_error(f"Invalid payload: {exc}", 422)

    session = _get_session()
    try:
        result = InventorySignalService(session, tenant_id).process_stock_signal(body.model_dump())
        AuditService(session, tenant_id, actor_id).log(
            entity_type="inventory_signal",
            entity_id=result["signal_id"],
            action="create",
            metadata_json={"notified": result["notified"], "product_sku": body.product_sku},
        )
        session.commit()
        return jsonify(result), 201
    finally:
        session.close()


@crm_api.route("/reports/clv", methods=["GET"])
@crm_auth_required
@permission_required(Permission.REPORTS_READ)
def report_clv():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        force_recompute = request.args.get("recompute") == "true"
        service = CLVService(session, tenant_id)
        if force_recompute:
            service.compute_snapshots()
            session.commit()
        data = service.cohort_report()
        return jsonify(data)
    finally:
        session.close()


@crm_api.route("/messages/webhook", methods=["POST"])
@rate_limited(limit=120, window_seconds=60)
def ingest_message_webhook():
    payload = request.get_json(silent=True) or {}
    tenant_id = payload.get("tenant_id")
    source = payload.get("source", "bot")
    event_id = payload.get("event_id")
    event_type = payload.get("event_type")
    if not tenant_id or not event_id or not event_type:
        return _json_error("tenant_id, event_id and event_type are required", 400)

    session = _get_session()
    raw_body = request.get_data(cache=True) or b""

    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        if tenant is None:
            return _json_error("Unauthorized webhook", 401)

        secret = get_tenant_crm_webhook_secret(tenant)
        if not settings.is_secret_configured(secret):
            return _json_error("CRM webhook secret not configured", 503)

        auth_mode = (tenant.webhook_auth_mode or "token").strip().lower()
        auth_ok, auth_method, reject_reason, weak_method_used = _verify_webhook_auth(
            auth_mode=auth_mode,
            secret=secret,
            body=raw_body,
        )
        if not auth_ok:
            AuditService(session, tenant_id=tenant_id, actor_user_id=None).log(
                entity_type="webhook",
                entity_id=str(event_id),
                action="auth_rejected",
                metadata_json={
                    "source": source,
                    "event_type": event_type,
                    "event_key": event_id,
                    "auth_mode": auth_mode,
                    "reason": reject_reason,
                    "token_header_present": bool(request.headers.get("X-CRM-Webhook-Token")),
                    "signature_header_present": bool(request.headers.get("X-CRM-Signature")),
                },
            )
            session.commit()
            return _json_error("Unauthorized webhook", 401)

        if weak_method_used:
            logger.warning(
                "webhook_auth_weaker_method_used tenant_id=%s mode=%s method=%s event_id=%s",
                tenant_id,
                auth_mode,
                auth_method,
                event_id,
            )

        service = WebhookIngestionService(session, tenant_id)

        def _handler(event_payload: dict) -> dict:
            return _process_bot_event(
                session=session,
                tenant_id=tenant_id,
                payload=event_payload,
                trigger_event_id=event_id,
                trigger_event_key=f"{source}:{event_type}:{event_id}",
            )

        created, result = service.ingest(
            source=source,
            event_type=event_type,
            event_key=event_id,
            payload=payload,
            handler=_handler,
        )

        session.commit()
        return jsonify(
            {
                "created": created,
                "status": result.get("status"),
                "auth_method": auth_method,
                "result": result,
            }
        )
    except Exception:
        session.rollback()
        logger.exception("webhook_processing_failed tenant_id=%s event_id=%s", tenant_id, event_id)
        return _json_error("Webhook processing failed", 500)
    finally:
        session.close()


@crm_api.route("/messages/inbound", methods=["POST"])
@rate_limited(limit=120, window_seconds=60)
def ingest_inbound_message_alias():
    return ingest_message_webhook()


@crm_api.route("/messages/webhook-events", methods=["GET"])
@crm_auth_required
@permission_required(Permission.SETTINGS_READ)
def list_webhook_events():
    tenant_id = _tenant_from_auth()
    status = request.args.get("status")
    limit = min(200, max(1, int(request.args.get("limit", "100"))))
    session = _get_session()
    try:
        rows = WebhookEventRepository(session, tenant_id).list(status=status, limit=limit)
        return jsonify(
            {
                "items": [
                    {
                        "id": row.id,
                        "source": row.source,
                        "event_type": row.event_type,
                        "event_key": row.event_key,
                        "status": row.status,
                        "duplicate_count": row.duplicate_count,
                        "error_message": row.error_message,
                        "processed_at": _serialize_datetime(row.processed_at),
                        "created_at": _serialize_datetime(row.created_at),
                    }
                    for row in rows
                ]
            }
        )
    finally:
        session.close()


@crm_api.route("/messages/webhook-events/<event_id>/replay", methods=["POST"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
@rate_limited(limit=20, window_seconds=60)
def replay_webhook_event(event_id: str):
    if not _is_owner_or_admin():
        return _json_error("Replay is restricted to Owner/Admin", 403)

    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    session = _get_session()
    try:
        repo = WebhookEventRepository(session, tenant_id)
        row = repo.get(event_id)
        if row is None:
            return _json_error("Webhook event not found", 404)

        result = _process_bot_event(
            session=session,
            tenant_id=tenant_id,
            payload=row.payload or {},
            trigger_event_id=f"replay:{row.id}",
            trigger_event_key=f"replay:{row.source}:{row.event_type}:{row.event_key}",
        )
        repo.mark_processed(row)
        AuditService(session, tenant_id, actor_id).log(
            entity_type="webhook_event",
            entity_id=row.id,
            action="replay",
            metadata_json={"source": row.source, "event_type": row.event_type, "event_key": row.event_key},
        )
        session.commit()
        return jsonify({"status": "processed", "result": result})
    except Exception:
        session.rollback()
        logger.exception("webhook_replay_failed tenant_id=%s event_id=%s", tenant_id, event_id)
        return _json_error("Replay failed", 500)
    finally:
        session.close()


def _upsert_contact(session: Session, tenant_id: str, payload: dict, *, occurred_at: datetime) -> CRMContact:
    try:
        phone = normalize_phone_e164(payload.get("phone"))
    except ValueError:
        phone = None
    email = normalize_email(payload.get("email"))

    query = _tenant_query(session, tenant_id, CRMContact)
    if phone:
        contact = query.filter(CRMContact.phone == phone).first()
        if contact:
            contact.last_activity_at = _max_timestamp(contact.last_activity_at, occurred_at)
            return contact
    if email:
        contact = query.filter(CRMContact.email == email).first()
        if contact:
            contact.last_activity_at = _max_timestamp(contact.last_activity_at, occurred_at)
            return contact

    contact = CRMContact(
        tenant_id=tenant_id,
        name=payload.get("name") or payload.get("phone") or payload.get("email") or "Unknown",
        phone=phone,
        email=email,
        source_channel=payload.get("channel"),
        metadata_json=payload.get("contact_metadata", {}),
        last_activity_at=_max_timestamp(None, occurred_at),
    )
    session.add(contact)
    session.flush()
    return contact


def _upsert_conversation(
    session: Session,
    tenant_id: str,
    contact_id: str,
    payload: dict,
    *,
    occurred_at: datetime,
) -> CRMConversation:
    channel = payload.get("channel", "whatsapp")
    external_conversation_id = payload.get("conversation_external_id")

    query = _tenant_query(session, tenant_id, CRMConversation, include_deleted=True).filter(
        CRMConversation.contact_id == contact_id,
        CRMConversation.channel == channel,
    )

    if external_conversation_id:
        row = query.filter(CRMConversation.external_id == external_conversation_id).first()
        if row:
            row.last_message_at = _max_timestamp(row.last_message_at, occurred_at)
            return row

    row = query.order_by(CRMConversation.created_at.desc()).first()
    if row:
        row.last_message_at = _max_timestamp(row.last_message_at, occurred_at)
        return row

    row = CRMConversation(
        tenant_id=tenant_id,
        contact_id=contact_id,
        channel=channel,
        external_id=external_conversation_id,
        started_at=_max_timestamp(None, occurred_at),
        last_message_at=_max_timestamp(None, occurred_at),
        metadata_json=payload.get("conversation_metadata", {}),
    )
    session.add(row)
    session.flush()
    return row


def _ensure_default_stage(session: Session, tenant_id: str) -> CRMPipelineStage:
    stage = (
        _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True)
        .order_by(CRMPipelineStage.position.asc())
        .first()
    )
    if stage:
        return stage

    stage = CRMPipelineStage(
        tenant_id=tenant_id,
        name="NEW",
        position=1,
        color="#64748b",
        is_won=False,
        is_lost=False,
    )
    session.add(stage)
    session.flush()
    return stage


def _resolve_stage_id_for_event(session: Session, tenant_id: str, payload: dict, *, fallback_stage_id: str | None = None) -> str:
    stage_id = payload.get("stage_id")
    if stage_id:
        row = _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True).filter(CRMPipelineStage.id == stage_id).first()
        if row:
            return row.id

    stage_name = payload.get("stage")
    if isinstance(stage_name, str) and stage_name.strip():
        row = (
            _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True)
            .filter(func.lower(CRMPipelineStage.name) == stage_name.strip().lower())
            .first()
        )
        if row:
            return row.id

    if fallback_stage_id:
        return fallback_stage_id
    return _ensure_default_stage(session, tenant_id).id


def _apply_webhook_stage_change(
    session: Session,
    tenant_id: str,
    deal: CRMDeal,
    payload: dict,
    *,
    occurred_at: datetime,
) -> bool:
    target_stage_id = _resolve_stage_id_for_event(session, tenant_id, payload, fallback_stage_id=deal.stage_id)
    last_changed = _parse_occurred_at(deal.last_stage_changed_at or deal.created_at)
    from_stage = deal.stage_id

    if occurred_at < last_changed:
        session.add(
            CRMDealEvent(
                tenant_id=tenant_id,
                deal_id=deal.id,
                actor_user_id=payload.get("actor_user_id"),
                event_type="STALE",
                stage_reason="stale_stage_change",
                payload={
                    "from_stage": from_stage,
                    "attempted_to_stage": target_stage_id,
                    "occurred_at": occurred_at.isoformat(),
                    "last_stage_changed_at": last_changed.isoformat(),
                    "source": payload.get("source", "webhook"),
                },
                created_at=occurred_at.replace(tzinfo=None),
            )
        )
        return False

    deal.stage_id = target_stage_id
    deal.last_stage_changed_at = _max_timestamp(deal.last_stage_changed_at, occurred_at)
    deal.last_activity_at = _max_timestamp(deal.last_activity_at, occurred_at)
    session.add(
        CRMDealEvent(
            tenant_id=tenant_id,
            deal_id=deal.id,
            actor_user_id=payload.get("actor_user_id"),
            event_type="stage_changed",
            stage_reason=str(payload.get("stage_reason") or "webhook_stage_change"),
            payload={
                "from_stage": from_stage,
                "to_stage": target_stage_id,
                "occurred_at": occurred_at.isoformat(),
                "source": payload.get("source", "webhook"),
            },
            created_at=occurred_at.replace(tzinfo=None),
        )
    )
    return True


def _upsert_deal(
    session: Session,
    tenant_id: str,
    contact: CRMContact,
    payload: dict,
    *,
    occurred_at: datetime,
) -> tuple[CRMDeal | None, bool]:
    stale_stage_change = False
    explicit_deal_id = payload.get("deal_id")
    event_type = payload.get("event_type")
    if explicit_deal_id:
        existing = _tenant_query(session, tenant_id, CRMDeal).filter(CRMDeal.id == explicit_deal_id).first()
        if existing:
            existing.last_activity_at = _max_timestamp(existing.last_activity_at, occurred_at)
            if event_type == "stage_changed":
                applied = _apply_webhook_stage_change(session, tenant_id, existing, payload, occurred_at=occurred_at)
                stale_stage_change = not applied
            return existing, stale_stage_change

    if event_type not in {"quote_sent", "stage_changed", "order_delivered"}:
        return None, False

    stage_id = _resolve_stage_id_for_event(session, tenant_id, payload)
    title = payload.get("deal_title") or payload.get("product_model") or f"Auto deal {contact.name}"
    row = CRMDeal(
        tenant_id=tenant_id,
        contact_id=contact.id,
        stage_id=stage_id,
        owner_user_id=contact.owner_user_id,
        title=title,
        status=DealStatus.OPEN,
        source_channel=payload.get("channel"),
        last_activity_at=_max_timestamp(None, occurred_at),
        last_stage_changed_at=_max_timestamp(None, occurred_at),
        metadata_json={"source": "webhook_upsert", "external_deal_id": payload.get("external_deal_id")},
    )
    session.add(row)
    session.flush()
    _refresh_primary_deal_id(session, tenant_id, contact, event_occurred_at=occurred_at)
    session.add(
        CRMDealEvent(
            tenant_id=tenant_id,
            deal_id=row.id,
            actor_user_id=None,
            event_type="created",
            stage_reason="webhook_upsert_created",
            payload={"source": "webhook_upsert", "occurred_at": occurred_at.isoformat()},
            created_at=occurred_at.replace(tzinfo=None),
        )
    )
    if event_type == "stage_changed":
        applied = _apply_webhook_stage_change(session, tenant_id, row, payload, occurred_at=occurred_at)
        stale_stage_change = not applied
    return row, stale_stage_change


def _deterministic_ab_variant(
    *,
    tenant_id: str,
    contact_id: str,
    stage: str | None,
    objection_type: str | None,
) -> tuple[str, str]:
    stage_key = (stage or "unknown").strip().lower()
    objection_key = (objection_type or "none").strip().lower()
    variant_key = f"{tenant_id}:{contact_id}:{stage_key}:{objection_key}"
    digest = hashlib.sha256(variant_key.encode("utf-8")).hexdigest()
    variant = "A" if int(digest[-1], 16) % 2 == 0 else "B"
    return variant, variant_key


def _is_textual_user_reply(payload: dict[str, Any], *, event_type: str | None) -> bool:
    if event_type != "inbound_message":
        return False
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        return False
    subtype = str(payload.get("message_subtype") or payload.get("message_type") or "").strip().lower()
    if subtype == "reaction":
        return False
    if bool(payload.get("is_reaction")):
        return False
    return True


def _process_bot_event(
    session: Session,
    tenant_id: str,
    payload: dict,
    *,
    trigger_event_id: str | None = None,
    trigger_event_key: str | None = None,
) -> dict:
    event_type = payload.get("event_type")
    occurred_at = _parse_occurred_at(payload.get("occurred_at"))
    occurred_at_naive = occurred_at.replace(tzinfo=None)
    policy = _sales_policy(session, tenant_id)
    trigger_map = {
        "inbound_message": AutomationTrigger.MESSAGE_RECEIVED,
        "intent_detected": AutomationTrigger.INTENT_DETECTED,
        "quote_sent": AutomationTrigger.QUOTE_SENT,
        "stage_changed": AutomationTrigger.STAGE_CHANGED,
        "inactivity": AutomationTrigger.INACTIVITY_TIMER,
        "order_delivered": AutomationTrigger.ORDER_DELIVERED,
    }

    contact = _upsert_contact(session, tenant_id, payload, occurred_at=occurred_at)
    conversation = _upsert_conversation(session, tenant_id, contact.id, payload, occurred_at=occurred_at)
    deal, stale_stage_change = _upsert_deal(session, tenant_id, contact, payload, occurred_at=occurred_at)
    assigned_user_id = None

    if not contact.owner_user_id and event_type == "inbound_message":
        try:
            assigned_user = AssignmentService(session, tenant_id).assign_lead(
                contact_id=contact.id,
                deal_id=(deal.id if deal else payload.get("deal_id")),
                channel=payload.get("channel", "web"),
            )
            assigned_user_id = assigned_user.id
            contact.owner_user_id = assigned_user.id
        except AssignmentError:
            assigned_user_id = None

    if event_type == "inbound_message":
        direction = MessageDirection.INBOUND
    elif event_type in {"outbound_message", "quote_sent"}:
        direction = MessageDirection.OUTBOUND
    else:
        direction = MessageDirection.SYSTEM

    stage_at_send = payload.get("stage")
    objection_type = payload.get("objection_type")
    ab_variant = payload.get("ab_variant")
    variant_key = payload.get("variant_key")
    if direction == MessageDirection.OUTBOUND and not ab_variant:
        ab_variant, variant_key = _deterministic_ab_variant(
            tenant_id=tenant_id,
            contact_id=contact.id,
            stage=stage_at_send,
            objection_type=objection_type,
        )
    if direction == MessageDirection.OUTBOUND and not variant_key:
        _, variant_key = _deterministic_ab_variant(
            tenant_id=tenant_id,
            contact_id=contact.id,
            stage=stage_at_send,
            objection_type=objection_type,
        )
    if direction == MessageDirection.OUTBOUND:
        forced_variant = _forced_ab_variant_from_policy(
            policy,
            channel=payload.get("channel"),
            stage=stage_at_send,
            objection_type=objection_type,
        )
        if forced_variant:
            ab_variant = forced_variant

    sales_meta = _normalize_sales_intelligence(
        payload,
        ab_variant=ab_variant,
        variant_key=variant_key,
        fallback_stage=stage_at_send,
    )
    payload_with_meta = dict(payload)
    payload_with_meta["sales_intelligence_v1"] = sales_meta

    message = CRMMessage(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        contact_id=contact.id,
        channel=payload.get("channel", "web"),
        direction=direction,
        body=payload.get("body"),
        external_message_id=payload.get("external_message_id"),
        idempotency_key=payload.get("idempotency_key"),
        metadata_json=payload_with_meta,
        sent_at=occurred_at_naive,
        created_at=occurred_at_naive,
    )
    session.add(message)
    session.flush()

    now_ts = occurred_at_naive
    if direction == MessageDirection.OUTBOUND:
        session.add(
            CRMMessageEvent(
                tenant_id=tenant_id,
                message_id=message.id,
                conversation_id=conversation.id,
                event_type="salesbot_outbound",
                status="sent",
                ab_variant=ab_variant,
                variant_key=variant_key,
                objection_type=objection_type,
                stage_at_send=stage_at_send,
                replied_within_24h=False,
                stage_progress_within_7d=False,
                final_outcome=None,
                payload={
                    "source": "webhook",
                    "event_type": event_type,
                    "occurred_at": occurred_at.isoformat(),
                    "sales_intelligence_v1": sales_meta,
                },
                created_at=occurred_at_naive,
            )
        )
    else:
        session.add(
            CRMMessageEvent(
                tenant_id=tenant_id,
                message_id=message.id,
                conversation_id=conversation.id,
                event_type="ingested_message",
                status="ingested",
                payload={
                    "source": "webhook",
                    "event_type": event_type,
                    "occurred_at": occurred_at.isoformat(),
                    "sales_intelligence_v1": sales_meta,
                },
                created_at=occurred_at_naive,
            )
        )

    if _is_textual_user_reply(payload, event_type=event_type):
        (
            _tenant_query(session, tenant_id, CRMMessageEvent, include_deleted=True)
            .filter(
                CRMMessageEvent.conversation_id == conversation.id,
                CRMMessageEvent.event_type == "salesbot_outbound",
                CRMMessageEvent.created_at >= now_ts - timedelta(hours=24),
                (CRMMessageEvent.replied_within_24h.is_(False)) | (CRMMessageEvent.replied_within_24h.is_(None)),
            )
            .update({CRMMessageEvent.replied_within_24h: True}, synchronize_session=False)
        )

        canceled_drafts = (
            _tenant_query(session, tenant_id, CRMOutboundDraft, include_deleted=True)
            .filter(
                CRMOutboundDraft.conversation_id == conversation.id,
                CRMOutboundDraft.status.in_(["draft", "scheduled"]),
                (CRMOutboundDraft.scheduled_for.is_(None)) | (CRMOutboundDraft.scheduled_for >= now_ts),
            )
            .all()
        )
        for row in canceled_drafts:
            row.status = "canceled"
            meta = dict(row.metadata_json or {})
            meta["stop_reason"] = "text_reply"
            meta["stopped_at"] = occurred_at.isoformat()
            row.metadata_json = meta

        canceled_tasks = 0
        pending_tasks = (
            _tenant_query(session, tenant_id, CRMTask, include_deleted=True)
            .filter(
                CRMTask.contact_id == contact.id,
                CRMTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
            )
            .all()
        )
        for task in pending_tasks:
            metadata = dict(task.metadata_json or {})
            if metadata.get("kind") != "followup":
                continue
            task.status = TaskStatus.CANCELED
            metadata["stop_reason"] = "text_reply"
            metadata["stopped_at"] = occurred_at.isoformat()
            task.metadata_json = metadata
            canceled_tasks += 1

        session.add(
            CRMMessageEvent(
                tenant_id=tenant_id,
                message_id=message.id,
                conversation_id=conversation.id,
                event_type="followup_stop_decision",
                status="applied",
                payload={
                    "reason": "text_reply",
                    "occurred_at": occurred_at.isoformat(),
                    "canceled_drafts": len(canceled_drafts),
                    "canceled_tasks": canceled_tasks,
                },
                created_at=occurred_at_naive,
            )
        )

    if event_type == "stage_changed" and not stale_stage_change:
        (
            _tenant_query(session, tenant_id, CRMMessageEvent, include_deleted=True)
            .filter(
                CRMMessageEvent.conversation_id == conversation.id,
                CRMMessageEvent.event_type == "salesbot_outbound",
                CRMMessageEvent.created_at >= now_ts - timedelta(days=7),
                (CRMMessageEvent.stage_progress_within_7d.is_(False))
                | (CRMMessageEvent.stage_progress_within_7d.is_(None)),
            )
            .update({CRMMessageEvent.stage_progress_within_7d: True}, synchronize_session=False)
        )

    if event_type == "order_delivered":
        (
            _tenant_query(session, tenant_id, CRMMessageEvent, include_deleted=True)
            .filter(
                CRMMessageEvent.conversation_id == conversation.id,
                CRMMessageEvent.event_type == "salesbot_outbound",
            )
            .update({CRMMessageEvent.final_outcome: "won"}, synchronize_session=False)
        )

    conversation.last_message_at = _max_timestamp(conversation.last_message_at, occurred_at)
    contact.last_activity_at = _max_timestamp(contact.last_activity_at, occurred_at)
    if deal is not None:
        deal.last_activity_at = _max_timestamp(deal.last_activity_at, occurred_at)
    _refresh_primary_deal_id(session, tenant_id, contact, event_occurred_at=occurred_at)

    deal_id = (deal.id if deal else payload.get("deal_id"))
    guardrail = _discount_guardrail_decision(policy=policy, payload=payload, sales_meta=sales_meta)
    if guardrail.get("blocked"):
        assignee = contact.owner_user_id or payload.get("owner_user_id") or payload.get("actor_user_id") or "system"
        task = CRMTask(
            tenant_id=tenant_id,
            title="Review discount request",
            description=(
                f"Requested discount {guardrail['proposed_discount_percent']}% exceeds max "
                f"{guardrail['max_allowed_discount_percent']}% for stage {sales_meta.get('stage') or 'UNKNOWN'}."
            ),
            status=TaskStatus.TODO,
            priority="high",
            assigned_to_user_id=assignee,
            created_by_user_id=payload.get("actor_user_id") or assignee,
            contact_id=contact.id,
            deal_id=deal_id,
            metadata_json={
                "kind": "handoff",
                "source": "sales_policy_guardrail",
                "guardrail": guardrail,
                "sales_intelligence_v1": sales_meta,
            },
        )
        session.add(task)
        sales_meta["needs_handoff"] = True
        payload_with_meta["sales_intelligence_v1"] = sales_meta
        message.metadata_json = payload_with_meta
        session.add(
            CRMMessageEvent(
                tenant_id=tenant_id,
                message_id=message.id,
                conversation_id=conversation.id,
                event_type="discount_guardrail_blocked",
                status="applied",
                payload={"guardrail": guardrail, "sales_intelligence_v1": sales_meta},
                created_at=occurred_at_naive,
            )
        )

    signal = payload.get("score_signal")
    if not signal:
        signal = {
            "inbound_message": "inbound_message",
            "quote_sent": "quote_sent",
            "inactivity": "no_reply",
        }.get(event_type)

    if deal_id and signal:
        ScoringService(session, tenant_id).apply_signal(
            deal_id=deal_id,
            signal_key=signal,
            context={
                "channel": payload.get("channel"),
                "score": payload.get("score", 0),
                "stage": payload.get("stage"),
                "tags": payload.get("tags", []),
                "product_model": payload.get("product_model"),
                "inactivity_minutes": payload.get("inactivity_minutes"),
            },
        )

    trigger = trigger_map.get(event_type)
    if event_type == "stage_changed" and stale_stage_change:
        trigger = None
    runs = []
    if trigger:
        runs = AutomationService(session, tenant_id).run_trigger(
            trigger,
            {
                "contact_id": contact.id,
                "conversation_id": conversation.id,
                "deal_id": deal_id,
                "channel": payload.get("channel"),
                "stage": sales_meta.get("stage") or payload.get("stage"),
                "intent": sales_meta.get("intent"),
                "missing_fields": sales_meta.get("missing_fields", []),
                "playbook_snippet": sales_meta.get("playbook_snippet"),
                "confidence": sales_meta.get("confidence"),
                "score": payload.get("score", 0),
                "stock_available": payload.get("stock_available", payload.get("quantity_available")),
                "tags": payload.get("tags", []),
                "product_model": payload.get("product_model"),
                "actor_user_id": payload.get("actor_user_id"),
                "owner_user_id": payload.get("owner_user_id"),
                "amount_estimated": payload.get("amount_estimated"),
                "currency": payload.get("currency", "USD"),
                "source": payload.get("source", "webhook"),
                "automation_hop": int(payload.get("automation_hop") or 0),
                "inactivity_minutes": payload.get("inactivity_minutes"),
                "occurred_at": occurred_at.isoformat(),
                "guardrail": guardrail if guardrail.get("evaluated") else None,
            },
            trigger_event_id=trigger_event_id,
            trigger_event_key=trigger_event_key,
        )

    playbook_suggestion = None
    if event_type == "intent_detected":
        objection_key = payload.get("objection_key") or payload.get("intent")
        if objection_key:
            playbooks = PlaybookService(session, tenant_id).list(
                objection_key=objection_key,
                channel=payload.get("channel"),
            )
            if playbooks:
                pick = playbooks[0]
                playbook_suggestion = {
                    "playbook_id": pick.id,
                    "objection_key": pick.objection_key,
                    "suggested_response": pick.suggested_response,
                }
                sales_meta["playbook_snippet"] = pick.suggested_response[:220]
                payload_with_meta["sales_intelligence_v1"] = sales_meta
                message.metadata_json = payload_with_meta

    return {
        "contact_id": contact.id,
        "conversation_id": conversation.id,
        "message_id": message.id,
        "deal_id": deal_id,
        "automations_executed": len(runs),
        "assigned_user_id": assigned_user_id,
        "stale_stage_change": stale_stage_change,
        "playbook_suggestion": playbook_suggestion,
        "sales_intelligence_v1": sales_meta,
        "discount_guardrail": guardrail,
    }


@crm_api.route("/orders", methods=["GET"])
@crm_auth_required
@permission_required(Permission.DEALS_READ)
def list_orders():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMOrder, include_deleted=True).order_by(CRMOrder.created_at.desc()).limit(
            200
        ).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": o.id,
                        "deal_id": o.deal_id,
                        "contact_id": o.contact_id,
                        "status": o.status,
                        "payment_status": o.payment_status,
                        "total_amount": o.total_amount,
                        "currency": o.currency,
                        "delivery_address": o.delivery_address,
                        "created_at": _serialize_datetime(o.created_at),
                    }
                    for o in rows
                ]
            }
        )
    finally:
        session.close()
