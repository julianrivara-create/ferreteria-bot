from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crm.models import CRMDeal, CRMDealScoreEvent, CRMScoringRule
from app.crm.services.condition_eval import matches_conditions


class ScoringService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def apply_signal(self, deal_id: str, signal_key: str, context: dict) -> int:
        deal = (
            self.session.query(CRMDeal)
            .filter(CRMDeal.tenant_id == self.tenant_id, CRMDeal.id == deal_id)
            .with_for_update()
            .first()
        )
        if deal is None:
            return 0

        rules = (
            self.session.query(CRMScoringRule)
            .filter(
                CRMScoringRule.tenant_id == self.tenant_id,
                CRMScoringRule.signal_key == signal_key,
                CRMScoringRule.enabled.is_(True),
            )
            .all()
        )

        if not rules:
            return deal.score

        running = deal.score
        for rule in rules:
            if not matches_conditions(rule.conditions_json or {}, context):
                continue
            prev = running
            running += rule.points
            event = CRMDealScoreEvent(
                tenant_id=self.tenant_id,
                deal_id=deal.id,
                rule_id=rule.id,
                signal_key=signal_key,
                delta=rule.points,
                previous_score=prev,
                new_score=running,
                reason=rule.name,
                metadata_json={"context": context},
            )
            self.session.add(event)

        deal.score = running
        self.session.flush()
        return running

    def recompute_deal_score(self, deal_id: str) -> int:
        deal = (
            self.session.query(CRMDeal)
            .filter(CRMDeal.tenant_id == self.tenant_id, CRMDeal.id == deal_id)
            .with_for_update()
            .first()
        )
        if deal is None:
            return 0

        total = (
            self.session.query(func.coalesce(func.sum(CRMDealScoreEvent.delta), 0))
            .filter(CRMDealScoreEvent.tenant_id == self.tenant_id, CRMDealScoreEvent.deal_id == deal_id)
            .scalar()
        )
        deal.score = int(total or 0)
        self.session.flush()
        return deal.score

    def explain(self, deal_id: str, *, limit: int = 50) -> dict:
        deal = (
            self.session.query(CRMDeal)
            .filter(CRMDeal.tenant_id == self.tenant_id, CRMDeal.id == deal_id)
            .first()
        )
        if deal is None:
            return {"found": False}

        events = (
            self.session.query(CRMDealScoreEvent)
            .filter(CRMDealScoreEvent.tenant_id == self.tenant_id, CRMDealScoreEvent.deal_id == deal_id)
            .order_by(CRMDealScoreEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "found": True,
            "deal_id": deal.id,
            "score": deal.score,
            "events": [
                {
                    "id": e.id,
                    "signal_key": e.signal_key,
                    "delta": e.delta,
                    "previous_score": e.previous_score,
                    "new_score": e.new_score,
                    "reason": e.reason,
                    "metadata": e.metadata_json,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }
