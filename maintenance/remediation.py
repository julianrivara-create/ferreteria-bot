from __future__ import annotations

from datetime import timedelta
from typing import Any

from .logging_config import logger
from .persistence import (
    count_executed_actions_since,
    insert_action,
    latest_executed_action_at,
    utcnow,
)
from .types import ACTION_REDEPLOY, ACTION_RESTART, OUTCOME_DEPENDENCY_ERROR, OUTCOME_FAIL


_TIMEOUT_PATTERNS = ("timeout", "timed out")
_REFUSED_PATTERNS = ("connection refused",)
_UPSTREAM_CODES = {429, 502, 504}


def _find_check(checks: list[dict[str, Any]], check_type: str) -> list[dict[str, Any]]:
    return [c for c in checks if c.get("type") == check_type]


def has_internal_evidence(check_results: list[dict[str, Any]], logs_summary: dict[str, Any] | None = None) -> bool:
    for item in _find_check(check_results, "http_health"):
        code = item.get("status_code")
        if isinstance(code, int) and code >= 500:
            return True

    for item in _find_check(check_results, "http_base") + _find_check(check_results, "http_health"):
        error = str(item.get("error", "")).lower()
        if any(x in error for x in _TIMEOUT_PATTERNS) or any(x in error for x in _REFUSED_PATTERNS):
            if "nxdomain" not in error and "name or service not known" not in error:
                return True

    signatures = (logs_summary or {}).get("hard_failure_signatures") or []
    return bool(signatures)


def has_external_first_fail_signature(check_results: list[dict[str, Any]], logs_summary: dict[str, Any] | None = None) -> bool:
    logs_has_internal = bool((logs_summary or {}).get("hard_failure_signatures") or [])
    for item in _find_check(check_results, "http_health") + _find_check(check_results, "http_base"):
        code = item.get("status_code")
        if isinstance(code, int) and code in _UPSTREAM_CODES and not logs_has_internal:
            return True
    return False


def _within_cooldown(last_action_at, cooldown_minutes: int) -> bool:
    if not last_action_at:
        return False
    return last_action_at > (utcnow() - timedelta(minutes=max(1, int(cooldown_minutes))))


def _can_execute_action(
    conn,
    *,
    tenant_id: str,
    service_id: str,
    action_type: str,
    max_per_day: int,
    cooldown_minutes: int,
) -> tuple[bool, str]:
    since = utcnow() - timedelta(days=1)
    used = count_executed_actions_since(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        action_type=action_type,
        since=since,
    )
    if used >= max(0, int(max_per_day)):
        return False, f"daily cap reached for {action_type}: {used}/{max_per_day}"

    last_at = latest_executed_action_at(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        action_type=action_type,
    )
    if _within_cooldown(last_at, cooldown_minutes):
        return False, f"cooldown active for {action_type}"
    return True, ""


async def _execute_restart(
    conn,
    railway_client,
    *,
    tenant_id: str,
    service_id: str,
    run_id: str,
    process_name: str,
    dry_run: bool,
    reason: str,
) -> dict[str, Any]:
    if dry_run:
        insert_action(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=service_id,
            action_type=ACTION_RESTART,
            status="skipped",
            reason=f"[dry-run] {reason}",
            dry_run=True,
        )
        return {"action_type": ACTION_RESTART, "status": "skipped", "reason": reason}

    deployment_id = await railway_client.latest_deployment_id(conn, tenant_id=tenant_id, service_id=service_id)
    if not deployment_id:
        insert_action(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=service_id,
            action_type=ACTION_RESTART,
            status="failed",
            reason="no deployment id found",
            dry_run=False,
        )
        return {"action_type": ACTION_RESTART, "status": "failed", "reason": "no deployment id found"}

    ok = await railway_client.deployment_restart(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        deployment_id=deployment_id,
    )
    insert_action(
        conn,
        run_id=run_id,
        tenant_id=tenant_id,
        process_name=process_name,
        service_id=service_id,
        action_type=ACTION_RESTART,
        status="executed" if ok else "failed",
        reason=reason,
        dry_run=False,
        provider_action_id=deployment_id,
    )
    return {"action_type": ACTION_RESTART, "status": "executed" if ok else "failed", "reason": reason}


async def _execute_redeploy(
    conn,
    railway_client,
    *,
    tenant_id: str,
    service_id: str,
    run_id: str,
    process_name: str,
    dry_run: bool,
    reason: str,
) -> dict[str, Any]:
    if dry_run:
        insert_action(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=service_id,
            action_type=ACTION_REDEPLOY,
            status="skipped",
            reason=f"[dry-run] {reason}",
            dry_run=True,
        )
        return {"action_type": ACTION_REDEPLOY, "status": "skipped", "reason": reason}

    deployment_id = await railway_client.latest_deployment_id(conn, tenant_id=tenant_id, service_id=service_id)
    if not deployment_id:
        insert_action(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name=process_name,
            service_id=service_id,
            action_type=ACTION_REDEPLOY,
            status="failed",
            reason="no deployment id found",
            dry_run=False,
        )
        return {"action_type": ACTION_REDEPLOY, "status": "failed", "reason": "no deployment id found"}

    new_id = await railway_client.deployment_redeploy(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        deployment_id=deployment_id,
    )
    ok = bool(new_id)
    insert_action(
        conn,
        run_id=run_id,
        tenant_id=tenant_id,
        process_name=process_name,
        service_id=service_id,
        action_type=ACTION_REDEPLOY,
        status="executed" if ok else "failed",
        reason=reason,
        dry_run=False,
        provider_action_id=new_id or deployment_id,
    )
    return {"action_type": ACTION_REDEPLOY, "status": "executed" if ok else "failed", "reason": reason}


async def maybe_remediate_runner(
    conn,
    railway_client,
    *,
    tenant_id: str,
    service_id: str,
    run_id: str,
    outcome: str,
    consecutive_fail_count: int,
    check_results: list[dict[str, Any]],
    logs_summary: dict[str, Any] | None,
    remediation_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    enabled = bool(remediation_cfg.get("enabled", False))
    dry_run = bool(remediation_cfg.get("dry_run", True))

    if outcome != OUTCOME_FAIL:
        return actions
    if any(c.get("status") == OUTCOME_DEPENDENCY_ERROR for c in check_results):
        logger.info("Remediation skipped: dependency error present")
        return actions
    if has_external_first_fail_signature(check_results, logs_summary):
        logger.info("Remediation skipped: external first-fail signature detected")
        return actions
    if not enabled:
        logger.info("Remediation disabled by config")
        return actions

    restart_cap = int(remediation_cfg.get("max_restarts_per_day", 3))
    redeploy_cap = int(remediation_cfg.get("max_redeploys_per_day", 1))
    restart_cd = int(remediation_cfg.get("restart_cooldown_minutes", 30))
    redeploy_cd = int(remediation_cfg.get("redeploy_cooldown_minutes", 180))

    if consecutive_fail_count <= 1:
        if not has_internal_evidence(check_results, logs_summary):
            logger.info("Restart blocked: no internal evidence on first FAIL")
            return actions
        ok, reason = _can_execute_action(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            action_type=ACTION_RESTART,
            max_per_day=restart_cap,
            cooldown_minutes=restart_cd,
        )
        if not ok:
            insert_action(
                conn,
                run_id=run_id,
                tenant_id=tenant_id,
                process_name="runner",
                service_id=service_id,
                action_type=ACTION_RESTART,
                status="blocked",
                reason=reason,
                dry_run=dry_run,
            )
            return actions
        actions.append(
            await _execute_restart(
                conn,
                railway_client,
                tenant_id=tenant_id,
                service_id=service_id,
                run_id=run_id,
                process_name="runner",
                dry_run=dry_run,
                reason="first FAIL with internal evidence",
            )
        )
        return actions

    ok, reason = _can_execute_action(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        action_type=ACTION_REDEPLOY,
        max_per_day=redeploy_cap,
        cooldown_minutes=redeploy_cd,
    )
    if not ok:
        insert_action(
            conn,
            run_id=run_id,
            tenant_id=tenant_id,
            process_name="runner",
            service_id=service_id,
            action_type=ACTION_REDEPLOY,
            status="blocked",
            reason=reason,
            dry_run=dry_run,
        )
        return actions
    actions.append(
        await _execute_redeploy(
            conn,
            railway_client,
            tenant_id=tenant_id,
            service_id=service_id,
            run_id=run_id,
            process_name="runner",
            dry_run=dry_run,
            reason="consecutive FAIL >= 2 with stable fingerprint",
        )
    )
    return actions

