from __future__ import annotations

import base64
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session

from app.crm.api.auth import crm_auth_required, parse_pagination_args, permission_required
from app.crm.api.routes import _process_bot_event
from app.crm.domain.enums import DealStatus, MessageDirection, TaskStatus, UserRole
from app.crm.domain.permissions import Permission, ROLE_PERMISSIONS, has_permission
from app.crm.models import (
    CRMAuditLog,
    CRMAutomation,
    CRMAutomationRun,
    CRMContact,
    CRMConversation,
    CRMDeal,
    CRMDealEvent,
    CRMMessage,
    CRMMessageEvent,
    CRMOutboundDraft,
    CRMPipelineStage,
    CRMSLABreach,
    CRMTask,
    CRMTaskEvent,
    CRMTenant,
    CRMUser,
    CRMWebhookEvent,
)
from app.crm.repositories.tasks import TaskRepository
from app.crm.services.ab_variant_service import ABVariantService
from app.crm.services.audit_service import AuditService
from app.crm.services.sla_service import SLAService
from app.db.session import SessionLocal
from maintenance.paths import watchdog_state_candidates

console_api = Blueprint("console_api", __name__)


STATUS_NEEDS_ACTION = "Needs action"
STATUS_OVERDUE = "Overdue"
STATUS_HEALTHY = "Healthy"
STATUS_FAILED = "Failed"
STATUS_STALE = "Stale"

MAINT_OUTCOME_OK = "OK"
MAINT_OUTCOME_WARN = "WARN"
MAINT_OUTCOME_FAIL = "FAIL"
MAINT_OUTCOME_DEPENDENCY_ERROR = "DEPENDENCY_ERROR"

DEFAULT_STALE_WARN_MINUTES = 60
DEFAULT_STALE_FAIL_MINUTES = 180

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _get_session() -> Session:
    return SessionLocal()


def _tenant_from_auth() -> str:
    user = getattr(g, "crm_user", None)
    if not user:
        raise RuntimeError("Missing authenticated user")
    return user["tenant_id"]


def _actor_user_id() -> str | None:
    user = getattr(g, "crm_user", None)
    return user.get("id") if user else None


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    norm = value.strip().lower()
    if norm in {"1", "true", "yes", "y", "on"}:
        return True
    if norm in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _is_owner_or_admin() -> bool:
    user = getattr(g, "crm_user", None) or {}
    role = user.get("role")
    return role in {UserRole.OWNER.value, UserRole.ADMIN.value}


def _tenant_query(session: Session, tenant_id: str, model: Any, *, include_deleted: bool = False):
    query = session.query(model).filter(getattr(model, "tenant_id") == tenant_id)
    if not include_deleted and hasattr(model, "deleted_at"):
        query = query.filter(getattr(model, "deleted_at").is_(None))
    return query


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _rank_status(statuses: list[str]) -> str:
    if STATUS_FAILED in statuses:
        return STATUS_FAILED
    if STATUS_OVERDUE in statuses:
        return STATUS_OVERDUE
    if STATUS_NEEDS_ACTION in statuses:
        return STATUS_NEEDS_ACTION
    if STATUS_STALE in statuses:
        return STATUS_STALE
    return STATUS_HEALTHY


def _task_status_label(task: CRMTask) -> str:
    if task.status in {TaskStatus.DONE, TaskStatus.CANCELED}:
        return STATUS_HEALTHY
    now = _utc_now()
    due_at = _parse_dt(task.due_at)
    if due_at and due_at < now:
        return STATUS_OVERDUE
    return STATUS_NEEDS_ACTION


def _deal_status_label(deal: CRMDeal) -> str:
    if deal.status in {DealStatus.WON, DealStatus.LOST}:
        return STATUS_HEALTHY
    last_activity = _parse_dt(deal.last_activity_at or deal.updated_at or deal.created_at)
    if last_activity and last_activity < (_utc_now() - timedelta(days=2)):
        return STATUS_STALE
    return STATUS_NEEDS_ACTION


def _conversation_status_label(*, unread: bool, needs_handoff: bool, last_message_at: datetime | None) -> str:
    if needs_handoff:
        return STATUS_NEEDS_ACTION
    if unread:
        return STATUS_NEEDS_ACTION
    last_dt = _parse_dt(last_message_at)
    if last_dt and last_dt < (_utc_now() - timedelta(days=3)):
        return STATUS_STALE
    return STATUS_HEALTHY


def _state_candidates() -> list[str]:
    return watchdog_state_candidates()


def _read_watchdog_state() -> dict[str, Any]:
    for candidate in _state_candidates():
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    return __import__("json").load(handle)
            except Exception:
                continue
    return {
        "last_run_ts": None,
        "last_success_ts": None,
        "last_status": "UNKNOWN",
        "last_run_duration_ms": 0,
        "cost_counters": {
            "log_pulls_today": 0,
            "log_bytes_today": 0,
            "log_last_reset_date": _utc_now().date().isoformat(),
        },
    }


def _latest_worker_heartbeat(session: Session, tenant_id: str) -> dict[str, Any] | None:
    row = (
        _tenant_query(session, tenant_id, CRMAuditLog, include_deleted=True)
        .filter(
            CRMAuditLog.entity_type == "maintenance_worker",
            CRMAuditLog.action == "heartbeat",
        )
        .order_by(CRMAuditLog.created_at.desc())
        .first()
    )
    if row is None:
        return None

    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return {
        "created_at": row.created_at,
        "status": str(metadata.get("status") or "").upper() or None,
        "metadata": metadata,
    }


def _normalize_maintenance_outcome(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    return raw or None


def _is_degraded_maintenance_outcome(outcome: str | None) -> bool:
    return outcome in {MAINT_OUTCOME_FAIL, MAINT_OUTCOME_WARN, MAINT_OUTCOME_DEPENDENCY_ERROR}


def _maintenance_outcome_to_status(outcome: str | None) -> str:
    if outcome == MAINT_OUTCOME_FAIL:
        return STATUS_FAILED
    if outcome in {MAINT_OUTCOME_WARN, MAINT_OUTCOME_DEPENDENCY_ERROR}:
        return STATUS_NEEDS_ACTION
    return STATUS_HEALTHY


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _latest_maintenance_run(
    session: Session,
    tenant_id: str,
    process_name: str,
    *,
    outcome: str | None = None,
) -> dict[str, Any] | None:
    sql = """
        SELECT
            id,
            process_name,
            service_id,
            outcome,
            started_at,
            finished_at,
            consecutive_fail_count,
            first_seen_at,
            last_seen_at,
            schema_version,
            code_version,
            summary_json
        FROM maintenance_runs
        WHERE tenant_id = :tenant_id
          AND process_name = :process_name
    """
    params: dict[str, Any] = {"tenant_id": tenant_id, "process_name": process_name}
    if outcome:
        sql += " AND outcome = :outcome"
        params["outcome"] = outcome
    sql += " ORDER BY finished_at DESC LIMIT 1"
    try:
        row = session.execute(text(sql), params).mappings().first()
    except Exception:
        return None
    if not row:
        return None
    payload = dict(row)
    payload["summary_json"] = _as_dict(payload.get("summary_json"))
    return payload


def _latest_maintenance_state(session: Session, tenant_id: str, process_name: str) -> dict[str, Any] | None:
    try:
        row = (
            session.execute(
                text(
                    """
                    SELECT
                        service_id,
                        previous_fingerprint,
                        previous_outcome,
                        consecutive_fail_count,
                        first_seen_at,
                        last_seen_at,
                        updated_at
                    FROM maintenance_state
                    WHERE tenant_id = :tenant_id
                      AND process_name = :process_name
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "process_name": process_name},
            )
            .mappings()
            .first()
        )
    except Exception:
        return None
    return dict(row) if row else None


def _watchdog_thresholds(latest_watchdog_run: dict[str, Any] | None) -> tuple[int, int]:
    warn_minutes = DEFAULT_STALE_WARN_MINUTES
    fail_minutes = DEFAULT_STALE_FAIL_MINUTES
    if latest_watchdog_run:
        summary = _as_dict(latest_watchdog_run.get("summary_json"))
        checks = _as_dict(summary.get("checks"))
        staleness = _as_dict(checks.get("watchdog_staleness"))
        warn_candidate = _as_int(staleness.get("stale_warn_minutes"))
        fail_candidate = _as_int(staleness.get("stale_fail_minutes"))
        if warn_candidate and warn_candidate > 0:
            warn_minutes = warn_candidate
        if fail_candidate and fail_candidate > 0:
            fail_minutes = fail_candidate
    if fail_minutes < warn_minutes:
        fail_minutes = warn_minutes
    return warn_minutes, fail_minutes


def _watchdog_maintenance_context(session: Session, tenant_id: str) -> dict[str, Any]:
    state = _read_watchdog_state()
    state_last_success_ts = _parse_dt(state.get("last_success_ts"))
    state_last_run_ts = _parse_dt(state.get("last_run_ts"))
    state_status = _normalize_maintenance_outcome(state.get("last_status"))

    heartbeat_audit = _latest_worker_heartbeat(session, tenant_id)
    heartbeat_audit_ts = _parse_dt((heartbeat_audit or {}).get("created_at"))
    audit_status = _normalize_maintenance_outcome((heartbeat_audit or {}).get("status"))

    latest_runner_run = _latest_maintenance_run(session, tenant_id, "runner")
    latest_runner_ok_run = _latest_maintenance_run(
        session, tenant_id, "runner", outcome=MAINT_OUTCOME_OK
    )
    latest_watchdog_run = _latest_maintenance_run(session, tenant_id, "watchdog")
    latest_runner_state = _latest_maintenance_state(session, tenant_id, "runner")

    stale_warn_minutes, stale_fail_minutes = _watchdog_thresholds(latest_watchdog_run)

    runner_last_run_ts = _parse_dt((latest_runner_run or {}).get("finished_at"))
    runner_last_success_ts = _parse_dt((latest_runner_ok_run or {}).get("finished_at"))

    heartbeat_reference = None
    heartbeat_source = None
    if runner_last_success_ts is not None:
        heartbeat_reference = runner_last_success_ts
        heartbeat_source = "maintenance_runs_ok"
    elif runner_last_run_ts is not None:
        heartbeat_reference = runner_last_run_ts
        heartbeat_source = "maintenance_runs_last"
    elif state_last_success_ts is not None:
        heartbeat_reference = state_last_success_ts
        heartbeat_source = "last_success_ts"
    elif state_last_run_ts is not None:
        heartbeat_reference = state_last_run_ts
        heartbeat_source = "last_run_ts"
    elif heartbeat_audit_ts is not None:
        heartbeat_reference = heartbeat_audit_ts
        heartbeat_source = "audit_log"

    runner_outcome = _normalize_maintenance_outcome((latest_runner_run or {}).get("outcome"))
    if runner_outcome is None:
        if state_status in {MAINT_OUTCOME_FAIL, MAINT_OUTCOME_WARN}:
            runner_outcome = state_status
        elif audit_status in {MAINT_OUTCOME_FAIL, MAINT_OUTCOME_WARN}:
            runner_outcome = audit_status

    consecutive_fail_count = 0
    state_count = _as_int((latest_runner_state or {}).get("consecutive_fail_count"))
    run_count = _as_int((latest_runner_run or {}).get("consecutive_fail_count"))
    if state_count is not None:
        consecutive_fail_count = max(0, state_count)
    elif run_count is not None:
        consecutive_fail_count = max(0, run_count)

    return {
        "state": state,
        "state_last_success_ts": state_last_success_ts,
        "state_last_run_ts": state_last_run_ts,
        "state_status": state_status,
        "heartbeat_audit": heartbeat_audit,
        "heartbeat_audit_ts": heartbeat_audit_ts,
        "audit_status": audit_status,
        "latest_runner_run": latest_runner_run,
        "latest_runner_ok_run": latest_runner_ok_run,
        "latest_watchdog_run": latest_watchdog_run,
        "latest_runner_state": latest_runner_state,
        "stale_warn_minutes": stale_warn_minutes,
        "stale_fail_minutes": stale_fail_minutes,
        "runner_last_run_ts": runner_last_run_ts,
        "runner_last_success_ts": runner_last_success_ts,
        "heartbeat_reference": heartbeat_reference,
        "heartbeat_source": heartbeat_source,
        "runner_outcome": runner_outcome,
        "consecutive_fail_count": consecutive_fail_count,
    }


def _add_alert(
    alerts: list[dict[str, Any]],
    *,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    linked_entity: dict[str, Any],
    first_seen: datetime | None,
    last_seen: datetime | None,
    status: str = "active",
    count: int | None = None,
):
    runbook_hints = {
        "worker_heartbeat_stale": "Check maintenance-worker logs, volume mount, and heartbeat write to `MAINTENANCE_STATE_FILE` (default `/app/state/state.json`).",
        "maintenance_status_fail": "Run a one-off maintenance cycle and inspect DB/HTTP/log checks in the latest report.",
        "webhook_failures": "Inspect webhook payload schema and auth mode, then replay one failed event from Diagnostics.",
        "webhook_auth_rejections": "Validate `webhook_auth_mode` and secret rotation on sender + receiver.",
        "sla_breaches": "Review blocked deals/tasks and either resolve breach or move stage with reason.",
        "automation_failures": "Open automation run logs, inspect failing condition/action payload, then retry safely.",
        "queue_depth_high": "Drain stale drafts, pause noisy automations, and inspect follow-up pacing settings.",
    }

    alerts.append(
        {
            "type": alert_type,
            "severity": severity,
            "status": status,
            "title": title,
            "message": message,
            "count": count,
            "first_seen": _serialize_datetime(first_seen),
            "last_seen": _serialize_datetime(last_seen),
            "dedupe_key": f"{alert_type}:{linked_entity.get('kind')}:{linked_entity.get('id')}",
            "linked_entity": linked_entity,
            "runbook_hint": runbook_hints.get(alert_type, "Check diagnostics and recent events before retrying."),
        }
    )


def _build_alerts(
    session: Session,
    tenant_id: str,
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    now = _utc_now()
    alerts: list[dict[str, Any]] = []
    ctx = context or _watchdog_maintenance_context(session, tenant_id)

    heartbeat_ref = _parse_dt(ctx.get("heartbeat_reference"))
    stale_warn_minutes = int(ctx.get("stale_warn_minutes") or DEFAULT_STALE_WARN_MINUTES)
    stale_fail_minutes = int(ctx.get("stale_fail_minutes") or DEFAULT_STALE_FAIL_MINUTES)
    runner_outcome = _normalize_maintenance_outcome(ctx.get("runner_outcome"))
    runner_last_run = _as_dict(ctx.get("latest_runner_run"))
    runner_last_run_ts = _parse_dt(runner_last_run.get("finished_at"))

    if heartbeat_ref is None:
        _add_alert(
            alerts,
            alert_type="worker_heartbeat_stale",
            severity="medium",
            title="Worker heartbeat missing",
            message="No successful maintenance run found in state.",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=None,
            last_seen=None,
            status=STATUS_NEEDS_ACTION,
        )
    else:
        drift = now - heartbeat_ref
        drift_minutes = drift.total_seconds() / 60.0
        if drift_minutes >= stale_fail_minutes:
            _add_alert(
                alerts,
                alert_type="worker_heartbeat_stale",
                severity="high",
                title="Worker heartbeat stale",
                message=f"Last worker heartbeat was {round(drift_minutes, 1)}m ago.",
                linked_entity={"kind": "tenant", "id": tenant_id},
                first_seen=heartbeat_ref,
                last_seen=heartbeat_ref,
                status=STATUS_FAILED,
            )
        elif drift_minutes >= stale_warn_minutes:
            _add_alert(
                alerts,
                alert_type="worker_heartbeat_stale",
                severity="medium",
                title="Worker heartbeat approaching stale threshold",
                message=f"Last worker heartbeat was {round(drift_minutes, 1)}m ago.",
                linked_entity={"kind": "tenant", "id": tenant_id},
                first_seen=heartbeat_ref,
                last_seen=heartbeat_ref,
                status=STATUS_NEEDS_ACTION,
            )

    if _is_degraded_maintenance_outcome(runner_outcome):
        _add_alert(
            alerts,
            alert_type="maintenance_status_fail",
            severity="high" if runner_outcome == MAINT_OUTCOME_FAIL else "medium",
            title="Maintenance status degraded",
            message=f"Last maintenance status is {runner_outcome}",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=runner_last_run_ts or heartbeat_ref,
            last_seen=runner_last_run_ts or heartbeat_ref,
            status=STATUS_FAILED if runner_outcome == MAINT_OUTCOME_FAIL else STATUS_NEEDS_ACTION,
        )

    window_start = _to_naive_utc(now - timedelta(hours=24))

    webhook_failed = (
        _tenant_query(session, tenant_id, CRMWebhookEvent, include_deleted=True)
        .filter(CRMWebhookEvent.status == "failed", CRMWebhookEvent.created_at >= window_start)
        .order_by(CRMWebhookEvent.created_at.desc())
        .all()
    )
    if webhook_failed:
        _add_alert(
            alerts,
            alert_type="webhook_failures",
            severity="high",
            title="Webhook failures",
            message=f"{len(webhook_failed)} webhook events failed in the last 24h.",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=webhook_failed[-1].created_at,
            last_seen=webhook_failed[0].created_at,
            count=len(webhook_failed),
            status=STATUS_FAILED,
        )

    auth_rejections = (
        _tenant_query(session, tenant_id, CRMAuditLog, include_deleted=True)
        .filter(
            CRMAuditLog.entity_type == "webhook",
            CRMAuditLog.action == "auth_rejected",
            CRMAuditLog.created_at >= window_start,
        )
        .order_by(CRMAuditLog.created_at.desc())
        .all()
    )
    if auth_rejections:
        _add_alert(
            alerts,
            alert_type="webhook_auth_rejections",
            severity="medium",
            title="Webhook auth rejections",
            message=f"{len(auth_rejections)} webhook auth rejections in the last 24h.",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=auth_rejections[-1].created_at,
            last_seen=auth_rejections[0].created_at,
            count=len(auth_rejections),
            status=STATUS_NEEDS_ACTION,
        )

    open_breaches = (
        _tenant_query(session, tenant_id, CRMSLABreach, include_deleted=True)
        .filter(CRMSLABreach.status == "open")
        .order_by(CRMSLABreach.breached_at.desc())
        .all()
    )
    if open_breaches:
        _add_alert(
            alerts,
            alert_type="sla_breaches",
            severity="medium",
            title="Open SLA breaches",
            message=f"{len(open_breaches)} deals breached configured SLA.",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=open_breaches[-1].breached_at,
            last_seen=open_breaches[0].breached_at,
            count=len(open_breaches),
            status=STATUS_OVERDUE,
        )

    failed_runs = (
        _tenant_query(session, tenant_id, CRMAutomationRun, include_deleted=True)
        .filter(CRMAutomationRun.status.in_(["failed", "error"]), CRMAutomationRun.executed_at >= window_start)
        .order_by(CRMAutomationRun.executed_at.desc())
        .all()
    )
    if failed_runs:
        _add_alert(
            alerts,
            alert_type="automation_failures",
            severity="medium",
            title="Automation failures",
            message=f"{len(failed_runs)} automation runs failed in the last 24h.",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=failed_runs[-1].executed_at,
            last_seen=failed_runs[0].executed_at,
            count=len(failed_runs),
            status=STATUS_NEEDS_ACTION,
        )

    queue_depth = (
        _tenant_query(session, tenant_id, CRMOutboundDraft, include_deleted=True)
        .filter(CRMOutboundDraft.status.in_(["draft", "scheduled"]))
        .count()
    )
    if queue_depth > 20:
        _add_alert(
            alerts,
            alert_type="queue_depth_high",
            severity="medium",
            title="Outbound queue depth high",
            message=f"{queue_depth} queued drafts pending dispatch.",
            linked_entity={"kind": "tenant", "id": tenant_id},
            first_seen=None,
            last_seen=None,
            count=queue_depth,
            status=STATUS_NEEDS_ACTION,
        )

    alerts.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item.get("severity", "low"), 99),
            item.get("last_seen") or "",
        ),
        reverse=False,
    )
    return alerts


def _build_bot_health(session: Session, tenant_id: str) -> dict[str, Any]:
    now = _utc_now()
    since = _to_naive_utc(now - timedelta(hours=24))

    webhook_rows = (
        _tenant_query(session, tenant_id, CRMWebhookEvent, include_deleted=True)
        .filter(CRMWebhookEvent.created_at >= since)
        .order_by(CRMWebhookEvent.created_at.desc())
        .all()
    )

    total = len(webhook_rows)
    failed = sum(1 for row in webhook_rows if row.status == "failed")
    duplicate_total = sum(int(row.duplicate_count or 0) for row in webhook_rows)

    auth_rejections = (
        _tenant_query(session, tenant_id, CRMAuditLog, include_deleted=True)
        .filter(
            CRMAuditLog.entity_type == "webhook",
            CRMAuditLog.action == "auth_rejected",
            CRMAuditLog.created_at >= since,
        )
        .count()
    )

    latencies_ms: list[float] = []
    for row in webhook_rows:
        if row.processed_at and row.created_at:
            delta = (row.processed_at - row.created_at).total_seconds() * 1000
            if delta >= 0:
                latencies_ms.append(delta)
    latencies_ms.sort()
    p95_latency = 0.0
    if latencies_ms:
        p95_index = min(len(latencies_ms) - 1, int(len(latencies_ms) * 0.95))
        p95_latency = round(latencies_ms[p95_index], 2)

    error_rate = _safe_ratio(failed, total)
    duplicate_rate = _safe_ratio(duplicate_total, total)

    statuses = [STATUS_HEALTHY]
    no_traffic_24h = total == 0
    if error_rate >= 0.1:
        statuses.append(STATUS_FAILED)
    elif error_rate > 0:
        statuses.append(STATUS_NEEDS_ACTION)
    if auth_rejections > 0:
        statuses.append(STATUS_NEEDS_ACTION)

    recent_errors = [
        {
            "event_id": row.id,
            "event_key": row.event_key,
            "source": row.source,
            "error_message": row.error_message,
            "created_at": _serialize_datetime(row.created_at),
        }
        for row in webhook_rows
        if row.status == "failed"
    ][:20]

    return {
        "status": _rank_status(statuses),
        "webhook_intake_status": STATUS_HEALTHY if total == 0 or failed == 0 else (_rank_status(statuses)),
        "window_hours": 24,
        "no_traffic_24h": no_traffic_24h,
        "total_events": total,
        "failed_events": failed,
        "auth_rejections": auth_rejections,
        "latency_p95_ms": p95_latency,
        "error_rate": error_rate,
        "duplicate_rate": duplicate_rate,
        "recent_errors": recent_errors,
    }


def _build_watchdog_health(session: Session, tenant_id: str) -> dict[str, Any]:
    ctx = _watchdog_maintenance_context(session, tenant_id)
    alerts = _build_alerts(session, tenant_id, context=ctx)
    severity_counts = Counter(alert["severity"] for alert in alerts if alert.get("status") in {"active", STATUS_FAILED, STATUS_NEEDS_ACTION, STATUS_OVERDUE, STATUS_STALE})

    state = _as_dict(ctx.get("state"))
    last_success = _parse_dt(ctx.get("runner_last_success_ts")) or _parse_dt(ctx.get("state_last_success_ts"))
    last_run = _parse_dt(ctx.get("runner_last_run_ts")) or _parse_dt(ctx.get("state_last_run_ts"))
    heartbeat_audit_ts = _parse_dt(ctx.get("heartbeat_audit_ts"))
    heartbeat_reference = _parse_dt(ctx.get("heartbeat_reference"))
    stale_warn_minutes = int(ctx.get("stale_warn_minutes") or DEFAULT_STALE_WARN_MINUTES)
    stale_fail_minutes = int(ctx.get("stale_fail_minutes") or DEFAULT_STALE_FAIL_MINUTES)
    runner_outcome = _normalize_maintenance_outcome(ctx.get("runner_outcome"))

    heartbeat_minutes = None
    heartbeat_source = str(ctx.get("heartbeat_source") or "") or None
    worker_status = STATUS_NEEDS_ACTION
    if heartbeat_reference is not None:
        heartbeat_minutes = round((_utc_now() - heartbeat_reference).total_seconds() / 60.0, 2)
        if heartbeat_minutes >= stale_fail_minutes:
            worker_status = STATUS_FAILED
        elif heartbeat_minutes >= stale_warn_minutes:
            worker_status = STATUS_NEEDS_ACTION
        else:
            worker_status = STATUS_HEALTHY
    if runner_outcome:
        worker_status = _rank_status([worker_status, _maintenance_outcome_to_status(runner_outcome)])

    db_ok = False
    try:
        db_ok = bool(session.execute(text("SELECT 1")).scalar() == 1)
    except Exception:
        db_ok = False

    queue_depth = (
        _tenant_query(session, tenant_id, CRMOutboundDraft, include_deleted=True)
        .filter(CRMOutboundDraft.status.in_(["draft", "scheduled"]))
        .count()
    )

    job_failures = (
        _tenant_query(session, tenant_id, CRMAutomationRun, include_deleted=True)
        .filter(CRMAutomationRun.status.in_(["failed", "error"]), CRMAutomationRun.executed_at >= _to_naive_utc(_utc_now() - timedelta(hours=24)))
        .count()
    )

    api_status = STATUS_HEALTHY
    db_status = STATUS_HEALTHY if db_ok else STATUS_FAILED
    queue_status = STATUS_HEALTHY if queue_depth <= 20 else STATUS_NEEDS_ACTION

    statuses = [api_status, db_status, worker_status, queue_status]
    if job_failures > 0:
        statuses.append(STATUS_NEEDS_ACTION)
    if any(alert["severity"] == "critical" for alert in alerts):
        statuses.append(STATUS_FAILED)

    return {
        "status": _rank_status(statuses),
        "checks": {
            "api": {"status": api_status},
            "db": {"status": db_status},
            "workers": {
                "status": worker_status,
                "last_success_ts": _serialize_datetime(last_success),
                "last_run_ts": _serialize_datetime(last_run),
                "last_audit_heartbeat_ts": _serialize_datetime(heartbeat_audit_ts),
                "heartbeat_source": heartbeat_source,
                "heartbeat_minutes": heartbeat_minutes,
                "stale_warn_minutes": stale_warn_minutes,
                "stale_fail_minutes": stale_fail_minutes,
                "last_runner_outcome": runner_outcome,
                "consecutive_fail_count": int(ctx.get("consecutive_fail_count") or 0),
                "schema_version": (ctx.get("latest_runner_run") or {}).get("schema_version"),
                "code_version": (ctx.get("latest_runner_run") or {}).get("code_version"),
            },
            "jobs": {"status": STATUS_HEALTHY if job_failures == 0 else STATUS_NEEDS_ACTION, "job_failures": job_failures},
            "webhook_intake": {"status": _build_bot_health(session, tenant_id)["status"]},
            "queue_depth": {"status": queue_status, "depth": queue_depth},
        },
        "active_alerts_by_severity": {
            "critical": severity_counts.get("critical", 0),
            "high": severity_counts.get("high", 0),
            "medium": severity_counts.get("medium", 0),
            "low": severity_counts.get("low", 0),
        },
        "job_failures": job_failures,
        "alerts_total": len(alerts),
    }


def _stage_maps(session: Session, tenant_id: str) -> tuple[dict[str, str], dict[str, str]]:
    rows = (
        _tenant_query(session, tenant_id, CRMPipelineStage, include_deleted=True)
        .order_by(CRMPipelineStage.position.asc())
        .all()
    )
    by_id = {row.id: row.name for row in rows}
    by_upper_name = {row.name.upper(): row.id for row in rows}
    return by_id, by_upper_name


def _stage_name(stage_map: dict[str, str], stage_id: str | None) -> str:
    if not stage_id:
        return "UNKNOWN"
    return (stage_map.get(stage_id) or stage_id).upper()


def _encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def _decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    if not value:
        return None
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        ts, row_id = raw.split("|", 1)
        parsed = _parse_dt(ts)
        if parsed is None:
            return None
        return _to_naive_utc(parsed), row_id
    except Exception:
        return None


@console_api.route("/home", methods=["GET"])
@crm_auth_required
@permission_required(Permission.REPORTS_READ)
def home_dashboard():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        stage_by_id, _ = _stage_maps(session, tenant_id)
        today_start = _to_naive_utc(_utc_now().replace(hour=0, minute=0, second=0, microsecond=0))
        tomorrow_start = today_start + timedelta(days=1)
        yesterday_start = today_start - timedelta(days=1)

        tracked = ["NEW", "QUALIFIED", "QUOTED", "NEGOTIATING", "WON", "LOST"]
        today_counts = Counter({key: 0 for key in tracked})
        yesterday_counts = Counter({key: 0 for key in tracked})

        events_today = (
            _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True)
            .filter(
                CRMDealEvent.event_type.in_(["created", "stage_changed"]),
                CRMDealEvent.created_at >= today_start,
                CRMDealEvent.created_at < tomorrow_start,
            )
            .all()
        )
        for event in events_today:
            payload = event.payload or {}
            stage = _stage_name(stage_by_id, payload.get("to_stage") or payload.get("stage_id"))
            if stage in tracked:
                today_counts[stage] += 1

        events_yesterday = (
            _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True)
            .filter(
                CRMDealEvent.event_type.in_(["created", "stage_changed"]),
                CRMDealEvent.created_at >= yesterday_start,
                CRMDealEvent.created_at < today_start,
            )
            .all()
        )
        for event in events_yesterday:
            payload = event.payload or {}
            stage = _stage_name(stage_by_id, payload.get("to_stage") or payload.get("stage_id"))
            if stage in tracked:
                yesterday_counts[stage] += 1

        won_today = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.status == DealStatus.WON, CRMDeal.closed_at >= today_start, CRMDeal.closed_at < tomorrow_start)
            .count()
        )
        lost_today = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.status == DealStatus.LOST, CRMDeal.closed_at >= today_start, CRMDeal.closed_at < tomorrow_start)
            .count()
        )
        won_yesterday = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.status == DealStatus.WON, CRMDeal.closed_at >= yesterday_start, CRMDeal.closed_at < today_start)
            .count()
        )
        lost_yesterday = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.status == DealStatus.LOST, CRMDeal.closed_at >= yesterday_start, CRMDeal.closed_at < today_start)
            .count()
        )

        today_counts["WON"] = won_today
        today_counts["LOST"] = lost_today
        yesterday_counts["WON"] = won_yesterday
        yesterday_counts["LOST"] = lost_yesterday

        overdue_tasks = (
            _tenant_query(session, tenant_id, CRMTask)
            .filter(
                CRMTask.status.notin_([TaskStatus.DONE, TaskStatus.CANCELED]),
                CRMTask.due_at.isnot(None),
                CRMTask.due_at < _to_naive_utc(_utc_now()),
            )
            .count()
        )
        sla_breaches = _tenant_query(session, tenant_id, CRMSLABreach, include_deleted=True).filter(CRMSLABreach.status == "open").count()
        stuck_deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(
                CRMDeal.status == DealStatus.OPEN,
                CRMDeal.last_activity_at.isnot(None),
                CRMDeal.last_activity_at < _to_naive_utc(_utc_now() - timedelta(days=2)),
            )
            .count()
        )

        followup_candidates = (
            _tenant_query(session, tenant_id, CRMTask)
            .filter(
                CRMTask.status.notin_([TaskStatus.DONE, TaskStatus.CANCELED]),
                CRMTask.due_at.isnot(None),
                CRMTask.due_at <= _to_naive_utc(_utc_now()),
            )
            .all()
        )
        followups_due = 0
        for task in followup_candidates:
            metadata = task.metadata_json or {}
            if isinstance(metadata, dict) and metadata.get("kind") == "followup":
                followups_due += 1

        bot_health = _build_bot_health(session, tenant_id)
        watchdog = _build_watchdog_health(session, tenant_id)

        sales_status = STATUS_HEALTHY if today_counts["WON"] >= today_counts["LOST"] else STATUS_NEEDS_ACTION
        action_status = STATUS_HEALTHY
        if overdue_tasks or sla_breaches:
            action_status = STATUS_OVERDUE
        elif stuck_deals or followups_due:
            action_status = STATUS_NEEDS_ACTION

        trend = {name: today_counts[name] - yesterday_counts[name] for name in tracked}

        payload = {
            "request_id": getattr(g, "request_id", None),
            "sales_today": {
                "status": sales_status,
                "counts": {name: int(today_counts[name]) for name in tracked},
                "trend_vs_yesterday": trend,
                "view_all_href": "/crm?view=sales_today",
            },
            "action_required": {
                "status": action_status,
                "overdue_tasks": overdue_tasks,
                "sla_breaches": sla_breaches,
                "stuck_deals": stuck_deals,
                "followups_due": followups_due,
                "total": overdue_tasks + sla_breaches + stuck_deals + followups_due,
                "view_all_href": "/crm?view=action_required",
            },
            "bot_health": {
                **bot_health,
                "view_all_href": "/bot",
            },
            "watchdog": {
                **watchdog,
                "view_all_href": "/watchdog",
            },
        }
        return jsonify(payload)
    finally:
        session.close()


@console_api.route("/search", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def global_search():
    tenant_id = _tenant_from_auth()
    query = (request.args.get("q") or "").strip()
    if not query:
        return _json_error("q is required", 400)

    limit = min(25, max(1, int(request.args.get("limit", "15"))))
    q_lower = query.lower()
    like = f"%{q_lower}%"

    session = _get_session()
    try:
        contacts = (
            _tenant_query(session, tenant_id, CRMContact)
            .filter(
                or_(
                    func.lower(CRMContact.name).like(like),
                    func.lower(CRMContact.email).like(like),
                    CRMContact.phone.like(f"%{query}%"),
                    CRMContact.id == query,
                )
            )
            .order_by(CRMContact.last_activity_at.desc(), CRMContact.created_at.desc())
            .limit(limit)
            .all()
        )

        deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(
                or_(
                    CRMDeal.id == query,
                    func.lower(CRMDeal.title).like(like),
                    CRMDeal.contact_id == query,
                )
            )
            .order_by(CRMDeal.last_activity_at.desc(), CRMDeal.created_at.desc())
            .limit(limit)
            .all()
        )

        conversations = (
            _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
            .filter(
                or_(
                    CRMConversation.id == query,
                    CRMConversation.external_id == query,
                    CRMConversation.contact_id == query,
                )
            )
            .order_by(CRMConversation.last_message_at.desc(), CRMConversation.created_at.desc())
            .limit(limit)
            .all()
        )

        tasks = (
            _tenant_query(session, tenant_id, CRMTask)
            .filter(
                or_(
                    CRMTask.id == query,
                    func.lower(CRMTask.title).like(like),
                    CRMTask.deal_id == query,
                    CRMTask.contact_id == query,
                )
            )
            .order_by(CRMTask.due_at.asc().nullslast(), CRMTask.created_at.desc())
            .limit(limit)
            .all()
        )

        webhook_events = (
            _tenant_query(session, tenant_id, CRMWebhookEvent, include_deleted=True)
            .filter(
                or_(
                    CRMWebhookEvent.id == query,
                    CRMWebhookEvent.event_key == query,
                    func.lower(CRMWebhookEvent.event_type).like(like),
                )
            )
            .order_by(CRMWebhookEvent.created_at.desc())
            .limit(limit)
            .all()
        )

        alerts = [
            alert
            for alert in _build_alerts(session, tenant_id)
            if q_lower in (alert.get("title", "") + " " + alert.get("message", "") + " " + alert.get("dedupe_key", "")).lower()
        ][:limit]

        return jsonify(
            {
                "request_id": getattr(g, "request_id", None),
                "query": query,
                "groups": [
                    {
                        "type": "Contact",
                        "items": [
                            {
                                "id": row.id,
                                "label": row.name,
                                "sub_label": row.email or row.phone,
                                "status": STATUS_NEEDS_ACTION if row.score >= 70 else STATUS_HEALTHY,
                                "href": f"/detail/contact/{row.id}",
                            }
                            for row in contacts
                        ],
                    },
                    {
                        "type": "Deal",
                        "items": [
                            {
                                "id": row.id,
                                "label": row.title,
                                "sub_label": row.contact_id,
                                "status": _deal_status_label(row),
                                "href": f"/detail/contact/{row.contact_id}" if row.contact_id else f"/detail/deal/{row.id}",
                            }
                            for row in deals
                        ],
                    },
                    {
                        "type": "Conversation",
                        "items": [
                            {
                                "id": row.id,
                                "label": row.external_id or row.id,
                                "sub_label": row.channel,
                                "status": STATUS_HEALTHY if row.is_open else STATUS_STALE,
                                "href": f"/detail/conversation/{row.id}",
                            }
                            for row in conversations
                        ],
                    },
                    {
                        "type": "Task",
                        "items": [
                            {
                                "id": row.id,
                                "label": row.title,
                                "sub_label": row.deal_id or row.contact_id,
                                "status": _task_status_label(row),
                                "href": f"/detail/contact/{row.contact_id}" if row.contact_id else (f"/detail/deal/{row.deal_id}" if row.deal_id else f"/detail/task/{row.id}"),
                            }
                            for row in tasks
                        ],
                    },
                    {
                        "type": "Webhook Event",
                        "items": [
                            {
                                "id": row.id,
                                "label": row.event_key,
                                "sub_label": f"{row.source}:{row.event_type}",
                                "status": STATUS_FAILED if row.status == "failed" else STATUS_HEALTHY,
                                "href": (
                                    f"/detail/conversation/{(row.payload or {}).get('conversation_id')}"
                                    if isinstance(row.payload, dict) and (row.payload or {}).get("conversation_id")
                                    else (
                                        f"/detail/contact/{(row.payload or {}).get('contact_id')}"
                                        if isinstance(row.payload, dict) and (row.payload or {}).get("contact_id")
                                        else "/watchdog"
                                    )
                                ),
                            }
                            for row in webhook_events
                        ],
                    },
                    {
                        "type": "Alert",
                        "items": [
                            {
                                "id": row["dedupe_key"],
                                "label": row["title"],
                                "sub_label": row["message"],
                                "status": STATUS_FAILED if row["severity"] in {"critical", "high"} else STATUS_NEEDS_ACTION,
                                "href": "/watchdog",
                            }
                            for row in alerts
                        ],
                    },
                ],
            }
        )
    finally:
        session.close()


def _conversation_summary(
    session: Session,
    tenant_id: str,
    conversation: CRMConversation,
    *,
    stage_by_id: dict[str, str],
) -> dict[str, Any]:
    latest_message = (
        _tenant_query(session, tenant_id, CRMMessage, include_deleted=True)
        .filter(CRMMessage.conversation_id == conversation.id)
        .order_by(CRMMessage.created_at.desc())
        .first()
    )
    contact = _tenant_query(session, tenant_id, CRMContact).filter(CRMContact.id == conversation.contact_id).first()
    primary_deal = None
    if contact and contact.primary_deal_id:
        primary_deal = _tenant_query(session, tenant_id, CRMDeal).filter(CRMDeal.id == contact.primary_deal_id).first()

    metadata = (latest_message.metadata_json if latest_message and isinstance(latest_message.metadata_json, dict) else {}) or {}
    sales_meta = metadata.get("sales_intelligence_v1") if isinstance(metadata.get("sales_intelligence_v1"), dict) else {}
    merged_meta = {**metadata, **sales_meta}

    unread = bool(conversation.metadata_json.get("unread") if isinstance(conversation.metadata_json, dict) else False)
    if latest_message:
        direction = latest_message.direction.value if hasattr(latest_message.direction, "value") else str(latest_message.direction)
        unread = unread or direction == MessageDirection.INBOUND.value

    needs_handoff = bool(merged_meta.get("needs_handoff") or merged_meta.get("handoff_required"))
    high_intent = bool(merged_meta.get("high_intent")) or (float(merged_meta.get("confidence") or 0) >= 0.85)
    intent = merged_meta.get("intent")
    stage = merged_meta.get("stage") or (stage_by_id.get(primary_deal.stage_id) if primary_deal else None)

    return {
        "id": conversation.id,
        "contact_id": conversation.contact_id,
        "contact_name": contact.name if contact else None,
        "channel": conversation.channel,
        "external_id": conversation.external_id,
        "last_message_at": _serialize_datetime(conversation.last_message_at),
        "is_open": conversation.is_open,
        "last_message_preview": latest_message.body if latest_message else None,
        "unread": unread,
        "needs_handoff": needs_handoff,
        "high_intent": high_intent,
        "intent": intent,
        "stage": (stage or "UNKNOWN").upper() if isinstance(stage, str) else "UNKNOWN",
        "status": _conversation_status_label(
            unread=unread,
            needs_handoff=needs_handoff,
            last_message_at=conversation.last_message_at,
        ),
    }


@console_api.route("/conversations", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONVERSATIONS_READ)
def list_console_conversations():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()

    channel_filter = request.args.get("channel")
    unread_filter = _parse_bool(request.args.get("unread"))
    needs_handoff_filter = _parse_bool(request.args.get("needs_handoff"))
    high_intent_filter = _parse_bool(request.args.get("high_intent"))
    intent_filter = (request.args.get("intent") or "").strip().lower()
    stage_filter = (request.args.get("stage") or "").strip().upper()

    session = _get_session()
    try:
        stage_by_id, _ = _stage_maps(session, tenant_id)
        query = _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
        if channel_filter:
            query = query.filter(CRMConversation.channel == channel_filter)
        rows = query.order_by(CRMConversation.last_message_at.desc(), CRMConversation.created_at.desc()).limit(600).all()

        enriched = [_conversation_summary(session, tenant_id, row, stage_by_id=stage_by_id) for row in rows]

        if unread_filter is not None:
            enriched = [row for row in enriched if bool(row["unread"]) is unread_filter]
        if needs_handoff_filter is not None:
            enriched = [row for row in enriched if bool(row["needs_handoff"]) is needs_handoff_filter]
        if high_intent_filter is not None:
            enriched = [row for row in enriched if bool(row["high_intent"]) is high_intent_filter]
        if intent_filter:
            enriched = [row for row in enriched if (row.get("intent") or "").lower() == intent_filter]
        if stage_filter:
            enriched = [row for row in enriched if (row.get("stage") or "").upper() == stage_filter]

        total = len(enriched)
        start = (pagination["page"] - 1) * pagination["page_size"]
        end = start + pagination["page_size"]
        paged = enriched[start:end]

        return jsonify(
            {
                "items": paged,
                "pagination": {
                    "page": pagination["page"],
                    "page_size": pagination["page_size"],
                    "total": total,
                    "pages": (total + pagination["page_size"] - 1) // pagination["page_size"],
                },
            }
        )
    finally:
        session.close()


def _extract_output_contract(messages: list[CRMMessage]) -> dict[str, Any] | None:
    for msg in reversed(messages):
        metadata = msg.metadata_json if isinstance(msg.metadata_json, dict) else None
        if not metadata:
            continue
        sales_meta = metadata.get("sales_intelligence_v1")
        if isinstance(sales_meta, dict):
            return sales_meta
        if "missing_fields" in metadata or "suggested_actions" in metadata or "objection_type" in metadata:
            return metadata
    return None


def _relevant_webhook_events(
    session: Session,
    tenant_id: str,
    *,
    conversation: CRMConversation,
    contact: CRMContact | None,
    deal_ids: set[str],
) -> list[CRMWebhookEvent]:
    rows = (
        _tenant_query(session, tenant_id, CRMWebhookEvent, include_deleted=True)
        .order_by(CRMWebhookEvent.created_at.desc())
        .limit(200)
        .all()
    )

    result: list[CRMWebhookEvent] = []
    contact_phone = (contact.phone or "") if contact else ""
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if payload.get("conversation_id") == conversation.id:
            result.append(row)
            continue
        if conversation.external_id and payload.get("conversation_external_id") == conversation.external_id:
            result.append(row)
            continue
        if payload.get("contact_id") == conversation.contact_id:
            result.append(row)
            continue
        if contact_phone and str(payload.get("phone") or "") == contact_phone:
            result.append(row)
            continue
        if deal_ids and payload.get("deal_id") in deal_ids:
            result.append(row)
            continue
    return result[:50]


@console_api.route("/conversation/<conversation_id>", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONVERSATIONS_READ)
def conversation_detail(conversation_id: str):
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        stage_by_id, _ = _stage_maps(session, tenant_id)
        conversation = (
            _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
            .filter(CRMConversation.id == conversation_id)
            .first()
        )
        if conversation is None:
            return _json_error("Conversation not found", 404)

        contact = _tenant_query(session, tenant_id, CRMContact).filter(CRMContact.id == conversation.contact_id).first()

        messages = (
            _tenant_query(session, tenant_id, CRMMessage, include_deleted=True)
            .filter(CRMMessage.conversation_id == conversation.id)
            .order_by(CRMMessage.created_at.asc())
            .limit(300)
            .all()
        )

        deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.contact_id == conversation.contact_id)
            .order_by(CRMDeal.updated_at.desc(), CRMDeal.created_at.desc())
            .all()
        )
        deal_ids = {row.id for row in deals}

        tasks = (
            _tenant_query(session, tenant_id, CRMTask)
            .filter(or_(CRMTask.contact_id == conversation.contact_id, CRMTask.deal_id.in_(deal_ids if deal_ids else ["__none__"])))
            .order_by(CRMTask.due_at.asc().nullslast(), CRMTask.created_at.desc())
            .limit(200)
            .all()
        )

        deal_events = []
        if deal_ids:
            deal_events = (
                _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True)
                .filter(CRMDealEvent.deal_id.in_(list(deal_ids)))
                .order_by(CRMDealEvent.created_at.desc())
                .limit(200)
                .all()
            )

        task_ids = [task.id for task in tasks]
        task_events = []
        if task_ids:
            task_events = (
                _tenant_query(session, tenant_id, CRMTaskEvent, include_deleted=True)
                .filter(CRMTaskEvent.task_id.in_(task_ids))
                .order_by(CRMTaskEvent.created_at.desc())
                .limit(200)
                .all()
            )

        automation_runs = (
            _tenant_query(session, tenant_id, CRMAutomationRun, include_deleted=True)
            .order_by(CRMAutomationRun.executed_at.desc())
            .limit(100)
            .all()
        )
        filtered_runs = [
            row
            for row in automation_runs
            if isinstance(row.event_payload, dict)
            and (
                row.event_payload.get("conversation_id") == conversation.id
                or row.event_payload.get("contact_id") == conversation.contact_id
                or row.event_payload.get("deal_id") in deal_ids
            )
        ][:50]

        webhook_events = _relevant_webhook_events(
            session,
            tenant_id,
            conversation=conversation,
            contact=contact,
            deal_ids=deal_ids,
        )

        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        auth_mode = tenant.webhook_auth_mode if tenant else "token"

        diagnostics_events = []
        for event in webhook_events[:50]:
            payload = event.payload if isinstance(event.payload, dict) else {}
            occurred_at = _parse_dt(payload.get("occurred_at"))
            received_at = _parse_dt(event.created_at)
            auth_method = str(payload.get("auth_method") or "unknown")
            mode_match = None
            if auth_method != "unknown":
                if auth_mode == "both":
                    mode_match = auth_method in {"token", "hmac"}
                else:
                    mode_match = auth_method == auth_mode
            diagnostics_events.append(
                {
                    "id": event.id,
                    "event_key": event.event_key,
                    "event_type": event.event_type,
                    "status": event.status,
                    "auth_method": auth_method,
                    "auth_mode": auth_mode,
                    "auth_mode_match": mode_match,
                    "occurred_at": _serialize_datetime(occurred_at),
                    "received_at": _serialize_datetime(received_at),
                    "processed_at": _serialize_datetime(event.processed_at),
                    "duplicate_count": event.duplicate_count,
                    "error_message": event.error_message,
                }
            )

        output_contract = _extract_output_contract(messages)
        summary = _conversation_summary(session, tenant_id, conversation, stage_by_id=stage_by_id)
        primary_actions = [
            {"id": "create_task", "label": "Create task", "type": "task"},
            {"id": "move_stage", "label": "Move stage", "type": "deal"},
            {"id": "send_followup", "label": "Send follow-up", "type": "message"},
        ]

        return jsonify(
            {
                "request_id": getattr(g, "request_id", None),
                "conversation": summary,
                "overview": {
                    "contact": {
                        "id": contact.id if contact else None,
                        "name": contact.name if contact else None,
                        "phone": contact.phone if contact else None,
                        "email": contact.email if contact else None,
                        "primary_deal_id": contact.primary_deal_id if contact else None,
                    },
                    "detected": {
                        "intent": output_contract.get("intent") if output_contract else None,
                        "objection_type": output_contract.get("objection_type") if output_contract else None,
                        "stage": output_contract.get("stage") if output_contract else None,
                        "missing_fields": output_contract.get("missing_fields") if output_contract else [],
                        "confidence": output_contract.get("confidence") if output_contract else None,
                    },
                    "playbook_snippet": output_contract.get("playbook_snippet") if output_contract else None,
                    "suggested_actions": primary_actions,
                },
                "messages": [
                    {
                        "id": row.id,
                        "direction": row.direction.value if hasattr(row.direction, "value") else str(row.direction),
                        "body": row.body,
                        "channel": row.channel,
                        "created_at": _serialize_datetime(row.created_at),
                        "metadata": row.metadata_json if isinstance(row.metadata_json, dict) else {},
                    }
                    for row in messages
                ],
                "deals": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "stage_id": row.stage_id,
                        "stage": _stage_name(stage_by_id, row.stage_id),
                        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                        "score": row.score,
                        "amount_estimated": row.amount_estimated,
                        "currency": row.currency,
                        "last_activity_at": _serialize_datetime(row.last_activity_at),
                    }
                    for row in deals
                ],
                "tasks": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                        "priority": row.priority,
                        "due_at": _serialize_datetime(row.due_at),
                        "assigned_to_user_id": row.assigned_to_user_id,
                    }
                    for row in tasks
                ],
                "events": {
                    "deal_events": [
                        {
                            "id": row.id,
                            "deal_id": row.deal_id,
                            "event_type": row.event_type,
                            "stage_reason": row.stage_reason,
                            "payload": row.payload if isinstance(row.payload, dict) else {},
                            "created_at": _serialize_datetime(row.created_at),
                        }
                        for row in deal_events
                    ],
                    "task_events": [
                        {
                            "id": row.id,
                            "task_id": row.task_id,
                            "event_type": row.event_type,
                            "payload": row.payload if isinstance(row.payload, dict) else {},
                            "created_at": _serialize_datetime(row.created_at),
                        }
                        for row in task_events
                    ],
                    "automation_runs": [
                        {
                            "id": row.id,
                            "automation_id": row.automation_id,
                            "status": row.status,
                            "actions_count": row.actions_count,
                            "trigger_type": row.trigger_type,
                            "error_message": row.error_message,
                            "executed_at": _serialize_datetime(row.executed_at),
                        }
                        for row in filtered_runs
                    ],
                },
                "diagnostics": {
                    "status": _rank_status([
                        STATUS_FAILED if any(item["status"] == "failed" for item in diagnostics_events) else STATUS_HEALTHY,
                        STATUS_NEEDS_ACTION if any(item["duplicate_count"] for item in diagnostics_events) else STATUS_HEALTHY,
                    ]),
                    "request_id": getattr(g, "request_id", None),
                    "webhook_auth_mode": auth_mode,
                    "recent_webhook_events": diagnostics_events,
                    "output_contract": output_contract,
                    "recent_errors": [item for item in diagnostics_events if item["status"] == "failed"],
                    "debug_visible": _is_owner_or_admin(),
                },
            }
        )
    finally:
        session.close()


@console_api.route("/contacts/<contact_id>", methods=["GET"])
@crm_auth_required
@permission_required(Permission.CONTACTS_READ)
def contact_detail(contact_id: str):
    tenant_id = _tenant_from_auth()
    timeline_limit = min(100, max(1, int(request.args.get("timeline_limit", "30"))))
    timeline_cursor = _decode_cursor(request.args.get("timeline_cursor"))

    session = _get_session()
    try:
        stage_by_id, _ = _stage_maps(session, tenant_id)
        contact = _tenant_query(session, tenant_id, CRMContact).filter(CRMContact.id == contact_id).first()
        if contact is None:
            return _json_error("Contact not found", 404)

        deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.contact_id == contact_id)
            .order_by(CRMDeal.updated_at.desc())
            .all()
        )
        deal_ids = [row.id for row in deals]

        conversations = (
            _tenant_query(session, tenant_id, CRMConversation, include_deleted=True)
            .filter(CRMConversation.contact_id == contact_id)
            .order_by(CRMConversation.last_message_at.desc())
            .all()
        )
        conversation_ids = [row.id for row in conversations]

        tasks = (
            _tenant_query(session, tenant_id, CRMTask)
            .filter(or_(CRMTask.contact_id == contact_id, CRMTask.deal_id.in_(deal_ids if deal_ids else ["__none__"])))
            .order_by(CRMTask.due_at.asc().nullslast(), CRMTask.created_at.desc())
            .all()
        )
        task_ids = [row.id for row in tasks]

        messages_query = _tenant_query(session, tenant_id, CRMMessage, include_deleted=True)
        if conversation_ids:
            messages_query = messages_query.filter(CRMMessage.conversation_id.in_(conversation_ids))
        else:
            messages_query = messages_query.filter(text("1=0"))

        deal_events_query = _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True)
        if deal_ids:
            deal_events_query = deal_events_query.filter(CRMDealEvent.deal_id.in_(deal_ids))
        else:
            deal_events_query = deal_events_query.filter(text("1=0"))

        task_events_query = _tenant_query(session, tenant_id, CRMTaskEvent, include_deleted=True)
        if task_ids:
            task_events_query = task_events_query.filter(CRMTaskEvent.task_id.in_(task_ids))
        else:
            task_events_query = task_events_query.filter(text("1=0"))

        if timeline_cursor is not None:
            cursor_dt, cursor_id = timeline_cursor
            messages_query = messages_query.filter(
                or_(
                    CRMMessage.created_at < cursor_dt,
                    and_(CRMMessage.created_at == cursor_dt, CRMMessage.id < cursor_id),
                )
            )
            deal_events_query = deal_events_query.filter(
                or_(
                    CRMDealEvent.created_at < cursor_dt,
                    and_(CRMDealEvent.created_at == cursor_dt, CRMDealEvent.id < cursor_id),
                )
            )
            task_events_query = task_events_query.filter(
                or_(
                    CRMTaskEvent.created_at < cursor_dt,
                    and_(CRMTaskEvent.created_at == cursor_dt, CRMTaskEvent.id < cursor_id),
                )
            )

        messages = messages_query.order_by(CRMMessage.created_at.desc(), CRMMessage.id.desc()).limit(timeline_limit).all()
        deal_events = deal_events_query.order_by(CRMDealEvent.created_at.desc(), CRMDealEvent.id.desc()).limit(timeline_limit).all()
        task_events = task_events_query.order_by(CRMTaskEvent.created_at.desc(), CRMTaskEvent.id.desc()).limit(timeline_limit).all()

        timeline_rows: list[dict[str, Any]] = []
        for row in messages:
            timeline_rows.append(
                {
                    "id": row.id,
                    "type": "message",
                    "created_at": row.created_at,
                    "payload": {
                        "conversation_id": row.conversation_id,
                        "direction": row.direction.value if hasattr(row.direction, "value") else str(row.direction),
                        "body": row.body,
                        "channel": row.channel,
                    },
                }
            )
        for row in deal_events:
            timeline_rows.append(
                {
                    "id": row.id,
                    "type": "deal_event",
                    "created_at": row.created_at,
                    "payload": {
                        "deal_id": row.deal_id,
                        "event_type": row.event_type,
                        "stage_reason": row.stage_reason,
                        "metadata": row.payload if isinstance(row.payload, dict) else {},
                    },
                }
            )
        for row in task_events:
            timeline_rows.append(
                {
                    "id": row.id,
                    "type": "task_event",
                    "created_at": row.created_at,
                    "payload": {
                        "task_id": row.task_id,
                        "event_type": row.event_type,
                        "metadata": row.payload if isinstance(row.payload, dict) else {},
                    },
                }
            )

        timeline_rows.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        timeline_rows = timeline_rows[:timeline_limit]

        next_cursor = None
        if timeline_rows:
            tail = timeline_rows[-1]
            next_cursor = _encode_cursor(tail["created_at"], tail["id"])

        open_deals = [row for row in deals if row.status == DealStatus.OPEN]
        open_deals.sort(
            key=lambda row: (
                row.last_activity_at or row.updated_at or row.created_at,
                row.updated_at or row.created_at,
                row.id,
            ),
            reverse=True,
        )
        primary_reason = None
        if contact.primary_deal_id:
            if open_deals and open_deals[0].id == contact.primary_deal_id:
                primary_reason = "Primary deal is the most recently active open deal."
            elif open_deals:
                primary_reason = "Primary deal is pinned and not displaced by older activity."
            else:
                primary_reason = "Primary deal is preserved while no open alternatives exist."

        return jsonify(
            {
                "contact": {
                    "id": contact.id,
                    "name": contact.name,
                    "phone": contact.phone,
                    "email": contact.email,
                    "source_channel": contact.source_channel,
                    "score": contact.score,
                    "owner_user_id": contact.owner_user_id,
                    "primary_deal_id": contact.primary_deal_id,
                    "primary_deal_reasoning": primary_reason,
                    "last_activity_at": _serialize_datetime(contact.last_activity_at),
                },
                "conversations": [
                    {
                        "id": row.id,
                        "channel": row.channel,
                        "external_id": row.external_id,
                        "last_message_at": _serialize_datetime(row.last_message_at),
                    }
                    for row in conversations
                ],
                "deals": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "stage": _stage_name(stage_by_id, row.stage_id),
                        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                        "amount_estimated": row.amount_estimated,
                        "last_activity_at": _serialize_datetime(row.last_activity_at),
                    }
                    for row in deals
                ],
                "tasks": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                        "due_at": _serialize_datetime(row.due_at),
                        "priority": row.priority,
                    }
                    for row in tasks
                ],
                "timeline": [
                    {
                        "id": row["id"],
                        "type": row["type"],
                        "created_at": _serialize_datetime(row["created_at"]),
                        **row["payload"],
                    }
                    for row in timeline_rows
                ],
                "timeline_next_cursor": next_cursor,
            }
        )
    finally:
        session.close()


@console_api.route("/deals", methods=["GET"])
@crm_auth_required
@permission_required(Permission.DEALS_READ)
def list_console_deals():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()

    stage_filter = request.args.get("stage")
    search = (request.args.get("search") or "").strip()
    owner_filter = request.args.get("owner")
    channel_filter = request.args.get("channel")
    status_filter = request.args.get("status")
    high_score_min = request.args.get("high_score_min")
    sla_only = _parse_bool(request.args.get("sla_breach"))
    last_activity_after = _parse_dt(request.args.get("last_activity_after"))

    session = _get_session()
    try:
        stage_by_id, stage_id_by_name = _stage_maps(session, tenant_id)
        query = _tenant_query(session, tenant_id, CRMDeal)

        if stage_filter:
            stage_id = stage_id_by_name.get(stage_filter.upper(), stage_filter)
            query = query.filter(CRMDeal.stage_id == stage_id)
        if owner_filter:
            query = query.filter(CRMDeal.owner_user_id == owner_filter)
        if channel_filter:
            query = query.filter(CRMDeal.source_channel == channel_filter)
        if status_filter:
            query = query.filter(CRMDeal.status == status_filter)
        if high_score_min:
            try:
                query = query.filter(CRMDeal.score >= int(high_score_min))
            except ValueError:
                pass
        if last_activity_after:
            query = query.filter(CRMDeal.last_activity_at >= _to_naive_utc(last_activity_after))
        if search:
            search_like = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    CRMDeal.id == search,
                    CRMDeal.contact_id == search,
                    func.lower(CRMDeal.title).like(search_like),
                )
            )

        rows = query.order_by(CRMDeal.last_activity_at.desc(), CRMDeal.updated_at.desc()).all()

        if sla_only:
            breach_ids = {
                row.deal_id
                for row in _tenant_query(session, tenant_id, CRMSLABreach, include_deleted=True)
                .filter(CRMSLABreach.status == "open")
                .all()
            }
            rows = [row for row in rows if row.id in breach_ids]

        total = len(rows)
        start = (pagination["page"] - 1) * pagination["page_size"]
        end = start + pagination["page_size"]
        paged = rows[start:end]

        open_breach_count_by_deal = Counter(
            row.deal_id
            for row in _tenant_query(session, tenant_id, CRMSLABreach, include_deleted=True)
            .filter(CRMSLABreach.status == "open")
            .all()
        )

        can_stage_change = has_permission(getattr(g, "crm_user", {}).get("role"), Permission.DEALS_STAGE_CHANGE)

        return jsonify(
            {
                "items": [
                    {
                        "id": row.id,
                        "contact_id": row.contact_id,
                        "title": row.title,
                        "stage_id": row.stage_id,
                        "stage": _stage_name(stage_by_id, row.stage_id),
                        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                        "score": row.score,
                        "amount_estimated": row.amount_estimated,
                        "amount_final": row.amount_final,
                        "currency": row.currency,
                        "source_channel": row.source_channel,
                        "owner_user_id": row.owner_user_id,
                        "last_activity_at": _serialize_datetime(row.last_activity_at),
                        "sla_breaches": open_breach_count_by_deal.get(row.id, 0),
                        "status_label": _deal_status_label(row),
                        "can_stage_change": can_stage_change,
                    }
                    for row in paged
                ],
                "pagination": {
                    "page": pagination["page"],
                    "page_size": pagination["page_size"],
                    "total": total,
                    "pages": (total + pagination["page_size"] - 1) // pagination["page_size"],
                },
            }
        )
    finally:
        session.close()


@console_api.route("/deals/<deal_id>/stage", methods=["POST"])
@crm_auth_required
@permission_required(Permission.DEALS_STAGE_CHANGE)
def change_deal_stage(deal_id: str):
    tenant_id = _tenant_from_auth()
    actor_user_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    stage_ref = payload.get("stage_id") or payload.get("stage")
    if not stage_ref:
        return _json_error("stage_id or stage is required", 400)

    occurred_at = _parse_dt(payload.get("occurred_at")) or _utc_now()
    stage_reason = str(payload.get("stage_reason") or "console_stage_change")

    session = _get_session()
    try:
        stage_by_id, stage_id_by_name = _stage_maps(session, tenant_id)
        stage_id = stage_id_by_name.get(str(stage_ref).upper(), str(stage_ref))
        if stage_id not in stage_by_id:
            return _json_error("Stage not found", 404)

        deal = _tenant_query(session, tenant_id, CRMDeal).filter(CRMDeal.id == deal_id).first()
        if deal is None:
            return _json_error("Deal not found", 404)

        before = {
            "stage_id": deal.stage_id,
            "status": deal.status.value if hasattr(deal.status, "value") else str(deal.status),
            "last_stage_changed_at": _serialize_datetime(deal.last_stage_changed_at),
        }

        previous_stage = deal.stage_id
        deal.stage_id = stage_id
        deal.last_activity_at = _to_naive_utc(occurred_at)
        deal.last_stage_changed_at = _to_naive_utc(occurred_at)

        session.add(
            CRMDealEvent(
                tenant_id=tenant_id,
                deal_id=deal.id,
                actor_user_id=actor_user_id,
                event_type="stage_changed",
                stage_reason=stage_reason,
                payload={
                    "from_stage": previous_stage,
                    "to_stage": stage_id,
                    "occurred_at": occurred_at.isoformat(),
                    "source": "console",
                },
                created_at=_to_naive_utc(occurred_at),
            )
        )

        AuditService(session, tenant_id, actor_user_id).log(
            entity_type="deal",
            entity_id=deal.id,
            action="stage_change",
            before_data=before,
            after_data={
                "stage_id": deal.stage_id,
                "status": deal.status.value if hasattr(deal.status, "value") else str(deal.status),
                "last_stage_changed_at": _serialize_datetime(deal.last_stage_changed_at),
            },
            metadata_json={"stage_reason": stage_reason},
        )
        session.commit()

        return jsonify(
            {
                "id": deal.id,
                "stage_id": deal.stage_id,
                "stage": _stage_name(stage_by_id, deal.stage_id),
                "status": deal.status.value if hasattr(deal.status, "value") else str(deal.status),
                "request_id": getattr(g, "request_id", None),
            }
        )
    finally:
        session.close()


@console_api.route("/tasks", methods=["GET"])
@crm_auth_required
@permission_required(Permission.TASKS_READ)
def list_console_tasks():
    tenant_id = _tenant_from_auth()
    pagination = parse_pagination_args()
    status_filter = request.args.get("status")
    due_scope = request.args.get("due_scope")
    assigned_to = request.args.get("assigned_to_user_id")

    session = _get_session()
    try:
        repo = TaskRepository(session, tenant_id)
        rows, total = repo.list(
            page=pagination["page"],
            page_size=pagination["page_size"],
            sort_by=pagination["sort_by"],
            sort_dir=pagination["sort_dir"],
            filters={
                "status": status_filter,
                "due_scope": due_scope,
                "assigned_to_user_id": assigned_to,
            },
        )

        now = _utc_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today_start + timedelta(days=1)
        buckets = {"today": 0, "overdue": 0, "upcoming": 0}

        for row in _tenant_query(session, tenant_id, CRMTask).all():
            if row.status in {TaskStatus.DONE, TaskStatus.CANCELED}:
                continue
            due_at = _parse_dt(row.due_at)
            if due_at is None:
                buckets["upcoming"] += 1
                continue
            if due_at < now:
                buckets["overdue"] += 1
            elif today_start <= due_at < tomorrow:
                buckets["today"] += 1
            else:
                buckets["upcoming"] += 1

        return jsonify(
            {
                "items": [
                    {
                        "id": row.id,
                        "contact_id": row.contact_id,
                        "deal_id": row.deal_id,
                        "assigned_to_user_id": row.assigned_to_user_id,
                        "title": row.title,
                        "description": row.description,
                        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                        "priority": row.priority,
                        "due_at": _serialize_datetime(row.due_at),
                        "completed_at": _serialize_datetime(row.completed_at),
                        "status_label": _task_status_label(row),
                    }
                    for row in rows
                ],
                "buckets": buckets,
                "pagination": {
                    "page": pagination["page"],
                    "page_size": pagination["page_size"],
                    "total": total,
                    "pages": (total + pagination["page_size"] - 1) // pagination["page_size"],
                },
            }
        )
    finally:
        session.close()


@console_api.route("/tasks/bulk-complete", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_BULK)
def console_bulk_complete_tasks():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids", [])
    if not isinstance(task_ids, list) or not task_ids:
        return _json_error("task_ids must be a non-empty list", 400)

    session = _get_session()
    try:
        now = _to_naive_utc(_utc_now())
        count = TaskRepository(session, tenant_id).bulk_mark_done(task_ids, now)

        rows = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.id.in_(task_ids)).all()
        for row in rows:
            session.add(
                CRMTaskEvent(
                    tenant_id=tenant_id,
                    task_id=row.id,
                    actor_user_id=actor_id,
                    event_type="completed",
                    payload={"bulk": True},
                    created_at=now,
                )
            )

        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id="bulk",
            action="bulk_update",
            metadata_json={"operation": "bulk_complete", "count": count, "task_ids": task_ids},
        )
        session.commit()
        return jsonify({"updated": count, "request_id": getattr(g, "request_id", None)})
    finally:
        session.close()


@console_api.route("/tasks/bulk-reassign", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_BULK)
def console_bulk_reassign_tasks():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids", [])
    assignee = payload.get("assigned_to_user_id")
    if not isinstance(task_ids, list) or not task_ids or not assignee:
        return _json_error("task_ids and assigned_to_user_id are required", 400)

    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.id.in_(task_ids)).all()
        now = _to_naive_utc(_utc_now())
        for row in rows:
            row.assigned_to_user_id = assignee
            session.add(
                CRMTaskEvent(
                    tenant_id=tenant_id,
                    task_id=row.id,
                    actor_user_id=actor_id,
                    event_type="reassigned",
                    payload={"assigned_to_user_id": assignee, "bulk": True},
                    created_at=now,
                )
            )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id="bulk",
            action="bulk_update",
            metadata_json={"operation": "bulk_reassign", "task_ids": task_ids, "assigned_to_user_id": assignee},
        )
        session.commit()
        return jsonify({"updated": len(rows), "request_id": getattr(g, "request_id", None)})
    finally:
        session.close()


@console_api.route("/tasks/bulk-reschedule", methods=["POST"])
@crm_auth_required
@permission_required(Permission.TASKS_BULK)
def console_bulk_reschedule_tasks():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids", [])
    due_at = _parse_dt(payload.get("due_at"))
    if not isinstance(task_ids, list) or not task_ids or due_at is None:
        return _json_error("task_ids and due_at (ISO datetime) are required", 400)

    session = _get_session()
    try:
        rows = _tenant_query(session, tenant_id, CRMTask).filter(CRMTask.id.in_(task_ids)).all()
        now = _to_naive_utc(_utc_now())
        due_naive = _to_naive_utc(due_at)
        for row in rows:
            row.due_at = due_naive
            session.add(
                CRMTaskEvent(
                    tenant_id=tenant_id,
                    task_id=row.id,
                    actor_user_id=actor_id,
                    event_type="rescheduled",
                    payload={"due_at": due_at.isoformat(), "bulk": True},
                    created_at=now,
                )
            )
        AuditService(session, tenant_id, actor_id).log(
            entity_type="task",
            entity_id="bulk",
            action="bulk_update",
            metadata_json={"operation": "bulk_reschedule", "task_ids": task_ids, "due_at": due_at.isoformat()},
        )
        session.commit()
        return jsonify({"updated": len(rows), "request_id": getattr(g, "request_id", None)})
    finally:
        session.close()


@console_api.route("/watchdog/health", methods=["GET"])
@crm_auth_required
@permission_required(Permission.SETTINGS_READ)
def watchdog_health():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        return jsonify({"request_id": getattr(g, "request_id", None), **_build_watchdog_health(session, tenant_id)})
    finally:
        session.close()


@console_api.route("/watchdog/alerts", methods=["GET"])
@crm_auth_required
@permission_required(Permission.SETTINGS_READ)
def watchdog_alerts():
    tenant_id = _tenant_from_auth()
    severity_filter = request.args.get("severity")
    status_filter = request.args.get("status")

    session = _get_session()
    try:
        rows = _build_alerts(session, tenant_id)
        if severity_filter:
            rows = [row for row in rows if row.get("severity") == severity_filter]
        if status_filter:
            rows = [row for row in rows if str(row.get("status", "")).lower() == status_filter.lower()]

        return jsonify({"items": rows, "total": len(rows), "request_id": getattr(g, "request_id", None)})
    finally:
        session.close()


def _require_admin_for_watchdog_action() -> tuple[bool, tuple[Any, int] | None]:
    if not _is_owner_or_admin():
        return False, _json_error("Action requires Owner/Admin", 403)
    return True, None


@console_api.route("/watchdog/actions/<action>", methods=["POST"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def watchdog_actions(action: str):
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    session = _get_session()
    try:
        ok, error = _require_admin_for_watchdog_action()
        if not ok:
            return error

        action = action.strip().lower()
        if action == "rerun-job":
            job_name = str(payload.get("job_name") or "sla_check")
            result: dict[str, Any] = {"job_name": job_name, "status": "queued"}
            if job_name == "sla_check":
                breaches = SLAService(session, tenant_id).check_stage_breaches()
                result = {"job_name": job_name, "status": "executed", "breaches_detected": len(breaches)}
            AuditService(session, tenant_id, actor_id).log(
                entity_type="watchdog_action",
                entity_id=job_name,
                action="rerun_job",
                metadata_json=result,
            )
            session.commit()
            return jsonify({"ok": True, "action": action, "result": result, "request_id": getattr(g, "request_id", None)})

        if action == "replay-webhook":
            event_id = payload.get("event_id")
            if not event_id:
                return _json_error("event_id is required", 400)
            row = _tenant_query(session, tenant_id, CRMWebhookEvent, include_deleted=True).filter(CRMWebhookEvent.id == event_id).first()
            if row is None:
                return _json_error("Webhook event not found", 404)

            try:
                result = _process_bot_event(
                    session=session,
                    tenant_id=tenant_id,
                    payload=row.payload if isinstance(row.payload, dict) else {},
                    trigger_event_id=f"console_replay:{row.id}",
                    trigger_event_key=f"console_replay:{row.source}:{row.event_type}:{row.event_key}",
                )
                row.status = "processed"
                row.processed_at = _to_naive_utc(_utc_now())
                row.error_message = None
            except Exception as exc:
                row.status = "failed"
                row.processed_at = _to_naive_utc(_utc_now())
                row.error_message = str(exc)[:1000]
                session.commit()
                return _json_error(f"Replay failed: {exc}", 500)

            AuditService(session, tenant_id, actor_id).log(
                entity_type="watchdog_action",
                entity_id=row.id,
                action="replay_webhook",
                metadata_json={"event_key": row.event_key, "event_type": row.event_type},
            )
            session.commit()
            return jsonify({"ok": True, "action": action, "result": result, "request_id": getattr(g, "request_id", None)})

        if action == "pause-automations":
            minutes = int(payload.get("minutes") or 60)
            until = _utc_now() + timedelta(minutes=max(1, minutes))
            rows = _tenant_query(session, tenant_id, CRMAutomation, include_deleted=True).filter(CRMAutomation.enabled.is_(True)).all()
            for row in rows:
                row.enabled = False

            tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
            if tenant:
                settings = tenant.integration_settings or {}
                settings["automations_paused_until"] = until.isoformat()
                tenant.integration_settings = settings

            AuditService(session, tenant_id, actor_id).log(
                entity_type="watchdog_action",
                entity_id="automations",
                action="pause_automations",
                metadata_json={"minutes": minutes, "paused_count": len(rows), "paused_until": until.isoformat()},
            )
            session.commit()
            return jsonify(
                {
                    "ok": True,
                    "action": action,
                    "result": {"paused_count": len(rows), "paused_until": until.isoformat()},
                    "request_id": getattr(g, "request_id", None),
                }
            )

        if action == "drain-queue":
            rows = (
                _tenant_query(session, tenant_id, CRMOutboundDraft, include_deleted=True)
                .filter(CRMOutboundDraft.status.in_(["draft", "scheduled"]))
                .all()
            )
            canceled = 0
            for row in rows:
                row.status = "canceled"
                metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
                metadata["drained_by"] = actor_id
                metadata["drained_at"] = _utc_now().isoformat()
                row.metadata_json = metadata
                canceled += 1

            AuditService(session, tenant_id, actor_id).log(
                entity_type="watchdog_action",
                entity_id="queue",
                action="drain_queue",
                metadata_json={"canceled": canceled},
            )
            session.commit()
            return jsonify(
                {
                    "ok": True,
                    "action": action,
                    "result": {"canceled": canceled},
                    "request_id": getattr(g, "request_id", None),
                }
            )

        return _json_error("Unknown action", 404)
    finally:
        session.close()


def _parse_range() -> tuple[datetime, datetime]:
    now = _utc_now()
    date_from = _parse_dt(request.args.get("date_from")) or (now - timedelta(days=30))
    date_to = _parse_dt(request.args.get("date_to")) or now
    if date_to <= date_from:
        date_to = date_from + timedelta(days=1)
    return date_from, date_to


def _group_by_local_day(values: list[datetime]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        if value.tzinfo is None:
            key = value.date().isoformat()
        else:
            key = value.astimezone(timezone.utc).date().isoformat()
        counts[key] += 1
    return dict(sorted(counts.items()))


@console_api.route("/reports/kpi", methods=["GET"])
@crm_auth_required
@permission_required(Permission.REPORTS_READ)
def reports_kpi():
    tenant_id = _tenant_from_auth()
    start, end = _parse_range()
    start_naive = _to_naive_utc(start)
    end_naive = _to_naive_utc(end)

    session = _get_session()
    try:
        stage_by_id, stage_id_by_name = _stage_maps(session, tenant_id)
        quoted_stage_ids = {stage_id_by_name.get("QUOTED")} - {None}

        contacts = (
            _tenant_query(session, tenant_id, CRMContact)
            .filter(CRMContact.created_at >= start_naive, CRMContact.created_at < end_naive)
            .all()
        )

        deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(CRMDeal.created_at < end_naive)
            .all()
        )
        deal_by_id = {row.id: row for row in deals}
        contact_by_id = {
            row.id: row
            for row in _tenant_query(session, tenant_id, CRMContact)
            .filter(CRMContact.id.in_([deal.contact_id for deal in deals] or ["__none__"]))
            .all()
        }

        quote_events = (
            _tenant_query(session, tenant_id, CRMDealEvent, include_deleted=True)
            .filter(
                CRMDealEvent.event_type.in_(["created", "stage_changed"]),
                CRMDealEvent.created_at >= start_naive,
                CRMDealEvent.created_at < end_naive,
            )
            .all()
        )

        quoted_times: list[datetime] = []
        quoted_deal_ids: set[str] = set()
        time_to_quote_hours: list[float] = []
        for event in quote_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            stage_id = payload.get("to_stage") or payload.get("stage_id")
            if stage_id not in quoted_stage_ids and _stage_name(stage_by_id, stage_id) != "QUOTED":
                continue
            quoted_times.append(event.created_at)
            quoted_deal_ids.add(event.deal_id)
            deal = deal_by_id.get(event.deal_id)
            if not deal:
                continue
            contact = contact_by_id.get(deal.contact_id)
            if not contact:
                continue
            delta = (event.created_at - contact.created_at).total_seconds() / 3600.0
            if delta >= 0:
                time_to_quote_hours.append(delta)

        won_deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(
                CRMDeal.status == DealStatus.WON,
                CRMDeal.closed_at.isnot(None),
                CRMDeal.closed_at >= start_naive,
                CRMDeal.closed_at < end_naive,
            )
            .all()
        )

        closed_deals = (
            _tenant_query(session, tenant_id, CRMDeal)
            .filter(
                CRMDeal.status.in_([DealStatus.WON, DealStatus.LOST]),
                CRMDeal.closed_at.isnot(None),
                CRMDeal.closed_at >= start_naive,
                CRMDeal.closed_at < end_naive,
            )
            .all()
        )

        time_to_close_hours = []
        for deal in closed_deals:
            delta = (deal.closed_at - deal.created_at).total_seconds() / 3600.0
            if delta >= 0:
                time_to_close_hours.append(delta)

        leads_total = len(contacts)
        quoted_total = len(quoted_deal_ids)
        won_total = len(won_deals)

        return jsonify(
            {
                "request_id": getattr(g, "request_id", None),
                "window": {"from": start.isoformat(), "to": end.isoformat()},
                "series": {
                    "leads_per_day": _group_by_local_day([row.created_at for row in contacts]),
                    "quoted_per_day": _group_by_local_day(quoted_times),
                    "won_per_day": _group_by_local_day([row.closed_at for row in won_deals if row.closed_at]),
                },
                "totals": {
                    "leads": leads_total,
                    "quoted": quoted_total,
                    "won": won_total,
                },
                "conversion_rates": {
                    "lead_to_quote": _safe_ratio(quoted_total, leads_total),
                    "quote_to_won": _safe_ratio(won_total, quoted_total),
                    "lead_to_won": _safe_ratio(won_total, leads_total),
                },
                "median_time_to_quote_hours": round(median(time_to_quote_hours), 2) if time_to_quote_hours else 0.0,
                "median_time_to_close_hours": round(median(time_to_close_hours), 2) if time_to_close_hours else 0.0,
            }
        )
    finally:
        session.close()


@console_api.route("/reports/ab-variants", methods=["GET"])
@crm_auth_required
@permission_required(Permission.REPORTS_READ)
def reports_ab_variants():
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
                and_(CRMMessage.tenant_id == CRMMessageEvent.tenant_id, CRMMessage.id == CRMMessageEvent.message_id),
            )
            .with_entities(
                CRMMessage.channel,
                CRMMessageEvent.stage_at_send,
                CRMMessageEvent.objection_type,
                CRMMessageEvent.ab_variant,
                func.count(CRMMessageEvent.id).label("sent"),
                func.sum(case((CRMMessageEvent.replied_within_24h.is_(True), 1), else_=0)).label("reply_24h"),
                func.sum(case((CRMMessageEvent.stage_progress_within_7d.is_(True), 1), else_=0)).label("stage_progress_7d"),
                func.sum(case((CRMMessageEvent.final_outcome == "won", 1), else_=0)).label("won"),
                func.sum(case((CRMMessageEvent.final_outcome == "lost", 1), else_=0)).label("lost"),
            )
            .filter(CRMMessageEvent.event_type == "salesbot_outbound", CRMMessageEvent.ab_variant.isnot(None))
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
            segment_key = (channel or "unknown", stage_at_send or "unknown", objection_type or "NONE")
            segment = segments.setdefault(
                segment_key,
                {
                    "channel": segment_key[0],
                    "stage": segment_key[1],
                    "objection_type": segment_key[2],
                    "totals": {"sent": 0, "reply_24h": 0, "stage_progress_7d": 0, "won": 0, "lost": 0},
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
                    "reply_24h_rate": _safe_ratio(int(reply_24h or 0), max(sent, 1)),
                    "stage_progress_7d_rate": _safe_ratio(int(stage_progress_7d or 0), max(sent, 1)),
                    "won_rate": _safe_ratio(int(won or 0), max(sent, 1)),
                    "lost_rate": _safe_ratio(int(lost or 0), max(sent, 1)),
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
            sent_total = max(1, int(segment["totals"]["sent"]))
            items.append(
                {
                    **segment,
                    "totals": {
                        **segment["totals"],
                        "reply_24h_rate": _safe_ratio(segment["totals"]["reply_24h"], sent_total),
                        "stage_progress_7d_rate": _safe_ratio(segment["totals"]["stage_progress_7d"], sent_total),
                        "won_rate": _safe_ratio(segment["totals"]["won"], sent_total),
                        "lost_rate": _safe_ratio(segment["totals"]["lost"], sent_total),
                    },
                }
            )

        autopromote = ABVariantService(session, tenant_id).evaluate(apply=autopromote_requested)
        if autopromote_requested:
            session.commit()

        return jsonify(
            {
                "filters": {"channel": channel_filter, "stage": stage_filter, "objection_type": objection_filter},
                "items": items,
                "autopromote": autopromote,
            }
        )
    finally:
        session.close()


@console_api.route("/settings/tenant", methods=["GET"])
@crm_auth_required
@permission_required(Permission.SETTINGS_READ)
def get_tenant_settings():
    tenant_id = _tenant_from_auth()
    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        if tenant is None:
            return _json_error("Tenant not found", 404)

        users = _tenant_query(session, tenant_id, CRMUser, include_deleted=True).order_by(CRMUser.full_name.asc()).all()
        role_counts = Counter((row.role.value if hasattr(row.role, "value") else str(row.role)) for row in users)

        integration = tenant.integration_settings or {}
        thresholds = integration.get("thresholds") if isinstance(integration.get("thresholds"), dict) else {}

        return jsonify(
            {
                "tenant": {
                    "id": tenant.id,
                    "business_name": tenant.business_name,
                    "timezone": tenant.timezone,
                    "channels": tenant.channels,
                    "quiet_hours_start": tenant.quiet_hours_start,
                    "quiet_hours_end": tenant.quiet_hours_end,
                    "followup_min_interval_minutes": tenant.followup_min_interval_minutes,
                    "webhook_auth_mode": tenant.webhook_auth_mode,
                },
                "thresholds": {
                    "high_value_ready_to_pay": thresholds.get("high_value_ready_to_pay", 0),
                    "objection_loop_limit": thresholds.get("objection_loop_limit", 3),
                    "handoff_rules": thresholds.get("handoff_rules", {}),
                },
                "channel_settings": {
                    "web": "web" in (tenant.channels or []),
                    "instagram": "instagram" in (tenant.channels or []),
                    "whatsapp": "whatsapp" in (tenant.channels or []),
                },
                "rbac": {
                    "role_counts": role_counts,
                    "permission_matrix": {
                        role.value if hasattr(role, "value") else str(role): sorted(list(perms))
                        for role, perms in ROLE_PERMISSIONS.items()
                    },
                },
            }
        )
    finally:
        session.close()


@console_api.route("/settings/tenant", methods=["POST"])
@crm_auth_required
@permission_required(Permission.SETTINGS_WRITE)
def update_tenant_settings():
    tenant_id = _tenant_from_auth()
    actor_id = _actor_user_id()
    payload = request.get_json(silent=True) or {}

    session = _get_session()
    try:
        tenant = session.query(CRMTenant).filter(CRMTenant.id == tenant_id).first()
        if tenant is None:
            return _json_error("Tenant not found", 404)

        before = {
            "timezone": tenant.timezone,
            "quiet_hours_start": tenant.quiet_hours_start,
            "quiet_hours_end": tenant.quiet_hours_end,
            "followup_min_interval_minutes": tenant.followup_min_interval_minutes,
            "webhook_auth_mode": tenant.webhook_auth_mode,
            "channels": tenant.channels,
            "integration_settings": tenant.integration_settings,
        }

        allowed_fields = {
            "timezone",
            "quiet_hours_start",
            "quiet_hours_end",
            "followup_min_interval_minutes",
            "webhook_auth_mode",
            "channels",
        }
        for key in allowed_fields:
            if key in payload:
                setattr(tenant, key, payload[key])

        if "thresholds" in payload and isinstance(payload["thresholds"], dict):
            integration = tenant.integration_settings or {}
            integration["thresholds"] = {
                **(integration.get("thresholds") or {}),
                **payload["thresholds"],
            }
            tenant.integration_settings = integration

        after = {
            "timezone": tenant.timezone,
            "quiet_hours_start": tenant.quiet_hours_start,
            "quiet_hours_end": tenant.quiet_hours_end,
            "followup_min_interval_minutes": tenant.followup_min_interval_minutes,
            "webhook_auth_mode": tenant.webhook_auth_mode,
            "channels": tenant.channels,
            "integration_settings": tenant.integration_settings,
        }

        AuditService(session, tenant_id, actor_id).log(
            entity_type="tenant_settings",
            entity_id=tenant_id,
            action="update",
            before_data=before,
            after_data=after,
            metadata_json={"source": "console"},
        )
        session.commit()
        return jsonify({"status": "updated", "request_id": getattr(g, "request_id", None)})
    finally:
        session.close()
