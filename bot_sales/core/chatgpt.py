#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ChatGPT Integration Module
Handles OpenAI API communication with function calling support
"""

import ast
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
            result = self._mock_response(messages)
            result["meta"] = {
                "response_mode": "mock",
                "used_fallback": True,
                "model": self.model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 0,
            }
            return result
        
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
                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                tokens_used = int(getattr(usage, "total_tokens", 0) or 0)
                logging.info(f"OpenAI API call successful: {tokens_used} tokens, {elapsed:.2f}s")
                
                # Parse response
                message = response.choices[0].message
                
                result = {
                    "role": "assistant",
                    "content": message.content or "",
                    "meta": {
                        "response_mode": "openai",
                        "used_fallback": False,
                        "model": self.model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": tokens_used,
                        "latency_ms": int(elapsed * 1000),
                    },
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
            logging.error(
                f"[ChatGPTClient] API no disponible tras {max_retries} intentos. "
                f"Usando mock de emergencia. Error: {last_error}",
                exc_info=True,
            )
            result = self._mock_response(messages)
            result["meta"] = {
                "response_mode": "fallback_mock",
                "used_fallback": True,
                "model": self.model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 0,
                "error": str(last_error),
            }
            return result
        except Exception as mock_e:
            logging.error(f"Mock fallback also failed: {mock_e}")
            return {
                "role": "assistant",
                "content": "🔧 Disculpá, estoy teniendo problemas técnicos. Por favor intentá de nuevo en unos minutos o contactá a un vendedor humano. ¡Gracias por tu paciencia!",
                "error": str(last_error),
                "meta": {
                    "response_mode": "error",
                    "used_fallback": True,
                    "model": self.model,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "latency_ms": 0,
                    "error": str(last_error),
                },
            }

    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate mock responses for testing without API key
        """
        last_role = messages[-1].get("role", "")
        raw_msg = str(messages[-1].get("content", "") or "")
        last_msg = raw_msg.lower()
        if self.mock_mode:
            print(f"DEBUG MOCK: Role={last_role} Msg={last_msg[:100]}...")
            import sys
            sys.stdout.flush()

        if last_role == "function":
            payload = self._parse_mock_payload(raw_msg)
            if isinstance(payload, dict):
                if payload.get("respuesta"):
                    return {"role": "assistant", "content": str(payload.get("respuesta"))}

                if payload.get("status") == "found" and payload.get("products"):
                    return {"role": "assistant", "content": self._format_products_reply(payload["products"])}

                if payload.get("status") == "found" and payload.get("alternatives"):
                    return {
                        "role": "assistant",
                        "content": self._format_products_reply(
                            payload["alternatives"],
                            heading="No encontre exacto eso, pero si estas alternativas:",
                        ),
                    }

                if payload.get("status") == "found" and payload.get("pregunta_matched"):
                    return {"role": "assistant", "content": str(payload.get("respuesta", "Claro, te cuento."))}

                if payload.get("status") == "success" and payload.get("hold_id"):
                    expires = payload.get("expires_in_minutes", 30)
                    product = payload.get("product") or {}
                    product_name = product.get("model") or product.get("name") or product.get("sku", "el producto")
                    return {
                        "role": "assistant",
                        "content": (
                            f"Listo, te reserve **{product_name}**.\n\n"
                            f"La reserva dura **{expires} minutos**.\n"
                            "Decime tu zona y como queres pagar para seguir."
                        ),
                    }

                if payload.get("status") == "success" and payload.get("sale_id"):
                    return {"role": "assistant", "content": str(payload.get("message", "Venta confirmada."))}

                if payload.get("status") == "available" and payload.get("offer"):
                    offer = payload.get("offer") or {}
                    product = offer.get("product") or {}
                    name = product.get("model") or product.get("name") or offer.get("sku", "producto")
                    price = offer.get("discounted_price_formatted") or "precio promo disponible"
                    return {
                        "role": "assistant",
                        "content": f"Tengo una oferta relacionada: **{name}** a **{price}**. Si queres, te la agrego.",
                    }

                if payload.get("status") == "not_found":
                    return {
                        "role": "assistant",
                        "content": "No encontre una FAQ exacta. Si queres, decime si es por envio, pagos, factura o cambios.",
                    }

            if "bundles" in last_msg:
                return {
                    "role": "assistant",
                    "content": "No tengo combos activos cargados ahora mismo, pero puedo armarte una compra completa por rubro."
                }

            if "recommendations" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Te paso algunas opciones relacionadas para completar la compra."
                }

            if "upsell_product" in last_msg:
                return {
                    "role": "assistant",
                    "content": "Tambien tengo una opcion de gama mas alta si queres comparar rendimiento y precio."
                }

            return {"role": "assistant", "content": "Perfecto, seguimos con el siguiente paso."}

        if "confirmar con mercadopago" in last_msg:
            return {
                "role": "assistant",
                "content": "Generando confirmación de pago...",
                "function_call": {
                    "name": "confirmar_venta",
                    "arguments": {
                        "hold_id": "HOLD-MOCK-MP-999",
                        "zona": "CABA",
                        "metodo_pago": "MercadoPago",
                    },
                },
            }

        category_map = {
            "herramienta": "Herramientas Electricas",
            "herramientas": "Herramientas Electricas",
            "manuales": "Herramientas Manuales",
            "tornillo": "Tornilleria",
            "tornillos": "Tornilleria",
            "fijacion": "Fijaciones",
            "tarugo": "Fijaciones",
            "pintura": "Pintureria",
            "pintureria": "Pintureria",
            "rodillo": "Pintureria",
            "plomeria": "Plomeria",
            "silicona": "Plomeria",
            "seguridad": "Seguridad",
            "guante": "Seguridad",
        }
        for keyword, category in category_map.items():
            if keyword in last_msg and any(trigger in last_msg for trigger in ["categoria", "rubro", "tenes", "tienen", "mostrame", "que hay", "busco"]):
                return {
                    "role": "assistant",
                    "content": f"Te muestro lo disponible en {category}...",
                    "function_call": {"name": "buscar_por_categoria", "arguments": {"categoria": category}},
                }

        if any(
            word in last_msg
            for word in [
                "busco",
                "quiero",
                "tenes",
                "tienen",
                "modelo",
                "categoria",
                "color",
                "taladro",
                "amoladora",
                "atornillador",
                "llave",
                "martillo",
                "destornillador",
                "pintura",
                "rodillo",
                "tornillo",
                "tarugo",
                "pinza",
                "cinta",
                "mecha",
                "silicona",
            ]
        ):
            color = None
            for c in ["black", "negro", "blue", "azul", "white", "blanco", "red", "rojo", "green", "verde", "pink", "rosa"]:
                if c in last_msg:
                    color = c
                    break
            return {
                "role": "assistant",
                "content": "Déjame consultar disponibilidad en catálogo...",
                "function_call": {
                    "name": "buscar_stock",
                    "arguments": {"modelo": last_msg, "color": color},
                },
            }

        if any(word in last_msg for word in ["envio", "envío", "garantia", "garantía", "pago", "cuota", "factura", "devolucion", "devolución", "cambio", "retiro"]):
            return {
                "role": "assistant",
                "content": "Reviso políticas y te respondo al instante...",
                "function_call": {"name": "consultar_faq", "arguments": {"pregunta": last_msg}},
            }

        if any(word in last_msg for word in ["pack", "combo", "bundle"]):
            return {
                "role": "assistant",
                "content": "Te muestro los combos activos.",
                "function_call": {"name": "listar_bundles", "arguments": {"categoria": None}},
            }

        if any(word in last_msg for word in ["caro", "presupuesto", "barato", "economico", "económico"]):
            return {
                "role": "assistant",
                "content": "Entiendo. Si me decís tu presupuesto, te paso alternativas más convenientes."
            }

        if any(word in last_msg for word in ["reservalo", "reservamelo", "reservámelo", "me lo llevo", "lo quiero", "quiero reservar"]):
            return {
                "role": "assistant",
                "content": (
                    "Para reservarlo necesito estos datos:\n"
                    "1. Nombre y apellido\n"
                    "2. Celular con WhatsApp\n"
                    "3. Email\n"
                ),
            }

        if any(word in last_msg for word in ["pensarlo", "despues", "después", "luego"]):
            return {
                "role": "assistant",
                "content": "Perfecto, te espero cuando quieras. Si te decidís, te ayudo a cerrar rápido."
            }

        if "reserva demo" in last_msg:
            return {
                "role": "assistant",
                "content": "Perfecto, proceso una reserva de prueba.",
                "function_call": {
                    "name": "crear_reserva",
                    "arguments": {
                        "sku": "PRD-MOCK-001",
                        "nombre": "Cliente Demo",
                        "contacto": "11223344",
                    },
                },
            }

        if "efectivo" in last_msg:
            return {
                "role": "assistant",
                "content": "Confirmando operación...",
                "function_call": {
                    "name": "confirmar_venta",
                    "arguments": {
                        "hold_id": "HOLD-MOCK-123",
                        "zona": "CABA",
                        "metodo_pago": "Efectivo",
                    },
                },
            }

        return {"role": "assistant", "content": "No llegué a entender del todo. ¿Me contás qué producto o categoría buscás?"}

    @staticmethod
    def _parse_mock_payload(raw_msg: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = ast.literal_eval(raw_msg)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _format_mock_price(product: Dict[str, Any]) -> str:
        price = product.get("price_formatted")
        if price:
            return str(price)
        amount = product.get("price_ars") or product.get("price")
        try:
            amount_int = int(amount)
        except (TypeError, ValueError):
            return "precio a confirmar"
        return "$" + f"{amount_int:,}".replace(",", ".")

    def _format_products_reply(self, products: List[Dict[str, Any]], heading: str = "Encontre estas opciones con stock:") -> str:
        lines = [heading, ""]
        for product in products[:4]:
            name = product.get("model") or product.get("name") or product.get("sku", "Producto")
            category = product.get("category", "")
            available = product.get("available") or product.get("stock_qty") or product.get("stock") or 0
            price = self._format_mock_price(product)
            detail_parts = [f"**{name}**", price]
            if category:
                detail_parts.append(category)
            detail_parts.append(f"stock: {available}")
            lines.append("- " + " | ".join(str(part) for part in detail_parts if part))

        lines.append("")
        lines.append("Si queres, te recomiendo una opcion segun uso, presupuesto o marca.")
        return "\n".join(lines)

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
        
        return f"""Sos un asistente de ventas virtual para {config.STORE_NAME}, un negocio de {config.STORE_TYPE} en {config.STORE_COUNTRY}.

Vendemos: {categories_str}

PERSONALIDAD Y TONO:
- Usá lenguaje argentino informal (vos, che, dale, etc.)
- Sé amigable, directo y eficiente
- Usá emojis ocasionalmente (🔧 🔩 💳 ✅ 😓)
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
- Si el cliente muestra interés en un producto → LLAMÁ obtener_upselling() para ofrecer una opción superior o más rendidora

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
5. Pedir: nombre y contacto (celular/WhatsApp) 📱
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
            "description": "Buscar productos de ferretería por nombre, descripción o término de búsqueda. Filtros opcionales: categoría y proveedor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "modelo": {"type": "string", "description": "Nombre o descripción del producto (ej: 'llave allen', 'mecha 10mm', 'tornillo autoperforante')"},
                    "categoria": {"type": "string", "description": "Categoría opcional (ej: 'Llaves', 'Bulonería', 'Pinturas')"},
                    "proveedor": {"type": "string", "description": "Proveedor opcional: BlueTools, Bremen, Bulonfer"},
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
            "description": "Buscar alternativas cuando el producto exacto no está disponible. Útil cuando hay sin stock o el cliente quiere opciones similares.",
            "parameters": {
                "type": "object",
                "properties": {
                    "modelo": {"type": "string", "description": "Producto originalmente solicitado"},
                    "categoria": {"type": "string", "description": "Categoría del producto (opcional)"},
                    "proveedor": {"type": "string", "description": "Proveedor preferido (opcional)"},
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
