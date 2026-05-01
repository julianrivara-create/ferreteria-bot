"""
In-process metrics aggregation for the ferreteria bot.
Lightweight — no external dependencies. Counters only, reset on restart.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict


class BotMetrics:
    """Thread-safe in-process counters."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._counters: Dict[str, int] = defaultdict(int)
                cls._instance._lock = threading.Lock()
        return cls._instance

    def inc(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._counters[key] += n

    def get(self, key: str) -> int:
        with self._lock:
            return self._counters.get(key, 0)

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counters)


# Singleton
metrics = BotMetrics()

# Helper functions for common counters
def record_turn(intent: str, handler: str, state_after: str) -> None:
    metrics.inc("turns_total")
    metrics.inc(f"intent.{intent}")
    metrics.inc(f"handler.{handler}")
    metrics.inc(f"state.{state_after}")

def record_acceptance(success: bool) -> None:
    if success:
        metrics.inc("acceptance.detected")
    else:
        metrics.inc("acceptance.missed")

def record_search(status: str) -> None:
    metrics.inc(f"search.{status}")

def record_escalation(reason: str) -> None:
    metrics.inc("escalations_total")
    metrics.inc(f"escalation.{reason}")

def record_latency_bucket(latency_ms: int) -> None:
    if latency_ms < 500:
        metrics.inc("latency.under_500ms")
    elif latency_ms < 1500:
        metrics.inc("latency.500ms_1500ms")
    elif latency_ms < 3000:
        metrics.inc("latency.1500ms_3000ms")
    else:
        metrics.inc("latency.over_3000ms")
