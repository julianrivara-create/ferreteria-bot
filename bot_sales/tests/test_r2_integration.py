"""
test_r2_integration.py — Integration tests for R2 price validation wired in bot.py.

Tests that _chat_with_functions correctly logs hallucinated prices and does
NOT log when prices match the catalog. No actual LLM calls are made.
"""
import logging
from unittest.mock import MagicMock, patch
import pytest


def _make_bot_with_catalog(catalog_prices: list, session_id: str = "sess1"):
    """
    Build a minimal SalesBot instance with:
    - last_catalog_result seeded with given prices (Fuente A)
    - mocked chatgpt, contexts, sessions
    """
    from bot_sales.bot import SalesBot

    bot = SalesBot.__new__(SalesBot)
    bot.tenant_id = "ferreteria"
    bot.chatgpt = MagicMock()
    bot.functions = []
    bot.contexts = {
        session_id: [{"role": "user", "content": "¿cuánto cuesta?"}]
    }
    candidates = [{"price_ars": p, "sku": f"SKU{i}"} for i, p in enumerate(catalog_prices)]
    bot.sessions = {
        session_id: {
            "last_catalog_result": {
                "status": "resolved",
                "candidates": candidates,
            }
        }
    }
    bot._set_last_turn_meta = MagicMock()
    return bot


def _mock_direct_response(content: str) -> dict:
    """chatgpt.send_message return value for a direct (no function call) response."""
    return {
        "content": content,
        "meta": {"used_fallback": False, "model": "gpt-4o", "prompt_tokens": 10,
                 "completion_tokens": 5, "total_tokens": 15, "latency_ms": 100,
                 "response_mode": "direct"},
    }


class TestR2Integration:
    def test_no_log_when_response_matches_catalog(self, caplog):
        """No warning when LLM mentions a price that exists in catalog."""
        bot = _make_bot_with_catalog([12500], "sess1")
        bot.chatgpt.send_message.return_value = _mock_direct_response(
            "El taladro cuesta $12.500, está disponible."
        )

        with caplog.at_level(logging.WARNING, logger="bot_sales.bot"):
            result = bot._chat_with_functions("sess1")

        assert result == "El taladro cuesta $12.500, está disponible."
        hallucination_logs = [r for r in caplog.records if "hallucinated_prices_detected" in r.message]
        assert hallucination_logs == [], "Should not log hallucination for catalog price"

    def test_log_when_response_has_hallucinated_price(self, caplog):
        """Warning is logged when LLM mentions a price not in catalog."""
        bot = _make_bot_with_catalog([12500], "sess1")
        bot.chatgpt.send_message.return_value = _mock_direct_response(
            "Ese producto anda por $99000 más o menos."
        )

        with caplog.at_level(logging.WARNING, logger="bot_sales.bot"):
            result = bot._chat_with_functions("sess1")

        assert result == "Ese producto anda por $99000 más o menos."
        hallucination_logs = [r for r in caplog.records if "hallucinated_prices_detected" in r.message]
        assert len(hallucination_logs) == 1

    def test_log_includes_response_preview(self, caplog):
        """The WARNING log message contains a preview of the response."""
        bot = _make_bot_with_catalog([12500], "sess1")
        response_text = "El producto especial vale $88000 en nuestro catálogo."
        bot.chatgpt.send_message.return_value = _mock_direct_response(response_text)

        with caplog.at_level(logging.WARNING, logger="bot_sales.bot"):
            bot._chat_with_functions("sess1")

        hall_log = next(
            (r for r in caplog.records if "hallucinated_prices_detected" in r.message), None
        )
        assert hall_log is not None
        assert response_text[:50] in hall_log.message

    def test_log_includes_session_id(self, caplog):
        """The WARNING log message includes the session_id."""
        session_id = "test_session_xyz"
        bot = _make_bot_with_catalog([12500], session_id)
        bot.chatgpt.send_message.return_value = _mock_direct_response(
            "Le sale $55000 el producto."
        )

        with caplog.at_level(logging.WARNING, logger="bot_sales.bot"):
            bot._chat_with_functions(session_id)

        hall_log = next(
            (r for r in caplog.records if "hallucinated_prices_detected" in r.message), None
        )
        assert hall_log is not None
        assert session_id in hall_log.message

    def test_fuente_b_price_not_flagged(self, caplog):
        """
        Price from LLM's own buscar_stock call (Fuente B) is not flagged.

        Sequence:
          Turn 1: LLM calls buscar_stock → gets product at $7500
          Turn 2: LLM mentions $7500 in free-text response
          Expected: NO hallucination warning (price was legitimately seen).
        """
        bot = _make_bot_with_catalog([], "sess1")  # empty Fuente A

        # Simulate two send_message calls:
        # First → function call for buscar_stock
        # Second → direct response mentioning the price from buscar_stock
        first_call = {
            "function_call": {
                "name": "buscar_stock",
                "arguments": {"modelo": "taladro"},
            }
        }
        second_call = _mock_direct_response("Encontré el taladro a $7.500, disponible.")

        bot.chatgpt.send_message.side_effect = [first_call, second_call]

        # Mock _execute_function to return the product
        bot._execute_function = MagicMock(return_value={
            "status": "found",
            "products": [{"sku": "TAL001", "price_ars": 7500, "price_formatted": "$7.500"}],
        })
        bot._slim_function_result = MagicMock(return_value={
            "status": "found",
            "products": [{"sku": "TAL001", "price_ars": 7500}],
        })

        with caplog.at_level(logging.WARNING, logger="bot_sales.bot"):
            result = bot._chat_with_functions("sess1")

        assert result == "Encontré el taladro a $7.500, disponible."
        hallucination_logs = [r for r in caplog.records if "hallucinated_prices_detected" in r.message]
        assert hallucination_logs == [], "Fuente B price should not be flagged as hallucinated"
