#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database Adapter for Postgres
Implements the same interface as the old SQLite Database class
but uses SQLAlchemy models and app.db.session
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

from app.db.session import ScopedSession
from app.db.models import Product, Order, OrderStatus, OrderItem, Lead
from sqlalchemy import or_, and_
import structlog

logger = structlog.get_logger()


def now_ts() -> float:
    return time.time()


def iso_time(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or now_ts()))


class Database:
    """
    Postgres Database Adapter
    Mimics the old SQLite interface for bot compatibility
    """
    
    def __init__(self, *_args, **_kwargs):
        """Initialize DB adapter (legacy args are accepted and ignored)."""
        self.session = ScopedSession()
        logger.info("database_adapter_initialized", backend="postgres")
    
    def log_event(self, event: str, data: Dict[str, Any] = None) -> None:
        """Log business events"""
        logger.info(event, **data or {})
    
    def find_matches(
        self,
        model: Optional[str],
        marca: Optional[str] = None,
        medida: Optional[str] = None,
        color: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find products matching criteria"""
        query = self.session.query(Product).filter(Product.active == True)
        
        if model:
            query = query.filter(Product.model.ilike(f"%{model}%"))
        if marca:
            query = query.filter(Product.brand.ilike(f"%{marca}%"))
        if medida:
            query = query.filter(Product.size.ilike(f"%{medida}%"))
        if color:
            query = query.filter(Product.color.ilike(f"%{color}%"))
        
        products = query.all()
        
        return [
            {
                "sku": p.sku,
                "category": p.category,
                "model": p.model,
                "brand": p.brand,
                "material": p.material,
                "size": p.size,
                "unit_of_measure": p.unit_of_measure,
                "color": p.color,
                "stock_qty": p.on_hand_qty,
                "price_ars": p.price_ars
            }
            for p in products
        ]
    
    def get_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Get product details by SKU"""
        product = self.session.query(Product).filter(Product.sku == sku).first()
        
        if not product:
            return None
        
        return {
            "sku": product.sku,
            "category": product.category,
            "model": product.model,
            "brand": product.brand,
            "material": product.material,
            "size": product.size,
            "unit_of_measure": product.unit_of_measure,
            "color": product.color,
            "stock_qty": product.on_hand_qty,
            "price_ars": product.price_ars
        }

    def update_product(self, sku: str, updates: Dict[str, Any]) -> bool:
        """Update product fields using legacy-compatible keys."""
        product = self.session.query(Product).filter(Product.sku == sku).first()
        if not product:
            return False

        field_map = {
            "model": "model",
            "modelo": "model",
            "category": "category",
            "categoria": "category",
            "brand": "brand",
            "marca": "brand",
            "material": "material",
            "size": "size",
            "medida": "size",
            "unit_of_measure": "unit_of_measure",
            "color": "color",
            "price_ars": "price_ars",
            "precio": "price_ars",
            "stock": "on_hand_qty",
            "on_hand_qty": "on_hand_qty",
            "active": "active",
        }

        for src_key, dst_key in field_map.items():
            if src_key not in updates:
                continue
            value = updates[src_key]
            if dst_key in {"price_ars", "on_hand_qty"} and value not in (None, ""):
                try:
                    value = int(float(value))
                except Exception:
                    continue
            setattr(product, dst_key, value)

        self.session.commit()
        return True

    def insert_product(self, data: Dict[str, Any]) -> bool:
        """Insert product using legacy-compatible payload keys."""
        sku = str(data.get("sku", "")).strip()
        if not sku:
            return False
        if self.session.query(Product).filter(Product.sku == sku).first():
            return False

        try:
            price_raw = data.get("price_ars", data.get("precio", 0))
            stock_raw = data.get("on_hand_qty", data.get("stock", 0))

            product = Product(
                sku=sku,
                model=str(data.get("model", data.get("modelo", sku))).strip(),
                category=str(data.get("category", data.get("categoria", "Others"))).strip() or "Others",
                brand=str(data.get("brand", data.get("marca", ""))).strip() or None,
                material=str(data.get("material", "")).strip() or None,
                size=str(data.get("size", data.get("medida", ""))).strip() or None,
                unit_of_measure=str(data.get("unit_of_measure", "unidad")).strip(),
                color=str(data.get("color", "")).strip(),
                price_ars=int(float(price_raw)) if price_raw not in (None, "") else 0,
                on_hand_qty=max(0, int(float(stock_raw)) if stock_raw not in (None, "") else 0),
                reserved_qty=0,
                active=True,
            )
            self.session.add(product)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def get_order_snapshot(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Return order details needed by business logic for hold/sale flows."""
        from uuid import UUID
        try:
            oid = UUID(order_id)
        except Exception:
            return None

        order = self.session.query(Order).filter(Order.id == oid).first()
        if not order or not order.items:
            return None

        item = order.items[0]
        meta = order.meta or {}
        return {
            "id": str(order.id),
            "status": order.status.value if order.status else None,
            "sku": item.sku,
            "quantity": item.quantity,
            "name": order.user_name,
            "contact": order.user_phone,
            "email": order.user_email,
            "zone": meta.get("zone"),
            "payment_method": meta.get("payment_method"),
        }
    
    def available_for_sku(self, sku: str) -> int:
        """Calculate available stock for a SKU"""
        product = self.session.query(Product).filter(Product.sku == sku).first()
        
        if not product:
            return 0
        
        return product.available_qty  # Uses the @property from models.py
    
    def create_hold(
        self,
        sku: str,
        name: str,
        contact: str,
        email: str = None,
        hold_minutes: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Create a hold/reservation by creating an Order with status HOLD"""
        if self.available_for_sku(sku) <= 0:
            return None
        
        product = self.session.query(Product).filter(Product.sku == sku).with_for_update().first()
        
        if not product or product.available_qty <= 0:
            return None
        
        # Create Order with HOLD status
        order = Order(
            user_id=contact,
            status=OrderStatus.HOLD,
            user_name=name,
            user_phone=contact,
            user_email=email,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=hold_minutes),
            meta={"source": "bot"}
        )
        
        # Create OrderItem
        item = OrderItem(
            sku=sku,
            quantity=1,
            price_at_purchase=product.price_ars
        )
        order.items.append(item)
        order.total_amount = product.price_ars
        
        # Reserve stock
        product.reserved_qty += 1
        
        self.session.add(order)
        self.session.commit()
        
        hold_id = str(order.id)
        
        self.log_event("HOLD_CREATED", {
            "hold_id": hold_id,
            "sku": sku,
            "name": name,
            "contact": contact
        })
        
        return {
            "hold_id": hold_id,
            "expires_in_minutes": hold_minutes,
            "expires_at": order.expires_at.timestamp()
        }
    
    def cleanup_holds(self) -> None:
        """Remove expired holds and release stock"""
        expired_orders = self.session.query(Order).filter(
            Order.status == OrderStatus.HOLD,
            Order.expires_at <= datetime.now(timezone.utc)
        ).all()
        
        for order in expired_orders:
            for item in order.items:
                product = self.session.query(Product).filter(Product.sku == item.sku).with_for_update().first()
                if product and product.reserved_qty >= item.quantity:
                    product.reserved_qty -= item.quantity
            
            order.status = OrderStatus.EXPIRED
        
        self.session.commit()
        logger.info("cleanup_holds_completed", expired_count=len(expired_orders))
    
    def release_hold(self, hold_id: str) -> bool:
        """Manually release a hold"""
        try:
            from uuid import UUID
            order_id = UUID(hold_id)
        except:
            return False
        
        order = self.session.query(Order).filter(Order.id == order_id, Order.status == OrderStatus.HOLD).first()
        
        if not order:
            return False
        
        for item in order.items:
            product = self.session.query(Product).filter(Product.sku == item.sku).with_for_update().first()
            if product and product.reserved_qty >= item.quantity:
                product.reserved_qty -= item.quantity
        
        order.status = OrderStatus.CANCELLED
        self.session.commit()
        
        return True
    
    def confirm_sale(
        self,
        hold_id: str,
        zone: str,
        payment_method: str
    ) -> Tuple[bool, str]:
        """Confirm a sale from a hold"""
        try:
            from uuid import UUID
            order_id = UUID(hold_id)
        except:
            return False, "Hold ID inválido"
        
        order = self.session.query(Order).filter(Order.id == order_id, Order.status == OrderStatus.HOLD).first()
        
        if not order:
            return False, "Hold expirado o no encontrado."
        
        # Check physical stock
        for item in order.items:
            product = self.session.query(Product).filter(Product.sku == item.sku).with_for_update().first()
            if not product or product.on_hand_qty <= 0:
                return False, "Error crítico: Sin stock físico disponible."
        
        # Update order metadata
        order.meta = order.meta or {}
        order.meta.update({
            "zone": zone,
            "payment_method": payment_method
        })
        
        # Transition to confirmed (uses OrderService logic)
        from app.services.order_service import OrderService
        OrderService.transition_status(self.session, order.id, OrderStatus.CONFIRMED)
        
        self.session.commit()
        
        sale_id = str(order.id)
        
        self.log_event("SALE_CONFIRMED", {
            "sale_id": sale_id,
            "order_id": str(order.id),
            "zone": zone,
            "payment": payment_method
        })
        
        return True, sale_id
    
    def upsert_lead(self, name: str, contact: str, note: str = "") -> Optional[str]:
        """Create a lead (for handoff scenarios) - Persists in DB."""
        lead_id: Optional[str] = None
        try:
            lead = Lead(
                name=name,
                contact=contact,
                note=note,
                source="bot",
            )
            self.session.add(lead)
            self.session.commit()
            lead_id = str(lead.id)
        except Exception as exc:
            self.session.rollback()
            logger.error("lead_persist_failed", error=str(exc))

        if lead_id:
            self.log_event("LEAD_CREATED", {
                "lead_id": lead_id,
                "name": name,
                "contact": contact,
                "note": note
            })
        else:
            self.log_event("LEAD_CREATE_FAILED", {
                "name": name,
                "contact": contact,
                "note": note
            })

        return lead_id
    
    def log_message(self, session_id: str, sender: str, message: str) -> None:
        """Log a chat message - Just use structured logging"""
        logger.info("chat_message", session_id=session_id, sender=sender, message=message[:100])
    
    def upsert_customer(self, email: str, name: str, phone: str = None, amount_spent: int = 0) -> None:
        """Update or create customer profile - Skip for now or implement later"""
        logger.info("customer_upsert", email=email, name=name, amount_spent=amount_spent)
    
    def load_stock(self) -> List[Dict[str, Any]]:
        """Load all stock items"""
        products = self.session.query(Product).filter(Product.active == True).all()
        
        return [
            {
                "sku": p.sku,
                "category": p.category,
                "model": p.model,
                "brand": p.brand,
                "material": p.material,
                "size": p.size,
                "unit_of_measure": p.unit_of_measure,
                "color": p.color,
                "stock_qty": p.on_hand_qty,
                "price_ars": p.price_ars
            }
            for p in products
        ]
    
    def get_all_products(self) -> List[Dict[str, Any]]:
        """Alias for load_stock"""
        return self.load_stock()
    
    def find_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Find all products in a category"""
        products = self.session.query(Product).filter(
            Product.category.ilike(category),
            Product.active == True
        ).all()
        
        return [
            {
                "sku": p.sku,
                "category": p.category,
                "model": p.model,
                "brand": p.brand,
                "material": p.material,
                "size": p.size,
                "unit_of_measure": p.unit_of_measure,
                "color": p.color,
                "stock_qty": p.on_hand_qty,
                "price_ars": p.price_ars
            }
            for p in products
        ]
    
    def get_all_categories(self) -> List[str]:
        """Get list of all unique categories"""
        results = self.session.query(Product.category).filter(Product.active == True).distinct().all()
        return [r[0] for r in results if r[0]]
    
    def get_all_models(self) -> List[str]:
        """Get list of all unique models"""
        results = self.session.query(Product.model).filter(Product.active == True).distinct().all()
        return [r[0] for r in results if r[0]]
    
    def get_all_colors(self) -> List[str]:
        """Get list of all unique colors"""
        results = self.session.query(Product.color).filter(Product.active == True).distinct().all()
        return [r[0] for r in results if r[0]]
    
    def close(self):
        """Close database connection"""
        ScopedSession.remove()
