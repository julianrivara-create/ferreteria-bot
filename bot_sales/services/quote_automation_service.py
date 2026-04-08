from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.channels.whatsapp_meta import WhatsAppMeta

from ..ferreteria_automation import build_quote_ready_followup, evaluate_quote_automation
from ..knowledge.loader import KnowledgeLoader
from ..persistence.quote_store import QuoteStore, utc_now_iso
from .quote_service import QuoteService


class QuoteAutomationError(RuntimeError):
    pass


class QuoteAutomationService:
    def __init__(
        self,
        store: QuoteStore,
        *,
        tenant_id: str = "ferreteria",
        tenant_profile: Optional[Dict[str, Any]] = None,
    ):
        self.store = store
        self.tenant_id = tenant_id
        self.tenant_profile = tenant_profile or {}
        self.quote_service = QuoteService(store, tenant_id=tenant_id)
        self.knowledge_loader = KnowledgeLoader(tenant_id=tenant_id, tenant_profile=self.tenant_profile)

    def _knowledge(self) -> Dict[str, Any]:
        return self.knowledge_loader.load()

    def _quote_items(self, quote: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.quote_service.build_runtime_items_from_lines(quote.get("lines") or [])

    def _context_json(self, decision: Dict[str, Any]) -> str:
        payload = {
            "eligible": bool(decision.get("eligible")),
            "followup_type": decision.get("followup_type"),
            "risk_flags": decision.get("risk_flags") or [],
            "decision_summary": decision.get("decision_summary"),
            "ready_for_send": bool(decision.get("ready_for_send")),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _update_automation_fields(self, quote_id: str, decision: Dict[str, Any]) -> None:
        self.store.update_quote_header(
            quote_id,
            automation_state=decision.get("automation_state") or "manual_only",
            automation_reason=decision.get("blocked_reason"),
            automation_context_json=self._context_json(decision),
            automation_updated_at=utc_now_iso(),
        )

    def refresh_quote_automation(self, quote_id: str, actor: str = "system") -> Dict[str, Any]:
        quote = self.store.get_quote(quote_id)
        if not quote:
            raise QuoteAutomationError("Quote not found")
        items = self._quote_items(quote)
        decision = evaluate_quote_automation(quote, items, knowledge=self._knowledge())
        previous_state = str(quote.get("automation_state") or "manual_only")
        previous_reason = quote.get("automation_reason")
        previous_context = json.dumps(quote.get("automation_context") or {}, ensure_ascii=False, sort_keys=True)
        next_context = self._context_json(decision)

        with self.store.transaction():
            self._update_automation_fields(quote_id, decision)
            if (
                previous_state != decision.get("automation_state")
                or previous_reason != decision.get("blocked_reason")
                or previous_context != next_context
            ):
                self.store.append_event(
                    quote_id,
                    "automation_evaluated",
                    "operator" if actor != "system" else "system",
                    actor_ref=actor,
                    payload={
                        "automation_state": decision.get("automation_state"),
                        "blocked_reason": decision.get("blocked_reason"),
                        "risk_flags": decision.get("risk_flags") or [],
                        "ready_for_send": bool(decision.get("ready_for_send")),
                    },
                )
        quote = self.store.get_quote(quote_id)
        return {"quote": quote, "decision": decision}

    def send_quote_ready_followup(self, quote_id: str, actor: str = "system") -> Dict[str, Any]:
        refreshed = self.refresh_quote_automation(quote_id, actor=actor)
        quote = refreshed["quote"] or {}
        decision = refreshed["decision"] or {}
        items = self._quote_items(quote)

        if not decision.get("eligible") or quote.get("automation_state") != "eligible_for_auto_followup":
            raise QuoteAutomationError("Quote is not eligible for automated follow-up")
        if str(quote.get("channel") or "") != "whatsapp":
            raise QuoteAutomationError("Automated follow-up only supports WhatsApp")
        customer_ref = str(quote.get("customer_ref") or "").strip()
        if not customer_ref:
            raise QuoteAutomationError("Quote is missing customer reference")
        if int(quote.get("auto_followup_count") or 0) > 0:
            raise QuoteAutomationError("Automated follow-up was already sent")

        message = build_quote_ready_followup(quote, items)
        result = WhatsAppMeta.send_reply(customer_ref, message)
        status = str((result or {}).get("status") or "sent")

        with self.store.transaction():
            if status == "sent":
                self.store.update_quote_header(
                    quote_id,
                    automation_state="awaiting_customer_confirmation",
                    automation_reason=None,
                    automation_context_json=json.dumps(
                        {
                            "eligible": True,
                            "followup_type": decision.get("followup_type"),
                            "decision_summary": "Standard automated follow-up sent.",
                            "risk_flags": [],
                            "ready_for_send": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    automation_updated_at=utc_now_iso(),
                    last_auto_followup_at=utc_now_iso(),
                    auto_followup_count=int(quote.get("auto_followup_count") or 0) + 1,
                )
                self.store.append_event(
                    quote_id,
                    "automation_followup_sent",
                    "operator" if actor != "system" else "system",
                    actor_ref=actor,
                    payload={
                        "channel": "whatsapp",
                        "followup_type": decision.get("followup_type"),
                        "message": message,
                    },
                )
            else:
                self.store.update_quote_header(
                    quote_id,
                    automation_state="automation_blocked",
                    automation_reason="followup_send_failed",
                    automation_context_json=json.dumps(
                        {
                            "eligible": False,
                            "followup_type": decision.get("followup_type"),
                            "decision_summary": "Follow-up send failed and needs operator review.",
                            "risk_flags": ["followup_send_failed"],
                            "ready_for_send": False,
                            "send_result": result,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    automation_updated_at=utc_now_iso(),
                )
                self.store.append_event(
                    quote_id,
                    "automation_followup_failed",
                    "operator" if actor != "system" else "system",
                    actor_ref=actor,
                    payload={
                        "channel": "whatsapp",
                        "followup_type": decision.get("followup_type"),
                        "message": message,
                        "result": result,
                    },
                )

        return {"quote": self.store.get_quote(quote_id), "send_result": result}

    def block_automation(self, quote_id: str, reason: str, actor: str) -> Dict[str, Any]:
        quote = self.store.get_quote(quote_id)
        if not quote:
            raise QuoteAutomationError("Quote not found")
        with self.store.transaction():
            self.store.update_quote_header(
                quote_id,
                automation_state="automation_blocked",
                automation_reason=reason,
                automation_context_json=json.dumps(
                    {
                        "eligible": False,
                        "decision_summary": "Automation manually blocked by operator.",
                        "risk_flags": [reason] if reason else [],
                        "ready_for_send": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                automation_updated_at=utc_now_iso(),
            )
            self.store.append_event(
                quote_id,
                "automation_manually_blocked",
                "operator",
                actor_ref=actor,
                payload={"reason": reason},
            )
        return {"quote": self.store.get_quote(quote_id)}

    def reset_automation(self, quote_id: str, actor: str) -> Dict[str, Any]:
        quote = self.store.get_quote(quote_id)
        if not quote:
            raise QuoteAutomationError("Quote not found")
        with self.store.transaction():
            self.store.update_quote_header(
                quote_id,
                automation_state="manual_only",
                automation_reason=None,
                automation_context_json=json.dumps({}, ensure_ascii=False),
                automation_updated_at=utc_now_iso(),
            )
            self.store.append_event(
                quote_id,
                "automation_reset",
                "operator",
                actor_ref=actor,
                payload={},
            )
        return {"quote": self.store.get_quote(quote_id)}

    def list_eligible_quotes(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.list_quotes(
            statuses=["ready_for_followup"],
            automation_states=["eligible_for_auto_followup"],
            limit=limit,
        )
