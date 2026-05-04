"""
test_turn_interpreter_multi_item.py

Tests that TurnInterpreter correctly handles multi-item quote requests
without JSON truncation.

Root cause: max_tokens=200 truncated JSON for 5+ item lists with long product
names, causing JSONDecodeError → intent=unknown, confidence=0.00 → fallback chain.
Fixed by raising max_tokens to 1024.

Fast tests (no LLM calls): TestTurnInterpreterMultiItemMocked
Slow tests (real API):     TestTurnInterpreterMultiItemRealLLM  -- use -m slow
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.routing.turn_interpreter import TurnInterpreter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_llm(response_dict: dict) -> MagicMock:
    """Mock LLM that returns a given dict as a JSON string."""
    mock = MagicMock()
    mock.model = "gpt-4o"
    mock.max_tokens = 800
    mock.temperature = 0.7
    mock.send_message.return_value = json.dumps(response_dict)
    return mock


def _interpretation_json(intent="product_search", confidence=0.95, product_terms=None, tone="neutral") -> dict:
    return {
        "intent": intent,
        "confidence": confidence,
        "tone": tone,
        "policy_topic": None,
        "search_mode": "exact",
        "entities": {
            "product_terms": product_terms or [],
            "use_case": None,
            "material": None,
            "dimensions": {},
            "qty": None,
            "brand": None,
            "budget": None,
        },
        "quote_reference": {"references_existing_quote": False, "line_hints": []},
        "reset_signal": False,
    }


def _make_real_interpreter() -> TurnInterpreter:
    from bot_sales.core.chatgpt import ChatGPTClient
    client = ChatGPTClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
        temperature=0.0,
        max_tokens=800,  # TurnInterpreter will override to 1024 during the call
    )
    return TurnInterpreter(client)


# ---------------------------------------------------------------------------
# Fast tests (mocked LLM) — validate code integration without API calls
# ---------------------------------------------------------------------------

class TestTurnInterpreterMultiItemMocked:

    def test_short_query_intent_classified(self):
        """Short query resolves to non-unknown intent with high confidence."""
        llm = _make_mock_llm(_interpretation_json(
            intent="product_search", confidence=0.97, product_terms=["taladro"]
        ))
        result = TurnInterpreter(llm).interpret("tenés taladros?")

        assert result.intent != "unknown"
        assert result.confidence > 0.5
        assert "taladro" in result.entities.product_terms

    def test_max_tokens_set_to_1024_during_call(self):
        """
        Regression guard: max_tokens must be 1024 (not 200) when send_message is called.

        Bug history: 200 caused JSON truncation on multi-item queries.
        """
        captured = []

        mock = MagicMock()
        mock.model = "gpt-4o"
        mock.max_tokens = 800
        mock.temperature = 0.7

        def capture_and_respond(messages):
            captured.append(mock.max_tokens)
            return json.dumps(_interpretation_json(product_terms=["taladro"]))

        mock.send_message.side_effect = capture_and_respond
        TurnInterpreter(mock).interpret("tenés taladros?")

        assert captured == [1024], (
            f"max_tokens during LLM call was {captured}, expected [1024]. "
            "Bug: 200 was truncating JSON for multi-item queries."
        )


# ---------------------------------------------------------------------------
# Slow tests (real LLM API) — validate that max_tokens=1024 prevents truncation
# Run with: pytest -m slow bot_sales/tests/test_turn_interpreter_multi_item.py
# ---------------------------------------------------------------------------

class TestTurnInterpreterMultiItemRealLLM:
    """
    Real LLM integration tests. Require OPENAI_API_KEY env var.

    These tests reproduce the actual bug condition: a real LLM call with
    max_tokens=200 would truncate JSON for 5+ item lists. With max_tokens=1024
    (the fix), JSON must arrive complete and parse without error.

    Mocked tests cannot reproduce this — they return pre-fabricated JSON
    regardless of max_tokens.
    """

    @pytest.fixture(autouse=True)
    def _require_api_key(self):
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

    @pytest.mark.slow
    def test_5_item_list_intent_classified_real(self):
        """
        Real LLM call: 5-item quote list must not truncate JSON with max_tokens=1024.

        With the old max_tokens=200 this query could produce truncated JSON
        (pretty-printed 5-item list is ~150-170 tokens, right at the old limit).
        """
        ti = _make_real_interpreter()
        query = "necesito 10 tornillos M6, 5 clavos 50mm, 3 codos 90, 2 cuplas, 1 sellador siliconado"

        result = ti.interpret(query)

        assert result is not None
        assert result.intent != "unknown", (
            f"intent=unknown suggests JSON truncation or parse failure. "
            f"intent={result.intent}, confidence={result.confidence}, "
            f"product_terms={result.entities.product_terms}"
        )
        assert result.confidence >= 0.5
        assert len(result.entities.product_terms) >= 3, (
            f"Expected ≥3 product terms extracted, got: {result.entities.product_terms}"
        )

    @pytest.mark.slow
    def test_10_item_list_intent_classified_real(self):
        """
        Real LLM call: 10-item list with long product names must not truncate JSON.

        This is the hardest case — pretty-printed JSON for 10 items with long
        names easily exceeds 200 tokens but fits within 1024.
        """
        ti = _make_real_interpreter()
        query = (
            "necesito presupuesto: 100 tornillos M6 cabeza hexagonal, "
            "50 codos 90 grados galvanizados, 30 cuplas de 1/2 pulgada, "
            "20 niples de 1 pulgada, 10 llaves de paso 1/2, "
            "5 selladores siliconados, 3 caños PP-R 22mm, "
            "2 ramales tee 90, 1 disco de corte 230mm, 1 amoladora angular"
        )

        result = ti.interpret(query)

        assert result is not None
        assert result.intent != "unknown", (
            f"intent=unknown on 10-item query suggests JSON truncation. "
            f"intent={result.intent}, confidence={result.confidence}, "
            f"product_terms={result.entities.product_terms}"
        )
        assert result.confidence >= 0.5
        assert len(result.entities.product_terms) >= 7, (
            f"Expected ≥7 product terms from 10-item list, got: {result.entities.product_terms}"
        )

    @pytest.mark.slow
    def test_query_with_greeting_and_list_real(self):
        """
        Real LLM call: original bug reproducer — greeting + 5-item list.

        This is the exact query that triggered the bug in EOD manual testing.
        With max_tokens=200 the response was non-deterministic (sometimes
        fallback chain rescued it, sometimes returned generic error message).
        With max_tokens=1024 it must classify correctly every time.
        """
        ti = _make_real_interpreter()
        query = (
            "hola, necesito cotización para una obra: 100 tornillos M6 cabeza hexagonal, "
            "50 codos 90 grados, 30 cuplas, 10 llaves de paso, sellador siliconado"
        )

        result = ti.interpret(query)

        assert result is not None
        assert result.intent != "unknown", (
            f"Original bug reproducer still failing. "
            f"intent={result.intent}, confidence={result.confidence}, "
            f"product_terms={result.entities.product_terms}"
        )
        assert result.confidence >= 0.5
        assert len(result.entities.product_terms) >= 3, (
            f"Expected ≥3 product terms from greeting+list query, got: {result.entities.product_terms}"
        )
