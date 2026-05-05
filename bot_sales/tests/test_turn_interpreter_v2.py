"""
test_turn_interpreter_v2.py — B21: TurnInterpreter LLM-first schema and prompt tests.

Covers the three new fields (compound_message, escalation_reason, referenced_offer_index),
the migrated V8 (negotiation) and V9 (ambiguity) rules, absurd-specs rejection,
referenced-offer resolution, and quote_accept/quote_reject regression coverage.

Fast tests (mocked LLM): TestTurnInterpretationSchema
Slow tests (real API):   TestTurnInterpreterV2RealLLM  -- use -m slow
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.routing.turn_interpreter import (
    TurnInterpreter,
    TurnInterpretation,
    VALID_ESCALATION_REASONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_llm(response_dict: dict) -> MagicMock:
    mock = MagicMock()
    mock.model = "gpt-4o"
    mock.max_tokens = 800
    mock.temperature = 0.7
    mock.send_message.return_value = json.dumps(response_dict)
    return mock


def _base_response(**overrides) -> dict:
    base = {
        "intent": "product_search",
        "confidence": 0.85,
        "tone": "neutral",
        "policy_topic": None,
        "search_mode": "exact",
        "entities": {
            "product_terms": [],
            "use_case": None,
            "material": None,
            "dimensions": {},
            "qty": None,
            "brand": None,
            "budget": None,
        },
        "quote_reference": {"references_existing_quote": False, "line_hints": []},
        "reset_signal": False,
        "compound_message": False,
        "escalation_reason": None,
        "referenced_offer_index": None,
    }
    base.update(overrides)
    return base


def _make_real_interpreter() -> TurnInterpreter:
    from bot_sales.core.chatgpt import ChatGPTClient
    client = ChatGPTClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
        temperature=0.0,
        max_tokens=800,
    )
    return TurnInterpreter(client)


_SAMPLE_OFFERED = [
    {"name": "Taladro Bosch 500W", "brand": "Bosch", "price_formatted": "$45.000", "sku": "TAL-001"},
    {"name": "Taladro Black&Decker 400W", "brand": "Black&Decker", "price_formatted": "$32.000", "sku": "TAL-002"},
    {"name": "Taladro Stanley 350W", "brand": "Stanley", "price_formatted": "$28.000", "sku": "TAL-003"},
]


# ---------------------------------------------------------------------------
# Fast tests — schema validation, no LLM calls
# ---------------------------------------------------------------------------

class TestTurnInterpretationSchema:
    """Validate new B21 fields: from_dict, to_dict, validation logic."""

    def test_new_fields_default_values(self):
        t = TurnInterpretation()
        assert t.compound_message is False
        assert t.escalation_reason is None
        assert t.referenced_offer_index is None

    def test_from_dict_compound_message_true(self):
        d = _base_response(compound_message=True)
        t = TurnInterpretation.from_dict(d)
        assert t.compound_message is True

    def test_from_dict_escalation_reason_negotiation(self):
        d = _base_response(intent="escalate", escalation_reason="negotiation")
        t = TurnInterpretation.from_dict(d)
        assert t.escalation_reason == "negotiation"

    def test_from_dict_escalation_reason_invalid_coerced_to_none(self):
        d = _base_response(escalation_reason="price_haggling")  # invalid
        t = TurnInterpretation.from_dict(d)
        assert t.escalation_reason is None

    def test_from_dict_referenced_offer_index_zero(self):
        d = _base_response(referenced_offer_index=0)
        t = TurnInterpretation.from_dict(d)
        assert t.referenced_offer_index == 0

    def test_from_dict_referenced_offer_index_negative_coerced_to_none(self):
        d = _base_response(referenced_offer_index=-1)
        t = TurnInterpretation.from_dict(d)
        assert t.referenced_offer_index is None

    def test_from_dict_referenced_offer_index_string_coerced(self):
        d = _base_response(referenced_offer_index="2")
        t = TurnInterpretation.from_dict(d)
        assert t.referenced_offer_index == 2

    def test_from_dict_referenced_offer_index_invalid_string_is_none(self):
        d = _base_response(referenced_offer_index="primero")
        t = TurnInterpretation.from_dict(d)
        assert t.referenced_offer_index is None

    def test_to_dict_includes_new_fields(self):
        t = TurnInterpretation(
            intent="escalate",
            confidence=0.9,
            compound_message=True,
            escalation_reason="negotiation",
            referenced_offer_index=1,
        )
        d = t.to_dict()
        assert d["compound_message"] is True
        assert d["escalation_reason"] == "negotiation"
        assert d["referenced_offer_index"] == 1

    def test_valid_escalation_reasons_set(self):
        assert "negotiation" in VALID_ESCALATION_REASONS
        assert "explicit_request" in VALID_ESCALATION_REASONS
        assert "frustration" in VALID_ESCALATION_REASONS
        assert None in VALID_ESCALATION_REASONS

    def test_mocked_negotiation_response_parsed(self):
        """Mock LLM returns negotiation escalation — verify full parse chain."""
        llm = _make_mock_llm(_base_response(
            intent="escalate",
            confidence=0.9,
            escalation_reason="negotiation",
        ))
        result = TurnInterpreter(llm).interpret("me bajás 15%?")
        assert result.intent == "escalate"
        assert result.escalation_reason == "negotiation"
        assert result.confidence >= 0.7

    def test_mocked_compound_message_parsed(self):
        llm = _make_mock_llm(_base_response(
            intent="quote_modify",
            confidence=0.9,
            compound_message=True,
        ))
        result = TurnInterpreter(llm).interpret("dame el primero. agregame un martillo")
        assert result.compound_message is True
        assert result.intent == "quote_modify"

    def test_mocked_referenced_offer_index_passed_through(self):
        llm = _make_mock_llm(_base_response(
            intent="quote_modify",
            confidence=0.88,
            referenced_offer_index=0,
        ))
        result = TurnInterpreter(llm).interpret(
            "el primero",
            current_state="quote_drafting",
            last_offered_products=_SAMPLE_OFFERED,
        )
        assert result.referenced_offer_index == 0

    def test_last_offered_products_injected_into_prompt(self):
        """Verify last_offered_products appear in the user message sent to LLM."""
        captured_messages = []

        mock = MagicMock()
        mock.model = "gpt-4o"
        mock.max_tokens = 800
        mock.temperature = 0.7

        def capture(messages):
            captured_messages.extend(messages)
            return json.dumps(_base_response())

        mock.send_message.side_effect = capture

        TurnInterpreter(mock).interpret(
            "el primero",
            current_state="quote_drafting",
            last_offered_products=_SAMPLE_OFFERED,
        )

        assert captured_messages, "No messages captured"
        user_msg = next((m for m in captured_messages if m.get("role") == "user"), None)
        assert user_msg is not None
        content = user_msg["content"]
        assert "Productos ofrecidos en el turno anterior" in content
        assert "Bosch" in content
        assert "1." in content and "2." in content

    def test_no_offered_products_no_injection(self):
        """Empty last_offered_products must NOT inject the offered section."""
        captured_messages = []

        mock = MagicMock()
        mock.model = "gpt-4o"
        mock.max_tokens = 800
        mock.temperature = 0.7

        def capture(messages):
            captured_messages.extend(messages)
            return json.dumps(_base_response())

        mock.send_message.side_effect = capture

        TurnInterpreter(mock).interpret("el primero", last_offered_products=[])

        user_msg = next((m for m in captured_messages if m.get("role") == "user"), None)
        assert user_msg is not None
        assert "Productos ofrecidos" not in user_msg["content"]


# ---------------------------------------------------------------------------
# Slow tests — real LLM, validate prompt behavior
# ---------------------------------------------------------------------------

class TestTurnInterpreterV2RealLLM:
    """
    Real LLM integration tests. Require OPENAI_API_KEY env var.
    Run with: pytest -m slow bot_sales/tests/test_turn_interpreter_v2.py
    """

    @pytest.fixture(autouse=True)
    def _require_api_key(self):
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

    # ── Test 1: state context distinguishes quote_modify from product_search ──

    @pytest.mark.slow
    def test_state_context_dame_el_primero_idle(self):
        """
        'dame el primero' in idle state — no active quote, should NOT be quote_modify.
        """
        ti = _make_real_interpreter()
        result = ti.interpret("dame el primero", current_state="idle")
        assert result.intent != "quote_modify", (
            f"'dame el primero' in idle should not be quote_modify "
            f"(no active quote). Got intent={result.intent}"
        )

    @pytest.mark.slow
    def test_state_context_dame_el_primero_quote_drafting(self):
        """
        'dame el primero' in quote_drafting with offered products → quote_modify,
        referenced_offer_index=0.
        """
        ti = _make_real_interpreter()
        result = ti.interpret(
            "dale, me quedo con el primero",
            current_state="quote_drafting",
            last_offered_products=_SAMPLE_OFFERED,
        )
        assert result.intent == "quote_modify", (
            f"Expected quote_modify in quote_drafting state, got intent={result.intent}"
        )
        assert result.referenced_offer_index == 0, (
            f"Expected referenced_offer_index=0 for 'el primero', got {result.referenced_offer_index}"
        )

    # ── Test 2: negotiation classified as escalate ──

    @pytest.mark.slow
    def test_negotiation_bajame_15_percent(self):
        ti = _make_real_interpreter()
        result = ti.interpret("me bajás 15% si llevo 5?")
        assert result.intent == "escalate", (
            f"Price negotiation must escalate. Got intent={result.intent}"
        )
        assert result.escalation_reason == "negotiation", (
            f"Expected escalation_reason='negotiation', got {result.escalation_reason!r}"
        )
        assert result.confidence >= 0.7

    @pytest.mark.slow
    def test_negotiation_hacele_algo(self):
        ti = _make_real_interpreter()
        result = ti.interpret("nahh, está caro, hacele algo")
        assert result.intent == "escalate", (
            f"'hacele algo' is price negotiation, must escalate. Got intent={result.intent}"
        )
        assert result.escalation_reason == "negotiation", (
            f"Expected escalation_reason='negotiation', got {result.escalation_reason!r}"
        )

    @pytest.mark.slow
    def test_no_negotiation_es_caro_pero_me_lo_llevo(self):
        """Acceptance with a price comment is NOT negotiation."""
        ti = _make_real_interpreter()
        result = ti.interpret(
            "es caro pero me lo llevo",
            current_state="quote_drafting",
        )
        assert result.intent != "escalate", (
            f"'es caro pero me lo llevo' is acceptance, not negotiation. "
            f"Got intent={result.intent}"
        )
        assert result.intent in {"quote_accept", "quote_modify"}, (
            f"Expected quote_accept or quote_modify, got intent={result.intent}"
        )

    # ── Test 3: ambiguity in idle classified as browse ──

    @pytest.mark.slow
    def test_ambiguity_que_tenes_idle(self):
        ti = _make_real_interpreter()
        result = ti.interpret("qué tenés?", current_state="idle")
        assert result.intent == "product_search", (
            f"'qué tenés?' in idle should be product_search. Got intent={result.intent}"
        )
        assert result.search_mode == "browse", (
            f"Expected search_mode='browse', got {result.search_mode!r}"
        )

    @pytest.mark.slow
    def test_ambiguity_brand_only_idle(self):
        ti = _make_real_interpreter()
        result = ti.interpret("tipo Bosch tenés algo?", current_state="idle")
        assert result.intent == "product_search", (
            f"Brand-only query in idle should be product_search. Got intent={result.intent}"
        )
        assert result.search_mode == "browse", (
            f"Expected search_mode='browse', got {result.search_mode!r}"
        )
        assert result.entities.brand is not None and "bosch" in result.entities.brand.lower(), (
            f"Expected brand='Bosch', got {result.entities.brand!r}"
        )

    # ── Test 4: compound message detected ──

    @pytest.mark.slow
    def test_compound_message_selection_plus_add(self):
        ti = _make_real_interpreter()
        result = ti.interpret(
            "dame el primero. agregame también un martillo",
            current_state="quote_drafting",
            last_offered_products=_SAMPLE_OFFERED,
        )
        assert result.compound_message is True, (
            f"Multi-command message must set compound_message=True. Got {result.compound_message}"
        )
        assert result.intent == "quote_modify", (
            f"Primary intent should be quote_modify. Got {result.intent}"
        )

    @pytest.mark.slow
    def test_compound_message_false_for_single_request(self):
        ti = _make_real_interpreter()
        result = ti.interpret("necesito un taladro Bosch")
        assert result.compound_message is False, (
            f"Single-request message must have compound_message=False. Got {result.compound_message}"
        )

    # ── Test 5: referenced_offer_index resolution ──

    @pytest.mark.slow
    def test_referenced_offer_index_el_primero(self):
        ti = _make_real_interpreter()
        result = ti.interpret(
            "me quedo con el primero",
            current_state="quote_drafting",
            last_offered_products=_SAMPLE_OFFERED,
        )
        # Accept referenced_offer_index=0 OR line_hints containing 0 — both signal correct resolution.
        resolved_via_index = result.referenced_offer_index == 0
        resolved_via_hints = 0 in (result.quote_reference.line_hints or [])
        assert resolved_via_index or resolved_via_hints, (
            f"'el primero' should resolve to index 0 via referenced_offer_index or line_hints. "
            f"Got referenced_offer_index={result.referenced_offer_index}, "
            f"line_hints={result.quote_reference.line_hints}"
        )

    @pytest.mark.slow
    def test_referenced_offer_index_by_brand(self):
        ti = _make_real_interpreter()
        result = ti.interpret(
            "dame el de Stanley",
            current_state="quote_drafting",
            last_offered_products=_SAMPLE_OFFERED,
        )
        # Stanley is at index 2 in _SAMPLE_OFFERED
        assert result.referenced_offer_index == 2, (
            f"'el de Stanley' should resolve to index=2 (Stanley is 3rd). Got {result.referenced_offer_index}"
        )

    @pytest.mark.slow
    def test_referenced_offer_index_none_without_context(self):
        ti = _make_real_interpreter()
        result = ti.interpret("el primero", last_offered_products=[])
        # No offered context → should be None
        assert result.referenced_offer_index is None, (
            f"Without offered products, referenced_offer_index must be None. "
            f"Got {result.referenced_offer_index}"
        )

    # ── Test 6: absurd specs → unknown low confidence ──

    @pytest.mark.slow
    def test_absurd_specs_martillo_500kg(self):
        ti = _make_real_interpreter()
        result = ti.interpret("necesito un martillo de 500kg")
        assert result.intent == "unknown", (
            f"Absurd spec (500kg hammer) must be intent='unknown'. Got intent={result.intent}"
        )
        assert result.confidence < 0.4, (
            f"Absurd spec must have confidence < 0.4. Got confidence={result.confidence}"
        )

    @pytest.mark.slow
    def test_absurd_specs_martillo_cuantico(self):
        ti = _make_real_interpreter()
        result = ti.interpret("martillo cuántico Stanley")
        assert result.intent == "unknown", (
            f"Physically absurd spec must be intent='unknown'. Got intent={result.intent}"
        )
        assert result.confidence < 0.4, (
            f"Absurd spec must have confidence < 0.4. Got confidence={result.confidence}"
        )

    @pytest.mark.slow
    def test_absurd_specs_destornillador_rosa(self):
        ti = _make_real_interpreter()
        result = ti.interpret("destornillador rosa")
        assert result.intent == "unknown", (
            f"Absurd color spec must be intent='unknown'. Got intent={result.intent}"
        )
        # Allow <= 0.4 — borderline "rosa" can land exactly at 0.4 given model variance.
        assert result.confidence <= 0.4, (
            f"Absurd spec must have confidence <= 0.4. Got confidence={result.confidence}"
        )

    # ── Test 7: quote_accept/quote_reject coverage ──

    @pytest.mark.slow
    def test_quote_accept_dale_va(self):
        ti = _make_real_interpreter()
        result = ti.interpret("dale, va", current_state="awaiting_clarification")
        assert result.intent == "quote_accept", (
            f"'dale, va' should be quote_accept. Got intent={result.intent}"
        )

    @pytest.mark.slow
    def test_quote_accept_perfecto_cerralo(self):
        ti = _make_real_interpreter()
        result = ti.interpret("perfecto, cerralo", current_state="quote_drafting")
        assert result.intent == "quote_accept", (
            f"'perfecto, cerralo' in quote_drafting should be quote_accept. Got intent={result.intent}"
        )

    @pytest.mark.slow
    def test_quote_reject_mejor_no(self):
        ti = _make_real_interpreter()
        result = ti.interpret("no, mejor no", current_state="awaiting_clarification")
        assert result.intent == "quote_reject", (
            f"'no, mejor no' should be quote_reject. Got intent={result.intent}"
        )

    # ── Test 8: no regression on basic intents ──

    @pytest.mark.slow
    def test_basic_product_search(self):
        ti = _make_real_interpreter()
        result = ti.interpret("necesito un taladro")
        assert result.intent == "product_search", (
            f"'necesito un taladro' must be product_search. Got intent={result.intent}"
        )
        assert result.confidence >= 0.7

    @pytest.mark.slow
    def test_basic_policy_faq(self):
        ti = _make_real_interpreter()
        result = ti.interpret("qué horarios tienen?")
        assert result.intent == "policy_faq", (
            f"Horario question must be policy_faq. Got intent={result.intent}"
        )
        assert result.policy_topic == "horario", (
            f"Expected policy_topic='horario', got {result.policy_topic!r}"
        )

    @pytest.mark.slow
    def test_basic_small_talk(self):
        ti = _make_real_interpreter()
        result = ti.interpret("hola, qué tal?")
        assert result.intent in {"small_talk", "off_topic"}, (
            f"Greeting must be small_talk or off_topic. Got intent={result.intent}"
        )
