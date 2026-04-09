from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from Planning.ab_testing import ABTestingEngine
from Planning.flow_manager import SalesFlowManager
from Planning.followup_scheduler import FollowupScheduler
from Planning.output_contract import OutputContractParser
from Planning.pipeline import PipelineStage, compute_missing_fields
from Planning.playbook_router import PlaybookRouter


def _now() -> datetime:
    return datetime(2026, 2, 17, 12, 0, 0)


def test_compute_missing_fields_requires_sales_minimum():
    missing = compute_missing_fields({})
    assert "product_family" in missing
    assert "model" in missing
    assert "storage" in missing
    assert "condition" in missing
    assert "payment_preference" in missing
    assert "urgency" in missing


def test_compute_missing_fields_card_requires_installments_flag():
    missing = compute_missing_fields(
        {
            "product_family": "Herramienta",
            "model": "Herramienta 15",
            "storage": "128GB",
            "condition": "new_sealed",
            "payment_preference": "card",
            "urgency": "today",
        }
    )
    assert missing == ["needs_installments"]


def test_missing_fields_reply_asks_max_two_questions():
    manager = SalesFlowManager()
    output = manager.process_input("s1", "hola, quiero info", now=_now())
    assert output["cta"]["type"] == "ASK_TWO_FIELDS"
    assert output["reply_text"].count("?") <= 2


def test_stage_transition_new_to_qualified():
    manager = SalesFlowManager()
    output = manager.process_input(
        "s2",
        "Quiero Herramienta 15 128gb nuevo, pago transferencia y lo necesito hoy",
        now=_now(),
    )
    assert output["stage"] == PipelineStage.QUALIFIED.value
    assert output["stage_update"]["from_stage"] == PipelineStage.NEW.value
    assert output["stage_update"]["to_stage"] == PipelineStage.QUALIFIED.value


def test_stage_transition_qualified_to_quoted_on_exact_price():
    manager = SalesFlowManager()
    now = _now()
    manager.process_input(
        "s3",
        "Busco Herramienta 15 128gb nuevo, pago efectivo, lo necesito hoy",
        now=now,
    )
    output = manager.process_input("s3", "Pasame precio final exacto", now=now + timedelta(minutes=5))
    assert output["stage"] == PipelineStage.QUOTED.value


def test_stage_transition_quoted_to_negotiating_on_price_objection():
    manager = SalesFlowManager()
    now = _now()
    manager.process_input("s4", "Quiero Herramienta 15 128gb nuevo pago transferencia hoy", now=now)
    manager.process_input("s4", "precio final exacto", now=now + timedelta(minutes=3))
    output = manager.process_input("s4", "Está caro, ¿mejor precio?", now=now + timedelta(minutes=6))
    assert output["stage"] == PipelineStage.NEGOTIATING.value
    assert output["objection_type"] == "PRICE_OBJECTION"


def test_stage_transition_negotiating_to_won_on_high_intent():
    manager = SalesFlowManager()
    now = _now()
    manager.process_input("s5", "Herramienta 15 128gb nuevo, transferencia, hoy", now=now)
    manager.process_input("s5", "precio final exacto", now=now + timedelta(minutes=2))
    manager.process_input("s5", "está caro", now=now + timedelta(minutes=4))
    output = manager.process_input("s5", "Te pago ahora, pasame link", now=now + timedelta(minutes=6))
    assert output["stage"] == PipelineStage.WON.value
    assert output["cta"]["type"] == "PAYMENT_LINK"


def test_playbook_router_returns_objection_specific_snippet():
    router = PlaybookRouter("Planning/sales_playbook.md")
    snippets = router.get_playbook_snippets("OBJECTION_PRICE", PipelineStage.NEGOTIATING)
    text = " ".join(snippets).lower()
    assert "precio" in text
    assert len(text) < 600


def test_playbook_router_returns_trust_snippet():
    router = PlaybookRouter("Planning/sales_playbook.md")
    snippets = router.get_playbook_snippets("OBJECTION_TRUST", PipelineStage.NEGOTIATING)
    text = " ".join(snippets).lower()
    assert "serial" in text or "garantía oficial del fabricante" in text or "garantia oficial del fabricante" in text


def test_output_contract_parser_accepts_valid_json():
    parser = OutputContractParser()
    raw = """
    {
      "reply_text": "Perfecto, cerramos hoy.",
      "intent": "HIGH_INTENT_SIGNAL",
      "stage": "QUOTED",
      "stage_update": null,
      "missing_fields": [],
      "extracted_entities": {"product_family":"Herramienta"},
      "objection_type": null,
      "recommended_offer": [
        {"variant":"A","product_config":"Herramienta 15 128GB","price":"USD 900","why":"Ahorro"},
        {"variant":"B","product_config":"Herramienta 15 256GB","price":"USD 980","why":"Más valor"}
      ],
      "cta": {"type":"RESERVE_NOW","text":"¿Te lo reservo ahora?"},
      "next_task": null,
      "confidence": 0.9,
      "human_handoff": {"enabled": false, "reason": null}
    }
    """
    parsed = parser.parse(raw)
    assert parsed.stage == PipelineStage.QUOTED
    assert parsed.confidence == 0.9


def test_output_contract_parser_retries_with_format_fixer():
    parser = OutputContractParser()
    invalid = "not json"

    def fixer(_: str, __: str) -> str:
        return """
        {
          "reply_text":"ok",
          "intent":"GENERIC_INFO",
          "stage":"NEW",
          "stage_update": null,
          "missing_fields":["model"],
          "extracted_entities":{},
          "objection_type":null,
          "recommended_offer":[],
          "cta":{"type":"ASK_TWO_FIELDS","text":"decime modelo"},
          "next_task": null,
          "confidence":0.5,
          "human_handoff":{"enabled":false,"reason":null}
        }
        """

    parsed = parser.parse(invalid, format_fixer=fixer, max_attempts=2)
    assert parsed.intent == "GENERIC_INFO"


def test_output_contract_parser_raises_when_invalid_and_no_fixer():
    parser = OutputContractParser()
    with pytest.raises(ValueError):
        parser.parse("not json", max_attempts=1)


def test_followup_sequence_for_quoted_is_created():
    scheduler = FollowupScheduler()
    state = {"followup_plan": [], "followup_sent_count": 0}
    scheduler.ensure_sequence(state, stage=PipelineStage.QUOTED, objection_type=None, now=_now())
    assert len(state["followup_plan"]) == 3


def test_followup_sequence_is_idempotent():
    scheduler = FollowupScheduler()
    state = {"followup_plan": [], "followup_sent_count": 0}
    scheduler.ensure_sequence(state, stage=PipelineStage.QUOTED, objection_type=None, now=_now())
    scheduler.ensure_sequence(state, stage=PipelineStage.QUOTED, objection_type=None, now=_now())
    keys = [row["key"] for row in state["followup_plan"]]
    assert len(keys) == len(set(keys))


def test_followup_due_after_24h():
    scheduler = FollowupScheduler()
    state = {"followup_plan": [], "followup_sent_count": 0}
    now = _now()
    scheduler.ensure_sequence(state, stage=PipelineStage.QUOTED, objection_type=None, now=now)
    due = scheduler.due_followups(state, now=now + timedelta(hours=24, minutes=1))
    assert any(item["key"] == "quoted_24h" for item in due)


def test_followup_caps_at_three():
    scheduler = FollowupScheduler(max_followups=3)
    state = {"followup_plan": [], "followup_sent_count": 0}
    now = _now()
    scheduler.ensure_sequence(state, stage=PipelineStage.QUOTED, objection_type=None, now=now)
    for key in ("quoted_24h", "quoted_48h", "quoted_144h"):
        scheduler.mark_sent(state, key, sent_at=now + timedelta(hours=24))
    due = scheduler.due_followups(state, now=now + timedelta(days=10))
    assert due == []


def test_followups_stop_on_reply():
    scheduler = FollowupScheduler()
    state = {"followup_plan": [], "followup_sent_count": 2}
    scheduler.ensure_sequence(state, stage=PipelineStage.QUOTED, objection_type=None, now=_now())
    scheduler.stop_on_user_reply(state)
    assert all(item["status"] != "pending" for item in state["followup_plan"])
    assert state["followup_sent_count"] == 0


def test_negotiating_price_followup_created():
    scheduler = FollowupScheduler()
    state = {"followup_plan": [], "followup_sent_count": 0}
    scheduler.ensure_sequence(state, stage=PipelineStage.NEGOTIATING, objection_type="PRICE_OBJECTION", now=_now())
    assert any(item["key"] == "negotiating_price_24h" for item in state["followup_plan"])


def test_negotiating_trust_followup_created():
    scheduler = FollowupScheduler()
    state = {"followup_plan": [], "followup_sent_count": 0}
    scheduler.ensure_sequence(state, stage=PipelineStage.NEGOTIATING, objection_type="TRUST_OBJECTION", now=_now())
    assert any(item["key"] == "negotiating_trust_24h" for item in state["followup_plan"])


def test_ab_variant_assignment_is_deterministic():
    engine = ABTestingEngine()
    v1 = engine.pick_variant("session-1", stage=PipelineStage.QUOTED, objection_type="PRICE_OBJECTION")
    v2 = engine.pick_variant("session-1", stage=PipelineStage.QUOTED, objection_type="PRICE_OBJECTION")
    assert v1 == v2
    assert v1 in {"A", "B"}


def test_ab_logging_reply_within_24h():
    engine = ABTestingEngine()
    state = {"ab_events": []}
    sent_at = _now()
    engine.log_outbound(
        state,
        variant="A",
        stage=PipelineStage.QUOTED,
        objection_type="PRICE_OBJECTION",
        created_at=sent_at,
    )
    engine.record_reply(state, replied_at=sent_at + timedelta(hours=4))
    assert state["ab_events"][0]["reply_within_24h"] is True


def test_ab_logging_stage_progress_within_7d():
    engine = ABTestingEngine()
    state = {"ab_events": []}
    sent_at = _now()
    engine.log_outbound(
        state,
        variant="B",
        stage=PipelineStage.QUOTED,
        objection_type="PRICE_OBJECTION",
        created_at=sent_at,
    )
    engine.record_stage_progress(state, new_stage=PipelineStage.NEGOTIATING, when=sent_at + timedelta(days=1))
    assert state["ab_events"][0]["stage_progress_within_7d"] is True


def test_ab_report_groups_by_stage_objection_variant():
    engine = ABTestingEngine()
    state = {"ab_events": []}
    now = _now()
    row = engine.log_outbound(
        state,
        variant="A",
        stage=PipelineStage.QUOTED,
        objection_type="PRICE_OBJECTION",
        created_at=now,
    )
    row["reply_within_24h"] = True
    row["stage_progress_within_7d"] = True
    row["final_outcome"] = "won"
    report = engine.report(state["ab_events"])
    assert report[0]["sent"] == 1
    assert report[0]["won_rate"] == 1.0


def test_handoff_triggered_for_custom_condition():
    manager = SalesFlowManager()
    output = manager.process_input(
        "h1",
        "Necesito Herramienta 15 128gb nuevo con factura A corporativa",
        now=_now(),
    )
    assert output["human_handoff"]["enabled"] is True
    assert output["next_task"]["type"] == "HUMAN_HANDOFF"


def test_handoff_triggered_for_repeated_objection_loop():
    manager = SalesFlowManager()
    now = _now()
    manager.process_input("h2", "Herramienta 15 128gb nuevo transferencia hoy", now=now)
    manager.process_input("h2", "precio final exacto", now=now + timedelta(minutes=2))
    manager.process_input("h2", "Está caro", now=now + timedelta(minutes=4))
    output = manager.process_input("h2", "Sigue caro", now=now + timedelta(minutes=6))
    assert output["human_handoff"]["enabled"] is True
    assert output["human_handoff"]["reason"] == "repeated_objection_loop"


def test_handoff_triggered_for_high_value_ready_to_pay():
    manager = SalesFlowManager()
    output = manager.process_input(
        "h3",
        "Quiero Herramienta 15 Pro 256gb nuevo, pago transferencia hoy, tengo USD 2500 y te pago ahora",
        now=_now(),
    )
    assert output["human_handoff"]["enabled"] is True
    assert output["human_handoff"]["reason"] == "high_value_ready_to_pay"


def test_flow_uses_price_objection_snippet_in_reply():
    manager = SalesFlowManager()
    now = _now()
    manager.process_input("snip-1", "Herramienta 15 128gb nuevo transferencia hoy", now=now)
    manager.process_input("snip-1", "precio final exacto", now=now + timedelta(minutes=2))
    output = manager.process_input("snip-1", "me parece caro", now=now + timedelta(minutes=4))
    assert output["objection_type"] == "PRICE_OBJECTION"
    assert "precio" in output["reply_text"].lower()


def test_when_missing_fields_empty_response_contains_offer_and_cta():
    manager = SalesFlowManager()
    output = manager.process_input(
        "offers-1",
        "Busco Herramienta 15 128gb nuevo, pago usdt, lo necesito hoy",
        now=_now(),
    )
    assert output["missing_fields"] == []
    assert len(output["recommended_offer"]) == 2
    assert output["cta"]["type"] in {"RESERVE_NOW", "PAYMENT_LINK"}


def test_invalid_model_output_triggers_handoff_task_and_safe_fallback():
    manager = SalesFlowManager(model_responder=lambda _: "not-json")
    output = manager.process_input(
        "invalid-1",
        "Quiero Herramienta 15 128gb nuevo, pago transferencia y lo necesito hoy",
        now=_now(),
    )
    assert output["human_handoff"]["enabled"] is True
    assert output["human_handoff"]["reason"] == "LLM_OUTPUT_INVALID"
    assert output["next_task"]["type"] == "HUMAN_HANDOFF"
    assert output["next_task"]["assigned_to"] == "owner"
    assert "¿Me repetís modelo y capacidad?" in output["reply_text"]

    state = manager._get_state("invalid-1")
    assert state["message_events"][-1]["status"] == "NEEDS_REVIEW"


def test_invalid_model_output_does_not_mutate_stage_or_duplicate_review_task():
    manager = SalesFlowManager(model_responder=lambda _: "broken")
    now = _now()
    first = manager.process_input(
        "invalid-2",
        "Quiero Herramienta 15 128gb nuevo, pago transferencia y lo necesito hoy",
        now=now,
    )
    second = manager.process_input(
        "invalid-2",
        "precio final exacto",
        now=now + timedelta(minutes=2),
    )

    state = manager._get_state("invalid-2")
    assert first["stage"] == PipelineStage.NEW.value
    assert second["stage"] == PipelineStage.NEW.value
    assert state["followup_plan"] == []
    assert state["review_task"]["reason"] == "LLM_OUTPUT_INVALID"
    assert state["review_task"]["assigned_to"] == "owner"
