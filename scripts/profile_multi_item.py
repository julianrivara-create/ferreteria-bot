#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Profiling script for multi-item query latency.

Usage:
    PYTHONPATH=. python3 scripts/profile_multi_item.py

Instruments key functions via monkey-patching (no bot code modified).
Produces a timing breakdown to identify the actual bottleneck.
"""

import time
import sys
import os
import functools
from pathlib import Path

# ── Ensure project root is on sys.path ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# ── Timing infrastructure ─────────────────────────────────────────────────────
_timings: dict = {}


def _record(label: str, elapsed: float) -> None:
    _timings.setdefault(label, []).append(elapsed)


def _clear() -> None:
    _timings.clear()


# ── Monkey-patch BEFORE any bot import that uses these functions ──────────────

# 1. Database methods
import bot_sales.core.database as _db_mod

_orig_find_matches = _db_mod.Database.find_matches
_orig_find_matches_hybrid = _db_mod.Database.find_matches_hybrid
_orig_get_all_models = _db_mod.Database.get_all_models
_orig_available_for_sku = _db_mod.Database.available_for_sku


def _p_find_matches(self, model, *args, **kwargs):
    t0 = time.perf_counter()
    r = _orig_find_matches(self, model, *args, **kwargs)
    _record("find_matches", time.perf_counter() - t0)
    return r


def _p_find_matches_hybrid(self, model, *args, **kwargs):
    t0 = time.perf_counter()
    r = _orig_find_matches_hybrid(self, model, *args, **kwargs)
    _record("find_matches_hybrid", time.perf_counter() - t0)
    return r


def _p_get_all_models(self):
    t0 = time.perf_counter()
    r = _orig_get_all_models(self)
    _record("get_all_models", time.perf_counter() - t0)
    return r


def _p_available_for_sku(self, sku):
    t0 = time.perf_counter()
    r = _orig_available_for_sku(self, sku)
    _record("available_for_sku", time.perf_counter() - t0)
    return r


_db_mod.Database.find_matches = _p_find_matches
_db_mod.Database.find_matches_hybrid = _p_find_matches_hybrid
_db_mod.Database.get_all_models = _p_get_all_models
_db_mod.Database.available_for_sku = _p_available_for_sku

# 2. KnowledgeLoader
import bot_sales.knowledge.loader as _kl_mod

_orig_kl_load = _kl_mod.KnowledgeLoader.load


def _p_kl_load(self, force=False):
    t0 = time.perf_counter()
    r = _orig_kl_load(self, force=force)
    _record("knowledge_load", time.perf_counter() - t0)
    return r


_kl_mod.KnowledgeLoader.load = _p_kl_load

# 3. BusinessLogic methods
import bot_sales.core.business_logic as _bl_mod

_orig_buscar_stock = _bl_mod.BusinessLogic.buscar_stock
_orig_normalize_model = _bl_mod.BusinessLogic._normalize_model


def _p_buscar_stock(self, modelo, *args, **kwargs):
    t0 = time.perf_counter()
    r = _orig_buscar_stock(self, modelo, *args, **kwargs)
    _record("buscar_stock", time.perf_counter() - t0)
    return r


def _p_normalize_model(self, modelo):
    t0 = time.perf_counter()
    r = _orig_normalize_model(self, modelo)
    _record("_normalize_model", time.perf_counter() - t0)
    return r


_bl_mod.BusinessLogic.buscar_stock = _p_buscar_stock
_bl_mod.BusinessLogic._normalize_model = _p_normalize_model

# 4. ferreteria_quote functions
import bot_sales.ferreteria_quote as _fq_mod

_orig_parse_quote_items = _fq_mod.parse_quote_items
_orig_resolve_quote_item = _fq_mod.resolve_quote_item


def _p_parse_quote_items(message):
    t0 = time.perf_counter()
    r = _orig_parse_quote_items(message)
    _record("parse_quote_items", time.perf_counter() - t0)
    return r


def _p_resolve_quote_item(parsed, logic, knowledge=None):
    t0 = time.perf_counter()
    r = _orig_resolve_quote_item(parsed, logic, knowledge=knowledge)
    _record("resolve_quote_item", time.perf_counter() - t0)
    return r


_fq_mod.parse_quote_items = _p_parse_quote_items
_fq_mod.resolve_quote_item = _p_resolve_quote_item

# ── Bot init ──────────────────────────────────────────────────────────────────

def init_bot():
    """Initialize minimal bot: DB + BusinessLogic + KnowledgeLoader. No Flask, no LLM."""
    import yaml
    from bot_sales.core.database import Database
    from bot_sales.core.business_logic import BusinessLogic
    from bot_sales.knowledge.loader import KnowledgeLoader

    profile_path = PROJECT_ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    paths = profile.get("paths", {})

    catalog_csv = str(PROJECT_ROOT / paths.get("catalog", "data/tenants/ferreteria/catalog.csv"))
    db_path = str(PROJECT_ROOT / paths.get("db", "data/ferreteria.db"))
    log_path = str(PROJECT_ROOT / "logs" / "profile_bot.log")

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    db = Database(db_file=db_path, catalog_csv=catalog_csv, log_path=log_path)
    logic = BusinessLogic(db)
    kl = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)

    # Pre-load knowledge and attach to logic (mirrors production setup).
    # Catch KnowledgeValidationError — production SalesBot._knowledge() does the same.
    try:
        knowledge = kl.load()
        logic.knowledge = knowledge
        print(f"  Knowledge loaded OK")
    except Exception as exc:
        print(f"  WARNING: knowledge load failed ({type(exc).__name__}: {exc})")
        print(f"  Proceeding with knowledge=None (mirrors production fallback)")
        knowledge = None
        logic.knowledge = None

    return db, logic, kl, profile


# ── Profiling run ─────────────────────────────────────────────────────────────

def run_profile(query: str, logic, kl, run_label: str) -> dict:
    """Run one profiling pass for the given query."""
    _clear()

    t_total_start = time.perf_counter()

    # Step 1: parse
    parsed_items = _fq_mod.parse_quote_items(query)
    item_names = [p["normalized"][:30] for p in parsed_items]

    # Step 2: load knowledge (once, as the bot should)
    t_know = time.perf_counter()
    try:
        knowledge = kl.load()
    except Exception:
        knowledge = None
    know_elapsed = time.perf_counter() - t_know

    # Step 3: resolve items sequentially (current production behavior)
    t_resolve_start = time.perf_counter()
    per_item_times = []
    resolved = []
    for i, p in enumerate(parsed_items):
        t_item = time.perf_counter()
        item = _fq_mod.resolve_quote_item(p, logic, knowledge=knowledge)
        item_elapsed = time.perf_counter() - t_item
        per_item_times.append(item_elapsed)
        resolved.append(item)

    resolve_elapsed = time.perf_counter() - t_resolve_start
    total_elapsed = time.perf_counter() - t_total_start

    return {
        "label": run_label,
        "query": query,
        "item_count": len(parsed_items),
        "item_names": item_names,
        "total_elapsed": total_elapsed,
        "know_elapsed": know_elapsed,
        "resolve_elapsed": resolve_elapsed,
        "per_item_times": per_item_times,
        "resolved_statuses": [r.get("status") for r in resolved],
        "timings_snapshot": {k: list(v) for k, v in _timings.items()},
    }


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(result: dict) -> None:
    label = result["label"]
    timings = result["timings_snapshot"]

    # Compute total from all measured buckets
    all_measured = [t for v in timings.values() for t in v]
    total_measured = sum(all_measured)

    print(f"\n{'='*65}")
    print(f"PROFILE REPORT — {label}")
    print(f"{'='*65}")
    print(f"  Query       : {result['query'][:70]}")
    print(f"  Items parsed: {result['item_count']}  →  {result['item_names']}")
    print(f"  Statuses    : {result['resolved_statuses']}")
    print()
    print(f"  Total elapsed  : {result['total_elapsed']:.3f}s")
    print(f"  knowledge_load : {result['know_elapsed']:.3f}s  (1 call, pre-resolve)")
    print(f"  resolve_all    : {result['resolve_elapsed']:.3f}s  (all {result['item_count']} items)")
    print()

    BUCKETS = [
        ("parse_quote_items",    "parse_quote_items"),
        ("resolve_quote_item",   "resolve_quote_item (per item)"),
        ("buscar_stock",         "buscar_stock (per call)"),
        ("find_matches_hybrid",  "find_matches_hybrid (per call)"),
        ("find_matches",         "find_matches (per call)"),
        ("_normalize_model",     "_normalize_model (per call)"),
        ("get_all_models",       "get_all_models (per call)"),
        ("available_for_sku",    "available_for_sku (per call)"),
        ("knowledge_load",       "knowledge_load (per call)"),
    ]

    print(f"  {'Function':<35} {'calls':>5}  {'total':>7}  {'avg':>7}  {'%':>5}")
    print(f"  {'-'*35}  {'-----':>5}  {'-------':>7}  {'-------':>7}  {'-----':>5}")
    for key, display in BUCKETS:
        times = timings.get(key, [])
        if not times:
            continue
        cnt = len(times)
        tot = sum(times)
        avg = tot / cnt
        pct = (tot / total_measured * 100) if total_measured > 0 else 0
        print(f"  {display:<35} {cnt:>5}  {tot:>7.3f}s  {avg:>7.3f}s  {pct:>4.1f}%")

    print()
    print(f"  Per-item resolve times:")
    for i, (name, t) in enumerate(zip(result["item_names"], result["per_item_times"])):
        print(f"    item {i+1}: '{name}' → {t:.3f}s")

    # Estimate: how many full-table scans happened
    fm_calls = len(timings.get("find_matches", []))
    fmh_calls = len(timings.get("find_matches_hybrid", []))
    print()
    print(f"  Full-catalog scans: find_matches={fm_calls}  find_matches_hybrid={fmh_calls}")
    print(f"  (Each scan loads ALL ~63K rows from SQLite into Python)")


def print_summary(results: list) -> None:
    print(f"\n{'='*65}")
    print("SUMMARY ACROSS RUNS")
    print(f"{'='*65}")
    for r in results:
        print(f"  {r['label']:<10}  total={r['total_elapsed']:.3f}s  "
              f"resolve={r['resolve_elapsed']:.3f}s  "
              f"know={r['know_elapsed']:.3f}s")

    totals = [r["total_elapsed"] for r in results]
    avg_total = sum(totals) / len(totals)
    print(f"\n  Average total: {avg_total:.3f}s")

    # Identify dominant bottleneck in last run
    last = results[-1]["timings_snapshot"]
    bucket_totals = {k: sum(v) for k, v in last.items()}
    ranked = sorted(bucket_totals.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  TOP BOTTLENECK (last run): {ranked[0][0]} = {ranked[0][1]:.3f}s total")
    if len(ranked) > 1:
        print(f"  2nd: {ranked[1][0]} = {ranked[1][1]:.3f}s")
    if len(ranked) > 2:
        print(f"  3rd: {ranked[2][0]} = {ranked[2][1]:.3f}s")


# ── Main ──────────────────────────────────────────────────────────────────────

QUERY_5_ITEMS = (
    "Necesito 10 tornillos para chapa 8mm, 5 mechas 8mm, "
    "2 taladros, 3 tarugos 8mm y 1 silicona"
)

QUERY_3_ITEMS = "Necesito mechas 8mm, tarugos 8mm y tornillos 8mm"

RUNS = 3


def main() -> None:
    print("=" * 65)
    print("FERRETERIA MULTI-ITEM LATENCY PROFILER")
    print("=" * 65)

    print("\nInitializing bot (DB + BusinessLogic + KnowledgeLoader)...")
    t0 = time.perf_counter()
    db, logic, kl, profile = init_bot()
    init_elapsed = time.perf_counter() - t0
    print(f"Bot initialized in {init_elapsed:.2f}s")

    # Count rows in DB for reference
    row_count = db.cursor.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
    print(f"Catalog rows in SQLite: {row_count:,}")

    results_5 = []
    print(f"\n{'─'*65}")
    print(f"BENCHMARK: 5-item query")
    print(f"Query: {QUERY_5_ITEMS!r}")
    for i in range(1, RUNS + 1):
        result = run_profile(QUERY_5_ITEMS, logic, kl, f"5-item run{i}")
        results_5.append(result)
        print(f"  Run {i}: total={result['total_elapsed']:.3f}s  "
              f"resolve={result['resolve_elapsed']:.3f}s")
        if i == RUNS:
            print_report(result)

    print_summary(results_5)

    results_3 = []
    print(f"\n{'─'*65}")
    print(f"BENCHMARK: 3-item query")
    print(f"Query: {QUERY_3_ITEMS!r}")
    for i in range(1, RUNS + 1):
        result = run_profile(QUERY_3_ITEMS, logic, kl, f"3-item run{i}")
        results_3.append(result)
        print(f"  Run {i}: total={result['total_elapsed']:.3f}s  "
              f"resolve={result['resolve_elapsed']:.3f}s")
        if i == RUNS:
            print_report(result)

    print_summary(results_3)

    print(f"\n{'='*65}")
    print("DIAGNOSIS COMPLETE")
    print("Review the reports above to identify the dominant bottleneck.")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
