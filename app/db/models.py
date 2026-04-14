
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, ForeignKeyConstraint, Enum as SQLEnum, Boolean, JSON, PrimaryKeyConstraint, Index
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
import enum
from datetime import datetime, timezone

Base = declarative_base()
JSONType = JSON().with_variant(JSONB, "postgresql")


def _utc_now():
    """Return timezone-aware UTC datetime for consistent DB defaults."""
    return datetime.now(timezone.utc)

class OrderStatus(enum.Enum):
    CREATED = "created"
    HOLD = "hold"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class Product(Base):
    __tablename__ = 'products'
    tenant_id = Column(String(100), nullable=False, index=True)
    sku = Column(String(50), index=True)
    model = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    brand = Column(String(100))
    material = Column(String(100))
    size = Column(String(50))
    unit_of_measure = Column(String(20), default='unidad')
    color = Column(String(50))
    price_ars = Column(Integer, nullable=False)
    on_hand_qty = Column(Integer, default=0, nullable=False)
    reserved_qty = Column(Integer, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
    order_items = relationship("OrderItem", back_populates="product")
    __table_args__ = (PrimaryKeyConstraint('tenant_id', 'sku'),)

    @property
    def available_qty(self) -> int:
        return max(0, self.on_hand_qty - self.reserved_qty)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.CREATED, nullable=False, index=True)
    total_amount = Column(Integer)
    user_name = Column(String(200))
    user_phone = Column(String(50))
    user_email = Column(String(200))
    created_at = Column(DateTime, default=_utc_now, nullable=False, index=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
    expires_at = Column(DateTime, index=True)
    finalized_at = Column(DateTime)
    meta = Column(JSONType, default=dict)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order")
    __table_args__ = (Index('ix_tenant_id_user_id', 'tenant_id', 'user_id'),)

class OrderItem(Base):
    __tablename__ = 'order_items'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    tenant_id = Column(String(100), nullable=False)
    sku = Column(String(50), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    price_at_purchase = Column(Integer, nullable=False)
    order = relationship("Order", back_populates="items")
    product = relationship(
        "Product",
        primaryjoin="and_(OrderItem.tenant_id == Product.tenant_id, OrderItem.sku == Product.sku)",
        foreign_keys="[OrderItem.tenant_id, OrderItem.sku]",
        back_populates="order_items",
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ['tenant_id', 'sku'],
            ['products.tenant_id', 'products.sku'],
            ondelete='RESTRICT',
        ),
    )

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(String(100), primary_key=True)
    tenant_id = Column(String(100), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey('orders.id'), nullable=False, index=True)
    status = Column(String(50), nullable=False)
    provider = Column(String(20), default='mercadopago')
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
    meta = Column(JSONType, default=dict)
    order = relationship("Order", back_populates="payments")

class IdempotencyKey(Base):
    __tablename__ = 'idempotency_keys'
    key = Column(String(255), primary_key=True)
    status = Column(String(20), nullable=False)
    response_json = Column(JSONType)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    completed_at = Column(DateTime)
    locked_until = Column(DateTime)
    expires_at = Column(DateTime, index=True)

class InventoryEvent(Base):
    __tablename__ = 'inventory_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(100), nullable=False)
    sku = Column(String(50), nullable=False, index=True)
    delta_on_hand = Column(Integer, nullable=False)
    delta_reserved = Column(Integer, default=0, nullable=False)
    reason = Column(String(100), nullable=False)
    source = Column(String(100), nullable=False)
    actor = Column(String(200))
    created_at = Column(DateTime, default=_utc_now, nullable=False, index=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ['tenant_id', 'sku'],
            ['products.tenant_id', 'products.sku'],
            ondelete='RESTRICT',
        ),
    )


class Lead(Base):
    """Stores leads created during handoff to human agents."""
    __tablename__ = 'leads'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(100), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    contact = Column(String(200), nullable=False)
    note = Column(String(1000), default="")
    source = Column(String(50), default="bot")
    created_at = Column(DateTime, default=_utc_now, nullable=False, index=True)
    __table_args__ = (Index('ix_tenant_lead_created', 'tenant_id', 'created_at'),)
