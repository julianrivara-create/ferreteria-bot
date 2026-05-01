"""
TurnInterpreter — single LLM call per turn that replaces IntentRouter + AcceptanceDetector.
Returns a rich TurnInterpretation with intent, entities, tone, and quote context.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "product_search",
    "policy_faq",
    "quote_modify",
    "quote_accept",
    "quote_reject",
    "escalate",
    "off_topic",
    "small_talk",
    "unknown",
}

VALID_TONES = {"neutral", "frustrated", "urgent"}
VALID_SEARCH_MODES = {"exact", "browse", "by_use", None}
VALID_POLICY_TOPICS = {
    "horario", "envio", "garantia", "factura", "devolucion", "reserva", "pago", None
}


@dataclass
class EntityBundle:
    product_terms: List[str] = field(default_factory=list)
    use_case: Optional[str] = None
    material: Optional[str] = None
    dimensions: Dict[str, Any] = field(default_factory=dict)
    qty: Optional[int] = None
    brand: Optional[str] = None
    budget: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "EntityBundle":
        if not isinstance(d, dict):
            return cls()
        return cls(
            product_terms=d.get("product_terms") or [],
            use_case=d.get("use_case"),
            material=d.get("material"),
            dimensions=d.get("dimensions") or {},
            qty=d.get("qty"),
            brand=d.get("brand"),
            budget=d.get("budget"),
        )

    def to_dict(self) -> dict:
        return {
            "product_terms": self.product_terms,
            "use_case": self.use_case,
            "material": self.material,
            "dimensions": self.dimensions,
            "qty": self.qty,
            "brand": self.brand,
            "budget": self.budget,
        }


@dataclass
class QuoteReference:
    references_existing_quote: bool = False
    line_hints: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "QuoteReference":
        if not isinstance(d, dict):
            return cls()
        return cls(
            references_existing_quote=bool(d.get("references_existing_quote", False)),
            line_hints=d.get("line_hints") or [],
        )

    def to_dict(self) -> dict:
        return {
            "references_existing_quote": self.references_existing_quote,
            "line_hints": self.line_hints,
        }


@dataclass
class TurnInterpretation:
    intent: str = "unknown"
    confidence: float = 0.0
    tone: str = "neutral"
    policy_topic: Optional[str] = None
    search_mode: Optional[str] = None
    entities: EntityBundle = field(default_factory=EntityBundle)
    quote_reference: QuoteReference = field(default_factory=QuoteReference)
    reset_signal: bool = False

    def is_low_confidence(self) -> bool:
        return self.confidence < 0.55

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "tone": self.tone,
            "policy_topic": self.policy_topic,
            "search_mode": self.search_mode,
            "entities": self.entities.to_dict(),
            "quote_reference": self.quote_reference.to_dict(),
            "reset_signal": self.reset_signal,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TurnInterpretation":
        if not isinstance(d, dict):
            return cls()
        intent = d.get("intent", "unknown")
        if intent not in VALID_INTENTS:
            intent = "unknown"
        tone = d.get("tone", "neutral")
        if tone not in VALID_TONES:
            tone = "neutral"
        confidence = float(d.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        policy_topic = d.get("policy_topic")
        if policy_topic not in VALID_POLICY_TOPICS:
            policy_topic = None
        search_mode = d.get("search_mode")
        if search_mode not in VALID_SEARCH_MODES:
            search_mode = None
        return cls(
            intent=intent,
            confidence=confidence,
            tone=tone,
            policy_topic=policy_topic,
            search_mode=search_mode,
            entities=EntityBundle.from_dict(d.get("entities") or {}),
            quote_reference=QuoteReference.from_dict(d.get("quote_reference") or {}),
            reset_signal=bool(d.get("reset_signal", False)),
        )

    @classmethod
    def unknown(cls) -> "TurnInterpretation":
        return cls(intent="unknown", confidence=0.0)


_SYSTEM_PROMPT = """Sos un clasificador de mensajes para un chatbot de ferretería argentina.
Dado un mensaje del cliente, devolvé SOLO JSON válido con esta estructura exacta. Sin texto adicional.

{
  "intent": "product_search|policy_faq|quote_modify|quote_accept|quote_reject|escalate|off_topic|small_talk|unknown",
  "confidence": 0.0,
  "tone": "neutral|frustrated|urgent",
  "policy_topic": "horario|envio|garantia|factura|devolucion|reserva|pago|null",
  "search_mode": "exact|browse|by_use|null",
  "entities": {
    "product_terms": [],
    "use_case": null,
    "material": null,
    "dimensions": {},
    "qty": null,
    "brand": null,
    "budget": null
  },
  "quote_reference": {
    "references_existing_quote": false,
    "line_hints": []
  },
  "reset_signal": false
}

Reglas:
- confidence < 0.6 si el mensaje es ambiguo
- search_mode="by_use" si el cliente describe un uso en vez de nombrar un producto
- search_mode="browse" si pide ver opciones sin producto específico
- policy_topic solo cuando la pregunta es sobre política operativa de la tienda
- tone="frustrated" si hay señales de enojo o repetición ("ya te dije", "cuántas veces", "no entendés")
- tone="urgent" si hay presión de tiempo ("para hoy", "urgente", "ya")
- quote_accept o quote_reject para CUALQUIER aceptación o rechazo, no solo "ok" o "dale"
- reset_signal=true si el cliente quiere cancelar todo y empezar de cero
- intent="escalate" si el cliente pide hablar con una persona explícitamente
"""


class TurnInterpreter:
    """
    Single LLM call per turn that classifies intent and extracts entities.
    Replaces IntentRouter + AcceptanceDetector.
    """

    def __init__(self, llm_client):
        """
        llm_client: an object with a send_message(messages, model=..., max_tokens=...) method
                    compatible with ChatGPTClient.
        """
        self.llm = llm_client

    def interpret(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        current_state: str = "idle",
    ) -> TurnInterpretation:
        """
        Classify the user turn into a TurnInterpretation.
        Uses a cheap, fast model call with max 200 output tokens.
        Falls back to TurnInterpretation.unknown() on any error.
        """
        try:
            messages = self._build_messages(user_message, history or [], current_state)
            # Save and override model/max_tokens for this cheap routing call
            orig_model = getattr(self.llm, "model", None)
            orig_max_tokens = getattr(self.llm, "max_tokens", None)
            orig_temperature = getattr(self.llm, "temperature", None)
            try:
                self.llm.model = "gpt-4o-mini"
                self.llm.max_tokens = 200
                self.llm.temperature = 0.0
                response = self.llm.send_message(messages=messages)
            finally:
                self.llm.model = orig_model
                self.llm.max_tokens = orig_max_tokens
                self.llm.temperature = orig_temperature
            return self._parse_response(response)
        except Exception as exc:
            logger.warning("TurnInterpreter failed: %s", exc)
            return TurnInterpretation.unknown()

    def _build_messages(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        current_state: str,
    ) -> List[Dict[str, str]]:
        # Last 3 turns of history for context
        recent = history[-6:] if len(history) > 6 else history
        context_lines = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                prefix = "Cliente" if role == "user" else "Bot"
                context_lines.append(f"{prefix}: {content[:120]}")

        context_str = "\n".join(context_lines) if context_lines else "(sin historial)"
        user_content = (
            f"Estado actual de la conversación: {current_state}\n"
            f"Historial reciente:\n{context_str}\n\n"
            f"Mensaje del cliente: {user_message}"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, response: Any) -> TurnInterpretation:
        """Extract JSON from LLM response and parse into TurnInterpretation."""
        # Handle different response shapes from ChatGPTClient
        text = ""
        if isinstance(response, str):
            text = response
        elif isinstance(response, dict):
            # OpenAI-style response dict
            choices = response.get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "")
            else:
                text = response.get("content", "") or response.get("text", "")
        elif hasattr(response, "content"):
            text = str(response.content)

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("TurnInterpreter JSON parse failed text=%r error=%s", text[:300], exc)
            return TurnInterpretation.unknown()
        return TurnInterpretation.from_dict(parsed)
