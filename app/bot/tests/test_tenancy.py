from app.bot.core.chatgpt import OpenAIServiceDegradedError
from app.services.bot_core import BotCore
import time


class _DummyBot:
    def __init__(self, exc):
        self._exc = exc

    def process_message(self, session_id: str, text: str) -> str:
        raise self._exc


class _DummyFallback:
    def __init__(self):
        self.calls = 0

    def process_message(self, session_id: str, text: str, **kwargs) -> str:
        self.calls += 1
        return "fallback-ok"


def _reset_bot_core_state():
    BotCore._bot_instance = None
    BotCore._fallback_bot = None
    BotCore._init_failed = False
    BotCore._init_error = None
    BotCore._last_init_attempt = 0.0


def setup_function():
    _reset_bot_core_state()


def teardown_function():
    _reset_bot_core_state()


def test_botcore_uses_fallback_only_for_openai_degraded():
    fallback = _DummyFallback()
    BotCore._bot_instance = _DummyBot(
        OpenAIServiceDegradedError("insufficient_quota", Exception("quota exceeded"))
    )
    BotCore._fallback_bot = fallback

    response = BotCore.reply("web", "user-1", "hola")

    assert response == "fallback-ok"
    assert fallback.calls == 1


def test_botcore_does_not_fallback_on_internal_errors():
    fallback = _DummyFallback()
    BotCore._bot_instance = _DummyBot(ValueError("db failed"))
    BotCore._fallback_bot = fallback

    response = BotCore.reply("web", "user-1", "hola")

    assert "problema técnico interno" in response.lower()
    assert fallback.calls == 0


def test_botcore_does_not_fallback_when_bot_not_initialized():
    BotCore._init_failed = True
    BotCore._init_error = "database unavailable"
    BotCore._last_init_attempt = time.time()

    response = BotCore.reply("web", "user-1", "hola")

    assert "problema técnico interno" in response.lower()
