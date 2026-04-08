from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.crm.models import CRMMessage, CRMMessageEvent, CRMTenant


DEFAULT_SALES_POLICY: dict[str, Any] = {
    "discount_caps_by_stage": {
        "QUALIFIED": 0,
        "QUOTED": 3,
        "NEGOTIATING": 6,
    },
    "high_intent_handoff_threshold": 80,
    "ab_autopromote_enabled": True,
    "ab_min_sample": 150,
    "low_stock_threshold": 3,
    "ab_winners": {},
    "ab_autopromote_state": {},
}


def merge_sales_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    policy = dict(DEFAULT_SALES_POLICY)
    raw = raw or {}
    for key in ("discount_caps_by_stage", "ab_winners", "ab_autopromote_state"):
        value = raw.get(key)
        if isinstance(value, dict):
            policy[key] = {**policy.get(key, {}), **value}
    for key in ("high_intent_handoff_threshold", "ab_autopromote_enabled", "ab_min_sample", "low_stock_threshold"):
        if key in raw:
            policy[key] = raw[key]
    return policy


class ABVariantService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def evaluate(self, *, apply: bool = False, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.utcnow()
        tenant = self.session.query(CRMTenant).filter(CRMTenant.id == self.tenant_id).first()
        settings = dict((tenant.integration_settings or {}) if tenant else {})
        policy = merge_sales_policy((settings.get("sales_policy") or {}) if isinstance(settings.get("sales_policy"), dict) else {})

        if not bool(policy.get("ab_autopromote_enabled", True)):
            return {
                "enabled": False,
                "applied": False,
                "evaluations": [],
                "winners": dict(policy.get("ab_winners") or {}),
                "min_sample": int(policy.get("ab_min_sample", 150) or 150),
            }

        min_sample = max(1, int(policy.get("ab_min_sample", 150) or 150))
        since = now - timedelta(days=30)

        rows = (
            self.session.query(
                CRMMessage.channel,
                CRMMessageEvent.stage_at_send,
                CRMMessageEvent.objection_type,
                CRMMessageEvent.ab_variant,
                func.count(CRMMessageEvent.id).label("sent"),
                func.sum(case((CRMMessageEvent.final_outcome == "won", 1), else_=0)).label("won"),
            )
            .join(
                CRMMessage,
                (CRMMessage.tenant_id == CRMMessageEvent.tenant_id) & (CRMMessage.id == CRMMessageEvent.message_id),
            )
            .filter(
                CRMMessageEvent.tenant_id == self.tenant_id,
                CRMMessageEvent.event_type == "salesbot_outbound",
                CRMMessageEvent.ab_variant.in_(["A", "B"]),
                CRMMessageEvent.created_at >= since,
            )
            .group_by(
                CRMMessage.channel,
                CRMMessageEvent.stage_at_send,
                CRMMessageEvent.objection_type,
                CRMMessageEvent.ab_variant,
            )
            .all()
        )

        grouped: dict[tuple[str, str, str], dict[str, dict[str, float]]] = {}
        for channel, stage, objection, variant, sent, won in rows:
            key = (str(channel or "unknown"), str(stage or "unknown"), str(objection or "NONE"))
            segment = grouped.setdefault(key, {})
            sent_i = int(sent or 0)
            won_i = int(won or 0)
            segment[str(variant)] = {
                "sent": sent_i,
                "won": won_i,
                "won_rate": (won_i / sent_i) if sent_i else 0.0,
            }

        winners = dict(policy.get("ab_winners") or {})
        state = dict(policy.get("ab_autopromote_state") or {})
        evaluations: list[dict[str, Any]] = []
        today = now.date()

        for (channel, stage, objection), variants in sorted(grouped.items()):
            data_a = variants.get("A")
            data_b = variants.get("B")
            segment_key = f"{channel}|{stage}|{objection}"
            winner_candidate = None
            candidate_delta = 0.0

            if data_a and data_b and data_a["sent"] >= min_sample and data_b["sent"] >= min_sample:
                delta = data_a["won_rate"] - data_b["won_rate"]
                if delta >= 0.02:
                    winner_candidate = "A"
                    candidate_delta = delta
                elif delta <= -0.02:
                    winner_candidate = "B"
                    candidate_delta = abs(delta)

            previous = state.get(segment_key, {}) if isinstance(state.get(segment_key), dict) else {}
            prev_candidate = previous.get("candidate")
            prev_day_raw = previous.get("last_day")
            prev_day = None
            if isinstance(prev_day_raw, str):
                try:
                    prev_day = datetime.fromisoformat(prev_day_raw).date()
                except ValueError:
                    prev_day = None
            prev_streak = int(previous.get("streak") or 0)

            if winner_candidate is None:
                streak = 0
            elif prev_candidate == winner_candidate and prev_day and prev_day == (today - timedelta(days=1)):
                streak = prev_streak + 1
            else:
                streak = 1

            promote = bool(winner_candidate) and streak >= 3
            if promote:
                winners[segment_key] = winner_candidate

            state[segment_key] = {
                "candidate": winner_candidate,
                "streak": streak,
                "last_day": today.isoformat(),
                "delta_won_rate": round(candidate_delta, 6),
            }

            evaluations.append(
                {
                    "segment": {"channel": channel, "stage": stage, "objection_type": objection, "key": segment_key},
                    "variants": {
                        "A": data_a or {"sent": 0, "won": 0, "won_rate": 0.0},
                        "B": data_b or {"sent": 0, "won": 0, "won_rate": 0.0},
                    },
                    "candidate": winner_candidate,
                    "streak_days": streak,
                    "promoted": promote,
                }
            )

        if apply and tenant is not None:
            policy["ab_winners"] = winners
            policy["ab_autopromote_state"] = state
            policy["ab_last_run_at"] = now.isoformat()
            settings["sales_policy"] = policy
            tenant.integration_settings = settings
            self.session.flush()

        return {
            "enabled": True,
            "applied": bool(apply),
            "evaluations": evaluations,
            "winners": winners,
            "min_sample": min_sample,
        }
