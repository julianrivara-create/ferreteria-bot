#!/usr/bin/env python3
"""
review_unresolved.py
====================
Operational review script for unresolved/ambiguous ferreteria quote terms.

Run:
    python scripts/review_unresolved.py
    python scripts/review_unresolved.py --top 30
    python scripts/review_unresolved.py --db /custom/path/ferreteria.db
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_sales.persistence.quote_store import QuoteStore  # noqa: E402


RECOVERABLE_ISSUES = {
    "missing_dimensions",
    "variant_ambiguity",
    "weak_match",
    "category_fallback",
    "blocked_term",
}
OPERATOR_ONLY_ISSUES = {
    "catalog_gap",
    "unknown_term",
}


def _default_db_path() -> Path:
    return ROOT / "data" / "ferreteria.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Review unresolved Ferreteria quote terms")
    parser.add_argument("--top", type=int, default=20, help="How many top terms to show")
    parser.add_argument("--db", type=str, default="", help="Override SQLite DB path")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else _default_db_path()
    if not db_path.exists():
        print(f"No unresolved DB found at {db_path}")
        return 0

    store = QuoteStore(str(db_path), tenant_id="ferreteria")
    try:
        rows = store.list_unresolved_terms(limit=500)
    finally:
        store.close()

    if not rows:
        print("No unresolved terms logged yet.")
        return 0

    total = len(rows)
    by_status = Counter(row.get("status") or "unknown" for row in rows)
    by_family = Counter((row.get("inferred_family") or "sin_familia") for row in rows)
    by_issue = Counter((row.get("issue_type") or "sin_tipo") for row in rows)
    by_term = Counter((row.get("normalized_text") or row.get("raw_text") or "").strip() for row in rows)
    by_recoverability = Counter(
        "recoverable"
        if (row.get("issue_type") or "") in RECOVERABLE_ISSUES
        else "operator_only"
        if (row.get("issue_type") or "") in OPERATOR_ONLY_ISSUES
        else "review"
        for row in rows
    )

    print("\n=== FERRETERIA UNRESOLVED TERMS REPORT ===")
    print(f"DB: {db_path}")
    print(f"Total logged events: {total}")
    print()
    print("By status:")
    for status, count in sorted(by_status.items()):
        pct = round(count / total * 100)
        print(f"  {status:<24} {count:>5}  ({pct}%)")

    print()
    print("By inferred family:")
    for family, count in by_family.most_common(args.top):
        print(f"  {family:<24} {count:>5}")

    print()
    print("By issue type:")
    for issue, count in by_issue.most_common(args.top):
        print(f"  {issue:<24} {count:>5}")

    print()
    print("By recoverability:")
    for bucket, count in by_recoverability.most_common():
        print(f"  {bucket:<24} {count:>5}")

    print()
    print(f"Top {args.top} repeated normalized terms:")
    for i, (term, count) in enumerate(by_term.most_common(args.top), 1):
        print(f"  {i:>3}. [{count:>3}x]  {term}")

    print()
    print("ACTION:")
    print("  - sinonimos / coloquialismos -> synonyms.yaml o language_patterns.yaml")
    print("  - falta de dimensión -> family_rules.yaml o clarification_rules.yaml")
    print("  - sustitución insegura -> substitute_rules.yaml")
    print("  - producto realmente ausente -> revisar catálogo")
    print("  - después de cada fix repetido -> agregar fixture de regresión")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
