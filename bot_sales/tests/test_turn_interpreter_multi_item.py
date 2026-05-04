"""
test_turn_interpreter_multi_item.py

Tests that TurnInterpreter correctly handles multi-item quote requests
without JSON truncation.

Root cause: max_tokens=200 truncated JSON for 5+ item lists with long product
names, causing JSONDecodeError → intent=unknown, confidence=0.00 → fallback chain.
Fixed by raising max_tokens to 1024.

Fast tests (no LLM calls): TestTurnInterpreterMultiItem
Slow tests (real API):     TestTurnInterpreterMultiItemLive  -- use -m slow
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.routing.turn_interpreter import TurnInterpreter, TurnInterpretation


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


# ---------------------------------------------------------------------------
# Fast tests (mocked LLM)
# ---------------------------------------------------------------------------

class TestTurnInterpreterMultiItem:

    def test_short_query_intent_classified(self):
        """Short query resolves to non-unknown intent with high confidence."""
        llm = _make_mock_llm(_interpretation_json(
            intent="product_search", confidence=0.97, product_terms=["taladro"]
        ))
        result = TurnInterpreter(llm).interpret("tenés taladros?")

        assert result.intent != "unknown"
        assert result.confidence > 0.5
        assert "taladro" in result.entities.product_terms

    def test_5_item_list_intent_classified(self):
        """5-item quote list resolves correctly — tests parsing for multi-item."""
        terms = [
            "tornillos M6",
            "clavos 50mm",
            "codos 90 grados",
            "cuplas",
            "sellador siliconado",
        ]
        llm = _make_mock_llm(_interpretation_json(product_terms=terms))
        query = "necesito 10 tornillos M6, 5 clavos 50mm, 3 codos 90, 2 cuplas, 1 sellador siliconado"
        result = TurnInterpreter(llm).interpret(query)

        assert result.intent != "unknown", f"Expected non-unknown intent, got: {result.intent}"
        assert result.confidence > 0.5
        assert len(result.entities.product_terms) == 5

    def test_10_item_list_intent_classified(self):
        """10 items with long product names produce valid TurnInterpretation."""
        terms = [
            "tornillo M6 cabeza hexagonal acero inoxidable",
            "codo 90 grados PVC 3/4",
            "cupla galvanizada 1 pulgada",
            "llave de paso esfera bronce",
            "sellador siliconado transparente",
            "electrodo rutilo 3.25mm",
            "manguera radiador 1/2 pulgada",
            "broca concreto 10mm",
            "disco corte amoladora 115mm",
            "cable unipolar 2.5mm negro",
        ]
        llm = _make_mock_llm(_interpretation_json(confidence=0.93, product_terms=terms))
        query = "cotización para obra: " + ", ".join(f"100 {t}" for t in terms)
        result = TurnInterpreter(llm).interpret(query)

        assert result.intent != "unknown", f"Expected non-unknown intent, got: {result.intent}"
        assert result.confidence > 0.5
        assert len(result.entities.product_terms) == 10

    def test_query_with_greeting_and_list(self):
        """Greeting + multi-item list: saludo no corrompe la clasificación."""
        terms = [
            "tornillos M6 cabeza hexagonal",
            "codos 90 grados",
            "cuplas",
            "llaves de paso",
            "sellador siliconado",
        ]
        llm = _make_mock_llm(_interpretation_json(confidence=0.92, product_terms=terms))
        query = (
            "hola, necesito cotización para una obra: 100 tornillos M6 cabeza hexagonal, "
            "50 codos 90 grados, 30 cuplas, 10 llaves de paso, sellador siliconado"
        )
        result = TurnInterpreter(llm).interpret(query)

        assert result.intent != "unknown", f"Greeting corrupted intent: {result.intent}"
        assert result.confidence > 0.5
        assert len(result.entities.product_terms) > 0

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

    def test_no_truncation_in_response(self):
        """
        Truncated JSON (simulating the old max_tokens=200 cutoff) gracefully degrades
        to unknown; a complete JSON for the same reproducer query parses correctly.
        """
        # Simulate a truncated response — JSON cut mid-string as max_tokens=200 would produce
        truncated = (
            '{"intent": "product_search", "confidence": 0.95, "tone": "neutral", '
            '"policy_topic": null, "search_mode": "exact", "entities": {"product_terms": '
            '["tornillos M6 cabeza hexagonal", "codos 90 grados", "cuplas", "llaves de paso'
            # intentionally truncated — no closing bracket/brace
        )
        mock_trunc = MagicMock()
        mock_trunc.model = "gpt-4o"
        mock_trunc.max_tokens = 800
        mock_trunc.temperature = 0.7
        mock_trunc.send_message.return_value = truncated

        result_trunc = TurnInterpreter(mock_trunc).interpret("test query")
        assert result_trunc.intent == "unknown", "Truncated JSON must degrade to unknown"
        assert result_trunc.confidence == 0.0

        # Same query with full JSON must parse correctly
        full_terms = [
            "tornillos M6 cabeza hexagonal",
            "codos 90 grados",
            "cuplas",
            "llaves de paso",
            "sellador siliconado",
        ]
        llm_full = _make_mock_llm(_interpretation_json(confidence=0.95, product_terms=full_terms))
        result_full = TurnInterpreter(llm_full).interpret(
            "hola, necesito cotización para una obra: 100 tornillos M6 cabeza hexagonal, "
            "50 codos 90 grados, 30 cuplas, 10 llaves de paso, sellador siliconado"
        )
        assert result_full.intent != "unknown"
        assert len(result_full.entities.product_terms) == 5


# ---------------------------------------------------------------------------
# Slow tests (real LLM API) — run with: pytest -m slow
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestTurnInterpreterMultiItemLive:
    """
    Real LLM integration tests. Require OPENAI_API_KEY env var.
    Verify that with max_tokens=1024 the LLM returns complete, parseable JSON
    for multi-item quote requests.
    """

    @pytest.fixture(autouse=True)
    def _require_api_key(self):
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

    def _make_real_interpreter(self):
        import os
        from bot_sales.core.chatgpt import ChatGPTClient
        client = ChatGPTClient(
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=800,
        )
        return TurnInterpreter(client)

    def test_5_item_list_real_llm(self):
        """Real LLM call: reproducer query must not return intent=unknown."""
        ti = self._make_real_interpreter()
        query = (
            "hola, necesito cotización para una obra: 100 tornillos M6 cabeza hexagonal, "
            "50 codos 90 grados, 30 cuplas, 10 llaves de paso, sellador siliconado"
        )
        result = ti.interpret(query)

        assert result.intent != "unknown", (
            f"Real LLM returned intent=unknown (possible JSON truncation). "
            f"intent={result.intent}, confidence={result.confidence}"
        )
        assert result.confidence > 0.5
        assert len(result.entities.product_terms) >= 3, (
            f"Expected ≥3 product terms, got: {result.entities.product_terms}"
        )
