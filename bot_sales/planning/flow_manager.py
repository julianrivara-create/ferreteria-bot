from __future__ import annotations

import copy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .ab_testing import ABTestingEngine
from .followup_scheduler import FollowupScheduler
from .intents import IntentClassifier, IntentResult, SalesIntent
from .output_contract import (
    CTA,
    ExtractedEntities,
    HandoffDecision,
    NextTask,
    OutputContractParser,
    RecommendedOffer,
    SalesResponseContract,
    StageUpdate,
)
from .pipeline import PipelineStage, StageDecision, compute_missing_fields, decide_stage
from .playbook_router import PlaybookRouter
from .prompts import DynamicPrompts


class SalesFlowManager:
    """
    Deterministic sales operator:
    - tracks pipeline stage
    - tracks missing close-blocking fields
    - routes objection playbook snippets
    - enforces CTA on every answer
    - schedules idempotent follow-ups
    - logs A/B variant outcomes
    """

    def __init__(
        self,
        *,
        playbook_path: str | None = None,
        llm_classifier: Callable[[str, list[dict]], str] | None = None,
        model_responder: Callable[[dict[str, Any]], str] | None = None,
        format_fixer: Callable[[str, str], str] | None = None,
    ):
        self.classifier = IntentClassifier()
        self.parser = OutputContractParser()
        self.followups = FollowupScheduler(max_followups=3)
        self.ab_engine = ABTestingEngine()
        self.session_states: dict[str, dict[str, Any]] = {}
        self.llm_classifier = llm_classifier
        self.model_responder = model_responder
        self.format_fixer = format_fixer

        resolved_playbook = playbook_path or str(Path(__file__).with_name("sales_playbook.md"))
        self.playbook = PlaybookRouter(resolved_playbook)

    def process_input(self, session_id: str, user_message: str, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.utcnow()
        state = self._get_state(session_id)
        working_state = copy.deepcopy(state)
        working_state["last_user_at"] = now

        intent_result = self.classifier.classify(
            user_message,
            working_state["history"],
            llm_classifier=self.llm_classifier,
        )
        intent = intent_result.intent
        objection_type = self.classifier.detect_objection_type(intent)

        extracted = self.classifier.extract_entities(user_message)
        self._merge_entities(working_state, extracted)
        self._update_flags_from_intent(working_state, intent, user_message)

        # User replied -> pause pending follow-ups and mark reply outcome for A/B.
        self.followups.stop_on_user_reply(working_state)
        self.ab_engine.record_reply(working_state, replied_at=now)

        self._update_objection_loop(working_state, objection_type)

        missing_fields = compute_missing_fields(working_state["entities"], intent_name=intent.value)
        current_stage = PipelineStage(working_state["stage"])
        stage_decision = decide_stage(
            current_stage=current_stage,
            intent_name=intent.value,
            context=working_state["entities"],
            missing_fields=missing_fields,
            objection_type=objection_type,
            now=now,
        )
        stage_update = self._apply_stage_decision(working_state, stage_decision, now)
        stage = PipelineStage(working_state["stage"])

        if stage in {PipelineStage.QUOTED, PipelineStage.NEGOTIATING}:
            self.followups.ensure_sequence(working_state, stage=stage, objection_type=objection_type, now=now)

        snippets = self.playbook.get_playbook_snippets(intent.value, stage)
        variant = self.ab_engine.pick_variant(session_id, stage=stage, objection_type=objection_type)
        variant_key = f"{session_id}:{stage.value}:{objection_type or 'NONE'}"
        system_prompt = DynamicPrompts.get_system_prompt(stage, snippets)

        if self.model_responder is not None:
            payload = self._model_payload(
                user_message=user_message,
                stage=stage,
                intent=intent,
                missing_fields=missing_fields,
                extracted=working_state["entities"],
                snippets=snippets,
                system_prompt=system_prompt,
            )
            raw = self.model_responder(payload)
            try:
                contract = self.parser.parse(raw, format_fixer=self.format_fixer, max_attempts=2)
            except ValueError:
                fallback = self._invalid_output_contract_response(
                    state=state,
                    session_id=session_id,
                    user_message=user_message,
                    now=now,
                )
                self._save_state(session_id, state)
                return fallback.model_dump(mode="json")
        else:
            contract = self._deterministic_contract(
                intent_result=intent_result,
                stage=stage,
                stage_update=stage_update,
                missing_fields=missing_fields,
                entities=working_state["entities"],
                objection_type=objection_type,
                snippets=snippets,
                variant=variant,
                variant_key=variant_key,
                now=now,
                user_message=user_message,
                objection_loops=working_state.get("objection_loops", 0),
            )

        working_state["history"].append({"role": "user", "content": user_message, "at": now.isoformat()})
        working_state["history"].append({"role": "assistant", "content": contract.reply_text, "at": now.isoformat()})

        self.ab_engine.log_outbound(
            working_state,
            variant=variant,
            stage=stage,
            objection_type=contract.objection_type,
            created_at=now,
        )
        self._append_message_event(
            working_state,
            status="SENT",
            reason=None,
            at=now,
            reply_text=contract.reply_text,
            stage=stage.value,
        )

        self._save_state(session_id, working_state)
        return contract.model_dump(mode="json")

    def process_due_followups(self, session_id: str, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.utcnow()
        state = self._get_state(session_id)
        due = self.followups.due_followups(state, now=now)
        if not due:
            return []

        generated_tasks: list[dict[str, Any]] = []
        for item in due:
            title, cta = self._followup_template(item["template"])
            task = {
                "type": "FOLLOWUP",
                "due_at": item["due_at"].isoformat(),
                "title": title,
                "cta": cta,
                "key": item["key"],
            }
            generated_tasks.append(task)
            self.followups.mark_sent(state, key=item["key"], sent_at=now)

        self._save_state(session_id, state)
        return generated_tasks

    def get_ab_report(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            state = self._get_state(session_id)
            return self.ab_engine.report(state.get("ab_events", []))
        merged: list[dict[str, Any]] = []
        for state in self.session_states.values():
            merged.extend(state.get("ab_events", []))
        return self.ab_engine.report(merged)

    def process_model_output(self, raw_output: str) -> dict[str, Any]:
        contract = self.parser.parse(raw_output, format_fixer=self.format_fixer, max_attempts=2)
        return contract.model_dump(mode="json")

    def _get_state(self, session_id: str) -> dict[str, Any]:
        if session_id not in self.session_states:
            self.session_states[session_id] = {
                "stage": PipelineStage.NEW.value,
                "history": [],
                "entities": {},
                "deal_events": [],
                "objection_loops": 0,
                "last_objection_type": None,
                "followup_plan": [],
                "followup_sent_count": 0,
                "ab_events": [],
                "last_user_at": None,
                "message_events": [],
                "review_task": None,
                "handoff_assignees": ["owner"],
                "handoff_rr_index": 0,
            }
        return self.session_states[session_id]

    def _save_state(self, session_id: str, state: dict[str, Any]) -> None:
        self.session_states[session_id] = state

    def _next_handoff_assignee(self, state: dict[str, Any]) -> str:
        assignees = state.get("handoff_assignees") or ["owner"]
        idx = int(state.get("handoff_rr_index", 0)) % len(assignees)
        assignee = assignees[idx]
        state["handoff_rr_index"] = (idx + 1) % len(assignees)
        return str(assignee)

    @staticmethod
    def _append_message_event(
        state: dict[str, Any],
        *,
        status: str,
        reason: str | None,
        at: datetime,
        reply_text: str,
        stage: str,
    ) -> None:
        events = state.setdefault("message_events", [])
        events.append(
            {
                "id": f"msg-event-{len(events)+1}",
                "status": status,
                "reason": reason,
                "at": at.isoformat(),
                "reply_text": reply_text,
                "stage": stage,
            }
        )

    def _invalid_output_contract_response(
        self,
        *,
        state: dict[str, Any],
        session_id: str,
        user_message: str,
        now: datetime,
    ) -> SalesResponseContract:
        review_task = state.get("review_task")
        if review_task and review_task.get("reason") == "LLM_OUTPUT_INVALID":
            assignee = str(review_task.get("assigned_to") or "owner")
        else:
            assignee = self._next_handoff_assignee(state)
            state["review_task"] = {
                "reason": "LLM_OUTPUT_INVALID",
                "assigned_to": assignee,
                "created_at": now.isoformat(),
            }

        fallback_reply = "Perfecto, lo reviso y te confirmo en un minuto. ¿Me repetís producto y variante?"
        stage = PipelineStage(state["stage"])
        entities = ExtractedEntities.model_validate(state.get("entities", {}))
        contract = SalesResponseContract(
            reply_text=fallback_reply,
            intent=SalesIntent.GENERIC_INFO.value,
            stage=stage,
            stage_update=None,
            missing_fields=["model", "condition"],
            extracted_entities=entities,
            objection_type=None,
            recommended_offer=[],
            cta=CTA(type="ASK_TWO_FIELDS", text="¿Me repetís producto y variante?"),
            next_task=NextTask(
                type="HUMAN_HANDOFF",
                due_at=now + timedelta(minutes=5),
                title=f"LLM output inválido ({session_id})",
                assigned_to=assignee,
            ),
            confidence=0.0,
            human_handoff=HandoffDecision(enabled=True, reason="LLM_OUTPUT_INVALID"),
            playbook_snippet=None,
            ab_variant=None,
            variant_key=None,
        )
        state["history"].append({"role": "user", "content": user_message, "at": now.isoformat()})
        state["history"].append({"role": "assistant", "content": contract.reply_text, "at": now.isoformat()})
        self._append_message_event(
            state,
            status="NEEDS_REVIEW",
            reason="LLM_OUTPUT_INVALID",
            at=now,
            reply_text=contract.reply_text,
            stage=stage.value,
        )
        return contract

    @staticmethod
    def _merge_entities(state: dict[str, Any], extracted: dict[str, Any]) -> None:
        entities = state.setdefault("entities", {})
        for key, value in extracted.items():
            if value is None:
                continue
            if key == "model" and isinstance(value, str):
                entities[key] = value.strip()
            else:
                entities[key] = value

    @staticmethod
    def _update_flags_from_intent(state: dict[str, Any], intent: SalesIntent, user_message: str) -> None:
        entities = state.setdefault("entities", {})
        msg = user_message.lower()

        if intent in {SalesIntent.HIGH_INTENT_SIGNAL, SalesIntent.BUYING_SIGNAL}:
            entities["ready_to_pay"] = True
        if intent == SalesIntent.LOST_SIGNAL:
            entities["force_lost"] = True
        if intent in {SalesIntent.EXACT_PRICE_REQUEST, SalesIntent.HIGH_INTENT_SIGNAL}:
            entities["quote_sent"] = True
        if any(token in msg for token in ("cotizacion", "cotización", "pasame precio", "opcion a", "opción b")):
            entities["quote_sent"] = True

        if "no tengo apuro" in msg or "mas adelante" in msg:
            entities["urgency"] = entities.get("urgency") or "this_month"

        # Extract rough budget number for handoff threshold.
        if entities.get("budget"):
            entities["budget_value"] = _budget_to_float(str(entities["budget"]))

    @staticmethod
    def _update_objection_loop(state: dict[str, Any], objection_type: str | None) -> None:
        if not objection_type:
            state["objection_loops"] = 0
            state["last_objection_type"] = None
            return
        if state.get("last_objection_type") == objection_type:
            state["objection_loops"] = int(state.get("objection_loops", 0)) + 1
        else:
            state["objection_loops"] = 1
            state["last_objection_type"] = objection_type

    def _apply_stage_decision(self, state: dict[str, Any], decision: StageDecision, now: datetime) -> StageUpdate | None:
        if decision.new_stage is None or not decision.reason:
            return None

        previous = PipelineStage(state["stage"])
        state["stage"] = decision.new_stage.value
        state["deal_events"].append(
            {
                "event_type": "stage_changed",
                "from_stage": previous.value,
                "to_stage": decision.new_stage.value,
                "stage_reason": decision.reason,
                "at": now.isoformat(),
            }
        )
        self.ab_engine.record_stage_progress(state, new_stage=decision.new_stage, when=now)
        if decision.new_stage in {PipelineStage.WON, PipelineStage.LOST}:
            self.ab_engine.record_final_outcome(state, outcome=decision.new_stage)
        return StageUpdate(from_stage=previous, to_stage=decision.new_stage, reason=decision.reason)

    def _deterministic_contract(
        self,
        *,
        intent_result: IntentResult,
        stage: PipelineStage,
        stage_update: StageUpdate | None,
        missing_fields: list[str],
        entities: dict[str, Any],
        objection_type: str | None,
        snippets: list[str],
        variant: str,
        variant_key: str,
        now: datetime,
        user_message: str,
        objection_loops: int,
    ) -> SalesResponseContract:
        handoff = self._handoff_decision(
            user_message=user_message,
            stage=stage,
            objection_loops=objection_loops,
            budget_value=float(entities.get("budget_value") or 0),
            ready_to_pay=bool(entities.get("ready_to_pay")),
        )

        recommended_offer: list[RecommendedOffer] = []
        if not missing_fields:
            recommended_offer = self._build_offer_options(entities=entities, variant=variant, objection_type=objection_type)

        if handoff.enabled:
            reply_text = "Te paso con un asesor comercial para cerrarlo ahora mismo con contexto completo."
            cta = CTA(type="HUMAN_HANDOFF", text="¿Te contacto por DM ahora para cerrar?")
            next_task = NextTask(
                type="HUMAN_HANDOFF",
                due_at=now + timedelta(minutes=5),
                title=f"Handoff comercial {entities.get('model') or entities.get('product_family') or 'lead'}",
            )
        elif missing_fields:
            reply_text = "¿Me podés repetir qué necesitás? Quiero asegurarme de armarte bien el pedido."
            cta = CTA(type="ASK_TWO_FIELDS", text="Respondeme esos datos y te paso opción A/B cerrada.")
            next_task = None
        else:
            confirm = self._confirm_line(stage=stage, intent=intent_result.intent, entities=entities)
            recommendation = self._recommendation_line(recommended_offer, snippets, objection_type, variant)
            cta = self._build_cta(intent=intent_result.intent, entities=entities)
            reply_text = f"{confirm} {recommendation} {cta.text}".strip()
            next_task = None

        return SalesResponseContract(
            reply_text=reply_text[:1180],
            intent=intent_result.intent.value,
            stage=stage,
            stage_update=stage_update,
            missing_fields=missing_fields,
            extracted_entities=ExtractedEntities.model_validate(entities),
            objection_type=objection_type,
            recommended_offer=recommended_offer,
            cta=cta,
            next_task=next_task,
            confidence=round(float(intent_result.confidence), 2),
            human_handoff=handoff,
            playbook_snippet=(snippets[0] if snippets else None),
            ab_variant=variant,
            variant_key=variant_key,
        )

    @staticmethod
    def _model_payload(
        *,
        user_message: str,
        stage: PipelineStage,
        intent: SalesIntent,
        missing_fields: list[str],
        extracted: dict[str, Any],
        snippets: list[str],
        system_prompt: str,
    ) -> dict[str, Any]:
        return {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "intent": intent.value,
            "stage": stage.value,
            "missing_fields": missing_fields,
            "extracted_entities": extracted,
            "playbook_snippets": snippets,
            "output_contract": "SalesResponseContract JSON",
        }

    @staticmethod
    def _questions_for_missing(missing_fields: list[str]) -> list[str]:
        map_q = {
            "product_family": "¿Qué categoría o rubro estás buscando?",
            "model": "¿Qué modelo exacto querés?",
            "storage": "¿Qué capacidad, dosis o medida preferís?",
            "condition": "¿Qué variante necesitás (color, talle, presentación, etc.)?",
            "payment_preference": "¿Pagás por efectivo, transferencia, tarjeta o pasarela digital?",
            "needs_installments": "¿Necesitás cuotas?",
            "urgency": "¿Lo necesitás hoy, esta semana o este mes?",
            "color_preference": "¿Tenés preferencia de color?",
            "delivery_method": "¿Preferís envío o entrega coordinada?",
        }
        return [map_q.get(field, f"¿Me confirmás {field}?") for field in missing_fields][:2]

    @staticmethod
    def _build_offer_options(
        *,
        entities: dict[str, Any],
        variant: str,
        objection_type: str | None,
    ) -> list[RecommendedOffer]:
        base_family = entities.get("product_family") or "Producto"
        base_model = entities.get("model") or base_family
        storage = entities.get("storage") or "estándar"
        condition = entities.get("condition") or "disponible"
        # Prices must come from catalog data only — never calculated from the user's
        # stated budget. budget_value is used solely in _handoff_decision to trigger
        # high-value handoffs, NOT to derive offer prices.
        tone_a = "directa" if variant == "A" else "empática"
        tone_b = "empática" if variant == "A" else "directa"
        reason_tail = "prioriza ahorro sin perder valor." if objection_type == "PRICE_OBJECTION" else "mantiene mejor equilibrio costo/beneficio."

        return [
            RecommendedOffer(
                variant="A",
                product_config=f"{base_model} {storage} ({condition})",
                price=None,  # catalog-sourced only — never invent from budget
                why=f"Propuesta {tone_a}: {reason_tail}",
            ),
            RecommendedOffer(
                variant="B",
                product_config=f"{base_model} opción premium ({condition})",
                price=None,  # catalog-sourced only — never invent from budget
                why=f"Propuesta {tone_b}: sube valor percibido para mejor cierre.",
            ),
        ]

    @staticmethod
    def _confirm_line(*, stage: PipelineStage, intent: SalesIntent, entities: dict[str, Any]) -> str:
        model = entities.get("model") or entities.get("product_family") or "equipo"
        if stage == PipelineStage.NEGOTIATING:
            return f"Perfecto, tomo tu duda sobre {model}."
        if intent in {SalesIntent.HIGH_INTENT_SIGNAL, SalesIntent.BUYING_SIGNAL}:
            return f"Excelente, ya estamos para cerrar {model}."
        return f"Perfecto, tengo tu búsqueda de {model}."

    @staticmethod
    def _recommendation_line(
        offers: list[RecommendedOffer],
        snippets: list[str],
        objection_type: str | None,
        variant: str,
    ) -> str:
        if offers:
            offer_a = offers[0]
            offer_b = offers[1] if len(offers) > 1 else None
            if variant == "A":
                line = f"Te recomiendo A: {offer_a.product_config}"
                if offer_a.price:
                    line += f" ({offer_a.price})"
                if offer_b:
                    line += f". También B: {offer_b.product_config}"
            else:
                line = "Entiendo que quieras decidir con seguridad."
                line += f" A: {offer_a.product_config}"
                if offer_b:
                    line += f" | B: {offer_b.product_config}"

            if objection_type and snippets:
                line += f". {snippets[0]}"
            return line

        if snippets:
            return snippets[0]
        return "Con esa info te preparo una opción concreta para avanzar."

    @staticmethod
    def _build_cta(*, intent: SalesIntent, entities: dict[str, Any]) -> CTA:
        if intent in {SalesIntent.HIGH_INTENT_SIGNAL, SalesIntent.BUYING_SIGNAL}:
            if entities.get("payment_preference") in {"transfer", "usdt", "cash"}:
                return CTA(type="PAYMENT_LINK", text="¿Te envío el paso de pago ahora?")
            return CTA(type="RESERVE_NOW", text="¿Te lo reservo ahora para que no se libere?")
        return CTA(type="RESERVE_NOW", text="¿Preferís que avancemos con opción A o B?")

    @staticmethod
    def _handoff_decision(
        *,
        user_message: str,
        stage: PipelineStage,
        objection_loops: int,
        budget_value: float,
        ready_to_pay: bool,
    ) -> HandoffDecision:
        msg = user_message.lower()
        unsupported = (
            "permuta",
            "canje",
            "factura a",
            "corporativo",
            "leasing",
            "orden de compra",
        )
        if any(token in msg for token in unsupported):
            return HandoffDecision(enabled=True, reason="custom_condition_not_supported")
        if objection_loops >= 2 and stage == PipelineStage.NEGOTIATING:
            return HandoffDecision(enabled=True, reason="repeated_objection_loop")
        if ready_to_pay and budget_value >= 100000:
            return HandoffDecision(enabled=True, reason="high_value_ready_to_pay")
        return HandoffDecision(enabled=False, reason=None)

    @staticmethod
    def _followup_template(template: str) -> tuple[str, str]:
        if template == "quoted_followup_1":
            return ("Follow-up 24h post-quote", "¿Te cierro A o B hoy?")
        if template == "quoted_followup_2":
            return ("Follow-up 48h post-quote", "Si querés, te paso una opción más económica A.")
        if template == "quoted_followup_3":
            return ("Follow-up final 5-7d", "Lo dejamos abierto y retomamos cuando te quede cómodo.")
        if template == "negotiation_price_reassurance":
            return ("Follow-up objeción precio", "Te paso alternativa más accesible con respaldo oficial del fabricante.")
        if template == "negotiation_trust_reassurance":
            return ("Follow-up objeción confianza", "Te comparto detalle de garantía y trazabilidad del producto.")
        return ("Follow-up", "¿Querés que lo retomemos?")


def _budget_to_float(raw: str) -> float:
    if not raw:
        return 0.0
    numbers = "".join(ch for ch in raw if ch.isdigit() or ch in {".", ","})
    if not numbers:
        return 0.0
    # Keep last decimal separator only.
    if numbers.count(",") > 1:
        numbers = numbers.replace(",", "")
    if numbers.count(".") > 1:
        numbers = numbers.replace(".", "")
    numbers = numbers.replace(",", ".")
    try:
        return float(numbers)
    except ValueError:
        return 0.0
