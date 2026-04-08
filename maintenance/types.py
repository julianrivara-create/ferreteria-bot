from __future__ import annotations

OUTCOME_OK = "OK"
OUTCOME_WARN = "WARN"
OUTCOME_FAIL = "FAIL"
OUTCOME_DEPENDENCY_ERROR = "DEPENDENCY_ERROR"

OUTCOME_ORDER = {
    OUTCOME_FAIL: 0,
    OUTCOME_DEPENDENCY_ERROR: 1,
    OUTCOME_WARN: 2,
    OUTCOME_OK: 3,
}

DEPENDENCY_DOMAINS = {
    "railway_logs",
    "railway_metrics",
    "railway_deployments",
}

ACTION_RESTART = "restart"
ACTION_REDEPLOY = "redeploy"

