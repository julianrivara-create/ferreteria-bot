from __future__ import annotations

import os


def _is_railway_runtime() -> bool:
    return bool((os.getenv("RAILWAY_ENVIRONMENT") or "").strip()) or bool((os.getenv("RAILWAY_PROJECT_ID") or "").strip())


def _abs_path(path: str) -> str:
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return expanded
    return os.path.abspath(expanded)


def state_file_path() -> str:
    explicit_file = (os.getenv("MAINTENANCE_STATE_FILE") or "").strip()
    if explicit_file:
        return _abs_path(explicit_file)

    explicit_dir = (os.getenv("MAINTENANCE_STATE_DIR") or "").strip()
    if explicit_dir:
        return os.path.join(_abs_path(explicit_dir), "state.json")

    if _is_railway_runtime() or os.path.isdir("/app/state"):
        return "/app/state/state.json"

    return os.path.join(os.getcwd(), "state", "state.json")


def reports_dir_path() -> str:
    explicit_dir = (os.getenv("MAINTENANCE_REPORTS_DIR") or "").strip()
    if explicit_dir:
        return _abs_path(explicit_dir)

    if _is_railway_runtime() or os.path.isdir("/app/reports"):
        return "/app/reports"

    return os.path.join(os.getcwd(), "reports")


def logs_dir_path() -> str:
    explicit_dir = (os.getenv("MAINTENANCE_LOG_DIR") or "").strip()
    if explicit_dir:
        return _abs_path(explicit_dir)
    return os.path.join(reports_dir_path(), "logs")


def watchdog_state_candidates() -> list[str]:
    candidates = []
    preferred = state_file_path()
    if preferred:
        candidates.append(preferred)
    candidates.extend(
        [
            os.path.join(os.getcwd(), "state", "state.json"),
            "/app/state/state.json",
        ]
    )

    unique: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normpath(path)
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(norm)
    return unique
