"""
test_b22c_compound_mixed.py — Regression tests for B22c compound accept+info handler.

B22c-min scope: intent=quote_accept + compound_message=true + sub_commands include
at least one customer_info phrase (shipping zone, name, phone, billing). Handler stores
customer_delivery_info.raw in sess and triggers acceptance without a second LLM call.

Fast tests (no LLM):
    pytest bot_sales/tests/test_b22c_compound_mixed.py -v -m "not slow"

Slow test (LLM real):
    source .env
    PYTHONPATH=. pytest bot_sales/tests/test_b22c_compound_mixed.py -v -m slow
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.routing.turn_interpreter import TurnInterpretation


# ---------------------------------------------------------------------------
# Fast unit tests — looks_like_customer_info
# ---------------------------------------------------------------------------


class TestLooksLikeCustomerInfo:
    def test_shipping_zone(self):
        from bot_sales.ferreteria_quote import looks_like_customer_info
        assert looks_like_customer_info("mandalo a Quilmes")
        assert looks_like_customer_info("envialo a Buenos Aires")

    def test_customer_name(self):
        from bot_sales.ferreteria_quote import looks_like_customer_info
        assert looks_like_customer_info("soy Juan")
        assert looks_like_customer_info("me llamo García")

    def test_billing(self):
        from bot_sales.ferreteria_quote import looks_like_customer_info
        assert looks_like_customer_info("factura a Pérez SA")
        assert looks_like_customer_info("a nombre de García")

    def test_phone(self):
        from bot_sales.ferreteria_quote import looks_like_customer_info
        assert looks_like_customer_info("mi número es 5555")
        assert looks_like_customer_info("mi cel es 11-1234")

    def test_false_negatives_acceptance_phrases(self):
        from bot_sales.ferreteria_quote import looks_like_customer_info
        assert not looks_like_customer_info("me llevo todo")
        assert not looks_like_customer_info("cerralo")
        assert not looks_like_customer_info("dale")

    def test_false_negatives_product_phrases(self):
        from bot_sales.ferreteria_quote import looks_like_customer_info
        assert not looks_like_customer_info("agregame martillo")
        assert not looks_like_customer_info("zona industrial")
        assert not looks_like_customer_info("factura A")
        assert not looks_like_customer_info("factura B")


# ---------------------------------------------------------------------------
# Fast unit test — compound handler with mocked TI (isolates handler from LLM)
# ---------------------------------------------------------------------------


class TestCompoundMixedHandlerMockedTI:
    @staticmethod
    def _make_resolved_cart() -> List[Dict[str, Any]]:
        return [
            {
                "line_id": f"dest_{uuid.uuid4().hex[:8]}",
                "original": "destornillador philips",
                "normalized": "destornillador philips",
                "qty": 1,
                "status": "resolved",
                "products": [{"sku": "D001", "model": "Dest PH1 Bahco", "price_ars": 5000}],
                "unit_price": 5000.0,
                "subtotal": 5000.0,
            }
        ]

    def test_handler_stores_info_and_returns_acceptance_response(self):
        """_process_compound_mixed with mock interpretation:
        - Identifies 'mandalo a Quilmes' as info_cmd
        - Stores it in sess['customer_delivery_info']['raw']
        - Returns a non-empty acceptance response
        """
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)

        sid = f"test_b22c_mock_{uuid.uuid4().hex[:8]}"
        cart = self._make_resolved_cart()
        bot.sessions[sid] = {
            "active_quote": list(cart),
            "quote_state": "open",
        }

        interp = TurnInterpretation(
            intent="quote_accept",
            confidence=0.9,
            compound_message=True,
            sub_commands=["me llevo todo", "mandalo a Quilmes"],
        )

        sess = bot.sessions[sid]
        knowledge = bot._knowledge()

        result = bot._process_compound_mixed(
            sid, interp, "me llevo todo y mandalo a Quilmes", sess, knowledge
        )

        assert result is not None, "Handler must return a response string, not None"
        assert len(result) > 0, "Response must not be empty"

        delivery = sess.get("customer_delivery_info") or {}
        assert "mandalo a Quilmes" in delivery.get("raw", ""), (
            f"customer_delivery_info.raw must contain 'mandalo a Quilmes'. "
            f"Got: {delivery!r}"
        )

    def test_handler_returns_none_when_no_info_cmds(self):
        """If no sub-command matches looks_like_customer_info → handler returns None
        (signals fallback to pre_route acceptance path)."""
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)

        sid = f"test_b22c_noop_{uuid.uuid4().hex[:8]}"
        cart = self._make_resolved_cart()
        bot.sessions[sid] = {
            "active_quote": list(cart),
            "quote_state": "open",
        }

        interp = TurnInterpretation(
            intent="quote_accept",
            confidence=0.9,
            compound_message=True,
            sub_commands=["me llevo todo", "cerralo"],
        )

        sess = bot.sessions[sid]
        result = bot._process_compound_mixed(
            sid, interp, "me llevo todo y cerralo", sess, bot._knowledge()
        )

        assert result is None, (
            "Handler with no info sub-commands must return None (fallback)"
        )
        assert "customer_delivery_info" not in sess, (
            "No customer_delivery_info must be set when handler returns None"
        )

    def test_handler_appends_not_overwrites_existing_info(self):
        """If customer_delivery_info already has data, new info is appended."""
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)

        sid = f"test_b22c_append_{uuid.uuid4().hex[:8]}"
        cart = self._make_resolved_cart()
        bot.sessions[sid] = {
            "active_quote": list(cart),
            "quote_state": "open",
            "customer_delivery_info": {"raw": "soy Juan"},
        }

        interp = TurnInterpretation(
            intent="quote_accept",
            confidence=0.9,
            compound_message=True,
            sub_commands=["cerralo", "mandalo a Quilmes"],
        )

        sess = bot.sessions[sid]
        result = bot._process_compound_mixed(
            sid, interp, "cerralo y mandalo a Quilmes", sess, bot._knowledge()
        )

        if result is not None:
            raw = sess.get("customer_delivery_info", {}).get("raw", "")
            assert "soy Juan" in raw, f"Previous info must be preserved. Got: {raw!r}"
            assert "mandalo a Quilmes" in raw, f"New info must be appended. Got: {raw!r}"


# ---------------------------------------------------------------------------
# Fast test — fallback on unsupported combinations
# ---------------------------------------------------------------------------


class TestCompoundMixedFallback:
    def test_no_sub_commands_returns_none(self):
        """Empty sub_commands → handler returns None."""
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)
        sid = f"test_b22c_nosc_{uuid.uuid4().hex[:8]}"
        bot.sessions[sid] = {"active_quote": [{"line_id": f"x_{uuid.uuid4().hex[:8]}", "status": "resolved"}]}

        interp = TurnInterpretation(
            intent="quote_accept",
            confidence=0.9,
            compound_message=True,
            sub_commands=[],
        )
        result = bot._process_compound_mixed(
            sid, interp, "cerralo", bot.sessions[sid], bot._knowledge()
        )
        assert result is None


# ---------------------------------------------------------------------------
# Slow E2E test — full LLM flow
# ---------------------------------------------------------------------------


class TestB22cCompoundAcceptE2E:
    @pytest.mark.slow
    def test_compound_accept_with_shipping_zone(self):
        """B22c regression: 'me llevo todo y mandalo a Quilmes' must close the
        sale AND capture the delivery zone in sess in one turn.

        T1: 'destornillador philips' → bot offers options
        T2: 'el primero'             → resolves destornillador
        T3: 'me llevo todo y mandalo a Quilmes' → compound accept+info
              → response acknowledges closing the sale
              → sess['customer_delivery_info']['raw'] contains 'Quilmes'
              → cart remains intact (1 resolved item)

        Pre-B22c: T3 processes only the accept part; shipping zone lost.
        Post-B22c: T3 stores delivery info AND closes the sale in one turn.
        """
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant

        tenant = get_runtime_tenant("ferreteria")
        bot = get_runtime_bot(tenant.id)
        sid = f"test_b22c_e2e_{uuid.uuid4().hex[:8]}"

        # T1
        r1 = bot.process_message(sid, "destornillador philips")
        assert "destornillador" in r1.lower(), (
            f"T1 debe ofrecer destornilladores. Got: {r1[:200]}"
        )

        # T2 — resolve to first option
        bot.process_message(sid, "el primero")
        sess_t2 = bot.sessions.get(sid, {})
        aq_t2 = sess_t2.get("active_quote") or []
        dest = next(
            (it for it in aq_t2 if "destornillador" in str(it.get("normalized", "")).lower()),
            None,
        )
        assert dest is not None, f"T2: destornillador debe estar en carrito. Cart: {aq_t2}"
        assert dest.get("status") == "resolved", (
            f"T2: destornillador debe quedar resolved. Got: {dest.get('status')!r}"
        )

        # T3 — compound: accept + customer info in one turn
        r3 = bot.process_message(sid, "me llevo todo y mandalo a Quilmes")
        r3l = r3.lower()

        # Response must acknowledge acceptance (one of: confirm, cerramos, pedido, etc.)
        acceptance_signals = ["confirm", "cerram", "pedido", "presupuesto", "listo", "perfect"]
        assert any(sig in r3l for sig in acceptance_signals), (
            f"T3: respuesta debe reconocer cierre de venta. Got: {r3[:300]}"
        )

        # Customer delivery info must be stored in sess
        sess_t3 = bot.sessions.get(sid, {})
        delivery = sess_t3.get("customer_delivery_info") or {}
        raw = delivery.get("raw", "")
        assert "quilmes" in raw.lower(), (
            f"T3: 'Quilmes' debe estar en customer_delivery_info.raw. "
            f"Got delivery={delivery!r}. Response: {r3[:300]}"
        )

        # Cart must still have the resolved destornillador
        aq_t3 = sess_t3.get("active_quote") or []
        assert len(aq_t3) >= 1, f"T3: carrito no debe estar vacío. Got: {aq_t3}"
