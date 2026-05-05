"""
test_b22a_compound_modify.py — Regression tests for B22a compound modify handler.

TurnInterpretation gains sub_commands field; bot.py processes compound quote_modify
turns by dispatching each sub-command sequentially without a second LLM call.

Fast tests (no LLM):
    pytest bot_sales/tests/test_b22a_compound_modify.py -v -m "not slow"

Slow test (LLM real):
    source .env
    PYTHONPATH=. pytest bot_sales/tests/test_b22a_compound_modify.py -v -m slow
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.routing.turn_interpreter import TurnInterpretation


# ---------------------------------------------------------------------------
# Fast unit tests — TurnInterpretation schema
# ---------------------------------------------------------------------------


class TestSubCommandsField:
    def test_default_empty(self):
        """TurnInterpretation.unknown() must have sub_commands=[]."""
        ti = TurnInterpretation.unknown()
        assert ti.sub_commands == []

    def test_default_factory_not_shared(self):
        """Each instance gets its own list — no shared default mutable."""
        ti1 = TurnInterpretation()
        ti2 = TurnInterpretation()
        ti1.sub_commands.append("x")
        assert ti2.sub_commands == []

    def test_round_trip(self):
        """to_dict/from_dict round-trip preserves sub_commands."""
        ti = TurnInterpretation(
            intent="quote_modify",
            compound_message=True,
            sub_commands=["dame el primero", "agregame martillo"],
        )
        d = ti.to_dict()
        ti2 = TurnInterpretation.from_dict(d)
        assert ti2.sub_commands == ["dame el primero", "agregame martillo"]
        assert ti2.compound_message is True
        assert ti2.intent == "quote_modify"

    def test_defensive_coercion_not_a_list(self):
        """Non-list sub_commands -> empty list."""
        ti = TurnInterpretation.from_dict({"sub_commands": "not a list"})
        assert ti.sub_commands == []

    def test_defensive_coercion_non_string_elements(self):
        """List with non-string elements -> filtered to strings only."""
        ti = TurnInterpretation.from_dict({"sub_commands": [1, 2, 3]})
        assert ti.sub_commands == []  # no strings remain after filter

    def test_defensive_coercion_mixed_elements(self):
        """Mixed list -> keeps only str elements."""
        ti = TurnInterpretation.from_dict({"sub_commands": ["ok", 99, None, "también"]})
        assert ti.sub_commands == ["ok", "también"]

    def test_defensive_coercion_truncated_at_5(self):
        """Lists longer than 5 elements are truncated."""
        ti = TurnInterpretation.from_dict({"sub_commands": ["a"] * 10})
        assert len(ti.sub_commands) == 5

    def test_missing_field_backward_compat(self):
        """TI dict without sub_commands -> empty list (backward compatibility)."""
        ti = TurnInterpretation.from_dict({"intent": "quote_modify"})
        assert ti.sub_commands == []

    def test_sub_commands_in_to_dict(self):
        """sub_commands key must be present in to_dict() output."""
        ti = TurnInterpretation(sub_commands=["a", "b"])
        d = ti.to_dict()
        assert "sub_commands" in d
        assert d["sub_commands"] == ["a", "b"]


# ---------------------------------------------------------------------------
# Fast unit test — atomicity of compound fallback
# ---------------------------------------------------------------------------


class TestCompoundFallbackAtomicity:
    """Verify that a failed compound modify restores the original cart."""

    @staticmethod
    def _make_cart() -> List[Dict[str, Any]]:
        return [
            {
                "line_id": "aaa111",
                "original": "destornillador philips",
                "normalized": "destornillador philips",
                "qty": 1,
                "status": "ambiguous",
                "products": [
                    {"sku": "D001", "model": "Dest PH1 Bahco", "price_ars": 5000},
                    {"sku": "D002", "model": "Dest PH2 Stanley", "price_ars": 6000},
                ],
            }
        ]

    def test_compound_fallback_preserves_original_cart(self):
        """If a sub-command fails (opt_idx out of range), the cart must be
        restored to its pre-compound state — no partial modifications."""
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)

        sid = f"test_b22a_atom_{uuid.uuid4().hex[:8]}"
        original_cart = self._make_cart()
        bot.sessions[sid] = {
            "active_quote": list(original_cart),
            "quote_state": "open",
        }

        # sub_cmd[0] = "dame el primero" -> opt_idx=0, within range -> would succeed
        # sub_cmd[1] = "dame el decimo"  -> opt_idx=None (not recognized) -> fails
        # After the fallback, cart must be identical to original_cart.
        interp = TurnInterpretation(
            intent="quote_modify",
            confidence=0.9,
            compound_message=True,
            sub_commands=["dame el primero", "dame el decimo"],
        )

        sess = bot.sessions[sid]
        knowledge = bot._knowledge()
        result = bot._process_compound_modify(
            sid, interp, "dame el primero, dame el decimo", sess, knowledge
        )

        assert result is None, "Should return None (fallback) when a sub-command fails"
        restored = sess.get("active_quote") or []
        assert len(restored) == len(original_cart), (
            f"Cart size changed after fallback: {len(restored)} vs {len(original_cart)}"
        )
        assert restored[0]["status"] == "ambiguous", (
            f"Cart item was modified despite fallback: {restored[0]['status']}"
        )
        assert restored[0]["line_id"] == "aaa111", "line_id changed after fallback"


# ---------------------------------------------------------------------------
# Slow E2E test — full LLM flow
# ---------------------------------------------------------------------------


class TestB22aCompoundModifyE2E:
    @pytest.mark.slow
    def test_compound_modify_e2e(self):
        """Cliente compone presupuesto en un turno con dos comandos.

        T1: 'destornillador philips' -> bot offers options
        T2: 'dame el primero y agregame martillo' -> compound: dest resolved + martillo added
        T3: 'stanley' -> martillo clarification
        T4: 'presupuesto?' -> final quote shows dest + martillo + prices

        Pre-B22a: T2 processes only the additive part (martillo), ignores
                  'dame el primero' -> destornillador stays ambiguous.
        Post-B22a: T2 resolves destornillador (sub_cmd[0]) AND adds martillo
                   (sub_cmd[1]) in one turn.
        """
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)
        sid = f"test_b22a_e2e_{uuid.uuid4().hex[:8]}"

        # T1
        r1 = bot.process_message(sid, "destornillador philips")
        assert "destornillador" in r1.lower(), (
            f"T1 debe ofrecer destornilladores. Got: {r1[:200]}"
        )

        # T2 — compound: option selection + additive in one turn
        r2 = bot.process_message(sid, "dame el primero y agregame martillo")
        r2l = r2.lower()
        # Martillo must be acknowledged (additive sub-command)
        assert "martillo" in r2l, f"T2: martillo debe aparecer en respuesta. Got: {r2[:300]}"
        # Cart must contain both items
        sess_t2 = bot.sessions.get(sid, {})
        aq_t2 = sess_t2.get("active_quote") or []
        assert len(aq_t2) >= 2, (
            f"T2: carrito debe tener dest + martillo (>=2 items). Got: {aq_t2}"
        )

        # T3
        bot.process_message(sid, "stanley")

        # T4 — final quote must show both products + at least one price
        r4 = bot.process_message(sid, "presupuesto?")
        r4l = r4.lower()
        assert "destornillador" in r4l, f"T4 debe mencionar destornillador. Got: {r4[:300]}"
        assert "martillo" in r4l, f"T4 debe mencionar martillo. Got: {r4[:300]}"
        assert "$" in r4 or "precio" in r4l, (
            f"T4 debe mostrar precios. Got: {r4[:300]}"
        )
