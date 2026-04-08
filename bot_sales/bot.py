#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main Bot Orchestrator
Coordinates ChatGPT, Business Logic, and Database
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .core.database import Database
from .core.chatgpt import ChatGPTClient, get_available_functions
from .core.business_logic import BusinessLogic
from .core.tenancy import tenant_manager
from .knowledge.loader import KnowledgeLoader
from .persistence.quote_store import QuoteStore
from .services.quote_service import QuoteService
from .services.handoff_service import HandoffService
from .services.quote_automation_service import QuoteAutomationService
from .planning.flow_manager import SalesFlowManager
from .analytics import Analytics
from . import ferreteria_quote as fq
from .ferreteria_continuity import apply_followup_to_open_quote, classify_followup_message
from .ferreteria_escalation import assess_quote_recoverability
from .config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
    DB_FILE,
    CATALOG_CSV,
    LOG_PATH,
    POLICIES_FILE,
    MAX_CONTEXT_MESSAGES
)


class SalesBot:
    """
    Main sales bot orchestrator
    Manages conversation flow and function calling
    """
    
    def __init__(
        self,
        db: Optional[Database] = None,
        api_key: str = None,
        model: str = None,
        tenant_id: str = "default_tenant",
        tenant_profile: Optional[Dict[str, Any]] = None,
        sandbox_mode: bool = False,
    ):
        """Initialize bot components"""
        self.tenant_id = tenant_id
        self.tenant_profile = tenant_profile or {}
        self.sandbox_mode = sandbox_mode

        # Initialize database
        if db:
            self.db = db
        else:
            self.db = Database(DB_FILE, CATALOG_CSV, LOG_PATH)

        self.knowledge_loader: Optional[KnowledgeLoader] = None
        self.quote_store: Optional[QuoteStore] = None
        self.quote_service: Optional[QuoteService] = None
        self.handoff_service: Optional[HandoffService] = None
        self.quote_automation_service: Optional[QuoteAutomationService] = None
        self.faq_file = "faqs.json"
        if self._is_ferreteria_runtime():
            self.knowledge_loader = KnowledgeLoader(
                tenant_id=self.tenant_id,
                tenant_profile=self.tenant_profile,
            )
            try:
                self.faq_file = self.knowledge_loader.get_paths()["faqs"]
            except Exception:
                self.faq_file = "faqs.json"
            try:
                db_path = self._resolve_runtime_db_path()
                self.quote_store = QuoteStore(db_path, tenant_id=self.tenant_id)
                self.quote_service = QuoteService(self.quote_store, tenant_id=self.tenant_id)
                self.handoff_service = HandoffService(self.quote_store, side_effects_enabled=not self.sandbox_mode)
                self.quote_automation_service = QuoteAutomationService(
                    self.quote_store,
                    tenant_id=self.tenant_id,
                    tenant_profile=self.tenant_profile,
                )
            except Exception as exc:
                logging.warning("ferreteria_quote_store_unavailable tenant=%s error=%s", self.tenant_id, exc)
                self.quote_store = None
                self.quote_service = None
                self.handoff_service = None
                self.quote_automation_service = None
        
        # Initialize analytics
        self.analytics = Analytics(self.db)
        
        # Initialize business logic
        self.logic = BusinessLogic(self.db, faq_file=self.faq_file)
        
        # Resolve tenant-scoped policies path (fallback to global default)
        profile_paths = self.tenant_profile.get("paths", {})
        self.policies_path = profile_paths.get("policies", POLICIES_FILE)
        if not Path(self.policies_path).is_absolute():
            self.policies_path = str(Path(__file__).resolve().parent.parent / self.policies_path)

        # Load policies
        self.policies = self._load_policies()
        
        # Config defaults
        if not api_key:
            api_key = OPENAI_API_KEY
        if not model:
            model = OPENAI_MODEL

        # Initialize ChatGPT client
        self.chatgpt = ChatGPTClient(
            api_key=api_key,
            model=model,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS
        )
        
        # Build system prompt dynamically from tenant config/profile
        try:
            from .core.tenant_config import get_tenant_config
            tenant_config = (
                get_tenant_config(config_data=self.tenant_profile)
                if self.tenant_profile
                else get_tenant_config()
            )
            self.system_prompt = tenant_config.render_prompt(policies=self.policies)
            logging.info("Using dynamic prompt from tenant config")
        except Exception as e:
            logging.warning(f"Could not load tenant config: {e}. Falling back to static prompt...")
            self.system_prompt = ChatGPTClient.build_system_prompt(self.policies)
        
        # Get available functions
        self.functions = get_available_functions()
        
        # Conversation contexts (in-memory, keyed by session_id)
        self.contexts: Dict[str, List[Dict[str, str]]] = {}
        
        # Session state (for tracking hold_id, etc.)
        self.sessions: Dict[str, Dict[str, Any]] = {}

        try:
            self.flow_manager: Optional[SalesFlowManager] = SalesFlowManager()
            logging.info("sales_flow_manager_initialized tenant=%s", self.tenant_id)
        except Exception as exc:
            self.flow_manager = None
            logging.warning("sales_flow_manager_unavailable tenant=%s error=%s", self.tenant_id, exc)
        
        logging.info("SalesBot initialized successfully (tenant=%s)", self.tenant_id)

    def close(self) -> None:
        """Release resources held by the bot (DB connection, quote store, etc.).

        Safe to call multiple times.  Used by test fixtures and long-running
        processes to avoid leaking SQLite file handles.
        """
        try:
            if getattr(self, "quote_store", None) is not None:
                self.quote_store.close()
        except Exception as exc:
            logging.debug("quote_store_close_error tenant=%s error=%s", self.tenant_id, exc)
        try:
            if getattr(self, "db", None) is not None:
                conn = getattr(self.db, "conn", None)
                if conn is not None:
                    conn.close()
        except Exception as exc:
            logging.debug("db_close_error tenant=%s error=%s", self.tenant_id, exc)
        logging.debug("SalesBot closed tenant=%s", self.tenant_id)

    def _load_policies(self) -> str:
        """Load policies from markdown file"""
        if os.path.exists(self.policies_path):
            with open(self.policies_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logging.warning("Policies file not found: %s", self.policies_path)
            return "No hay políticas cargadas."

    def _resolve_runtime_db_path(self) -> str:
        if getattr(self.db, "db_file", None):
            return str(self.db.db_file)
        profile_paths = self.tenant_profile.get("paths", {}) if isinstance(self.tenant_profile, dict) else {}
        db_path = profile_paths.get("db") or DB_FILE
        path = Path(db_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / db_path
        return str(path)

    def _knowledge(self) -> Optional[Dict[str, Any]]:
        if not self.knowledge_loader:
            return None
        try:
            return self.knowledge_loader.load()
        except Exception as exc:
            logging.warning("knowledge_load_failed tenant=%s error=%s", self.tenant_id, exc)
            return None

    def _quote_channel(self) -> str:
        return "cli"

    def _load_active_quote_from_store(self, session_id: str) -> None:
        if not self.quote_service:
            return
        loaded = self.quote_service.load_active_quote(session_id)
        sess = self.sessions.setdefault(session_id, {})
        if not loaded:
            if sess.get("quote_state") != "accepted":
                sess.pop("active_quote", None)
                sess.pop("quote_state", None)
            return
        sess["active_quote"] = loaded.get("items") or []
        persisted_status = str((loaded.get("quote") or {}).get("status") or "")
        if persisted_status in {"review_requested", "under_internal_review", "revision_requested", "ready_for_followup"}:
            sess["quote_state"] = "accepted"
        else:
            sess["quote_state"] = "open"

    def _persist_quote_state(
        self,
        session_id: str,
        *,
        response_text: Optional[str] = None,
        user_message: Optional[str] = None,
        accepted: bool = False,
        event_type: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
        status_override: Optional[str] = None,
    ) -> Optional[str]:
        if not self.quote_service:
            return None
        sess = self.sessions.get(session_id) or {}
        items = sess.get("active_quote") or []
        quote_id = self.quote_service.save_quote_snapshot(
            session_id=session_id,
            items=items,
            channel=self._quote_channel(),
            customer_ref=session_id,
            accepted=accepted,
            status_override=status_override,
            event_type=event_type,
            event_payload=event_payload,
            user_message=user_message,
            bot_response=response_text,
        )
        if quote_id and self.quote_automation_service:
            try:
                self.quote_automation_service.refresh_quote_automation(quote_id)
            except Exception as exc:
                logging.warning("quote_automation_refresh_failed tenant=%s quote=%s error=%s", self.tenant_id, quote_id, exc)
        return quote_id

    def _accept_quote_for_review(self, session_id: str, user_message: str, response_text: str) -> Optional[str]:
        if not self.quote_service:
            return None
        if not self.quote_store:
            return self._persist_quote_state(
                session_id,
                response_text=response_text,
                user_message=user_message,
                accepted=True,
                event_type="quote_acceptance_requested",
                event_payload={"source": "customer_acceptance"},
            )
        with self.quote_store.transaction():
            quote_id = self._persist_quote_state(
                session_id,
                response_text=response_text,
                user_message=user_message,
                accepted=True,
                event_type="quote_acceptance_requested",
                event_payload={"source": "customer_acceptance"},
            )
            if quote_id and self.handoff_service and not self.sandbox_mode:
                self.handoff_service.create_review_handoff(quote_id, customer_ref=session_id)
            return quote_id

    def _ensure_session_initialized(self, session_id: str) -> None:
        if session_id in self.contexts:
            return
        # Load from DB first (survives restarts); skip in sandbox to keep tests isolated
        if not self.sandbox_mode:
            persisted_ctx, persisted_state = self.db.load_session(session_id, self.tenant_id)
            if persisted_ctx:
                self.contexts[session_id] = persisted_ctx
                self.sessions[session_id] = persisted_state
                return
        self.contexts[session_id] = [{"role": "system", "content": self.system_prompt}]
        self.sessions[session_id] = {}
        if not self.sandbox_mode:
            self.analytics.start_session(session_id)

    def _record_user_turn(self, session_id: str, user_message: str) -> None:
        self.contexts[session_id].append({
            "role": "user",
            "content": user_message,
        })
        if not self.sandbox_mode:
            self.analytics.track_message(session_id)

    def _append_assistant_turn(self, session_id: str, response_text: str) -> str:
        self.contexts[session_id].append({
            "role": "assistant",
            "content": response_text,
        })
        # Persist after every bot turn (skip in sandbox to keep tests isolated)
        if not self.sandbox_mode:
            self.db.save_session(
                session_id,
                self.tenant_id,
                self.contexts[session_id],
                self.sessions.get(session_id, {}),
            )
        return response_text

    def _reset_turn_meta(self, session_id: str) -> None:
        self._set_last_turn_meta(
            session_id,
            route_source="unknown",
            model_name=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            estimated_cost_micros=0,
            latency_ms=0,
            response_mode=None,
        )

    def _handle_lite_mode(self, session_id: str, user_message: str) -> str:
        faq_result = self.logic.consultar_faq(user_message)
        if faq_result["status"] == "found":
            response = faq_result["respuesta"]
            self._set_last_turn_meta(session_id, route_source="faq")
        elif "stock" in user_message.lower() or "precio" in user_message.lower():
            models = self.logic.listar_modelos()
            response = "Tenemos stock disponible: " + ", ".join([m['model'] for m in models['models'][:5]]) + "..."
            self._set_last_turn_meta(session_id, route_source="deterministic")
        else:
            response = "Entiendo. En este momento no tengo esa información, te paso con un asesor humano ya mismo. 👤"
            if not self.sandbox_mode:
                self.logic.derivar_humano("Consulta no resuelta en Lite Mode", contacto=session_id)
            self._set_last_turn_meta(session_id, route_source="fallback")
        return self._append_assistant_turn(session_id, response)

    def _handle_sales_contract_reply(
        self,
        session_id: str,
        sales_contract: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if not sales_contract:
            return None

        if (sales_contract.get("human_handoff") or {}).get("enabled"):
            if not self.sandbox_mode:
                try:
                    summary = self._generate_handoff_summary(session_id)
                    self.logic.derivar_humano(
                        razon=str((sales_contract.get("human_handoff") or {}).get("reason") or "Handoff requerido"),
                        contacto=session_id,
                        resumen=summary,
                    )
                except Exception as exc:
                    logging.warning("sales_flow_handoff_failed session=%s error=%s", session_id, exc)

            response_text = str(sales_contract.get("reply_text") or "Te paso con un asesor para continuar.")
            self._set_last_turn_meta(session_id, route_source="model_assisted")
            return self._append_assistant_turn(session_id, response_text)

        if sales_contract.get("missing_fields"):
            response_text = str(sales_contract.get("reply_text") or "")
            if response_text:
                self._set_last_turn_meta(session_id, route_source="model_assisted")
                return self._append_assistant_turn(session_id, response_text)

        return None

    def process_message(self, session_id: str, user_message: str) -> str:
        """
        Process a user message and return bot response
        
        Args:
            session_id: Unique identifier for conversation (phone, chat ID, etc.)
            user_message: User's message text
        
        Returns:
            Bot's response text
        """
        self._ensure_session_initialized(session_id)

        if self._is_ferreteria_runtime():
            self._load_active_quote_from_store(session_id)

        self._record_user_turn(session_id, user_message)
        self._reset_turn_meta(session_id)
        
        # Trim context if too long (keep system message + last N messages)
        self._trim_context(session_id)
        
        # Check for LITE MODE (Basic Bot)
        from .config import LITE_MODE
        if LITE_MODE:
            return self._handle_lite_mode(session_id, user_message)

        ferreteria_pre_route = self._try_ferreteria_pre_route(session_id, user_message)
        if ferreteria_pre_route:
            return self._append_assistant_turn(session_id, ferreteria_pre_route)

        sales_contract = self._run_sales_intelligence(session_id, user_message)
        self.sessions[session_id]["sales_intelligence_v1"] = self._build_sales_intelligence_meta(sales_contract)
        sales_response = self._handle_sales_contract_reply(session_id, sales_contract)
        if sales_response is not None:
            return sales_response

        # Process with ChatGPT (with potential function calls)
        response_text = self._chat_with_functions(session_id)
        
        return self._append_assistant_turn(session_id, response_text)

    def _try_ferreteria_pre_route(self, session_id: str, user_message: str) -> Optional[str]:
        """Tenant-specific product-first routing for ferreteria with full multi-turn state."""
        if not self._is_ferreteria_runtime():
            return None

        text = (user_message or "").strip()
        if not text:
            return None

        normalized = self._normalize_lookup_text(text)
        sess = self.sessions.setdefault(session_id, {})
        quote_state: Optional[str] = sess.get("quote_state")
        open_quote: Optional[List] = sess.get("active_quote")
        knowledge = self._knowledge()

        def _done(response: str, route_source: str = "deterministic", **meta: Any) -> str:
            payload = {"route_source": route_source}
            payload.update(meta)
            self._set_last_turn_meta(session_id, **payload)
            return response

        # ── 0. FAQ — always works regardless of quote state ─────────────────
        faq_result = self.logic.consultar_faq(text)
        if faq_result.get("status") == "found":
            return _done(str(faq_result.get("respuesta") or ""), "faq")

        # ── 0.5. Acceptance ──────────────────────────────────────────────────
        if open_quote and fq.looks_like_acceptance(text, knowledge=knowledge):
            response = fq.generate_acceptance_response(open_quote, knowledge=knowledge)
            if "✓" in response:
                self._accept_quote_for_review(session_id, user_message, response)
                sess["quote_state"] = "accepted"
                sess.pop("pending_decision", None)
                sess.pop("pending_clarification_target", None)
            else:
                self._persist_quote_state(
                    session_id,
                    response_text=response,
                    user_message=user_message,
                    event_type="quote_acceptance_blocked",
                    event_payload={"reason": "pending_lines"},
                )
            return _done(response, "deterministic")

        # ── 1. Explicit reset ────────────────────────────────────────────────
        if fq.looks_like_reset(text, knowledge=knowledge):
            if self.quote_service:
                self.quote_service.mark_reset(session_id)
            sess.pop("active_quote", None)
            sess.pop("quote_state", None)
            sess.pop("pending_decision", None)
            sess.pop("pending_clarification_target", None)
            return _done("Presupuesto borrado. Cuando quieras empezamos uno nuevo.", "deterministic")

        # ── 1.5. Post-acceptance guard: clear for fresh request ──────────────
        if quote_state == "accepted":
            # If still within accepted state, a new request starts fresh
            # (FAQ already handled above; acceptance phrases would be weird here)
            sess.pop("active_quote", None)
            sess.pop("quote_state", None)
            sess.pop("pending_decision", None)
            open_quote = None

        # ── 2. Pending merge-vs-replace decision resolution ──────────────────
        pending_decision = sess.get("pending_decision")
        if pending_decision and pending_decision.get("type") == "merge_or_replace":
            pending_items = pending_decision.get("new_items", [])
            existing_ids = {it.get("line_id") for it in (open_quote or [])}
            to_merge = [it for it in pending_items if it.get("line_id") not in existing_ids]

            def _do_merge() -> str:
                merged = list(open_quote or []) + to_merge
                sess["active_quote"] = merged
                sess["quote_state"] = "open"
                sess.pop("pending_decision", None)
                comps = fq.get_complementary_suggestions(merged, self.logic, knowledge=knowledge)
                reply = fq.generate_updated_quote_response(merged, complementary=comps or None)
                self._persist_quote_state(
                    session_id,
                    response_text=reply,
                    user_message=user_message,
                    event_type="quote_merged",
                    event_payload={"merged_count": len(to_merge)},
                )
                return reply

            def _do_new() -> str:
                sess["active_quote"] = pending_items
                sess["quote_state"] = "open"
                sess.pop("pending_decision", None)
                comps = fq.get_complementary_suggestions(pending_items, self.logic, knowledge=knowledge)
                reply = self._generate_quote_response(pending_items, complementary=comps or None)
                self._persist_quote_state(
                    session_id,
                    response_text=reply,
                    user_message=user_message,
                    event_type="quote_replaced",
                    event_payload={"new_line_count": len(pending_items)},
                )
                return reply

            if fq.looks_like_merge_answer(text, knowledge=knowledge):
                return _done(_do_merge(), "deterministic")

            if fq.looks_like_new_answer(text, knowledge=knowledge) or fq.looks_like_reset(text, knowledge=knowledge):
                return _done(_do_new(), "deterministic")

            # Unrecognized answer — increment retry counter
            turns = pending_decision.get("turns", 0) + 1
            pending_decision["turns"] = turns
            sess["pending_decision"] = pending_decision

            if turns >= 2:
                # Auto-default to merge (conservative) and clear state
                reply = _do_merge()
                return _done(
                    "Lo sumo al presupuesto actual. "
                    "Si querés empezar uno nuevo, decime *nuevo presupuesto*.\n\n"
                    + reply,
                    "deterministic",
                )
            # Re-ask with question
            return _done(fq.MERGE_VS_REPLACE_QUESTION, "deterministic")

        # ── 2.5. Pending clarification target resolution ─────────────────────
        # When needs_disambiguation fired, we stored the candidates.
        # A follow-up reply like "la mecha" should resolve to the stored target.
        pending_clarif_target = sess.get("pending_clarification_target")

        # ── 2.7. Remove operation ────────────────────────────────────────────
        if open_quote and fq.looks_like_remove(text):
            updated, msg = fq.apply_remove(text, open_quote)
            sess["active_quote"] = updated
            comps = fq.get_complementary_suggestions(updated, self.logic, knowledge=knowledge)
            header = fq.generate_updated_quote_response(updated, complementary=comps or None)
            self._persist_quote_state(
                session_id,
                response_text=f"{msg}\n\n{header}",
                user_message=user_message,
                event_type="line_removed",
                event_payload={"message": text},
            )
            return _done(f"{msg}\n\n{header}", "deterministic")

        # ── 2.9. Replace operation ───────────────────────────────────────────
        if open_quote and fq.looks_like_replace(text):
            updated, msg = fq.apply_replace(text, open_quote, self.logic, knowledge=knowledge)
            sess["active_quote"] = updated
            comps = fq.get_complementary_suggestions(updated, self.logic, knowledge=knowledge)
            header = fq.generate_updated_quote_response(updated, complementary=comps or None)
            self._persist_quote_state(
                session_id,
                response_text=f"{msg}\n\n{header}",
                user_message=user_message,
                event_type="line_replaced",
                event_payload={"message": text},
            )
            return _done(f"{msg}\n\n{header}", "deterministic")

        # ── 3. Additive ──────────────────────────────────────────────────────
        if open_quote and fq.looks_like_additive(text):
            updated = fq.apply_additive(text, open_quote, self.logic, knowledge=knowledge)
            sess["active_quote"] = updated
            sess["quote_state"] = "open"
            sess.pop("pending_decision", None)
            comps = fq.get_complementary_suggestions(updated, self.logic, knowledge=knowledge)
            reply = fq.generate_updated_quote_response(updated, complementary=comps or None)
            self._persist_quote_state(
                session_id,
                response_text=reply,
                user_message=user_message,
                event_type="line_added",
                event_payload={"message": text},
            )
            return _done(reply, "deterministic")

        # ── 3.5. Phase 4 continuation before fallback/escalation ────────────
        if open_quote:
            continuation = classify_followup_message(text, open_quote, knowledge=knowledge)
            if continuation.get("kind") == "followup":
                followup = apply_followup_to_open_quote(
                    text,
                    open_quote,
                    self.logic,
                    knowledge=knowledge,
                    pending_target_ids=pending_clarif_target,
                )

                if followup.get("status") == "needs_disambiguation":
                    target_ids = followup.get("candidate_target_ids") or [
                        it.get("line_id") for it in open_quote
                        if it.get("status") in ("ambiguous", "unresolved", "blocked_by_missing_info")
                    ]
                    sess["pending_clarification_target"] = [line_id for line_id in target_ids if line_id]
                    return _done(str(followup.get("prompt") or fq.needs_disambiguation(text, open_quote) or ""), "deterministic")

                if followup.get("status") == "no_target":
                    pending_lines = [
                        it for it in open_quote
                        if it.get("status") in ("ambiguous", "unresolved", "blocked_by_missing_info")
                    ]
                    updated = list(open_quote)
                    if len(pending_lines) == 1:
                        only = pending_lines[0]
                        updated = []
                        for line in open_quote:
                            if line.get("line_id") == only.get("line_id"):
                                preserved = dict(line)
                                preserved["clarification_attempts"] = int(line.get("clarification_attempts") or 0) + 1
                                updated.append(preserved)
                            else:
                                updated.append(line)
                    sess["active_quote"] = updated
                    assessment = assess_quote_recoverability(updated, text, knowledge=knowledge)
                    if assessment.get("operator_required"):
                        self._persist_quote_state(
                            session_id,
                            user_message=user_message,
                            event_type="quote_operator_review_candidate",
                            event_payload={"reason": assessment.get("reason")},
                        )
                        return None

                if followup.get("status") in {"updated", "no_progress"}:
                    updated = list(followup.get("items") or open_quote)
                    sess["active_quote"] = updated
                    sess["quote_state"] = "open"
                    if followup.get("status") == "updated":
                        sess.pop("pending_clarification_target", None)
                        comps = fq.get_complementary_suggestions(updated, self.logic, knowledge=knowledge)
                        reply = fq.generate_updated_quote_response(updated, complementary=comps or None)
                        self._persist_quote_state(
                            session_id,
                            response_text=reply,
                            user_message=user_message,
                            event_type="line_updated",
                            event_payload={
                                "message": text,
                                "line_ids": followup.get("target_line_ids") or [],
                                "improved_line_ids": followup.get("improved_line_ids") or [],
                            },
                        )
                        return _done(reply, "deterministic")

                    assessment = assess_quote_recoverability(updated, text, knowledge=knowledge)
                    if assessment.get("continue_clarifying"):
                        recoverable_ids = [
                            line.get("line_id")
                            for line in (assessment.get("recoverable_lines") or [])
                            if line.get("line_id")
                        ]
                        if recoverable_ids:
                            sess["pending_clarification_target"] = recoverable_ids
                        comps = fq.get_complementary_suggestions(updated, self.logic, knowledge=knowledge)
                        reply = fq.generate_updated_quote_response(updated, complementary=comps or None)
                        prompt = str(assessment.get("prompt") or "").strip()
                        if prompt:
                            reply = f"{reply}\n\n{prompt}"
                        self._persist_quote_state(
                            session_id,
                            response_text=reply,
                            user_message=user_message,
                            event_type="line_clarification_needed",
                            event_payload={
                                "message": text,
                                "reason": assessment.get("reason"),
                                "recoverable_line_ids": recoverable_ids,
                            },
                        )
                        return _done(reply, "deterministic")

                    if assessment.get("operator_required"):
                        self._persist_quote_state(
                            session_id,
                            user_message=user_message,
                            event_type="quote_operator_review_candidate",
                            event_payload={"reason": assessment.get("reason")},
                        )
                        return None

        # ── 4. Clarification (with identity targeting) ───────────────────────
        if open_quote and fq.looks_like_clarification(text, open_quote):
            disambig = fq.needs_disambiguation(text, open_quote)
            if disambig:
                # Store the pending candidates by line_id so next reply resolves correctly
                pending_cands = [
                    it for it in open_quote if it["status"] in ("ambiguous", "unresolved", "blocked_by_missing_info")
                ]
                sess["pending_clarification_target"] = [
                    it.get("line_id") for it in pending_cands if it.get("line_id")
                ]
                return _done(disambig, "deterministic")

            # Pass the stored target if disambiguation already ran
            target_line_id = None
            if pending_clarif_target:
                # Find which stored target the clarification matches best
                pending_lines = [
                    it for it in open_quote
                    if it.get("line_id") in pending_clarif_target
                    and it["status"] in ("ambiguous", "unresolved", "blocked_by_missing_info")
                ]
                matched = fq._match_to_line(text, pending_lines) if pending_lines else None
                target_line_id = matched.get("line_id") if matched else (
                    pending_lines[0].get("line_id") if len(pending_lines) == 1 else None
                )
                sess.pop("pending_clarification_target", None)

            updated = fq.apply_clarification(
                text,
                open_quote,
                self.logic,
                target_line_id=target_line_id,
                knowledge=knowledge,
            )
            sess["active_quote"] = updated
            comps = fq.get_complementary_suggestions(updated, self.logic, knowledge=knowledge)
            reply = fq.generate_updated_quote_response(updated, complementary=comps or None)
            self._persist_quote_state(
                session_id,
                response_text=reply,
                user_message=user_message,
                event_type="line_updated",
                event_payload={"message": text},
            )
            return _done(reply, "deterministic")

        # ── 5. New multi-item quote request ──────────────────────────────────
        parsed_items = self._parse_quote_items(user_message)
        if len(parsed_items) >= 2:
            resolved_items = [self._resolve_quote_item(p) for p in parsed_items]

            # If there's an open non-accepted quote, ask merge vs replace
            if open_quote and quote_state == "open":
                # Store new items in pending_decision
                sess["pending_decision"] = {
                    "type": "merge_or_replace",
                    "new_items": resolved_items,
                }
                return _done(fq.MERGE_VS_REPLACE_QUESTION, "deterministic")

            # No active quote — start fresh
            sess["active_quote"] = resolved_items
            sess["quote_state"] = "open"
            sess.pop("pending_decision", None)
            comps = fq.get_complementary_suggestions(resolved_items, self.logic, knowledge=knowledge)
            reply = self._generate_quote_response(resolved_items, complementary=comps or None)
            self._persist_quote_state(
                session_id,
                response_text=reply,
                user_message=user_message,
                event_type="quote_opened",
                event_payload={"line_count": len(resolved_items)},
            )
            return _done(reply, "deterministic")

        # ── 6. Single-item / category / product-first paths ──────────────────
        category = self._detect_ferreteria_category(normalized)
        if category:
            result = self.logic.buscar_por_categoria(category)
            if result.get("status") == "found":
                return _done(self._format_ferreteria_products_reply(
                    result.get("products", []),
                    heading=f"Te paso opciones de **{category}** con stock:",
                ), "deterministic")
            return _done(f"No veo stock activo en **{category}** ahora. Decime uso/medida y te propongo alternativa.", "deterministic")

        if self._looks_like_project_request(normalized):
            return _done(fq.BROAD_REQUEST_REPLY, "fallback")

        if self._looks_like_product_request(normalized):
            parsed_single = self._parse_quote_items(user_message)
            if len(parsed_single) == 1:
                resolved_single = self._resolve_quote_item(parsed_single[0])
                single_norm = str(resolved_single.get("normalized", "")).strip().lower()
                single_raw_words = [
                    word for word in self._normalize_lookup_text(parsed_single[0].get("raw", "")).split()
                    if word not in self._FILLER_WORDS
                ]
                generic_browse_terms = {
                    "taladro", "amoladora", "atornillador", "silicona",
                    "teflon", "pintura", "rodillo", "guante", "guantes",
                    "tornillo", "tornillos",
                }

                if (
                    resolved_single.get("status") == "resolved"
                    and single_norm in generic_browse_terms
                    and len(single_raw_words) <= 2
                ):
                    return _done(self._format_ferreteria_products_reply(resolved_single.get("products", [])), "deterministic")

                if resolved_single.get("status") in ("resolved", "ambiguous", "unresolved", "blocked_by_missing_info"):
                    sess["active_quote"] = [resolved_single]
                    sess["quote_state"] = "open"
                    comps = []
                    if resolved_single.get("status") == "resolved":
                        comps = fq.get_complementary_suggestions([resolved_single], self.logic, knowledge=knowledge)
                    reply = self._generate_quote_response([resolved_single], complementary=comps or None)
                    self._persist_quote_state(
                        session_id,
                        response_text=reply,
                        user_message=user_message,
                        event_type="quote_opened",
                        event_payload={"line_count": 1},
                    )
                    return _done(reply, "deterministic")

            stock_result = self.logic.buscar_stock(text)
            if stock_result.get("status") == "found":
                return _done(self._format_ferreteria_products_reply(stock_result.get("products", [])), "deterministic")
            if stock_result.get("status") == "no_stock":
                alternatives = self.logic.buscar_alternativas(text)
                if alternatives.get("status") == "found":
                    return _done(self._format_ferreteria_products_reply(
                        alternatives.get("alternatives", []),
                        heading="No tengo stock exacto de eso ahora, pero si estas alternativas:",
                    ), "deterministic")
                return _done("Ese producto existe pero hoy no tiene stock. Busco alternativa por uso o medida si queres.", "deterministic")
            if stock_result.get("status") == "no_match":
                return _done(
                    "No encontre ese item exacto en el catalogo actual.\n\n"
                    "Decime una de estas dos cosas y sigo:\n"
                    "1. La medida, uso o material\n"
                    "2. El rubro del producto",
                    "fallback",
                )

        # ── 7. Session guard ─────────────────────────────────────────────────
        if open_quote and len(text.split()) <= 6 and not re.search(r"[,/+]|\by\b|\be\b", text, re.I):
            # Check if short message resolves a pending decision
            if pending_decision:
                return _done(fq.MERGE_VS_REPLACE_QUESTION, "deterministic")
            return _done(fq.session_guard_response(open_quote), "deterministic")

        return None



    def _is_ferreteria_runtime(self) -> bool:


        if str(self.tenant_id).strip().lower() == "ferreteria":
            return True
        business = self.tenant_profile.get("business", {}) if isinstance(self.tenant_profile, dict) else {}
        return str(business.get("industry", "")).strip().lower() == "ferreteria"

    @staticmethod
    def _normalize_lookup_text(text: str) -> str:
        normalized = text.lower().strip()
        replacements = str.maketrans({
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ñ": "n",
        })
        normalized = normalized.translate(replacements)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _detect_ferreteria_category(self, normalized_message: str) -> Optional[str]:
        aliases = {
            "herramienta": "Herramientas Electricas",
            "herramientas": "Herramientas Electricas",
            "taladro": "Herramientas Electricas",
            "amoladora": "Herramientas Electricas",
            "atornillador": "Herramientas Electricas",
            "manual": "Herramientas Manuales",
            "martillo": "Herramientas Manuales",
            "destornillador": "Herramientas Manuales",
            "llave": "Herramientas Manuales",
            "tornillo": "Tornilleria",
            "tornillos": "Tornilleria",
            "autoperforante": "Tornilleria",
            "tarugo": "Fijaciones",
            "tarugos": "Fijaciones",
            "fijacion": "Fijaciones",
            "fijaciones": "Fijaciones",
            "pintura": "Pintureria",
            "pintureria": "Pintureria",
            "latex": "Pintureria",
            "esmalte": "Pintureria",
            "rodillo": "Pintureria",
            "silicona": "Plomeria",
            "teflon": "Plomeria",
            "plomeria": "Plomeria",
            "guante": "Seguridad",
            "guantes": "Seguridad",
            "seguridad": "Seguridad",
        }
        for token, category in aliases.items():
            if token in normalized_message:
                return category
        return None

    # -- Quote Builder helpers (delegates to ferreteria_quote module) -----------

    _FILLER_WORDS = fq._FILLER_WORDS  # keep for backward compat if referenced elsewhere

    def _parse_quote_items(self, message: str) -> List[Dict[str, Any]]:
        """Parse a customer message into a list of raw item dicts with qty info."""
        return fq.parse_quote_items(message)

    def _resolve_quote_item(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a single parsed item dict against the catalog."""
        return fq.resolve_quote_item(parsed, self.logic, knowledge=self._knowledge())

    def _generate_quote_response(
        self,
        resolved_items: List[Dict[str, Any]],
        complementary: Optional[List[str]] = None,
    ) -> str:
        """Format resolved items into a structured customer-facing quote."""
        return fq.generate_quote_response(resolved_items, complementary=complementary)

    def _looks_like_project_request(self, normalized_message: str) -> bool:
        project_terms = (
            "presupuesto",
            "obra",
            "bano",
            "bano",
            "cocina",
            "instalacion",
            "instalacion",
            "arreglar",
            "reparacion",
            "reparar",
            "ambiente",
        )
        if not any(term in normalized_message for term in project_terms):
            return False
        return not any(token in normalized_message for token in ("taladro", "silicona", "teflon", "tornillo", "tarugo", "pintura", "rodillo"))

    def _looks_like_product_request(self, normalized_message: str) -> bool:
        product_terms = (
            "busco",
            "necesito",
            "quiero",
            "tenes",
            "tienen",
            "taladro",
            "amoladora",
            "atornillador",
            "martillo",
            "destornillador",
            "llave",
            "tornillo",
            "tarugo",
            "pintura",
            "rodillo",
            "silicona",
            "teflon",
            "guante",
            "cable",
            "mecha",
            "broca",
            "sellador",
            "taco fisher",
            "taco",
            "caño",
            "cano",
            "fijacion",
        )
        return any(term in normalized_message for term in product_terms)

    @staticmethod
    def _format_ferreteria_products_reply(products: List[Dict[str, Any]], heading: str = "Encontre estas opciones con stock:") -> str:
        lines = [heading, ""]
        for product in products[:4]:
            name = product.get("model") or product.get("name") or product.get("sku", "Producto")
            category = product.get("category", "")
            price = product.get("price_formatted") or "precio a confirmar"
            stock = product.get("available") or product.get("stock_qty") or product.get("stock") or 0
            detail = [f"**{name}**", price, f"stock: {stock}"]
            if category:
                detail.insert(2, category)
            lines.append("- " + " | ".join(str(part) for part in detail if part))

        lines.append("")
        lines.append("Si queres, te ayudo a elegir por uso, medida, marca o presupuesto.")
        return "\n".join(lines)

    def _chat_with_functions(self, session_id: str) -> str:
        """
        Send message to ChatGPT and handle function calls
        May require multiple iterations if functions are called
        """
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Send to ChatGPT
            response = self.chatgpt.send_message(
                messages=self.contexts[session_id],
                functions=self.functions
            )
            
            # Check if function was called
            if "function_call" in response:
                func_call = response["function_call"]
                func_name = func_call["name"]
                func_args = func_call["arguments"]
                
                logging.info(f"Function called: {func_name} with args: {func_args}")
                
                # Execute function
                func_result = self._execute_function(session_id, func_name, func_args)
                
                # Add function result to context
                self.contexts[session_id].append({
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": func_name,
                        "arguments": str(func_args)
                    }
                })
                
                self.contexts[session_id].append({
                    "role": "function",
                    "name": func_name,
                    "content": str(func_result)
                })
                
                # Continue loop to get final response
                continue
            
            # No function call, return response
            meta = response.get("meta") or {}
            route_source = "fallback" if meta.get("used_fallback") else "model_assisted"
            self._set_last_turn_meta(
                session_id,
                route_source=route_source,
                model_name=meta.get("model"),
                prompt_tokens=int(meta.get("prompt_tokens") or 0),
                completion_tokens=int(meta.get("completion_tokens") or 0),
                total_tokens=int(meta.get("total_tokens") or 0),
                estimated_cost_micros=0,
                latency_ms=int(meta.get("latency_ms") or 0),
                response_mode=meta.get("response_mode"),
            )
            return response.get("content", "...")
        
        # Max iterations reached
        self._set_last_turn_meta(session_id, route_source="fallback", response_mode="max_iterations")
        return "Perdón, tuve un problema procesando tu solicitud. ¿Empezamos de nuevo?"

    @staticmethod
    def _build_sales_intelligence_meta(contract: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(contract, dict):
            return None
        missing = contract.get("missing_fields")
        if not isinstance(missing, list):
            missing = []
        confidence = contract.get("confidence")
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        cta = contract.get("cta") if isinstance(contract.get("cta"), dict) else {}
        handoff = contract.get("human_handoff") if isinstance(contract.get("human_handoff"), dict) else {}
        return {
            "schema": "sales_intelligence_v1",
            "intent": contract.get("intent"),
            "stage": contract.get("stage"),
            "missing_fields": missing,
            "objection_type": contract.get("objection_type"),
            "confidence": round(confidence, 4),
            "ab_variant": contract.get("ab_variant"),
            "variant_key": contract.get("variant_key"),
            "playbook_snippet": contract.get("playbook_snippet"),
            "cta_type": cta.get("type"),
            "needs_handoff": bool(handoff.get("enabled")),
        }

    def _run_sales_intelligence(self, session_id: str, user_message: str) -> Optional[Dict[str, Any]]:
        if self.flow_manager is None:
            return None
        try:
            return self.flow_manager.process_input(session_id, user_message)
        except Exception as exc:
            logging.warning("sales_intelligence_failed_using_legacy_flow tenant=%s session=%s error=%s", self.tenant_id, session_id, exc)
            return None

    def _execute_function(self, session_id: str, func_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a business logic function"""
        try:
            if func_name == "buscar_stock":
                result = self.logic.buscar_stock(
                    modelo=args.get("modelo"),
                    storage_gb=args.get("storage_gb"),
                    color=args.get("color")
                )
                # Track product queries
                if result.get("status") == "found" and result.get("products"):
                    for prod in result["products"]:
                        self.analytics.track_product_query(
                            session_id, 
                            prod["sku"], 
                            prod.get("category", "Unknown")
                        )
                return result
            
            elif func_name == "listar_modelos":
                return self.logic.listar_modelos()
            
            elif func_name == "buscar_alternativas":
                return self.logic.buscar_alternativas(
                    modelo=args.get("modelo"),
                    storage_gb=args.get("storage_gb"),
                    color=args.get("color")
                )
            
            elif func_name == "crear_reserva":
                if self.sandbox_mode:
                    return {"status": "sandbox_blocked", "message": "Reserva bloqueada en modo entrenamiento"}
                result = self.logic.crear_reserva(
                    sku=args.get("sku"),
                    nombre=args.get("nombre"),
                    contacto=args.get("contacto"),
                    email=args.get("email")
                )
                # Store hold_id in session
                if result["status"] == "success":
                    self.sessions[session_id]["hold_id"] = result["hold_id"]
                return result
            
            elif func_name == "confirmar_venta":
                # Use hold_id from session if not provided
                hold_id = args.get("hold_id") or self.sessions[session_id].get("hold_id")
                if not hold_id:
                    return {"status": "error", "message": "No hay reserva activa"}
                
                if self.sandbox_mode:
                    return {"status": "sandbox_blocked", "message": "Confirmacion de venta bloqueada en modo entrenamiento"}
                result = self.logic.confirmar_venta(
                    hold_id=hold_id,
                    zona=args.get("zona"),
                    metodo_pago=args.get("metodo_pago")
                )
                
                # Track sale if successful
                if result["status"] == "success" and "product_sku" in result:
                    product = self.db.get_product_by_sku(result["product_sku"])
                    if product:
                        if not self.sandbox_mode:
                            self.analytics.track_sale(
                                session_id,
                                result["product_sku"],
                                product["price_ars"],
                                product.get("category", "Unknown")
                            )
                
                # Clear session state after sale
                if result["status"] == "success":
                    self.sessions[session_id] = {}
                
                return result
            
            elif func_name == "obtener_politicas":
                return self.logic.obtener_politicas(tema=args.get("tema"))
            
            elif func_name == "buscar_por_categoria":
                return self.logic.buscar_por_categoria(
                    categoria=args.get("categoria")
                )
            
            elif func_name == "obtener_cross_sell_offer":
                result = self.logic.obtener_cross_sell_offer(
                    producto_comprado_sku=args.get("producto_comprado_sku")
                )
                
                # Track cross-sell offer
                if result.get("status") == "available" and result.get("offer"):
                    offer = result["offer"]
                    self.analytics.track_cross_sell_offer(
                        session_id,
                        offer["sku"],
                        offer["product"].get("category", "Unknown")
                    )
                    # Store in session for tracking acceptance
                    self.sessions[session_id]["cross_sell_offered"] = offer["sku"]
                
                return result
            
            elif func_name == "derivar_humano":
                # SMART HANDOFF: Generate summary
                summary = self._generate_handoff_summary(session_id)
                logging.info(f"Handoff Summary generated: {summary}")
                
                if self.sandbox_mode:
                    return {"status": "sandbox_blocked", "message": "Handoff bloqueado en modo entrenamiento", "summary": summary}
                return self.logic.derivar_humano(
                    razon=args.get("razon"),
                    contacto=args.get("contacto"),
                    nombre=args.get("nombre"),
                    resumen=summary
                )
            
            elif func_name == "consultar_faq":
                return self.logic.consultar_faq(
                    pregunta=args.get("pregunta")
                )
            
            elif func_name == "listar_bundles":
                return self.logic.listar_bundles(
                    categoria=args.get("categoria")
                )
            
            elif func_name == "obtener_bundle":
                return self.logic.obtener_bundle(
                    bundle_id=args.get("bundle_id")
                )
            
            elif func_name == "obtener_recomendaciones":
                return self.logic.obtener_recomendaciones(
                    producto_sku=args.get("producto_sku"),
                    categoria=args.get("categoria")
                )

            elif func_name == "obtener_upselling":
                return self.logic.obtener_upselling(
                    sku_actual=args.get("sku_actual")
                )
            
            elif func_name == "comparar_productos":
                return self.logic.comparar_productos(
                    sku1=args.get("sku1"),
                    sku2=args.get("sku2")
                )
            
            elif func_name == "validar_datos_cliente":
                return self.logic.validar_datos_cliente(
                    nombre=args.get("nombre"),
                    email=args.get("email"),
                    contacto=args.get("contacto"),
                    dni=args.get("dni")
                )
            
            elif func_name == "detectar_fraude":
                return self.logic.detectar_fraude(
                    email=args.get("email"),
                    phone=args.get("phone"),
                    message=args.get("message")
                )

            else:
                return {
                    "status": "error",
                    "message": f"Función desconocida: {func_name}"
                }
        
        except Exception as e:
            logging.error(f"Error executing function {func_name}: {e}")
            return {
                "status": "error",
                "message": f"Error: {str(e)}"
            }

    def _trim_context(self, session_id: str):
        """Trim conversation context to avoid token limits"""
        context = self.contexts[session_id]
        
        if len(context) <= MAX_CONTEXT_MESSAGES + 1:  # +1 for system message
            return
        
        # Keep system message + last N messages
        system_msg = context[0]
        recent_messages = context[-(MAX_CONTEXT_MESSAGES):]
        self.contexts[session_id] = [system_msg] + recent_messages

    def _generate_handoff_summary(self, session_id: str) -> str:
        """Generate a brief summary of the conversation for the human agent"""
        try:
            # Grab recent context (system prompt not needed for summary context)
            recent_msgs = self.contexts.get(session_id, [])
            if not recent_msgs:
                return "Sin historial previo."
                
            # Filter to avoid sending too much token garbage
            # Convert list of dicts to string conversation
            conversation_text = ""
            for msg in recent_msgs[-10:]: # Last 10 messages
                role = msg.get('role', 'unknown')
                content = msg.get('content') or str(msg.get('function_call', ''))
                conversation_text += f"{role}: {content}\n"

            summary_prompt = [
                {"role": "system", "content": "Actúa como un asistente senior. Resume esta conversación en 2 líneas para el vendedor: 1) Qué busca el cliente. 2) Por qué se derivó (traba, queja, solicitud específica)."},
                {"role": "user", "content": f"Conversación:\n{conversation_text}"}
            ]
            
            # Call LLM (using the same client)
            # Note: If LLM is down (mock mode), this will return a generic mock response,
            # which is fine/safe.
            response = self.chatgpt.send_message(summary_prompt)
            
            content = response.get("content", "No se pudo generar resumen.")
            return content

        except Exception as e:
            logging.error(f"Error generating summary: {e}")
            return "Resumen no disponible (Error al procesar)"

    def _set_last_turn_meta(self, session_id: str, **meta: Any) -> None:
        sess = self.sessions.setdefault(session_id, {})
        sess["last_turn_meta"] = meta

    def get_last_turn_meta(self, session_id: str) -> Dict[str, Any]:
        sess = self.sessions.get(session_id) or {}
        return dict(sess.get("last_turn_meta") or {})

    def reset_session(self, session_id: str):
        """Reset a conversation session (in-memory and persisted)."""
        self.contexts.pop(session_id, None)
        self.sessions.pop(session_id, None)
        if not self.sandbox_mode:
            self.db.delete_session(session_id, self.tenant_id)
        logging.info("Session %s reset (tenant=%s)", session_id, self.tenant_id)

    def close(self):
        """Cleanup resources"""
        if self.quote_store:
            self.quote_store.close()
        self.db.close()
