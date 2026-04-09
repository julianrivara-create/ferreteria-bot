from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .pipeline import PipelineStage


def _require_text(value: Any, *, field_name: str, min_length: int = 1, max_length: int = 255) -> str:
    text = str(value or "").strip()
    if len(text) < min_length:
        raise ValueError(f"{field_name} must have at least {min_length} chars")
    if len(text) > max_length:
        raise ValueError(f"{field_name} must have at most {max_length} chars")
    return text


def _parse_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    else:
        raise ValueError(f"{field_name} must be datetime or ISO string")

    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass
class StageUpdate:
    from_stage: PipelineStage
    to_stage: PipelineStage
    reason: str

    def __post_init__(self) -> None:
        self.from_stage = PipelineStage(self.from_stage)
        self.to_stage = PipelineStage(self.to_stage)
        self.reason = _require_text(self.reason, field_name="stage_update.reason", min_length=1, max_length=255)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_stage": self.from_stage.value,
            "to_stage": self.to_stage.value,
            "reason": self.reason,
        }


@dataclass
class ExtractedEntities:
    product_family: str | None = None
    model: str | None = None
    storage: str | None = None
    condition: str | None = None
    budget: str | None = None
    urgency: str | None = None
    payment_preference: str | None = None
    needs_installments: bool | None = None
    color_preference: str | None = None
    delivery_method: str | None = None

    @classmethod
    def model_validate(cls, data: Any) -> "ExtractedEntities":
        if not isinstance(data, dict):
            return cls()
        allowed = {
            "product_family",
            "model",
            "storage",
            "condition",
            "budget",
            "urgency",
            "payment_preference",
            "needs_installments",
            "color_preference",
            "delivery_method",
        }
        filtered = {k: data.get(k) for k in allowed}
        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_family": self.product_family,
            "model": self.model,
            "storage": self.storage,
            "condition": self.condition,
            "budget": self.budget,
            "urgency": self.urgency,
            "payment_preference": self.payment_preference,
            "needs_installments": self.needs_installments,
            "color_preference": self.color_preference,
            "delivery_method": self.delivery_method,
        }


@dataclass
class RecommendedOffer:
    variant: str
    product_config: str
    price: str | None = None
    why: str = ""

    def __post_init__(self) -> None:
        self.variant = _require_text(self.variant, field_name="recommended_offer.variant", min_length=1, max_length=1)
        if self.variant not in {"A", "B"}:
            raise ValueError("recommended_offer.variant must be 'A' or 'B'")
        self.product_config = _require_text(
            self.product_config,
            field_name="recommended_offer.product_config",
            min_length=1,
            max_length=255,
        )
        self.why = _require_text(self.why, field_name="recommended_offer.why", min_length=1, max_length=255)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "product_config": self.product_config,
            "price": self.price,
            "why": self.why,
        }


@dataclass
class CTA:
    type: str
    text: str

    def __post_init__(self) -> None:
        self.type = _require_text(self.type, field_name="cta.type", min_length=1, max_length=64)
        self.text = _require_text(self.text, field_name="cta.text", min_length=1, max_length=280)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "text": self.text}


@dataclass
class NextTask:
    type: str
    due_at: datetime
    title: str
    assigned_to: str | None = None

    def __post_init__(self) -> None:
        self.type = _require_text(self.type, field_name="next_task.type", min_length=1, max_length=64)
        self.due_at = _parse_datetime(self.due_at, field_name="next_task.due_at")
        self.title = _require_text(self.title, field_name="next_task.title", min_length=1, max_length=255)
        if self.assigned_to is not None:
            self.assigned_to = _require_text(
                self.assigned_to, field_name="next_task.assigned_to", min_length=1, max_length=128
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "due_at": self.due_at.isoformat(),
            "title": self.title,
            "assigned_to": self.assigned_to,
        }


@dataclass
class HandoffDecision:
    enabled: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": bool(self.enabled), "reason": self.reason}


@dataclass
class SalesResponseContract:
    reply_text: str
    intent: str
    stage: PipelineStage
    stage_update: StageUpdate | None = None
    missing_fields: list[str] = field(default_factory=list)
    extracted_entities: ExtractedEntities = field(default_factory=ExtractedEntities)
    objection_type: str | None = None
    recommended_offer: list[RecommendedOffer] = field(default_factory=list)
    cta: CTA = field(default_factory=lambda: CTA(type="ASK_ONE_FIELD", text="¿Querés que sigamos?"))
    next_task: NextTask | None = None
    confidence: float = 0.0
    human_handoff: HandoffDecision = field(default_factory=HandoffDecision)
    playbook_snippet: str | None = None
    ab_variant: str | None = None
    variant_key: str | None = None

    def __post_init__(self) -> None:
        self.reply_text = _require_text(self.reply_text, field_name="reply_text", min_length=1, max_length=1200)
        self.intent = _require_text(self.intent, field_name="intent", min_length=1, max_length=80)
        self.stage = PipelineStage(self.stage)
        self.confidence = float(self.confidence)
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        self.missing_fields = [str(f).strip() for f in (self.missing_fields or []) if str(f).strip()]
        if self.ab_variant is not None and self.ab_variant not in {"A", "B"}:
            raise ValueError("ab_variant must be 'A' or 'B' when present")

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        del mode
        return {
            "reply_text": self.reply_text,
            "intent": self.intent,
            "stage": self.stage.value,
            "stage_update": self.stage_update.to_dict() if self.stage_update else None,
            "missing_fields": list(self.missing_fields),
            "extracted_entities": self.extracted_entities.to_dict(),
            "objection_type": self.objection_type,
            "recommended_offer": [row.to_dict() for row in self.recommended_offer],
            "cta": self.cta.to_dict(),
            "next_task": self.next_task.to_dict() if self.next_task else None,
            "confidence": float(self.confidence),
            "human_handoff": self.human_handoff.to_dict(),
            "playbook_snippet": self.playbook_snippet,
            "ab_variant": self.ab_variant,
            "variant_key": self.variant_key,
        }


class OutputContractParser:
    def parse(
        self,
        raw_output: str,
        *,
        format_fixer: Callable[[str, str], str] | None = None,
        max_attempts: int = 2,
    ) -> SalesResponseContract:
        attempts = max(1, max_attempts)
        candidate = raw_output or ""
        last_error = "unknown"

        for attempt in range(attempts):
            try:
                payload = _json_payload(candidate)
                return _contract_from_payload(payload)
            except Exception as exc:
                last_error = str(exc)
                if format_fixer is None or attempt == attempts - 1:
                    break
                candidate = format_fixer(candidate, last_error)

        raise ValueError(f"Invalid sales output contract after {attempts} attempts: {last_error}")


def _contract_from_payload(payload: dict[str, Any]) -> SalesResponseContract:
    stage_update_payload = payload.get("stage_update")
    stage_update = StageUpdate(**stage_update_payload) if isinstance(stage_update_payload, dict) else None

    extracted_payload = payload.get("extracted_entities")
    extracted_entities = (
        ExtractedEntities.model_validate(extracted_payload)
        if isinstance(extracted_payload, dict)
        else ExtractedEntities()
    )

    offers_payload = payload.get("recommended_offer") or []
    offers: list[RecommendedOffer] = []
    for item in offers_payload:
        if isinstance(item, dict):
            offers.append(RecommendedOffer(**item))

    cta_payload = payload.get("cta")
    if not isinstance(cta_payload, dict):
        raise ValueError("cta must be an object")
    cta = CTA(**cta_payload)

    next_task_payload = payload.get("next_task")
    next_task = NextTask(**next_task_payload) if isinstance(next_task_payload, dict) else None

    handoff_payload = payload.get("human_handoff")
    handoff = HandoffDecision(**handoff_payload) if isinstance(handoff_payload, dict) else HandoffDecision()

    return SalesResponseContract(
        reply_text=payload.get("reply_text"),
        intent=payload.get("intent"),
        stage=payload.get("stage"),
        stage_update=stage_update,
        missing_fields=payload.get("missing_fields") or [],
        extracted_entities=extracted_entities,
        objection_type=payload.get("objection_type"),
        recommended_offer=offers,
        cta=cta,
        next_task=next_task,
        confidence=payload.get("confidence", 0.0),
        human_handoff=handoff,
        playbook_snippet=payload.get("playbook_snippet"),
        ab_variant=payload.get("ab_variant"),
        variant_key=payload.get("variant_key"),
    )


def _json_payload(raw_output: str) -> dict[str, Any]:
    raw_output = (raw_output or "").strip()
    if not raw_output:
        raise ValueError("empty output")

    block = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_output, flags=re.DOTALL | re.IGNORECASE)
    if block:
        raw_output = block.group(1)

    loaded = json.loads(raw_output)
    if not isinstance(loaded, dict):
        raise ValueError("output must be a JSON object")
    return loaded
