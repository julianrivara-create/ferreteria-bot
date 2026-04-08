#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main Bot Orchestrator
Coordinates ChatGPT, Business Logic, and Database
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional

try:
    import redis as _redis_mod
except ImportError:
    _redis_mod = None

from .core.database import Database
from .core.chatgpt import ChatGPTClient, get_available_functions
from .core.business_logic import BusinessLogic
from .analytics import Analytics
from .config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
    POLICIES_FILE,
    MAX_CONTEXT_MESSAGES,
    ENABLE_DEBUG_COMMANDS,
)
from Planning.flow_manager import SalesFlowManager


class _RedisSessionStore:
    """Persist conversation contexts & session state in Redis.
    Falls back to plain dicts if Redis is unavailable.
    """
    _SESSION_TTL = 86400  # 24 hours

    def __init__(self):
        self._r = None
        self._mem_ctx: Dict[str, List[Dict[str, str]]] = {}
        self._mem_sess: Dict[str, Dict[str, Any]] = {}
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url and _redis_mod:
            try:
                self._r = _redis_mod.from_url(redis_url, decode_responses=True)
                self._r.ping()
                logging.info("redis_session_store_initialized")
            except Exception as exc:
                logging.warning("redis_unavailable_using_memory_fallback error=%s", exc)
                self._r = None
        else:
            logging.info("redis_unavailable_using_memory_fallback")

    def _disable_redis_runtime(self, exc: Exception):
        """Switch to in-memory storage if Redis fails after startup."""
        if self._r is not None:
            logging.warning("redis_runtime_error_switching_to_memory error=%s", exc)
        self._r = None

    # -- contexts ---------------------------------------------------------
    def get_context(self, sid: str) -> List[Dict[str, str]]:
        if self._r:
            try:
                raw = self._r.get(f"ctx:{sid}")
                if raw:
                    return json.loads(raw)
                return []
            except Exception as exc:
                self._disable_redis_runtime(exc)
        return self._mem_ctx.get(sid, [])

    def set_context(self, sid: str, ctx: List[Dict[str, str]]):
        if self._r:
            try:
                self._r.set(f"ctx:{sid}", json.dumps(ctx, ensure_ascii=False), ex=self._SESSION_TTL)
                return
            except Exception as exc:
                self._disable_redis_runtime(exc)
        self._mem_ctx[sid] = ctx

    def has_context(self, sid: str) -> bool:
        if self._r:
            try:
                return self._r.exists(f"ctx:{sid}") > 0
            except Exception as exc:
                self._disable_redis_runtime(exc)
        return sid in self._mem_ctx

    def del_context(self, sid: str):
        if self._r:
            try:
                self._r.delete(f"ctx:{sid}")
                return
            except Exception as exc:
                self._disable_redis_runtime(exc)
        self._mem_ctx.pop(sid, None)

    # -- sessions ---------------------------------------------------------
    def get_session(self, sid: str) -> Dict[str, Any]:
        if self._r:
            try:
                raw = self._r.get(f"sess:{sid}")
                if raw:
                    return json.loads(raw)
                return {}
            except Exception as exc:
                self._disable_redis_runtime(exc)
        return self._mem_sess.get(sid, {})

    def set_session(self, sid: str, data: Dict[str, Any]):
        if self._r:
            try:
                self._r.set(f"sess:{sid}", json.dumps(data, ensure_ascii=False, default=str), ex=self._SESSION_TTL)
                return
            except Exception as exc:
                self._disable_redis_runtime(exc)
        self._mem_sess[sid] = data

    def del_session(self, sid: str):
        if self._r:
            try:
                self._r.delete(f"sess:{sid}")
                return
            except Exception as exc:
                self._disable_redis_runtime(exc)
        self._mem_sess.pop(sid, None)


class SalesBot:
    """
    Main sales bot orchestrator
    Manages conversation flow and function calling
    """
    
    def __init__(self):
        """Initialize bot components"""
        # Initialize database (Postgres adapter, no arguments needed)
        self.db = Database()
        
        # Initialize analytics
        self.analytics = Analytics(self.db)
        
        # Initialize business logic
        self.logic = BusinessLogic(self.db)
        
        # Load policies
        self.policies = self._load_policies()
        
        # Initialize ChatGPT client
        self.chatgpt = ChatGPTClient(
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS
        )
        
        # Build system prompt
        self.system_prompt = ChatGPTClient.build_system_prompt(self.policies)
        if ENABLE_DEBUG_COMMANDS:
            logging.debug("System Prompt Loaded (%s chars)", len(self.system_prompt))
            logging.debug("System Prompt Preview: %s", self.system_prompt[:200])
            if "ASISTENTE" in self.system_prompt:
                logging.debug("Loaded GENERIC prompt")
            if "VENDEDOR" in self.system_prompt:
                logging.debug("Loaded VENDEDOR prompt")
        
        # Get available functions
        self.functions = get_available_functions()
        
        # Persistent session store (Redis if available, else in-memory)
        self._store = _RedisSessionStore()

        try:
            self.flow_manager = SalesFlowManager()
            logging.info("sales_flow_manager_initialized")
        except Exception as exc:
            self.flow_manager = None
            logging.warning("sales_flow_manager_unavailable error=%s", exc)
        
        # Backward-compat: property-like dicts replaced by _store methods
        # Legacy references in this file now use self._store.*
        
        logging.info("SalesBot initialized successfully")

    def _load_policies(self) -> str:
        """Load policies from markdown file"""
        if os.path.exists(POLICIES_FILE):
            with open(POLICIES_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logging.warning(f"Policies file not found: {POLICIES_FILE}")
            return "No hay políticas cargadas."

    def process_message(self, session_id: str, user_message: str) -> str:
        result = self.process_message_with_meta(session_id, user_message)
        return result.get("content", "...")

    def process_message_with_meta(self, session_id: str, user_message: str) -> Dict[str, Any]:
        """
        Process a user message and return bot response
        
        Args:
            session_id: Unique identifier for conversation (phone, chat ID, etc.)
            user_message: User's message text
        
        Returns:
            {"content": "...", "meta": {...} | None}
        """
        # Initialize context if new session
        if not self._store.has_context(session_id):
            self._store.set_context(session_id, [
                {"role": "system", "content": self.system_prompt}
            ])
            self._store.set_session(session_id, {})
            # Track new session
            self.analytics.start_session(session_id)
        
        # Add user message to context
        ctx = self._store.get_context(session_id)
        ctx.append({
            "role": "user",
            "content": user_message
        })
        self._store.set_context(session_id, ctx)
        
        # Track message
        self.analytics.track_message(session_id)
        
        # Trim context if too long (keep system message + last N messages)
        self._trim_context(session_id)
        
        # DEBUG COMMANDS: disabled by default and only for controlled environments.
        if ENABLE_DEBUG_COMMANDS and user_message.strip() == "/debug":
            response = (
                f"🤖 BOT DIAGNOSTICS:\n"
                f"• Initialized: Yes\n"
                f"• Mock Mode: {self.chatgpt.mock_mode}\n"
                f"• API Key Set: {'Yes' if self.chatgpt.api_key and len(self.chatgpt.api_key) > 10 else 'No'}\n"
                f"• Key Prefix: {self.chatgpt.api_key[:7] if self.chatgpt.api_key else 'None'}\n"
                f"• Model: {self.chatgpt.model}\n"
                f"• DB Connection: {'OK' if self.db.session else 'Error'}\n"
                f"• Policies Loaded: {len(self.policies) > 50}\n"
                f"• Init Error: {getattr(self.chatgpt, 'init_error', 'None')}\n"
                f"• System Prompt: {len(self.system_prompt)} chars\n"
                f"• Versions: OpenAI={getattr(self.chatgpt, 'openai_version', '?')} | HTTPX={getattr(self.chatgpt, 'httpx_version', '?')}"
            )
            return {"content": response, "meta": None}

        if ENABLE_DEBUG_COMMANDS and user_message.strip() == "/debug_stock":
             try:
                 # Test Business Logic directly
                 result = self.logic.buscar_stock("taladro")
                 db_info = "Connected" if self.db.session else "Disconnected"
                 return {
                     "content": f"🔍 Stock Debug:\nDB: {db_info}\nResult: {str(result)}\nOne Product: {str(result.get('products', ['None'])[0]) if result.get('products') else 'None'}",
                     "meta": None,
                 }
             except Exception as e:
                 import traceback
                 return {"content": f"❌ Stock Error:\n{str(e)}\n{traceback.format_exc()}", "meta": None}

        sales_contract = self._run_sales_intelligence(session_id, user_message)
        sales_meta = self._build_sales_intelligence_meta(sales_contract)
        if sales_contract and sales_contract.get("human_handoff", {}).get("enabled"):
            try:
                summary = self._generate_handoff_summary(session_id)
                self.logic.derivar_humano(
                    razon=str(sales_contract.get("human_handoff", {}).get("reason") or "Handoff requerido"),
                    contacto=session_id,
                    resumen=summary,
                )
            except Exception as exc:
                logging.warning("sales_handoff_autocreate_failed error=%s", exc)

            response = str(sales_contract.get("reply_text") or "Te paso con un asesor para continuar.")
            ctx = self._store.get_context(session_id)
            ctx.append({"role": "assistant", "content": response})
            self._store.set_context(session_id, ctx)
            sess = self._store.get_session(session_id)
            sess["sales_intelligence_v1"] = sales_meta
            self._store.set_session(session_id, sess)
            return {"content": response, "meta": sales_meta}
        
        # Check for LITE MODE (Basic Bot)
        from .config import LITE_MODE
        if LITE_MODE:
            # 1. Check FAQ
            faq_result = self.logic.consultar_faq(user_message)
            if faq_result["status"] == "found":
                response = faq_result["respuesta"]
            
            # 2. Check for menu/stock keywords (Simple Logic)
            elif "stock" in user_message.lower() or "precio" in user_message.lower():
                # Simple lookup — list available products
                models = self.logic.listar_modelos()
                response = "Tenemos stock disponible: " + ", ".join([m['model'] for m in models['models'][:5]]) + "..."
            
            # 3. Default: Handoff
            else:
                response = "Entiendo. En este momento no tengo esa información, te paso con un asesor humano ya mismo. 👤"
                # Log handoff
                self.logic.derivar_humano("Consulta no resuelta en Lite Mode", contacto=session_id)
                
            # Add assistant response to context
            ctx = self._store.get_context(session_id)
            ctx.append({
                "role": "assistant",
                "content": response
            })
            self._store.set_context(session_id, ctx)
            sess = self._store.get_session(session_id)
            sess["sales_intelligence_v1"] = sales_meta
            self._store.set_session(session_id, sess)
            return {"content": response, "meta": sales_meta}

        if sales_contract and sales_contract.get("missing_fields"):
            response_text = str(sales_contract.get("reply_text") or "")
            if response_text:
                ctx = self._store.get_context(session_id)
                ctx.append({"role": "assistant", "content": response_text})
                self._store.set_context(session_id, ctx)
                sess = self._store.get_session(session_id)
                sess["sales_intelligence_v1"] = sales_meta
                self._store.set_session(session_id, sess)
                return {"content": response_text, "meta": sales_meta}

        # Process with ChatGPT (with potential function calls)
        response_text = self._chat_with_functions(session_id)
        
        # Add assistant response to context
        ctx = self._store.get_context(session_id)
        ctx.append({
            "role": "assistant",
            "content": response_text
        })
        self._store.set_context(session_id, ctx)

        sess = self._store.get_session(session_id)
        sess["sales_intelligence_v1"] = sales_meta
        self._store.set_session(session_id, sess)

        return {"content": response_text, "meta": sales_meta}

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
            "cta_type": (contract.get("cta") or {}).get("type") if isinstance(contract.get("cta"), dict) else None,
            "needs_handoff": bool((contract.get("human_handoff") or {}).get("enabled")),
        }

    def _run_sales_intelligence(self, session_id: str, user_message: str) -> Optional[Dict[str, Any]]:
        if self.flow_manager is None:
            return None
        try:
            return self.flow_manager.process_input(session_id, user_message)
        except Exception as exc:
            logging.warning("sales_intelligence_failed_using_legacy_flow error=%s", exc)
            return None

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
                messages=self._store.get_context(session_id),
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
                ctx = self._store.get_context(session_id)
                ctx.append({
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": func_name,
                        "arguments": str(func_args)
                    }
                })
                
                ctx.append({
                    "role": "function",
                    "name": func_name,
                    "content": str(func_result)
                })
                self._store.set_context(session_id, ctx)
                
                # Continue loop to get final response
                continue
            
            # No function call, return response
            return response.get("content", "...")
        
        # Max iterations reached
        return "Perdón, tuve un problema procesando tu solicitud. ¿Empezamos de nuevo?"

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
                if result.get("status") == "success" and result.get("productos"):
                    for prod in result["productos"]:
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
                result = self.logic.crear_reserva(
                    sku=args.get("sku"),
                    nombre=args.get("nombre"),
                    contacto=args.get("contacto"),
                    email=args.get("email")
                )
                # Store hold_id in session
                if result["status"] == "success":
                    sess = self._store.get_session(session_id)
                    sess["hold_id"] = result["hold_id"]
                    self._store.set_session(session_id, sess)
                return result
            
            elif func_name == "confirmar_venta":
                # Use hold_id from session if not provided
                hold_id = args.get("hold_id") or self._store.get_session(session_id).get("hold_id")
                if not hold_id:
                    return {"status": "error", "message": "No hay reserva activa"}
                
                result = self.logic.confirmar_venta(
                    hold_id=hold_id,
                    zona=args.get("zona"),
                    metodo_pago=args.get("metodo_pago")
                )
                
                # Track sale if successful
                if result["status"] == "success" and "product_sku" in result:
                    product = self.db.get_product_by_sku(result["product_sku"])
                    if product:
                        self.analytics.track_sale(
                            session_id,
                            result["product_sku"],
                            product["price_ars"],
                            product.get("category", "Unknown")
                        )
                
                # Clear session state after sale
                if result["status"] == "success":
                    self._store.set_session(session_id, {})
                
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
                    sess = self._store.get_session(session_id)
                    sess["cross_sell_offered"] = offer["sku"]
                    self._store.set_session(session_id, sess)
                
                return result
            
            elif func_name == "derivar_humano":
                # SMART HANDOFF: Generate summary
                summary = self._generate_handoff_summary(session_id)
                logging.info(f"Handoff Summary generated: {summary}")
                
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
        context = self._store.get_context(session_id)
        
        if len(context) <= MAX_CONTEXT_MESSAGES + 1:  # +1 for system message
            return
        
        # Keep system message + last N messages
        system_msg = context[0]
        recent_messages = context[-(MAX_CONTEXT_MESSAGES):]
        self._store.set_context(session_id, [system_msg] + recent_messages)

    def _generate_handoff_summary(self, session_id: str) -> str:
        """Generate a brief summary of the conversation for the human agent"""
        try:
            # Grab recent context (system prompt not needed for summary context)
            recent_msgs = self._store.get_context(session_id)
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

    def reset_session(self, session_id: str):
        """Reset a conversation session"""
        self._store.del_context(session_id)
        self._store.del_session(session_id)
        logging.info(f"Session {session_id} reset")

    def close(self):
        """Cleanup resources"""
        self.db.close()
