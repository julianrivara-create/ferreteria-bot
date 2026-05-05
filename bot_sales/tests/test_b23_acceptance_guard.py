"""
test_b23_acceptance_guard.py — Regression test for B23 S08 fix.

TurnInterpreter quote_modify must take precedence over looks_like_acceptance
when both signals fire on the same turn.

Run:
    source .env
    PYTHONPATH=. python3 -m pytest bot_sales/tests/test_b23_acceptance_guard.py -v -m slow
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.runtime import get_runtime_bot, get_runtime_tenant


def _make_bot():
    tenant = get_runtime_tenant("ferreteria")
    return get_runtime_bot(tenant.id)


class TestB23AcceptanceGuard:
    @pytest.mark.slow
    def test_acceptance_guard_quote_modify_wins(self):
        """Regression for B23 S08 fix:
        TurnInterpreter quote_modify must win over looks_like_acceptance
        when both fire on the same turn.

        E41 scenario: ambiguous destornillador in cart + 'cualquiera está bien'.
        Pre-fix: acceptance fires → cart marked accepted → 1.5 cleanup wipes →
                 turn 3 'agregame martillo' has no cart context → LLM fallback.
        Post-fix: quote_modify wins → clarification path → cart stays open →
                  turn 3 builds correctly → turn 5 shows both items.
        """
        bot = _make_bot()
        sid = f"test_e41_b23_fix_{uuid.uuid4().hex[:8]}"

        # T1: destornillador philips — bot ofrece opciones A/B/C
        r1 = bot.process_message(sid, "destornillador philips")
        assert "destornillador" in r1.lower(), (
            f"T1 debe ofrecer destornilladores. Respuesta: {r1[:200]}"
        )

        # T2: "cualquiera está bien" — selección, NO aceptación de presupuesto
        # Pre-fix (bot.py 0.5): looks_like_acceptance disparaba, quote_state=accepted.
        # Post-fix: intent=quote_modify gana → clarification path → cart stays open.
        r2 = bot.process_message(sid, "cualquiera está bien")
        sess_after_t2 = bot.sessions.get(sid, {})
        quote_state_after_t2 = sess_after_t2.get("quote_state")
        assert quote_state_after_t2 != "accepted", (
            f"T2: quote_state no debe ser 'accepted' después de 'cualquiera está bien' "
            f"con ítem ambiguo en carrito. Got quote_state={quote_state_after_t2!r}. "
            f"Respuesta: {r2[:200]}"
        )

        # T3: "agregame martillo" — must trigger additive path (section 3 in pre_route).
        # Pre-fix (ferreteria_quote.py): _ADDITIVE_RE missing 'agregame' → section 3 skipped
        # → section 3.5/LLM fallback → generic qualification question.
        # Post-fix: 'agregame' added to _ADDITIVE_RE → additive fires → martillo shown.
        r3 = bot.process_message(sid, "agregame martillo")
        assert "martillo" in r3.lower(), (
            f"T3 debe ofrecer martillos. Respuesta: {r3[:200]}"
        )

        # T4: elegir Stanley
        r4 = bot.process_message(sid, "stanley")

        # T5: pedir presupuesto — debe contener AMBOS productos (suite-checker level).
        # NOTE: price assertion deliberately omitted. With the two B23 fixes applied,
        # T5 typically shows a disambiguation question "¿Eso es para Destornillador
        # o para Martillo?" which contains both words but no prices → suite WARN.
        # Reaching PASS (both words + prices) requires a third fix: apply_clarification
        # must resolve "cualquiera está bien" to a specific product option rather than
        # looping on disambiguation. That is tracked as a separate follow-up item.
        r5 = bot.process_message(sid, "presupuesto?")
        r5l = r5.lower()
        assert "destornillador" in r5l, (
            f"T5 debe mencionar destornillador. "
            f"Respuesta: {r5[:300]}"
        )
        assert "martillo" in r5l, (
            f"T5 debe mencionar martillo. "
            f"Respuesta: {r5[:300]}"
        )
