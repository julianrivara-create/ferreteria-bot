#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Business Logic Module
Implements callable functions for ChatGPT function calling
Each function bridges between ChatGPT and the Database
"""

import re
import logging
from typing import Dict, Any, List, Optional
from difflib import get_close_matches
from .database import Database
from ..faq import FAQHandler
from ..bundles import BundleManager
from ..recommendations import RecommendationEngine
from ..integrations.email_client import EmailClient
from ..integrations.mercadopago_client import MercadoPagoClient
from ..security.validators import Validator
from ..security.fraud_detector import FraudDetector
from ..intelligence.sentiment import SentimentAnalyzer
from ..intelligence.comparisons import ProductComparator
from ..i18n.translator import Translator
from .payment_validator import payment_validator
from ..config import config as bot_config


def format_money_ars(v: int) -> str:
    """Format Argentine pesos"""
    if v <= 0:
        return "A confirmar"
    return "$" + f"{v:,}".replace(",", ".")


class BusinessLogic:
    """Business logic layer for bot operations"""
    
    def __init__(self, db: Database):
        self.db = db
        self.faq_handler = FAQHandler()
        self.bundle_manager = BundleManager(db=db)
        self.recommendation_engine = RecommendationEngine(db=db)
        self.email_client = EmailClient()
        self.mp_client = MercadoPagoClient()
        
        # Security & Intelligence features
        self.validator = Validator()
        self.fraud_detector = FraudDetector()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.product_comparator = ProductComparator(db)
        self.translator = Translator()
        self.payment_validator = payment_validator

    @staticmethod
    def _is_transfer_payment(method: str) -> bool:
        normalized = (method or "").strip().lower()
        return "transfer" in normalized

    def _build_transfer_payment_instructions(self) -> Dict[str, str]:
        cvu = str(getattr(bot_config, "TRANSFER_CVU", "") or "").strip()
        alias = str(getattr(bot_config, "TRANSFER_ALIAS", "") or "").strip()
        account_name = str(getattr(bot_config, "TRANSFER_ACCOUNT_NAME", "") or "").strip()

        detail_lines: List[str] = []
        if cvu:
            detail_lines.append(f"CVU: {cvu}")
        if alias:
            detail_lines.append(f"Alias: {alias}")
        if account_name:
            detail_lines.append(f"Titular: {account_name}")

        if not detail_lines:
            return {"chat_text": "", "email_text": "", "email_html": ""}

        chat_text = (
            "Perfecto. Para hacer la transferencia, usá estos datos:\n"
            + "\n".join(f"- {line}" for line in detail_lines)
            + "\nCuando la realices, pasame el comprobante por este medio para acreditarla enseguida."
        )
        email_text = "\n".join(detail_lines) + "\n\nCuando realices la transferencia, enviá el comprobante para confirmar la acreditación."
        email_html = (
            "<p>Para avanzar con la transferencia, usá estos datos:</p>"
            + "<ul>"
            + "".join(f"<li>{line}</li>" for line in detail_lines)
            + "</ul>"
            + "<p>Cuando la realices, enviá el comprobante para confirmar la acreditación.</p>"
        )
        return {
            "chat_text": chat_text,
            "email_text": email_text,
            "email_html": email_html,
        }

    def buscar_stock(
        self,
        modelo: str,
        marca: Optional[str] = None,
        medida: Optional[str] = None,
        categoria: Optional[str] = None,
        color: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for products in stock
        
        Returns:
            {
                "status": "found" | "no_stock" | "no_match",
                "products": [...],
                "message": "Human-readable message for context"
            }
        """
        # Normalize model name
        modelo = self._normalize_model(modelo)
        
        matches = self.db.find_matches(modelo, marca=marca, medida=medida, color=color)
        
        # If a category filter was given, narrow down
        if categoria and matches:
            cat_lower = categoria.lower()
            matches = [m for m in matches if cat_lower in (m.get('category') or '').lower()]
        
        if not matches:
            search_desc = modelo
            if marca:
                search_desc += f" {marca}"
            if medida:
                search_desc += f" {medida}"
            return {
                "status": "no_match",
                "products": [],
                "message": f"No encontré productos para '{search_desc}'"
            }
        
        # Check availability
        products_with_availability = []
        for product in matches:
            avail = self.db.available_for_sku(product['sku'])
            if avail > 0:
                product['available'] = avail
                product['price_formatted'] = format_money_ars(product['price_ars'])
                products_with_availability.append(product)
        
        if not products_with_availability:
            return {
                "status": "no_stock",
                "products": matches,
                "message": "El producto existe pero no hay stock disponible ahora"
            }
        
        return {
            "status": "found",
            "products": products_with_availability,
            "message": f"Encontré {len(products_with_availability)} producto(s) disponible(s)"
        }

    def listar_modelos(self) -> Dict[str, Any]:
        """
        List all available models grouped by category
        
        Returns:
            {
                "status": "success",
                "models": [...],
                "message": "..."
            }
        """
        all_stock = self.db.load_stock()
        
        # Group by model and show availability
        model_summary = {}
        for item in all_stock:
            model = item['model']
            avail = self.db.available_for_sku(item['sku'])
            
            if model not in model_summary:
                model_summary[model] = {
                    "model": model,
                    "category": item.get('category', ''),
                    "available_count": 0,
                    "brand_options": set(),
                    "size_options": set(),
                    "color_options": set()
                }
            
            if avail > 0:
                model_summary[model]["available_count"] += avail
                if item.get('brand'):
                    model_summary[model]["brand_options"].add(item['brand'])
                if item.get('size'):
                    model_summary[model]["size_options"].add(item['size'])
                if item.get('color'):
                    model_summary[model]["color_options"].add(item['color'])
        
        # Convert sets to lists
        models = []
        for model_name, data in model_summary.items():
            if data["available_count"] > 0:
                data["brand_options"] = sorted(list(data["brand_options"]))
                data["size_options"] = sorted(list(data["size_options"]))
                data["color_options"] = sorted(list(data["color_options"]))
                models.append(data)
        
        return {
            "status": "success",
            "models": models,
            "message": f"Tengo {len(models)} modelos con stock disponible"
        }

    def buscar_alternativas(
        self,
        modelo: str,
        marca: Optional[str] = None,
        color: Optional[str] = None,
        limit: int = 3
    ) -> Dict[str, Any]:
        """
        Find alternative products when exact match not available
        
        Returns:
            {
                "status": "found" | "none",
                "alternatives": [...],
                "message": "..."
            }
        """
        alternatives = []
        
        # Try same model, different specs
        modelo = self._normalize_model(modelo)
        similar = self.db.find_matches(modelo, None, None)
        
        for item in similar:
            avail = self.db.available_for_sku(item['sku'])
            if avail > 0:
                item['available'] = avail
                item['price_formatted'] = format_money_ars(item['price_ars'])
                alternatives.append(item)
        
        # If no alternatives in same model, show other products from same category
        if not alternatives:
            all_stock = self.db.load_stock()
            for item in all_stock:
                avail = self.db.available_for_sku(item['sku'])
                if avail > 0:
                    item['available'] = avail
                    item['price_formatted'] = format_money_ars(item['price_ars'])
                    alternatives.append(item)
        
        # Sort by availability
        alternatives = sorted(
            alternatives,
            key=lambda x: x.get('available', 0),
            reverse=True
        )[:limit]
        
        if not alternatives:
            return {
                "status": "none",
                "alternatives": [],
                "message": "No hay alternativas disponibles en este momento"
            }
        
        return {
            "status": "found",
            "alternatives": alternatives,
            "message": f"Encontré {len(alternatives)} alternativa(s) disponible(s)"
        }

    def crear_reserva(
        self,
        sku: str,
        nombre: str,
        contacto: str,
        email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a hold/reservation
        
        Returns:
            {
                "status": "success" | "error",
                "hold_id": "...",
                "expires_in_minutes": 30,
                "message": "..."
            }
        """
        # Validate product exists
        product = self.db.get_product_by_sku(sku)
        if not product:
            return {
                "status": "error",
                "message": f"SKU {sku} no encontrado"
            }
        
        # GUARDRAIL: Anti-Hallucination & Validation
        # 1. Check for Placeholder/Hallucinated Data
        placeholders = ["juan", "juan perez", "ejemplo", "usuario", "cliente", "example"]
        if nombre.lower() in placeholders or "123456" in contacto or "ejemplo" in str(email):
            return {
                "status": "error",
                "message": "INSTRUCCIÓN PARA EL BOT: NO hay ningún error técnico. El usuario todavía no te dió sus datos reales. NO te disculpes. Simplemente decile: 'Para reservarlo, necesito tu nombre, teléfono y email'."
            }

        # 2. Validate Data Formats
        if not self.validator.validate_phone(contacto)[0]:
             return {
                "status": "error",
                "message": f"El teléfono '{contacto}' no parece válido. Por favor pedile al usuario un número real."
            }
            
        if email and not self.validator.validate_email(email)[0]:
             return {
                "status": "error",
                "message": f"El email '{email}' no es válido. Pedile un email real."
            }

        # Check availability
        avail = self.db.available_for_sku(sku)
        if avail <= 0:
            return {
                "status": "error",
                "message": "Sin stock disponible para reservar"
            }
        
        # Create hold
        from ..config import HOLD_MINUTES
        result = self.db.create_hold(sku, nombre, contacto, email, HOLD_MINUTES)
        
        if not result:
            return {
                "status": "error",
                "message": "No se pudo crear la reserva"
            }
        
        return {
            "status": "success",
            "hold_id": result['hold_id'],
            "expires_in_minutes": result['expires_in_minutes'],
            "product": product,
            "message": f"Reserva creada exitosamente. Expira en {result['expires_in_minutes']} minutos."
        }

    def confirmar_venta(
        self,
        hold_id: str,
        zona: str,
        metodo_pago: str
    ) -> Dict[str, Any]:
        """
        Confirm sale from hold
        
        Returns:
            {
                "status": "success" | "error",
                "sale_id": "...",
                "product_sku": "...",  # NEW: For cross-sell check
                "message": "..."
            }
        """
        # Get hold info before confirming (to know what was sold)
        hold_info = self.db.get_order_snapshot(hold_id)
        if not hold_info or hold_info.get("status") != "hold":
            return {"status": "error", "message": "Reserva expirada o no encontrada."}

        sku = hold_info["sku"]
        name = hold_info.get("name")
        customer_email = hold_info.get("email")
        
        # GUARDRAIL: Check physical stock (ignoring other holds, as we hold one)
        # We need to ensure stock_qty > 0.
        product_data = self.db.get_product_by_sku(sku)
        if not product_data or product_data['stock_qty'] <= 0:
            logging.critical(f"GUARDRAIL STOP: Attempted to sell {sku} with 0 physical stock. Hold: {hold_id}")
            return {"status": "error", "message": "Error crítico: Sin stock físico disponible al momento de cerrar."}
        
        success, result_msg = self.db.confirm_sale(hold_id, zona, metodo_pago)
        
        if success:
            sold_sku = sku
            mp_link = ""
            transfer_instructions: Optional[Dict[str, str]] = None
            if "mercadopago" in metodo_pago.lower() and sold_sku:
                try:
                    mp_link = self.mp_client.create_preference(
                        title=f"{product_data.get('model', 'Producto')} ({sold_sku})",
                        price=float(product_data.get('price_ars', 1000)),
                        quantity=1,
                        external_reference=result_msg
                    )
                except Exception as e:
                    logging.exception("Error generating MercadoPago link for sale %s: %s", result_msg, e)


            # Send Email Confirmation
            if sold_sku:
                try:
                    order_details = {
                        "order_id": result_msg,
                        "nombre": name or "Cliente",
                        "producto": product_data.get('model', sold_sku),
                        "precio": product_data.get('price_ars', 0),
                        "zona": zona,
                        "metodo_pago": metodo_pago
                    }
                    if mp_link:
                        order_details["payment_link"] = mp_link

                    if self._is_transfer_payment(metodo_pago):
                        transfer_instructions = self._build_transfer_payment_instructions()
                        order_details["transfer_instructions_text"] = transfer_instructions["email_text"]
                        order_details["transfer_instructions_html"] = transfer_instructions["email_html"]

                    if customer_email:
                        self.email_client.send_order_confirmation(customer_email, order_details)
                    else:
                        logging.warning("No customer email available for sale %s; skipping email confirmation.", result_msg)
                except Exception as e:
                    logging.exception("Error sending order confirmation email for sale %s: %s", result_msg, e)
            
            final_msg = f"¡Venta confirmada! ID: {result_msg}"
            if mp_link:
                final_msg += f"\n💳 Acá tenés tu link de pago: {mp_link}"
            if self._is_transfer_payment(metodo_pago):
                if transfer_instructions is None:
                    transfer_instructions = self._build_transfer_payment_instructions()
                if transfer_instructions.get("chat_text"):
                    final_msg += f"\n\n{transfer_instructions['chat_text']}"

            # AUTO-CROSS-SELL INJECTION
            cross_sell = self.obtener_cross_sell_offer(sold_sku)
            cross_sell_info = None
            if cross_sell.get('status') == 'available':
                offer = cross_sell['offer']
                final_msg += f"\n\n🔥 ¡OFERTA ESPECIAL! 🔥\nTe ofrecemos {offer['product']['model']} {offer['reason']} con {offer['discount_percent']}% OFF.\nPrecio Promo: {offer['discounted_price_formatted']} (Antes {offer['original_price_formatted']}).\n¿Te lo agrego?"
                cross_sell_info = cross_sell

            return {
                "status": "success",
                "sale_id": result_msg,
                "product_sku": sold_sku, 
                "cross_sell_opportunity": cross_sell_info, # Pass to LLM context
                "message": final_msg
            }
        else:
            return {
                "status": "error",
                "message": result_msg
            }

    def buscar_por_categoria(self, categoria: str) -> Dict[str, Any]:
        """
        Search products by category
        
        Args:
            categoria: Nombre de la categoría (ej: Llaves, Bulonería, Pinturas, Herramientas Electricas)
        
        Returns:
            {
                "status": "found" | "no_match",
                "products": [...],
                "message": "..."
            }
        """
        products = self.db.find_by_category(categoria)
        
        if not products:
            return {
                "status": "no_match",
                "products": [],
                "message": f"No encontré productos en la categoría {categoria}"
            }
        
        # Check availability
        available_products = []
        for product in products:
            avail = self.db.available_for_sku(product['sku'])
            if avail > 0:
                product['available'] = avail
                product['price_formatted'] = format_money_ars(product['price_ars'])
                available_products.append(product)
        
        if not available_products:
            return {
                "status": "no_stock",
                "products": [],
                "message": f"No hay stock disponible en {categoria} ahora"
            }
        
        return {
            "status": "found",
            "products": available_products,
            "message": f"Encontré {len(available_products)} producto(s) de {categoria}"
        }

    def obtener_cross_sell_offer(
        self,
        producto_comprado_sku: str
    ) -> Dict[str, Any]:
        """
        Get cross-sell offer after purchase
        SMART RULES based on product category:
        - Herramientas Electricas → Discos Abrasivos (5% off)
        - Bulonería → Tarugos y Tacos (5% off)
        - Pinturas → Albañilería (5% off)
        - Llaves → Bocallaves y Dados (5% off)
        
        Args:
            producto_comprado_sku: SKU of product just sold
        
        Returns:
            {
                "status": "available" | "none",
                "offer": {...} or None,
                "message": "..."
            }
        """
        # Get product that was sold
        producto = self.db.get_product_by_sku(producto_comprado_sku)
        
        if not producto:
            return {"status": "none", "offer": None, "message": "Producto no encontrado"}
        
        category = producto.get('category', '')

        # Cross-sell rules for ferretería
        # Herramientas Electricas → Discos Abrasivos (5% off)
        # Bulonería → Tarugos y Tacos (5% off)
        # Pinturas → Albañilería (5% off)
        # Llaves → Bocallaves y Dados (5% off)
        CROSS_SELL_MAP = {
            'Herramientas Electricas': ('Discos Abrasivos', 5, 'para usar con tu herramienta'),
            'Bulonería': ('Tarugos y Tacos', 5, 'para complementar tu fijación'),
            'Pinturas': ('Rodillos y Pinceles', 5, 'para la aplicación'),
            'Llaves': ('Bocallaves y Dados', 5, 'para ampliar tu juego'),
            'Plomería': ('Teflón y Adhesivos', 5, 'para sellar correctamente'),
            'Electricidad': ('Cablecanal y Fichas', 5, 'para la instalación'),
            'Jardinería': ('Mangueras', 5, 'para complementar'),
            'Albañilería': ('Niveles y Cucharas', 5, 'para la obra'),
            'Tornillería y Fijaciones': ('Tarugos y Tacos', 5, 'para completar la fijación'),
        }

        if category in CROSS_SELL_MAP:
            target_cat, discount_pct, reason = CROSS_SELL_MAP[category]
            complementos = self.db.find_by_category(target_cat)

            for item in sorted(complementos, key=lambda x: x.get('price_ars', 0), reverse=True):
                avail = self.db.available_for_sku(item['sku'])
                if avail > 0:
                    original_price = item['price_ars']
                    discounted_price = int(original_price * (1 - discount_pct / 100))
                    discount_amount = original_price - discounted_price
                    return {
                        "status": "available",
                        "offer": {
                            "sku": item['sku'],
                            "product": item,
                            "original_price": original_price,
                            "original_price_formatted": format_money_ars(original_price),
                            "discounted_price": discounted_price,
                            "discounted_price_formatted": format_money_ars(discounted_price),
                            "discount_percent": discount_pct,
                            "discount_amount": discount_amount,
                            "available": avail,
                            "reason": reason,
                        },
                        "message": f"Oferta: {item['model']} {reason} con {discount_pct}% de descuento"
                    }

        return {"status": "none", "offer": None, "message": "No hay ofertas disponibles"}

    def agregar_producto_extra(
        self,
        original_sale_id: str,
        offer_sku: str
    ) -> Dict[str, Any]:
        """
        Add an extra product to a confirmed customer (reuses data).
        Works for cross-sells, upsells, or just adding another item post-purchase.
        
        Args:
            original_sale_id: ID of the confirmed sale
            offer_sku: SKU of the item to add
            
        Returns:
            Success/Error dict
        """
        # 1. Get original sale data
        sale = self.db.get_order_snapshot(original_sale_id)
        if not sale:
            return {"status": "error", "message": "No encontré la venta original para copiar los datos."}

        name = sale.get("name")
        contact = sale.get("contact")
        email = sale.get("email")
        zone = sale.get("zone") or "A coordinar"
        payment_method = sale.get("payment_method") or "A confirmar"
        
        # 2. Create Reservation for new item (Reuse data)
        # Note: We can reuse crear_reserva.
        # Since 'name' comes from DB, it should be valid, but guardrail might trigger if name looks fake.
        # Assuming DB data is clean enough.
        
        res_result = self.crear_reserva(offer_sku, name, contact, email)
        
        if res_result["status"] != "success":
             return {"status": "error", "message": f"No pude reservar el item extra: {res_result['message']}"}
             
        new_hold_id = res_result["hold_id"]
        
        # 3. Confirm Sale immediately
        # We assume same payment method and zone
        conf_result = self.confirmar_venta(new_hold_id, zone, payment_method)
        
        if conf_result["status"] == "success":
            return {
                "status": "success",
                "message": f"¡Listo! Agregué el producto {offer_sku} a tu pedido. Te llegará todo junto a {zone}."
            }
        else:
             return {"status": "error", "message": f"Error al confirmar el item extra: {conf_result['message']}"}

    def obtener_politicas(self, tema: str) -> Dict[str, Any]:
        """
        Get policy information
        
        Args:
            tema: One of: envios, pagos, garantia, devoluciones, cuotas
        
        Returns:
            {
                "status": "success",
                "info": "...",
                "message": "..."
            }
        """
        policies = {
            "envios": """🚚 ENVÍOS:
• CABA: Gratis, moto 24-48hs (rango)
• AMBA: Consultar costo, 48-72hs
• Interior: Correo/Andreani, 3-5 días hábiles

IMPORTANTE: No prometemos horarios exactos, solo rangos.""",
            
            "pagos": """💳 FORMAS DE PAGO:
• Transferencia/Efectivo: Posible descuento (se confirma antes)
• MercadoPago: Aceptamos
• Tarjeta con cuotas: Según plan vigente, informamos recargo antes de cerrar

Preguntame por la forma que prefieras.""",
            
            "cuotas": """📊 CUOTAS:
Los pagos con tarjeta se procesan vía MercadoPago.
Podés ver las cuotas y promociones bancarias disponibles directamente al momento de pagar.
¿Te gustaría avanzar con la compra?""",
            
            "garantia": """🛡️ GARANTÍA:
• Cobertura oficial del fabricante según producto
• Plazos y condiciones según política vigente
• Cualquier tema de postventa se gestiona por canal oficial

¿Tenés alguna duda específica?""",
            
            "devoluciones": """🔄 CAMBIOS Y DEVOLUCIONES:
Dependen del estado del equipo y días desde la compra.
Para coordinar esto, te paso con un asesor.
¿Me das tu contacto?"""
        }
        
        info = policies.get(tema.lower(), "No tengo info sobre ese tema. ¿Querés que te pase con un asesor?")
        
        return {
            "status": "success",
            "info": info,
            "message": f"Información sobre {tema}"
        }

    def derivar_humano(
        self,
        razon: str,
        contacto: Optional[str] = None,
        nombre: Optional[str] = None,
        resumen: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handoff to human with AI summary
        
        Returns:
            {
                "status": "success",
                "lead_id": "...",
                "message": "..."
            }
        """
        lead_name = nombre or "Cliente"
        lead_contact = contacto or "No proporcionado"
        
        note_content = f"Handoff: {razon}"
        if resumen:
            note_content += f"\n\n📝 Resumen IA:\n{resumen}"
        
        lead_id = self.db.upsert_lead(
            name=lead_name,
            contact=lead_contact,
            note=note_content
        )

        if not lead_id:
            return {
                "status": "error",
                "lead_id": None,
                "message": (
                    f"Ok, te paso con un asesor para {razon}. "
                    "Tuvimos un problema técnico al registrar el lead, pero igual te contactamos."
                )
            }

        return {
            "status": "success",
            "lead_id": lead_id,
            "message": f"Ok, te paso con un asesor para {razon}. Te contacta pronto al {lead_contact}"
        }

    def _normalize_model(self, modelo: str) -> str:
        """Normalize model name for consistent matching in ferretería context"""
        modelo = modelo.strip()
        
        # Common ferretería abbreviations/shortcuts
        patterns = [
            (r'\ballen\s*(\d+[\.,]?\d*)\s*mm', r'llave allen \1mm'),
            (r'\bmecha\s*(\d+[\.,]?\d*)\s*mm', r'mecha \1mm'),
            (r'\btarugo\s*(\d+)\s*mm', r'tarugo \1mm'),
            (r'\bdestornillador\s*(philips|plano|estrella|torx)', r'destornillador \1'),
            (r'\bllave\s*boca\s*(\d+)', r'llave boca \1mm'),
            (r'\bdisco\s*de?\s*corte\s*(\d+)', r'disco de corte \1mm'),
            (r'\bcinta\s*(\w+)', r'cinta \1'),
            (r'\bb&d\b', 'Black+Decker'),
            (r'\bbyd\b', 'Black+Decker'),
            (r'\bdewalt\b', 'DeWalt'),
            (r'\bbosch\b', 'Bosch'),
            (r'\bstanley\b', 'Stanley'),
        ]

        for pattern, replacement in patterns:
            match = re.search(pattern, modelo, re.IGNORECASE)
            if match:
                return re.sub(pattern, replacement, modelo, flags=re.IGNORECASE)
        
        # Fuzzy match against known models
        known_models = self.db.get_all_models()
        matches = get_close_matches(modelo, known_models, n=1, cutoff=0.6)
        if matches:
            return matches[0]
        
        return modelo

    def consultar_faq(self, pregunta: str) -> Dict[str, Any]:
        """
        Check if question matches an FAQ
        Saves tokens by answering without AI
        
        Args:
            pregunta: User's question
        
        Returns:
            {
                "status": "found" | "not_found",
                "respuesta": "..." or None
            }
        """
        faq = self.faq_handler.detect_faq(pregunta)
        
        if faq:
            return {
                "status": "found",
                "respuesta": faq["respuesta"],
                "pregunta_matched": faq["pregunta"]
            }
        
        return {
            "status": "not_found",
            "message": "No es una pregunta frecuente"
        }
    
    def listar_bundles(self, categoria: Optional[str] = None) -> Dict[str, Any]:
        """
        List available bundles (permanent and seasonal)
        
        Args:
            categoria: Filter by category (optional)
        
        Returns:
            {
                "status": "success",
                "bundles": [...],
                "message": "..."
            }
        """
        bundles = self.bundle_manager.get_active_bundles(categoria)
        
        if not bundles:
            return {
                "status": "empty",
                "bundles": [],
                "total": 0,
                "message": "No hay bundles activos en este momento"
            }
        
        # Format bundles for display
        bundles_formatted = []
        for bundle in bundles:
            bundles_formatted.append({
                "bundle_id": bundle["bundle_id"],
                "name": bundle["name"],
                "description": bundle["description"],
                "final_price": bundle["final_price"],
                "discount_percent": bundle["discount_percent"],
                "savings": bundle["savings"],
                "is_seasonal": bundle.get("is_seasonal", False)
            })
        
        return {
            "status": "success",
            "bundles": bundles_formatted,
            "total": len(bundles_formatted),
            "message": f"{len(bundles_formatted)} pack(s) disponible(s)"
        }
    
    def obtener_bundle(self, bundle_id: str) -> Dict[str, Any]:
        """
        Get details of a specific bundle
        
        Args:
            bundle_id: Bundle identifier
        
        Returns:
            {
                "status": "found" | "not_found",
                "bundle": {...},
                "formatted_message": "..."
            }
        """
        bundle = self.bundle_manager.get_bundle_by_id(bundle_id)
        
        if not bundle:
            return {
                "status": "not_found",
                "message": "Bundle no encontrado o no disponible"
            }
        
        # Format for display
        formatted_msg = self.bundle_manager.format_bundle_message(bundle)
        
        return {
            "status": "found",
            "bundle": bundle,
            "formatted_message": formatted_msg,
            "message": f"Bundle found: {bundle.get('bundle_id')} {bundle.get('name')}"
        }

    def obtener_recomendaciones(self, producto_sku: Optional[str] = None, categoria: Optional[str] = None) -> Dict[str, Any]:
        """
        Get product recommendations
        
        Args:
            producto_sku: SKU of current product context (optional)
            categoria: Category context (optional)
            
        Returns:
            {
                "status": "success",
                "recommendations": [...],
                "formatted_message": "..."
            }
        """
        recs = self.recommendation_engine.get_recommendations(
            current_product_sku=producto_sku,
            category=categoria,
            limit=3
        )
        
        if not recs:
            return {
                "status": "empty",
                "message": "No tengo recomendaciones específicas por ahora."
            }
            
        formatted_msg = self.recommendation_engine.format_recommendation_message(recs)
        
        return {
            "status": "success",
            "recommendations": recs,
            "formatted_message": formatted_msg
        }

    def obtener_upselling(self, sku_actual: str) -> Dict[str, Any]:
        """
        Smart Upselling for ferretería: Find a 'better' version of the current product.
        Logic:
        1. Same category, better brand (higher price)
        2. Same product, larger size/quantity
        3. Kit version of individual product
        """
        current_product = self.db.get_product_by_sku(sku_actual)
        if not current_product:
             return {"status": "error", "message": "Producto original no encontrado"}

        potential_upsells = []
        all_stock = self.db.load_stock()
        
        current_price = current_product['price_ars']
        current_model = current_product['model']
        current_category = current_product.get('category', '')
        
        # 1. Same category, higher price (better brand/model)
        same_category_better = [
            p for p in all_stock
            if p.get('category') == current_category
            and p['sku'] != current_product['sku']
            and p['price_ars'] > current_price
            and self.db.available_for_sku(p['sku']) > 0
        ]
        potential_upsells.extend(same_category_better)

        # Filter and Sort: Must be more expensive but within 40% range (smart upsell)
        valid_upsells = []
        seen_skus = set()
        
        for p in potential_upsells:
            if p['sku'] in seen_skus: continue
            
            price_diff = p['price_ars'] - current_price
            # Must be more expensive but not insane (max 40% more)
            if price_diff > 0 and price_diff < (current_price * 0.40):
                p['price_diff'] = price_diff
                p['price_diff_formatted'] = format_money_ars(price_diff)
                valid_upsells.append(p)
                seen_skus.add(p['sku'])
                
        # Pick the best one (lowest price difference first to be persuasive)
        valid_upsells.sort(key=lambda x: x['price_diff'])
        
        if not valid_upsells:
             return {"status": "none", "message": "No hay oportunidades de upsell lógicas"}

        best_upsell = valid_upsells[0]
        brand_info = f" ({best_upsell.get('brand')})" if best_upsell.get('brand') else ""
        
        return {
            "status": "found",
            "upsell_product": best_upsell,
            "message": f"Por solo {best_upsell['price_diff_formatted']} más, llevate el {best_upsell['model']}{brand_info}!"
        }

    def comparar_productos(self, sku1: str, sku2: str) -> Dict[str, Any]:
        """
        Compara dos productos lado a lado
        
        Args:
            sku1: SKU del primer producto
            sku2: SKU del segundo producto
        
        Returns:
            {
                'status': str,
                'comparison_table': str,
                'recommendation': str
            }
        """
        result = self.product_comparator.compare_products(sku1, sku2)
        return result

    def validar_datos_cliente(self, nombre: str, email: str = None, 
                             contacto: str = None, dni: str = None) -> Dict[str, Any]:
        """
        Valida datos del cliente
        
        Returns:
            {
                'valid': bool,
                'errors': {field: error_message}
            }
        """
        data = {
            'nombre': nombre,
            'email': email,
            'contacto': contacto,
            'dni': dni
        }
        
        is_valid, errors = self.validator.validate_customer_data(data)
        
        return {
            'valid': is_valid,
            'errors': errors,
            'message': 'Datos válidos' if is_valid else 'Hay errores en los datos'
        }

    def detectar_fraude(self, email: str = None, phone: str = None, 
                       message: str = None) -> Dict[str, Any]:
        """
        Calcula risk score para transacción
        
        Returns:
            {
                'risk_score': int (0-100),
                'should_block': bool,
                'reasons': []
            }
        """
        score, reasons = self.fraud_detector.calculate_risk_score(
            email=email, phone=phone, message=message
        )
        
        should_block = self.fraud_detector.should_block(score)
        
        return {
            'risk_score': score,
            'should_block': should_block,
            'reasons': reasons,
            'action': 'block' if should_block else 'allow'
        }
