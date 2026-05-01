"""
AcceptanceDetector — LLM-based acceptance/rejection classifier.

Primary: single ChatGPT call classifies the user message as accept/reject/none.
Fallback: keyword matching from acceptance_patterns.yaml if the LLM call fails.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Sos un clasificador de intenciones para un bot de ventas de ferretería argentina.

Tu tarea es determinar si el mensaje del cliente acepta, rechaza o no se relaciona \
con el presupuesto activo.

Respondé ÚNICAMENTE con un objeto JSON con estos campos:
- "action": uno de "accept", "reject" o "none"
- "confidence": un número entre 0.0 y 1.0

"accept" → el cliente confirma, acepta o quiere cerrar el presupuesto
           (ej: "dale", "lo quiero", "cerralo", "ok acepto", "confirmalo")
"reject" → el cliente rechaza, cancela o no quiere el presupuesto
           (ej: "no gracias", "lo dejo", "cancel", "no me interesa")
"none"   → el mensaje NO es una respuesta de aceptación o rechazo
           (ej: preguntas, consultas, pedidos de productos, saludos)

No respondas nada más que el JSON.
"""

_USER_TEMPLATE = "Mensaje del cliente: {message}"


def _keyword_fallback(
    message: str,
    patterns: Optional[Dict[str, List[str]]],
) -> Dict[str, Any]:
    """Keyword-based fallback when LLM call fails."""
    if not patterns:
        return {"action": "none", "confidence": 0.0}

    from bot_sales.ferreteria_language import normalize_basic

    norm = normalize_basic(message.strip())

    def _matches(phrase_list: List[str]) -> bool:
        return any(normalize_basic(p) in norm for p in phrase_list if p)

    if _matches(patterns.get("accept_phrases", [])):
        return {"action": "accept", "confidence": 0.85}

    reset_phrases = patterns.get("reset_phrases", []) + patterns.get("new_quote_phrases", [])
    if _matches(reset_phrases):
        return {"action": "reject", "confidence": 0.80}

    return {"action": "none", "confidence": 0.0}


class AcceptanceDetector:
    """
    Classify a customer message as acceptance, rejection, or neither.

    Parameters
    ----------
    chatgpt_client:
        An instance of ChatGPTClient (or compatible object with send_message()).
    acceptance_patterns:
        Keyword patterns loaded from acceptance_patterns.yaml (used as fallback).
    """

    def __init__(
        self,
        chatgpt_client: Any,
        acceptance_patterns: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._client = chatgpt_client
        self._patterns = acceptance_patterns or {}

    def detect(self, message: str) -> Dict[str, Any]:
        """
        Classify message intent.

        Returns
        -------
        dict with keys:
            "action":     "accept" | "reject" | "none"
            "confidence": float 0.0–1.0
            "source":     "llm" | "keyword_fallback"
        """
        if not message or not message.strip():
            return {"action": "none", "confidence": 1.0, "source": "keyword_fallback"}

        try:
            result = self._call_llm(message)
            result["source"] = "llm"
            return result
        except Exception as exc:
            logger.warning(
                "acceptance_detector_llm_failed message_len=%d error=%s — using keyword fallback",
                len(message),
                exc,
                exc_info=True,
            )
            fallback = _keyword_fallback(message, self._patterns)
            fallback["source"] = "keyword_fallback"
            return fallback

    def _call_llm(self, message: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(message=message)},
        ]

        # Prefer a lightweight model; ChatGPTClient picks the configured one.
        response = self._client.send_message(messages)
        raw_content = (response.get("content") or "").strip()

        # Strip markdown code fences if present
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
            raw_content = raw_content.strip()

        parsed = json.loads(raw_content)

        action = str(parsed.get("action", "none")).lower()
        if action not in {"accept", "reject", "none"}:
            action = "none"

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return {"action": action, "confidence": confidence}
