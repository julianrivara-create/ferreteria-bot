from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import timedelta
from typing import Any

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .checks_db import check_db
from .checks_http import check_http
from .checks_logs import fetch_railway_logs, scan_logs, summarize_logs_check
from .checks_metrics import run_metrics_check
from .config import SCHEMA_VERSION, load_tenant_config
from .db import connect_db, resolve_db_url
from .logging_config import logger
from .mailer import send_email
from .persistence import (
    acquire_process_lock,
    ensure_tenant_id,
    insert_run,
    json_fingerprint,
    latest_outcome_at,
    persist_worker_heartbeat_audit,
    read_process_state,
    release_process_lock,
    upsert_process_state,
    utcnow,
)
from .railway_client import RailwayClient, RailwayDependencyError
from .remediation import maybe_remediate_runner
from .report import save_reports
from .state import read_state, write_state
from .types import OUTCOME_DEPENDENCY_ERROR, OUTCOME_FAIL, OUTCOME_OK, OUTCOME_WARN


def _code_version() -> str:
    return (
        (os.environ.get("CODE_VERSION") or "").strip()
        or (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "").strip()
        or "unknown"
    )


def _normalize_status(value: str | None) -> str:
    raw = str(value or OUTCOME_OK).upper()
    if raw not in {OUTCOME_OK, OUTCOME_WARN, OUTCOME_FAIL, OUTCOME_DEPENDENCY_ERROR}:
        return OUTCOME_WARN
    return raw


def compute_outcome(check_results: list[dict[str, Any]]) -> str:
    statuses = {_normalize_status(c.get("status")) for c in check_results}
    if OUTCOME_FAIL in statuses:
        return OUTCOME_FAIL
    if OUTCOME_DEPENDENCY_ERROR in statuses:
        return OUTCOME_DEPENDENCY_ERROR
    if OUTCOME_WARN in statuses:
        return OUTCOME_WARN
    return OUTCOME_OK


def _http_statuses(http_results: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    warn_latency = int((cfg.get("thresholds") or {}).get("http_warn_latency_ms", 2000))
    for item in http_results:
        row = dict(item)
        status = OUTCOME_OK
        if not row.get("ok"):
            status = OUTCOME_FAIL
        elif int(row.get("latency_ms") or 0) > warn_latency:
            status = OUTCOME_WARN
        row["status"] = status
        out.append(row)
    return out


def _db_status(db_result: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    row = dict(db_result)
    warn_latency = int((cfg.get("thresholds") or {}).get("db_warn_latency_ms", 1500))
    status = OUTCOME_OK
    if not row.get("ok"):
        status = OUTCOME_FAIL
    elif int(row.get("latency_ms") or 0) > warn_latency:
        status = OUTCOME_WARN
    row["status"] = status
    return row


async def _safe_check(
    check_name: str,
    coro,
    *,
    timeout_seconds: float,
    timeout_status: str = OUTCOME_DEPENDENCY_ERROR,
    exception_status: str = OUTCOME_WARN,
) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return {
            "check_results": [
                {
                    "type": check_name,
                    "status": timeout_status,
                    "ok": False,
                    "error": f"timeout after {timeout_seconds:.1f}s",
                }
            ]
        }
    except Exception as exc:
        return {
            "check_results": [
                {
                    "type": check_name,
                    "status": exception_status,
                    "ok": False,
                    "error": str(exc),
                }
            ]
        }


async def _run_http(cfg: dict[str, Any]) -> dict[str, Any]:
    raw = await check_http(
        cfg["base_url"],
        cfg.get("health_path"),
        cfg.get("thresholds", {}).get("http_timeout_ms", 5000),
    )
    return {"check_results": _http_statuses(raw, cfg)}


async def _run_db(cfg: dict[str, Any]) -> dict[str, Any]:
    result = await asyncio.to_thread(check_db, cfg.get("db_url_env_key", "DATABASE_URL"))
    return {"check_results": [_db_status(result, cfg)]}


async def _run_logs(
    cfg: dict[str, Any],
    *,
    conn,
    tenant_id: str,
    railway_client: RailwayClient,
) -> dict[str, Any]:
    railway_cfg = cfg.get("railway") or {}
    try:
        logs = await fetch_railway_logs(
            railway_cfg.get("service_id"),
            os.environ.get("RAILWAY_API_TOKEN"),
            int(railway_cfg.get("log_lookback_hours", 4)),
            int(railway_cfg.get("log_max_lines", 1000)),
            bucket_seconds=int(railway_cfg.get("log_dedupe_bucket_seconds", 30)),
            railway_client=railway_client,
            conn=conn,
            tenant_id=tenant_id,
        )
    except RailwayDependencyError as exc:
        return {
            "check_results": [
                {
                    "type": "logs",
                    "status": OUTCOME_DEPENDENCY_ERROR,
                    "ok": False,
                    "dependency": exc.to_payload(),
                    "error": exc.message,
                }
            ],
            "log_findings": [],
            "logs_summary": {"hard_failure_signatures": []},
        }

    findings = scan_logs(logs, cfg.get("custom_checks", {}).get("extra_log_patterns", []))
    summary = summarize_logs_check(logs, findings)
    return {
        "check_results": [summary],
        "log_findings": findings,
        "logs_summary": summary,
        "logs": logs,
    }


async def _run_metrics(
    cfg: dict[str, Any],
    *,
    conn,
    tenant_id: str,
    railway_client: RailwayClient,
) -> dict[str, Any]:
    railway_cfg = cfg.get("railway") or {}
    try:
        result = await run_metrics_check(
            railway_client,
            conn,
            tenant_id=tenant_id,
            service_id=railway_cfg.get("service_id"),
            metrics_cfg=railway_cfg,
        )
    except RailwayDependencyError as exc:
        result = {
            "type": "metrics",
            "status": OUTCOME_DEPENDENCY_ERROR,
            "ok": False,
            "dependency": exc.to_payload(),
            "error": exc.message,
        }
    return {"check_results": [result]}


def _build_reasons(check_results: list[dict[str, Any]], log_findings: list[dict[str, Any]]) -> list[str]:
    reasons = []
    for row in check_results:
        status = _normalize_status(row.get("status"))
        if status == OUTCOME_OK:
            continue
        name = row.get("type", "unknown")
        if row.get("error"):
            reasons.append(f"{name}: {row['error']}")
        else:
            reasons.append(f"{name}: {status}")
    for finding in log_findings:
        reasons.append(
            f"log-anomaly {finding.get('rule_name')}: {finding.get('count')}>{finding.get('threshold')} ({finding.get('severity')})"
        )
    return reasons[:20]


def _should_send_dependency_email(last_dependency_outcome_at, cfg: dict[str, Any]) -> bool:
    cooldown = int((cfg.get("alerts") or {}).get("dependency_cooldown_minutes", 120))
    last = last_dependency_outcome_at
    if not last:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=utcnow().tzinfo)
    return last < (utcnow() - timedelta(minutes=max(1, cooldown)))


async def run_maint(tenant_cfg: dict[str, Any], *, force_dry_run_remediation: bool = False) -> None:
    started_at = utcnow()
    started_monotonic = time.time()
    run_id = str(uuid.uuid4())
    railway_cfg = tenant_cfg.get("railway") or {}
    service_id = railway_cfg.get("service_id")
    process_name = "runner"
    code_version = _code_version()
    db_url = resolve_db_url(tenant_cfg)
    if not db_url:
        logger.error("DATABASE_URL missing, maintenance runner cannot continue")
        return

    conn = connect_db(db_url)
    conn.autocommit = False
    tenant_id = None
    lock_acquired = False

    check_results: list[dict[str, Any]] = []
    log_findings: list[dict[str, Any]] = []
    logs_summary: dict[str, Any] = {"hard_failure_signatures": []}
    actions: list[dict[str, Any]] = []

    try:
        tenant_id = ensure_tenant_id(conn, str(tenant_cfg.get("tenant_name") or ""))
        if not tenant_id:
            logger.warning("No tenant found in crm_tenants; skipping run")
            return

        lock_acquired = acquire_process_lock(conn, tenant_id, process_name)
        if not lock_acquired:
            logger.warning("Maintenance runner lock already held for tenant=%s", tenant_id)
            return

        logger.info("Starting maintenance run for %s", tenant_cfg.get("tenant_name"))
        previous_dependency_outcome_at = latest_outcome_at(
            conn, tenant_id, process_name, service_id, OUTCOME_DEPENDENCY_ERROR
        )
        railway_client = RailwayClient(os.environ.get("RAILWAY_API_TOKEN"), tenant_cfg.get("dependency"))

        tasks = []
        enabled = tenant_cfg.get("checks_enabled") or {}
        if enabled.get("http"):
            tasks.append(
                _safe_check(
                    "http",
                    _run_http(tenant_cfg),
                    timeout_seconds=max(1.0, int(tenant_cfg.get("thresholds", {}).get("http_timeout_ms", 5000)) / 1000.0 + 2),
                    timeout_status=OUTCOME_FAIL,
                    exception_status=OUTCOME_WARN,
                )
            )
        if enabled.get("db"):
            tasks.append(
                _safe_check(
                    "db",
                    _run_db(tenant_cfg),
                    timeout_seconds=12.0,
                    timeout_status=OUTCOME_FAIL,
                    exception_status=OUTCOME_WARN,
                )
            )
        if enabled.get("logs"):
            tasks.append(
                _safe_check(
                    "logs",
                    _run_logs(tenant_cfg, conn=conn, tenant_id=tenant_id, railway_client=railway_client),
                    timeout_seconds=30.0,
                    timeout_status=OUTCOME_DEPENDENCY_ERROR,
                    exception_status=OUTCOME_DEPENDENCY_ERROR,
                )
            )
        if enabled.get("metrics"):
            tasks.append(
                _safe_check(
                    "metrics",
                    _run_metrics(tenant_cfg, conn=conn, tenant_id=tenant_id, railway_client=railway_client),
                    timeout_seconds=25.0,
                    timeout_status=OUTCOME_DEPENDENCY_ERROR,
                    exception_status=OUTCOME_DEPENDENCY_ERROR,
                )
            )

        task_results = await asyncio.gather(*tasks, return_exceptions=False)
        for payload in task_results:
            check_results.extend(payload.get("check_results", []))
            log_findings.extend(payload.get("log_findings", []))
            if payload.get("logs_summary"):
                logs_summary = payload["logs_summary"]

        outcome = compute_outcome(check_results)
        reasons = _build_reasons(check_results, log_findings)

        current_fp = None
        if outcome != OUTCOME_OK:
            current_fp = json_fingerprint(
                {
                    "outcome": outcome,
                    "checks": [
                        {
                            "type": c.get("type"),
                            "status": c.get("status"),
                            "status_code": c.get("status_code"),
                            "error": c.get("error"),
                        }
                        for c in sorted(check_results, key=lambda x: str(x.get("type")))
                    ],
                    "log_findings": [
                        {
                            "rule_name": f.get("rule_name"),
                            "severity": f.get("severity"),
                        }
                        for f in sorted(log_findings, key=lambda x: str(x.get("rule_name")))
                    ],
                }
            )

        previous_state = read_process_state(conn, tenant_id, process_name, service_id)
        prev_fp = previous_state.get("previous_fingerprint")
        prev_outcome = previous_state.get("previous_outcome")
        prev_count = int(previous_state.get("consecutive_fail_count") or 0)
        prev_first_seen = previous_state.get("first_seen_at")
        # Heartbeat signal: runner executed (regardless of outcome).
        last_seen_at = started_at

        if outcome == OUTCOME_FAIL:
            if prev_outcome == OUTCOME_FAIL and prev_fp and prev_fp == current_fp:
                consecutive_fail_count = prev_count + 1
                first_seen_at = prev_first_seen or started_at
            else:
                consecutive_fail_count = 1
                first_seen_at = started_at
        else:
            consecutive_fail_count = 0
            first_seen_at = None

        remediation_cfg = dict(tenant_cfg.get("remediation") or {})
        if force_dry_run_remediation:
            remediation_cfg["dry_run"] = True
            remediation_cfg["enabled"] = True

        actions = await maybe_remediate_runner(
            conn,
            railway_client,
            tenant_id=tenant_id,
            service_id=service_id,
            run_id=run_id,
            outcome=outcome,
            consecutive_fail_count=consecutive_fail_count,
            check_results=check_results,
            logs_summary=logs_summary,
            remediation_cfg=remediation_cfg,
        )

        finished_at = utcnow()
        duration_ms = int((time.time() - started_monotonic) * 1000)
        telemetry = {
            "run_id": run_id,
            "schema_version": SCHEMA_VERSION,
            "code_version": code_version,
            "last_run_duration_ms": duration_ms,
            "consecutive_fail_count": consecutive_fail_count,
            "actions": actions,
        }

        summary_json = {
            "run_id": run_id,
            "tenant": tenant_cfg.get("tenant_name"),
            "checks": {str(c.get("type")): c for c in check_results},
            "log_findings": log_findings,
            "reasons": reasons,
            "actions": actions,
            "telemetry": telemetry,
            "dependency": next((c.get("dependency") for c in check_results if c.get("dependency")), None),
        }

        insert_run(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=service_id,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            fingerprint=current_fp,
            previous_fingerprint=prev_fp,
            previous_outcome=prev_outcome,
            consecutive_fail_count=consecutive_fail_count,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            schema_version=SCHEMA_VERSION,
            code_version=code_version,
            summary_json=summary_json,
        )
        upsert_process_state(
            conn,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=service_id,
            previous_fingerprint=current_fp,
            previous_outcome=outcome,
            consecutive_fail_count=consecutive_fail_count,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )
        persist_worker_heartbeat_audit(conn, tenant_id, outcome, duration_ms, reasons)
        conn.commit()

        # File report + legacy state file still updated for compatibility.
        md_content, json_data = save_reports(
            tenant_cfg["tenant_name"],
            outcome,
            check_results,
            log_findings,
            reasons,
            telemetry,
        )
        legacy_state = read_state()
        legacy_state["last_run_ts"] = finished_at.isoformat()
        legacy_state["last_status"] = outcome
        legacy_state["last_run_duration_ms"] = duration_ms
        if outcome == OUTCOME_OK:
            legacy_state["last_ok_ts"] = legacy_state["last_run_ts"]
            legacy_state["last_success_ts"] = legacy_state["last_run_ts"]
        elif outcome == OUTCOME_WARN:
            legacy_state["last_success_ts"] = legacy_state["last_run_ts"]
        write_state(legacy_state)

        should_email = False
        if outcome == OUTCOME_FAIL:
            should_email = True
        elif outcome == OUTCOME_DEPENDENCY_ERROR:
            should_email = _should_send_dependency_email(previous_dependency_outcome_at, tenant_cfg)
        elif outcome == OUTCOME_OK and prev_outcome in {OUTCOME_FAIL, OUTCOME_WARN, OUTCOME_DEPENDENCY_ERROR}:
            should_email = bool((tenant_cfg.get("alerts") or {}).get("send_recovery", True))

        if should_email:
            send_email(
                tenant_cfg,
                f"- Status: {outcome}",
                md_content,
                json.dumps(json_data).encode("utf-8"),
            )

        logger.info("Maintenance run finished. Status: %s (%sms)", outcome, duration_ms)
    except Exception as exc:
        conn.rollback()
        logger.exception("Maintenance runner failed unexpectedly: %s", exc)
    finally:
        if tenant_id and lock_acquired:
            try:
                release_process_lock(conn, tenant_id, process_name)
                conn.commit()
            except Exception:
                conn.rollback()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintenance Bot Runner")
    parser.add_argument("--tenant", required=True, help="Path to tenant YAML")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--loop", action="store_true", help="Run in loop with APScheduler")
    parser.add_argument("--interval-minutes", type=int, default=240, help="Interval for loop")
    parser.add_argument("--dry-run-remediation", action="store_true", help="Enable remediation in dry-run mode")
    args = parser.parse_args()

    if not os.path.exists(args.tenant):
        print(f"Error: Tenant file {args.tenant} not found")
        return

    tenant_cfg = load_tenant_config(args.tenant)

    if args.once:
        asyncio.run(run_maint(tenant_cfg, force_dry_run_remediation=args.dry_run_remediation))
    elif args.loop:
        scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 3600},
            timezone="UTC",
        )
        scheduler.add_job(
            run_maint,
            "interval",
            minutes=args.interval_minutes,
            args=[tenant_cfg],
            kwargs={"force_dry_run_remediation": args.dry_run_remediation},
        )
        scheduler.start()
        logger.info("Scheduler started (interval: %sm). Press Ctrl+C to exit.", args.interval_minutes)
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
