from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .logging_config import logger
from .state import update_counters
from .types import OUTCOME_DEPENDENCY_ERROR, OUTCOME_FAIL, OUTCOME_OK, OUTCOME_WARN

_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
_HEX_RE = re.compile(r"\b0x[0-9a-f]+\b", re.IGNORECASE)
_REQ_ID_RE = re.compile(r"\b(?:req(?:uest)?[_-]?id|trace[_-]?id|span[_-]?id)[=: ]+[A-Za-z0-9._-]+\b", re.IGNORECASE)
_NUM_RE = re.compile(r"\b\d{5,}\b")

_HARD_FAILURE_SIGNATURES = [
    re.compile(r"outofmemory", re.IGNORECASE),
    re.compile(r"crashloop", re.IGNORECASE),
    re.compile(r"\bpanic\b", re.IGNORECASE),
    re.compile(r"unhandled exception", re.IGNORECASE),
    re.compile(r"segmentation fault", re.IGNORECASE),
]


def normalize_log_message(message: str) -> str:
    text = (message or "").strip()
    text = _UUID_RE.sub("<uuid>", text)
    text = _HEX_RE.sub("<hex>", text)
    text = _REQ_ID_RE.sub("<reqid>", text)
    text = _NUM_RE.sub("<num>", text)
    return " ".join(text.split())


def bucket_timestamp(ts_raw: str, bucket_seconds: int) -> int:
    bucket = max(1, int(bucket_seconds or 30))
    try:
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        epoch = int(ts.timestamp())
    except Exception:
        epoch = 0
    return (epoch // bucket) * bucket


def build_log_fingerprint(service_id: str, message: str, ts_raw: str, bucket_seconds: int = 30) -> str:
    normalized = normalize_log_message(message)
    msg_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    bkt = bucket_timestamp(ts_raw, bucket_seconds)
    return f"{service_id}:{msg_hash}:{bkt}"


def dedupe_logs(logs: list[dict[str, Any]], service_id: str, bucket_seconds: int = 30) -> list[dict[str, Any]]:
    seen = set()
    deduped: list[dict[str, Any]] = []
    for item in logs or []:
        if not isinstance(item, dict):
            continue
        fp = build_log_fingerprint(
            service_id=service_id,
            message=str(item.get("message", "")),
            ts_raw=str(item.get("timestamp", "")),
            bucket_seconds=bucket_seconds,
        )
        if fp in seen:
            continue
        seen.add(fp)
        out = dict(item)
        out["normalized_message"] = normalize_log_message(str(item.get("message", "")))
        out["dedupe_fingerprint"] = fp
        deduped.append(out)
    return deduped


def extract_hard_failure_signatures(logs: list[dict[str, Any]]) -> list[str]:
    hits = set()
    for item in logs or []:
        msg = str(item.get("message", ""))
        for pattern in _HARD_FAILURE_SIGNATURES:
            if pattern.search(msg):
                hits.add(pattern.pattern)
    return sorted(hits)


async def fetch_railway_logs(
    service_id: str,
    api_token: str | None,
    lookback_hours: int = 4,
    max_lines: int = 1000,
    *,
    bucket_seconds: int = 30,
    railway_client=None,
    conn=None,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Backward-compatible wrapper. If `railway_client` is provided it is used;
    otherwise this function returns an empty list and logs why.
    """
    if not api_token:
        logger.warning("RAILWAY_API_TOKEN not provided, skipping log fetch")
        return []
    if not service_id:
        logger.warning("Railway service_id not configured, skipping log fetch")
        return []
    if railway_client is None or conn is None or not tenant_id:
        logger.warning("Railway client context missing, skipping log fetch")
        return []

    logs = await railway_client.deployment_logs(
        conn,
        tenant_id=tenant_id,
        service_id=service_id,
        lookback_hours=int(lookback_hours),
        limit=int(max_lines),
    )

    min_ts = datetime.now(timezone.utc) - timedelta(hours=max(1, int(lookback_hours)))
    filtered: list[dict[str, Any]] = []
    for entry in logs:
        ts_raw = str(entry.get("timestamp", ""))
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            if ts >= min_ts:
                filtered.append(entry)
        except Exception:
            filtered.append(entry)

    deduped = dedupe_logs(filtered[: int(max_lines)], service_id, bucket_seconds=bucket_seconds)
    approx_bytes = sum(len(x.get("message", "")) for x in deduped)
    update_counters(pulls=1, bytes_val=approx_bytes)
    return deduped


def scan_logs(logs: list[dict[str, Any]], patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for pattern in patterns or []:
        try:
            regex = re.compile(str(pattern.get("regex", "")), re.IGNORECASE)
        except re.error:
            findings.append(
                {
                    "rule_name": pattern.get("name", "invalid_regex"),
                    "severity": OUTCOME_WARN,
                    "count": 1,
                    "threshold": pattern.get("max_count_4h", 0),
                    "evidence": ["Invalid regex configuration"],
                }
            )
            continue

        matches = [l for l in logs if regex.search(l.get("normalized_message", l.get("message", "")))]
        threshold = int(pattern.get("max_count_4h", 0))
        if len(matches) > threshold:
            sev = str(pattern.get("severity", OUTCOME_WARN)).upper()
            if sev not in {OUTCOME_WARN, OUTCOME_FAIL}:
                sev = OUTCOME_WARN
            findings.append(
                {
                    "rule_name": pattern.get("name", "unnamed_rule"),
                    "severity": sev,
                    "count": len(matches),
                    "threshold": threshold,
                    "evidence": [str(m.get("message", ""))[:200] for m in matches[:3]],
                }
            )
    return findings


def summarize_logs_check(logs: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    status = OUTCOME_OK
    if any(f.get("severity") == OUTCOME_FAIL for f in findings):
        status = OUTCOME_FAIL
    elif findings:
        status = OUTCOME_WARN
    return {
        "type": "logs",
        "status": status,
        "ok": status in {OUTCOME_OK, OUTCOME_WARN},
        "log_count": len(logs),
        "finding_count": len(findings),
        "hard_failure_signatures": extract_hard_failure_signatures(logs),
    }

