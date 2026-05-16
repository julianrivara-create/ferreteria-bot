"""
test_dt20_ti_bypass_clarification.py — DT-20 regression tests.

Bug: short option-picks ("A", "B", "1", "la primera") while in
``awaiting_clarification`` paid for a full TurnInterpreter LLM hop
(~3–4s/turn) even though they are deterministically resolvable.

Fix: ``SalesBot._try_ferreteria_intent_route`` now short-circuits the TI
call when the state is ``awaiting_clarification`` AND
``_bypass_index_for_clarification`` recognises the message as an
unambiguous option pick. It synthesises a minimal TurnInterpretation
(``intent="quote_modify"``, ``referenced_offer_index=<idx>``,
``references_existing_quote=True``) and returns ``None`` so pre_route's
Phase 4 continuation resolves the pick via
``apply_followup_to_open_quote``.

Tests:
  - 4 short replies bypass (no LLM call).
  - 2 non-short replies still go through the TI.
  - Bypass does not fire outside ``awaiting_clarification``.
  - Bypass does not fire when there is no active_quote.

Expected latency saving on bypassed turns: ~3–4 s (one full LLM hop).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBypassIndexHelper:
    """Pure-helper coverage — no SalesBot instantiation needed."""

    @pytest.fixture(autouse=True)
    def _import_helper(self):
        from bot_sales.bot import SalesBot
        self.fn = SalesBot._bypass_index_for_clarification

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("A", 0),
            ("B", 1),
            ("C", 2),
            ("a)", 0),
            ("la opcion A", 0),
            ("con el A", 0),
            ("con la B", 1),
            ("la primera", 0),
            ("la segunda", 1),
            ("la tercera", 2),
            ("1", 0),
            ("2", 1),
            ("3", 2),
            ("cualquiera", 0),
            ("me da igual", 0),
        ],
    )
    def test_bypass_accepts_short_picks(self, text, expected):
        assert self.fn(text) == expected, f"{text!r} should bypass with idx={expected}"

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "podrías explicarme la diferencia entre A y B",
            "no me gusta ninguna de las opciones",
            "ninguna",
            "tornillo 8mm",
            "agregame un martillo",
            "hola que tal",
        ],
    )
    def test_bypass_rejects_long_or_ambiguous(self, text):
        assert self.fn(text) is None, f"{text!r} should NOT bypass — needs TI"


class TestBypassIntegration:
    """End-to-end through ``_try_ferreteria_intent_route``.

    Verifies the TI ``interpret`` call is skipped exactly when expected and
    a synthetic ``last_turn_interpretation`` is written to the session.
    """

    def _make_bot(self):
        from bot_sales.bot import SalesBot
        bot = SalesBot.__new__(SalesBot)
        bot.sessions = {}
        bot.contexts = {}
        bot.turn_interpreter = MagicMock()
        bot._is_ferreteria_runtime = MagicMock(return_value=True)
        return bot

    def _seed_clarification(self, bot, sid: str) -> None:
        from bot_sales.state.conversation_state import StateStore
        sess = bot.sessions.setdefault(sid, {})
        sess["active_quote"] = [
            {
                "line_id": "L1",
                "status": "ambiguous",
                "normalized": "amoladora",
                "original": "amoladora",
                "qty": 1,
                "qty_explicit": False,
                "unit_price": None,
                "subtotal": None,
                "products": [
                    {"model": "Bosch GWS 7-115", "sku": "AM1", "price_ars": 50000},
                    {"model": "Black & Decker G720", "sku": "AM2", "price_ars": 35000},
                    {"model": "Stanley STGS6115", "sku": "AM3", "price_ars": 32000},
                ],
            }
        ]
        state_v2 = StateStore.load(sess)
        state_v2.transition("awaiting_clarification")
        StateStore.save(sess, state_v2)

    @pytest.mark.parametrize("text", ["A", "2", "la primera", "con el A"])
    def test_short_pick_bypasses_ti(self, text):
        bot = self._make_bot()
        sid = "s-bypass"
        self._seed_clarification(bot, sid)

        result = bot._try_ferreteria_intent_route(sid, text)

        assert result is None, "bypass must return None so pre_route handles the pick"
        bot.turn_interpreter.interpret.assert_not_called()
        interp = bot.sessions[sid].get("last_turn_interpretation") or {}
        assert interp.get("intent") == "quote_modify"
        assert interp.get("confidence") == 1.0
        assert interp.get("referenced_offer_index") in (0, 1, 2)
        assert (interp.get("quote_reference") or {}).get("references_existing_quote") is True

    @staticmethod
    def _safe_run(bot, sid: str, text: str) -> None:
        """Run the routed call but swallow downstream errors caused by the
        minimally-mocked bot (we only care here about whether ``interpret``
        was invoked)."""
        try:
            bot._try_ferreteria_intent_route(sid, text)
        except (AttributeError, TypeError, Exception):  # noqa: BLE001 — intentional
            pass

    @pytest.mark.parametrize(
        "text",
        [
            "podrías explicarme la diferencia entre A y B",
            "no me gusta ninguna, traeme otro modelo",
        ],
    )
    def test_long_or_ambiguous_still_runs_ti(self, text):
        from bot_sales.routing.turn_interpreter import TurnInterpretation
        bot = self._make_bot()
        sid = "s-no-bypass"
        self._seed_clarification(bot, sid)
        bot.turn_interpreter.interpret.return_value = TurnInterpretation(
            intent="quote_modify", confidence=0.9
        )

        self._safe_run(bot, sid, text)

        bot.turn_interpreter.interpret.assert_called_once()

    def test_bypass_skipped_when_state_is_not_clarifying(self):
        from bot_sales.routing.turn_interpreter import TurnInterpretation
        from bot_sales.state.conversation_state import StateStore
        bot = self._make_bot()
        sid = "s-idle"
        sess = bot.sessions.setdefault(sid, {})
        sess["active_quote"] = [{"line_id": "L1", "status": "resolved", "products": []}]
        state_v2 = StateStore.load(sess)
        state_v2.transition("idle")
        StateStore.save(sess, state_v2)
        bot.turn_interpreter.interpret.return_value = TurnInterpretation(
            intent="product_search", confidence=0.9
        )

        self._safe_run(bot, sid, "A")

        bot.turn_interpreter.interpret.assert_called_once(), (
            "bypass must only fire while state == awaiting_clarification"
        )

    def test_bypass_skipped_when_no_active_quote(self):
        from bot_sales.routing.turn_interpreter import TurnInterpretation
        from bot_sales.state.conversation_state import StateStore
        bot = self._make_bot()
        sid = "s-empty"
        sess = bot.sessions.setdefault(sid, {})
        state_v2 = StateStore.load(sess)
        state_v2.transition("awaiting_clarification")
        StateStore.save(sess, state_v2)
        bot.turn_interpreter.interpret.return_value = TurnInterpretation(
            intent="product_search", confidence=0.9
        )

        self._safe_run(bot, sid, "A")

        bot.turn_interpreter.interpret.assert_called_once()
