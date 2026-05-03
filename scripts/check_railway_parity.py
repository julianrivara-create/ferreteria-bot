#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.runtime_integrity import evaluate_runtime_integrity


BANNED_RUNTIME_DEPS = {
    "pytest",
    "pytest-cov",
    "pytest-mock",
    "pytest-benchmark",
    "coverage",
    "flake8",
    "bandit",
    "black",
    "openai-whisper",
    "torch",
    "pydub",
    "soundfile",
}


def _line(status: str, label: str, detail: str = "") -> str:
    suffix = f" - {detail}" if detail else ""
    return f"[{status}] {label}{suffix}"


def _print_category(name: str, status: str) -> None:
    print(f"\n{name.upper()} :: {status}")


def _normalize_base_url(value: str) -> str:
    base = value.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base


def _read_requirements(path: Path) -> set[str]:
    deps: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
            continue
        name = re.split(r"[<>=!~\[]", stripped, maxsplit=1)[0].strip().lower()
        if name:
            deps.add(name)
    return deps


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


def _load_railway_vars(service: str) -> dict[str, str]:
    if shutil.which("railway") is None:
        raise RuntimeError("railway CLI not found")
    result = _run_command(["railway", "variables", "--service", service, "--json"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "railway variables failed")
    payload = json.loads(result.stdout or "{}")
    if isinstance(payload, dict):
        return {str(key): "" if value is None else str(value) for key, value in payload.items()}
    raise RuntimeError("unexpected railway variables payload")


def _load_latest_deployment(service: str) -> dict[str, Any]:
    if shutil.which("railway") is None:
        raise RuntimeError("railway CLI not found")
    result = _run_command(["railway", "deployment", "list", "-s", service, "--json"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "railway deployment list failed")
    payload = json.loads(result.stdout or "[]")
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("no deployments returned")
    latest = payload[0]
    if not isinstance(latest, dict):
        raise RuntimeError("unexpected deployment payload")
    return latest


def _build_checks(service: str) -> tuple[str, list[str]]:
    checks: list[tuple[str, str, str]] = []
    runtime_deps = _read_requirements(ROOT / "requirements.txt")
    dev_deps = _read_requirements(ROOT / "requirements-dev.txt")

    banned_present = sorted(BANNED_RUNTIME_DEPS & runtime_deps)
    checks.append(
        (
            "FAIL" if banned_present else "OK",
            "Runtime requirements are slim",
            ", ".join(banned_present) if banned_present else "no dev/heavy deps in requirements.txt",
        )
    )

    missing_dev = sorted({"pytest", "black", "flake8", "bandit"} - dev_deps)
    checks.append(
        (
            "WARN" if missing_dev else "OK",
            "Development requirements kept separately",
            ", ".join(missing_dev) if missing_dev else "tooling present in requirements-dev.txt",
        )
    )

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    pip_installs = dockerfile.count("pip install")
    checks.append(
        (
            "FAIL" if pip_installs != 1 else "OK",
            "Dockerfile installs dependencies once",
            f"pip install occurrences={pip_installs}",
        )
    )
    healthcheck_ok = "HEALTHCHECK" in dockerfile and "/health" in dockerfile
    checks.append(
        (
            "FAIL" if not healthcheck_ok else "OK",
            "Dockerfile healthcheck targets /health",
            "configured" if healthcheck_ok else "missing or not aligned",
        )
    )
    cmd_ok = 'gunicorn --bind 0.0.0.0:${PORT:-5000} wsgi:app' in dockerfile
    checks.append(
        (
            "FAIL" if not cmd_ok else "OK",
            "Docker CMD matches Railway start command",
            "aligned" if cmd_ok else "mismatch",
        )
    )

    try:
        latest = _load_latest_deployment(service)
        latest_status = str(latest.get("status", "unknown"))
        meta = latest.get("meta", {}) if isinstance(latest.get("meta"), dict) else {}
        commit_hash = str(meta.get("commitHash", "") or "")
        commit_message = str(meta.get("commitMessage", "") or meta.get("cliMessage", "") or "")
        repo = str(meta.get("repo", "") or "")

        local_head_result = _run_command(["git", "rev-parse", "HEAD"])
        local_head = local_head_result.stdout.strip() if local_head_result.returncode == 0 else ""
        dirty_tree = bool(_run_command(["git", "status", "--short"]).stdout.strip())

        checks.append(
            (
                "OK" if latest_status == "SUCCESS" else "WARN",
                "Latest Railway deployment is settled",
                latest_status,
            )
        )

        drift_reasons: list[str] = []
        if repo and commit_hash and local_head and commit_hash != local_head:
            drift_reasons.append(f"Railway commit {commit_hash[:7]} != local HEAD {local_head[:7]}")
        if repo and dirty_tree:
            drift_reasons.append("local worktree has uncommitted changes that GitHub auto-deploy cannot see")
        checks.append(
            (
                "WARN" if drift_reasons else "OK",
                "Railway release source matches local release source",
                "; ".join(drift_reasons) if drift_reasons else (commit_message or "manual/local deployment"),
            )
        )
    except Exception as exc:
        checks.append(("WARN", "Railway deployment source", str(exc)))

    status = "OK"
    for check_status, _, _ in checks:
        if check_status == "FAIL":
            status = "FAIL"
            break
        if check_status == "WARN" and status != "FAIL":
            status = "WARN"
    return status, [_line(check_status, label, detail) for check_status, label, detail in checks]


def _integrity_checks(env: dict[str, str]) -> dict[str, tuple[str, list[str]]]:
    report = evaluate_runtime_integrity(env=env, repo_root=ROOT)
    rendered: dict[str, tuple[str, list[str]]] = {}
    for category_name, category in report["categories"].items():
        rendered[category_name] = (
            category["status"],
            [_line(check["status"], check["name"], check["detail"]) for check in category["checks"]],
        )
    return rendered


def _health_checks(base_url: str, admin_token: str | None) -> tuple[str, list[str]]:
    lines: list[str] = []
    status = "OK"
    session = requests.Session()
    session.headers.update({"User-Agent": "railway-parity-check/1.0"})

    try:
        health = session.get(f"{base_url}/health", timeout=10)
        health_ok = health.status_code == 200
        lines.append(_line("OK" if health_ok else "FAIL", "GET /health", f"status={health.status_code}"))
        if not health_ok:
            status = "FAIL"
    except Exception as exc:  # pragma: no cover - network failure path
        return "FAIL", [_line("FAIL", "GET /health", str(exc))]

    try:
        api_health = session.get(f"{base_url}/api/health", timeout=10)
        api_ok = api_health.status_code == 200
        lines.append(_line("OK" if api_ok else "FAIL", "GET /api/health", f"status={api_health.status_code}"))
        runtime_header = api_health.headers.get("X-Runtime-Stack", "")
        runtime_ok = runtime_header == "final"
        lines.append(_line("OK" if runtime_ok else "FAIL", "X-Runtime-Stack", runtime_header or "missing"))
        if not api_ok or not runtime_ok:
            status = "FAIL"
    except Exception as exc:  # pragma: no cover - network failure path
        lines.append(_line("FAIL", "GET /api/health", str(exc)))
        status = "FAIL"

    if admin_token:
        try:
            diag = session.get(
                f"{base_url}/diag/runtime-integrity",
                headers={"X-Admin-Token": admin_token},
                timeout=10,
            )
            diag_ok = diag.status_code == 200
            lines.append(_line("OK" if diag_ok else "FAIL", "GET /diag/runtime-integrity", f"status={diag.status_code}"))
            if diag_ok:
                payload = diag.json()
                remote_status = payload.get("overall_status", "unknown")
                lines.append(_line("OK" if remote_status != "FAIL" else "FAIL", "Remote runtime integrity", remote_status))
                if remote_status == "FAIL":
                    status = "FAIL"
                elif remote_status == "WARN" and status != "FAIL":
                    status = "WARN"
            else:
                status = "FAIL"
        except Exception as exc:  # pragma: no cover - network failure path
            lines.append(_line("FAIL", "GET /diag/runtime-integrity", str(exc)))
            status = "FAIL"
    else:
        lines.append(_line("WARN", "GET /diag/runtime-integrity", "admin token not available"))
        if status != "FAIL":
            status = "WARN"

    return status, lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local vs Railway production parity.")
    parser.add_argument("--service", default="ferreteria-bot", help="Railway service name to inspect")
    parser.add_argument("--base-url", default="", help="Override base URL instead of deriving from Railway vars")
    parser.add_argument("--admin-token", default="", help="Admin token override for diagnostic endpoint")
    parser.add_argument("--skip-railway", action="store_true", help="Run local checks only")
    args = parser.parse_args()

    categories: dict[str, tuple[str, list[str]]] = {}
    categories["build"] = _build_checks(args.service)

    railway_vars: dict[str, str] = {}
    if args.skip_railway:
        local_env = dict(os.environ)
        local_env["_SETTINGS_DATABASE_URL"] = local_env.get("DATABASE_URL", "")
        categories.update(_integrity_checks(local_env))
    else:
        try:
            railway_vars = _load_railway_vars(args.service)
            railway_vars["_SETTINGS_DATABASE_URL"] = railway_vars.get("DATABASE_URL", "")
            categories.update(_integrity_checks(railway_vars))
        except Exception as exc:
            categories["env"] = ("FAIL", [_line("FAIL", "Load Railway variables", str(exc))])
            categories["data"] = ("FAIL", [_line("FAIL", "Load Railway variables", "skipped because Railway vars are unavailable")])
            categories["service_role"] = ("FAIL", [_line("FAIL", "Load Railway variables", "service role could not be validated")])
            categories["domains"] = ("FAIL", [_line("FAIL", "Load Railway variables", "domain config could not be validated")])

    base_url = args.base_url.strip()
    if not base_url and railway_vars.get("RAILWAY_PUBLIC_DOMAIN"):
        base_url = railway_vars["RAILWAY_PUBLIC_DOMAIN"]
    if base_url:
        categories["health"] = _health_checks(
            _normalize_base_url(base_url),
            args.admin_token.strip() or railway_vars.get("ADMIN_TOKEN", "").strip() or None,
        )
    else:
        categories["health"] = ("FAIL", [_line("FAIL", "Base URL", "missing --base-url and RAILWAY_PUBLIC_DOMAIN")])

    overall = "OK"
    for _, (status, _) in categories.items():
        if status == "FAIL":
            overall = "FAIL"
            break
        if status == "WARN" and overall != "FAIL":
            overall = "WARN"

    for name, (status, lines) in categories.items():
        _print_category(name, status)
        for line in lines:
            print(line)

    print(f"\nOVERALL :: {overall}")
    return 1 if overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
