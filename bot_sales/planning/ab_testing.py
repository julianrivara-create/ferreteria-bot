from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from .pipeline import PipelineStage, STAGE_RANK


class ABTestingEngine:
    def pick_variant(self, session_id: str, *, stage: PipelineStage, objection_type: str | None) -> str:
        seed = f"{session_id}|{stage.value}|{objection_type or 'none'}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return "A" if int(digest[-1], 16) % 2 == 0 else "B"

    def log_outbound(
        self,
        state: dict[str, Any],
        *,
        variant: str,
        stage: PipelineStage,
        objection_type: str | None,
        created_at: datetime,
    ) -> dict[str, Any]:
        events = state.setdefault("ab_events", [])
        row = {
            "id": f"ab-{len(events)+1}",
            "variant": variant,
            "stage": stage.value,
            "objection_type": objection_type or "NONE",
            "created_at": created_at,
            "reply_within_24h": False,
            "stage_progress_within_7d": False,
            "final_outcome": None,
        }
        events.append(row)
        return row

    def record_reply(self, state: dict[str, Any], *, replied_at: datetime) -> None:
        events = state.get("ab_events", [])
        for row in reversed(events):
            if row["reply_within_24h"]:
                continue
            age = replied_at - row["created_at"]
            if timedelta(seconds=0) <= age <= timedelta(hours=24):
                row["reply_within_24h"] = True
                return

    def record_stage_progress(self, state: dict[str, Any], *, new_stage: PipelineStage, when: datetime) -> None:
        events = state.get("ab_events", [])
        new_rank = STAGE_RANK.get(new_stage, 0)
        for row in events:
            if row["stage_progress_within_7d"]:
                continue
            age = when - row["created_at"]
            if age < timedelta(seconds=0) or age > timedelta(days=7):
                continue
            previous_rank = STAGE_RANK.get(PipelineStage(row["stage"]), 0)
            if new_rank > previous_rank:
                row["stage_progress_within_7d"] = True

    def record_final_outcome(self, state: dict[str, Any], *, outcome: PipelineStage) -> None:
        if outcome not in {PipelineStage.WON, PipelineStage.LOST}:
            return
        events = state.get("ab_events", [])
        for row in events:
            row["final_outcome"] = outcome.value.lower()

    def report(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in events:
            key = (row["stage"], row["objection_type"], row["variant"])
            agg = grouped.setdefault(
                key,
                {
                    "stage": row["stage"],
                    "objection_type": row["objection_type"],
                    "variant": row["variant"],
                    "sent": 0,
                    "reply_24h": 0,
                    "stage_progress_7d": 0,
                    "won": 0,
                    "lost": 0,
                },
            )
            agg["sent"] += 1
            agg["reply_24h"] += int(bool(row.get("reply_within_24h")))
            agg["stage_progress_7d"] += int(bool(row.get("stage_progress_within_7d")))
            final_outcome = str(row.get("final_outcome") or "").lower()
            if final_outcome == "won":
                agg["won"] += 1
            if final_outcome == "lost":
                agg["lost"] += 1

        output = []
        for agg in grouped.values():
            sent = max(1, agg["sent"])
            output.append(
                {
                    **agg,
                    "reply_24h_rate": round(agg["reply_24h"] / sent, 4),
                    "stage_progress_7d_rate": round(agg["stage_progress_7d"] / sent, 4),
                    "won_rate": round(agg["won"] / sent, 4),
                }
            )
        return sorted(output, key=lambda row: (row["stage"], row["objection_type"], row["variant"]))
