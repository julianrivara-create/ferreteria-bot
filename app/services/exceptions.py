"""
Service-layer exception classes.
"""


class OpenAIServiceDegradedError(RuntimeError):
    """Raised when OpenAI is degraded and fallback mode should be used."""

    def __init__(self, reason: str, original_error: Exception):
        self.reason = reason
        self.original_error = original_error
        super().__init__(f"{reason}: {original_error}")
