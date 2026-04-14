
from app.db.models import Order, Product, OrderStatus, InventoryEvent
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid
import structlog

logger = structlog.get_logger()

class OrderService:
    @staticmethod
    def transition_status(session: Session, order_id, new_status: OrderStatus, meta: dict = None):
        if isinstance(order_id, str): order_id = uuid.UUID(order_id)
        
        order = session.query(Order).filter(Order.id == order_id).first()
        if not order: raise ValueError("Order not found")
        
        if new_status == OrderStatus.CONFIRMED:
            OrderService.finalize_order(session, order_id)
        
        order.status = new_status
        order.updated_at = datetime.now(timezone.utc)
        if meta:
            if not order.meta: order.meta = {}
            order.meta.update(meta)

    @staticmethod
    def finalize_order(session: Session, order_id):
        if isinstance(order_id, str): order_id = uuid.UUID(order_id)
        order = session.get(Order, order_id)
        
        if order.finalized_at: return 

        # Validate stock before applying mutations to keep inventory consistent.
        for item in order.items:
            product = session.query(Product).filter(
                Product.tenant_id == order.tenant_id,
                Product.sku == item.sku,
            ).with_for_update().first()
            if not product or product.on_hand_qty < item.quantity or product.reserved_qty < item.quantity:
                raise ValueError(f"Insufficient stock for SKU {item.sku}")
        
        # Atomic Stock Deduction
        for item in order.items:
            product = session.query(Product).filter(
                Product.tenant_id == order.tenant_id,
                Product.sku == item.sku,
            ).with_for_update().first()
            if product:
                product.reserved_qty -= item.quantity
                product.on_hand_qty -= item.quantity
                
                # Log Event
                session.add(InventoryEvent(
                    tenant_id=order.tenant_id,
                    sku=item.sku, delta_on_hand=-item.quantity, delta_reserved=-item.quantity,
                    reason="order_confirmed", source="order_finalize"
                ))
        
        order.finalized_at = datetime.now(timezone.utc)
