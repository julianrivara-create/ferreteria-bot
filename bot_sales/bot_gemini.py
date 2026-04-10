#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main Bot Orchestrator - Gemini Version
Uses Google Gemini instead of OpenAI
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .core.database import Database
from .core.gemini import GeminiClient  # Changed from chatgpt
from .core.chatgpt import get_available_functions  # Reuse function definitions
from .core.business_logic import BusinessLogic
from .planning.flow_manager import SalesFlowManager
from .analytics import Analytics
from .config import (
    GEMINI_API_KEY,  # Changed from OPENAI_API_KEY
    GEMINI_MODEL,    # Changed from OPENAI_MODEL
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
    DB_FILE,
    CATALOG_CSV,
    LOG_PATH,
    POLICIES_FILE,
    MAX_CONTEXT_MESSAGES
)


class SalesBotGemini:
    """
    Main sales bot orchestrator - Gemini version
    Manages conversation flow and function calling with Gemini API
    """
    
    def __init__(
        self,
        db: Optional[Database] = None,
        api_key: str = None,
        model: str = None,
        tenant_id: str = "default_tenant",
        tenant_profile: Optional[Dict[str, Any]] = None,
    ):
        """Initialize bot components"""
        self.tenant_id = tenant_id
        self.tenant_profile = tenant_profile or {}

        # Initialize database
        if db:
            self.db = db
        else:
            self.db = Database(
                DB_FILE,
                CATALOG_CSV,
                LOG_PATH,
                api_key=os.getenv("OPENAI_API_KEY", ""),
            )
        
        # Initialize analytics
        self.analytics = Analytics(self.db)
        
        # Initialize business logic
        self.logic = BusinessLogic(self.db)
        
        profile_paths = self.tenant_profile.get("paths", {})
        self.policies_path = profile_paths.get("policies", POLICIES_FILE)
        if not Path(self.policies_path).is_absolute():
            self.policies_path = str(Path(__file__).resolve().parent.parent / self.policies_path)

        # Load policies
        self.policies = self._load_policies()
        
        # Config defaults
        if not api_key:
            api_key = GEMINI_API_KEY
        if not model:
            model = GEMINI_MODEL

        # Initialize Gemini client
        self.gemini = GeminiClient(
            api_key=api_key,
            model=model,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS
        )
        
        # Build system prompt (tenant-aware when profile is available)
        try:
            from .core.tenant_config import get_tenant_config

            tenant_config = (
                get_tenant_config(config_data=self.tenant_profile)
                if self.tenant_profile
                else get_tenant_config()
            )
            self.system_prompt = tenant_config.render_prompt(policies=self.policies)
        except Exception:
            self.system_prompt = GeminiClient.build_system_prompt(self.policies)
        
        # Get available functions
        self.functions = get_available_functions()
        
        # Conversation contexts (in-memory, keyed by session_id)
        self.contexts: Dict[str, List[Dict[str, str]]] = {}
        
        # Session state (for tracking hold_id, etc.)
        self.sessions: Dict[str, Dict[str, Any]] = {}

        try:
            self.flow_manager: Optional[SalesFlowManager] = SalesFlowManager()
            logging.info("sales_flow_manager_initialized_gemini tenant=%s", self.tenant_id)
        except Exception as exc:
            self.flow_manager = None
            logging.warning("sales_flow_manager_unavailable_gemini tenant=%s error=%s", self.tenant_id, exc)
        
        logging.info("SalesBotGemini initialized successfully (tenant=%s)", self.tenant_id)

    def _load_policies(self) -> str:
        """Load policies from markdown file"""
        if os.path.exists(self.policies_path):
            with open(self.policies_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logging.warning("Policies file not found: %s", self.policies_path)
            return "No hay políticas cargadas."

    def process_message(self, session_id: str, user_message: str) -> str:
        """
        Process a user message and return bot response
        
        Args:
            session_id: Unique identifier for conversation (phone, chat ID, etc.)
            user_message: User's message text
        
        Returns:
            Bot's response text
        """
        # Load from DB if not already in memory (survives restarts)
        if session_id not in self.contexts:
            persisted_ctx, persisted_state = self.db.load_session(session_id, self.tenant_id)
            if persisted_ctx:
                self.contexts[session_id] = persisted_ctx
                self.sessions[session_id] = persisted_state
            else:
                self.contexts[session_id] = [
                    {"role": "system", "content": self.system_prompt}
                ]
                self.sessions[session_id] = {}

        # Add user message to context
        self.contexts[session_id].append({
            "role": "user",
            "content": user_message
        })

        # Trim context if too long (keep system message + last N messages)
        self._trim_context(session_id)

        sales_contract = self._run_sales_intelligence(session_id, user_message)
        sales_meta = self._build_sales_intelligence_meta(sales_contract)
        self.sessions[session_id]["sales_intelligence_v1"] = sales_meta

        if sales_contract and (sales_contract.get("human_handoff") or {}).get("enabled"):
            try:
                self.logic.derivar_humano(
                    razon=str((sales_contract.get("human_handoff") or {}).get("reason") or "Handoff requerido"),
                    contacto=session_id,
                )
            except Exception as exc:
                logging.warning("sales_flow_handoff_failed_gemini session=%s error=%s", session_id, exc)

            response_text = str(sales_contract.get("reply_text") or "Te paso con un asesor para continuar.")
            self.contexts[session_id].append({"role": "assistant", "content": response_text})
            self.db.save_session(session_id, self.tenant_id, self.contexts[session_id], self.sessions[session_id])
            return response_text

        if sales_contract and sales_contract.get("missing_fields"):
            response_text = str(sales_contract.get("reply_text") or "")
            if response_text:
                self.contexts[session_id].append({"role": "assistant", "content": response_text})
                self.db.save_session(session_id, self.tenant_id, self.contexts[session_id], self.sessions[session_id])
                return response_text

        # Process with Gemini (with potential function calls)
        response_text = self._chat_with_functions(session_id)

        # Add assistant response to context
        self.contexts[session_id].append({
            "role": "assistant",
            "content": response_text
        })

        # Persist updated context and session state
        self.db.save_session(session_id, self.tenant_id, self.contexts[session_id], self.sessions[session_id])

        return response_text

    def _chat_with_functions(self, session_id: str) -> str:
        """
        Send message to Gemini and handle function calls
        May require multiple iterations if functions are called
        """
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Send to Gemini
            response = self.gemini.send_message(
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
            return response.get("content", "...")
        
        # Max iterations reached
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
            logging.warning(
                "sales_intelligence_failed_using_legacy_flow_gemini tenant=%s session=%s error=%s",
                self.tenant_id,
                session_id,
                exc,
            )
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
                result = self.logic.crear_reserva(
                    sku=args.get("sku"),
                    nombre=args.get("nombre"),
                    contacto=args.get("contacto")
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
                
                result = self.logic.confirmar_venta(
                    hold_id=hold_id,
                    zona=args.get("zona"),
                    metodo_pago=args.get("metodo_pago")
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
                return self.logic.obtener_cross_sell_offer(
                    producto_comprado_sku=args.get("producto_comprado_sku")
                )
            
            elif func_name == "derivar_humano":
                return self.logic.derivar_humano(
                    razon=args.get("razon"),
                    contacto=args.get("contacto"),
                    nombre=args.get("nombre")
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

    def reset_session(self, session_id: str):
        """Reset a conversation session (in-memory and persisted)."""
        self.contexts.pop(session_id, None)
        self.sessions.pop(session_id, None)
        self.db.delete_session(session_id, self.tenant_id)
        logging.info("Session %s reset (tenant=%s)", session_id, self.tenant_id)

    def close(self):
        """Cleanup resources"""
        self.db.close()
