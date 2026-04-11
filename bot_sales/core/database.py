#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database module
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
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts or now_ts()))


class Database:
    """Database manager for multi-industry catalog operations."""

    def __init__(self, db_file: str, catalog_csv: str, log_path: str, api_key: str = ""):
        self.db_file = db_file
        self.catalog_csv = catalog_csv
        # timeout=30 means concurrent threads wait up to 30s instead of raising 'database is locked'
        self.conn = sqlite3.connect(db_file, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        # WAL mode allows concurrent reads while a write is in progress (vs. default exclusive lock)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.commit()
        self.cursor = self.conn.cursor()
        self._init_db()

        # Setup logging
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s'
        )

        # Vector search engine uses an isolated connection so request traffic
        # never shares transactional state with background indexing.
        effective_key = (api_key or "").strip()
        from bot_sales.core.vector_search import VectorSearchEngine
        self._vector = VectorSearchEngine(db_file, api_key=effective_key)
        if effective_key:
            products = [self._row_to_product(row)
                        for row in self.conn.execute("SELECT * FROM stock").fetchall()]
            self._vector.start_indexing(products)

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
                proveedor TEXT DEFAULT '',
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

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                session_id TEXT NOT NULL,
                tenant_id  TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '[]',
                session_state_json TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL,
                PRIMARY KEY (session_id, tenant_id)
            )
        ''')

        # Indexes for query performance
        self.cursor.executescript('''
            CREATE INDEX IF NOT EXISTS idx_stock_category      ON stock(category);
            CREATE INDEX IF NOT EXISTS idx_holds_expires       ON holds(expires_at);
            CREATE INDEX IF NOT EXISTS idx_holds_sku           ON holds(sku);
            CREATE INDEX IF NOT EXISTS idx_holds_contact       ON holds(contact);
            CREATE INDEX IF NOT EXISTS idx_sales_contact       ON sales(contact);
            CREATE INDEX IF NOT EXISTS idx_sales_sku           ON sales(sku);
            CREATE INDEX IF NOT EXISTS idx_sales_ts            ON sales(confirmed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_customers_email     ON customers(email);
            CREATE INDEX IF NOT EXISTS idx_leads_created       ON leads(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated    ON conversation_sessions(updated_at DESC);
        ''')

        self.conn.commit()

        self._ensure_stock_schema()
        
        # Always replace on boot so stock_qty reflects the latest CSV values.
        # INSERT OR REPLACE overwrites existing rows; new SKUs are inserted fresh.
        self._load_catalog_from_csv(replace_existing=True)

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
                # Validate to prevent SQL injection: only allow word chars, spaces and hyphens
                if not re.match(r'^[\w\s\-]+$', default_cat):
                    raise ValueError(
                        f"DEFAULT_CATEGORY contiene caracteres inválidos: {default_cat!r}"
                    )
                safe_default = default_cat.replace("'", "''")
                self.cursor.execute(
                    f"ALTER TABLE stock ADD COLUMN category TEXT DEFAULT '{safe_default}'"
                )
            else:
                self.cursor.execute("ALTER TABLE stock ADD COLUMN category TEXT")

        if "currency" not in columns:
            self.cursor.execute("ALTER TABLE stock ADD COLUMN currency TEXT DEFAULT 'ARS'")

        if "attributes_json" not in columns:
            self.cursor.execute("ALTER TABLE stock ADD COLUMN attributes_json TEXT DEFAULT '{}'")

        if "proveedor" not in columns:
            self.cursor.execute("ALTER TABLE stock ADD COLUMN proveedor TEXT DEFAULT ''")

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

        keys = row.keys() if hasattr(row, "keys") else []
        product = {
            "sku": row["sku"],
            "category": row["category"],
            "model": row["model"],
            "name": row["model"],  # Compatibility alias for storefront/UI
            "storage_gb": row["storage_gb"] or 0,
            "color": row["color"] or "",
            "proveedor": (row["proveedor"] if "proveedor" in keys else "") or "",
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

    def _load_catalog_from_csv(self, replace_existing: bool = True):
        """Load catalog from CSV file, optionally preserving existing SKUs."""
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
                    or normalized.get("descripcion")
                    or normalized.get("description")
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
                proveedor = normalized.get("proveedor") or normalized.get("provider") or normalized.get("supplier") or ""
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
                    "descripcion",
                    "description",
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
                    "proveedor",
                    "provider",
                    "supplier",
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
                        proveedor,
                        stock_qty,
                        price_ars,
                        currency,
                        json.dumps(attributes, ensure_ascii=False),
                    )
                )

            insert_mode = "INSERT OR REPLACE" if replace_existing else "INSERT OR IGNORE"
            self.cursor.executemany(
                insert_mode +
                """
                INTO stock
                (sku, category, model, storage_gb, color, proveedor, stock_qty, price_ars, currency, attributes_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                catalog_data,
            )
            self.conn.commit()
            action = "Loaded" if replace_existing else "Merged missing"
            logging.info("%s %s products from catalog", action, len(catalog_data))

    def find_matches(
        self,
        model: Optional[str],
        storage_gb: Optional[int] = None,
        color: Optional[str] = None,
        categoria: Optional[str] = None,
        proveedor: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find products matching criteria.

        Matching is flexible:
        - model query is tokenized and checked against model/category/proveedor/attributes
        - optional categoria and proveedor act as strict filters when provided
        """
        rows = self.cursor.execute("SELECT * FROM stock").fetchall()
        products = [self._row_to_product(row) for row in rows]

        if model:
            tokens = [
                t for t in re.split(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+", model.lower())
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
                        str(p.get("proveedor", "")).lower(),
                        json.dumps(p.get("attributes", {}), ensure_ascii=False).lower(),
                    ]
                )
                if all(token in haystack for token in tokens) or any(token in haystack for token in tokens):
                    filtered.append(p)
            products = filtered

        products = [
            p
            for p in products
            if self._matches_variant_filters(
                p,
                storage_gb=storage_gb,
                color=color,
                categoria=categoria,
                proveedor=proveedor,
            )
        ]

        return products

    def find_matches_hybrid(
        self,
        model: Optional[str],
        storage_gb: Optional[int] = None,
        color: Optional[str] = None,
        categoria: Optional[str] = None,
        proveedor: Optional[str] = None,
        vector_top_k: int = 20,
        keyword_threshold: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: keyword-first, vector-augmented.

        Logic:
          1. Run keyword search (existing find_matches).
          2. If keyword results >= keyword_threshold → return them (fast path).
          3. Otherwise run vector search and merge results, keyword results
             get priority (appear first), vector fills remaining slots.
        """
        keyword_results = self.find_matches(model, storage_gb, color, categoria, proveedor)

        # Fast path: keyword search found enough candidates
        if len(keyword_results) >= keyword_threshold:
            return keyword_results

        # Slow path: augment with vector search
        if not model or not self._vector.is_ready:
            return keyword_results

        try:
            vector_hits = self._vector.search(model, top_k=vector_top_k)
            if not vector_hits:
                return keyword_results

            # Keyword SKUs for dedup
            keyword_skus = {p["sku"] for p in keyword_results}
            candidate_skus = [sku for sku, _score in vector_hits if sku not in keyword_skus]
            if not candidate_skus:
                return keyword_results

            sku_map = self._fetch_products_by_skus(candidate_skus)

            # Preserve the same strict filters used in the keyword path.
            extra = []
            for sku, score in vector_hits:
                if sku in keyword_skus:
                    continue
                p = sku_map.get(sku)
                if p is None:
                    continue
                if not self._matches_variant_filters(
                    p,
                    storage_gb=storage_gb,
                    color=color,
                    categoria=categoria,
                    proveedor=proveedor,
                ):
                    continue
                p["_vector_score"] = score
                extra.append(p)

            return keyword_results + extra

        except Exception as exc:
            logging.warning("hybrid_search_vector_failed: %s", exc)
            return keyword_results

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

    def cleanup_holds(self) -> int:
        """Remove expired holds. Returns count of deleted rows."""
        self.cursor.execute("DELETE FROM holds WHERE expires_at <= ?", (now_ts(),))
        self.conn.commit()
        return self.cursor.rowcount

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

    def load_session(self, session_id: str, tenant_id: str) -> tuple:
        """Load persistent conversation context and session state.

        Returns:
            (context: list, session_state: dict) — both empty if not found.
        """
        row = self.cursor.execute(
            "SELECT context_json, session_state_json FROM conversation_sessions "
            "WHERE session_id = ? AND tenant_id = ?",
            (session_id, tenant_id),
        ).fetchone()
        if not row:
            return [], {}
        try:
            context = json.loads(row["context_json"] or "[]")
            state = json.loads(row["session_state_json"] or "{}")
        except Exception:
            context, state = [], {}
        return context, state

    def save_session(
        self,
        session_id: str,
        tenant_id: str,
        context: list,
        session_state: dict,
    ) -> None:
        """Upsert conversation context and session state."""
        self.cursor.execute(
            """
            INSERT INTO conversation_sessions
                (session_id, tenant_id, context_json, session_state_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, tenant_id) DO UPDATE SET
                context_json       = excluded.context_json,
                session_state_json = excluded.session_state_json,
                updated_at         = excluded.updated_at
            """,
            (
                session_id,
                tenant_id,
                json.dumps(context, ensure_ascii=False),
                json.dumps(session_state, ensure_ascii=False),
                now_ts(),
            ),
        )
        self.conn.commit()

    def delete_session(self, session_id: str, tenant_id: str) -> None:
        """Remove a session (reset or after sale)."""
        self.cursor.execute(
            "DELETE FROM conversation_sessions WHERE session_id = ? AND tenant_id = ?",
            (session_id, tenant_id),
        )
        self.conn.commit()

    def close(self):
        """Close database connection"""
        if hasattr(self, "_vector") and self._vector:
            self._vector.close()
        self.conn.close()

    def _matches_variant_filters(
        self,
        product: Dict[str, Any],
        *,
        storage_gb: Optional[int] = None,
        color: Optional[str] = None,
        categoria: Optional[str] = None,
        proveedor: Optional[str] = None,
    ) -> bool:
        if storage_gb is not None:
            try:
                expected_storage = int(storage_gb)
            except (TypeError, ValueError):
                expected_storage = storage_gb
            actual_storage = self._parse_int(product.get("storage_gb"))
            if actual_storage != expected_storage:
                return False

        if color:
            color_lower = str(color).strip().lower()
            color_haystack = " ".join(
                [
                    str(product.get("color", "")).lower(),
                    json.dumps(product.get("attributes", {}), ensure_ascii=False).lower(),
                ]
            )
            if color_lower not in color_haystack:
                return False

        if categoria:
            cat_lower = str(categoria).strip().lower()
            if cat_lower not in str(product.get("category", "")).lower():
                return False

        if proveedor:
            prov_lower = str(proveedor).strip().lower()
            if prov_lower not in str(product.get("proveedor", "")).lower():
                return False

        return True

    def _fetch_products_by_skus(self, skus: List[str]) -> Dict[str, Dict[str, Any]]:
        if not skus:
            return {}
        placeholders = ",".join("?" for _ in skus)
        rows = self.conn.execute(
            f"SELECT * FROM stock WHERE sku IN ({placeholders})",
            tuple(skus),
        ).fetchall()
        return {row["sku"]: self._row_to_product(row) for row in rows}
