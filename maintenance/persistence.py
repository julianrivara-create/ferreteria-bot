from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extras import Json

from .locks import advisory_unlock, try_advisory_lock


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_tenant_id(conn, tenant_name: str | None) -> str | None:
    with conn.cursor() as cur:
        if tenant_name:
            cur.execute(
                """
                SELECT id
                FROM crm_tenants
                WHERE lower(business_name) = lower(%s)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (tenant_name,),
            )
            row = cur.fetchone()
            if row:
                return row[0]
        cur.execute("SELECT id FROM crm_tenants ORDER BY created_at ASC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None


def acquire_process_lock(conn, tenant_id: str, process_name: str) -> bool:
    return try_advisory_lock(conn, tenant_id, process_name)


def release_process_lock(conn, tenant_id: str, process_name: str) -> None:
    advisory_unlock(conn, tenant_id, process_name)


def read_process_state(conn, tenant_id: str, process_name: str, service_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT previous_fingerprint, previous_outcome, consecutive_fail_count, first_seen_at, last_seen_at
            FROM maintenance_state
            WHERE tenant_id = %s AND process_name = %s AND service_id = %s
            """,
            (tenant_id, process_name, service_id),
        )
        row = cur.fetchone()
    if not row:
        return {
            "previous_fingerprint": None,
            "previous_outcome": None,
            "consecutive_fail_count": 0,
            "first_seen_at": None,
            "last_seen_at": None,
        }
    return {
        "previous_fingerprint": row[0],
        "previous_outcome": row[1],
        "consecutive_fail_count": int(row[2] or 0),
        "first_seen_at": row[3],
        "last_seen_at": row[4],
    }


def upsert_process_state(
    conn,
    *,
    tenant_id: str,
    process_name: str,
    service_id: str,
    previous_fingerprint: str | None,
    previous_outcome: str | None,
    consecutive_fail_count: int,
    first_seen_at: datetime | None,
    last_seen_at: datetime | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO maintenance_state (
                tenant_id, process_name, service_id, previous_fingerprint, previous_outcome,
                consecutive_fail_count, first_seen_at, last_seen_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, process_name, service_id)
            DO UPDATE SET
                previous_fingerprint = EXCLUDED.previous_fingerprint,
                previous_outcome = EXCLUDED.previous_outcome,
                consecutive_fail_count = EXCLUDED.consecutive_fail_count,
                first_seen_at = EXCLUDED.first_seen_at,
                last_seen_at = EXCLUDED.last_seen_at,
                updated_at = NOW()
            """,
            (
                tenant_id,
                process_name,
                service_id,
                previous_fingerprint,
                previous_outcome,
                int(consecutive_fail_count),
                first_seen_at,
                last_seen_at,
            ),
        )


def insert_run(
    conn,
    *,
    run_id: str,
    tenant_id: str,
    process_name: str,
    service_id: str,
    started_at: datetime,
    finished_at: datetime,
    outcome: str,
    fingerprint: str | None,
    previous_fingerprint: str | None,
    previous_outcome: str | None,
    consecutive_fail_count: int,
    first_seen_at: datetime | None,
    last_seen_at: datetime | None,
    schema_version: str,
    code_version: str,
    summary_json: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO maintenance_runs (
                id, tenant_id, process_name, service_id, started_at, finished_at, outcome,
                fingerprint, previous_fingerprint, previous_outcome, consecutive_fail_count,
                first_seen_at, last_seen_at, schema_version, code_version, summary_json, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, NOW()
            )
            """,
            (
                run_id,
                tenant_id,
                process_name,
                service_id,
                started_at,
                finished_at,
                outcome,
                fingerprint,
                previous_fingerprint,
                previous_outcome,
                int(consecutive_fail_count),
                first_seen_at,
                last_seen_at,
                schema_version,
                code_version,
                Json(summary_json),
            ),
        )


def insert_action(
    conn,
    *,
    run_id: str,
    tenant_id: str,
    process_name: str,
    service_id: str,
    action_type: str,
    status: str,
    reason: str,
    dry_run: bool,
    provider_action_id: str | None = None,
) -> str:
    action_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO maintenance_actions (
                id, run_id, tenant_id, process_name, service_id, action_type, status,
                reason, dry_run, provider_action_id, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                action_id,
                run_id,
                tenant_id,
                process_name,
                service_id,
                action_type,
                status,
                reason[:1000],
                bool(dry_run),
                provider_action_id,
            ),
        )
    return action_id


def count_executed_actions_since(
    conn,
    *,
    tenant_id: str,
    service_id: str,
    action_type: str,
    since: datetime,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM maintenance_actions
            WHERE tenant_id = %s
              AND service_id = %s
              AND action_type = %s
              AND status = 'executed'
              AND created_at >= %s
            """,
            (tenant_id, service_id, action_type, since),
        )
        row = cur.fetchone()
    return int(row[0] or 0)


def latest_executed_action_at(
    conn,
    *,
    tenant_id: str,
    service_id: str,
    action_type: str,
) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT created_at
            FROM maintenance_actions
            WHERE tenant_id = %s
              AND service_id = %s
              AND action_type = %s
              AND status = 'executed'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id, service_id, action_type),
        )
        row = cur.fetchone()
    return row[0] if row else None


def read_dependency_state(conn, tenant_id: str, service_id: str, domain: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT fail_streak, circuit_open_until, last_error_json
            FROM maintenance_dependency_state
            WHERE tenant_id = %s AND service_id = %s AND dependency_domain = %s
            """,
            (tenant_id, service_id, domain),
        )
        row = cur.fetchone()
    if not row:
        return {"fail_streak": 0, "circuit_open_until": None, "last_error_json": None}
    return {"fail_streak": int(row[0] or 0), "circuit_open_until": row[1], "last_error_json": row[2]}


def _upsert_dependency_state(
    conn,
    *,
    tenant_id: str,
    service_id: str,
    domain: str,
    fail_streak: int,
    circuit_open_until: datetime | None,
    last_error_json: dict[str, Any] | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO maintenance_dependency_state (
                tenant_id, service_id, dependency_domain, fail_streak,
                circuit_open_until, last_error_json, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, service_id, dependency_domain)
            DO UPDATE SET
                fail_streak = EXCLUDED.fail_streak,
                circuit_open_until = EXCLUDED.circuit_open_until,
                last_error_json = EXCLUDED.last_error_json,
                updated_at = NOW()
            """,
            (tenant_id, service_id, domain, int(fail_streak), circuit_open_until, Json(last_error_json) if last_error_json else None),
        )


def mark_dependency_success(conn, tenant_id: str, service_id: str, domain: str) -> None:
    _upsert_dependency_state(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        domain=domain,
        fail_streak=0,
        circuit_open_until=None,
        last_error_json=None,
    )


def mark_dependency_failure(
    conn,
    *,
    tenant_id: str,
    service_id: str,
    domain: str,
    threshold: int,
    open_minutes: int,
    error_payload: dict[str, Any],
) -> dict[str, Any]:
    state = read_dependency_state(conn, tenant_id, service_id, domain)
    fail_streak = int(state.get("fail_streak") or 0) + 1
    open_until = state.get("circuit_open_until")
    if fail_streak >= max(1, int(threshold)):
        open_until = utcnow() + timedelta(minutes=max(1, int(open_minutes)))
    _upsert_dependency_state(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        domain=domain,
        fail_streak=fail_streak,
        circuit_open_until=open_until,
        last_error_json=error_payload,
    )
    return {"fail_streak": fail_streak, "circuit_open_until": open_until, "last_error_json": error_payload}


def latest_run_by_process(conn, tenant_id: str, process_name: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, service_id, outcome, finished_at, summary_json
            FROM maintenance_runs
            WHERE tenant_id = %s AND process_name = %s
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (tenant_id, process_name),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "service_id": row[1], "outcome": row[2], "finished_at": row[3], "summary_json": row[4] or {}}


def latest_success_run_ts(conn, tenant_id: str, process_name: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT finished_at
            FROM maintenance_runs
            WHERE tenant_id = %s
              AND process_name = %s
              AND outcome IN ('OK', 'WARN')
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (tenant_id, process_name),
        )
        row = cur.fetchone()
    return row[0] if row else None


def latest_ok_run_ts(conn, tenant_id: str, process_name: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT finished_at
            FROM maintenance_runs
            WHERE tenant_id = %s
              AND process_name = %s
              AND outcome = 'OK'
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (tenant_id, process_name),
        )
        row = cur.fetchone()
    return row[0] if row else None


def latest_outcome_at(conn, tenant_id: str, process_name: str, service_id: str, outcome: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT finished_at
            FROM maintenance_runs
            WHERE tenant_id = %s
              AND process_name = %s
              AND service_id = %s
              AND outcome = %s
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (tenant_id, process_name, service_id, outcome),
        )
        row = cur.fetchone()
    return row[0] if row else None


def persist_worker_heartbeat_audit(conn, tenant_id: str, status: str, duration_ms: int, reasons: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crm_audit_logs (
                id, tenant_id, actor_user_id, entity_type, entity_id, action,
                before_data, after_data, metadata_json, request_id, created_at
            ) VALUES (%s, %s, NULL, %s, %s, %s, NULL, NULL, %s, NULL, NOW())
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                "maintenance_worker",
                "runner",
                "heartbeat",
                Json(
                    {
                        "status": status,
                        "duration_ms": duration_ms,
                        "reasons": reasons[:5],
                        "source": "maintenance.runner",
                    }
                ),
            ),
        )


def json_fingerprint(payload: dict[str, Any]) -> str:
    import hashlib

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
