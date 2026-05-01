"""
Unit and integration tests for TurnInterpreter routing.

These tests cover the 3 critical routing cases previously handled by the
`core/IntentClassifier` bypass in `process_message()`:

  1. Greeting ("hola") -> small_talk -> OfftopicHandler, not a questionnaire
  2. Customer info ("me llamo Juan") -> conversational path, not OfftopicHandler fallback
  3. Handoff ("quiero hablar con un humano") -> escalate -> EscalationHandler

All tests PASS with the current code (IntentClassifier bypass active) and
must continue to pass after Commit 3 removes that bypass.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from bot_sales.bot import SalesBot
from bot_sales.core.database import Database
from bot_sales.routing.turn_interpreter import (
    TurnInterpreter,
    TurnInterpretation,
    VALID_INTENTS,
)

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def build_bot(tmp_path: Path, db_name: str = "routing_test.db") -> SalesBot:
    catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    profile = yaml.safe_load(
        (ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8")
    )
    db = Database(
        db_file=str(tmp_path / db_name),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / f"{db_name}.log"),
    )
    return SalesBot(
        db=db,
        api_key="",
        tenant_id="ferreteria",
        tenant_profile=profile,
        sandbox_mode=True,
    )


def _full_interp(intent: str, confidence: float = 0.92, tone: str = "neutral") -> dict:
    """Build a complete TurnInterpreter JSON payload."""
    return {
        "intent": intent,
        "confidence": confidence,
        "tone": tone,
        "policy_topic": None,
        "search_mode": None,
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
    }


_QUESTIONNAIRE_MARKERS = ("cotizarte", "urgencia", "product_family", "¿con qué", "¿para cuándo")


def _is_questionnaire(response: str) -> bool:
    r = response.lower()
    return any(m in r for m in _QUESTIONNAIRE_MARKERS)


# ---------------------------------------------------------------------------
# Unit tests: TurnInterpreter JSON parsing (no LLM, no bot.py)
# ---------------------------------------------------------------------------

class TestTurnInterpreterParsing:
    """Pure unit tests — mock LLM client, exercise _parse_response and from_dict."""

    def _make_interpreter(self, response_content: str) -> TurnInterpreter:
        llm = MagicMock()
        llm.model = "gpt-4o-mini"
        llm.max_tokens = 200
        llm.temperature = 0.0
        llm.send_message.return_value = {"content": response_content}
        return TurnInterpreter(llm)

    def test_small_talk_greeting(self):
        ti = self._make_interpreter(json.dumps(_full_interp("small_talk", 0.95)))
        result = ti.interpret("hola")
        assert result.intent == "small_talk"
        assert result.confidence == pytest.approx(0.95)
        assert not result.is_low_confidence()

    def test_escalate_intent(self):
        ti = self._make_interpreter(json.dumps(_full_interp("escalate", 0.90, "frustrated")))
        result = ti.interpret("quiero hablar con un humano")
        assert result.intent == "escalate"
        assert result.tone == "frustrated"
        assert not result.is_low_confidence()

    def test_unknown_on_json_parse_failure(self):
        ti = self._make_interpreter("not valid json at all")
        result = ti.interpret("test")
        assert result.intent == "unknown"
        assert result.is_low_confidence()

    def test_confidence_clamped_to_one(self):
        ti = self._make_interpreter(json.dumps({**_full_interp("small_talk"), "confidence": 99.0}))
        result = ti.interpret("hola")
        assert result.confidence <= 1.0

    def test_old_schema_intent_becomes_unknown(self):
        """IntentClassifier schema values (GREETING_CHAT, QUOTATION, etc.) are invalid here."""
        ti = self._make_interpreter(json.dumps({**_full_interp("small_talk"), "intent": "GREETING_CHAT"}))
        result = ti.interpret("hola")
        assert result.intent == "unknown"

    def test_markdown_fenced_json_parsed(self):
        raw = "```json\n" + json.dumps(_full_interp("policy_faq", 0.88)) + "\n```"
        ti = self._make_interpreter(raw)
        result = ti.interpret("¿cuáles son los horarios?")
        assert result.intent == "policy_faq"

    def test_low_confidence_boundary(self):
        below = TurnInterpretation(intent="unknown", confidence=0.54)
        at = TurnInterpretation(intent="small_talk", confidence=0.55)
        assert below.is_low_confidence()
        assert not at.is_low_confidence()

    def test_reset_signal_parsed(self):
        payload = {**_full_interp("unknown"), "reset_signal": True}
        ti = self._make_interpreter(json.dumps(payload))
        result = ti.interpret("borrá todo y empezá de cero")
        assert result.reset_signal is True

    def test_entities_extracted(self):
        payload = _full_interp("product_search", 0.9)
        payload["entities"]["product_terms"] = ["taladro", "percutor"]
        payload["entities"]["qty"] = 3
        ti = self._make_interpreter(json.dumps(payload))
        result = ti.interpret("necesito 3 taladros percutores")
        assert "taladro" in result.entities.product_terms
        assert result.entities.qty == 3

    def test_customer_info_in_valid_intents(self):
        """customer_info must be a recognized intent after Commit 2."""
        assert "customer_info" in VALID_INTENTS

    def test_customer_info_parses_correctly(self):
        ti = self._make_interpreter(json.dumps(_full_interp("customer_info", 0.85)))
        result = ti.interpret("me llamo Juan, soy de Constructora ABC")
        assert result.intent == "customer_info"
        assert not result.is_low_confidence()


# ---------------------------------------------------------------------------
# Unit tests: _should_bypass_sales_intelligence regex
# ---------------------------------------------------------------------------

class TestShouldBypassSalesIntelligence:
    """Direct tests of the regex that routes conversational messages past SalesFlowManager."""

    def _bypass(self, bot: SalesBot, text: str) -> bool:
        return bot._should_bypass_sales_intelligence(text)

    def test_me_llamo_matches(self, tmp_path):
        bot = build_bot(tmp_path, "bypass1.db")
        try:
            assert self._bypass(bot, "Me llamo Juan")
            assert self._bypass(bot, "me llamo Pedro García")
        finally:
            bot.close()

    def test_soy_x_matches(self, tmp_path):
        bot = build_bot(tmp_path, "bypass2.db")
        try:
            assert self._bypass(bot, "Soy Pedro de Constructora ABC")
        finally:
            bot.close()

    def test_hola_matches(self, tmp_path):
        bot = build_bot(tmp_path, "bypass3.db")
        try:
            assert self._bypass(bot, "hola")
            assert self._bypass(bot, "Buenas tardes")
        finally:
            bot.close()

    def test_short_non_product_matches(self, tmp_path):
        bot = build_bot(tmp_path, "bypass4.db")
        try:
            assert self._bypass(bot, "ok")
            assert self._bypass(bot, "dale")
        finally:
            bot.close()

    def test_product_request_does_not_match(self, tmp_path):
        bot = build_bot(tmp_path, "bypass5.db")
        try:
            assert not self._bypass(bot, "Necesito 100 tornillos M6 de acero inoxidable")
            assert not self._bypass(bot, "Quiero cotizar 3 taladros para obra")
        finally:
            bot.close()


# ---------------------------------------------------------------------------
# Integration tests: the 3 critical bypass cases
# ---------------------------------------------------------------------------

class TestCriticalBypassRouting:
    """
    Verify the 3 conversational intents previously handled by core/IntentClassifier
    bypass continue to work correctly after the refactor.

    Strategy: mock IntentClassifier.classify() to return QUOTATION (non-bypass)
    so TurnInterpreter always runs even in current code. Mock TurnInterpreter and
    handlers. Assertions are behavior-based (no questionnaire, correct response).
    """

    def _mock_no_bypass(self, monkeypatch):
        """Force core/IntentClassifier to return QUOTATION so the bypass never fires."""
        monkeypatch.setattr(
            "bot_sales.core.intent_classifier.IntentClassifier.classify",
            lambda self, msg, **kw: {"intent": "QUOTATION", "confidence": 0.5},
        )

    def test_greeting_routes_to_offtopic_handler(self, tmp_path, monkeypatch):
        """'hola' -> small_talk (high confidence) -> OfftopicHandler, not a questionnaire."""
        bot = build_bot(tmp_path, "t_greeting.db")
        try:
            self._mock_no_bypass(monkeypatch)
            monkeypatch.setattr(
                bot.turn_interpreter, "interpret",
                lambda *a, **kw: TurnInterpretation(intent="small_talk", confidence=0.92),
            )
            monkeypatch.setattr(
                bot.offtopic_handler, "handle",
                lambda **kw: "¡Hola! ¿En qué te puedo ayudar hoy?",
            )

            response = bot.process_message("s_greeting", "hola")

            assert response is not None
            assert not _is_questionnaire(response)
            assert any(w in response.lower() for w in ["hola", "ayudar", "puedo"])
            assert bot.sessions.get("s_greeting", {}).get("active_quote", []) == []
        finally:
            bot.close()

    def test_customer_info_does_not_hit_offtopic_fallback(self, tmp_path, monkeypatch):
        """
        'Me llamo Juan' must NOT get "fuera de lo que manejo" (OfftopicHandler fallback).
        Path: unknown/customer_info (low confidence) -> falls through ->
        _should_bypass_sales_intelligence() matches 'me llamo' -> _chat_with_functions().
        """
        bot = build_bot(tmp_path, "t_custinfo.db")
        try:
            self._mock_no_bypass(monkeypatch)
            # Low confidence unknown -> all handler guards fail -> falls through to bypass check
            monkeypatch.setattr(
                bot.turn_interpreter, "interpret",
                lambda *a, **kw: TurnInterpretation(intent="unknown", confidence=0.4),
            )
            monkeypatch.setattr(bot, "_chat_with_functions", lambda sid: "Anotado, Juan. ¿Qué necesitás cotizar?")
            monkeypatch.setattr(bot, "_run_sales_intelligence", lambda sid, msg: None)

            response = bot.process_message("s_custinfo", "Me llamo Juan")

            assert response is not None
            assert "fuera de lo que manejo" not in response
            assert not _is_questionnaire(response)
            assert bot.sessions.get("s_custinfo", {}).get("active_quote", []) == []
        finally:
            bot.close()

    def test_customer_info_falls_through_to_main_llm(self, tmp_path, monkeypatch):
        """
        'Me llamo Juan' with customer_info intent (Commit 2+) must NOT hit OfftopicHandler.
        It falls through _try_ferreteria_intent_route() -> None ->
        _should_bypass_sales_intelligence() matches 'me llamo' -> _chat_with_functions().
        """
        bot = build_bot(tmp_path, "t_custinfo2.db")
        try:
            self._mock_no_bypass(monkeypatch)
            monkeypatch.setattr(
                bot.turn_interpreter, "interpret",
                lambda *a, **kw: TurnInterpretation(intent="customer_info", confidence=0.88),
            )
            monkeypatch.setattr(bot, "_chat_with_functions", lambda sid: "Anotado, Juan. ¿Qué necesitás cotizar?")
            monkeypatch.setattr(bot, "_run_sales_intelligence", lambda sid, msg: None)

            response = bot.process_message("s_custinfo2", "Me llamo Juan")

            assert response is not None
            assert "fuera de lo que manejo" not in response
            assert not _is_questionnaire(response)
        finally:
            bot.close()

    def test_handoff_request_triggers_escalation_handler(self, tmp_path, monkeypatch):
        """
        'Quiero hablar con un humano' -> escalate (high confidence) -> EscalationHandler.
        Must not produce a product questionnaire.
        """
        bot = build_bot(tmp_path, "t_escalate.db")
        try:
            self._mock_no_bypass(monkeypatch)
            monkeypatch.setattr(
                bot.turn_interpreter, "interpret",
                lambda *a, **kw: TurnInterpretation(intent="escalate", confidence=0.92),
            )
            monkeypatch.setattr(
                bot.escalation_handler, "handle",
                lambda **kw: "Te conecto con un asesor ahora mismo.",
            )

            response = bot.process_message("s_escalate", "quiero hablar con un humano")

            assert response is not None
            assert not _is_questionnaire(response)
            assert any(w in response.lower() for w in ["asesor", "conect", "humano", "persona", "alguien"])
        finally:
            bot.close()
