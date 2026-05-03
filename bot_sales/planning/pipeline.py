from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class PipelineStage(str, Enum):
    NEW = "NEW"
    QUALIFIED = "QUALIFIED"
    QUOTED = "QUOTED"
    NEGOTIATING = "NEGOTIATING"
    WON = "WON"
    LOST = "LOST"
    NURTURE = "NURTURE"


STAGE_RANK: dict[PipelineStage, int] = {
    PipelineStage.NEW: 10,
    PipelineStage.QUALIFIED: 20,
    PipelineStage.QUOTED: 30,
    PipelineStage.NEGOTIATING: 40,
    PipelineStage.WON: 50,
    PipelineStage.LOST: 50,
    PipelineStage.NURTURE: 15,
}


DEFAULT_ENTRY_CRITERIA: dict[PipelineStage, tuple[str, ...]] = {
    PipelineStage.NEW: tuple(),
    PipelineStage.QUALIFIED: (
        "product_family",
        "model",
        "storage",
        "condition",
        "payment_preference",
        "urgency",
    ),
    PipelineStage.QUOTED: (
        "product_family",
        "model",
        "storage",
        "condition",
        "payment_preference",
        "urgency",
    ),
    PipelineStage.NEGOTIATING: (
        "product_family",
        "model",
        "storage",
        "condition",
        "payment_preference",
        "urgency",
    ),
    PipelineStage.WON: (
        "product_family",
        "model",
        "storage",
        "condition",
        "payment_preference",
        "urgency",
    ),
    PipelineStage.LOST: tuple(),
    PipelineStage.NURTURE: tuple(),
}


TRANSITIONS: dict[PipelineStage, set[PipelineStage]] = {
    PipelineStage.NEW: {PipelineStage.QUALIFIED, PipelineStage.LOST, PipelineStage.NURTURE},
    PipelineStage.QUALIFIED: {PipelineStage.QUOTED, PipelineStage.LOST, PipelineStage.NURTURE},
    PipelineStage.QUOTED: {PipelineStage.NEGOTIATING, PipelineStage.WON, PipelineStage.LOST, PipelineStage.NURTURE},
    PipelineStage.NEGOTIATING: {PipelineStage.QUOTED, PipelineStage.WON, PipelineStage.LOST, PipelineStage.NURTURE},
    PipelineStage.NURTURE: {PipelineStage.QUALIFIED, PipelineStage.QUOTED, PipelineStage.LOST},
    PipelineStage.WON: {PipelineStage.WON},
    PipelineStage.LOST: {PipelineStage.LOST, PipelineStage.NURTURE},
}


@dataclass
class StageDecision:
    new_stage: PipelineStage | None
    reason: str | None


def default_pipeline_config() -> list[dict[str, Any]]:
    return [
        {"key": PipelineStage.NEW.value, "name": "Incoming", "position": 1, "sla_hours": 24},
        {"key": PipelineStage.QUALIFIED.value, "name": "Requirements Confirmed", "position": 2, "sla_hours": 24},
        {"key": PipelineStage.QUOTED.value, "name": "Quote Sent", "position": 3, "sla_hours": 48},
        {"key": PipelineStage.NEGOTIATING.value, "name": "Negotiating", "position": 4, "sla_hours": 36},
        {"key": PipelineStage.WON.value, "name": "Won", "position": 5, "is_won": True},
        {"key": PipelineStage.LOST.value, "name": "Lost", "position": 6, "is_lost": True},
        {"key": PipelineStage.NURTURE.value, "name": "Nurture", "position": 7, "sla_hours": 168},
    ]


# Intents that are conversational/social in nature — no purchase fields needed.
_CONVERSATIONAL_INTENTS: frozenset[str] = frozenset({
    "CHIT_CHAT",
    "GREETING_CHAT",
    "GREETING",
    "SUPPORT",
    "UNKNOWN",
})


def compute_missing_fields(context: dict[str, Any], intent_name: str | None = None) -> list[str]:
    # Conversational intents (greetings, small talk) never require product or
    # close-blocking fields — returning them would push the bot to ask
    # "¿Qué categoría buscás?" in response to "hola".
    if intent_name and intent_name.upper() in _CONVERSATIONAL_INTENTS:
        return []

    missing: list[str] = []
    # Multi-industry: require at least category or model, plus intent-to-close basics.
    if not context.get("product_family") and not context.get("model"):
        missing.append("product_family")
    if not context.get("urgency"):
        missing.append("urgency")

    payment_preference = context.get("payment_preference")
    needs_installments = context.get("needs_installments")
    if not payment_preference:
        missing.append("payment_preference")
    if payment_preference in {"card", "tarjeta"} and needs_installments is None:
        missing.append("needs_installments")

    return missing


def can_enter_stage(stage: PipelineStage, context: dict[str, Any]) -> bool:
    required = DEFAULT_ENTRY_CRITERIA.get(stage, tuple())
    return all(context.get(field) not in (None, "", []) for field in required)


def is_transition_allowed(current: PipelineStage, target: PipelineStage) -> bool:
    return target in TRANSITIONS.get(current, set())


def decide_stage(
    *,
    current_stage: PipelineStage,
    intent_name: str,
    context: dict[str, Any],
    missing_fields: list[str],
    objection_type: str | None,
    now: datetime,
) -> StageDecision:
    del now  # Reserved for future time-based transition rules.

    if context.get("force_lost"):
        target = PipelineStage.LOST
        return _decision(current_stage, target, "lead_opted_out")

    if context.get("force_won"):
        target = PipelineStage.WON
        if not missing_fields:
            return _decision(current_stage, target, "payment_or_commitment_confirmed")

    if context.get("inactive_days", 0) >= 14 and current_stage not in {PipelineStage.WON, PipelineStage.LOST}:
        return _decision(current_stage, PipelineStage.NURTURE, "inactive_over_14_days")

    if current_stage == PipelineStage.NEW and can_enter_stage(PipelineStage.QUALIFIED, context):
        return _decision(current_stage, PipelineStage.QUALIFIED, "minimum_requirements_confirmed")

    if current_stage in {PipelineStage.NEW, PipelineStage.QUALIFIED, PipelineStage.NURTURE}:
        if context.get("quote_sent") and not missing_fields:
            return _decision(current_stage, PipelineStage.QUOTED, "quote_or_options_sent")
        if intent_name == "EXACT_PRICE_REQUEST" and not missing_fields:
            return _decision(current_stage, PipelineStage.QUOTED, "exact_price_request_with_full_config")

    if current_stage in {PipelineStage.QUOTED, PipelineStage.NEGOTIATING} and objection_type:
        return _decision(current_stage, PipelineStage.NEGOTIATING, f"objection_detected:{objection_type}")

    if current_stage in {PipelineStage.QUALIFIED, PipelineStage.QUOTED, PipelineStage.NEGOTIATING}:
        if context.get("ready_to_pay") and not missing_fields:
            return _decision(current_stage, PipelineStage.WON, "high_intent_ready_to_pay")

    return StageDecision(new_stage=None, reason=None)


def _decision(current_stage: PipelineStage, target: PipelineStage, reason: str) -> StageDecision:
    if target == current_stage:
        return StageDecision(new_stage=None, reason=None)
    if not is_transition_allowed(current_stage, target):
        return StageDecision(new_stage=None, reason=None)
    return StageDecision(new_stage=target, reason=reason)
