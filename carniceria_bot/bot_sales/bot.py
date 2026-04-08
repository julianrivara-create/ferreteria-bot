#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main Bot Orchestrator
Coordinates ChatGPT, Business Logic, and Database
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .core.database import Database
from .core.chatgpt import ChatGPTClient, get_available_functions
from .core.business_logic import BusinessLogic
from .analytics import Analytics
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
    ):
        """Initialize bot components"""
        self.tenant_id = tenant_id
        self.tenant_profile = tenant_profile or {}

        # Initialize database
        if db:
            self.db = db
        else:
            self.db = Database(DB_FILE, CATALOG_CSV, LOG_PATH)
        
        # Initialize analytics
        self.analytics = Analytics(self.db)
        
        # Initialize business logic
        self.logic = BusinessLogic(self.db)
        
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
        
        logging.info("SalesBot initialized successfully (tenant=%s)", self.tenant_id)

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
        # Initialize context if new session
        if session_id not in self.contexts:
            self.contexts[session_id] = [
                {"role": "system", "content": self.system_prompt}
            ]
            self.sessions[session_id] = {}
            # Track new session
            self.analytics.start_session(session_id)
        
        # Add user message to context
        self.contexts[session_id].append({
            "role": "user",
            "content": user_message
        })
        
        # Track message
        self.analytics.track_message(session_id)
        
        # Trim context if too long (keep system message + last N messages)
        self._trim_context(session_id)
        
        # Check for LITE MODE (Basic Bot)
        from .config import LITE_MODE
        if LITE_MODE:
            # 1. Check FAQ
            faq_result = self.logic.consultar_faq(user_message)
            if faq_result["status"] == "found":
                response = faq_result["respuesta"]
            
            # 2. Check for menu/stock keywords (Simple Logic)
            elif "stock" in user_message.lower() or "precio" in user_message.lower():
                # Simple lookup for iPhone 15 as example or generic msg
                # For basic bot, we might just list available models
                models = self.logic.listar_modelos()
                response = "Tenemos stock disponible: " + ", ".join([m['model'] for m in models['models'][:5]]) + "..."
            
            # 3. Default: Handoff
            else:
                response = "Entiendo. En este momento no tengo esa información, te paso con un asesor humano ya mismo. 👤"
                # Log handoff
                self.logic.derivar_humano("Consulta no resuelta en Lite Mode", contacto=session_id)
                
            # Add assistant response to context
            self.contexts[session_id].append({
                "role": "assistant",
                "content": response
            })
            return response

        # Process with ChatGPT (with potential function calls)
        response_text = self._chat_with_functions(session_id)
        
        # Add assistant response to context
        self.contexts[session_id].append({
            "role": "assistant",
            "content": response_text
        })
        
        return response_text

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

    def reset_session(self, session_id: str):
        """Reset a conversation session"""
        if session_id in self.contexts:
            del self.contexts[session_id]
        if session_id in self.sessions:
            del self.sessions[session_id]
        logging.info(f"Session {session_id} reset")

    def close(self):
        """Cleanup resources"""
        self.db.close()
