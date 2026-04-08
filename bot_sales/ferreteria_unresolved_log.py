#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ferreteria_unresolved_log.py
============================
Lightweight JSONL logger for unresolved/ambiguous quote items.

Used to capture real customer terms that the catalog or synonym map
did not handle well, so they can be reviewed for synonym/catalog growth.

Usage (from ferreteria_quote.py or bot.py):
    from bot_sales.ferreteria_unresolved_log import log_unresolved_item
    log_unresolved_item(item)

Review:
    python scripts/review_unresolved.py
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default path — override via FERRETERIA_UNRESOLVED_LOG env var
_DEFAULT_LOG = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "tenants"
    / "ferreteria"
    / "unresolved_terms.jsonl"
)
_UNRESOLVED_LOGGING_ENABLED: ContextVar[bool] = ContextVar("ferreteria_unresolved_logging_enabled", default=True)


def _log_path() -> Path:
    env = os.environ.get("FERRETERIA_UNRESOLVED_LOG", "")
    return Path(env) if env else _DEFAULT_LOG


@contextmanager
def suppress_unresolved_logging():
    token = _UNRESOLVED_LOGGING_ENABLED.set(False)
    try:
        yield
    finally:
        _UNRESOLVED_LOGGING_ENABLED.reset(token)


def log_unresolved_item(
    item: Dict[str, Any],
    reason: str = "",
    log_path: Optional[Path] = None,
) -> None:
    """
    Append one JSONL record for an unresolved, ambiguous, or blocked quote item.

    Parameters
    ----------
    item    : QuoteItem dict (must have at least 'status', 'original', 'normalized')
    reason  : free-text reason string  (e.g. "score below threshold", "category fallback")
    log_path: override path (defaults to FERRETERIA_UNRESOLVED_LOG env or data dir)
    """
    status = item.get("status", "")
    # Only log genuinely weak/missing matches
    if status not in ("unresolved", "ambiguous", "blocked_by_missing_info"):
        return
    if not _UNRESOLVED_LOGGING_ENABLED.get():
        return

    record = {
        "ts":         datetime.now().isoformat(timespec="seconds"),
        "raw":        item.get("original", "").strip(),
        "normalized": item.get("normalized", "").strip(),
        "status":     status,
        "reason":     reason or item.get("notes", ""),
        "family":     item.get("family"),
        "missing_dimensions": item.get("missing_dimensions") or [],
        "issue_type": item.get("issue_type"),
    }

    path = Path(log_path) if log_path else _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Never raise from logging — never break the bot


def summarize_log(
    log_path: Optional[Path] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Read the JSONL log and return a summary dict.

    Returns
    -------
    {
        "total":     int,
        "by_status": {"unresolved": N, "ambiguous": N},
        "top_terms": [{"term": str, "count": int}, ...]   # most repeated raw terms
    }
    """
    path = Path(log_path) if log_path else _log_path()
    if not path.exists():
        return {"total": 0, "by_status": {}, "top_terms": []}

    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    by_status: Dict[str, int] = {}
    term_counts: Dict[str, int] = {}
    for r in records:
        status = r.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if status == "blocked_by_missing_info":
            by_status["ambiguous"] = by_status.get("ambiguous", 0) + 1
        raw = r.get("raw", "").lower().strip()
        if raw:
            term_counts[raw] = term_counts.get(raw, 0) + 1

    top_terms = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return {
        "total":     len(records),
        "by_status": by_status,
        "top_terms": [{"term": t, "count": c} for t, c in top_terms],
    }
