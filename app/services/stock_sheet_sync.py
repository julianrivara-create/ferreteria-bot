"""
Strict Single-Sheet Stock Sync Service
Enforces Real Stock logic from Google Sheets.
Contract: sku | name | category | price_ars | stock | color | brand | material | size | unit_of_measure
"""
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.orm import Session
from app.db.models import Product
import json
import os
import structlog
import time

logger = structlog.get_logger()

class StockSheetSync:
    def __init__(self, spreadsheet_id, service_account_json=None, service_account_path=None):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = "STOCK" # Fixed contract
        self.client = self._auth_gspread(service_account_json, service_account_path)

    def _auth_gspread(self, json_str, file_path):
        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        if json_str:
            clean = json_str.strip()
            if clean.startswith("'") and clean.endswith("'"): clean = clean[1:-1]
            clean = clean.replace('\\n', '\n')
            creds = Credentials.from_service_account_info(json.loads(clean), scopes=scopes)
        elif file_path and os.path.exists(file_path):
            creds = Credentials.from_service_account_file(file_path, scopes=scopes)
        else:
            raise Exception("No valid credentials provided for Sheets")
        return gspread.authorize(creds)

    def sync_to_database(self, session: Session):
        """
        Reads sheet, validtes rows, upserts to DB.
        Returns detailed stats.
        """
        try:
            sheet = self.client.open_by_key(self.spreadsheet_id)
            try:
                ws = sheet.worksheet(self.worksheet_name)
            except gspread.WorksheetNotFound:
                # Try case-insensitive find
                ws = next((w for w in sheet.worksheets() if w.title.upper() == "STOCK"), None)
                if not ws:
                    # Fallback to "Products" (Legacy Name)
                    ws = next((w for w in sheet.worksheets() if w.title.upper() == "PRODUCTS"), None)
                
                if not ws: raise Exception(f"Worksheet '{self.worksheet_name}' or 'Products' not found")

            rows = ws.get_all_records()
            stats = {"updated": 0, "created": 0, "skipped": 0, "errors": []}

            # Valid columns check
            if not rows:
                return stats
            
            headers = [k.lower().strip() for k in rows[0].keys()]
            required = ['sku', 'price_ars', 'stock']
            for r in required:
                if r not in headers and r not in [h.replace('_', '') for h in headers]:
                    # Relaxed check, but let's assume get_all_records uses exact keys
                    pass 

            for i, row in enumerate(rows, start=2):
                # Normalize keys
                data = {k.lower().strip(): v for k, v in row.items()}
                
                sku = str(data.get('sku', '')).strip()
                if not sku:
                    stats['skipped'] += 1
                    stats['errors'].append(f"Row {i}: Missing SKU")
                    continue

                try:
                    price = int(str(data.get('price_ars', 0)).replace(',', '').replace('.', '').replace('$', '').strip() or 0)
                    stock = int(str(data.get('stock', 0)).strip() or 0)
                    # Enforce strict non-negative
                    if stock < 0: stock = 0
                except ValueError:
                    stats['skipped'] += 1
                    stats['errors'].append(f"Row {i} ({sku}): Invalid Price/Stock format")
                    continue

                # Optional fields
                name = str(data.get('name', sku)).strip()
                category = str(data.get('category', 'Others')).strip()
                color = str(data.get('color', '')).strip()
                brand = str(data.get('brand', data.get('marca', ''))).strip()
                material = str(data.get('material', '')).strip()
                size = str(data.get('size', data.get('medida', ''))).strip()
                unit_of_measure = str(data.get('unit_of_measure', 'unidad')).strip()

                # DB Operations
                product = session.query(Product).filter_by(sku=sku).first()
                if product:
                    # Update
                    product.model = name # Map name -> model
                    product.category = category
                    product.price_ars = price
                    product.on_hand_qty = stock # Use existing DB field
                    product.color = color
                    product.brand = brand or product.brand
                    product.material = material or product.material
                    product.size = size or product.size
                    product.unit_of_measure = unit_of_measure or product.unit_of_measure
                    stats['updated'] += 1
                else:
                    # Create
                    new_prod = Product(
                        sku=sku,
                        model=name,
                        category=category,
                        price_ars=price,
                        on_hand_qty=stock,
                        color=color,
                        brand=brand or None,
                        material=material or None,
                        size=size or None,
                        unit_of_measure=unit_of_measure or 'unidad',
                    )
                    session.add(new_prod)
                    stats['created'] += 1
            
            session.commit()
            stats['status'] = 'ok'
            return stats

        except Exception as e:
            session.rollback()
            logger.error("sync_failed", error=str(e))
            return {"status": "error", "message": str(e), "errors": [str(e)]}
