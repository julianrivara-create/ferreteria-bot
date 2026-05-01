"""
Handles off_topic and small_talk intents.
Responds naturally without entering the quote or product flow.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_REDIRECT_SUFFIX = (
    "\n\nSi necesitás herramientas, materiales o consultas sobre nuestros productos, "
    "estoy para ayudarte."
)

_SMALL_TALK_RESPONSES = {
    "greeting": "¡Hola! ¿En qué te puedo ayudar hoy?",
    "farewell": "¡Hasta luego! Cualquier cosa que necesites, acá estamos.",
    "thanks": "De nada, para eso estamos. ¿Algo más en lo que te pueda ayudar?",
}


class OfftopicHandler:
    def __init__(self, llm_client=None):
        self.llm = llm_client

    def handle(
        self,
        user_message: str,
        interpretation: Any,
        messages: List[Dict],
        system_prompt: str,
    ) -> str:
        """
        Return a short, natural response that redirects to ferretería topics.
        For small_talk, use canned responses where possible.
        """
        intent = getattr(interpretation, "intent", "off_topic")

        if intent == "small_talk":
            canned = self._canned_small_talk(user_message)
            if canned:
                return canned

        # For off_topic, use LLM with a short redirect instruction
        if self.llm:
            try:
                redirect_messages = [
                    {
                        "role": "system",
                        "content": (
                            "Sos un asistente de ferretería argentina. "
                            "El cliente dijo algo fuera de tema. "
                            "Respondé de forma breve, amable y redirigí al tema de ferretería. "
                            "No más de 2 oraciones."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ]
                response = self.llm.send_message(messages=redirect_messages)
                if isinstance(response, dict):
                    choices = response.get("choices", [])
                    if choices:
                        text = choices[0].get("message", {}).get("content", "")
                    else:
                        text = response.get("content", "") or response.get("text", "")
                    return text if text else self._fallback()
                return str(response) if response else self._fallback()
            except Exception as exc:
                logger.warning("OfftopicHandler LLM failed: %s", exc)

        return self._fallback()

    def _canned_small_talk(self, message: str) -> str:
        msg = message.lower().strip()
        if any(w in msg for w in ["hola", "buenas", "buen dia", "buenas tardes", "hey"]):
            return _SMALL_TALK_RESPONSES["greeting"]
        if any(w in msg for w in ["chau", "adios", "hasta luego", "bye"]):
            return _SMALL_TALK_RESPONSES["farewell"]
        if any(w in msg for w in ["gracias", "gracia", "thanks"]):
            return _SMALL_TALK_RESPONSES["thanks"]
        return ""

    def _fallback(self) -> str:
        return "Ese tema está fuera de lo que manejo." + _REDIRECT_SUFFIX
