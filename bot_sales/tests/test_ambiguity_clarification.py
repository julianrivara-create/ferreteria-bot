"""
Tests for the V9 ambiguous query detector (Slang / ambiguity-clarification feature).

All tests are LLM-free — they exercise the deterministic pre-LLM detector only.

Unit tests: detect_ambiguous_query() directly.
Integration tests: process_message() stub confirms V9 short-circuits before LLM.

Run:
    pytest bot_sales/tests/test_ambiguity_clarification.py -v
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.services.search_validator import (
    detect_ambiguous_query,
    V9_GENERIC_BROWSE_RESPONSE,
    _v9_has_product_keyword,
    _v9_detect_brand,
)
from bot_sales.state.conversation_state import ConversationStateV2, StateStore


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_bot():
    """
    Minimal SalesBot stub that wires only the attributes needed to reach the
    V9 check in process_message without touching the LLM or DB.
    Mirrors the pattern used in test_handoff_negotiation.py.
    """
    from bot_sales.bot import SalesBot
    with patch.object(SalesBot, "__init__", lambda s, *a, **kw: None):
        bot = SalesBot.__new__(SalesBot)
    bot.sandbox_mode = True
    bot.tenant_id = "ferreteria"
    bot.tenant_profile = {}
    bot.quote_service = None
    bot.sessions = {}
    bot.contexts = {}
    bot.system_prompt = "sistema test"
    return bot


# ─── Unit tests: detector functions ───────────────────────────────────────────

class TestV9ProductKeywordHelper(unittest.TestCase):
    """_v9_has_product_keyword detects known product terms."""

    def test_detects_taladro(self):
        self.assertTrue(_v9_has_product_keyword("quiero un taladro"))

    def test_detects_broca(self):
        self.assertTrue(_v9_has_product_keyword("mechas de 8mm"))

    def test_detects_category(self):
        self.assertTrue(_v9_has_product_keyword("algo de plomería"))

    def test_no_keyword_in_generic(self):
        self.assertFalse(_v9_has_product_keyword("dale mostrame qué hay"))

    def test_no_keyword_in_brand_only(self):
        self.assertFalse(_v9_has_product_keyword("tipo Bosch tenés algo?"))


class TestV9BrandDetector(unittest.TestCase):
    """_v9_detect_brand extracts canonical brand names."""

    def test_detects_bosch(self):
        self.assertEqual(_v9_detect_brand("tipo Bosch tenés algo?"), "Bosch")

    def test_detects_makita_lowercase(self):
        self.assertEqual(_v9_detect_brand("algo de makita"), "Makita")

    def test_detects_dewalt_mixed_case(self):
        self.assertEqual(_v9_detect_brand("DeWalt tenés algo?"), "DeWalt")

    def test_detects_black_decker_space(self):
        self.assertEqual(_v9_detect_brand("algo de black decker"), "Black+Decker")

    def test_no_brand_in_generic(self):
        self.assertIsNone(_v9_detect_brand("mostrame qué hay"))

    def test_no_brand_in_product_query(self):
        self.assertIsNone(_v9_detect_brand("broca 8mm"))


class TestV9DetectAmbiguousQuery(unittest.TestCase):
    """detect_ambiguous_query — unit tests for Type A and Type C."""

    # ── Type A: Generic browse (E14 + E47) ────────────────────────────────────

    def test_e14_dale_mostrame_que_hay(self):
        """E14: 'dale, mostrame qué hay' → fires Type A."""
        fired, response = detect_ambiguous_query("dale, mostrame qué hay")
        self.assertTrue(fired, "Expected V9 to fire for E14")
        self.assertEqual(response, V9_GENERIC_BROWSE_RESPONSE)

    def test_e47_si_tenes_standalone(self):
        """E47 turn 1: 'si tenes' alone → fires Type A."""
        fired, response = detect_ambiguous_query("si tenes")
        self.assertTrue(fired, "Expected V9 to fire for 'si tenes'")
        self.assertEqual(response, V9_GENERIC_BROWSE_RESPONSE)

    def test_e47_mostrame_standalone(self):
        """E47 turn 2: 'mostrame' alone → fires Type A."""
        fired, response = detect_ambiguous_query("mostrame")
        self.assertTrue(fired, "Expected V9 to fire for standalone 'mostrame'")
        self.assertEqual(response, V9_GENERIC_BROWSE_RESPONSE)

    def test_e47_los_caros_standalone(self):
        """E47 turn 3: 'los caros' alone → fires Type A."""
        fired, response = detect_ambiguous_query("los caros")
        self.assertTrue(fired, "Expected V9 to fire for 'los caros'")
        self.assertEqual(response, V9_GENERIC_BROWSE_RESPONSE)

    def test_que_hay_at_end(self):
        """'qué hay?' at end → fires Type A."""
        fired, _ = detect_ambiguous_query("qué hay?")
        self.assertTrue(fired)

    def test_que_tenes_at_end(self):
        """'qué tenés?' → fires Type A."""
        fired, _ = detect_ambiguous_query("qué tenés?")
        self.assertTrue(fired)

    def test_los_baratos(self):
        """'los baratos' → fires Type A."""
        fired, _ = detect_ambiguous_query("los baratos")
        self.assertTrue(fired)

    def test_mostra_el_catalogo(self):
        """'mostrá el catálogo' → fires Type A."""
        fired, _ = detect_ambiguous_query("mostrá el catálogo")
        self.assertTrue(fired)

    def test_response_mentions_rubros(self):
        """Type A response lists catalog sections."""
        _, response = detect_ambiguous_query("los caros")
        self.assertIn("herramientas", response.lower())
        self.assertIn("plomería", response.lower())
        self.assertIn("pinturas", response.lower())

    # ── Type C: Brand only (E20) ───────────────────────────────────────────────

    def test_e20_tipo_bosch_tenes_algo(self):
        """E20: 'tipo Bosch tenés algo?' → fires Type C with brand name."""
        fired, response = detect_ambiguous_query("tipo Bosch tenés algo?")
        self.assertTrue(fired, "Expected V9 to fire for E20")
        self.assertIn("Bosch", response)
        self.assertIn("taladros", response.lower())

    def test_brand_only_makita(self):
        """'algo de Makita' → fires Type C."""
        fired, response = detect_ambiguous_query("algo de Makita")
        self.assertTrue(fired)
        self.assertIn("Makita", response)

    def test_brand_only_milwaukee(self):
        """'Milwaukee tenés algo?' → fires Type C."""
        fired, response = detect_ambiguous_query("Milwaukee tenés algo?")
        self.assertTrue(fired)
        self.assertIn("Milwaukee", response)

    def test_type_c_response_mentions_tool_types(self):
        """Type C response asks about specific product types."""
        _, response = detect_ambiguous_query("tipo Bosch tenés algo?")
        self.assertIn("taladros", response.lower())
        self.assertIn("amoladoras", response.lower())

    # ── Negative tests: V9 must NOT fire ──────────────────────────────────────

    def test_no_fire_on_empty_query(self):
        """Empty query → no fire."""
        fired, _ = detect_ambiguous_query("")
        self.assertFalse(fired)

    def test_no_fire_when_product_mentioned_with_browse(self):
        """'mostrame taladros' → product keyword suppresses V9."""
        fired, _ = detect_ambiguous_query("mostrame taladros")
        self.assertFalse(fired, "Product keyword should suppress V9 Type A")

    def test_no_fire_qué_hay_de_mechas(self):
        """'qué hay de mechas?' → product keyword suppresses."""
        fired, _ = detect_ambiguous_query("qué hay de mechas?")
        self.assertFalse(fired)

    def test_no_fire_que_tenes_en_plomeria(self):
        """'qué tenés en plomería?' → category keyword suppresses."""
        fired, _ = detect_ambiguous_query("qué tenés en plomería?")
        self.assertFalse(fired)

    def test_no_fire_los_caros_de_amoladora(self):
        """'los caros de amoladora' → product keyword suppresses."""
        fired, _ = detect_ambiguous_query("los caros de amoladora")
        self.assertFalse(fired)

    def test_no_fire_si_tenes_mechas(self):
        """'si tenés mechas de 8mm' → product keyword suppresses."""
        fired, _ = detect_ambiguous_query("si tenés mechas de 8mm?")
        self.assertFalse(fired)

    def test_no_fire_e20_with_product(self):
        """'tipo Bosch tenés algún taladro?' → product keyword suppresses V9 Type C."""
        fired, _ = detect_ambiguous_query("tipo Bosch tenés algún taladro?")
        self.assertFalse(fired, "Product keyword should suppress V9 Type C")

    def test_no_fire_brand_without_shopping_signal(self):
        """'Trabajé para Bosch años' → brand without shopping signal → no fire."""
        fired, _ = detect_ambiguous_query("trabajé para Bosch años")
        self.assertFalse(fired)

    def test_no_fire_concrete_product_query(self):
        """'broca 8mm para madera' → concrete query, no fire."""
        fired, _ = detect_ambiguous_query("broca 8mm para madera")
        self.assertFalse(fired)

    def test_no_fire_e13_che_tenes_taladros(self):
        """E13: 'che, tenés taladros?' → product keyword suppresses."""
        fired, _ = detect_ambiguous_query("che, tenés taladros?")
        self.assertFalse(fired)

    def test_no_fire_que_hay_de_nuevo(self):
        """'qué hay de nuevo?' → 'de nuevo' follows 'qué hay', pattern requires end-of-string."""
        fired, _ = detect_ambiguous_query("qué hay de nuevo?")
        self.assertFalse(fired, "Conversational 'qué hay de nuevo?' should not fire V9")

    def test_no_fire_mostrame_un_taladro(self):
        """'mostrame un taladro' → 'taladro' is product keyword."""
        fired, _ = detect_ambiguous_query("mostrame un taladro")
        self.assertFalse(fired)


# ─── Integration tests: V9 in process_message ─────────────────────────────────

class TestV9Integration(unittest.TestCase):
    """
    Integration: process_message fires V9 pre-LLM and returns the clarification
    response without invoking TurnInterpreter.
    """

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_e14_process_message_returns_category_menu(self, mock_turn, mock_lat):
        """E14: process_message for 'dale, mostrame qué hay' returns generic browse response."""
        bot = _make_bot()
        response = bot.process_message("s_e14", "dale, mostrame qué hay")
        self.assertIn("herramientas", response.lower())
        self.assertIn("plomería", response.lower())

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_e47_los_caros_returns_category_menu(self, mock_turn, mock_lat):
        """E47: 'los caros' triggers V9 and returns category menu."""
        bot = _make_bot()
        response = bot.process_message("s_e47", "los caros")
        self.assertIn("herramientas", response.lower())

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_e20_tipo_bosch_returns_brand_response(self, mock_turn, mock_lat):
        """E20: 'tipo Bosch tenés algo?' returns brand-specific clarification."""
        bot = _make_bot()
        response = bot.process_message("s_e20", "tipo Bosch tenés algo?")
        self.assertIn("Bosch", response)
        self.assertIn("taladros", response.lower())

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    @patch("bot_sales.bot.SalesBot._try_ferreteria_intent_route")
    def test_llm_not_called_for_e14(self, mock_llm, mock_turn, mock_lat):
        """V9 must short-circuit before _try_ferreteria_intent_route (TurnInterpreter)."""
        bot = _make_bot()
        bot.process_message("s_llm", "dale, mostrame qué hay")
        mock_llm.assert_not_called()

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    @patch("bot_sales.bot.SalesBot._try_ferreteria_intent_route")
    def test_llm_not_called_for_e20(self, mock_llm, mock_turn, mock_lat):
        """V9 must short-circuit before TurnInterpreter for brand-only query."""
        bot = _make_bot()
        bot.process_message("s_e20_llm", "tipo Bosch tenés algo?")
        mock_llm.assert_not_called()

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    @patch("bot_sales.bot.SalesBot._try_ferreteria_intent_route")
    def test_v9_does_not_fire_for_concrete_query(self, mock_llm, mock_turn, mock_lat):
        """Concrete product query bypasses V9 and reaches TurnInterpreter."""
        mock_llm.return_value = "respuesta LLM"
        bot = _make_bot()
        bot.process_message("s_concrete", "broca 8mm para metal")
        mock_llm.assert_called()

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    def test_v9_fires_for_all_e47_turns(self, mock_turn, mock_lat):
        """E47: all three turns ('si tenes', 'mostrame', 'los caros') trigger V9."""
        turns = ["si tenes", "mostrame", "los caros"]
        for i, msg in enumerate(turns):
            with self.subTest(msg=msg):
                bot = _make_bot()
                response = bot.process_message(f"s_e47_{i}", msg)
                self.assertIn("herramientas", response.lower(),
                              f"V9 should fire for turn: {msg!r}")

    @patch("bot_sales.bot.record_latency_bucket")
    @patch("bot_sales.bot.record_turn")
    @patch("bot_sales.bot.SalesBot._try_ferreteria_pre_route", return_value=None)
    @patch("bot_sales.bot.SalesBot._try_ferreteria_intent_route")
    def test_v8_still_has_priority_over_v9(self, mock_llm, mock_pre, mock_turn, mock_lat):
        """V8 (negotiation) takes precedence — V9 never reached for negotiation input."""
        mock_llm.return_value = "respuesta LLM"
        bot = _make_bot()
        response = bot.process_message("s_v8v9", "dame un descuento")
        # V8 fires → response contains "asesor", not the generic category menu
        self.assertIn("asesor", response.lower())
        self.assertNotIn("rubros", response.lower())


if __name__ == "__main__":
    unittest.main()
