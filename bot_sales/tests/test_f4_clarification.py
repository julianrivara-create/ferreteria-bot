"""
F4 Bug fix — regression tests for detect_option_selection and looks_like_additive.

These tests guard the regex changes introduced to make clarification responses
deterministic: extended option-selection phrases and additional additive verb forms.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
import bot_sales.ferreteria_quote as fq


class TestF4DetectOptionSelection:
    # ── New two-word prefix patterns (D3) ─────────────────────────────────

    def test_la_opcion_A_returns_index_0(self):
        assert fq.detect_option_selection("la opcion A") == 0

    def test_la_opcion_b_lowercase_returns_index_1(self):
        assert fq.detect_option_selection("la opcion b") == 1

    def test_la_opcion_C_returns_index_2(self):
        assert fq.detect_option_selection("la opcion C") == 2

    def test_la_opcion_A_with_tilde_returns_index_0(self):
        assert fq.detect_option_selection("la opción A") == 0

    def test_la_opcion_b_with_tilde_returns_index_1(self):
        assert fq.detect_option_selection("la opción b") == 1

    def test_me_quedo_con_la_A_returns_index_0(self):
        assert fq.detect_option_selection("me quedo con la A") == 0

    def test_me_quedo_con_la_C_returns_index_2(self):
        assert fq.detect_option_selection("me quedo con la C") == 2

    def test_con_la_A_returns_index_0(self):
        assert fq.detect_option_selection("con la A") == 0

    def test_con_la_B_returns_index_1(self):
        assert fq.detect_option_selection("con la B") == 1

    def test_quiero_la_B_returns_index_1(self):
        assert fq.detect_option_selection("quiero la B") == 1

    def test_tomo_la_A_returns_index_0(self):
        assert fq.detect_option_selection("tomo la A") == 0

    def test_dame_la_A_returns_index_0(self):
        assert fq.detect_option_selection("dame la A") == 0

    def test_dame_la_B_returns_index_1(self):
        assert fq.detect_option_selection("dame la B") == 1

    def test_voy_con_la_B_returns_index_1(self):
        assert fq.detect_option_selection("voy con la B") == 1

    def test_elijo_la_C_returns_index_2(self):
        assert fq.detect_option_selection("elijo la C") == 2

    def test_option_in_compound_message_detected(self):
        # "la opcion A. tambien te pido un martillo" — CASO B T2
        assert fq.detect_option_selection("la opcion A. tambien te pido un martillo") == 0

    def test_me_quedo_con_la_B_in_compound_detected(self):
        # "me quedo con la B. cuanto es el total?"
        assert fq.detect_option_selection("me quedo con la B. cuanto es el total?") == 1

    # ── Regressions — existing patterns must still work (D3) ──────────────

    def test_existing_simple_A_still_works(self):
        assert fq.detect_option_selection("A") == 0

    def test_existing_simple_B_still_works(self):
        assert fq.detect_option_selection("B") == 1

    def test_existing_la_A_still_works(self):
        assert fq.detect_option_selection("la A") == 0

    def test_existing_opcion_A_still_works(self):
        assert fq.detect_option_selection("opcion A") == 0

    def test_existing_el_primero_still_works(self):
        assert fq.detect_option_selection("el primero") == 0

    def test_existing_segundo_still_works(self):
        assert fq.detect_option_selection("el segundo") == 1

    def test_existing_cualquiera_still_works(self):
        assert fq.detect_option_selection("cualquiera") == 0

    # ── Negative cases — must NOT match ───────────────────────────────────

    def test_unrelated_phrase_returns_None(self):
        assert fq.detect_option_selection("para madera") is None

    def test_martillo_alone_returns_None(self):
        assert fq.detect_option_selection("un martillo") is None

    def test_letter_f_out_of_range_returns_None(self):
        # F is outside a-e range
        assert fq.detect_option_selection("la opcion F") is None

    def test_additive_phrase_returns_None(self):
        assert fq.detect_option_selection("tambien te pido un martillo") is None

    def test_material_answer_returns_None(self):
        assert fq.detect_option_selection("Para madera, por favor") is None


class TestF4LooksLikeAdditive:
    # ── New additive verb forms (D4) ──────────────────────────────────────

    def test_tambien_te_pido_returns_True(self):
        assert fq.looks_like_additive("tambien te pido un martillo") is True

    def test_tambien_te_pido_with_product_returns_True(self):
        assert fq.looks_like_additive("tambien te pido 2 tornillos") is True

    def test_te_pido_tambien_returns_True(self):
        assert fq.looks_like_additive("te pido también un destornillador") is True

    def test_te_pido_tambien_no_tilde_returns_True(self):
        assert fq.looks_like_additive("te pido tambien una mecha") is True

    def test_tambien_dame_returns_True(self):
        assert fq.looks_like_additive("también dame un martillo") is True

    def test_tambien_dame_no_tilde_returns_True(self):
        assert fq.looks_like_additive("tambien dame brocas") is True

    def test_agregale_tambien_returns_True(self):
        assert fq.looks_like_additive("agregale también una mecha") is True

    def test_sumale_tambien_returns_True(self):
        assert fq.looks_like_additive("sumale también un martillo") is True

    def test_sumale_alone_returns_True(self):
        assert fq.looks_like_additive("sumale un tornillo") is True

    # ── Regressions — existing additive forms must still work (D4) ────────

    def test_existing_tambien_quiero_still_works(self):
        assert fq.looks_like_additive("tambien quiero un martillo") is True

    def test_existing_tambien_necesito_still_works(self):
        assert fq.looks_like_additive("tambien necesito brocas") is True

    def test_existing_agregame_still_works(self):
        assert fq.looks_like_additive("agregame un tornillo") is True

    def test_existing_agregale_still_works(self):
        assert fq.looks_like_additive("agregale una mecha") is True

    def test_existing_suma_still_works(self):
        assert fq.looks_like_additive("suma un martillo") is True

    def test_existing_y_tambien_still_works(self):
        assert fq.looks_like_additive("y tambien quiero tornillos") is True

    # ── Negative cases — must NOT match ───────────────────────────────────

    def test_unrelated_phrase_returns_False(self):
        assert fq.looks_like_additive("para madera") is False

    def test_option_selection_returns_False(self):
        assert fq.looks_like_additive("la opcion A") is False

    def test_plain_product_query_returns_False(self):
        assert fq.looks_like_additive("necesito un martillo") is False

    def test_clarification_answer_returns_False(self):
        assert fq.looks_like_additive("Para madera, por favor") is False


class TestSandboxStatePreservation:
    """D5 — guard that _load_active_quote_from_store skips in sandbox mode.

    Root cause: in training mode each turn gets a fresh SalesBot with an empty
    temp DB.  The old code queried the store, got None, and popped active_quote
    from the session — clobbering the state that TrainingSessionService had just
    injected via JSON round-trip.
    """

    def _make_sandbox_bot(self):
        from bot_sales.bot import SalesBot
        with patch.object(SalesBot, "__init__", lambda s, *a, **kw: None):
            bot = SalesBot.__new__(SalesBot)
        bot.sandbox_mode = True
        bot.tenant_id = "ferreteria"
        bot.sessions = {}
        bot.quote_service = MagicMock()
        bot.quote_service.load_active_quote.return_value = None  # empty temp DB
        return bot

    def test_load_active_quote_skipped_in_sandbox(self):
        """sandbox_mode=True → active_quote injected in session must survive."""
        bot = self._make_sandbox_bot()
        sid = "test_sandbox_session"
        injected_items = [{"sku": "DST-001", "description": "Dest. Phillips", "qty": 1, "status": "awaiting_clarification"}]
        bot.sessions[sid] = {"active_quote": injected_items, "quote_state": "open"}

        bot._load_active_quote_from_store(sid)

        assert bot.sessions[sid].get("active_quote") == injected_items, (
            "_load_active_quote_from_store must not pop active_quote when sandbox_mode=True"
        )
        bot.quote_service.load_active_quote.assert_not_called()

    def test_load_active_quote_skipped_preserves_quote_state(self):
        """Both active_quote and quote_state survive the sandbox guard."""
        bot = self._make_sandbox_bot()
        sid = "test_sandbox_session_2"
        bot.sessions[sid] = {
            "active_quote": [{"sku": "X"}],
            "quote_state": "open",
        }

        bot._load_active_quote_from_store(sid)

        assert bot.sessions[sid].get("quote_state") == "open"

    def test_training_flow_state_survives_json_round_trip(self):
        """JSON-serialise → deserialise of session state must preserve active_quote.

        Mimics what TrainingSessionService does between turns: serialise the
        session dict to JSON after T1, then re-inject it into a fresh bot for T2.
        The key assertion is that active_quote is intact after re-injection and
        after _load_active_quote_from_store runs (which it does in process_message).
        """
        from bot_sales.bot import SalesBot

        original_state = {
            "active_quote": [
                {
                    "sku": "DST-001",
                    "description": "Destornillador Phillips",
                    "qty": 1,
                    "unit_price": 1500.0,
                    "subtotal": 1500.0,
                    "status": "awaiting_clarification",
                    "products": [
                        {"sku": "DST-A", "description": "Opt A", "unit_price": 1200.0},
                        {"sku": "DST-B", "description": "Opt B", "unit_price": 1500.0},
                    ],
                }
            ],
            "quote_state": "open",
            "last_offered_products": None,
        }

        # T1 → T2 JSON round-trip (what TrainingSessionService does)
        state_json = json.dumps(original_state, ensure_ascii=False)
        rehydrated = json.loads(state_json)

        # Build fresh bot (sandbox) and inject rehydrated state
        with patch.object(SalesBot, "__init__", lambda s, *a, **kw: None):
            bot = SalesBot.__new__(SalesBot)
        bot.sandbox_mode = True
        bot.tenant_id = "ferreteria"
        bot.sessions = {}
        bot.quote_service = MagicMock()
        bot.quote_service.load_active_quote.return_value = None

        sid = "training_round_trip_session"
        bot.sessions[sid] = rehydrated

        # This is called at the top of process_message for ferreteria
        bot._load_active_quote_from_store(sid)

        aq = bot.sessions[sid].get("active_quote")
        assert aq is not None and len(aq) == 1, "active_quote must survive JSON round-trip + sandbox guard"
        assert aq[0]["status"] == "awaiting_clarification"
        assert len(aq[0].get("products", [])) == 2
