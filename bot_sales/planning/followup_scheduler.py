from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .pipeline import PipelineStage


class FollowupScheduler:
    def __init__(
        self,
        *,
        max_followups: int = 3,
        timezone_name: str = "UTC",
        quiet_hours_start: str = "22:00",
        quiet_hours_end: str = "08:00",
        min_interval_minutes: int = 60,
    ):
        self.max_followups = max_followups
        self.timezone_name = timezone_name
        self.quiet_hours_start = quiet_hours_start
        self.quiet_hours_end = quiet_hours_end
        self.min_interval_minutes = max(1, min_interval_minutes)

    def ensure_sequence(
        self,
        state: dict[str, Any],
        *,
        stage: PipelineStage,
        objection_type: str | None,
        now: datetime,
    ) -> None:
        plan = state.setdefault("followup_plan", [])

        if stage == PipelineStage.QUOTED:
            self._upsert(
                plan,
                key="quoted_24h",
                due_at=self._fit_policy(now + timedelta(hours=24)),
                template="quoted_followup_1",
            )
            self._upsert(
                plan,
                key="quoted_48h",
                due_at=self._fit_policy(now + timedelta(hours=48)),
                template="quoted_followup_2",
            )
            self._upsert(
                plan,
                key="quoted_144h",
                due_at=self._fit_policy(now + timedelta(hours=144)),
                template="quoted_followup_3",
            )

        if stage == PipelineStage.NEGOTIATING and objection_type == "PRICE_OBJECTION":
            self._upsert(
                plan,
                key="negotiating_price_24h",
                due_at=self._fit_policy(now + timedelta(hours=24)),
                template="negotiation_price_reassurance",
            )

        if stage == PipelineStage.NEGOTIATING and objection_type == "TRUST_OBJECTION":
            self._upsert(
                plan,
                key="negotiating_trust_24h",
                due_at=self._fit_policy(now + timedelta(hours=24)),
                template="negotiation_trust_reassurance",
            )

    def stop_on_user_reply(
        self,
        state: dict[str, Any],
        *,
        reply_text: str | None = "text",
        is_reaction: bool = False,
        now: datetime | None = None,
    ) -> bool:
        if is_reaction:
            return False
        if not isinstance(reply_text, str) or not reply_text.strip():
            return False

        plan = state.get("followup_plan", [])
        for item in plan:
            if item["status"] == "pending":
                item["status"] = "canceled"
        state["followup_sent_count"] = 0
        state["followup_stop_decision"] = {
            "reason": "text_reply",
            "at": (now or datetime.utcnow()).isoformat(),
        }
        return True

    def due_followups(self, state: dict[str, Any], *, now: datetime) -> list[dict[str, Any]]:
        plan = state.get("followup_plan", [])
        sent_count = int(state.get("followup_sent_count", 0))
        remaining = max(0, self.max_followups - sent_count)
        if remaining <= 0:
            return []

        due = []
        for item in sorted(plan, key=lambda row: row["due_at"]):
            if item["status"] != "pending":
                continue
            if item["due_at"] > now:
                continue
            due.append(item)
            if len(due) >= remaining:
                break
        return due

    def mark_sent(self, state: dict[str, Any], key: str, *, sent_at: datetime) -> None:
        plan = state.get("followup_plan", [])
        for item in plan:
            if item["key"] == key and item["status"] == "pending":
                item["status"] = "sent"
                item["sent_at"] = sent_at
                state["followup_sent_count"] = int(state.get("followup_sent_count", 0)) + 1
                break

    def _upsert(self, plan: list[dict[str, Any]], *, key: str, due_at: datetime, template: str) -> None:
        for item in plan:
            if item["key"] == key:
                return
        if self._violates_cooldown(plan, due_at):
            return
        plan.append(
            {
                "key": key,
                "due_at": due_at,
                "template": template,
                "status": "pending",
                "sent_at": None,
            }
        )

    def _violates_cooldown(self, plan: list[dict[str, Any]], due_at: datetime) -> bool:
        for item in plan:
            existing_due = item.get("due_at")
            if not isinstance(existing_due, datetime):
                continue
            if abs((existing_due - due_at).total_seconds()) < self.min_interval_minutes * 60:
                return True
        return False

    def _fit_policy(self, due_at: datetime) -> datetime:
        shifted = self._shift_out_of_quiet_hours(due_at)
        return shifted

    def _shift_out_of_quiet_hours(self, due_at: datetime) -> datetime:
        parsed_start = _parse_hhmm(self.quiet_hours_start)
        parsed_end = _parse_hhmm(self.quiet_hours_end)
        if not parsed_start or not parsed_end:
            return due_at

        try:
            tz = ZoneInfo(self.timezone_name)
        except Exception:
            tz = ZoneInfo("UTC")

        local_dt = due_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        local_hm = (local_dt.hour, local_dt.minute)
        crosses_midnight = parsed_start > parsed_end
        if crosses_midnight:
            in_quiet = local_hm >= parsed_start or local_hm < parsed_end
        else:
            in_quiet = parsed_start <= local_hm < parsed_end
        if not in_quiet:
            return due_at

        if crosses_midnight and local_hm >= parsed_start:
            candidate = (local_dt + timedelta(days=1)).replace(
                hour=parsed_end[0], minute=parsed_end[1], second=0, microsecond=0
            )
        else:
            candidate = local_dt.replace(hour=parsed_end[0], minute=parsed_end[1], second=0, microsecond=0)
            if not crosses_midnight and local_hm >= parsed_end:
                candidate = candidate + timedelta(days=1)

        return candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _parse_hhmm(raw: str) -> tuple[int, int] | None:
    try:
        hh, mm = str(raw).split(":", 1)
        h, m = int(hh), int(mm)
    except Exception:
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h, m
