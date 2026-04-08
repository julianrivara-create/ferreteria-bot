from __future__ import annotations

from typing import Any, Dict, List


class TrainingContextBuilder:
    """Build compact sandbox context from persisted training messages."""

    def __init__(self, max_replay_messages: int = 14):
        self.max_replay_messages = max_replay_messages

    def build_context(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        session_summary: str | None = None,
    ) -> List[Dict[str, Any]]:
        context: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if session_summary:
            context.append(
                {
                    "role": "system",
                    "content": (
                        "Resumen compacto del entrenamiento anterior para conservar contexto sin inflar tokens:\n"
                        f"{session_summary}"
                    ),
                }
            )
        replay = messages[-self.max_replay_messages :]
        for message in replay:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "")
            if role in {"user", "assistant", "function"} and content:
                payload: Dict[str, Any] = {"role": role, "content": content}
                if role == "function" and message.get("name"):
                    payload["name"] = message["name"]
                context.append(payload)
        return context

