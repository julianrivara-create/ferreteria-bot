"""
PolicyService — dynamic per-turn policy retrieval.
Replaces injecting all of policies.md into every system prompt.
"""
from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

POLICY_TOPICS: Dict[str, List[str]] = {
    "horario": ["horario", "hora", "abren", "cierran", "dias", "cuando", "atienden"],
    "envio": ["envio", "envios", "despacho", "retiro", "moto", "flete", "llega", "mandas", "entregan"],
    "garantia": ["garantia", "falla", "defecto", "roto", "no funciona"],
    "factura": ["factura", "facturacion", "iva", "monotributo", "responsable inscripto", "cuit"],
    "devolucion": ["devolucion", "cambio", "devolver", "cambiar", "no sirve", "me arrepenti"],
    "reserva": ["reserva", "hold", "apartar", "minutos", "tiempo", "reservar"],
    "pago": ["pago", "efectivo", "transferencia", "tarjeta", "credito", "debito", "mercadopago", "como pago"],
}

_GUARDRAILS = """GUARDRAILS COMERCIALES (no negociables):
- Nunca inventes precios, stock, medidas, plazos ni condiciones.
- Solo citá políticas que estén en el contexto dado. No agregues condiciones de tu cuenta.
- Si no tenés el dato, decí que lo confirmás y derivá si corresponde.
- No hagas promesas de precios sin tool result asociado.
- Tono: asesor de ferretería argentino, directo y técnico."""


class PolicyService:
    """
    Parses policies.md into sections and serves per-topic snippets dynamically.
    Keeps the global system prompt short (guardrails only).
    """

    def __init__(self, policies_text: str):
        self.policies_text = policies_text or ""
        self._sections: Dict[str, str] = {}
        if self.policies_text:
            self._sections = self._parse_sections(self.policies_text)
        logger.debug("PolicyService loaded %d sections", len(self._sections))

    def _parse_sections(self, text: str) -> Dict[str, str]:
        """Split markdown into sections by header (## or #)."""
        sections: Dict[str, str] = {}
        current_header = "general"
        current_lines: List[str] = []

        for line in text.splitlines():
            if re.match(r"^#{1,3}\s", line):
                if current_lines:
                    sections[current_header] = "\n".join(current_lines).strip()
                current_header = re.sub(r"^#+\s*", "", line).strip().lower()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            sections[current_header] = "\n".join(current_lines).strip()

        return sections

    def get_snippet_for_topic(self, topic: str) -> Optional[str]:
        """Return the most relevant policy section for a topic keyword."""
        if not topic or not self._sections:
            return None

        topic = topic.lower().strip()

        # Direct key match
        for key, content in self._sections.items():
            if topic in key or key in topic:
                return content

        # Keyword match using POLICY_TOPICS
        keywords = POLICY_TOPICS.get(topic, [topic])
        best_key: Optional[str] = None
        best_score = 0

        for key, content in self._sections.items():
            combined = (key + " " + content).lower()
            score = sum(1 for kw in keywords if kw in combined)
            if score > best_score:
                best_score = score
                best_key = key

        return self._sections.get(best_key) if best_key else None

    def get_guardrails_prompt(self) -> str:
        """Short guardrails for inclusion in every prompt (replaces full policies.md)."""
        return _GUARDRAILS

    def build_turn_policy_context(self, topic: Optional[str] = None) -> str:
        """Build a short, topic-specific policy block for a single turn."""
        guardrails = self.get_guardrails_prompt()
        if not topic:
            return guardrails
        snippet = self.get_snippet_for_topic(topic)
        if snippet:
            return f"{guardrails}\n\nPOLÍTICA RELEVANTE ({topic.upper()}):\n{snippet}"
        return guardrails

    def infer_topic_from_message(self, message: str) -> Optional[str]:
        """Heuristic: detect policy topic from raw user message."""
        msg = message.lower()
        best_topic: Optional[str] = None
        best_score = 0
        for topic, keywords in POLICY_TOPICS.items():
            score = sum(1 for kw in keywords if kw in msg)
            if score > best_score:
                best_score = score
                best_topic = topic
        return best_topic if best_score > 0 else None
