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


class OpenAIServiceDegradedError(RuntimeError):
    """Raised when OpenAI is degraded and fallback mode should be used."""

    def __init__(self, reason: str, original_error: Exception):
        self.reason = reason
        self.original_error = original_error
        super().__init__(f"{reason}: {original_error}")


class ChatGPTClient:
    """
    Client for interacting with OpenAI's ChatGPT API
    Supports function calling for bot actions
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o", temperature: float = 0.7, max_tokens: int = 800):
        """
        Initialize ChatGPT client
        
        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4o-mini)
            temperature: Response randomness (0-1)
            max_tokens: Max tokens in response
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        # Enable mock mode if no API key or placeholder
        self.mock_mode = not api_key or "PLACEHOLDER" in api_key or "sk-" not in api_key
        self.client = None
        
        if not self.mock_mode:
            try:
                import openai
                import httpx
                self.openai_version = openai.__version__
                self.httpx_version = httpx.__version__
                self.client = openai.OpenAI(api_key=api_key)
                logging.info(f"ChatGPT initialized with model {self.model}")
            except ImportError:
                logging.warning("openai package not installed. Switching to MOCK mode.")
                self.mock_mode = True
                self.init_error = "ImportError: openai not installed"
            except Exception as e:
                logging.warning(f"Failed to initialize OpenAI client: {e}. Switching to MOCK mode.")
                self.mock_mode = True
                self.init_error = str(e)
        
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
                    "timeout": 15  # Optimized timeout (15s)
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

        reason, should_trigger_fallback = self._classify_openai_failure(last_error)
        if should_trigger_fallback:
            raise OpenAIServiceDegradedError(reason=reason, original_error=last_error)

        return {
            "role": "assistant",
            "content": f"⚠️ Error de conexión con OpenAI: {str(last_error)}",
            "error": str(last_error),
        }

    @staticmethod
    def _classify_openai_failure(error: Exception) -> Tuple[str, bool]:
        """
        Decide whether a failure should activate offline fallback.
        Fallback only for quota/rate-limit/timeout/transient 5xx outages.
        """
        if error is None:
            return "unknown_openai_error", False

        status_code = getattr(error, "status_code", None)
        error_type = type(error).__name__
        message = str(error).lower()

        if "insufficient_quota" in message or "quota" in message:
            return "insufficient_quota", True

        if status_code == 429 or "rate limit" in message or "too many requests" in message:
            return "rate_limited", True

        if status_code in {500, 502, 503, 504}:
            return "openai_server_error", True

        if error_type in {"APITimeoutError", "APIConnectionError", "InternalServerError"}:
            return "openai_network_or_timeout", True

        if "timeout" in message or "timed out" in message:
            return "openai_timeout", True

        if "temporarily unavailable" in message or "try again later" in message:
            return "openai_temporarily_unavailable", True

        return "non_fallback_error", False

    def _mock_response(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate mock responses using the robust MockResponseHandler
        """
        from .mock_handler import mock_handler
        
        last_role = messages[-1].get("role", "")
        last_msg = str(messages[-1].get("content", "")).lower()
        
        if self.mock_mode:
            print(f"DEBUG MOCK: Role={last_role} Msg={last_msg[:100]}...")
            import sys
            sys.stdout.flush()
            
        # Try finding a match using the robust handler

        # Keep legacy logic below as secondary check (or remove it if 100% replaced)
        # For safety, we keep specific functional checks (like function_call triggers)
        
        # 1. Try Function Logic First (Legacy - Critical for flow)
        if last_role == "function":
             # Upselling Function Result
            if "upsell_product" in last_msg:
                 return {
                     "role": "assistant",
                     "content": "¡Buena elección! Pero ojo... 👀\n\nPor una diferencia muy chica podés saltar al siguiente nivel. 🚀\n¿Te interesa ver la opción?"
                 }

            # === SPECIFIC BUNDLE DETAILS (Must come FIRST) ===
            if "kit_taladrado" in last_msg.lower():
                return {"role": "assistant", "content": "🔧 ¡El Kit Taladrado trae mechas acero + tarugos nylon. Ahorrás 10% comprándolo junto. ¿Te lo reservo?"}

            if "kit_pintura" in last_msg.lower():
                return {"role": "assistant", "content": "🖌️ ¡El Kit Pintura Interior trae látex + rodillo + bandeja + lija. 8% OFF. ¿Te interesa?"}

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
                    "content": "Basado en lo que buscás, te recomiendo complementar con tarugos Fischer o mechas acero rápido. ¿Querés que te busque opciones?"
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

        # 2. Try New Robust Mock Handler (For User Messages)
        robust_response = mock_handler.get_response(last_msg)
        if robust_response:
             return {
                "role": "assistant",
                "content": robust_response
            }

        # 3. Legacy Rules (Keep specifically for complex function calls like MP or specific demo flows)
        
        # Scenario 6: MP Intent (Priority)
        if "confirmar con mercadopago" in last_msg:
             return {
                "role": "assistant",
                "content": "Generando link de pago...",
                "function_call": {
                    "name": "confirmar_venta",
                    "arguments": {
                        "hold_id": "HOLD-MOCK-MP-999",
                        "zona": "CABA",
                        "metodo_pago": "MercadoPago"
                    }
                }
            }

        # FAQ Mock (Legacy - kept as backup)
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
        if any(word in last_msg for word in ["pack", "combo", "bundle", "kit taladrado", "kit pintura"]):
            return {
                "role": "assistant",
                "content": "¡Claro! Tenemos kits con descuento. Te muestro...",
                "function_call": {
                    "name": "listar_bundles",
                    "arguments": {"categoria": None}
                }
            }

        # FAQ & common queries
        if "garantía" in last_msg:
            return {"role": "assistant", "content": "✅ Garantía de fábrica incluida en todos los productos. El plazo depende de la marca."}

        if "pagar en cuotas" in last_msg or "pago con mercadopago" in last_msg:
            return {"role": "assistant", "content": "💳 Pagos:\n• Efectivo/Transferencia: sin recargo\n• Débito: sin recargo\n• MercadoPago: consultá recargo vigente\n\n¿Cómo preferís abonar?"}

        if "confirmado" in last_msg:
            return {"role": "assistant", "content": "🎉 ¡Excelente! Reserva CONFIRMADA.\n\nTe la guardo por 24hs hábiles. ¡Gracias! 🔧"}

        if any(w in last_msg for w in ["caro", "más barato", "presupuesto", "económico"]):
            return {"role": "assistant", "content": "Entiendo. Puedo mostrarte alternativas de otras marcas en el mismo rango. ¿Para qué lo vas a usar?"}

        if "pensarlo" in last_msg:
            return {"role": "assistant", "content": "¡Dale, tranqui! Cuando te decidás avisame. 👋"}

        # Upselling Mock Triggers
        if "found" in last_msg and "upsell_product" in last_msg:
             # Handle the result of obtaining upsell options
             # We should parse the message but for mock we can be generic
             return {
                 "role": "assistant",
                 "content": "¡Buena elección! Pero ojo... 👀\n\nPor una diferencia muy chica podés saltar al siguiente nivel. 🚀\n¿Te interesa ver la opción?"
             }
        
        if "taladro" in last_msg and "interesa" in last_msg:
              return {
                "role": "assistant",
                "content": "Excelente elección. Dejame ver si tengo alguna oportunidad para vos...",
                "function_call": {
                    "name": "obtener_upselling",
                    "arguments": {"sku_actual": "TAL-MOCK-001"}
                }
            }

        # Scenario 5: Demo Reservation Flow (mock only)
        if "reserva demo" in last_msg:
             return {
                "role": "assistant",
                "content": "Perfecto, procesando reserva de prueba...",
                "function_call": {
                    "name": "crear_reserva",
                    "arguments": {
                        "sku": "PRD-MOCK-001",
                        "nombre": "Cliente Demo",
                        "contacto": "11223344"
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
            

            
        # 4. Final Fallback (Robust)
        return {
            "role": "assistant",
            "content": mock_handler.get_fallback()
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
        # Load prompt template from external file
        import os
        prompt_file = os.path.join(os.path.dirname(__file__), '../data/system_prompt_v2.txt')
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            return prompt_template.replace('{policies}', policies)
        except FileNotFoundError:
            # Fallback to basic prompt if file doesn't exist
            return f"""Sos un VENDEDOR experto de ferretería.
POLÍTICAS: {policies}
Si no sabés algo, derivá a humano con derivar_humano()."""


def get_available_functions() -> List[Dict[str, Any]]:
    """
    Define available functions for ChatGPT function calling
    
    Returns:
        List of function definitions in OpenAI format
    """
    return [
        {
            "name": "buscar_stock",
            "description": "Buscar productos de ferretería por nombre o descripción. Filtros opcionales: categoría y proveedor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "modelo": {
                        "type": "string",
                        "description": "Nombre o descripción del producto (ej: 'llave allen', 'mecha 10mm', 'tarugo fischer 8mm')"
                    },
                    "categoria": {
                        "type": "string",
                        "description": "Categoría opcional (ej: 'Llaves', 'Bulonería', 'Pinturas', 'Tarugos y Tacos')"
                    },
                    "proveedor": {
                        "type": "string",
                        "description": "Proveedor opcional: BlueTools, Bremen, Bulonfer"
                    }
                },
                "required": ["modelo"]
            }
        },
        {
            "name": "listar_modelos",
            "description": "Listar todos los modelos disponibles en catálogo",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "buscar_alternativas",
            "description": "Buscar productos alternativos cuando el producto exacto no está disponible o el cliente quiere opciones similares",
            "parameters": {
                "type": "object",
                "properties": {
                    "modelo": {
                        "type": "string",
                        "description": "Producto originalmente solicitado"
                    },
                    "categoria": {
                        "type": "string",
                        "description": "Categoría del producto (opcional)"
                    },
                    "proveedor": {
                        "type": "string",
                        "description": "Proveedor preferido (opcional)"
                    }
                },
                "required": ["modelo"]
            }
        },
        {
            "name": "crear_reserva",
            "description": "Crear una reserva de 30 minutos para un producto. Requiere SKU del producto, nombre y contacto del cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "SKU del producto a reservar (obtenido de buscar_stock)"
                    },
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del cliente"
                    },
                    "contacto": {
                        "type": "string",
                        "description": "WhatsApp o email del cliente"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email para envío de confirmación de pedido"
                    }
                },
                "required": ["sku", "nombre", "contacto", "email"]
            }
        },
        {
            "name": "confirmar_venta",
            "description": "Confirmar la venta final y decrementar stock. Requiere hold_id, zona y método de pago.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hold_id": {
                        "type": "string",
                        "description": "ID de la reserva creada previamente"
                    },
                    "zona": {
                        "type": "string",
                        "description": "Zona de entrega (CABA, AMBA o Interior)"
                    },
                    "metodo_pago": {
                        "type": "string",
                        "description": "Forma de pago (Transferencia, Efectivo, MercadoPago, Tarjeta)"
                    }
                },
                "required": ["hold_id", "zona", "metodo_pago"]
            }
        },
        {
            "name": "obtener_politicas",
            "description": "Obtener información detallada de políticas de la tienda",
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {
                        "type": "string",
                        "description": "Tema de la política (envios, pagos, garantia, devoluciones, cuotas)",
                        "enum": ["envios", "pagos", "garantia", "devoluciones", "cuotas"]
                    }
                },
                "required": ["tema"]
            }
        },
        {
            "name": "agregar_producto_extra",
            "description": "Usar cuando el usuario agrega CUALQUIER producto extra inmediatamente después de una compra (Cross-sell, oferta, u otro item). Reusa los datos de la venta anterior.",
            "parameters": {
                "type": "object",
                "properties": {
                    "original_sale_id": {
                        "type": "string",
                        "description": "El ID de la venta original."
                    },
                    "offer_sku": {
                        "type": "string",
                        "description": "El SKU del producto a agregar."
                    }
                },
                "required": ["original_sale_id", "offer_sku"]
            }
        },
        {
            "name": "derivar_humano",
            "description": "Derivar la conversación a un asesor humano. Usar para casos especiales, negociaciones, factura A, postventa, urgencias.",
            "parameters": {
                "type": "object",
                "properties": {
                    "razon": {
                        "type": "string",
                        "description": "Razón de la derivación (ej: 'factura A', 'negociación', 'postventa')"
                    },
                    "contacto": {
                        "type": "string",
                        "description": "Contacto del cliente para que el asesor se comunique"
                    },
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del cliente"
                    }
                },
                "required": ["razon"]
            }
        },
        {
            "name": "buscar_por_categoria",
            "description": "Buscar todos los productos de una categoría específica. Útil cuando el cliente pregunta por una categoría entera.",
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {
                        "type": "string",
                        "description": "Categoría de producto (ej: 'Llaves', 'Bocallaves y Dados', 'Bulonería', 'Pinturas', 'Herramientas Electricas')"
                    }
                },
                "required": ["categoria"]
            }
        },
        {
            "name": "obtener_cross_sell_offer",
            "description": "Obtener oferta de cross-selling tras una venta. Llamar DESPUÉS de confirmar_venta() para sugerir productos complementarios.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_comprado_sku": {
                        "type": "string",
                        "description": "SKU del producto que se acaba de vender (obtenido del response de confirmar_venta)"
                    }
                },
                "required": ["producto_comprado_sku"]
            }
        },
        {
            "name": "consultar_faq",
            "description": "Consultar si una pregunta del usuario coincide con las preguntas frecuentes. Usar ANTES de responder preguntas sobre envío, garantía, pagos, cuotas, etc. AHORRA TOKENS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "Pregunta del usuario textual"
                    }
                },
                "required": ["pregunta"]
            }
        },
        {
            "name": "listar_bundles",
            "description": "Listar packs/bundles disponibles (permanentes y temporales). Incluye descuentos especiales. Usar cuando el cliente busca combos o packs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {
                        "type": "string",
                        "description": "Filtrar por categoría (opcional, ej: 'Llaves', 'Herramientas Electricas', 'Pinturas')"
                    }
                },
                "required": []
            }
        },
        {
            "name": "obtener_bundle",
            "description": "Obtener detalles completos de un bundle específico incluyendo productos, precio, descuento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle_id": {
                        "type": "string",
                        "description": "ID del bundle (ej: 'kit_taladrado', 'kit_pintura')"
                    }
                },
                "required": ["bundle_id"]
            }
        },
        {
            "name": "obtener_recomendaciones",
            "description": "Obtener recomendaciones de productos basadas en lo que el cliente está viendo o comprando. Usar proactivamente cuando el cliente pregunta 'qué más tenés?' o después de mostrar un producto principal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_sku": {
                        "type": "string",
                        "description": "SKU del producto que el cliente está mirando (opcional)"
                    },
                    "categoria": {
                        "type": "string",
                        "description": "Categoría de interés (opcional)"
                    }
                },
                "required": []
            }
        },
        {
            "name": "obtener_upselling",
            "description": "Obtener opciones de upselling (mejor versión, más GB, Pro) para un producto que el cliente está considerando. USAR CUANDO el cliente se interesa en un modelo específico pero aún no confirma.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_actual": {
                        "type": "string",
                        "description": "SKU del producto que el cliente está mirando actualmente"
                    }
                },
                "required": ["sku_actual"]
            }
        },
        {
            "name": "comparar_productos",
            "description": "Comparar dos productos lado a lado mostrando diferencias. Usar cuando el cliente pregunta 'cuál es la diferencia' o 'X vs Y'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku1": {
                        "type": "string",
                        "description": "SKU del primer producto a comparar"
                    },
                    "sku2": {
                        "type": "string",
                        "description": "SKU del segundo producto a comparar"
                    }
                },
                "required": ["sku1", "sku2"]
            }
        },
        {
            "name": "validar_datos_cliente",
            "description": "Validar formato de datos del cliente antes de crear reserva. Proactivo para evitar errores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del cliente"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email del cliente (opcional)"
                    },
                    "contacto": {
                        "type": "string",
                        "description": "Teléfono de contacto (opcional)"
                    },
                    "dni": {
                        "type": "string",
                        "description": "DNI del cliente (opcional)"
                    }
                },
                "required": ["nombre"]
            }
        },
        {
            "name": "detectar_fraude",
            "description": "INTERNO: Calcular score de riesgo de fraude para una transacción. Usar ANTES de confirmar ventas de alto valor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email del cliente (opcional)"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Teléfono del cliente (opcional)"
                    },
                    "message": {
                        "type": "string",
                        "description": "Último mensaje del cliente (opcional)"
                    }
                },
                "required": []
            }
        }
    ]
