"""
Structured per-turn event for observability and metrics.
Logged as JSON to the existing logger and optionally to a DB table.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TurnEvent:
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str = ""
    tenant_id: str = ""
    state_before: str = "unknown"
    state_after: str = "unknown"
    interpreted_intent: str = "unknown"
    confidence: float = 0.0
    tone: str = "neutral"
    handler: str = "unknown"
    quote_id: Optional[str] = None
    policy_topic: Optional[str] = None
    search_mode: Optional[str] = None
    candidate_count: int = 0
    clarification_count: int = 0
    handoff_reason: Optional[str] = None
    model: str = ""
    latency_ms: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    # timestamps
    _start_ts: float = field(default_factory=time.time, repr=False)

    def finish(self) -> None:
        """Call when the turn is complete to record latency."""
        self.latency_ms = int((time.time() - self._start_ts) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("_start_ts", None)
        return d

    def log(self) -> None:
        """Emit as a single structured JSON log line."""
        self.finish()
        logger.info("TURN_EVENT %s", json.dumps(self.to_dict()))

    @classmethod
    def start(cls, session_id: str, tenant_id: str, state_before: str) -> "TurnEvent":
        return cls(
            session_id=session_id,
            tenant_id=tenant_id,
            state_before=state_before,
        )
