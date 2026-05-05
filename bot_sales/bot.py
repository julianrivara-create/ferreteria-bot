#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main Bot Orchestrator
Coordinates ChatGPT, Business Logic, and Database
"""

import os
import re
import logging
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional
from cachetools import TTLCache

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
from .state.conversation_state import ConversationStateV2, StateStore
from .routing.turn_interpreter import TurnInterpreter, TurnInterpretation
from .services.catalog_search_service import CatalogSearchService, ProductNeed
from .services.policy_service import PolicyService
from .services.pending_guard import sanitize_response
from .observability.turn_event import TurnEvent
from .observability.metrics import record_turn, record_search, record_escalation, record_latency_bucket
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

_ESCALATION_REQUEST_KEYWORDS = (
    "hablar con humano", "hablar con persona", "hablar con alguien",
    "atender humano", "atendeme un humano", "atendeme alguien",
    "hablar con un asesor", "hablar con asesor", "asesor humano",
    "una persona real", "alguien real", "persona de verdad",
    "no quiero un bot", "dame un humano", "pasame con alguien",
    "pasame con un humano", "pasame con alguien real",
    "necesito un humano", "necesito una persona",
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
        resolved_api_key = api_key or OPENAI_API_KEY

        # Initialize database
        if db:
            self.db = db
        else:
            self.db = Database(DB_FILE, CATALOG_CSV, LOG_PATH, api_key=resolved_api_key)

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
                logging.warning("ferreteria_quote_store_unavailable tenant=%s error=%s", self.tenant_id, exc, exc_info=True)
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
            api_key = resolved_api_key
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
            logging.error("tenant_config_load_failed tenant=%s error=%s", self.tenant_id, e, exc_info=True)
            self.system_prompt = ChatGPTClient.build_system_prompt(self.policies)
        
        # Phase 6: TurnInterpreter (replaces IntentRouter + AcceptanceDetector per-call)
        self.turn_interpreter = TurnInterpreter(self.chatgpt)

        # Phase 7: CatalogSearchService
        self.catalog_search = CatalogSearchService(self.db)

        # Phase 8: PolicyService — dynamic per-turn policy retrieval
        self.policy_service = PolicyService(self.policies if self.policies else "")

        # Phase 9: Handler instances
        from .handlers.policy_handler import PolicyHandler
        from .handlers.escalation_handler import EscalationHandler
        from .handlers.offtopic_handler import OfftopicHandler
        self.policy_handler = PolicyHandler(self.policy_service, self.chatgpt)
        self.escalation_handler = EscalationHandler(
            handoff_service=getattr(self, 'handoff_service', None)
        )
        self.offtopic_handler = OfftopicHandler(llm_client=self.chatgpt)

        # Get available functions
        self.functions = get_available_functions()
        
        # Conversation contexts — evicted after 24h of inactivity (prevents OOM on long-running Railway containers)
        self.contexts: TTLCache = TTLCache(maxsize=5000, ttl=86400)
        
        # Session state — same 24h TTL
        self.sessions: TTLCache = TTLCache(maxsize=5000, ttl=86400)

        try:
            self.flow_manager: Optional[SalesFlowManager] = SalesFlowManager()
            logging.info("sales_flow_manager_initialized tenant=%s", self.tenant_id)
        except Exception as exc:
            self.flow_manager = None
            logging.error("sales_flow_manager_unavailable tenant=%s error=%s", self.tenant_id, exc, exc_info=True)
        
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
            logging.warning("knowledge_load_failed tenant=%s error=%s", self.tenant_id, exc, exc_info=True)
            return None

    def _quote_channel(self, session_id: str = "") -> str:
        """Return the inbound channel for this session, defaulting to 'cli'."""
        if session_id:
            return self.sessions.get(session_id, {}).get("channel", "cli")
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
            channel=self._quote_channel(session_id),
            customer_ref=self.sessions.get(session_id, {}).get("customer_ref", session_id),
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
                logging.warning("quote_automation_refresh_failed tenant=%s quote=%s error=%s", self.tenant_id, quote_id, exc, exc_info=True)
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
                self.handoff_service.create_review_handoff(
                    quote_id,
                    customer_ref=self.sessions.get(session_id, {}).get("customer_ref", session_id),
                )
            return quote_id

    def _ensure_session_initialized(self, session_id: str) -> None:
        if session_id in self.contexts:
            # Sync system prompt in case the config was updated after this session
            # was loaded (e.g. user saved a new manual in the training panel).
            ctx = self.contexts[session_id]
            if ctx and ctx[0].get("role") == "system" and ctx[0].get("content") != self.system_prompt:
                ctx[0]["content"] = self.system_prompt
                logging.info("system_prompt_refreshed_in_memory session=%s tenant=%s", session_id, self.tenant_id)
            # Ensure V2 state is bootstrapped even for already-loaded sessions
            sess = self.sessions.setdefault(session_id, {})
            if "_state_v2" not in sess:
                StateStore.save(sess, StateStore.load(sess))
            return
        # Load from DB first (survives restarts); skip in sandbox to keep tests isolated
        if not self.sandbox_mode:
            persisted_ctx, persisted_state = self.db.load_session(session_id, self.tenant_id)
            if persisted_ctx:
                # Always inject the CURRENT system prompt — never trust what was
                # persisted in the DB, which could reflect an old manual/personality.
                if persisted_ctx and persisted_ctx[0].get("role") == "system":
                    persisted_ctx[0]["content"] = self.system_prompt
                self.contexts[session_id] = persisted_ctx
                self.sessions[session_id] = persisted_state
                # Bootstrap V2 state from any existing legacy keys
                if "_state_v2" not in persisted_state:
                    StateStore.save(persisted_state, StateStore.load(persisted_state))
                return
        self.contexts[session_id] = [{"role": "system", "content": self.system_prompt}]
        self.sessions[session_id] = {}
        # Bootstrap fresh V2 state
        StateStore.save(self.sessions[session_id], ConversationStateV2())
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
        return sanitize_response(response_text)

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
        if faq_result["status"] == "found" and faq_result.get("pregunta_matched"):
            # Use the top-ranked (keyword-matched) FAQ entry's answer directly
            entries = faq_result.get("faq_entries") or []
            response = entries[0]["respuesta"] if entries else ""
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
                    logging.warning("sales_flow_handoff_failed session=%s error=%s", session_id, exc, exc_info=True)

            response_text = str(sales_contract.get("reply_text") or "Te paso con un asesor para continuar.")
            self._set_last_turn_meta(session_id, route_source="model_assisted")
            return self._append_assistant_turn(session_id, response_text)

        if sales_contract.get("missing_fields"):
            response_text = str(sales_contract.get("reply_text") or "")
            if response_text:
                self._set_last_turn_meta(session_id, route_source="model_assisted")
                return self._append_assistant_turn(session_id, response_text)

        return None

    def process_message(
        self,
        session_id: str,
        user_message: str,
        channel: str = "",
        customer_ref: str = "",
    ) -> str:
        """
        Process a user message and return bot response.

        Args:
            session_id:    Unique identifier for conversation (phone, chat ID, etc.)
            user_message:  User's message text (may be extracted from an image/PDF/Excel)
            channel:       Inbound channel — "whatsapp", "instagram", "email", "cli", etc.
            customer_ref:  Customer identifier visible in the channel (phone number, email, etc.)

        Returns:
            Bot's response text
        """
        # ── Input validation ──────────────────────────────────────────────────
        user_message = (user_message or "").strip()
        if not user_message:
            return "¿En qué te puedo ayudar?"

        if len(user_message) > 2000:
            logging.warning(
                "input_too_long session=%s tenant=%s original_len=%d — truncated to 2000",
                session_id,
                self.tenant_id,
                len(user_message),
            )
            user_message = user_message[:2000]

        if not re.search(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]", user_message):
            logging.info(
                "input_no_letters session=%s tenant=%s msg_preview=%.40r — continuing",
                session_id,
                self.tenant_id,
                user_message,
            )
        # ─────────────────────────────────────────────────────────────────────

        self._ensure_session_initialized(session_id)

        # Store channel / customer_ref in session so the quote can be tagged
        if channel:
            self.sessions[session_id]["channel"] = channel
        if customer_ref:
            self.sessions[session_id]["customer_ref"] = customer_ref

        # Phase 10: TurnEvent — create at start of turn
        _sess_init = self.sessions.get(session_id, {})
        _state_v2_init = StateStore.load(_sess_init)
        turn_event = TurnEvent.start(
            session_id=session_id,
            tenant_id=getattr(self, 'tenant_id', 'ferreteria'),
            state_before=_state_v2_init.state,
        )

        if self._is_ferreteria_runtime():
            self._load_active_quote_from_store(session_id)
            # R3: refresh stale prices at turn start, before any response is generated
            _r3_sess = self.sessions.setdefault(session_id, {})
            _r3_aq = _r3_sess.get("active_quote") or []
            if _r3_aq:
                from bot_sales.ferreteria_quote import refresh_stale_prices
                _r3_aq, _r3_notifs = refresh_stale_prices(
                    _r3_aq,
                    lookup_fn=lambda q: next(
                        (float(p.get("price_ars") or 0) or None
                         for p in self.logic.buscar_stock(q).get("products", [])),
                        None,
                    ),
                )
                _r3_sess["active_quote"] = _r3_aq
                if _r3_notifs:
                    _r3_sess["_stale_price_notifications"] = _r3_notifs

        self._record_user_turn(session_id, user_message)
        self._reset_turn_meta(session_id)

        # ── Ferreteria Intent Router (Phase 3) ──────────────────────────────
        # Runs only for ferreteria; classifies into fine-grained intent before
        # passing to the quote builder.  Non-ferreteria flows are unaffected.
        if self._is_ferreteria_runtime():
            ferreteria_route = self._try_ferreteria_intent_route(session_id, user_message)
            # Phase 10: Populate TurnEvent from interpretation stored by _try_ferreteria_intent_route
            _interp = self.sessions.get(session_id, {}).get("last_turn_interpretation") or {}
            turn_event.interpreted_intent = _interp.get("intent", "unknown")
            turn_event.confidence = float(_interp.get("confidence", 0.0))
            turn_event.tone = _interp.get("tone", "neutral")
            turn_event.policy_topic = _interp.get("policy_topic")
            turn_event.search_mode = _interp.get("search_mode")
            _catalog = self.sessions.get(session_id, {}).get("last_catalog_result") or {}
            turn_event.candidate_count = len(_catalog.get("candidates", []))
            if ferreteria_route is not None:
                _state_after = StateStore.load(self.sessions.get(session_id, {})).state
                turn_event.state_after = _state_after
                # Determine handler name from intent
                _intent = turn_event.interpreted_intent
                if _intent == "policy_faq":
                    turn_event.handler = "policy"
                elif _intent in ("off_topic", "small_talk"):
                    turn_event.handler = "offtopic"
                elif _intent == "escalate":
                    turn_event.handler = "escalation"
                    record_escalation(
                        StateStore.load(self.sessions.get(session_id, {})).escalation_status or "unknown"
                    )
                else:
                    turn_event.handler = "intent_route"
                if _catalog:
                    record_search(_catalog.get("status", "unknown"))
                turn_event.log()
                record_turn(turn_event.interpreted_intent, turn_event.handler, turn_event.state_after)
                record_latency_bucket(turn_event.latency_ms)
                return ferreteria_route

        # Trim context if too long (keep system message + last N messages)
        self._trim_context(session_id)

        # Check for LITE MODE (Basic Bot)
        from .config import LITE_MODE
        if LITE_MODE:
            result = self._handle_lite_mode(session_id, user_message)
            turn_event.handler = "lite_mode"
            turn_event.state_after = StateStore.load(self.sessions.get(session_id, {})).state
            turn_event.log()
            record_turn(turn_event.interpreted_intent, turn_event.handler, turn_event.state_after)
            record_latency_bucket(turn_event.latency_ms)
            return result

        ferreteria_pre_route = self._try_ferreteria_pre_route(session_id, user_message)
        if ferreteria_pre_route:
            result = self._append_assistant_turn(session_id, ferreteria_pre_route)
            turn_event.handler = "pre_route"
            turn_event.state_after = StateStore.load(self.sessions.get(session_id, {})).state
            turn_event.log()
            record_turn(turn_event.interpreted_intent, turn_event.handler, turn_event.state_after)
            record_latency_bucket(turn_event.latency_ms)
            return result

        sales_contract = self._run_sales_intelligence(session_id, user_message)
        self.sessions[session_id]["sales_intelligence_v1"] = self._build_sales_intelligence_meta(sales_contract)
        sales_response = self._handle_sales_contract_reply(session_id, sales_contract)
        if sales_response is not None:
            turn_event.handler = "sales_intelligence"
            turn_event.state_after = StateStore.load(self.sessions.get(session_id, {})).state
            turn_event.log()
            record_turn(turn_event.interpreted_intent, turn_event.handler, turn_event.state_after)
            record_latency_bucket(turn_event.latency_ms)
            return sales_response

        # Process with ChatGPT (with potential function calls)
        response_text = self._chat_with_functions(session_id)
        result = self._append_assistant_turn(session_id, response_text)
        turn_event.handler = "llm_fallback"
        turn_event.state_after = StateStore.load(self.sessions.get(session_id, {})).state
        turn_event.log()
        record_turn(turn_event.interpreted_intent, turn_event.handler, turn_event.state_after)
        record_latency_bucket(turn_event.latency_ms)
        return result

    def _try_ferreteria_intent_route(
        self,
        session_id: str,
        user_message: str,
    ) -> Optional[str]:
        """
        Run the ferreteria TurnInterpreter (Phase 6) and dispatch to intent handlers.

        TurnInterpreter classifies intent, extracts entities, detects tone, and fills
        quote context in a single LLM call. Its result is stored and used to
        short-circuit common intents before the quote builder runs.

        Returns a final response string if the intent warrants special handling,
        or None to continue with the normal flow (quote builder etc.).
        """
        sess = self.sessions.setdefault(session_id, {})
        ctx = self.contexts.get(session_id, [])
        history = [m for m in ctx if m.get("role") in ("user", "assistant")][-6:]

        # ── Phase 6: TurnInterpreter ─────────────────────────────────────────
        state_v2 = StateStore.load(sess)
        current_state = state_v2.state if state_v2 else "idle"

        last_offered = sess.get("last_offered_products") or []

        try:
            interpretation = self.turn_interpreter.interpret(
                user_message,
                history=history,
                current_state=current_state,
                last_offered_products=last_offered,
            )
            sess["last_turn_interpretation"] = interpretation.to_dict()
            logging.info(
                "turn_interpreter session=%s intent=%s confidence=%.2f tone=%s",
                session_id,
                interpretation.intent,
                interpretation.confidence,
                interpretation.tone,
            )
        except Exception as exc:
            logging.warning("turn_interpreter_failed session=%s error=%s", session_id, exc)
            interpretation = TurnInterpretation.unknown()

        # Handle reset signal — clear quote state
        if interpretation.reset_signal:
            sess.pop("active_quote", None)
            sess.pop("quote_state", None)
            state_v2 = StateStore.load(sess)
            state_v2.transition("idle")
            state_v2.active_quote_id = None
            state_v2.acceptance_pending = False
            StateStore.save(sess, state_v2)
            logging.info("turn_interpreter reset_signal session=%s", session_id)

        # Phase 7: CatalogSearchService — run when intent is product_search
        if interpretation.intent == "product_search" and not interpretation.is_low_confidence():
            try:
                from bot_sales.services.search_validator import (
                    validate_query_specs,
                    validate_search_match,
                )
                from bot_sales.services.catalog_search_service import CatalogSearchResult

                need = ProductNeed.from_turn_interpretation(interpretation)

                # Level 1: detect impossible specs BEFORE searching the catalog.
                l1_valid, l1_reason = validate_query_specs(user_message)
                if not l1_valid:
                    logging.info(
                        "search_validator.blocked_pre_catalog session=%s reason=%s",
                        session_id, l1_reason,
                    )
                    catalog_result = CatalogSearchResult(
                        status="no_match", reason_codes=["impossible_spec"]
                    )
                else:
                    catalog_result = self.catalog_search.search(need)

                    # Level 2: verify spec claims against returned products.
                    if catalog_result.status in ("resolved", "options") and catalog_result.candidates:
                        l2_valid, l2_reason = validate_search_match(
                            user_message, catalog_result.candidates
                        )
                        if not l2_valid:
                            logging.info(
                                "search_validator.blocked_post_catalog session=%s reason=%s",
                                session_id, l2_reason,
                            )
                            catalog_result = CatalogSearchResult(
                                status="no_match", reason_codes=["spec_mismatch"]
                            )

                sess["last_catalog_result"] = catalog_result.to_dict()
                logging.info(
                    "catalog_search session=%s status=%s candidates=%d",
                    session_id,
                    catalog_result.status,
                    len(catalog_result.candidates),
                )
            except Exception as exc:
                logging.warning("catalog_search_failed session=%s error=%s", session_id, exc)

        # Phase 9: quote_modify — delegate to LLM with active quote context (C5)
        # Exception: additive ("agregale"), reset, and clarification messages must go through
        # _try_ferreteria_pre_route first so deterministic handlers apply correctly.
        if interpretation.intent == "quote_modify" and not interpretation.is_low_confidence():
            _open_q = sess.get("active_quote")

            # B22a: compound modify-modify handler.
            # Fires only when TI explicitly provided sub_commands (compound_message=true)
            # and every sub-command maps to a deterministic modify handler.
            # If processing succeeds → return unified response.
            # If it fails → fall through to the normal single-turn path unchanged.
            if (
                interpretation.compound_message
                and interpretation.sub_commands
                and _open_q
                and self._all_sub_commands_look_like_modify(interpretation.sub_commands)
            ):
                _compound_reply = self._process_compound_modify(
                    session_id, interpretation, user_message, sess, self._knowledge()
                )
                if _compound_reply is not None:
                    return self._append_assistant_turn(session_id, _compound_reply)
                # else: sub-command processing failed — continue to normal path

            _is_clarification_via_llm = (
                interpretation.quote_reference.references_existing_quote
                and bool(_open_q)
            )
            _is_deterministic = (
                fq.looks_like_additive(user_message)
                or fq.looks_like_reset(user_message)
                or _is_clarification_via_llm
            )
            if not _is_deterministic:
                self._trim_context(session_id)
                response_text = self._chat_with_functions(session_id)
                return self._append_assistant_turn(session_id, response_text)
            # else: fall through to _try_ferreteria_pre_route

        # Phase 9: PolicyHandler — handles policy_faq intent
        if interpretation.intent == "policy_faq" and not interpretation.is_low_confidence():
            messages = list(self.contexts.get(session_id, []))
            response_text = self.policy_handler.handle(
                user_message=user_message,
                interpretation=interpretation,
                messages=messages,
                system_prompt=self.system_prompt,
            )
            return self._append_assistant_turn(session_id, response_text)

        # Phase 9: OfftopicHandler — handles off_topic and small_talk intents
        if interpretation.intent in ("off_topic", "small_talk") and not interpretation.is_low_confidence():
            messages = list(self.contexts.get(session_id, []))
            response_text = self.offtopic_handler.handle(
                user_message=user_message,
                interpretation=interpretation,
                messages=messages,
                system_prompt=self.system_prompt,
            )
            return self._append_assistant_turn(session_id, response_text)

        # Phase 9: EscalationHandler — handles escalate intent or frustration-triggered handoffs
        if (
            interpretation.intent == "escalate"
            or self.escalation_handler.should_escalate_on_frustration(interpretation)
        ) and not interpretation.is_low_confidence():
            state_v2 = StateStore.load(sess)
            customer_contact = sess.get("customer_ref") or session_id
            response_text = self.escalation_handler.handle(
                session_id=session_id,
                user_message=user_message,
                interpretation=interpretation,
                state_v2=state_v2,
                customer_contact=customer_contact,
            )
            StateStore.save(sess, state_v2)
            return self._append_assistant_turn(session_id, response_text)

        # ── B24: Escalation safety net ──────────────────────────────────────
        # When TurnInterpreter fails (interpretation.intent == "unknown" +
        # confidence == 0.0), apply a minimal keyword-based escalation detector.
        # Covers the edge case of LLM failure + user requesting human handoff
        # in the same turn. Only activates on TurnInterpretation.unknown().
        if interpretation.intent == "unknown" and interpretation.confidence == 0.0:
            if self._looks_like_escalation_request(user_message):
                logging.info(
                    "escalation_safety_net session=%s reason=turn_interpreter_failed",
                    session_id,
                )
                state_v2 = StateStore.load(sess)
                customer_contact = sess.get("customer_ref") or session_id
                response_text = self.escalation_handler.handle(
                    session_id=session_id,
                    user_message=user_message,
                    interpretation=interpretation,
                    state_v2=state_v2,
                    customer_contact=customer_contact,
                )
                StateStore.save(sess, state_v2)
                return self._append_assistant_turn(session_id, response_text)

        # ── B22c: compound accept + customer_info ───────────────────────────
        # Fires when TI classified quote_accept + compound_message=true AND
        # sub_commands include at least one customer info phrase. Processes
        # info storage + acceptance in one turn without a second LLM call.
        # Fallback: returns None → pre_route section-0.5 handles acceptance.
        if (
            interpretation.intent == "quote_accept"
            and interpretation.compound_message
            and interpretation.sub_commands
            and sess.get("active_quote")
        ):
            _mixed_reply = self._process_compound_mixed(
                session_id, interpretation, user_message, sess, self._knowledge()
            )
            if _mixed_reply is not None:
                return self._append_assistant_turn(session_id, _mixed_reply)
            # else: fallthrough → pre_route handles acceptance normally

        # ── B24: legacy IntentRouter fallback removed.
        # TurnInterpretation.unknown() + downstream handlers cover the empty case.
        return None

    def _try_ferreteria_pre_route(self, session_id: str, user_message: str) -> Optional[str]:
        """Tenant-specific product-first routing for ferreteria with full multi-turn state."""
        if not self._is_ferreteria_runtime():
            return None

        text = (user_message or "").strip()
        if not text:
            return None

        normalized = self._normalize_lookup_text(text)
        sess = self.sessions.setdefault(session_id, {})
        # Load V2 state at the start of each turn for this route
        state_v2 = StateStore.load(sess)
        quote_state: Optional[str] = sess.get("quote_state")
        open_quote: Optional[List] = sess.get("active_quote")
        knowledge = self._knowledge()

        # ── 0. TurnInterpreter intent (from _try_ferreteria_intent_route) ─────
        # Small-talk, FAQ, escalate, and non-quote intents are handled by their
        # specialist handlers before pre_route runs. Only quote_* and product_search
        # intents (plus unknown) fall through here.
        intent = sess.get("last_turn_interpretation", {}).get("intent", "unknown")

        def _done(response: str, route_source: str = "deterministic", **meta: Any) -> str:
            # Persist offered products so TurnInterpreter can resolve "el primero" etc.
            offered = meta.pop("products", None)
            if offered is not None:
                sess["last_offered_products"] = [
                    {
                        "name": p.get("model") or p.get("name") or p.get("sku", "Producto"),
                        "brand": p.get("proveedor") or p.get("brand") or "",
                        "price_formatted": p.get("price_formatted") or "precio a confirmar",
                        "sku": p.get("sku") or "",
                    }
                    for p in offered[:5]
                ]
            payload = {"route_source": route_source}
            payload.update(meta)
            self._set_last_turn_meta(session_id, **payload)
            # Sync V2 state back after each deterministic route completes
            StateStore.save(sess, state_v2)
            return response

        # ── 0.5. Acceptance ──────────────────────────────────────────────────
        # B21+B23: si TurnInterpreter clasificó quote_modify, confiar en esa
        # señal — el cliente está modificando el carrito, no aceptando. Esto
        # cubre casos como T2 de E41 ("cualquiera está bien" con item ambiguo)
        # donde looks_like_acceptance disparaba prematuramente y el carrito
        # quedaba accepted con un ítem sin resolver.
        if (
            open_quote
            and intent != "quote_modify"
            and fq.looks_like_acceptance(text, knowledge=knowledge, chatgpt_client=self.chatgpt)
        ):
            response = fq.generate_acceptance_response(open_quote, knowledge=knowledge)
            if "✓" in response:
                self._accept_quote_for_review(session_id, user_message, response)
                sess["quote_state"] = "accepted"
                sess.pop("pending_decision", None)
                sess.pop("pending_clarification_target", None)
                state_v2.transition("awaiting_customer_confirmation")
                state_v2.acceptance_pending = True
            else:
                self._persist_quote_state(
                    session_id,
                    response_text=response,
                    user_message=user_message,
                    event_type="quote_acceptance_blocked",
                    event_payload={"reason": "pending_lines"},
                )
                state_v2.transition("awaiting_clarification")
            return _done(response, "deterministic")

        # ── 1. Explicit reset ────────────────────────────────────────────────
        if fq.looks_like_reset(text, knowledge=knowledge):
            if self.quote_service:
                self.quote_service.mark_reset(session_id)
            sess.pop("active_quote", None)
            sess.pop("quote_state", None)
            sess.pop("pending_decision", None)
            sess.pop("pending_clarification_target", None)
            state_v2.transition("idle")
            state_v2.active_quote_id = None
            state_v2.acceptance_pending = False
            return _done("Presupuesto borrado. Cuando quieras empezamos uno nuevo.", "deterministic")

        # ── 1.5. Post-acceptance guard: clear for fresh request ──────────────
        if quote_state == "accepted":
            # If still within accepted state, a new request starts fresh
            # (FAQ already handled above; acceptance phrases would be weird here)
            sess.pop("active_quote", None)
            sess.pop("quote_state", None)
            sess.pop("pending_decision", None)
            open_quote = None
            state_v2.transition("idle")
            state_v2.acceptance_pending = False

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
                state_v2.transition("quote_drafting")
                comps = self._get_suggestions(merged, knowledge=knowledge)
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
                state_v2.transition("quote_drafting")
                comps = self._get_suggestions(pending_items, knowledge=knowledge)
                reply = self._generate_quote_response(pending_items, complementary=comps or None, session_id=session_id)
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

            if turns >= 3:
                # Too many ambiguous turns: clear the pending state and let the LLM
                # take over naturally — avoids infinite "sumar o nuevo" loop.
                # The LLM still has the pending items in context and can decide.
                logging.info(
                    "merge_vs_replace_loop_exceeded session=%s turns=%d — releasing to LLM",
                    session_id, turns,
                )
                sess.pop("pending_decision", None)
                return None  # falls through to _chat_with_functions
            # Re-ask once before releasing to LLM
            return _done(fq.MERGE_VS_REPLACE_QUESTION, "deterministic")

        # ── 2.5. Pending clarification target resolution ─────────────────────
        # When needs_disambiguation fired, we stored the candidates.
        # A follow-up reply like "la mecha" should resolve to the stored target.
        pending_clarif_target = sess.get("pending_clarification_target")

        # ── 2.7. Remove operation ────────────────────────────────────────────
        if open_quote and fq.looks_like_remove(text):
            updated, msg = fq.apply_remove(text, open_quote)
            sess["active_quote"] = updated
            comps = self._get_suggestions(updated, knowledge=knowledge)
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
            comps = self._get_suggestions(updated, knowledge=knowledge)
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
            state_v2.transition("quote_drafting")
            comps = self._get_suggestions(updated, knowledge=knowledge)
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
                # B23-FU: TurnInterpreter referenced_offer_index is primary source
                # for option selection (e.g. "cualquiera está bien" → idx 0).
                _ti_ref_idx = sess.get("last_turn_interpretation", {}).get("referenced_offer_index")
                followup = apply_followup_to_open_quote(
                    text,
                    open_quote,
                    self.logic,
                    knowledge=knowledge,
                    pending_target_ids=pending_clarif_target,
                    ti_ref_idx=_ti_ref_idx,
                )

                if followup.get("status") == "needs_disambiguation":
                    target_ids = followup.get("candidate_target_ids") or [
                        it.get("line_id") for it in open_quote
                        if it.get("status") in ("ambiguous", "unresolved", "blocked_by_missing_info")
                    ]
                    sess["pending_clarification_target"] = [line_id for line_id in target_ids if line_id]
                    state_v2.transition("awaiting_clarification")
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
                    state_v2.transition("quote_drafting")
                    if followup.get("status") == "updated":
                        sess.pop("pending_clarification_target", None)
                        comps = self._get_suggestions(updated, knowledge=knowledge)
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
                            state_v2.transition("awaiting_clarification")
                        comps = self._get_suggestions(updated, knowledge=knowledge)
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
        _refs_existing = sess.get("last_turn_interpretation", {}).get("quote_reference", {}).get("references_existing_quote", False)
        if open_quote and _refs_existing:
            disambig = fq.needs_disambiguation(text, open_quote)
            if disambig:
                # Store the pending candidates by line_id so next reply resolves correctly
                pending_cands = [
                    it for it in open_quote if it["status"] in ("ambiguous", "unresolved", "blocked_by_missing_info")
                ]
                sess["pending_clarification_target"] = [
                    it.get("line_id") for it in pending_cands if it.get("line_id")
                ]
                state_v2.transition("awaiting_clarification")
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
            # Transition V2 state based on whether any lines are still pending
            _still_pending = any(
                it.get("status") in ("ambiguous", "unresolved", "blocked_by_missing_info")
                for it in updated
            )
            state_v2.transition("awaiting_clarification" if _still_pending else "quote_drafting")
            comps = self._get_suggestions(updated, knowledge=knowledge)
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
            # P1: load knowledge once, resolve items in parallel (was sequential)
            _knowledge_snapshot = self._knowledge()
            def _resolve_item(p):
                return fq.resolve_quote_item(p, self.logic, knowledge=_knowledge_snapshot)
            # MAX_WORKERS_OVERRIDE env var allows capping parallelism for local dev.
            # Useful on Python 3.14 where ThreadPoolExecutor + SQLite causes SIGSEGV.
            # In production (Railway, Python 3.11/3.12), leave unset for full P1 parallelism.
            _override = os.environ.get("MAX_WORKERS_OVERRIDE")
            if _override:
                try:
                    n_workers = max(1, int(_override))
                except ValueError:
                    n_workers = min(len(parsed_items), 5)
            else:
                n_workers = min(len(parsed_items), 5)
            with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as _pool:
                resolved_items = list(_pool.map(_resolve_item, parsed_items))

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
            state_v2.transition("quote_drafting")
            comps = self._get_suggestions(resolved_items, knowledge=knowledge)
            reply = self._generate_quote_response(resolved_items, complementary=comps or None, session_id=session_id)
            self._persist_quote_state(
                session_id,
                response_text=reply,
                user_message=user_message,
                event_type="quote_opened",
                event_payload={"line_count": len(resolved_items)},
            )
            return _done(reply, "deterministic")

        # ── 6. Single-item / category / product-first paths ──────────────────
        generic_category_browse_terms = {
            "herramientas electricas",
            "herramienta electrica",
            "herramientas",
            "herramienta",
            "herramientas manuales",
            "manual",
            "tornilleria",
            "fijaciones",
            "mechas",
            "brocas",
            "pinturas",
            "pintureria",
            "electricidad",
            "plomeria",
            "seguridad",
            "puntas y accesorios",
        }
        short_category = self._detect_ferreteria_browse_category(normalized)
        if short_category and normalized in generic_category_browse_terms:
            result = self.logic.buscar_por_categoria(short_category)
            if result.get("status") == "found":
                _prods = result.get("products", [])
                return _done(
                    self._format_ferreteria_products_reply(
                        _prods,
                        heading=f"Te paso opciones de **{short_category}** con stock:",
                        category_hint=short_category,
                        query_hint=normalized,
                    ),
                    "deterministic",
                    products=_prods,
                )

        # If TurnInterpreter found no specific product terms, the message is a
        # broad/project-scope request (e.g. "presupuesto para un baño").
        # Ask for specific products/rubros instead of attempting a catalog lookup.
        _ti_product_terms = (
            sess.get("last_turn_interpretation", {}).get("entities", {}).get("product_terms") or []
        )
        if intent == "product_search" and not _ti_product_terms:
            return _done(fq.BROAD_REQUEST_REPLY, "deterministic")

        # V1 physical spec guardrail — runs before intent gate.
        # Impossible specs (e.g. "martillo 500kg") must be explicitly rejected
        # regardless of TI's intent classification; TI may return "unknown" for
        # absurd requests and the spec validator would otherwise be skipped.
        from bot_sales.services.search_validator import validate_query_specs, validate_search_match
        _l1_valid, _l1_reason = validate_query_specs(text)
        if not _l1_valid:
            logging.info(
                "search_validator.blocked_pre_route session=%s reason=%s",
                session_id, _l1_reason,
            )
            return _done(
                "No tenemos ese producto en el catálogo. "
                "Las especificaciones indicadas no coinciden con ningún artículo disponible. "
                "Si querés, podemos buscar algo similar con especificaciones estándar.",
                "deterministic",
            )

        if intent == "product_search":
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
                    _prods = resolved_single.get("products", [])
                    return _done(
                        self._format_ferreteria_products_reply(
                            _prods,
                            query_hint=single_norm,
                        ),
                        "deterministic",
                        products=_prods,
                    )

                if resolved_single.get("status") in ("resolved", "ambiguous", "unresolved", "blocked_by_missing_info"):
                    # Level 2: verify spec claims against resolved products.
                    _resolved_prods = resolved_single.get("products", [])
                    if _resolved_prods:
                        _l2_valid, _l2_reason = validate_search_match(text, _resolved_prods)
                        if not _l2_valid:
                            logging.info(
                                "search_validator.blocked_post_route session=%s reason=%s",
                                session_id, _l2_reason,
                            )
                            return _done(
                                "No tenemos ese producto en el catálogo. "
                                "Las especificaciones indicadas no coinciden con ningún artículo disponible. "
                                "Si querés, podemos buscar algo similar con especificaciones estándar.",
                                "deterministic",
                            )

                    sess["active_quote"] = [resolved_single]
                    sess["quote_state"] = "open"
                    if resolved_single.get("status") in ("ambiguous", "unresolved", "blocked_by_missing_info"):
                        state_v2.transition("awaiting_clarification")
                    else:
                        state_v2.transition("quote_drafting")
                    comps = []
                    if resolved_single.get("status") == "resolved":
                        comps = self._get_suggestions([resolved_single], knowledge=knowledge)
                    reply = self._generate_quote_response([resolved_single], complementary=comps or None, session_id=session_id)
                    self._persist_quote_state(
                        session_id,
                        response_text=reply,
                        user_message=user_message,
                        event_type="quote_opened",
                        event_payload={"line_count": 1},
                    )
                    return _done(reply, "deterministic")

            # Fallback direct stock search — also guarded by L1 (already checked above).
            stock_result = self.logic.buscar_stock(text)
            if stock_result.get("status") == "found":
                _prods = stock_result.get("products", [])
                return _done(self._format_ferreteria_products_reply(_prods), "deterministic", products=_prods)
            if stock_result.get("status") == "no_stock":
                alternatives = self.logic.buscar_alternativas(text)
                if alternatives.get("status") == "found":
                    _prods = alternatives.get("alternatives", [])
                    return _done(self._format_ferreteria_products_reply(
                        _prods,
                        heading="No tengo stock exacto de eso ahora, pero si estas alternativas:",
                    ), "deterministic", products=_prods)
                return _done("Ese producto existe pero hoy no tiene stock. Busco alternativa por uso o medida si queres.", "deterministic")
            if stock_result.get("status") == "no_match":
                return _done(
                    "No encontre ese item exacto en el catalogo actual.\n\n"
                    "Decime una de estas dos cosas y sigo:\n"
                    "1. La medida, uso o material\n"
                    "2. El rubro del producto",
                    "fallback",
                )

        if intent == "product_search":
            category = self._detect_ferreteria_browse_category(normalized)
            if category:
                result = self.logic.buscar_por_categoria(category)
                if result.get("status") == "found":
                    _prods = result.get("products", [])
                    return _done(
                        self._format_ferreteria_products_reply(
                            _prods,
                            heading=f"Te paso opciones de **{category}** con stock:",
                            category_hint=category,
                            query_hint=normalized,
                        ),
                        "deterministic",
                        products=_prods,
                    )
                return _done(f"No veo stock activo en **{category}** ahora. Decime uso, medida o presupuesto y te propongo alternativa.", "deterministic")

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

    def _detect_ferreteria_browse_category(self, normalized_message: str) -> Optional[str]:
        # Category names must match exactly what is stored in the catalog DB.
        # Verified against data/tenants/ferreteria/catalog.csv.
        aliases = {
            "herramientas electricas": "Herramientas Eléctricas",
            "herramienta electrica": "Herramientas Eléctricas",
            "herramienta": "Herramientas Eléctricas",
            "herramientas": "Herramientas Eléctricas",
            "taladro": "Herramientas Eléctricas",
            "amoladora": "Herramientas Eléctricas",
            "atornillador": "Herramientas Eléctricas",
            "manual": "Herramientas Manuales",
            "herramientas manuales": "Herramientas Manuales",
            "martillo": "Herramientas Manuales",
            "destornillador": "Herramientas Manuales",
            "llave": "Herramientas Manuales",
            "tornilleria": "Tornillería y Fijaciones",
            "tornillo": "Tornillería y Fijaciones",
            "tornillos": "Tornillería y Fijaciones",
            "fijacion": "Tornillería y Fijaciones",
            "fijaciones": "Tornillería y Fijaciones",
            "tarugo": "Tornillería y Fijaciones",
            "tarugos": "Tornillería y Fijaciones",
            "anclaje": "Tornillería y Fijaciones",
            "mecha": "Mechas y Brocas",
            "mechas": "Mechas y Brocas",
            "broca": "Mechas y Brocas",
            "brocas": "Mechas y Brocas",
            "disco": "Discos y Hojas",
            "discos": "Discos y Hojas",
            "lija": "Lijas y Abrasivos",
            "lijas": "Lijas y Abrasivos",
            "cinta": "Cintas y Adhesivos",
            "cintas": "Cintas y Adhesivos",
            "adhesivo": "Cintas y Adhesivos",
            "pintura": "Pinturas y Acabados",
            "pinturas": "Pinturas y Acabados",
            "pintureria": "Pinturas y Acabados",
            "rodillo": "Pinturas y Acabados",
            "latex": "Pinturas y Acabados",
            "esmalte": "Pinturas y Acabados",
            "sellador": "Pinturas y Acabados",
            "cable": "Electricidad",
            "cables": "Electricidad",
            "electricidad": "Electricidad",
            "tomacorriente": "Electricidad",
            "silicona": "Plomería",
            "teflon": "Plomería",
            "plomeria": "Plomería",
            "cano": "Plomería",
            "seguridad": "Seguridad",
            "guante": "Seguridad",
            "guantes": "Seguridad",
            "casco": "Seguridad",
            "puntas": "Puntas y Accesorios",
            "accesorio": "Puntas y Accesorios",
            "accesorios": "Puntas y Accesorios",
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
        session_id: Optional[str] = None,
    ) -> str:
        """Format resolved items into a structured customer-facing quote."""
        reply = fq.generate_quote_response(resolved_items, complementary=complementary)
        if session_id:
            _notifs = self.sessions.get(session_id, {}).pop("_stale_price_notifications", None)
            if _notifs:
                reply += "\n\n📌 *Actualización de precios:*\n" + "\n".join(_notifs)
        return reply

    def _get_suggestions(
        self,
        resolved_items: List[Dict[str, Any]],
        knowledge: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Combine catalog-grounded complementary suggestions with profile cross-sell rules."""
        comps = fq.get_complementary_suggestions(resolved_items, self.logic, knowledge=knowledge)
        cross_sell_rules = (
            self.tenant_profile.get("cross_sell_rules") or []
            if isinstance(self.tenant_profile, dict)
            else []
        )
        cross = fq.get_cross_sell_suggestions(resolved_items, self.logic, cross_sell_rules=cross_sell_rules)
        # Deduplicate: complementary takes priority (catalog-grounded); cross-sell fills remaining slots
        seen = set(comps)
        for item in cross:
            if item not in seen:
                comps.append(item)
                seen.add(item)
        return comps[:3]

    @staticmethod
    def _consultative_browse_cta(query_hint: str = "", category_hint: str = "") -> str:
        hint = f"{query_hint} {category_hint}".strip().lower()
        if any(token in hint for token in ("taladro", "amoladora", "atornillador", "herramientas electricas")):
            return "Si queres, te marco cual conviene mas para hogar, obra o uso seguido."
        if any(token in hint for token in ("tornillo", "tarugo", "fijacion", "mecha", "broca", "tornilleria")):
            return "Si me decis superficie, medida o material, te digo cual conviene sin hacerte errarle."
        if any(token in hint for token in ("silicona", "sellador", "teflon", "plomeria", "cano", "conexion")):
            return "Si me decis uso y medida, te confirmo la opcion correcta y te lo dejo fino."
        if any(token in hint for token in ("pintura", "latex", "esmalte", "rodillo", "pintureria")):
            return "Si me decis interior o exterior y la superficie, te recomiendo la opcion mas conveniente."
        return "Si queres, te ayudo a elegir por uso, medida, marca o presupuesto."

    @classmethod
    def _format_ferreteria_products_reply(
        cls,
        products: List[Dict[str, Any]],
        heading: str = "Encontre estas opciones con stock:",
        *,
        category_hint: str = "",
        query_hint: str = "",
    ) -> str:
        if heading == "Encontre estas opciones con stock:" and len(products) == 1 and query_hint:
            heading = "Para arrancar, iria con esta opcion con stock:"
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
        lines.append(cls._consultative_browse_cta(query_hint=query_hint, category_hint=category_hint))
        return "\n".join(lines)

    @staticmethod
    def _looks_like_escalation_request(user_message: str) -> bool:
        norm = (user_message or "").strip().lower()
        return any(kw in norm for kw in _ESCALATION_REQUEST_KEYWORDS)

    @staticmethod
    def _all_sub_commands_look_like_modify(sub_commands: List) -> bool:
        """Return True iff every sub-command maps to a deterministic modify handler.

        Uses the union of all four detectors — at least one must match each sub-command.
        A sub-command that matches none triggers a fallback to the normal single-turn path.
        """
        if not sub_commands:
            return False
        for cmd in sub_commands:
            cmd_str = str(cmd)
            if (
                fq.looks_like_remove(cmd_str)
                or fq.looks_like_additive(cmd_str)
                or fq.looks_like_reset(cmd_str)
                or fq.detect_option_selection(cmd_str) is not None
            ):
                continue
            return False
        return True

    def _process_compound_modify(
        self,
        session_id: str,
        interpretation: Any,
        user_message: str,
        sess: dict,
        knowledge: Any,
    ) -> Optional[str]:
        """Process a compound quote_modify turn by dispatching each sub-command sequentially.

        Atomic processing: takes a shallow copy of the cart on entry. Each handler
        (apply_additive, apply_remove, apply_followup_to_open_quote) is expected to
        RETURN a new list of items, NOT mutate the input in-place. If any handler raises
        or returns an empty/invalid result, the original cart is restored and None is
        returned (fallback to normal single-turn path).

        Returns reply text on success, or None to signal fallback.
        """
        sub_commands = interpretation.sub_commands
        original_cart = list(sess.get("active_quote") or [])
        current_cart = list(original_cart)

        logging.info(
            "compound_modify session=%s intent=%s n_sub=%d sub_cmds=%r",
            session_id, interpretation.intent,
            len(sub_commands), sub_commands,
        )

        for i, cmd in enumerate(sub_commands):
            cmd_str = str(cmd).strip()
            success = False
            try:
                # Dispatch order matters: explicit intent (remove) wins over implicit intent
                # (option_select). E.g. "sacame el segundo" matches both looks_like_remove
                # and detect_option_selection(→1), but the user clearly means remove.
                if fq.looks_like_remove(cmd_str):
                    updated, _msg = fq.apply_remove(cmd_str, current_cart)
                    if updated is not None:
                        current_cart = updated
                        success = True

                elif fq.looks_like_additive(cmd_str):
                    updated = fq.apply_additive(
                        cmd_str, current_cart, self.logic, knowledge=knowledge
                    )
                    if updated is not None:
                        current_cart = updated
                        success = True

                elif fq.looks_like_reset(cmd_str):
                    current_cart = []
                    success = True

                elif (opt_idx := fq.detect_option_selection(cmd_str)) is not None:
                    # Apply option selection directly — do NOT route through
                    # apply_followup_to_open_quote because classify_followup_message
                    # would return kind="none" for phrases starting with "dame"
                    # (which is in _FRESH_REQUEST_WORDS), causing an early not_followup
                    # return before the option selection branch is ever reached.
                    # B22b: extract explicit qty from cmd ("dame dos del primero" → qty=2).
                    _opt_qty = fq._extract_qty_from_phrase(cmd_str)
                    _pending = [
                        it for it in current_cart
                        if it.get("status") in ("ambiguous", "unresolved", "blocked_by_missing_info")
                    ]
                    if _pending:
                        target_id = _pending[0].get("line_id")
                        _opt_updated: List = []
                        _improved = False
                        for _line in current_cart:
                            if _line.get("line_id") != target_id:
                                _opt_updated.append(_line)
                                continue
                            _candidates = _line.get("products") or []
                            if opt_idx < len(_candidates):
                                _chosen = _candidates[opt_idx]
                                _qty = _opt_qty if _opt_qty is not None else _line.get("qty", 1)
                                _uprice, _sub = fq._compute_subtotal(_chosen, _qty)
                                _new = dict(_line)
                                _new.update({
                                    "status": "resolved",
                                    "products": [_chosen],
                                    "qty": _qty,
                                    "unit_price": _uprice,
                                    "subtotal": _sub,
                                    "clarification": None,
                                    "notes": None,
                                    "issue_type": None,
                                })
                                _opt_updated.append(_new)
                                _improved = True
                            else:
                                _opt_updated.append(_line)
                        if _improved:
                            current_cart = _opt_updated
                            success = True
                        # else: opt_idx out of range → success stays False → abort

            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "compound_modify_fallback session=%s reason=exception step=%d cmd=%r exc=%s",
                    session_id, i, cmd_str, exc,
                )
                sess["active_quote"] = original_cart
                return None

            logging.info(
                "compound_modify_step session=%s step=%d/%d cmd=%r ok=%s",
                session_id, i + 1, len(sub_commands), cmd_str, success,
            )

            if not success:
                logging.warning(
                    "compound_modify_fallback session=%s reason=step_no_progress step=%d cmd=%r",
                    session_id, i, cmd_str,
                )
                sess["active_quote"] = original_cart
                return None

        # All sub-commands processed — commit and respond
        sess["active_quote"] = current_cart
        sess["quote_state"] = "open"
        comps = self._get_suggestions(current_cart, knowledge=knowledge)
        reply = fq.generate_updated_quote_response(current_cart, complementary=comps or None)
        self._persist_quote_state(
            session_id,
            response_text=reply,
            user_message=user_message,
            event_type="compound_modify",
            event_payload={
                "sub_commands": sub_commands,
                "n_sub": len(sub_commands),
            },
        )
        logging.info(
            "compound_modify_done session=%s n_sub=%d cart_size=%d",
            session_id, len(sub_commands), len(current_cart),
        )
        return reply

    def _process_compound_mixed(
        self,
        session_id: str,
        interpretation: Any,
        user_message: str,
        sess: dict,
        knowledge: Any,
    ) -> Optional[str]:
        """Process a compound quote_accept + customer_info turn.

        B22c-min scope: TI classified overall intent=quote_accept and
        compound_message=true. Sub-commands contain at least one customer
        info phrase (shipping zone, name, phone, etc.) in addition to the
        acceptance command. No extra LLM call.

        Atomicity: if acceptance fails (pending blocked items, exception),
        customer_delivery_info is restored to its pre-call state and None
        is returned to signal fallback to the normal pre_route path.

        customer_delivery_info.raw is free text. Structuring to specific
        fields (shipping_zone, customer_name, billing_target) is a follow-up
        when the reviewer handoff format is defined.
        """
        sub_cmds = interpretation.sub_commands
        if not sub_cmds:
            return None

        info_cmds = [c for c in sub_cmds if fq.looks_like_customer_info(c)]
        if not info_cmds:
            return None

        logging.info(
            "compound_mixed session=%s n_info=%d info_cmds=%r",
            session_id, len(info_cmds), info_cmds,
        )

        open_quote = sess.get("active_quote")
        if not open_quote:
            return None

        # Snapshot for atomic rollback
        customer_info_backup = dict(sess.get("customer_delivery_info") or {})

        try:
            # Step 1: store customer info (append — preserves multi-turn accumulation)
            delivery = sess.setdefault("customer_delivery_info", {})
            new_text = " | ".join(info_cmds)
            existing = delivery.get("raw", "")
            delivery["raw"] = f"{existing} | {new_text}" if existing else new_text

            # Step 2: process acceptance (inline section-0.5 logic, no re-check needed
            # because TI already confirmed intent=quote_accept for this turn)
            state_v2 = StateStore.load(sess)
            response = fq.generate_acceptance_response(open_quote, knowledge=knowledge)
            if "✓" in response:
                self._accept_quote_for_review(session_id, user_message, response)
                sess["quote_state"] = "accepted"
                sess.pop("pending_decision", None)
                sess.pop("pending_clarification_target", None)
                state_v2.transition("awaiting_customer_confirmation")
                state_v2.acceptance_pending = True
            else:
                # Quote has blocked items — cannot accept. Rollback info and fall through.
                sess["customer_delivery_info"] = customer_info_backup
                state_v2.transition("awaiting_clarification")
                self._persist_quote_state(
                    session_id,
                    response_text=response,
                    user_message=user_message,
                    event_type="quote_acceptance_blocked",
                    event_payload={"reason": "pending_lines"},
                )
                StateStore.save(sess, state_v2)
                return None

            StateStore.save(sess, state_v2)
            self._set_last_turn_meta(session_id, route_source="compound_mixed")
            logging.info(
                "compound_mixed_done session=%s info_stored=%r",
                session_id, delivery.get("raw"),
            )
            return response

        except Exception as exc:
            logging.warning(
                "compound_mixed_fallback session=%s reason=exception exc=%s",
                session_id, exc,
            )
            sess["customer_delivery_info"] = customer_info_backup
            return None

    def _chat_with_functions(self, session_id: str) -> str:
        """
        Send message to ChatGPT and handle function calls
        May require multiple iterations if functions are called
        """
        max_iterations = 5
        iteration = 0

        # R2: Accumulate all catalog prices the LLM sees this turn (Fuente A + Fuente B).
        # Fuente A: seeded from last_catalog_result (TurnInterpreter pre-LLM search).
        # Fuente B: extended below each time the LLM calls buscar_stock in the loop.
        from bot_sales.services.price_validator import (
            detect_hallucinated_prices,
            has_approximate_language,
        )
        _r2_sess = self.sessions.get(session_id, {})
        _r2_catalog = _r2_sess.get("last_catalog_result") or {}
        catalog_prices_seen: list = [
            int(c["price_ars"])
            for c in _r2_catalog.get("candidates", [])
            if c.get("price_ars") and int(c["price_ars"]) > 0
        ]

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

                # R2: Fuente B — accumulate prices from buscar_stock calls within the loop.
                if func_name == "buscar_stock":
                    for _p in func_result.get("products", []):
                        _pv = _p.get("price_ars")
                        if _pv and int(_pv) > 0:
                            catalog_prices_seen.append(int(_pv))

                # Add function result to context — slim the payload first to
                # prevent massive product lists from blowing the context window.
                slimmed_result = self._slim_function_result(func_name, func_result)

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
                    "content": str(slimmed_result)
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
            # R2: Validate LLM free-text response against catalog prices seen this turn.
            response_text = response.get("content", "...")
            _hallucinated = detect_hallucinated_prices(response_text, catalog_prices_seen)
            if _hallucinated:
                _is_approx = has_approximate_language(response_text)
                logging.warning(
                    "hallucinated_prices_detected session=%s prices=%s catalog_count=%d"
                    " is_approximation=%s preview=%.200s",
                    session_id, _hallucinated, len(catalog_prices_seen),
                    _is_approx, response_text,
                )
            return response_text

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
            logging.warning("sales_intelligence_failed_using_legacy_flow tenant=%s session=%s error=%s", self.tenant_id, session_id, exc, exc_info=True)
            return None

    # ── Context-size safety ───────────────────────────────────────────────────
    #
    # Functions like buscar_stock / buscar_por_categoria / buscar_alternativas
    # can return hundreds (or tens-of-thousands) of full product dicts when the
    # catalog is large.  Storing the raw result verbatim as a "function" message
    # causes context sizes of 700k+ tokens, which exceeds gpt-4o's 128k limit.
    #
    # _slim_function_result trims every product list down to at most MAX_PRODUCTS
    # items and keeps only the fields the LLM actually needs to compose a reply.
    # Non-product results are passed through unchanged (with a hard character cap
    # as a last-resort safety net).

    _PRODUCT_FIELDS = ("sku", "model", "category", "price_ars", "price_formatted", "available", "stock_qty")
    _MAX_PRODUCTS = 5          # top results per function call kept in context
    _MAX_RESULT_CHARS = 4_000  # hard cap on the serialised result string

    @staticmethod
    def _slim_product_list(products: list) -> list:
        """Return at most _MAX_PRODUCTS products with essential fields only."""
        slim = []
        for p in products[: SalesBot._MAX_PRODUCTS]:
            slim.append({k: p[k] for k in SalesBot._PRODUCT_FIELDS if k in p})
        return slim

    @staticmethod
    def _slim_function_result(func_name: str, result: Any) -> Any:
        """
        Trim function results that carry large product lists before they are
        serialised into the conversation context.

        Functions that return a 'products', 'alternatives', or 'recommendations'
        list have those lists truncated.  Everything else passes through, but is
        hard-capped at _MAX_RESULT_CHARS characters when serialised.
        """
        if not isinstance(result, dict):
            return result

        slimmed = dict(result)  # shallow copy — we'll replace the big lists

        for list_key in ("products", "alternatives", "recommendations"):
            if isinstance(slimmed.get(list_key), list):
                original_count = len(slimmed[list_key])
                slimmed[list_key] = SalesBot._slim_product_list(slimmed[list_key])
                if original_count > SalesBot._MAX_PRODUCTS:
                    slimmed["_truncated"] = (
                        f"{original_count - SalesBot._MAX_PRODUCTS} productos adicionales omitidos del contexto"
                    )

        # For obtener_cross_sell_offer the offer embeds a full product dict
        if isinstance(slimmed.get("offer"), dict) and isinstance(slimmed["offer"].get("product"), dict):
            full_product = slimmed["offer"]["product"]
            slimmed["offer"] = dict(slimmed["offer"])
            slimmed["offer"]["product"] = {k: full_product[k] for k in SalesBot._PRODUCT_FIELDS if k in full_product}

        # For obtener_upselling the upsell_product is a full product dict
        if isinstance(slimmed.get("upsell_product"), dict):
            full_product = slimmed["upsell_product"]
            slimmed["upsell_product"] = {k: full_product[k] for k in SalesBot._PRODUCT_FIELDS if k in full_product}

        # Hard-cap: if the result is still huge, truncate its string representation
        serialised = str(slimmed)
        if len(serialised) > SalesBot._MAX_RESULT_CHARS:
            logging.warning(
                "slim_function_result_still_large func=%s chars=%d — hard-truncating to %d",
                func_name,
                len(serialised),
                SalesBot._MAX_RESULT_CHARS,
            )
            slimmed = {"_raw_truncated": serialised[: SalesBot._MAX_RESULT_CHARS] + "…[truncado]"}

        return slimmed

    # ─────────────────────────────────────────────────────────────────────────

    def _execute_function(self, session_id: str, func_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a business logic function"""
        try:
            if func_name == "buscar_stock":
                from bot_sales.services.search_validator import (
                    validate_query_specs,
                    validate_search_match,
                )

                # Recover original user message from session context.
                # The LLM may silently drop impossible specs (e.g. "500kg",
                # "dorado") when extracting the "modelo" arg, so validators
                # must run on the raw user text, not on args.get("modelo").
                ctx = getattr(self, "contexts", {}).get(session_id, [])
                original_user_msg = next(
                    (
                        m["content"]
                        for m in reversed(ctx)
                        if m.get("role") == "user" and m.get("content")
                    ),
                    "",
                )

                # Level 1: detect impossible specs BEFORE searching the catalog.
                l1_valid, l1_reason = validate_query_specs(original_user_msg)
                if not l1_valid:
                    logging.info(
                        "search_validator.blocked_pre_search session=%s reason=%s",
                        session_id, l1_reason,
                    )
                    return {
                        "status": "no_match",
                        "products": [],
                        "message": "No encontré productos que coincidan con las especificaciones solicitadas.",
                        "_search_query": args.get("modelo", ""),
                        "_validator_reason": l1_reason,
                    }

                result = self.logic.buscar_stock(
                    modelo=args.get("modelo"),
                    storage_gb=args.get("storage_gb"),
                    color=args.get("color")
                )

                # Level 2: verify spec claims against returned products.
                if result.get("status") == "found":
                    l2_valid, l2_reason = validate_search_match(
                        original_user_msg, result.get("products", [])
                    )
                    if not l2_valid:
                        logging.info(
                            "search_validator.blocked_post_search session=%s reason=%s",
                            session_id, l2_reason,
                        )
                        result = {
                            "status": "no_match",
                            "products": [],
                            "message": "No encontré productos que coincidan con las especificaciones solicitadas.",
                        }

                # Pass original LLM query (pre-normalization) back so the prompt
                # can verify spec coincidence before presenting results.
                result["_search_query"] = args.get("modelo", "")
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

    def _summarize_context(self, messages_to_summarize: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Summarize old conversation messages into a compact system message.

        Makes a single LLM call to produce a 2-3 sentence Spanish summary of
        the oldest messages in a session.  Returns a system-role dict on success
        or None if the LLM call fails (caller falls back to simple truncation).
        """
        try:
            conversation_text = ""
            for msg in messages_to_summarize:
                role = msg.get("role", "unknown")
                content = str(msg.get("content") or "").strip()
                if content and role in ("user", "assistant"):
                    prefix = "Cliente" if role == "user" else "Asesor"
                    conversation_text += f"{prefix}: {content}\n"

            if not conversation_text.strip():
                return None

            summary_prompt = [
                {
                    "role": "system",
                    "content": (
                        "Resumí esta conversación en 2-3 oraciones en español. "
                        "Incluí: qué buscó el cliente, qué productos se mencionaron y en qué estado quedó la charla. "
                        "Sé breve y preciso. No agregues saludos ni conclusiones."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Conversación a resumir:\n{conversation_text}",
                },
            ]

            response = self.chatgpt.send_message(summary_prompt)
            summary_text = (response.get("content") or "").strip()

            if not summary_text:
                return None

            return {
                "role": "system",
                "content": f"Resumen de conversación anterior: {summary_text}",
            }

        except Exception as exc:
            logging.warning(
                "context_summarization_failed session_skipped error=%s", exc, exc_info=True
            )
            return None

    def _trim_context(self, session_id: str):
        """Trim conversation context to avoid token limits.

        When the context exceeds MAX_CONTEXT_MESSAGES, the oldest turns are
        summarized via a single LLM call and prepended as a system message so
        that long-running sessions retain meaningful context instead of losing
        it silently.
        """
        context = self.contexts[session_id]

        if len(context) <= MAX_CONTEXT_MESSAGES + 1:  # +1 for system message
            return

        # Keep system message + last N messages
        system_msg = context[0]
        recent_messages = context[-(MAX_CONTEXT_MESSAGES):]
        old_messages = context[1 : len(context) - MAX_CONTEXT_MESSAGES]

        # Attempt LLM summarization of the dropped messages
        summary_msg = self._summarize_context(old_messages)

        if summary_msg:
            self.contexts[session_id] = [system_msg, summary_msg] + recent_messages
            logging.info(
                "context_summarized session=%s tenant=%s old_msgs=%d",
                session_id,
                self.tenant_id,
                len(old_messages),
            )
        else:
            # Fallback: simple truncation
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

    def _get_state(self, session_id: str) -> ConversationStateV2:
        """Load ConversationStateV2 for a session, upgrading from legacy format if needed."""
        sess = self.sessions.setdefault(session_id, {})
        return StateStore.load(sess)

    def _save_state(self, session_id: str, state: ConversationStateV2) -> None:
        """Persist ConversationStateV2 back into the session dict, keeping legacy keys in sync."""
        sess = self.sessions.setdefault(session_id, {})
        StateStore.save(sess, state)

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
