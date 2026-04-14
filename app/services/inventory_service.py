
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Product
import csv
import io


settings = get_settings()


def _resolved_tenant_id(tenant_id: str | None = None) -> str:
    resolved = str(tenant_id or settings.DEFAULT_TENANT_ID or "").strip()
    if not resolved:
        raise ValueError("tenant_id is required for inventory imports")
    return resolved


class InventoryService:
    @staticmethod
    def import_stock_csv(content: str, tenant_id: str | None = None):
        resolved_tenant_id = _resolved_tenant_id(tenant_id)
        session = SessionLocal()
        try:
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                sku = row.get('SKU')
                qty = int(row.get('OnHandQty', 0))
                price = int(row.get('Price', 0))
                
                prod = session.query(Product).filter_by(tenant_id=resolved_tenant_id, sku=sku).first()
                if prod:
                    prod.on_hand_qty = qty
                    if price > 0: prod.price_ars = price
            session.commit()
        finally:
            session.close()
