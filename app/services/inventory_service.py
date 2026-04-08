
from app.db.session import SessionLocal
from app.db.models import Product
import csv
import io

class InventoryService:
    @staticmethod
    def import_stock_csv(content: str):
        session = SessionLocal()
        try:
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                sku = row.get('SKU')
                qty = int(row.get('OnHandQty', 0))
                price = int(row.get('Price', 0))
                
                prod = session.query(Product).filter_by(sku=sku).first()
                if prod:
                    prod.on_hand_qty = qty
                    if price > 0: prod.price_ars = price
            session.commit()
        finally:
            session.close()
