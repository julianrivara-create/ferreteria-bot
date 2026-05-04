"""
Integration tests for the V8 negotiation handoff rule.

No LLM calls — all tests run at commit time.

Run:
    pytest bot_sales/tests/test_handoff_negotiation.py -v
"""
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.services.search_validator import (
    detect_negotiation_intent,
    HANDOFF_NEGOTIATION_RESPONSE,
)
from bot_sales.state.conversation_state import ConversationStateV2, StateStore


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_bot():
    """
    Minimal SalesBot stub for V8 handoff tests.

    Bypasses __init__ entirely and wires only the attributes needed to
    reach the V8 check in process_message without hitting the LLM or DB.
    """
    from bot_sales.bot import SalesBot
    with patch.object(SalesBot, "__init__", lambda s, *a, **kw: None):
        bot = SalesBot.__new__(SalesBot)
    bot.sandbox_mode = True
    bot.tenant_id = "ferreteria"
    bot.tenant_profile = {}
    bot.quote_service = None   # skips _load_active_quote_from_store
    bot.sessions = {}
    bot.contexts = {}
    bot.system_prompt = "sistema test"
    return bot


def _session_with_cart(bot, session_id: str, cart: list) -> None:
    """Pre-populate a session with an open active_quote."""
    sess = {}
    StateStore.save(sess, ConversationStateV2())
    sess["active_quote"] = cart
    sess["quote_state"] = "open"
    bot.sessions[session_id] = sess
    bot.contexts[session_id] = [{"role": "system", "content": "test"}]


# ─── Integration tests ────────────────────────────────────────────────────────

class TestHandoffNegotiation(unittest.TestCase):
    """
    Tests verify that V8 fires pre-LLM, returns the handoff message,
    and leaves the cart (active_quote) untouched.
    """

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_handoff_response_when_negotiation_detected(self, mock_turn, mock_lat):
        """process_message returns HANDOFF_NEGOTIATION_RESPONSE for negotiation input."""
        bot = _make_bot()
        response = bot.process_message("s1", "dame mejor precio")
        self.assertIn("asesor humano", response.lower())
        self.assertIn("precio especial", response.lower())

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_carrito_preserved_after_handoff(self, mock_turn, mock_lat):
        """active_quote must survive the V8 handoff — cart is NOT reset."""
        cart = [{"sku": "TST001", "qty": 2, "product": "Martillo Stanley"}]
        bot = _make_bot()
        _session_with_cart(bot, "s2", cart)

        response = bot.process_message("s2", "me bajás el precio?")

        self.assertEqual(bot.sessions["s2"]["active_quote"], cart)
        self.assertEqual(bot.sessions["s2"]["quote_state"], "open")
        self.assertIn("asesor", response.lower())

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_no_counteroffer_in_response(self, mock_turn, mock_lat):
        """Bot must not offer a specific discount percentage or invented price."""
        bot = _make_bot()
        response = bot.process_message("s3", "hacés descuento?")
        self.assertNotIn("%", response)
        self.assertIsNone(re.search(r'\$[\d.,]+', response))
        self.assertIn("asesor", response.lower())

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    @patch("bot_sales.bot.SalesBot._try_ferreteria_intent_route")
    def test_llm_not_called_on_negotiation(self, mock_llm, mock_turn, mock_lat):
        """V8 must return before _try_ferreteria_intent_route (LLM) is invoked."""
        bot = _make_bot()
        bot.process_message("s4", "15% off?")
        mock_llm.assert_not_called()

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_handoff_fires_for_all_patterns(self, mock_turn, mock_lat):
        """Spot-check: one representative message per pattern."""
        cases = [
            "me hacés un descuento",          # descuento
            "haceme una rebaja",               # rebaja
            "si llevo 100 me bajás?",          # me bajás
            "bajame algo",                     # bajame
            "dame mejor precio",               # mejor precio
            "en otro lado está más barato",    # más barato
            "15% off?",                        # % off
            "te ofrezco $40000 en efectivo",   # te ofrezco
        ]
        for i, msg in enumerate(cases):
            with self.subTest(msg=msg):
                bot = _make_bot()
                response = bot.process_message(f"s_pat_{i}", msg)
                self.assertIn(
                    "asesor",
                    response.lower(),
                    f"Handoff not triggered for: {msg!r}",
                )

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    @patch("bot_sales.bot.SalesBot._try_ferreteria_pre_route", return_value=None)
    @patch("bot_sales.bot.SalesBot._try_ferreteria_intent_route")
    def test_no_handoff_for_price_objection(self, mock_llm, mock_pre, mock_turn, mock_lat):
        """E18/E21 — objeciones informales deben pasar al LLM, no interceptarse en V8."""
        # Mock the rest of the flow so the stub doesn't need knowledge_loader etc.
        mock_llm.return_value = "respuesta LLM de prueba"

        for msg in ("nahh está caro", "está caro, cuánto el último?"):
            with self.subTest(msg=msg):
                bot = _make_bot()
                bot.process_message("s_obj", msg)
                # V8 did NOT short-circuit → intent route was called
                mock_llm.assert_called()
                mock_llm.reset_mock()


if __name__ == "__main__":
    unittest.main()
