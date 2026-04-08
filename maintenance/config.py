from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml


SCHEMA_VERSION = "2.2"


DEFAULTS: dict[str, Any] = {
    "checks_enabled": {
        "http": True,
        "db": True,
        "logs": True,
        "metrics": True,
    },
    "railway": {
        "log_lookback_hours": 4,
        "log_max_lines": 1000,
        "log_max_bytes": 1024 * 1024,
        "metrics_enabled": True,
        "metrics_window_minutes": 10,
        "metrics_step_seconds": 60,
        "log_dedupe_bucket_seconds": 30,
        "metrics_thresholds": {
            "cpu_pct_warn": 70,
            "cpu_pct_fail": 90,
            "mem_pct_warn": 80,
            "mem_pct_fail": 95,
            "log_pulls_per_day_warn": 50,
            "log_pulls_per_day_fail": 100,
            "log_bytes_per_day_warn": 10 * 1024 * 1024,
            "log_bytes_per_day_fail": 20 * 1024 * 1024,
        },
    },
    "remediation": {
        "enabled": False,
        "dry_run": True,
        "max_restarts_per_day": 3,
        "max_redeploys_per_day": 1,
        "restart_cooldown_minutes": 30,
        "redeploy_cooldown_minutes": 180,
    },
    "watchdog": {
        "stale_warn_minutes": 60,
        "stale_fail_minutes": 180,
        "fail_cooldown_minutes": 45,
        "warn_cooldown_minutes": 240,
        "auto_recover_on_fail": False,
    },
    "dependency": {
        "dependency_circuit_fail_threshold": 3,
        "dependency_circuit_open_minutes": 15,
    },
    "alerts": {
        "dependency_cooldown_minutes": 120,
    },
    "thresholds": {
        "http_timeout_ms": 5000,
        "http_warn_latency_ms": 2000,
        "db_warn_latency_ms": 1500,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "tenant.schema.json"


def _load_schema() -> dict[str, Any]:
    with _schema_path().open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_tenant_config(cfg: dict[str, Any]) -> None:
    jsonschema.validate(instance=cfg, schema=_load_schema())

    checks = cfg.get("checks_enabled") or {}
    railway = cfg.get("railway") or {}
    watchdog = cfg.get("watchdog") or {}

    missing: list[str] = []
    if checks.get("logs") and not railway.get("service_id"):
        missing.append("railway.service_id (required when checks_enabled.logs=true)")
    if checks.get("metrics") and not railway.get("service_id"):
        missing.append("railway.service_id (required when checks_enabled.metrics=true)")
    if watchdog.get("auto_recover_on_fail") and not railway.get("worker_service_id"):
        missing.append("railway.worker_service_id (required when watchdog.auto_recover_on_fail=true)")
    if missing:
        raise ValueError("Invalid tenant config: " + "; ".join(missing))


def apply_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    return _deep_merge(DEFAULTS, cfg or {})


def load_tenant_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = apply_defaults(raw)
    validate_tenant_config(cfg)
    return cfg
