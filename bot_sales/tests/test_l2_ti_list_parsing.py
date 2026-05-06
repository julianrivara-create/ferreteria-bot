"""Tests for L2 — TurnInterpreter extended with items field for product lists."""

import pytest
from unittest.mock import MagicMock, patch
import json

from bot_sales.routing.turn_interpreter import TurnInterpretation, TurnInterpreter


# ── Unit: TurnInterpretation schema ─────────────────────────────────────────

class TestTurnInterpretationItems:

    def test_items_field_default_none(self):
        ti = TurnInterpretation()
        assert ti.items is None

    def test_from_dict_with_items(self):
        d = {
            "intent": "product_search",
            "confidence": 0.95,
            "tone": "neutral",
            "items": ["5 mechas 6mm", "1 martillo", "50 tornillos 3 pulgadas"],
        }
        ti = TurnInterpretation.from_dict(d)
        assert ti.items == ["5 mechas 6mm", "1 martillo", "50 tornillos 3 pulgadas"]

    def test_from_dict_items_null(self):
        d = {"intent": "product_search", "confidence": 0.9, "items": None}
        ti = TurnInterpretation.from_dict(d)
        assert ti.items is None

    def test_from_dict_items_missing(self):
        d = {"intent": "product_search", "confidence": 0.9}
        ti = TurnInterpretation.from_dict(d)
        assert ti.items is None

    def test_from_dict_items_filters_non_strings(self):
        d = {"intent": "product_search", "confidence": 0.9,
             "items": ["mecha 6mm", 42, None, "martillo"]}
        ti = TurnInterpretation.from_dict(d)
        assert ti.items == ["mecha 6mm", "martillo"]

    def test_from_dict_items_filters_empty_strings(self):
        d = {"intent": "product_search", "confidence": 0.9,
             "items": ["mecha 6mm", "  ", "martillo"]}
        ti = TurnInterpretation.from_dict(d)
        assert ti.items == ["mecha 6mm", "martillo"]

    def test_from_dict_items_empty_list_becomes_none(self):
        d = {"intent": "product_search", "confidence": 0.9, "items": []}
        ti = TurnInterpretation.from_dict(d)
        assert ti.items is None

    def test_from_dict_items_capped_at_20(self):
        d = {"intent": "product_search", "confidence": 0.9,
             "items": [f"item {i}" for i in range(25)]}
        ti = TurnInterpretation.from_dict(d)
        assert len(ti.items) == 20

    def test_to_dict_includes_items(self):
        ti = TurnInterpretation(
            intent="product_search",
            confidence=0.95,
            items=["5 mechas 6mm", "1 martillo"],
        )
        d = ti.to_dict()
        assert "items" in d
        assert d["items"] == ["5 mechas 6mm", "1 martillo"]

    def test_to_dict_items_none(self):
        ti = TurnInterpretation(intent="product_search", confidence=0.9)
        d = ti.to_dict()
        assert d["items"] is None

    def test_simple_query_has_null_items(self):
        """Single product query should not populate items."""
        d = {"intent": "product_search", "confidence": 0.9, "items": None}
        ti = TurnInterpretation.from_dict(d)
        assert ti.items is None

    def test_roundtrip_with_items(self):
        ti = TurnInterpretation(
            intent="product_search",
            confidence=0.95,
            items=["3 mechas 6mm", "1 martillo"],
        )
        ti2 = TurnInterpretation.from_dict(ti.to_dict())
        assert ti2.items == ti.items


# ── Unit: TurnInterpreter returns items via mocked LLM ───────────────────────

class TestTurnInterpreterItemsFromLLM:

    def _make_interpreter(self, response_dict: dict) -> TurnInterpreter:
        client = MagicMock()
        client.model = "gpt-4o"
        client.max_tokens = 200
        client.temperature = 0.0
        client.send_message.return_value = {"content": json.dumps(response_dict)}
        return TurnInterpreter(client)

    def test_ti_returns_items_for_numbered_list(self):
        ti = self._make_interpreter({
            "intent": "product_search",
            "confidence": 0.95,
            "tone": "neutral",
            "items": ["50 tornillos autoperforantes 3 pulgadas", "5 mechas 6mm",
                      "5 mechas 8mm", "1 amoladora chica"],
            "search_mode": None,
            "entities": {"product_terms": [], "use_case": None, "material": None,
                         "dimensions": {}, "qty": None, "brand": None, "budget": None},
            "quote_reference": {"references_existing_quote": False, "line_hints": []},
            "reset_signal": False, "compound_message": False, "sub_commands": [],
            "escalation_reason": None, "referenced_offer_index": None,
        })
        result = ti.interpret("Necesito:\n1) 50 tornillos\n2) 5 mechas 6mm\n3) 5 mechas 8mm\n4) amoladora")
        assert result.items is not None
        assert len(result.items) == 4
        assert "50 tornillos autoperforantes 3 pulgadas" in result.items

    def test_ti_returns_null_items_for_simple_query(self):
        ti = self._make_interpreter({
            "intent": "product_search",
            "confidence": 0.9,
            "tone": "neutral",
            "items": None,
            "search_mode": "exact",
            "entities": {"product_terms": ["martillo"], "use_case": None, "material": None,
                         "dimensions": {}, "qty": 1, "brand": None, "budget": None},
            "quote_reference": {"references_existing_quote": False, "line_hints": []},
            "reset_signal": False, "compound_message": False, "sub_commands": [],
            "escalation_reason": None, "referenced_offer_index": None,
        })
        result = ti.interpret("necesito un martillo")
        assert result.items is None

    def test_ti_items_fallback_on_none(self):
        """When items=None, TI result should still have all other fields intact."""
        ti = self._make_interpreter({
            "intent": "product_search",
            "confidence": 0.85,
            "tone": "neutral",
            "items": None,
            "search_mode": "browse",
            "entities": {"product_terms": ["mecha"], "use_case": None, "material": None,
                         "dimensions": {}, "qty": None, "brand": None, "budget": None},
            "quote_reference": {"references_existing_quote": False, "line_hints": []},
            "reset_signal": False, "compound_message": False, "sub_commands": [],
            "escalation_reason": None, "referenced_offer_index": None,
        })
        result = ti.interpret("qué mechas tenés?")
        assert result.items is None
        assert result.intent == "product_search"
        assert result.confidence == 0.85

    def test_ti_items_ignored_for_quote_modify(self):
        """Items are ignored at gate level when intent is quote_modify (prevents multi-turn regression)."""
        ti = self._make_interpreter({
            "intent": "quote_modify",
            "confidence": 0.9,
            "tone": "neutral",
            "items": ["destornillador", "martillo"],  # TI emits items from context — must be ignored
            "search_mode": None,
            "entities": {"product_terms": ["martillo"], "use_case": None, "material": None,
                         "dimensions": {}, "qty": 1, "brand": None, "budget": None},
            "quote_reference": {"references_existing_quote": True, "line_hints": []},
            "reset_signal": False, "compound_message": False, "sub_commands": [],
            "escalation_reason": None, "referenced_offer_index": None,
        })
        result = ti.interpret("agregame un martillo")
        # items field IS populated on the interpretation object
        assert result.items == ["destornillador", "martillo"]
        # but intent is quote_modify — the bot.py gate will NOT fire for this case


# ── Slow E2E ─────────────────────────────────────────────────────────────────

def get_runtime_bot():
    try:
        from bot_sales.bot import SalesBot
        bot = SalesBot(tenant_id="ferreteria")
        return bot
    except Exception as e:
        pytest.skip(f"Runtime bot unavailable: {e}")


@pytest.mark.slow
class TestL2EndToEnd:

    def test_numbered_list_5_items_via_ti(self):
        """TI should extract items and quote should have 5 items (or close)."""
        bot = get_runtime_bot()
        session_id = "l2_e2e_numbered_5_items"
        message = (
            "Hola, necesito presupuesto:\n"
            "1) 50 tornillos autoperforantes 3 pulgadas\n"
            "2) 5 mechas de 6mm\n"
            "3) 5 mechas de 8mm\n"
            "4) 1 amoladora chica\n"
            "5) 4 discos de corte 4 1/2\""
        )
        reply = bot.process_message(session_id, message)
        sess = bot.sessions.get(session_id, {})

        # Check TI extracted items
        ti_data = sess.get("last_turn_interpretation", {})
        ti_items = ti_data.get("items")

        active_quote = sess.get("active_quote", [])
        assert len(active_quote) >= 3, (
            f"Expected ≥3 items in quote, got {len(active_quote)}. "
            f"ti_items={ti_items}\nreply={reply[:300]}"
        )

    def test_bullet_list_via_ti(self):
        """Bullet list — TI extracts items, quote has ≥3."""
        bot = get_runtime_bot()
        session_id = "l2_e2e_bullet_list"
        message = (
            "necesito comprar:\n"
            "- mecha 6mm\n"
            "- mecha 8mm\n"
            "- destornillador phillips\n"
            "- martillo"
        )
        reply = bot.process_message(session_id, message)
        sess = bot.sessions.get(session_id, {})
        active_quote = sess.get("active_quote", [])
        assert len(active_quote) >= 3, (
            f"Expected ≥3 items, got {len(active_quote)}. reply={reply[:300]}"
        )
