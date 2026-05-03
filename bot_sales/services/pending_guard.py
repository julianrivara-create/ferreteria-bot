"""
Guard that detects PENDIENTE placeholder markers in LLM responses and replaces
the full response with a safe fallback message.
"""

import re

_PENDING_PATTERN = re.compile(r"\[PENDIENTE", re.IGNORECASE)

_FALLBACK_MESSAGE = "Dejame consultar ese dato y te confirmo."


def contains_pending_marker(text: str) -> bool:
    """Return True if text contains any [PENDIENTE...] placeholder."""
    return bool(_PENDING_PATTERN.search(text))


def sanitize_response(text: str) -> str:
    """
    If the LLM response contains a PENDIENTE placeholder, replace the entire
    response with the safe fallback. Otherwise return the original text.
    """
    if contains_pending_marker(text):
        return _FALLBACK_MESSAGE
    return text
