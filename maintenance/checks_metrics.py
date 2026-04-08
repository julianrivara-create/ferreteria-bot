from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .types import OUTCOME_DEPENDENCY_ERROR, OUTCOME_FAIL, OUTCOME_OK, OUTCOME_WARN


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return (num / den) * 100.0


async def run_metrics_check(
    railway_client,
    conn,
    *,
    tenant_id: str,
    service_id: str,
    metrics_cfg: dict[str, Any],
    dependency_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    window_minutes = int(metrics_cfg.get("metrics_window_minutes", 10))
    step_seconds = int(metrics_cfg.get("metrics_step_seconds", 60))
    thresholds = metrics_cfg.get("metrics_thresholds") or {}

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(minutes=max(1, window_minutes))

    try:
        rows = await railway_client.metrics(
            conn,
            tenant_id=tenant_id,
            service_id=service_id,
            start_date=start_date,
            end_date=end_date,
            sample_rate_seconds=max(15, step_seconds),
            measurements=["CPU_USAGE_2", "CPU_LIMIT", "MEMORY_USAGE_GB", "MEMORY_LIMIT_GB"],
        )
    except Exception as exc:
        payload = dependency_payload or {}
        payload = {**payload, "message": str(exc)}
        return {
            "type": "metrics",
            "status": OUTCOME_DEPENDENCY_ERROR,
            "ok": False,
            "dependency": payload,
            "error": str(exc),
        }

    by_name: dict[str, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        meas = str(row.get("measurement") or "")
        vals = row.get("values") or []
        parsed = []
        if isinstance(vals, list):
            for item in vals:
                if isinstance(item, dict) and item.get("value") is not None:
                    parsed.append(float(item.get("value")))
        by_name[meas] = parsed

    cpu_usage = by_name.get("CPU_USAGE_2") or by_name.get("CPU_USAGE") or []
    cpu_limit = by_name.get("CPU_LIMIT") or []
    mem_usage = by_name.get("MEMORY_USAGE_GB") or []
    mem_limit = by_name.get("MEMORY_LIMIT_GB") or []

    points = min(len(cpu_usage), len(cpu_limit), len(mem_usage), len(mem_limit))
    if points < 3:
        return {
            "type": "metrics",
            "status": OUTCOME_WARN,
            "ok": True,
            "warning_code": "INSUFFICIENT_METRICS_DATA",
            "points": points,
        }

    cpu_current = _pct(cpu_usage[-1], cpu_limit[-1])
    mem_current = _pct(mem_usage[-1], mem_limit[-1])
    cpu_avg = _pct(_avg(cpu_usage), _avg(cpu_limit))
    mem_avg = _pct(_avg(mem_usage), _avg(mem_limit))

    cpu_fail = float(thresholds.get("cpu_pct_fail", 90))
    cpu_warn = float(thresholds.get("cpu_pct_warn", 70))
    mem_fail = float(thresholds.get("mem_pct_fail", 95))
    mem_warn = float(thresholds.get("mem_pct_warn", 80))

    status = OUTCOME_OK
    reasons = []
    if cpu_current >= cpu_fail or mem_current >= mem_fail:
        status = OUTCOME_FAIL
        reasons.append("Resource usage above FAIL threshold")
    elif cpu_current >= cpu_warn or mem_current >= mem_warn:
        status = OUTCOME_WARN
        reasons.append("Resource usage above WARN threshold")

    return {
        "type": "metrics",
        "status": status,
        "ok": status in {OUTCOME_OK, OUTCOME_WARN},
        "cpu_current_pct": round(cpu_current, 2),
        "cpu_avg_pct": round(cpu_avg, 2),
        "mem_current_pct": round(mem_current, 2),
        "mem_avg_pct": round(mem_avg, 2),
        "points": points,
        "reasons": reasons,
    }

