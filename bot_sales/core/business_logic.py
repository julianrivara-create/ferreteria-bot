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

logger = logging.getLogger(__name__)
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


def format_money_ars(v: int) -> str:
    """Format Argentine pesos"""
    if v <= 0:
        return "A confirmar"
    return "$" + f"{v:,}".replace(",", ".")


class BusinessLogic:
    """Business logic layer for bot operations"""
    
    def __init__(self, db: Database, faq_file: str = "faqs.json"):
        self.db = db
        self.faq_handler = FAQHandler(faq_file=faq_file)
        self.bundle_manager = BundleManager(db=db)
        self.recommendation_engine = RecommendationEngine(db=db)
        self.email_client = EmailClient()
        self.mp_client = MercadoPagoClient()
        
        # New features
        self.validator = Validator()
        self.fraud_detector = FraudDetector()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.product_comparator = ProductComparator(db)
        self.translator = Translator()

        # P1: cache fuzzy-match results to avoid repeated O(N) scans
        self._normalize_cache: Dict[str, str] = {}

    def buscar_stock(
        self,
        modelo: str,
        categoria: Optional[str] = None,
        proveedor: Optional[str] = None,
        storage_gb: Optional[int] = None,
        color: Optional[str] = None,
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

        # Bug 3: validate query specs before hitting the catalog
        from bot_sales.services.search_validator import validate_query_specs
        valid, reason = validate_query_specs(modelo)
        if not valid:
            return {
                "status": "no_match",
                "products": [],
                "message": reason or f"No encontré productos para {modelo}",
                "_validator_blocked": True,
            }

        matches = self.db.find_matches_hybrid(modelo, storage_gb, color, categoria, proveedor)

        # Bug 2: score and rank results; drop low-relevance matches
        if matches:
            from bot_sales.ferreteria_quote import _score_product, _SCORE_LOW
            knowledge = getattr(self, "knowledge", None)
            scored = [
                (_score_product(m, modelo, knowledge=knowledge), m)
                for m in matches
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            matches = [m for score, m in scored if score > _SCORE_LOW][:5]

            if not matches:
                return {
                    "status": "no_match",
                    "products": [],
                    "message": f"No encontré productos relevantes para {modelo}",
                    "_filtered_by_scoring": True,
                }

        if not matches:
            filtros = " ".join(filter(None, [categoria, proveedor]))
            return {
                "status": "no_match",
                "products": [],
                "message": f"No encontré productos para {modelo}{' en ' + filtros if filtros else ''}".strip()
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
                "message": f"El producto existe pero no hay stock disponible ahora"
            }

        return {
            "status": "found",
            "products": products_with_availability,
            "message": f"Encontré {len(products_with_availability)} producto(s) disponible(s)"
        }

    def listar_modelos(self) -> Dict[str, Any]:
        """
        List all available models
        
        Returns:
            {
                "status": "success",
                "models": [...],
                "message": "..."
            }
        """
        all_stock = self.db.load_stock()
        
        # Group by category and show availability
        cat_summary = {}
        for item in all_stock:
            cat = item.get('category') or 'Varios'
            avail = self.db.available_for_sku(item['sku'])

            if cat not in cat_summary:
                cat_summary[cat] = {
                    "category": cat,
                    "available_count": 0,
                    "proveedores": set(),
                }

            if avail > 0:
                cat_summary[cat]["available_count"] += avail
                prov = item.get('proveedor', '')
                if prov:
                    cat_summary[cat]["proveedores"].add(prov)

        # Convert sets to lists
        models = []
        for cat_name, data in sorted(cat_summary.items()):
            if data["available_count"] > 0:
                data["proveedores"] = sorted(list(data["proveedores"]))
                models.append(data)
        
        return {
            "status": "success",
            "models": models,
            "message": f"Tengo {len(models)} modelos con stock disponible"
        }

    def buscar_alternativas(
        self,
        modelo: str,
        categoria: Optional[str] = None,
        proveedor: Optional[str] = None,
        storage_gb: Optional[int] = None,
        color: Optional[str] = None,
        limit: int = 3,
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
        placeholders = ["juan", "juan perez", "ejemplo", "usuario", "cliente", "example", "test"]
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
        result = self.db.create_hold(sku, nombre, contacto, HOLD_MINUTES)
        
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
        hold_info = self.db.cursor.execute(
            "SELECT sku, name, contact FROM holds WHERE hold_id = ?",
            (hold_id,)
        ).fetchone()
        
        if not hold_info:
            return {"status": "error", "message": "Reserva expirada o no encontrada."}
        
        sku, name, contact = hold_info
        
        # GUARDRAIL: Check physical stock (ignoring other holds, as we hold one)
        # We need to ensure stock_qty > 0.
        product_data = self.db.get_product_by_sku(sku)
        if not product_data or product_data['stock_qty'] <= 0:
            logger.critical("GUARDRAIL STOP: Attempted to sell %s with 0 physical stock. Hold: %s", sku, hold_id)
            return {"status": "error", "message": "Error crítico: Sin stock físico disponible al momento de cerrar."}
        
        success, result_msg = self.db.confirm_sale(hold_id, zona, metodo_pago)
        
        if success:
            sold_sku = sku
            mp_link = ""
            if "mercadopago" in metodo_pago.lower() and sold_sku:
                try:
                    mp_link = self.mp_client.create_preference(
                        title=f"{product_data.get('model', 'Producto')} ({sold_sku})",
                        price=float(product_data.get('price_ars', 1000)),
                        quantity=1,
                        external_reference=result_msg
                    )
                except Exception as e:
                    logger.warning("mp_link_generation_failed", error=str(e), sku=sold_sku)


            # Send Email Confirmation (only when customer provided an email address)
            if sold_sku and contact and "@" in str(contact):
                try:
                    order_details = {
                        "sale_id": result_msg,
                        "nombre": name or "Cliente",
                        "product_model": product_data.get('model', sold_sku),
                        "total_formatted": format_money_ars(product_data.get('price_ars', 0)),
                        "entrega": zona,
                        "metodo_pago": metodo_pago
                    }
                    if mp_link:
                         order_details["metodo_pago"] += f" (Link: {mp_link})"
                    self.email_client.send_order_confirmation(contact, order_details)
                except Exception as e:
                    logger.warning("email_confirmation_failed", error=str(e), sale_id=result_msg)
            
            final_msg = f"¡Venta confirmada! ID: {result_msg}"
            if mp_link:
                final_msg += f"\nAcá tenés tu link de pago: {mp_link}"

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
                "cross_sell_opportunity": cross_sell_info,  # Pass to LLM context
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
            categoria: Category/rubro name (ej: calzado, farmacia, tecnología, hogar)
        
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
        SMART RULES based on product category (configurable via Config)
        
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
        
        category = producto.get('category')
        
        # Check if cross-selling is enabled for this category
        from bot_sales.config import Config
        config = Config()
        
        if not config.ENABLE_CROSSSELLING:
            return {"status": "none", "offer": None, "message": "Cross-selling deshabilitado"}
        
        eligible_categories = config.get_crosssell_categories()
        
        if category not in eligible_categories:
            return {"status": "none", "offer": None, "message": f"Sin cross-sell para {category}"}
        
        # SMART CROSS-SELL RULES (Generic)
        # Try to find complementary products from other categories
        
        all_categories = self.db.get_all_categories()
        
        # Look for products in other categories (potential accessories/complements)
        for other_category in all_categories:
            if other_category == category:
                continue
            
            products = self.db.find_by_category(other_category)
            
            if not products:
                continue
            
            # Find best available product (prefer higher priced = better quality)
            for item in sorted(products, key=lambda x: x.get('price_ars', 0), reverse=True):
                avail = self.db.available_for_sku(item['sku'])
                if avail > 0:
                    # H6: read discount from config, not hardcoded
                    from ..config import Config as _Cfg
                    _discount_pct = getattr(_Cfg, "CROSS_SELL_DISCOUNT_PERCENT", 5)
                    original_price = item['price_ars']
                    discounted_price = int(original_price * (1 - _discount_pct / 100))
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
                            "discount_percent": _discount_pct,
                            "discount_amount": discount_amount,
                            "available": avail,
                            "reason": f"complemento ideal para tu {category}"
                        },
                        "message": f"Oferta: {item['model']} con {_discount_pct}% de descuento"
                    }
        
        # No cross-sell available
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
        sale = self.db.cursor.execute(
            "SELECT name, contact, email, zone, payment_method FROM sales WHERE sale_id = ?",
            (original_sale_id,)
        ).fetchone()
        
        if not sale:
            return {"status": "error", "message": "No encontré la venta original para copiar los datos."}
            
        name, contact, email, zone, payment_method = sale
        
        # 2. Create Reservation for new item (Reuse data)
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
        
        return {
            "status": "success",
            "lead_id": lead_id,
            "message": f"Ok, te paso con un asesor para {razon}. Te contacta pronto al {lead_contact}"
        }

    def _normalize_model(self, modelo: str) -> str:
        """Normalize model name for consistent matching (ferretería-specific)"""
        modelo = modelo.strip()

        # Ferretería abbreviation patterns: expand common shorthand before fuzzy match
        _PATTERNS = [
            (r'\ballen\s*(\d+[\.,]?\d*)\s*mm', r'llave allen \1mm'),
            (r'\bmecha\s*(\d+[\.,]?\d*)\s*mm', r'mecha \1mm'),
            (r'\btarugo\s*(\d+)\s*mm', r'tarugo \1mm'),
            (r'\bdestornillador\s+punta\s*(\w+)', r'destornillador \1'),
            (r'\bllave\s+(?:boca|plana)\s*(\d+)', r'llave boca \1'),
        ]
        for pattern, replacement in _PATTERNS:
            if re.search(pattern, modelo, re.IGNORECASE):
                modelo = re.sub(pattern, replacement, modelo, flags=re.IGNORECASE)
                break

        # P1: return cached result if available (same term repeated across synonyms)
        # Lazy init guards against __new__-constructed instances in tests.
        if not hasattr(self, "_normalize_cache"):
            self._normalize_cache = {}
        if modelo in self._normalize_cache:
            return self._normalize_cache[modelo]

        # Fuzzy match against known models in catalog
        known_models = self.db.get_all_models()
        matches = get_close_matches(modelo, known_models, n=1, cutoff=0.6)
        result = matches[0] if matches else modelo
        self._normalize_cache[modelo] = result
        return result

    def consultar_faq(self, pregunta: str) -> Dict[str, Any]:
        """
        Return all FAQ entries as structured context for the LLM.

        Instead of keyword-matching a single answer, every active FAQ is
        returned so the LLM can synthesise the best response from the
        policies already in its system prompt and from these entries.

        The function signature and return-value shape are preserved:
          - status "found" means context is available.
          - respuesta contains the formatted FAQ block.
          - faq_entries contains the raw list for programmatic use.

        Keyword matching is kept as a fast-path: if a keyword match is
        found, that entry is listed first so the LLM can prioritise it.
        """
        self.faq_handler._maybe_reload()
        all_entries = list(self.faq_handler.faqs.values())

        if not all_entries:
            return {
                "status": "not_found",
                "message": "No hay FAQs cargadas",
            }

        # Promote any keyword-matched entry to the top
        keyword_match = self.faq_handler.detect_faq(pregunta)
        matched_id: Optional[str] = None
        if keyword_match:
            matched_id = keyword_match.get("pregunta", "")

        ordered = []
        rest = []
        for entry in all_entries:
            if keyword_match and entry.get("pregunta") == matched_id:
                ordered.append(entry)
            else:
                rest.append(entry)
        ordered.extend(rest)

        # Build a structured context block the LLM can use
        lines = ["=== Preguntas Frecuentes (contexto para el asistente) ===", ""]
        for entry in ordered:
            q = str(entry.get("pregunta") or entry.get("question") or "").strip()
            a = str(entry.get("respuesta") or entry.get("answer") or "").strip()
            if q and a:
                lines.append(f"P: {q}")
                lines.append(f"R: {a}")
                lines.append("")

        context_block = "\n".join(lines).strip()

        return {
            "status": "found",
            "respuesta": context_block,
            "pregunta_matched": matched_id or "",
            "faq_entries": [
                {
                    "pregunta": str(e.get("pregunta") or e.get("question") or ""),
                    "respuesta": str(e.get("respuesta") or e.get("answer") or ""),
                }
                for e in ordered
            ],
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
        Smart Upselling: Find a 'better' version of the current product.
        Logic:
        1. Higher Storage (same model, same color if possible)
        2. Higher-priced variant (same base model)
        3. Next tier product (if available)
        """
        from bot_sales.config import Config
        config = Config()
        
        if not config.ENABLE_UPSELLING:
            return {"status": "none", "message": "Upselling deshabilitado"}
        
        current_product = self.db.get_product_by_sku(sku_actual)
        if not current_product:
             return {"status": "error", "message": "Producto original no encontrado"}

        potential_upsells = []
        all_stock = self.db.load_stock()
        
        current_price = current_product['price_ars']
        current_model = current_product['model']
        current_storage = current_product['storage_gb']
        current_category = current_product.get('category')
        
        # 1. Look for same model, MORE storage
        same_model_higher_storage = [
            p for p in all_stock 
            if p['model'] == current_model 
            and p['storage_gb'] > current_storage
            and self.db.available_for_sku(p['sku']) > 0
        ]
        potential_upsells.extend(same_model_higher_storage)
        
        # 2. Look for higher-priced products in same category (better variants)
        same_category_better = [
            p for p in all_stock
            if p.get('category') == current_category
            and p['model'] != current_model
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
        
        return {
            "status": "found",
            "upsell_product": best_upsell,
            "message": (
                f"Por solo {best_upsell['price_diff_formatted']} más, "
                f"te recomiendo {best_upsell.get('model', best_upsell.get('sku', 'una mejor opción'))}."
            ),
        }

    def comparar_productos(self, sku1: str, sku2: str) -> Dict[str, Any]:
        """
        Compara dos productos lado a lado.
        """
        return self.product_comparator.compare_products(sku1, sku2)

    def validar_datos_cliente(
        self,
        nombre: str,
        email: str = None,
        contacto: str = None,
        dni: str = None,
    ) -> Dict[str, Any]:
        """
        Valida datos de cliente para guardrails y cierre de venta.
        """
        data = {
            "nombre": nombre,
            "email": email,
            "contacto": contacto,
            "dni": dni,
        }

        is_valid, errors = self.validator.validate_customer_data(data)
        return {
            "valid": is_valid,
            "errors": errors,
            "message": "Datos válidos" if is_valid else "Hay errores en los datos",
        }

    def detectar_fraude(
        self,
        email: str = None,
        phone: str = None,
        message: str = None,
    ) -> Dict[str, Any]:
        """
        Calcula score de riesgo para transacciones.
        """
        score, reasons = self.fraud_detector.calculate_risk_score(
            email=email,
            phone=phone,
            message=message,
        )
        should_block = self.fraud_detector.should_block(score)

        return {
            "risk_score": score,
            "should_block": should_block,
            "reasons": reasons,
            "action": "block" if should_block else "allow",
        }
