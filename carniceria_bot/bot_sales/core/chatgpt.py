#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ChatGPT Integration Module
Handles OpenAI API communication with function calling support
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from .objections import ObjectionHandler


class ChatGPTClient:
    """
    Client for interacting with OpenAI's ChatGPT API
    Supports function calling for bot actions
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4", temperature: float = 0.7, max_tokens: int = 800):
        """
        Initialize ChatGPT client
        
        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4)
            temperature: Response randomness (0-1)
            max_tokens: Max tokens in response
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tokens = max_tokens
        # Enable mock mode if no API key or placeholder
        self.mock_mode = not api_key or "PLACEHOLDER" in api_key or "sk-" not in api_key
        self.client = None
        
        if not self.mock_mode:
            try:
                import openai
                self.client = openai.OpenAI(api_key=api_key)
                logging.info(f"ChatGPT initialized with model {self.model}")
            except ImportError:
                logging.warning("openai package not installed. Switching to MOCK mode.")
                self.mock_mode = True
            except Exception as e:
                logging.warning(f"Failed to initialize OpenAI client: {e}. Switching to MOCK mode.")
                self.mock_mode = True
        
        if self.mock_mode:
            logging.info("ChatGPT running in MOCK mode (no API key or client unavailable)")

    def send_message(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send message to ChatGPT and get response with retry logic
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            functions: Optional list of available functions for function calling
        
        Returns:
            Response dict with 'content' or 'function_call'
        """
        # MOCK MODE: Only for testing without API key
        if self.mock_mode:
            logging.info("MOCK MODE: Using simplified fallback response")
            return self._mock_response(messages)
        
        # Retry configuration
        max_retries = 3
        retry_delay = 1  # seconds
        
        last_error = None
        for attempt in range(max_retries):
            try:
                import time
                start_time = time.time()
                
                # Prepare API call
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "timeout": 30  # 30 second timeout
                }
                
                if functions:
                    kwargs["tools"] = [
                        {"type": "function", "function": func}
                        for func in functions
                    ]
                    kwargs["tool_choice"] = "auto"
                
                # Call OpenAI API
                response = self.client.chat.completions.create(**kwargs)
                
                # Track cost and performance
                elapsed = time.time() - start_time
                tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else 0
                logging.info(f"OpenAI API call successful: {tokens_used} tokens, {elapsed:.2f}s")
                
                # Parse response
                message = response.choices[0].message
                
                result = {
                    "role": "assistant",
                    "content": message.content or ""
                }
                
                # Check for function call
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    tool_call = message.tool_calls[0]
                    result["function_call"] = {
                        "name": tool_call.function.name,
                        "arguments": json.loads(tool_call.function.arguments),
                        "id": tool_call.id
                    }
                
                return result
                
            except Exception as e:
                last_error = e
                logging.warning(f"ChatGPT API attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    import time
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
        
        # All retries failed - fallback to mock or error
        logging.error(f"ChatGPT API failed after {max_retries} attempts. Last error: {last_error}")
        
        try:
            logging.info("Falling back to MOCK response due to API failure")
            return self._mock_response(messages)
        except Exception as mock_e:
            logging.error(f"Mock fallback also failed: {mock_e}")
            return {
                "role": "assistant",
                "content": "🔧 Disculpá, estoy teniendo problemas técnicos. Por favor intentá de nuevo en unos minutos o contactá a un vendedor humano. ¡Gracias por tu paciencia!",
                "error": str(last_error)
            }

    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate mock responses for testing without API key
        """
        last_role = messages[-1].get("role", "")
        last_msg = str(messages[-1].get("content", "")).lower()
        if self.mock_mode:
            print(f"DEBUG MOCK: Role={last_role} Msg={last_msg[:100]}...")
            import sys
            sys.stdout.flush()
        
        if last_role == "function":
            # Upselling Function Result
            if "upsell_product" in last_msg:
                 return {
                     "role": "assistant",
                     "content": "¡Buena elección! Pero ojo... 👀\n\nPor una diferencia muy chica podés saltar al siguiente nivel. 🚀\n¿Te interesa ver la opción?"
                 }

            # === SPECIFIC BUNDLE DETAILS (Must come FIRST) ===
            # We check for the bundle ID which we added to the message in business_logic.py
            if "apple_student" in last_msg.lower():
                 return {"role": "assistant", "content": "🎓 ¡El Pack Apple Student es un hit! Trae:\n• MacBook Air 13\"\n• AirPods 3ra Gen\n• Funda de regalo\n\nPrecio Promo: $1.850.000 (Ahorrás 15%). ¿Te lo reservo?"}
                 
            if "gamer_basic" in last_msg.lower():
                 return {"role": "assistant", "content": "¡Sí, tengo stock para entrega inmediata! 🎮 Es el más vendido. El precio final es $980.000. ¿Querés que te separe uno?"}

            if "play" in last_msg.lower() and "combo" in last_msg.lower():
                 return {"role": "assistant", "content": "🎮 ¡Tenemos el Pack Gamer Básico!\nIncluye:\n• PlayStation 5 Digital\n• 2 Joysticks DualSense\n• FIFA 24 Digital\n\nPrecio: $980.000 (10% OFF hoy)."}

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
                    "content": "¡Sí! Tenemos varios packs buenísimos con descuento hoy. ¿Buscás para jugar 🎮 o para estudiar/trabajar 🍎?"
                }
            if "recommendations" in last_msg:
                 return {
                    "role": "assistant",
                    "content": "Basado en lo que buscás, te súper recomiendo aprovechar los AirPods Pro que combinan genial. O si querés proteger el equipo, una funda MagSafe original."
                }
            if "products" in last_msg and "status': 'found'" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Encontré productos disponibles en catálogo. Si querés, te paso las opciones ordenadas por precio."
                }
            if "alternatives" in last_msg and "status': 'found'" in last_msg:
                return {
                    "role": "assistant",
                    "content": "No encontré exacto lo pedido, pero sí alternativas muy parecidas en stock."
                }
            if "hold_id" in last_msg:
                return {
                    "role": "assistant",
                    "content": "¡Perfecto! Ya te reservé el producto por 30 minutos. ¿Cómo preferís abonar? Transferencia o Efectivo?"
                }
                
            return {
                "role": "assistant",
                "content": "¡Bárbaro! Confirmado."
            }

        # Simple rule-based mocking for User messages
        
        # Scenario 6: MP Intent (Priority)
        if "confirmar con mercadopago" in last_msg:
             return {
                "role": "assistant",
                "content": "Generando link de pago...",
                "function_call": {
                    "name": "confirmar_venta",
                    "arguments": {
                        "hold_id": "HOLD-MOCK-MP-999",
                        "zona": "Palermo",
                        "metodo_pago": "MercadoPago"
                    }
                }
            }

        # Generic catalog intent across industries.
        if any(word in last_msg for word in ["busco", "quiero", "tenes", "tienen", "modelo", "talle", "size", "dosaje", "mg"]):
            color = None
            for c in ["black", "negro", "blue", "azul", "white", "blanco", "red", "rojo", "green", "verde", "pink", "rosa"]:
                if c in last_msg:
                    color = c
                    break
            return {
                "role": "assistant",
                "content": "Dejame buscar disponibilidad en catálogo...",
                "function_call": {
                    "name": "buscar_stock",
                    "arguments": {"modelo": last_msg, "color": color}
                }
            }

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
        if any(word in last_msg for word in ["pack", "combo", "bundle", "student"]):
            if "apple student" in last_msg:
                 return {
                    "role": "assistant",
                    "content": "Buscando ese pack específico...",
                    "function_call": {
                        "name": "obtener_bundle",
                        "arguments": {"bundle_id": "apple_student"}
                    }
                }
            return {
                "role": "assistant",
                "content": "¡Claro! Tenemos unos combos increíbles. Te muestro...",
                "function_call": {
                    "name": "listar_bundles",
                    "arguments": {"categoria": None}
                }
            }
            
        # === DEMO SCENARIO SPECIFIC MOCKS (For demo_final.py) ===
        
        # Scenario 1: FAQ & Recommendations
        if "envío" in last_msg:
            return {"role": "assistant", "content": "📦 Opciones de envío:\n• CABA: Gratis en moto (24-48hs)\n• AMBA: Consultar costo (48-72hs)\n• Interior: Por Correo/Andreani (3-5 días)\n• Retiro en local: Coordinamos horario"}
            
        if "recomendarme" in last_msg and "apple" in last_msg:
             return {"role": "assistant", "content": "🍎 Si buscás Apple, te recomiendo:\n1. MacBook Air M2 - Ideal estudiantes\n2. iPad Air 5 - Potencia y portabilidad\n3. AirPods Pro 2 - El mejor sonido\n\n¿Te interesa ver detalles de alguno?"}
             
        if "pack apple student" in last_msg:
             return {"role": "assistant", "content": "🎓 ¡El Pack Apple Student es un hit! Trae:\n• MacBook Air 13\"\n• AirPods 3ra Gen\n• Funda de regalo\n\nPrecio Promo: $1.850.000 (Ahorrás 15%). ¿Te lo reservo?"}
             
        if "garantía" in last_msg:
            return {"role": "assistant", "content": "✅ Garantía Oficial:\nTodos nuestros equipos tienen 1 año de garantía directa con Apple y 6 meses con nosotros por cualquier falla de fábrica. Comprá tranquilo."}

        # Scenario 2: Bundles & Sales
        if "combo de play 5" in last_msg:
             return {"role": "assistant", "content": "🎮 ¡Tenemos el Pack Gamer Básico!\nIncluye:\n• PlayStation 5 Digital\n• 2 Joysticks DualSense\n• FIFA 24 Digital\n\nPrecio: $980.000 (10% OFF hoy)."}

        if "pack gamer básico" in last_msg:
             return {"role": "assistant", "content": "¡Sí, tengo stock para entrega inmediata! 🎮 Es el más vendido. El precio final es $980.000. ¿Querés que te separe uno?"}

        if "pagar en cuotas" in last_msg or "pago con mercadopago" in last_msg:
            return {"role": "assistant", "content": "💳 Pagos:\n• Efectivo/Transferencia: Precio publicado\n• MercadoPago: QR o Link\n• Cuotas: 3 fijas sin interés o 6/12 con recargo bancario.\n\n¿Cómo preferís abonar?"}

        if "soy julian" in last_msg or "soy de palermo" in last_msg:
             return {"role": "assistant", "content": "¡Perfecto Juli! Ya tomé tus datos. 📝\n\nResumen del pedido:\n• Producto: Pack Gamer Básico\n• Entrega: Palermo (Moto Gratis)\n• Total: $980.000\n\n¿Confirmamos el pedido?"}

        if "confirmado" in last_msg:
             return {"role": "assistant", "content": "🎉 ¡Excelente! Pedido #4829 CONFIRMADO.\n\nTe reservé el stock por 30 minutos. Te mando el link de pago por WhatsApp al número que me pasaste. ¡Gracias por tu compra! 🚀"}

        # Scenario 3: Recommendations Context
        if "iphone 16 pro" in last_msg:
             return {"role": "assistant", "content": "📱 iPhone 16 Pro 128GB\nPrecio: U$S 1.200 / $1.450.000\nColores: Titanio Natural, Azul, Negro.\n\n¿Te gusta este modelo o buscás otra capacidad?"}

        if any(w in last_msg for w in ["caro", "que más tenés", "qué más tenés", "presupuesto", "barato"]):
             return {
                "role": "assistant",
                "content": (
                    "Entiendo. Si querés una opcion mas accesible, te muestro alternativas dentro del catalogo "
                    "actual con mejor precio. Decime tu presupuesto aproximado y te paso opciones."
                )
            }

        if "iphone 13" in last_msg:
             return {"role": "assistant", "content": "El iPhone 13 es un caño y es la mejor relación precio-calidad hoy. 🏅\n\n• 128GB: U$S 650\n• 256GB: U$S 750\n\nTe recomiendo el de 128GB en color Midnight. ¿Te separo uno?"}

        if "pensarlo" in last_msg:
             return {"role": "assistant", "content": "¡Dale, tranqui! Pensalo y cualquier cosa avísame. El stock vuela así que si te decidís escribime. ¡Estamos hablando! 👋"}

        # Upselling Mock Triggers
        if "found" in last_msg and "upsell_product" in last_msg:
             # Handle the result of obtaining upsell options
             # We should parse the message but for mock we can be generic
             return {
                 "role": "assistant",
                 "content": "¡Buena elección! Pero ojo... 👀\n\nPor una diferencia muy chica podés saltar al siguiente nivel. 🚀\n¿Te interesa ver la opción?"
             }
        
        if "iphone 15" in last_msg and "interesa" in last_msg:
              return {
                "role": "assistant",
                "content": "Excelente equipo. Dejame ver si tengo alguna oportunidad para vos...",
                "function_call": {
                    "name": "obtener_upselling",
                    "arguments": {"sku_actual": "IP15-128-BLK"} # Mock SKU
                }
            }



        # Scenario 5: Email Notification Flow
        if "@demo.com" in last_msg:
             # Trigger create reservation with email
             return {
                "role": "assistant",
                "content": "Perfecto, procesando reserva...",
                "function_call": {
                    "name": "crear_reserva",
                    "arguments": {
                        "sku": "IP13-128-MID", 
                        "nombre": "Julian", 
                        "contacto": "11223344",
                        "email": "julian@demo.com"
                    }
                }
            }
            
        if "efectivo" in last_msg: # Simplified for demo scenario 5
             # Trigger confirmation (which sends email)
             return {
                "role": "assistant",
                "content": "Confirmando venta...",
                "function_call": {
                    "name": "confirmar_venta",
                    "arguments": {
                        "hold_id": "HOLD-MOCK-123", # Mock ID
                        "zona": "CABA",
                        "metodo_pago": "Efectivo"
                    }
                }
            }
            

        # Fallbacks
        return {
            "role": "assistant",
            "content": "Perdón, no entendí bien. ¿Me podrías repetir qué estás buscando?"
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
        config = Config()
        
        # Get product categories dynamically
        try:
            categories = config.get_product_categories()
            categories_str = ", ".join(categories) if categories else "productos"
        except Exception as e:
            logging.warning(f"Could not get categories: {e}")
            categories_str = "productos"
        
        return f"""Sos un asistente de ventas virtual para {config.STORE_NAME}, una tienda de {config.STORE_TYPE} en {config.STORE_COUNTRY}.

Vendemos: {categories_str}

PERSONALIDAD Y TONO:
- Usá lenguaje argentino informal (vos, che, dale, etc.)
- Sé amigable, directo y eficiente
- Usá emojis ocasionalmente (📱 💳 ✅ 😓)
- No uses frases muy largas, mantené todo simple

REGLAS IMPORTANTES:
1. NUNCA inventes precios o disponibilidad - LLAMÁ buscar_stock()
2. NUNCA prometas horarios exactos de entrega - solo rangos (24-48hs, etc.)
3. Si no sabés algo con certeza, derivá a humano con derivar_humano()
4. Para temas sensibles (factura A, negociación especial, postventa) → derivar_humano()

PREGUNTAS FRECUENTES (FAQ):
- ANTES de responder sobre envío, garantía, pagos, cuotas, devoluciones → LLAMÁ consultar_faq()
- Si matchea un FAQ, usá esa respuesta EXACTA. Si no, respondé vos.

BUNDLES Y PACKS:
- Si el cliente busca combos/packs → LLAMÁ listar_bundles()
- Ofrece packs permanentes o temporales según corresponda

CROSS-SELLING Y RECOMENDACIONES:
- Al cerrar venta → LLAMÁ obtener_cross_sell_offer()
- Si preguntan "qué más tenés" o mostrás un producto → LLAMÁ obtener_recomendaciones()
- Si el cliente muestra interés en un modelo → LLAMÁ obtener_upselling() para ofrecer algo mejor (más GB, versión Pro/Max)

{ObjectionHandler().get_all_guidelines()}

POLÍTICAS DE LA TIENDA:
{policies}

FUNCIONES DISPONIBLES:
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
5. Pedir: nombre, contacto (celular) y MAIL 📧 (Importante para enviar confirmación)
6. Zona y Forma de Pago
7. Confirmar datos y crear reserva
8. Cerrar venta y ofrecer Cross-sell
"""


def get_available_functions() -> List[Dict[str, Any]]:
    """
    Define available functions for ChatGPT function calling
    
    Returns:
        List of function definitions in OpenAI format
    """
    return [
        {
            "name": "buscar_stock",
            "description": "Buscar productos por nombre/modelo y filtros opcionales (ej. color, almacenamiento).",
            "parameters": {
                "type": "object",
                "properties": {
                    "modelo": {"type": "string", "description": "Nombre del producto o modelo"},
                    "storage_gb": {"type": "integer", "description": "Almacenamiento/capacidad si aplica"},
                    "color": {"type": "string", "description": "Color o variante visual"},
                },
                "required": ["modelo"],
            },
        },
        {
            "name": "listar_modelos",
            "description": "Listar productos/modelos disponibles en stock.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "buscar_alternativas",
            "description": "Buscar alternativas cuando un producto exacto no está disponible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "modelo": {"type": "string", "description": "Producto originalmente solicitado"},
                    "storage_gb": {"type": "integer", "description": "Capacidad solicitada (opcional)"},
                    "color": {"type": "string", "description": "Color/variante solicitada (opcional)"},
                },
                "required": ["modelo"],
            },
        },
        {
            "name": "buscar_por_categoria",
            "description": "Buscar productos por categoría/rubro.",
            "parameters": {
                "type": "object",
                "properties": {"categoria": {"type": "string", "description": "Categoría de producto"}},
                "required": ["categoria"],
            },
        },
        {
            "name": "crear_reserva",
            "description": "Crear una reserva temporal para un producto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "SKU del producto"},
                    "nombre": {"type": "string", "description": "Nombre del cliente"},
                    "contacto": {"type": "string", "description": "Celular/WhatsApp del cliente"},
                    "email": {"type": "string", "description": "Email del cliente (opcional)"},
                },
                "required": ["sku", "nombre", "contacto"],
            },
        },
        {
            "name": "confirmar_venta",
            "description": "Confirmar venta de una reserva y descontar stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hold_id": {"type": "string", "description": "ID de reserva"},
                    "zona": {"type": "string", "description": "Zona de entrega"},
                    "metodo_pago": {"type": "string", "description": "Método de pago"},
                },
                "required": ["hold_id", "zona", "metodo_pago"],
            },
        },
        {
            "name": "obtener_cross_sell_offer",
            "description": "Obtener oferta de cross-sell contextual tras una venta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_comprado_sku": {
                        "type": "string",
                        "description": "SKU del producto vendido",
                    }
                },
                "required": ["producto_comprado_sku"],
            },
        },
        {
            "name": "obtener_recomendaciones",
            "description": "Recomendar productos relacionados por contexto o categoría.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_sku": {"type": "string", "description": "SKU de contexto (opcional)"},
                    "categoria": {"type": "string", "description": "Categoría de interés (opcional)"},
                },
                "required": [],
            },
        },
        {
            "name": "obtener_upselling",
            "description": "Sugerir una opción superior dentro de un rango razonable de precio.",
            "parameters": {
                "type": "object",
                "properties": {"sku_actual": {"type": "string", "description": "SKU del producto actual"}},
                "required": ["sku_actual"],
            },
        },
        {
            "name": "consultar_faq",
            "description": "Resolver preguntas frecuentes sin costo de LLM cuando haya match.",
            "parameters": {
                "type": "object",
                "properties": {"pregunta": {"type": "string", "description": "Pregunta textual del usuario"}},
                "required": ["pregunta"],
            },
        },
        {
            "name": "obtener_politicas",
            "description": "Devolver políticas de negocio (envíos, pagos, garantía, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"tema": {"type": "string", "description": "Tema a consultar"}},
                "required": ["tema"],
            },
        },
        {
            "name": "listar_bundles",
            "description": "Listar bundles/combo activos.",
            "parameters": {
                "type": "object",
                "properties": {"categoria": {"type": "string", "description": "Filtro opcional por categoría"}},
                "required": [],
            },
        },
        {
            "name": "obtener_bundle",
            "description": "Obtener detalle de un bundle por ID.",
            "parameters": {
                "type": "object",
                "properties": {"bundle_id": {"type": "string", "description": "Identificador del bundle"}},
                "required": ["bundle_id"],
            },
        },
        {
            "name": "comparar_productos",
            "description": "Comparar dos productos por SKU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku1": {"type": "string", "description": "SKU del primer producto"},
                    "sku2": {"type": "string", "description": "SKU del segundo producto"},
                },
                "required": ["sku1", "sku2"],
            },
        },
        {
            "name": "validar_datos_cliente",
            "description": "Validar datos del cliente antes de confirmar operación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "email": {"type": "string"},
                    "contacto": {"type": "string"},
                    "dni": {"type": "string"},
                },
                "required": ["nombre"],
            },
        },
        {
            "name": "detectar_fraude",
            "description": "Calcular riesgo de fraude para señales de cliente/mensaje.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": [],
            },
        },
        {
            "name": "derivar_humano",
            "description": "Derivar conversación a humano para casos especiales.",
            "parameters": {
                "type": "object",
                "properties": {
                    "razon": {"type": "string", "description": "Motivo de derivación"},
                    "contacto": {"type": "string"},
                    "nombre": {"type": "string"},
                },
                "required": ["razon"],
            },
        },
    ]
