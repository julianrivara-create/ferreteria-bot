"""
IntentRouter — lightweight intent classifier for the ferretería bot.

Single LLM call (no function calling) classifies user messages into one of
the defined intents using the last 3 turns of conversation as context.

Intents
-------
product_search       — buscando un producto o consultando stock/precio
faq_informational    — pregunta sobre políticas, envíos, pagos, horarios, etc.
quote_build          — armando / completando un presupuesto
acceptance           — confirmando/aceptando el presupuesto activo
rejection            — rechazando el presupuesto activo
escalation_signal    — quiere hablar con un humano / situación que requiere derivar
off_topic            — fuera del dominio de la ferretería
ambiguous            — no hay suficiente señal para clasificar con confianza

If confidence < 0.5 the router returns "ambiguous" regardless of the LLM output.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset({
    "product_search",
    "faq_informational",
    "quote_build",
    "acceptance",
    "rejection",
    "escalation_signal",
    "off_topic",
    "ambiguous",
})

_SYSTEM_PROMPT = """\
Sos un clasificador de intenciones para un bot de ventas de ferretería argentina.

Analizá el último mensaje del cliente (y el historial reciente si está disponible) \
y clasificalo en UNA de estas categorías:

- product_search: el cliente busca un producto, consulta stock o precio de algo concreto
- faq_informational: pregunta sobre envíos, pagos, garantía, horarios, factura, cambios, devoluciones
- quote_build: está armando o completando un presupuesto con varios artículos
- acceptance: está confirmando o aceptando el presupuesto que le mostraron
- rejection: rechaza el presupuesto o no quiere seguir con la compra
- escalation_signal: quiere hablar con una persona, reclama, está enojado o la situación requiere atención humana
- off_topic: el mensaje no tiene nada que ver con ferretería ni con la compra
- ambiguous: no hay suficiente información para clasificar con seguridad

Respondé ÚNICAMENTE con un objeto JSON:
{
  "intent": "<categoría>",
  "confidence": <0.0 a 1.0>
}

Reglas:
- Si no estás seguro, poné confidence < 0.5 y usá "ambiguous".
- No respondas nada fuera del JSON.
- El nivel de confianza debe reflejar qué tan claro es el intent, no qué tan probable es.
"""

_CONTEXT_TURN_LIMIT = 3
_MAX_OUTPUT_TOKENS = 150


def _format_history(history: List[Dict[str, str]]) -> str:
    lines = []
    for turn in history:
        role = turn.get("role", "")
        content = str(turn.get("content") or "").strip()
        if role == "user":
            lines.append(f"Cliente: {content}")
        elif role == "assistant":
            lines.append(f"Asistente: {content}")
    return "\n".join(lines)


class IntentRouter:
    """
    Classify a customer message intent before main bot processing.

    Parameters
    ----------
    chatgpt_client:
        An instance of ChatGPTClient (or compatible) with send_message().
    preferred_model:
        Model override — use "gpt-4o-mini" for speed/cost when available.
        Falls back to the client's configured model if this param is None.
    """

    def __init__(
        self,
        chatgpt_client: Any,
        preferred_model: Optional[str] = None,
    ) -> None:
        self._client = chatgpt_client
        self._preferred_model = preferred_model

    def classify(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Classify the user message intent.

        Parameters
        ----------
        message:
            The latest user message.
        history:
            Recent conversation turns (role/content dicts). Only the last
            _CONTEXT_TURN_LIMIT turns are used.

        Returns
        -------
        dict with keys:
            "intent":     one of VALID_INTENTS
            "confidence": float 0.0–1.0
            "source":     "llm" | "fallback"
        """
        if not message or not message.strip():
            return {"intent": "ambiguous", "confidence": 0.0, "source": "fallback"}

        recent = (history or [])[-(_CONTEXT_TURN_LIMIT * 2):]
        history_text = _format_history(recent)

        user_content = message.strip()
        if history_text:
            user_content = f"Historial reciente:\n{history_text}\n\nÚltimo mensaje del cliente: {message.strip()}"
        else:
            user_content = f"Mensaje del cliente: {message.strip()}"

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            result = self._call_llm(messages)
            return result
        except Exception as exc:
            logger.warning(
                "intent_router_llm_failed message_len=%d error=%s",
                len(message),
                exc,
                exc_info=True,
            )
            return {"intent": "ambiguous", "confidence": 0.0, "source": "fallback"}

    def _call_llm(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        # If a preferred model is requested, temporarily override via a patched
        # send_message call. Since ChatGPTClient doesn't support per-call model
        # override, we pass a lightweight wrapper.
        orig_model = getattr(self._client, "model", None)
        orig_max_tokens = getattr(self._client, "max_tokens", None)

        try:
            if self._preferred_model and orig_model != self._preferred_model:
                self._client.model = self._preferred_model
            self._client.max_tokens = _MAX_OUTPUT_TOKENS

            response = self._client.send_message(messages)
        finally:
            # Always restore original settings
            if orig_model is not None:
                self._client.model = orig_model
            if orig_max_tokens is not None:
                self._client.max_tokens = orig_max_tokens

        raw_content = (response.get("content") or "").strip()

        # Strip markdown code fences if present
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
            raw_content = raw_content.strip()

        parsed = json.loads(raw_content)

        intent = str(parsed.get("intent", "ambiguous")).lower()
        if intent not in VALID_INTENTS:
            intent = "ambiguous"

        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        if confidence < 0.5:
            intent = "ambiguous"

        return {"intent": intent, "confidence": confidence, "source": "llm"}
