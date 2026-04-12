import structlog
import time

from app.bot.core.fallback import get_fallback_service

logger = structlog.get_logger()


class SimpleFallbackBot:
    """Fallback backed by the offline FAQ catalog (tenant-aware)."""

    def process_message(self, session_id: str, text: str, tenant_id: str = "") -> str:
        del session_id
        text = text if isinstance(text, str) else str(text or "")
        service = get_fallback_service(tenant_id=tenant_id)
        response = service.get_response(text)
        if response:
            return response
        return (
            "Disculpa, tengo conectividad limitada en este momento. "
            "Podés consultar por envíos, pagos, garantía o escribir 'asesor' para atención humana."
        )


class BotCore:
    _bot_instance = None
    _fallback_bot = None
    _init_failed = False
    _init_error = None
    _last_init_attempt = 0.0
    _init_retry_seconds = 30

    @classmethod
    def get_bot(cls):
        if cls._bot_instance is not None:
            return cls._bot_instance
        now = time.time()
        if cls._init_failed and (now - cls._last_init_attempt) < cls._init_retry_seconds:
            return None
        cls._last_init_attempt = now

        try:
            from app.bot.bot import SalesBot

            cls._bot_instance = SalesBot()
            cls._init_failed = False
            cls._init_error = None

            # Detect mock mode: bot initialized but without a valid OpenAI API key.
            # In mock mode the bot returns pre-canned responses — not real AI.
            chatgpt = getattr(cls._bot_instance, "chatgpt", None)
            if chatgpt and getattr(chatgpt, "mock_mode", False):
                logger.critical(
                    "bot_running_in_mock_mode_no_openai_key",
                    message="OPENAI_API_KEY no está configurada. El bot responde con respuestas pre-escritas en lugar de IA real. "
                            "Configurá OPENAI_API_KEY en Railway → ferreteria-bot → Variables.",
                )

            logger.info("bot_core_initialized", bot_type="SalesBot", backend="postgres")
            return cls._bot_instance
        except Exception as e:
            cls._init_failed = True
            cls._init_error = str(e)
            logger.error("bot_initialization_failed", error=cls._init_error, using_fallback=False)
            return None

    @classmethod
    def get_fallback_bot(cls):
        if cls._fallback_bot is None:
            cls._fallback_bot = SimpleFallbackBot()
        return cls._fallback_bot

    @classmethod
    def _unavailable_message(cls) -> str:
        return (
            "Estoy temporalmente fuera de servicio por un problema técnico interno. "
            "Intentá nuevamente en unos minutos."
        )

    @classmethod
    def reply(cls, channel: str, user_id: str, text: str, metadata: dict = None, tenant_id: str = "") -> str:
        result = cls.reply_with_meta(channel, user_id, text, metadata=metadata, tenant_id=tenant_id)
        return str(result.get("content") or "")

    @classmethod
    def reply_with_meta(cls, channel: str, user_id: str, text: str, metadata: dict = None, tenant_id: str = "") -> dict:
        del metadata
        session_id = f"{channel}_{user_id}"
        bot = cls.get_bot()

        if not bot:
            logger.warning("bot_not_ready", init_failed=cls._init_failed, init_error=cls._init_error)
            return {"content": cls._unavailable_message(), "meta": None}

        from app.bot.core.chatgpt import OpenAIServiceDegradedError

        try:
            if hasattr(bot, "process_message_with_meta"):
                return bot.process_message_with_meta(session_id, text)
            return {"content": bot.process_message(session_id, text), "meta": None}
        except OpenAIServiceDegradedError as e:
            logger.warning(
                "openai_degraded_using_fallback",
                reason=e.reason,
                error=str(e.original_error),
            )
            fallback = cls.get_fallback_bot()
            try:
                return {"content": fallback.process_message(session_id, text, tenant_id=tenant_id), "meta": None}
            except Exception as fallback_error:
                logger.error("fallback_bot_error", error=str(fallback_error))
                return {
                    "content": (
                        "Estoy con conectividad limitada en este momento. "
                        "Por favor intentá nuevamente en unos minutos."
                    ),
                    "meta": None,
                }
        except Exception as e:
            logger.error("bot_reply_error_no_fallback", error=str(e))
            return {"content": cls._unavailable_message(), "meta": None}
