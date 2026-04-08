#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini Integration Module
Handles Google Gemini API communication with function calling support
Compatible drop-in replacement for chatgpt.py
"""

import json
import logging
from typing import List, Dict, Any, Optional

from .fallback import get_fallback_service



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
        
        try:
            from google import genai
            from google.genai import types
            
            # Build conversation from messages
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
                    # Include function results
                    func_name = msg.get("name", "function")
                    user_messages.append(f"[Resultado {func_name}]: {content}")
            
            # Get last user message
            last_user_msg = user_messages[-1] if user_messages else "hola"
            
            # Prepare prompt with system instructions prepended
            full_prompt = f"{system_msg}\n\n---\n\nUsuario: {last_user_msg}"
            
            # For now, don't use tools - just natural conversation
            # Gemini will respond naturally and we'll parse for function calls manually
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens
            )
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=config
            )
            
            # Parse response
            result = {
                "role": "assistant",
                "content": response.text if response.text else "..."
            }
            
            return result
            
        except Exception as e:
            logging.error(f"Gemini API error: {e}")
            
            # Use Fallback Service
            last_user_msg = user_messages[-1] if user_messages else ""
            fallback_response = get_fallback_service().get_response(last_user_msg)
            
            return {
                "role": "assistant",
                "content": f"{fallback_response}\n\n(⚠️ Modo Respaldo activado por error de conexión)",
                "error": str(e)
            }

    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate mock responses for testing without API key
        """
        last_role = messages[-1].get("role", "")
        last_msg = str(messages[-1].get("content", "")).lower()
        if self.mock_mode:
            print(f"DEBUG MOCK: Role={last_role} Msg={last_msg[:100]}...")
        
        if last_role == "function":
            # === SPECIFIC BUNDLE DETAILS (Must come FIRST) ===
            if "kit_taladrado" in last_msg.lower():
                return {"role": "assistant", "content": "🔧 ¡El Kit Taladrado trae mechas acero + tarugos nylon para todo tipo de pared. Ahorrás 10% comprándolo junto. ¿Te lo reservo?"}

            if "kit_pintura" in last_msg.lower():
                return {"role": "assistant", "content": "🖌️ ¡El Kit Pintura Interior trae látex + rodillo + bandeja + lija. Todo para pintar sin vueltas. 8% OFF. ¿Te interesa?"}

             # === GENERIC ANSWERS ===
            if "status': 'found'" in last_msg and "respuesta" in last_msg:
                # FAQ response
                import ast
                try:
                    data = ast.literal_eval(last_msg)
                    return {
                        "role": "assistant",
                        "content": data.get("respuesta", "Claro, te cuento.")
                    }
                except:
                    return {"role": "assistant", "content": "Tengo la info que buscás."}

            if "bundles" in last_msg:
                return {
                    "role": "assistant",
                    "content": "¡Sí! Tenemos kits con descuento. ¿Buscás algo para taladrar, pintar o armar? 🔧"
                }
            if "recommendations" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Basado en lo que buscás, te recomiendo complementar con los tarugos Fischer o una mecha acero rápido. ¿Querés que te busque opciones?"
                }
            if "success" in last_msg and "hold_id" in last_msg:
                return {
                    "role": "assistant",
                    "content": "¡Perfecto! Ya te reservé el producto por 30 minutos. ¿Cómo preferís abonar? Transferencia o Efectivo?"
                }
                
            return {
                "role": "assistant",
                "content": "¡Bárbaro! Confirmado."
            }

        # Fallback to general FAQ service for unmatched mock queries
        fallback_resp = get_fallback_service().get_response(last_msg)
        if fallback_resp and fallback_resp != get_fallback_service().faq_data.get("default_response"):
             return {
                "role": "assistant",
                "content": fallback_resp
            }

        # Simple rule-based mocking for User messages
        # FAQ Mock
        if any(word in last_msg for word in ["envío", "garantía", "pago", "cuota", "factura"]):
            return {
                "role": "assistant",
                "content": "Dejame chequear esa info...",
                "function_call": {
                    "name": "consultar_faq",
                    "arguments": {"pregunta": last_msg}
                }
            }
        
        # Bundles Mock
        if any(word in last_msg for word in ["pack", "combo", "bundle", "kit"]):
            return {
                "role": "assistant",
                "content": "¡Claro! Tenemos kits con descuento. Te muestro...",
                "function_call": {
                    "name": "listar_bundles",
                    "arguments": {"categoria": None}
                }
            }
            
        # === DEMO SCENARIO SPECIFIC MOCKS (For demo_final.py) ===
        
        # Scenario 1: FAQ & Recommendations
        if "envío" in last_msg:
            return {"role": "assistant", "content": "📦 Opciones de envío:\n• CABA: Gratis en moto (24-48hs)\n• AMBA: Consultar costo (48-72hs)\n• Interior: Por Correo/Andreani (3-5 días)\n• Entrega coordinada según zona"}
            
        if "garantía" in last_msg:
            return {"role": "assistant", "content": "✅ Garantía Oficial:\nCada producto cuenta con garantía oficial del fabricante según modelo y cobertura vigente."}

        # Scenario 2: Bundles & Sales
        if "pagar en cuotas" in last_msg or "pago con mercadopago" in last_msg:
            return {"role": "assistant", "content": "💳 Pagos:\n• Efectivo/Transferencia: sin recargo\n• Débito: sin recargo\n• MercadoPago: consultá recargo vigente\n\n¿Cómo preferís abonar?"}

        if "caro" in last_msg:
            return {"role": "assistant", "content": "Entiendo. 🤔 Puedo mostrarte alternativas de otras marcas en el mismo rango. ¿Te interesa?"}

        if "pensarlo" in last_msg:
            return {"role": "assistant", "content": "¡Dale, tranqui! 🐢 Si te decidís avisame. ¡Saludos!"}

        # Initialize default
        if "inicio" in last_msg or "hola" in last_msg:
            return {
                "role": "assistant",
                "content": "¡Buenas! 👋 Soy el asistente de la ferretería. ¿En qué te puedo ayudar hoy?"
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
        return f"""Sos un asistente de ventas virtual para una ferretería en Argentina.

CATÁLOGO:
Vendemos: herramientas manuales, herramientas eléctricas, bulonería, tarugos, pinturas, sanitaria y accesorios.
Marcas: Knipex, Bondhus, Dewalt, Stanley, BREMEN, Fischer, Makita, Bosch y más.

PERSONALIDAD Y TONO:
- Usá lenguaje argentino informal (vos, che, dale, etc.)
- Sé amigable, directo y eficiente
- Usá emojis ocasionalmente (🔧 🔩 💳 ✅)
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
