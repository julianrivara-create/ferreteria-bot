#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Runtime smoke checks for deploy readiness."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

# Ensure project root is importable when executed as `python3 scripts/...`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsgi import app


def _print_result(ok: bool, label: str, details: str = "") -> None:
    prefix = "OK" if ok else "FAIL"
    suffix = f" - {details}" if details else ""
    print(f"[{prefix}] {label}{suffix}")


def run_smoke() -> int:
    checks: List[Tuple[str, str, int]] = [
        ("GET", "/health", 200),
        ("GET", "/api/products", 200),
        ("GET", "/api/t/farmacia/products", 200),
        ("GET", "/api/t/ropa/products", 200),
        ("GET", "/dashboard/login", 200),
    ]

    failures = 0
    client = app.test_client()

    for method, path, expected in checks:
        resp = client.open(path, method=method)
        ok = resp.status_code == expected
        if not ok:
            failures += 1
        _print_result(ok, f"{method} {path}", f"status={resp.status_code}, expected={expected}")

    # Minimal contract for /health payload (supports legacy and Final Production schemas)
    health_resp = client.get("/health")
    health_json = health_resp.get_json(silent=True) or {}
    ok_status = "status" in health_json
    if not ok_status:
        failures += 1
    _print_result(ok_status, "/health has key 'status'")

    ok_identity = ("service" in health_json) or ("version" in health_json)
    if not ok_identity:
        failures += 1
    _print_result(ok_identity, "/health has key 'service' or 'version'")

    if failures:
        print(f"\nSmoke checks failed: {failures}")
        return 1

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke())
