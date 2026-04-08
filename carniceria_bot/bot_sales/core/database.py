#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database module - Extracted from demo_cli_offline.py
Handles all SQLite operations for stock, holds, sales, and leads
"""

import time
import sqlite3
import random
import logging
from typing import Dict, Any, List, Optional, Tuple
import csv
import os
import json
import re
from pathlib import Path


def now_ts() -> float:
    return time.time()


def iso_time(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or now_ts()))


class Database:
    """Database manager for iPhone store operations"""
    
    def __init__(self, db_file: str, catalog_csv: str, log_path: str):
        self.db_file = db_file
        self.catalog_csv = catalog_csv
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._init_db()
        
        # Setup logging
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s'
        )

    def log_event(self, event: str, data: Dict[str, Any] = None) -> None:
        """Log business events"""
        logging.info(f"{event} | {json.dumps(data or {}, ensure_ascii=False)}")

    def _init_db(self):
        """Initialize database schema and load catalog"""
        # Create tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock (
                sku TEXT PRIMARY KEY,
                category TEXT,
                model TEXT,
                storage_gb INTEGER,
                color TEXT,
                stock_qty INTEGER,
                price_ars INTEGER,
                currency TEXT DEFAULT 'ARS',
                attributes_json TEXT DEFAULT '{}'
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS holds (
                hold_id TEXT PRIMARY KEY,
                sku TEXT,
                name TEXT,
                contact TEXT,
                created_at REAL,
                expires_at REAL
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                sale_id TEXT PRIMARY KEY,
                sku TEXT,
                name TEXT,
                contact TEXT,
                zone TEXT,
                payment_method TEXT,
                confirmed_at REAL,
                hold_id TEXT
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT,
                contact TEXT,
                note TEXT,
                created_at REAL
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                email TEXT PRIMARY KEY,
                name TEXT,
                phone TEXT,
                total_spent INTEGER DEFAULT 0,
                purchase_count INTEGER DEFAULT 0,
                last_purchase_at REAL,
                created_at REAL
            )
        ''')
        
        self.conn.commit()

        self._ensure_stock_schema()
        
        # Load catalog from CSV if stock is empty
        if self.cursor.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 0:
            self._load_catalog_from_csv()

    def _ensure_stock_schema(self) -> None:
        """Ensure stock table has required columns for multi-industry catalogs."""
        columns = {
            row["name"]
            for row in self.cursor.execute("PRAGMA table_info(stock)").fetchall()
        }

        if "category" not in columns:
            from bot_sales.config import Config

            default_cat = Config.DEFAULT_CATEGORY
            if default_cat:
                self.cursor.execute(f"ALTER TABLE stock ADD COLUMN category TEXT DEFAULT '{default_cat}'")
            else:
                self.cursor.execute("ALTER TABLE stock ADD COLUMN category TEXT")

        if "currency" not in columns:
            self.cursor.execute("ALTER TABLE stock ADD COLUMN currency TEXT DEFAULT 'ARS'")

        if "attributes_json" not in columns:
            self.cursor.execute("ALTER TABLE stock ADD COLUMN attributes_json TEXT DEFAULT '{}'")

        self.conn.commit()

    @staticmethod
    def _parse_int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return default
        # Keep digits and minus for resilient CSV parsing.
        cleaned = "".join(ch for ch in text if ch.isdigit() or ch == "-")
        if not cleaned or cleaned == "-":
            return default
        try:
            return int(cleaned)
        except ValueError:
            return default

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.strip().lower().replace(" ", "").replace("_", "").replace("-", "")

    def _row_to_product(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Normalize stock row to compatibility shape plus flexible attributes."""
        if row is None:
            return {}

        attrs_raw = row["attributes_json"] if "attributes_json" in row.keys() else "{}"
        try:
            attributes = json.loads(attrs_raw) if attrs_raw else {}
            if not isinstance(attributes, dict):
                attributes = {}
        except Exception:
            attributes = {}

        product = {
            "sku": row["sku"],
            "category": row["category"],
            "model": row["model"],
            "name": row["model"],  # Compatibility alias for storefront/UI
            "storage_gb": row["storage_gb"] or 0,
            "color": row["color"] or "",
            "stock_qty": row["stock_qty"] or 0,
            "stock": row["stock_qty"] or 0,
            "price_ars": row["price_ars"] or 0,
            "price": row["price_ars"] or 0,
            "currency": row["currency"] or "ARS",
            "attributes_json": attrs_raw or "{}",
            "attributes": attributes,
        }

        # Expose extra attributes as top-level keys for backward-friendly consumers.
        for k, v in attributes.items():
            if k not in product:
                product[k] = v

        return product

    def _load_catalog_from_csv(self):
        """Load catalog from CSV file"""
        catalog_path = Path(self.catalog_csv)
        if not catalog_path.exists():
            fallback_candidates = [
                Path(__file__).resolve().parent.parent.parent / "config" / "catalog.csv",
                Path(__file__).resolve().parent.parent.parent / "data" / "tenants" / "default" / "catalog.csv",
            ]
            for candidate in fallback_candidates:
                if candidate.exists():
                    logging.warning("Catalog CSV not found at %s, using fallback %s", self.catalog_csv, candidate)
                    catalog_path = candidate
                    break

        if not catalog_path.exists():
            logging.warning(f"Catalog CSV not found: {self.catalog_csv}")
            logging.warning("No fallback data loaded. Please provide a catalog.csv file.")
            return

        with open(catalog_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            catalog_data = []
            for raw_row in reader:
                # Preserve original keys for attributes while enabling case-insensitive matching.
                clean_row = {
                    (k or "").strip(): (v.strip() if isinstance(v, str) else v)
                    for k, v in raw_row.items()
                }
                normalized = {
                    self._normalize_key(k): v
                    for k, v in clean_row.items()
                    if k
                }

                sku = normalized.get("sku") or normalized.get("id")
                if not sku:
                    continue

                category = normalized.get("category") or normalized.get("categoria") or ""
                model = (
                    normalized.get("model")
                    or normalized.get("name")
                    or normalized.get("producto")
                    or normalized.get("product")
                    or sku
                )
                storage_gb = self._parse_int(
                    normalized.get("storagegb")
                    or normalized.get("storage")
                    or normalized.get("capacitygb")
                    or normalized.get("capacidadgb")
                )
                color = normalized.get("color") or normalized.get("variant") or normalized.get("variante") or ""
                stock_qty = self._parse_int(
                    normalized.get("stockqty")
                    or normalized.get("stock")
                    or normalized.get("quantity")
                    or normalized.get("qty")
                )
                currency = (normalized.get("currency") or normalized.get("moneda") or "ARS").upper()
                price_ars = self._parse_int(
                    normalized.get("pricears")
                    or normalized.get("price")
                    or normalized.get("precio")
                    or normalized.get("priceusd")
                    or normalized.get("priceeur")
                    or normalized.get("pricemxn")
                    or normalized.get("pricebrl")
                )

                base_keys = {
                    "sku",
                    "id",
                    "category",
                    "categoria",
                    "model",
                    "name",
                    "producto",
                    "product",
                    "storagegb",
                    "storage",
                    "capacitygb",
                    "capacidadgb",
                    "color",
                    "variant",
                    "variante",
                    "stockqty",
                    "stock",
                    "quantity",
                    "qty",
                    "pricears",
                    "price",
                    "precio",
                    "priceusd",
                    "priceeur",
                    "pricemxn",
                    "pricebrl",
                    "currency",
                    "moneda",
                }

                attributes = {}
                for raw_key, raw_value in clean_row.items():
                    if not raw_key:
                        continue
                    norm_key = self._normalize_key(raw_key)
                    if norm_key in base_keys:
                        continue
                    if raw_value in ("", None):
                        continue
                    attributes[raw_key.strip().lower()] = raw_value

                catalog_data.append(
                    (
                        sku,
                        category,
                        model,
                        storage_gb,
                        color,
                        stock_qty,
                        price_ars,
                        currency,
                        json.dumps(attributes, ensure_ascii=False),
                    )
                )

            self.cursor.executemany(
                """
                INSERT OR REPLACE INTO stock
                (sku, category, model, storage_gb, color, stock_qty, price_ars, currency, attributes_json)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                catalog_data,
            )
            self.conn.commit()
            logging.info(f"Loaded {len(catalog_data)} products from catalog")

    def find_matches(
        self,
        model: Optional[str],
        storage_gb: Optional[int],
        color: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Find products matching criteria.

        Matching is flexible:
        - model query is tokenized and checked against model/category/color/attributes
        - optional storage_gb and color still act as strict filters when provided
        """
        rows = self.cursor.execute("SELECT * FROM stock").fetchall()
        products = [self._row_to_product(row) for row in rows]

        if model:
            tokens = [
                t for t in re.split(r"[^a-zA-Z0-9]+", model.lower())
                if len(t) >= 2
            ]
            if not tokens:
                tokens = [model.lower()]

            filtered = []
            for p in products:
                haystack = " ".join(
                    [
                        str(p.get("model", "")).lower(),
                        str(p.get("category", "")).lower(),
                        str(p.get("color", "")).lower(),
                        json.dumps(p.get("attributes", {}), ensure_ascii=False).lower(),
                    ]
                )
                if all(token in haystack for token in tokens) or any(token in haystack for token in tokens):
                    filtered.append(p)
            products = filtered

        if storage_gb is not None:
            products = [p for p in products if int(p.get("storage_gb", 0) or 0) == int(storage_gb)]

        if color:
            color_lower = color.lower()
            products = [p for p in products if color_lower in str(p.get("color", "")).lower()]

        return products

    def get_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Get product details by SKU"""
        row = self.cursor.execute(
            "SELECT * FROM stock WHERE sku = ?", (sku,)
        ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_product(row)

    def available_for_sku(self, sku: str) -> int:
        """Calculate available stock for a SKU (stock - active holds)"""
        self.cleanup_holds()
        
        stock = self.cursor.execute(
            "SELECT stock_qty FROM stock WHERE sku = ?", (sku,)
        ).fetchone()
        base = stock[0] if stock else 0
        
        reserved = self.cursor.execute(
            "SELECT COUNT(*) FROM holds WHERE sku = ?", (sku,)
        ).fetchone()[0]
        
        return max(0, base - reserved)

    def create_hold(
        self,
        sku: str,
        name: str,
        contact: str,
        hold_minutes: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Create a hold/reservation for a product"""
        if self.available_for_sku(sku) <= 0:
            return None
        
        hold_id = f"hold_{int(now_ts())}_{random.randint(1000,9999)}_{sku}"
        exp = now_ts() + hold_minutes * 60
        
        self.cursor.execute(
            "INSERT INTO holds VALUES (?,?,?,?,?,?)",
            (hold_id, sku, name, contact, now_ts(), exp)
        )
        self.conn.commit()
        
        self.log_event("HOLD_CREATED", {
            "hold_id": hold_id,
            "sku": sku,
            "name": name,
            "contact": contact
        })
        
        return {
            "hold_id": hold_id,
            "expires_in_minutes": hold_minutes,
            "expires_at": exp
        }

    def cleanup_holds(self) -> None:
        """Remove expired holds"""
        self.cursor.execute("DELETE FROM holds WHERE expires_at <= ?", (now_ts(),))
        self.conn.commit()

    def release_hold(self, hold_id: str) -> bool:
        """Manually release a hold"""
        self.cursor.execute("DELETE FROM holds WHERE hold_id = ?", (hold_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def confirm_sale(
        self,
        hold_id: str,
        zone: str,
        payment_method: str
    ) -> Tuple[bool, str]:
        """Confirm a sale from a hold"""
        hold = self.cursor.execute(
            "SELECT sku, name, contact FROM holds WHERE hold_id = ?",
            (hold_id,)
        ).fetchone()
        
        if not hold:
            return False, "Hold expirado o no encontrado."
        
        sku, name, contact = hold
        
        if self.available_for_sku(sku) <= 0:
            return False, "Sin stock físico disponible."
        
        sale_id = f"sale_{int(now_ts())}_{sku}_{random.randint(1000,9999)}"
        
        self.cursor.execute(
            "INSERT INTO sales VALUES (?,?,?,?,?,?,?,?)",
            (sale_id, sku, name, contact, zone, payment_method, now_ts(), hold_id)
        )
        self.cursor.execute(
            "UPDATE stock SET stock_qty = stock_qty - 1 WHERE sku = ?",
            (sku,)
        )
        self.cursor.execute(
            "DELETE FROM holds WHERE hold_id = ?",
            (hold_id,)
        )
        self.conn.commit()
        
        self.log_event("SALE_CONFIRMED", {
            "sale_id": sale_id,
            "sku": sku,
            "name": name,
            "zone": zone,
            "payment": payment_method
        })
        
        return True, sale_id

    def upsert_lead(self, name: str, contact: str, note: str = "") -> str:
        """Create or update a lead (for handoff scenarios)"""
        lid = f"lead_{int(now_ts())}_{random.randint(1000,9999)}"
        self.cursor.execute(
            "INSERT INTO leads VALUES (?,?,?,?,?)",
            (lid, name, contact, note, now_ts())
        )
        self.conn.commit()
        
        self.log_event("LEAD_CREATED", {
            "lead_id": lid,
            "name": name,
            "contact": contact,
            "note": note
        })
        
        return lid

    def upsert_customer(self, email: str, name: str, phone: str = None, amount_spent: int = 0) -> None:
        """Update or create customer profile foundation for retention"""
        if not email or "@" not in email:
            return

        row = self.cursor.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        
        if row:
            # Update existing
            self.cursor.execute("""
                UPDATE customers 
                SET total_spent = total_spent + ?,
                    purchase_count = purchase_count + 1,
                    last_purchase_at = ?,
                    name = COALESCE(?, name),
                    phone = COALESCE(?, phone)
                WHERE email = ?
            """, (amount_spent, now_ts(), name, phone, email))
        else:
            # Create new
            self.cursor.execute("""
                INSERT INTO customers (email, name, phone, total_spent, purchase_count, last_purchase_at, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (email, name, phone, amount_spent, now_ts(), now_ts()))
            
        self.conn.commit()

    def load_stock(self) -> List[Dict[str, Any]]:
        """Load all stock items"""
        return [self._row_to_product(row) for row in self.cursor.execute("SELECT * FROM stock")]
    
    def get_all_products(self) -> List[Dict[str, Any]]:
        """Alias for load_stock (compatibility)"""
        return self.load_stock()
    
    def find_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Find all products in a category"""
        sql = "SELECT * FROM stock WHERE category = ?"
        return [self._row_to_product(row) for row in self.cursor.execute(sql, (category,)).fetchall()]
    
    def get_all_categories(self) -> List[str]:
        """Get list of all unique categories"""
        return [
            row[0] for row in
            self.cursor.execute("SELECT DISTINCT category FROM stock ORDER BY category").fetchall()
        ]

    def get_all_models(self) -> List[str]:
        """Get list of all unique models"""
        return [
            row[0] for row in
            self.cursor.execute("SELECT DISTINCT model FROM stock ORDER BY model").fetchall()
        ]

    def get_all_colors(self) -> List[str]:
        """Get list of all unique colors"""
        return [
            row[0] for row in
            self.cursor.execute("SELECT DISTINCT color FROM stock ORDER BY color").fetchall()
        ]
    
    def get_unique_categories(self) -> List[str]:
        """Get list of unique product categories (alias for get_all_categories)."""
        return self.get_all_categories()

    def close(self):
        """Close database connection"""
        self.conn.close()
