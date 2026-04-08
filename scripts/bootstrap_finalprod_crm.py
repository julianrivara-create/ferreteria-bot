#!/usr/bin/env python3
"""Bootstrap Final Production CRM schema and tenants from tenants.yaml."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.runtime_bootstrap import ensure_runtime_bootstrap


def main() -> int:
    result = ensure_runtime_bootstrap()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
