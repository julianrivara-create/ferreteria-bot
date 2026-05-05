"""
test_b23_fu_option_selection.py — Regression tests for B23-FU fix.

detect_option_selection extended with generic-selection phrases.
apply_followup_to_open_quote gate loosened for single-pending-item case.

Fast tests (no LLM):
    pytest bot_sales/tests/test_b23_fu_option_selection.py -v -m "not slow"

Slow test (LLM real):
    source .env
    PYTHONPATH=. pytest bot_sales/tests/test_b23_fu_option_selection.py -v -m slow
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import detect_option_selection


class TestDetectOptionSelection:
    def test_generic_cualquiera(self):
        assert detect_option_selection("cualquiera está bien") == 0

    def test_generic_me_da_igual(self):
        assert detect_option_selection("me da igual") == 0

    def test_generic_da_igual(self):
        assert detect_option_selection("da igual") == 0

    def test_generic_el_que_sea(self):
        assert detect_option_selection("el que sea") == 0

    def test_option_letters_still_work(self):
        assert detect_option_selection("opción A") == 0
        assert detect_option_selection("la C") == 2
        assert detect_option_selection("B") == 1

    def test_ordinals_still_work(self):
        assert detect_option_selection("el primero") == 0
        assert detect_option_selection("el segundo") == 1
        assert detect_option_selection("tercero") == 2

    def test_unrelated_text_returns_none(self):
        assert detect_option_selection("agregame martillo") is None
        assert detect_option_selection("presupuesto?") is None
        assert detect_option_selection("stanley") is None


class TestS08E41FullFlow:
    @pytest.mark.slow
    def test_s08_e41_full_flow_with_generic_selection(self):
        """Regression for B23-FU: 5-turn E41 flow with 'cualquiera está bien'
        must resolve cart and show priced quote at T5.

        Pre-fix: T2 'cualquiera está bien' left destornillador ambiguous →
                 T4 disambiguation loop → T5 shows disambiguation, no prices.
        Post-fix: T2 resolves destornillador → T4 resolves martillo →
                  T5 shows both products with prices → PASS.
        """
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)
        sid = f"test_s08_fu_{uuid.uuid4().hex[:8]}"

        # T1
        r1 = bot.process_message(sid, "destornillador philips")
        assert "destornillador" in r1.lower(), f"T1 debe ofrecer destornilladores. Got: {r1[:200]}"

        # T2 — generic selection, must resolve the destornillador
        r2 = bot.process_message(sid, "cualquiera está bien")
        sess_t2 = bot.sessions.get(sid, {})
        aq_t2 = sess_t2.get("active_quote") or []
        dest_item = next((it for it in aq_t2 if "destornillador" in str(it.get("normalized", "")).lower()), None)
        assert dest_item is not None, f"T2: destornillador debe estar en el carrito. Cart: {aq_t2}"
        assert dest_item.get("status") == "resolved", (
            f"T2: destornillador debe quedar 'resolved' después de 'cualquiera está bien'. "
            f"Got status={dest_item.get('status')!r}. Response: {r2[:200]}"
        )

        # T3
        r3 = bot.process_message(sid, "agregame martillo")
        assert "martillo" in r3.lower(), f"T3 debe ofrecer martillos. Got: {r3[:200]}"

        # T4
        bot.process_message(sid, "stanley")

        # T5 — must show both products with prices
        r5 = bot.process_message(sid, "presupuesto?")
        r5l = r5.lower()
        assert "destornillador" in r5l, f"T5 debe mencionar destornillador. Got: {r5[:300]}"
        assert "martillo" in r5l, f"T5 debe mencionar martillo. Got: {r5[:300]}"
        assert "$" in r5 or "precio" in r5l, (
            f"T5 debe mostrar precios (ambos items resueltos). Got: {r5[:300]}"
        )
