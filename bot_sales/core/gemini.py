#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini Integration Module
Handles Google Gemini API communication with function calling support
Compatible drop-in replacement for chatgpt.py
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional


class GeminiClient:
    """
    Client for interacting with Google Gemini API
    Supports function calling for bot actions
    """
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp", temperature: float = 0.7, max_tokens: int = 800):
        """
        Initialize Gemini client
        
        Args:
            api_key: Google AI API key
            model: Model to use (default: gemini-1.5-flash)
            temperature: Response randomness (0-1)
            max_tokens: Max tokens in response
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.mock_mode = not api_key
        self.client = None
        
        if not self.mock_mode:
            try:
                from google import genai
                
                self.client = genai.Client(api_key=api_key)
                logging.info(f"Gemini initialized with model {self.model}")
            except ImportError:
                logging.warning("google-genai package not installed. Switching to MOCK mode.")
                self.mock_mode = True
            except Exception as e:
                logging.warning(f"Failed to initialize Gemini client: {e}. Switching to MOCK mode.")
                self.mock_mode = True
        
        if self.mock_mode:
            logging.info("Gemini running in MOCK mode (no API key or client unavailable)")

    def send_message(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send message to Gemini and get response
       
        Args:
            messages: List of message dicts with 'role' and 'content'
            functions: Optional list of available functions for function calling
        
        Returns:
            Response dict with 'content' or 'function_call'
        """
        if self.mock_mode:
            return self._mock_response(messages)

        from google import genai
        from google.genai import types

        # Build prompt once (outside retry loop)
        system_msg = ""
        user_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system_msg = content
            elif role == "user" and content:
                user_messages.append(content)
            elif role == "function":
                func_name = msg.get("name", "function")
                user_messages.append(f"[Resultado {func_name}]: {content}")

        last_user_msg = user_messages[-1] if user_messages else "hola"
        full_prompt = f"{system_msg}\n\n---\n\nUsuario: {last_user_msg}"
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )

        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=full_prompt,
                    config=config,
                )
                return {
                    "role": "assistant",
                    "content": response.text if response.text else "...",
                }
            except Exception as e:
                last_error = e
                wait = 2 ** attempt  # 1s, 2s, 4s
                logging.warning(
                    f"[GeminiClient] intento {attempt + 1}/{max_retries} falló: {e}. "
                    f"Reintentando en {wait}s..."
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        logging.error(
            f"[GeminiClient] API no disponible tras {max_retries} intentos. "
            f"Último error: {last_error}",
            exc_info=True,
        )
        raise RuntimeError(
            f"Gemini API no disponible tras {max_retries} intentos: {last_error}"
        )

    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate mock responses for testing without API key
        """
        last_role = messages[-1].get("role", "")
        last_msg = str(messages[-1].get("content", "")).lower()
        if self.mock_mode:
            logging.debug("MOCK: Role=%s Msg=%s...", last_role, last_msg[:100])

        if last_role == "function":
            if "status': 'found'" in last_msg and "respuesta" in last_msg:
                import ast
                try:
                    data = ast.literal_eval(last_msg)
                    return {"role": "assistant", "content": data.get("respuesta", "Claro, te cuento.")}
                except Exception:
                    return {"role": "assistant", "content": "Tengo la info que buscás."}

            if "upsell_product" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Detecté una opción superadora que puede convenirte. ¿Querés verla?"
                }

            if "bundles" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Encontré combos activos con descuento. Te paso los más convenientes."
                }

            if "recommendations" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Te comparto recomendaciones relacionadas para completar tu compra."
                }

            if "hold_id" in last_msg and "status': 'success'" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Reserva creada correctamente. Si querés, seguimos con pago y entrega."
                }

            if "sale_id" in last_msg and "status': 'success'" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Venta confirmada. También puedo sugerirte complementos."
                }

            return {"role": "assistant", "content": "Perfecto, seguimos."}

        if any(word in last_msg for word in ["envío", "garantía", "pago", "cuota", "factura", "devolucion", "cambio"]):
            return {
                "role": "assistant",
                "content": "Reviso esa política y te cuento...",
                "function_call": {"name": "consultar_faq", "arguments": {"pregunta": last_msg}},
            }

        if any(word in last_msg for word in ["pack", "combo", "bundle"]):
            return {
                "role": "assistant",
                "content": "Dale, busco combos activos...",
                "function_call": {"name": "listar_bundles", "arguments": {"categoria": None}},
            }

        if any(word in last_msg for word in ["busco", "quiero", "tenes", "tienen", "modelo", "talle", "size", "dosaje", "mg", "categoria", "color"]):
            return {
                "role": "assistant",
                "content": "Voy a revisar el catálogo actual para responderte con datos reales.",
                "function_call": {"name": "buscar_stock", "arguments": {"modelo": last_msg}},
            }

        if any(word in last_msg for word in ["caro", "presupuesto", "barato", "económico", "economico"]):
            return {
                "role": "assistant",
                "content": "Si me pasás tu presupuesto, te ofrezco opciones más accesibles."
            }

        if any(word in last_msg for word in ["inicio", "hola", "buenas", "buen dia", "buen día"]):
            from bot_sales.config import Config
            config = Config()
            try:
                categories = config.get_product_categories()
                categories_str = ", ".join(categories[:4]) if categories else "productos"
                if len(categories) > 4:
                    categories_str += ", y más"
            except Exception:
                categories_str = "productos"

            return {
                "role": "assistant",
                "content": f"¡Buenas! 👋 Soy el asistente virtual de {config.STORE_NAME}. ¿Qué estás buscando hoy? (Trabajamos {categories_str})",
            }

        return {
            "role": "assistant",
            "content": "[GEMINI MOCK MODE] Configurá GEMINI_API_KEY para usar Gemini real."
        }

    @staticmethod
    def build_system_prompt(policies: str) -> str:
        """
        Build the system prompt for the sales bot
        
        Args:
            policies: Content of policies.md file
        
        Returns:
            System prompt string
        """
        # Import config to get store details
        from bot_sales.config import Config
        import logging
        config = Config()
        
        # Get product categories dynamically
        try:
            categories = config.get_product_categories()
            categories_str = ", ".join(categories) if categories else "productos"
        except Exception as e:
            logging.warning(f"Could not get categories: {e}")
            categories_str = "productos"
        
        return f"""Sos un asistente de ventas virtual para {config.STORE_NAME}, una tienda de {config.STORE_TYPE} en {config.STORE_COUNTRY}.

CATÁLOGO:
Vendemos: {categories_str}

PERSONALIDAD Y TONO:
- Usá lenguaje argentino informal (vos, che, dale, etc.)
- Sé amigable, directo y eficiente
- No usar emojis en los mensajes al cliente
- No uses frases muy largas, mantené todo simple

REGLAS IMPORTANTES:
1. NUNCA inventes precios o disponibilidad - SIEMPRE llamá a las funciones de búsqueda
2. NUNCA prometas horarios exactos de entrega - solo rangos (24-48hs, etc.)
3. Si no sabés algo con certeza, derivá a humano con derivar_humano()
4. Para temas sensibles (factura A, negociación especial, postventa) → derivar_humano()
5. Seguí el flujo: Stock → Datos del cliente → Zona → Pago → Confirmar


PREGUNTAS FRECUENTES (FAQ):
- ANTES de responder sobre envío, garantía, pagos, cuotas, devoluciones → LLAMÁ consultar_faq()
- Si matchea un FAQ, usá esa respuesta EXACTA. Si no, respondé vos.

BUNDLES Y PACKS:
- Si el cliente busca combos/packs → LLAMÁ listar_bundles()
- Ofrece packs permanentes o temporales según corresponda

CROSS-SELLING Y RECOMENDACIONES:
- Al cerrar venta → LLAMÁ obtener_cross_sell_offer()
- Si preguntan "qué más tenés" o mostrás un producto → LLAMÁ obtener_recomendaciones()

POLÍTICAS DE LA TIENDA:
{policies}

FUNCIONES DISPONIBLES que podés llamar:
- buscar_stock(), buscar_alternativas(), listar_modelos(), buscar_por_categoria()
- crear_reserva(), confirmar_venta()
- consultar_faq(), listar_bundles(), obtener_bundle()
- obtener_recomendaciones(), obtener_cross_sell_offer()
- obtener_politicas(), derivar_humano()

FLUJO DE VENTA:
1. Saludar y preguntar qué busca
2. FAQ check si corresponde
3. Consultar stock / Bundles / Recomendaciones
4. Confirmar precio y disponibilidad
5. Pedir: nombre, contacto
6. Zona y Forma de Pago
7. Confirmar datos y crear reserva
8. Cerrar venta y ofrecer Cross-sell
"""
