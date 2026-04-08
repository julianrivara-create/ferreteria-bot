from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import SCHEMA_VERSION, load_tenant_config
from .db import connect_db, resolve_db_url
from .logging_config import logger
from .mailer import send_email
from .persistence import (
    acquire_process_lock,
    count_executed_actions_since,
    ensure_tenant_id,
    insert_action,
    insert_run,
    latest_executed_action_at,
    latest_ok_run_ts,
    latest_run_by_process,
    read_process_state,
    release_process_lock,
    upsert_process_state,
    utcnow,
)
from .railway_client import RailwayClient, RailwayDependencyError
from .state import read_state, write_state
from .types import ACTION_RESTART, OUTCOME_FAIL, OUTCOME_OK, OUTCOME_WARN


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_with_error(value: Any) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, "missing timestamp"
    raw = str(value).strip()
    if not raw:
        return None, "missing timestamp"
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except Exception as exc:
        return None, f"invalid timestamp '{value}': {exc}"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc), None


def _state_runner_heartbeat(state: dict[str, Any]) -> tuple[datetime | None, str | None]:
    if not isinstance(state, dict):
        return None, "state payload is not an object"
    raw = state.get("last_run_ts")
    if raw in (None, ""):
        # Backward compatibility for old state snapshots.
        raw = state.get("last_success_ts")
    return _parse_iso_with_error(raw)


def _reason_key(reason_codes: list[str]) -> str:
    uniq = sorted({str(x).strip() for x in reason_codes if str(x).strip()})
    return ",".join(uniq) if uniq else "none"


def _watchdog_fingerprint(tenant_cfg: dict[str, Any], source: str, reason_codes: list[str]) -> str:
    tenant = str(tenant_cfg.get("tenant_name") or "unknown")
    return f"WATCHDOG_STALE|tenant={tenant}|source={source}|reason={_reason_key(reason_codes)}"


def _within_minutes(dt: datetime | None, now: datetime, minutes: int) -> bool:
    if not dt:
        return False
    ref = dt
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref > (now - timedelta(minutes=max(1, int(minutes))))


def _watchdog_cooldown_minutes(outcome: str, tenant_cfg: dict[str, Any]) -> int:
    watchdog_cfg = tenant_cfg.get("watchdog") or {}
    if outcome == OUTCOME_FAIL:
        return int(watchdog_cfg.get("fail_cooldown_minutes", 45))
    return int(watchdog_cfg.get("warn_cooldown_minutes", 240))


def _should_send_deduped_alert(
    *,
    outcome: str,
    fingerprint: str | None,
    previous_fingerprint: str | None,
    previous_outcome: str | None,
    previous_alert_sent_at: datetime | None,
    now: datetime,
    tenant_cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    if outcome not in {OUTCOME_WARN, OUTCOME_FAIL}:
        return False, None
    if not fingerprint:
        return True, None
    cooldown = _watchdog_cooldown_minutes(outcome, tenant_cfg)
    if previous_outcome == outcome and previous_fingerprint == fingerprint and _within_minutes(
        previous_alert_sent_at, now, cooldown
    ):
        return False, f"cooldown active ({cooldown}m) for {fingerprint}"
    return True, None


def _evaluate_heartbeat(
    *,
    heartbeat_ts: datetime | None,
    now: datetime,
    warn_minutes: int,
    fail_minutes: int,
    state_parse_error: str | None = None,
) -> tuple[str, list[str], list[str], float | None]:
    outcome = OUTCOME_OK
    reasons: list[str] = []
    reason_codes: list[str] = []
    drift_minutes: float | None = None

    if heartbeat_ts is None:
        outcome = OUTCOME_WARN
        if state_parse_error and "missing timestamp" not in state_parse_error.lower():
            reason_codes.extend(["state_error", "no_heartbeat"])
            reasons.append("STATE_ERROR / HEARTBEAT_TIMESTAMP_MISSING")
        else:
            reason_codes.append("no_heartbeat")
            reasons.append("HEARTBEAT_TIMESTAMP_MISSING")
        return outcome, reasons, reason_codes, drift_minutes

    ref = heartbeat_ts
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    drift_minutes = (now - ref).total_seconds() / 60.0
    if drift_minutes >= fail_minutes:
        outcome = OUTCOME_FAIL
        reasons.append(f"runner stale for {drift_minutes:.1f}m (>= {fail_minutes}m)")
        reason_codes.append("stale")
    elif drift_minutes >= warn_minutes:
        outcome = OUTCOME_WARN
        reasons.append(f"runner stale for {drift_minutes:.1f}m (>= {warn_minutes}m)")
        reason_codes.append("stale")
    return outcome, reasons, reason_codes, drift_minutes


def _code_version() -> str:
    return (
        (os.environ.get("CODE_VERSION") or "").strip()
        or (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "").strip()
        or "unknown"
    )


def _fallback_no_db_check(tenant_cfg: dict[str, Any], run_id: str, *, db_fallback_reason: str) -> dict[str, Any]:
    state = read_state() or {}
    heartbeat_ts, state_parse_error = _state_runner_heartbeat(state)
    if state_parse_error and "missing timestamp" not in state_parse_error.lower():
        logger.warning("STATE_ERROR: %s", state_parse_error)

    now = utcnow()
    warn_minutes = int((tenant_cfg.get("watchdog") or {}).get("stale_warn_minutes", 60))
    fail_minutes = int((tenant_cfg.get("watchdog") or {}).get("stale_fail_minutes", 180))
    outcome, reasons, reason_codes, drift_minutes = _evaluate_heartbeat(
        heartbeat_ts=heartbeat_ts,
        now=now,
        warn_minutes=warn_minutes,
        fail_minutes=fail_minutes,
        state_parse_error=state_parse_error,
    )
    fingerprint = _watchdog_fingerprint(tenant_cfg, "state", reason_codes) if outcome in {OUTCOME_WARN, OUTCOME_FAIL} else None
    cache = state.get("watchdog_alert_cache") if isinstance(state.get("watchdog_alert_cache"), dict) else {}
    cache_fp = str(cache.get("fingerprint") or "")
    cache_outcome = str(cache.get("outcome") or "")
    cache_sent_at = _parse_iso(cache.get("sent_at"))

    should_email = outcome in {OUTCOME_WARN, OUTCOME_FAIL}
    suppressed_reason = None
    if should_email and fingerprint:
        cooldown = _watchdog_cooldown_minutes(outcome, tenant_cfg)
        if cache_fp == fingerprint and cache_outcome == outcome and _within_minutes(cache_sent_at, now, cooldown):
            should_email = False
            suppressed_reason = f"cooldown active ({cooldown}m) for {fingerprint}"

    if should_email:
        body = (
            f"Watchdog status: {outcome}\n"
            f"Tenant: {tenant_cfg.get('tenant_name')}\n"
            f"Source: state\n"
            f"Fallback reason: {db_fallback_reason}\n"
            f"Drift minutes: {drift_minutes}\n"
            f"Reasons: {', '.join(reasons) if reasons else 'none'}\n"
        )
        send_email(tenant_cfg, "- WATCHDOG ALERT", body)
        state["watchdog_alert_cache"] = {
            "fingerprint": fingerprint,
            "outcome": outcome,
            "sent_at": now.isoformat(),
        }
        write_state(state)
    elif suppressed_reason:
        logger.info("Watchdog alert suppressed in fallback path: %s", suppressed_reason)

    return {
        "outcome": outcome,
        "reasons": reasons,
        "run_id": run_id,
        "actions": [],
        "source": "state",
        "db_fallback_reason": db_fallback_reason,
    }


def _can_restart_worker(conn, *, tenant_id: str, worker_service_id: str, remediation_cfg: dict[str, Any]) -> tuple[bool, str]:
    limit = int(remediation_cfg.get("max_restarts_per_day", 3))
    cooldown = int(remediation_cfg.get("restart_cooldown_minutes", 30))
    since = utcnow() - timedelta(days=1)
    used = count_executed_actions_since(
        conn,
        tenant_id=tenant_id,
        service_id=worker_service_id,
        action_type=ACTION_RESTART,
        since=since,
    )
    if used >= max(0, limit):
        return False, f"restart daily cap reached ({used}/{limit})"
    last_at = latest_executed_action_at(
        conn,
        tenant_id=tenant_id,
        service_id=worker_service_id,
        action_type=ACTION_RESTART,
    )
    if last_at and last_at > (utcnow() - timedelta(minutes=max(1, cooldown))):
        return False, "restart cooldown active"
    return True, ""


async def check_health(tenant_cfg: dict[str, Any], *, force_auto_recover: bool = False) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    process_name = "watchdog"
    started_at = utcnow()
    started_mono = datetime.now(timezone.utc)
    code_version = _code_version()
    db_url = resolve_db_url(tenant_cfg)
    if not db_url:
        db_reason = "DB read failed: DATABASE_URL missing"
        logger.warning("Watchdog fallback to state: %s", db_reason)
        return _fallback_no_db_check(tenant_cfg, run_id, db_fallback_reason=db_reason)

    try:
        conn = connect_db(db_url)
    except Exception as exc:
        db_reason = f"DB read failed: {exc}"
        logger.warning("Watchdog fallback to state: %s", db_reason)
        return _fallback_no_db_check(tenant_cfg, run_id, db_fallback_reason=db_reason)
    conn.autocommit = False
    tenant_id = None
    lock_acquired = False

    try:
        tenant_id = ensure_tenant_id(conn, str(tenant_cfg.get("tenant_name") or ""))
        if not tenant_id:
            logger.warning("No tenant found in crm_tenants for watchdog")
            return {"outcome": OUTCOME_WARN, "reasons": ["tenant missing"], "run_id": run_id}

        worker_service_id = str((tenant_cfg.get("railway") or {}).get("worker_service_id") or "")
        if not worker_service_id:
            worker_service_id = str((tenant_cfg.get("railway") or {}).get("service_id") or "")

        lock_acquired = acquire_process_lock(conn, tenant_id, process_name)
        if not lock_acquired:
            logger.warning("Watchdog lock already held for tenant=%s", tenant_id)
            return {"outcome": OUTCOME_WARN, "reasons": ["lock already held"], "run_id": run_id}

        source = "db"
        db_fallback_reason: str | None = None
        latest_runner_ts: datetime | None = None
        latest_runner_ok_ts: datetime | None = None
        latest_runner_outcome: str | None = None
        state_parse_error: str | None = None

        try:
            latest_runner_run = latest_run_by_process(conn, tenant_id, "runner")
            latest_runner_ok_ts = latest_ok_run_ts(conn, tenant_id, "runner")
        except Exception as exc:
            conn.rollback()
            latest_runner_run = None
            latest_runner_ok_ts = None
            source = "state"
            db_fallback_reason = f"DB read failed: {exc}"

        if latest_runner_run and latest_runner_run.get("finished_at"):
            latest_runner_ts = _parse_iso(latest_runner_run.get("finished_at"))
            latest_runner_outcome = str(latest_runner_run.get("outcome") or "")
            if latest_runner_ts is None:
                source = "state"
                if not db_fallback_reason:
                    db_fallback_reason = "DB query returned no rows"
        else:
            source = "state"
            if not db_fallback_reason:
                db_fallback_reason = "DB query returned no rows"

        state = read_state() or {}
        if source == "state":
            logger.warning("Watchdog fallback to state: %s", db_fallback_reason or "DB query returned no rows")
            latest_runner_ts, state_parse_error = _state_runner_heartbeat(state)
            if state_parse_error and "missing timestamp" not in state_parse_error.lower():
                logger.warning("STATE_ERROR: %s", state_parse_error)
            if latest_runner_ok_ts is None:
                latest_runner_ok_ts = _parse_iso(state.get("last_ok_ts")) or _parse_iso(state.get("last_success_ts"))
            if not latest_runner_outcome:
                latest_runner_outcome = str(state.get("last_status") or "")

        now = utcnow()
        warn_minutes = int((tenant_cfg.get("watchdog") or {}).get("stale_warn_minutes", 60))
        fail_minutes = int((tenant_cfg.get("watchdog") or {}).get("stale_fail_minutes", 180))
        outcome, reasons, reason_codes, drift_minutes = _evaluate_heartbeat(
            heartbeat_ts=latest_runner_ts,
            now=now,
            warn_minutes=warn_minutes,
            fail_minutes=fail_minutes,
            state_parse_error=state_parse_error,
        )

        current_bytes = int((state.get("cost_counters") or {}).get("log_bytes_today") or 0)
        daily_limit_bytes = int(
            ((tenant_cfg.get("railway") or {}).get("metrics_thresholds") or {}).get("log_bytes_per_day_fail", 20 * 1024 * 1024)
        )
        if current_bytes > daily_limit_bytes and outcome == OUTCOME_OK:
            outcome = OUTCOME_WARN
            reasons.append(f"log usage exceeded ({current_bytes}>{daily_limit_bytes})")
            reason_codes.append("log_bytes_exceeded")

        remediation_cfg = dict(tenant_cfg.get("remediation") or {})
        auto_recover = bool((tenant_cfg.get("watchdog") or {}).get("auto_recover_on_fail", False)) or force_auto_recover
        dry_run = bool(remediation_cfg.get("dry_run", True))
        actions: list[dict[str, Any]] = []

        if outcome == OUTCOME_FAIL and auto_recover and worker_service_id:
            allowed, reason = _can_restart_worker(
                conn,
                tenant_id=tenant_id,
                worker_service_id=worker_service_id,
                remediation_cfg=remediation_cfg,
            )
            if not allowed:
                insert_action(
                    conn,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    process_name=process_name,
                    service_id=worker_service_id,
                    action_type=ACTION_RESTART,
                    status="blocked",
                    reason=reason,
                    dry_run=dry_run,
                )
                actions.append({"action_type": ACTION_RESTART, "status": "blocked", "reason": reason})
            else:
                if dry_run:
                    insert_action(
                        conn,
                        run_id=run_id,
                        tenant_id=tenant_id,
                        process_name=process_name,
                        service_id=worker_service_id,
                        action_type=ACTION_RESTART,
                        status="skipped",
                        reason="[dry-run] watchdog auto-recover",
                        dry_run=True,
                    )
                    actions.append({"action_type": ACTION_RESTART, "status": "skipped", "reason": "dry-run"})
                else:
                    railway_client = RailwayClient(os.environ.get("RAILWAY_API_TOKEN"), tenant_cfg.get("dependency"))
                    try:
                        dep_id = await railway_client.latest_deployment_id(
                            conn,
                            tenant_id=tenant_id,
                            service_id=worker_service_id,
                        )
                        if dep_id:
                            ok = await railway_client.deployment_restart(
                                conn,
                                tenant_id=tenant_id,
                                service_id=worker_service_id,
                                deployment_id=dep_id,
                            )
                            insert_action(
                                conn,
                                run_id=run_id,
                                tenant_id=tenant_id,
                                process_name=process_name,
                                service_id=worker_service_id,
                                action_type=ACTION_RESTART,
                                status="executed" if ok else "failed",
                                reason="watchdog stale fail auto-recover",
                                dry_run=False,
                                provider_action_id=dep_id,
                            )
                            actions.append(
                                {
                                    "action_type": ACTION_RESTART,
                                    "status": "executed" if ok else "failed",
                                    "reason": "watchdog stale fail auto-recover",
                                }
                            )
                        else:
                            insert_action(
                                conn,
                                run_id=run_id,
                                tenant_id=tenant_id,
                                process_name=process_name,
                                service_id=worker_service_id,
                                action_type=ACTION_RESTART,
                                status="failed",
                                reason="watchdog could not find worker deployment",
                                dry_run=False,
                            )
                            actions.append({"action_type": ACTION_RESTART, "status": "failed", "reason": "deployment missing"})
                    except RailwayDependencyError as exc:
                        insert_action(
                            conn,
                            run_id=run_id,
                            tenant_id=tenant_id,
                            process_name=process_name,
                            service_id=worker_service_id,
                            action_type=ACTION_RESTART,
                            status="failed",
                            reason=f"dependency error: {exc.message}",
                            dry_run=False,
                        )
                        actions.append({"action_type": ACTION_RESTART, "status": "failed", "reason": exc.message})
                        reasons.append(f"auto-recover dependency failure: {exc.message}")

        prev_state = read_process_state(conn, tenant_id, process_name, worker_service_id)
        prev_fp = prev_state.get("previous_fingerprint")
        prev_outcome = prev_state.get("previous_outcome")
        prev_count = int(prev_state.get("consecutive_fail_count") or 0)
        prev_first_seen = prev_state.get("first_seen_at")
        prev_alert_sent_at = prev_state.get("last_seen_at")

        fp = None
        if outcome != OUTCOME_OK:
            fp = _watchdog_fingerprint(tenant_cfg, source, reason_codes)

        if outcome == OUTCOME_FAIL:
            if prev_outcome == OUTCOME_FAIL and prev_fp and prev_fp == fp:
                consecutive_fail_count = prev_count + 1
                first_seen_at = prev_first_seen or started_at
            else:
                consecutive_fail_count = 1
                first_seen_at = started_at
        else:
            consecutive_fail_count = 0
            first_seen_at = None

        finished_at = utcnow()
        duration_ms = int((finished_at - started_mono).total_seconds() * 1000)

        should_email = False
        alert_suppressed_reason = None
        alert_sent_at: datetime | None = None

        if outcome in {OUTCOME_WARN, OUTCOME_FAIL}:
            should_email, alert_suppressed_reason = _should_send_deduped_alert(
                outcome=outcome,
                fingerprint=fp,
                previous_fingerprint=prev_fp,
                previous_outcome=prev_outcome,
                previous_alert_sent_at=prev_alert_sent_at,
                now=finished_at,
                tenant_cfg=tenant_cfg,
            )
            if should_email:
                alert_sent_at = finished_at
            else:
                alert_sent_at = prev_alert_sent_at
        elif outcome == OUTCOME_OK and prev_outcome in {OUTCOME_WARN, OUTCOME_FAIL}:
            should_email = bool((tenant_cfg.get("alerts") or {}).get("send_recovery", True))
            if should_email:
                alert_sent_at = finished_at

        persisted_last_seen_at = alert_sent_at if outcome in {OUTCOME_WARN, OUTCOME_FAIL} else None

        alert_cooldown_minutes = _watchdog_cooldown_minutes(outcome, tenant_cfg) if outcome in {OUTCOME_WARN, OUTCOME_FAIL} else None
        summary_json = {
            "run_id": run_id,
            "source": source,
            "db_fallback_reason": db_fallback_reason,
            "drift_minutes": drift_minutes,
            "reasons": reasons,
            "reason_codes": sorted({x for x in reason_codes if x}),
            "actions": actions,
            "checks": {
                "watchdog_staleness": {
                    "status": outcome,
                    "latest_runner_heartbeat_ts": latest_runner_ts.isoformat() if latest_runner_ts else None,
                    "latest_runner_success_ts": latest_runner_ok_ts.isoformat() if latest_runner_ok_ts else None,
                    "latest_runner_outcome": latest_runner_outcome,
                    "stale_warn_minutes": warn_minutes,
                    "stale_fail_minutes": fail_minutes,
                }
            },
            "alert": {
                "fingerprint": fp,
                "sent": should_email,
                "suppressed_reason": alert_suppressed_reason,
                "cooldown_minutes": alert_cooldown_minutes,
                "sent_at": alert_sent_at.isoformat() if alert_sent_at else None,
            },
        }

        insert_run(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=worker_service_id,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            fingerprint=fp,
            previous_fingerprint=prev_fp,
            previous_outcome=prev_outcome,
            consecutive_fail_count=consecutive_fail_count,
            first_seen_at=first_seen_at,
            last_seen_at=persisted_last_seen_at,
            schema_version=SCHEMA_VERSION,
            code_version=code_version,
            summary_json=summary_json,
        )
        upsert_process_state(
            conn,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=worker_service_id,
            previous_fingerprint=fp,
            previous_outcome=outcome,
            consecutive_fail_count=consecutive_fail_count,
            first_seen_at=first_seen_at,
            last_seen_at=persisted_last_seen_at,
        )
        conn.commit()

        if should_email:
            body = (
                f"Watchdog status: {outcome}\n"
                f"Tenant: {tenant_cfg.get('tenant_name')}\n"
                f"Source: {source}\n"
                f"Fallback reason: {db_fallback_reason}\n"
                f"Drift minutes: {drift_minutes}\n"
                f"Reasons: {', '.join(reasons) if reasons else 'none'}\n"
            )
            send_email(tenant_cfg, "- WATCHDOG ALERT", body)
        elif alert_suppressed_reason:
            logger.info("Watchdog alert suppressed: %s", alert_suppressed_reason)

        logger.info("Watchdog finished. Status: %s", outcome)
        return {
            "outcome": outcome,
            "reasons": reasons,
            "run_id": run_id,
            "actions": actions,
            "source": source,
            "drift_minutes": drift_minutes,
            "db_fallback_reason": db_fallback_reason,
        }
    except Exception as exc:
        conn.rollback()
        logger.exception("Watchdog check failed: %s", exc)
        return {"outcome": OUTCOME_FAIL, "reasons": [str(exc)], "run_id": run_id}
    finally:
        if tenant_id and lock_acquired:
            try:
                release_process_lock(conn, tenant_id, process_name)
                conn.commit()
            except Exception:
                conn.rollback()
        conn.close()


async def watchdog_loop(tenant_cfg: dict[str, Any], interval_minutes: int, *, force_auto_recover: bool = False) -> None:
    while True:
        await check_health(tenant_cfg, force_auto_recover=force_auto_recover)
        await asyncio.sleep(interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintenance Watchdog")
    parser.add_argument("--tenant", required=True, help="Path to tenant YAML")
    parser.add_argument("--loop", action="store_true", help="Run in loop")
    parser.add_argument("--once", action="store_true", help="Run once")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Check interval")
    parser.add_argument("--reset-state", action="store_true", help="Safety: Reset state counters")
    parser.add_argument("--auto-recover-worker", action="store_true", help="Force auto recovery mode")
    args = parser.parse_args()

    if args.reset_state:
        write_state(
            {
                "last_run_ts": None,
                "last_success_ts": datetime.now(timezone.utc).isoformat(),
                "last_ok_ts": datetime.now(timezone.utc).isoformat(),
                "last_digest_ts": None,
                "last_status": "RESET",
                "last_run_duration_ms": 0,
                "cost_counters": {
                    "log_pulls_today": 0,
                    "log_bytes_today": 0,
                    "log_last_reset_date": datetime.now(timezone.utc).date().isoformat(),
                },
            }
        )
        print("State reset successfully.")
        return

    tenant_cfg = load_tenant_config(args.tenant)
    if args.once:
        asyncio.run(check_health(tenant_cfg, force_auto_recover=args.auto_recover_worker))
    elif args.loop:
        logger.info("Watchdog started (interval: %sm)", args.interval_minutes)
        asyncio.run(watchdog_loop(tenant_cfg, args.interval_minutes, force_auto_recover=args.auto_recover_worker))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
