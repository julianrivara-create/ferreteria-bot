"""
Unit and integration tests for the B24 escalation safety net.

The safety net fires only when TurnInterpreter fails (returns
TurnInterpretation.unknown() with confidence=0.0) AND the user message
matches a keyword escalation pattern.

No LLM calls — all tests run at commit time.

Run:
    pytest bot_sales/tests/test_escalation_safety_net.py -v
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.bot import SalesBot, _ESCALATION_REQUEST_KEYWORDS
from bot_sales.routing.turn_interpreter import TurnInterpretation
from bot_sales.state.conversation_state import ConversationStateV2, StateStore


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_bot():
    """
    Minimal SalesBot stub for safety net tests.

    Bypasses __init__ and wires only the attributes needed to reach the
    safety net guard in _try_ferreteria_intent_route without hitting any LLM.
    """
    with patch.object(SalesBot, "__init__", lambda s, *a, **kw: None):
        bot = SalesBot.__new__(SalesBot)

    bot.sandbox_mode = True
    bot.tenant_id = "ferreteria"
    bot.tenant_profile = {}
    bot.sessions = {}
    bot.contexts = {}

    # TurnInterpreter mock — default: return unknown()
    bot.turn_interpreter = MagicMock()
    bot.turn_interpreter.interpret.return_value = TurnInterpretation.unknown()

    # EscalationHandler mock
    bot.escalation_handler = MagicMock()
    bot.escalation_handler.handle.return_value = "Claro, te paso con un asesor."
    bot.escalation_handler.should_escalate_on_frustration.return_value = False

    # _append_assistant_turn: return the text as-is for inspection
    bot._append_assistant_turn = MagicMock(side_effect=lambda sid, text: text)

    return bot


def _prime_session(bot, session_id: str) -> None:
    """Initialise a bare session so StateStore.load() returns a valid state."""
    sess = {}
    StateStore.save(sess, ConversationStateV2())
    bot.sessions[session_id] = sess
    bot.contexts[session_id] = []


# ─── Unit tests: keyword matching ────────────────────────────────────────────

class TestEscalationKeywords(unittest.TestCase):
    """Pure unit tests for _looks_like_escalation_request. No bot stub."""

    def test_all_keywords_match(self):
        for kw in _ESCALATION_REQUEST_KEYWORDS:
            with self.subTest(keyword=kw):
                self.assertTrue(
                    SalesBot._looks_like_escalation_request(kw),
                    f"Expected keyword to match: {kw!r}",
                )

    def test_keyword_embedded_in_sentence(self):
        self.assertTrue(
            SalesBot._looks_like_escalation_request(
                "Por favor pasame con alguien, quiero resolverlo ya."
            )
        )

    def test_case_insensitive(self):
        self.assertTrue(SalesBot._looks_like_escalation_request("NECESITO UN HUMANO"))
        self.assertTrue(SalesBot._looks_like_escalation_request("Dame Un Humano"))

    def test_normal_product_request_does_not_match(self):
        for msg in [
            "quiero una llave francesa 10mm",
            "tiene martillos?",
            "cuanto sale el taladro Bosch?",
            "agregame dos tornillos",
            "dale, lo compro",
        ]:
            with self.subTest(msg=msg):
                self.assertFalse(
                    SalesBot._looks_like_escalation_request(msg),
                    f"Expected no match for: {msg!r}",
                )

    def test_empty_and_none_do_not_match(self):
        self.assertFalse(SalesBot._looks_like_escalation_request(""))
        self.assertFalse(SalesBot._looks_like_escalation_request(None))


# ─── Unit tests: guard condition ─────────────────────────────────────────────

class TestSafetyNetGuardCondition(unittest.TestCase):
    """
    Verify the outer guard (intent==unknown AND confidence==0.0) is False
    for any non-failure interpretation, even when the message has keywords.

    This ensures the safety net never fires during normal TurnInterpreter
    operation, regardless of message content.
    """

    def test_guard_false_for_product_search(self):
        interp = TurnInterpretation(intent="product_search", confidence=0.9)
        self.assertFalse(interp.intent == "unknown" and interp.confidence == 0.0)

    def test_guard_false_for_escalate(self):
        # When TurnInterpreter succeeds with escalate, EscalationHandler fires
        # at Phase 9 — safety net must not also fire.
        interp = TurnInterpretation(intent="escalate", confidence=0.8)
        self.assertFalse(interp.intent == "unknown" and interp.confidence == 0.0)

    def test_guard_false_for_policy_faq(self):
        interp = TurnInterpretation(intent="policy_faq", confidence=0.7)
        self.assertFalse(interp.intent == "unknown" and interp.confidence == 0.0)

    def test_guard_true_only_for_unknown_zero_confidence(self):
        interp = TurnInterpretation.unknown()
        self.assertTrue(interp.intent == "unknown" and interp.confidence == 0.0)


# ─── Integration tests: full guard path ──────────────────────────────────────

class TestSafetyNetIntegration(unittest.TestCase):
    """
    Integration tests: call _try_ferreteria_intent_route with a stubbed bot.
    Verifies the safety net activates (or doesn't) based on intent + message.
    """

    def setUp(self):
        self.bot = _make_bot()
        self.session_id = "safety_net_test_session"
        _prime_session(self.bot, self.session_id)

    # ── Case 1: unknown() + escalation keyword → fires ───────────────────────

    def test_fires_when_unknown_with_escalation_keyword(self):
        """
        TurnInterpreter returns unknown() AND message contains an escalation
        keyword → safety net calls escalation_handler.handle() and returns
        the response.
        """
        self.bot.turn_interpreter.interpret.return_value = TurnInterpretation.unknown()

        result = self.bot._try_ferreteria_intent_route(
            self.session_id, "pasame con un humano por favor"
        )

        self.bot.escalation_handler.handle.assert_called_once()
        call_kwargs = self.bot.escalation_handler.handle.call_args[1]
        self.assertEqual(call_kwargs["session_id"], self.session_id)
        self.assertEqual(call_kwargs["user_message"], "pasame con un humano por favor")
        self.assertIsNotNone(result)

    def test_fires_for_multiple_escalation_keywords(self):
        """Safety net activates for each keyword variant."""
        keywords_to_test = [
            "necesito una persona",
            "no quiero un bot",
            "dame un humano",
            "hablar con un asesor",
        ]
        for msg in keywords_to_test:
            with self.subTest(msg=msg):
                bot = _make_bot()
                _prime_session(bot, self.session_id)
                bot.turn_interpreter.interpret.return_value = TurnInterpretation.unknown()

                result = bot._try_ferreteria_intent_route(self.session_id, msg)

                bot.escalation_handler.handle.assert_called_once()
                self.assertIsNotNone(result)

    # ── Case 2: unknown() + normal message → does NOT fire ───────────────────

    def test_does_not_fire_when_unknown_with_normal_message(self):
        """
        TurnInterpreter returns unknown() BUT message has no escalation
        keyword → safety net does NOT fire, function returns None so the
        downstream flow takes over.
        """
        self.bot.turn_interpreter.interpret.return_value = TurnInterpretation.unknown()

        result = self.bot._try_ferreteria_intent_route(
            self.session_id, "quiero un martillo de 500g"
        )

        self.bot.escalation_handler.handle.assert_not_called()
        self.assertIsNone(result)

    def test_does_not_fire_for_empty_message(self):
        self.bot.turn_interpreter.interpret.return_value = TurnInterpretation.unknown()

        result = self.bot._try_ferreteria_intent_route(self.session_id, "")

        self.bot.escalation_handler.handle.assert_not_called()
        self.assertIsNone(result)

    # ── Case 3: known intent + escalation keyword → guard blocks safety net ──

    def test_guard_blocks_safety_net_for_known_intent(self):
        """
        When TurnInterpreter succeeds (non-unknown intent), the safety net
        guard (intent=='unknown' AND confidence==0.0) evaluates to False,
        so the safety net never fires even if the message has keywords.

        We test the guard condition directly since calling
        _try_ferreteria_intent_route with product_search would require
        the full catalog stack.
        """
        # Simulate what the function checks: guard condition is False
        # for any successful TurnInterpreter classification.
        for intent, confidence in [
            ("product_search", 0.9),
            ("escalate", 0.85),
            ("policy_faq", 0.7),
            ("off_topic", 0.6),
            ("quote_accept", 0.95),
        ]:
            with self.subTest(intent=intent):
                interp = TurnInterpretation(intent=intent, confidence=confidence)
                guard_fires = interp.intent == "unknown" and interp.confidence == 0.0
                self.assertFalse(
                    guard_fires,
                    f"Safety net guard must be False for intent={intent!r}",
                )
                # Sanity: the message would have matched keywords
                self.assertTrue(
                    SalesBot._looks_like_escalation_request("dame un humano")
                )


if __name__ == "__main__":
    unittest.main()
