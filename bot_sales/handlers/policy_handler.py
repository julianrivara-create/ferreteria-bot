"""
Handles policy_faq intent. Retrieves relevant policy snippet and composes a response
using the LLM with that snippet as injected context — no global policies.md in prompt.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PolicyHandler:
    def __init__(self, policy_service, llm_client):
        self.policy_service = policy_service
        self.llm = llm_client

    def handle(
        self,
        user_message: str,
        interpretation: Any,  # TurnInterpretation
        messages: List[Dict],
        system_prompt: str,
    ) -> str:
        """
        Build a policy-specific system context and call the LLM.
        Returns the response text.
        """
        topic = getattr(interpretation, "policy_topic", None)
        if not topic:
            topic = self.policy_service.infer_topic_from_message(user_message)

        if not messages:
            logger.warning("PolicyHandler: empty messages context for session")

        policy_ctx = self.policy_service.build_turn_policy_context(topic)

        # Append policy context as a final system reminder — highest recency in attention (H1)
        augmented_messages = list(messages)
        augmented_messages.append({"role": "system", "content": policy_ctx})

        try:
            response = self.llm.send_message(messages=augmented_messages)
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return response.get("content", "") or response.get("text", "")
            return str(response) if response else ""
        except Exception as exc:
            logger.error("PolicyHandler LLM call failed: %s", exc)
            return "No pude acceder a esa información ahora. ¿Podés intentar de nuevo?"
