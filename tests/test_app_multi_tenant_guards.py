from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bot.core.database import Database
from app.db.models import Base, InventoryEvent, Lead, Order, OrderItem, OrderStatus, Product
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.stock_sheet_sync import StockSheetSync
from app.worker import jobs as worker_jobs


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


class _SessionProxy:
    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        return None


def _product(*, tenant_id: str, sku: str, model: str, qty: int, reserved: int = 0, price: int = 1000):
    return Product(
        tenant_id=tenant_id,
        sku=sku,
        model=model,
        category="Herramientas",
        price_ars=price,
        on_hand_qty=qty,
        reserved_qty=reserved,
        active=True,
        unit_of_measure="unidad",
        color="",
    )


def test_database_adapter_scopes_to_tenant_and_sets_tenant_on_writes(monkeypatch, db_session):
    monkeypatch.setattr("app.bot.core.database.ScopedSession", lambda: db_session)

    db_session.add_all(
        [
            _product(tenant_id="tenant-a", sku="SKU-1", model="Taladro A", qty=5, price=1500),
            _product(tenant_id="tenant-b", sku="SKU-1", model="Taladro B", qty=9, price=9900),
            _product(tenant_id="tenant-b", sku="SKU-2", model="Sierra B", qty=3, price=5000),
        ]
    )
    db_session.commit()

    db = Database(tenant_id="tenant-a")

    assert db.get_product_by_sku("SKU-1")["price_ars"] == 1500
    assert db.available_for_sku("SKU-1") == 5
    assert [item["sku"] for item in db.load_stock()] == ["SKU-1"]

    assert db.insert_product({"sku": "SKU-3", "model": "Amoladora", "stock": 4, "precio": 3200, "category": "Herramientas"})
    assert db_session.query(Product).filter_by(tenant_id="tenant-a", sku="SKU-3").one()
    assert db_session.query(Product).filter_by(tenant_id="tenant-b", sku="SKU-3").count() == 0

    hold = db.create_hold("SKU-1", name="Julian", contact="+5491111111111")
    assert hold is not None
    order = db_session.query(Order).filter_by(tenant_id="tenant-a", status=OrderStatus.HOLD).one()
    assert order.items[0].tenant_id == "tenant-a"

    lead_id = db.upsert_lead("Julian", "+5491111111111", "Necesita seguimiento")
    assert lead_id is not None
    assert db_session.query(Lead).filter_by(tenant_id="tenant-a", contact="+5491111111111").count() == 1


def test_order_service_finalize_order_scopes_by_order_tenant_and_logs_tenant_inventory_event(db_session):
    product_a = _product(tenant_id="tenant-a", sku="SKU-1", model="Taladro", qty=10, reserved=2, price=1500)
    product_b = _product(tenant_id="tenant-b", sku="SKU-1", model="Taladro", qty=50, reserved=7, price=9900)
    order = Order(
        tenant_id="tenant-a",
        user_id="user-1",
        status=OrderStatus.HOLD,
        user_name="Julian",
    )
    order.items.append(OrderItem(tenant_id="tenant-a", sku="SKU-1", quantity=2, price_at_purchase=1500))
    db_session.add_all([product_a, product_b, order])
    db_session.commit()

    OrderService.transition_status(db_session, order.id, OrderStatus.CONFIRMED)

    assert product_a.on_hand_qty == 8
    assert product_a.reserved_qty == 0
    assert product_b.on_hand_qty == 50
    assert product_b.reserved_qty == 7

    event = db_session.query(InventoryEvent).one()
    assert event.tenant_id == "tenant-a"
    assert event.sku == "SKU-1"
    assert order.updated_at.tzinfo is not None
    assert order.finalized_at.tzinfo is not None


def test_inventory_import_and_sheet_sync_only_touch_selected_tenant(monkeypatch, db_session):
    session_proxy = _SessionProxy(db_session)
    product_a = _product(tenant_id="tenant-a", sku="SKU-1", model="Taladro", qty=1, price=100)
    product_b = _product(tenant_id="tenant-b", sku="SKU-1", model="Taladro", qty=9, price=900)
    db_session.add_all([product_a, product_b])
    db_session.commit()

    monkeypatch.setattr("app.services.inventory_service.SessionLocal", lambda: session_proxy)
    InventoryService.import_stock_csv("SKU,OnHandQty,Price\nSKU-1,7,250\n", tenant_id="tenant-a")
    db_session.refresh(product_a)
    db_session.refresh(product_b)
    assert product_a.on_hand_qty == 7
    assert product_a.price_ars == 250
    assert product_b.on_hand_qty == 9
    assert product_b.price_ars == 900

    class _Worksheet:
        def get_all_records(self):
            return [
                {"sku": "SKU-1", "name": "Taladro Sync", "category": "Herramientas", "price_ars": "300", "stock": "8"},
                {"sku": "SKU-2", "name": "Sierra Sync", "category": "Herramientas", "price_ars": "450", "stock": "2"},
            ]

    class _Sheet:
        def worksheet(self, _name):
            return _Worksheet()

    class _Client:
        def open_by_key(self, _spreadsheet_id):
            return _Sheet()

    syncer = StockSheetSync.__new__(StockSheetSync)
    syncer.spreadsheet_id = "test-sheet"
    syncer.worksheet_name = "STOCK"
    syncer.tenant_id = "tenant-a"
    syncer.client = _Client()

    result = syncer.sync_to_database(db_session, tenant_id="tenant-a")
    assert result["status"] == "ok"

    db_session.refresh(product_a)
    db_session.refresh(product_b)
    assert product_a.model == "Taladro Sync"
    assert product_a.on_hand_qty == 8
    assert product_b.on_hand_qty == 9
    assert db_session.query(Product).filter_by(tenant_id="tenant-a", sku="SKU-2").count() == 1
    assert db_session.query(Product).filter_by(tenant_id="tenant-b", sku="SKU-2").count() == 0


def test_expire_holds_job_releases_reserved_stock_using_order_tenant(monkeypatch, db_session):
    session_proxy = _SessionProxy(db_session)
    product_a = _product(tenant_id="tenant-a", sku="SKU-1", model="Taladro", qty=5, reserved=2)
    product_b = _product(tenant_id="tenant-b", sku="SKU-1", model="Taladro", qty=8, reserved=4)
    order = Order(
        tenant_id="tenant-a",
        user_id="user-1",
        status=OrderStatus.HOLD,
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    order.items.append(OrderItem(tenant_id="tenant-a", sku="SKU-1", quantity=2, price_at_purchase=1000))
    db_session.add_all([product_a, product_b, order])
    db_session.commit()

    monkeypatch.setattr(worker_jobs, "SessionLocal", lambda: session_proxy)

    worker_jobs.expire_holds_job()

    db_session.refresh(order)
    db_session.refresh(product_a)
    db_session.refresh(product_b)
    assert order.status == OrderStatus.EXPIRED
    assert product_a.reserved_qty == 0
    assert product_b.reserved_qty == 4
    event = db_session.query(InventoryEvent).filter_by(reason="hold_expired", tenant_id="tenant-a").one()
    assert event.delta_reserved == -2
