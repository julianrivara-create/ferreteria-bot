"""
Handles escalate intent and frustration-triggered handoffs.
Wraps existing ferreteria_escalation.py logic behind a clean interface.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# H3 — Confidence thresholds (documented here for discoverability):
#   TurnInterpretation.is_low_confidence():  < 0.55  (turn_interpreter.py)
#   IntentRouter min confidence:             >= 0.5  (intent_router.py — less strict, it's the fallback)
#   Frustration escalation (below):         >= 0.55  (requires confident signal before acting)
_FRUSTRATION_ESCALATION_THRESHOLD = 0.55


class EscalationHandler:
    def __init__(self, handoff_service=None):
        self.handoff_service = handoff_service

    def handle(
        self,
        session_id: str,
        user_message: str,
        interpretation: Any,  # TurnInterpretation
        state_v2: Any,        # ConversationStateV2
        customer_contact: Optional[str] = None,
    ) -> str:
        """
        Trigger escalation. Updates state_v2 to 'escalated'.
        Returns a natural response to send to the customer.
        """
        reason = self._infer_reason(interpretation)

        state_v2.transition("escalated")
        state_v2.escalation_status = reason

        # Try to create a handoff record if service is available
        if self.handoff_service:
            try:
                handoff_id = self.handoff_service.create_handoff(
                    session_id=session_id,
                    reason=reason,
                    contact=customer_contact,
                    message=user_message,
                )
                state_v2.handoff_id = str(handoff_id) if handoff_id else None
            except Exception as exc:
                logger.warning("Handoff service failed: %s", exc)

        return (
            "Claro, te paso con un asesor ahora. "
            "En un momento alguien de nuestro equipo se pone en contacto con vos."
        )

    def should_escalate_on_frustration(self, interpretation: Any) -> bool:
        """Return True if tone signals frustration AND confidence meets threshold."""
        tone = getattr(interpretation, "tone", "neutral")
        confidence = getattr(interpretation, "confidence", 0.0)
        return tone == "frustrated" and confidence >= _FRUSTRATION_ESCALATION_THRESHOLD

    def _infer_reason(self, interpretation: Any) -> str:
        tone = getattr(interpretation, "tone", "neutral")
        intent = getattr(interpretation, "intent", "unknown")
        if intent in ("escalate", "escalation_signal"):
            return "customer_requested"
        if tone == "frustrated":
            return "frustration_detected"
        return "unknown"
