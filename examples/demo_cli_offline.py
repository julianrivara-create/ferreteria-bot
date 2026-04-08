#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🚀 iPHONE BOT - UTOPIA EDITION (V13 FINAL)
------------------------------------------------
✅ CSV Catalog Loading (62 products)
✅ Improved Policies (detailed, helpful)
✅ Alternatives on No Match  
✅ Auto-Advance Through States
✅ Progress Feedback
"""

import os
import re
import csv
import json
import time
import logging
import sqlite3
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from difflib import get_close_matches
import shlex

# -----------------------------
# Config / Settings
# -----------------------------

DB_FILE = "data/ferreteria.db"
LOG_PATH = "events.log"
TRANSCRIPT_PATH = "transcript.txt"
ADMIN_PASS = "admin"
HOLD_MINUTES = 30
DEMO_TICK_SECONDS = 0.5
FUZZY_CUTOFF = 0.70

class C:
    BOT = '\033[92m'      # Verde (changed from blue)
    USER = '\033[0m'      # Blanco
    SUCCESS = '\033[92m'  # Verde
    ALERT = '\033[93m'    # Amarillo
    GREY = '\033[90m'     # Gris
    END = '\033[0m'
    BOLD = '\033[1m'

# -----------------------------
# Frases Mejoradas
# -----------------------------

PHRASES = {
    "greet": ["¡Buenas! 👋 ¿Qué Herramienta estás buscando hoy?", "Hola, ¿en qué modelo estabas pensando?", "¡Hola! Decime qué buscás y me fijo el stock."],
    "ask_variant": ["Genial, ¿qué modelo exacto? (ej: Amoladora 115mm Pro 256GB Negro)", "Dale, decime modelo + GB + color para chequear stock."],
    "no_match": ["Uhh, no encontré esa variante exacta 😓. ¿Probamos con algo similar?", "Mala mía, no lo tengo cargado. ¿Otro color o capacidad?"],
    "no_stock": ["Uhh, justo esa combinación se me agotó 😓.", "Te pido disculpas, ese voló y no me quedó stock."],
    "stock_info": ["¡Sí! Tengo {avail} disponible(s) del {model} {gb}GB {color} a {price}.", "Perfecto, stock confirmado: {avail} unidad(es) a {price}."],
    "ask_name": ["Buena pick. ¿Cómo te agendo para la reserva?", "¡Dale! ¿Tu nombre?"],
    "ask_contact": ["Genial {name}. Ahora pasame WhatsApp o email.", "Dale {name}, necesito un contacto."],
    "ask_zone": ["Un gusto {name}. ¿Para qué zona sería? (CABA, AMBA, Interior)", "Anotado. ¿Envío a CABA/AMBA o Interior?"],
    "ask_payment": ["Llegamos a {zone}. ¿Cómo pagás? (Transferencia/Efectivo/MercadoPago)", "¿Preferís transferencia o MercadoPago?"],
    "hold_created": ["¡Listo ✅! Reservado por {minutes} min.", "Te lo guardé a tu nombre {name}. Expira en {minutes} min."],
    "sale_confirmed": ["🎉 ¡Venta confirmada! Gracias {name}. Te contacto ya para entrega.", "¡Cerramos! Total: {price} (Pago: {payment}). Envío a {zone}."],
    "handoff": ["Mmm, para {reason} mejor hablá con un asesor. Pasame contacto y te deriva.", "Tema sensible ({reason}), lo vemos con humano. ¿WhatsApp?"],
    "correct": ["Ok, corregimos. ¿Qué cambiamos (modelo/GB/color)?", "Entendido, volvamos atrás. Decime de nuevo."],
    # Policies Mejoradas
    "policies_shipping": [
        "🚚 Sí, hacemos envíos!\n• CABA/AMBA: Moto 24-48hs (sin cargo en CABA, consultar AMBA)\n• Interior: Andreani (3-5 días, costo según destino)\nNo manejamos horarios exactos, solo rangos. ¿A dónde lo necesitás?",
        "📦 Envíos:\n• CABA: Gratis, 24-48hs\n• GBA: $X (consultar), 48-72hs\n• Interior: Correo/Andreani, 3-5 días\n¿Cuál es tu zona?"
    ],
    "policies_payments": [
        "💳 Formas de pago:\n• Transferencia/Efectivo: Posible descuento (te confirmo)\n• MercadoPago: Aceptamos\n• Tarjeta: Según plan vigente (te informo recargo antes)\n¿Con cuál preferís?",
        "💰 Pagos: Transferencia (mejor precio), efectivo, MercadoPago, o tarjeta con cuotas. ¿Cuál te va mejor?"
    ],
    "policies_installments": [
        "📊 Cuotas disponibles según el plan del momento. Te confirmo recargo antes de cerrar. ¿Cuántas cuotas necesitarías?"
    ],
    "policies_warranty": [
        "🛡️ Garantía:\n• Apple oficial: 1 año\n• Nuestra garantía: +3 meses adicionales\n• Cualquier tema de postventa lo maneja un asesor directamente.\n¿Tenés alguna duda específica?"
    ],
    "policies_returns": [
        "🔄 Cambios y devoluciones dependen del estado del equipo y días desde la compra. Para coordinar, necesito que hables con un asesor. ¿Pasame tu contacto?"
    ],
}

# Intents para policies
INTENTS = {
    "catalog": ["qué modelos", "que modelos", "modelos", "qué tenés", "que tenes", "tenés", "tenes", "lista", "disponibles", "opciones", "alternativas", "variantes", "qué tenes en stock", "que hay", "mostrame"],
    "shipping": ["envío", "envio", "entrega", "mandás", "mandas", "mandan", "envían", "envian", "hacés envío", "hacen envío", "llega", "delivery", "a domicilio"],
    "payments": ["pago", "transfer", "mercadopago", "mp", "efectivo", "tarjeta", "aceptan", "formas de pago"],
    "installments": ["cuotas", "en cuotas", "sin interes", "sin interés", "financiación", "plan"],
    "warranty": ["garantía", "garantia", "falla", "defecto", "cobertura", "postventa"],
    "returns": ["devol", "devolución", "devolver", "reembolso", "me arrepentí", "me arrepenti", "no me gusta", "no me gustó"],
    "sensitive": ["urgente", "factura", "empresa", "descuento especial", "negociar", "precio especial", "mayorista"],
    "human": ["humano", "persona", "asesor", "atención", "hablar con alguien"],
    "pickup": ["retiro", "retirar", "buscar", "pasar a buscar", "voy a buscar", "lo paso a buscar"],
    "cancel": ["cancelar", "cancela", "no", "otros modelos", "otro modelo", "mejor otro", "cambiar", "reset"],
}

# -----------------------------
# Utils & DB
# -----------------------------

def now_ts() -> float: return time.time()
def iso_time(ts: Optional[float] = None) -> str: return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or now_ts()))

def format_money_ars(v: int) -> str:
    if v <= 0: return "A confirmar"
    return "$" + f"{v:,}".replace(",", ".")

def normalize_spaces(s: str) -> str: return re.sub(r"\s+", " ", s).strip()

def contains_any(text: str, parts: List[str]) -> bool:
    """Check if any pattern matches (supports regex)"""
    for p in parts:
        if p.startswith(r"\b"):  # regex pattern
            if re.search(p, text, re.IGNORECASE):
                return True
        elif p.lower() in text.lower():
            return True
    return False

def append_transcript(role: str, text: str) -> None:
    with open(TRANSCRIPT_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{iso_time()}] {role}: {text}\n")

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self._init_db()
        logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

    def log_event(self, event: str, data: Dict[str, Any] = None) -> None:
        logging.info(f"{event} | {json.dumps(data or {}, ensure_ascii=False)}")

    def _init_db(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS stock (sku TEXT PRIMARY KEY, model TEXT, storage_gb INTEGER, color TEXT, stock_qty INTEGER, price_ars INTEGER)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS holds (hold_id TEXT PRIMARY KEY, sku TEXT, name TEXT, contact TEXT, created_at REAL, expires_at REAL)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sales (sale_id TEXT PRIMARY KEY, sku TEXT, name TEXT, contact TEXT, zone TEXT, payment_method TEXT, confirmed_at REAL, hold_id TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS leads (lead_id TEXT PRIMARY KEY, name TEXT, contact TEXT, note TEXT, created_at REAL)''')
        self.conn.commit()
        
        # CSV LOADING (Feature #1)
        if self.cursor.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 0:
            import os
            catalog_file = "catalog.csv"
            if os.path.exists(catalog_file):
                # Load from CSV
                with open(catalog_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    catalog_data = []
                    for row in reader:
                        catalog_data.append((
                            row['SKU'],
                            row['Model'],
                            int(row['StorageGB']),
                            row['Color'],
                            int(row['StockQty']),
                            int(row['PriceARS'])
                        ))
                    self.cursor.executemany("INSERT INTO stock VALUES (?,?,?,?,?,?)", catalog_data)
                    self.conn.commit()
            else:
                # Fallback to hardcoded if no CSV
                data = [
                    ("IP15-128-BLK", "Taladro Percutor 13mm", 128, "Black", 3, 1200),
                    ("IP15-256-BLU", "Taladro Percutor 13mm", 256, "Blue", 1, 1400),
                    ("IP15P-128-NAT", "Taladro Percutor 13mm Pro", 128, "Natural Titanium", 2, 1600),
                    ("IP15P-256-NAT", "Taladro Percutor 13mm Pro", 256, "Natural Titanium", 2, 1800),
                    ("IP15PM-256-BLK", "Taladro Percutor 13mm Pro Max", 256, "Black Titanium", 1, 2000),
                ]
                self.cursor.executemany("INSERT INTO stock VALUES (?,?,?,?,?,?)", data)
                self.conn.commit()

    def find_matches(self, model: Optional[str], storage_gb: Optional[int], color: Optional[str]) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM stock WHERE 1=1"
        params = []
        if model:
            sql += " AND model LIKE ?"
            params.append(f"%{model}%")
        if storage_gb:
            sql += " AND storage_gb = ?"
            params.append(storage_gb)
        if color:
            sql += " AND color LIKE ?"
            params.append(f"%{color}%")
        return [dict(zip(["sku", "model", "storage_gb", "color", "stock_qty", "price_ars"], row))
                for row in self.cursor.execute(sql, params).fetchall()]

    def available_for_sku(self, sku: str) -> int:
        self.cleanup_holds()
        stock = self.cursor.execute("SELECT stock_qty FROM stock WHERE sku = ?", (sku,)).fetchone()
        base = stock[0] if stock else 0
        reserved = self.cursor.execute("SELECT COUNT(*) FROM holds WHERE sku = ?", (sku,)).fetchone()[0]
        return max(0, base - reserved)

    def create_hold(self, sku: str, name: str, contact: str) -> Dict[str, Any]:
        if self.available_for_sku(sku) <= 0: return None
        hold_id = f"hold_{int(now_ts())}_{random.randint(1000,9999)}_{sku}"
        exp = now_ts() + HOLD_MINUTES * 60
        self.cursor.execute("INSERT INTO holds VALUES (?,?,?,?,?,?)", (hold_id, sku, name, contact, now_ts(), exp))
        self.conn.commit()
        return {"hold_id": hold_id, "expires_in_minutes": HOLD_MINUTES}

    def cleanup_holds(self) -> None:
        self.cursor.execute("DELETE FROM holds WHERE expires_at <= ?", (now_ts(),))
        self.conn.commit()

    def release_hold(self, hold_id: str) -> bool:
        self.cursor.execute("DELETE FROM holds WHERE hold_id = ?", (hold_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def confirm_sale(self, hold_id: str, zone: str, payment_method: str) -> Tuple[bool, str]:
        hold = self.cursor.execute("SELECT sku, name, contact FROM holds WHERE hold_id = ?", (hold_id,)).fetchone()
        if not hold: return False, "Hold expirado."
        sku, name, contact = hold
        if self.available_for_sku(sku) <= 0: return False, "Sin stock físico."
        sale_id = f"sale_{int(now_ts())}_{sku}"
        self.cursor.execute("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?)", (sale_id, sku, name, contact, zone, payment_method, now_ts(), hold_id))
        self.cursor.execute("UPDATE stock SET stock_qty = stock_qty - 1 WHERE sku = ?", (sku,))
        self.cursor.execute("DELETE FROM holds WHERE hold_id = ?", (hold_id,))
        self.conn.commit()
        return True, sale_id

    def upsert_lead(self, name: str, contact: str, note: str = "") -> str:
        lid = f"lead_{int(now_ts())}_{random.randint(1000,9999)}"
        self.cursor.execute("INSERT INTO leads VALUES (?,?,?,?,?)", (lid, name, contact, note, now_ts()))
        self.conn.commit()
        return lid

    def load_stock(self):
        return [dict(zip(["sku", "model", "storage_gb", "color", "stock_qty", "price_ars"], row)) for row in self.cursor.execute("SELECT * FROM stock")]

# -----------------------------
# Parsing
# -----------------------------

COLOR_ALIASES = {
    "negro": "Black", "black": "Black", "negr": "Black", "nwgro": "Black",
    "azul": "Blue", "blue": "Blue", "azúl": "Blue", "azu": "Blue",
    "rosa": "Pink", "pink": "Pink", "rosado": "Pink",
    "blanco": "White", "white": "White", "blanc": "White",
    "natural": "Natural Titanium", "titanio": "Natural Titanium", "titan": "Natural Titanium",
    "oro": "Gold", "gold": "Gold", "dorado": "Gold",
    "desert": "Desert Titanium", "desierto": "Desert Titanium"
}

def extract_model(text: str, known_models: List[str]) -> Optional[str]:
    t = normalize_spaces(text.lower())
    patterns = [
        (re.compile(r"\b(\d+)\s*pro\s*max\b", re.I), lambda m: f"Herramienta {m.group(1)} Pro Max"),
        (re.compile(r"\b(\d+)\s*promax\b", re.I), lambda m: f"Herramienta {m.group(1)} Pro Max"),
        (re.compile(r"\b(\d+)\s*pro\b", re.I), lambda m: f"Herramienta {m.group(1)} Pro"),
        (re.compile(r"\btaladro\s*(\d+)\b", re.I), lambda m: f"Herramienta {m.group(1)}"),
        (re.compile(r"\b(\d{2})\b", re.I), lambda m: f"Herramienta {m.group(1)}"),
    ]
    for rx, fn in patterns:
        m = rx.search(t)
        if m:
            candidate = fn(m)
            match = get_close_matches(candidate.lower(), [km.lower() for km in known_models], n=1, cutoff=FUZZY_CUTOFF)
            return match[0] if match else candidate
    return None

def extract_storage_gb(text: str) -> Optional[int]:
    t = normalize_spaces(text.lower())
    # Fuzzy matching for typos
    typo_map = {126: 128, 127: 128, 254: 256, 255: 256, 510: 512}
    
    if re.search(r"\b1\s*tb\b|\b1024\b", t):
        return 1024
    m = re.search(r"\b(64|128|256|512)\s*gb\b|\b(64|128|256|512)\b", t)
    if m:
        for g in m.groups():
            if g:
                return int(g)
    # Check for typos
    numbers = re.findall(r'\b(\d+)\b', t)
    for num_str in numbers:
        num = int(num_str)
        if num in typo_map:
            return typo_map[num]
    return None

def extract_color(text: str, known_colors: List[str]) -> Optional[str]:
    t = normalize_spaces(text.lower())
    for key in COLOR_ALIASES:
        if key in t:
            candidate = COLOR_ALIASES[key]
            match = get_close_matches(candidate.lower(), [kc.lower() for kc in known_colors], n=1, cutoff=0.6)
            return match[0] if match else candidate
    return None

def extract_name(text: str) -> Optional[str]:
    """Extract name from text (looks for 'soy Name' or 'me llamo Name')"""
    # Regex for "Soy Julian" or "Me llamo Julian" anywhere in text
    match = re.search(r'\b(soy|me llamo|mi nombre es)\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ]+)', text, re.IGNORECASE)
    if match:
        return match.group(2)
    # Fallback: if text is short and likely just a name (and not a command)
    words = text.strip().split()
    
    # Flatten all intent keywords to check against
    all_keywords = []
    for kws in INTENTS.values():
        all_keywords.extend(kws)
        
    if len(words) <= 2:
        # Check against intent keys (categories) AND all specific keywords
        if not contains_any(text, list(INTENTS.keys()) + all_keywords):
             candidate = text.strip()
             # Ensure it's not a number (like a phone)
             if not any(char.isdigit() for char in candidate):
                 return candidate
    return None

def extract_contact(text: str) -> Optional[str]:
    """Extract contact (phone or email)"""
    # Email
    if '@' in text:
        m = re.search(r'\S+@\S+', text)
        if m:
            return m.group(0)
    # Phone
    m = re.search(r'\b\d{8,15}\b', text)
    if m:
        return m.group(0)
    return None

def extract_zone(text: str) -> Optional[str]:
    """Extract delivery zone (including pickup)"""
    t = normalize_spaces(text.lower())
    # Check for pickup intent first
    if contains_any(t, INTENTS["pickup"]):
        return "Retiro en local"
    zones_map = {
        "caba": "CABA", "capital": "CABA", 
        "amba": "AMBA", "gba": "AMBA", "zona norte": "AMBA", 
        "interior": "Interior", "cordoba": "Interior", "mendoza": "Interior"
    }
    for key in zones_map:
        if key in t:
            return zones_map[key]
    return None

def extract_payment_method(text: str) -> Optional[str]:
    """Extract payment method"""
    t = normalize_spaces(text.lower())
    methods = {
        "transferencia": "Transferencia",
        "transfer": "Transferencia",
        "efectivo": "Efectivo",
        "mercadopago": "MercadoPago",
        "mp": "MercadoPago",
        "tarjeta": "Tarjeta"
    }
    for key in methods:
        if key in t:
            return methods[key]
    return None

# -----------------------------
# Session & Bot
# -----------------------------

@dataclass
class Session:
    state: str = "GREET"
    model: Optional[str] = None
    storage_gb: Optional[int] = None
    color: Optional[str] = None
    name: str = ""
    contact: str = ""
    zone: str = ""
    payment_method: str = ""
    options: List[Dict[str, Any]] = field(default_factory=list)
    selection: Optional[Dict[str, Any]] = None
    hold_id: Optional[str] = None
    admin_mode: bool = False

class Bot:
    def __init__(self):
        self.db = Database()
        self.session = Session()
        self.refresh_knowledge()

    def refresh_knowledge(self):
        stock = self.db.load_stock()
        self.known_models = list(set(it['model'] for it in stock))
        self.known_colors = list(set(it['color'] for it in stock))

    def _pick(self, key, **kwargs):
        return random.choice(PHRASES.get(key, ["..."])).format(**kwargs)

    def _detect_policies(self, text: str) -> Optional[str]:
        """Policy detection (Feature #2)"""
        t = text.lower()
        if contains_any(t, INTENTS["shipping"]):
            return self._pick("policies_shipping")
        if contains_any(t, INTENTS["payments"]):
            return self._pick("policies_payments")
        if contains_any(t, INTENTS["installments"]):
            return self._pick("policies_installments")
        if contains_any(t, INTENTS["warranty"]):
            return self._pick("policies_warranty")
        if contains_any(t, INTENTS["returns"]):
            return self._pick("policies_returns")
        return None

    def _find_alternatives(self, model: str, storage_gb: int, color: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Find alternatives when exact match not found (Feature #3)"""
        alternatives = []
        
        # Try same model, different storage/color
        if model:
            similar = self.db.find_matches(model, None, None)
            for item in similar:
                avail = self.db.available_for_sku(item['sku'])
                if avail > 0:
                    item['available'] = avail
                    alternatives.append(item)
        
        if not alternatives:
            # Try any available stock
            all_stock = self.db.load_stock()
            for item in all_stock:
                avail = self.db.available_for_sku(item['sku'])
                if avail > 0:
                    item['available'] = avail
                    alternatives.append(item)
        
        return sorted(alternatives, key=lambda x: x.get('available', 0), reverse=True)[:limit]

    def _extract_entities(self, text: str):
        """Global entity extraction (Feature #4 - Auto-advance helper)"""
        s = self.session
        
        # Extract all entities globally
        new_model = extract_model(text, self.known_models)
        if new_model:
            if s.model and s.model.lower() != new_model.lower():
                s.storage_gb = None
                s.color = None
            s.model = new_model

        new_gb = extract_storage_gb(text)
        if new_gb: s.storage_gb = new_gb

        new_color = extract_color(text, self.known_colors)
        if new_color: s.color = new_color

        if new_color: s.color = new_color
        
        # Extract personal info for auto-advance
        
        # Fix: Only update name if not already set, OR if input is explicit ("Soy X")
        # Checking if "Soy" or "Me llamo" logic was used by extract_name
        name = extract_name(text)
        if name:
             is_explicit = re.search(r'\b(soy|me llamo|mi nombre es)\b', text, re.IGNORECASE)
             if not s.name or is_explicit:
                 s.name = name
        
        contact = extract_contact(text)
        if contact: s.contact = contact
        
        zone = extract_zone(text)
        if zone: s.zone = zone
        
        payment = extract_payment_method(text)
        if payment: s.payment_method = payment

    def _check_completion(self) -> Optional[str]:
        """Check what's missing for auto-advance (Feature #4)"""
        s = self.session
        if not s.name: return "name"
        if not s.contact: return "contact"
        if not s.zone: return "zone"
        if not s.payment_method: return "payment"
        return None

    def respond(self, text: str) -> str:
        s = self.session
        self.db.cleanup_holds()
        append_transcript("YOU", text)

        # 1. Global Commands
        if text.lower() in ("hola", "inicio", "reset", "empezar"):
            self.session = Session()
            return self._pick("greet")
        
        # 2. Cancel/Reset Intent (works anytime)
        if contains_any(text.lower(), INTENTS["cancel"]) and s.state not in ["GREET"]:
            if s.hold_id:
                self.db.release_hold(s.hold_id)
            self.session = Session()
            return "Ok, empezamos de nuevo. ¿Qué modelo buscás?"

        # 3. Admin
        if text.startswith("/admin") and ADMIN_PASS in text:
            s.admin_mode = True
            return "Admin ON."
        if s.admin_mode and "/exit" in text:
            s.admin_mode = False
            return "Admin OFF."

           # 3. Extract Entities (Move up to allow data processing first)
        self._extract_entities(text)
        # DEBUG
        # print(f"DEBUG: State={s.state} Model={s.model} GB={s.storage_gb} Color={s.color}")

        # 4. Handoff for sensitive topics
        if contains_any(text.lower(), INTENTS["sensitive"]) or contains_any(text.lower(), INTENTS["human"]):
            if s.contact:
                self.db.upsert_lead(s.name or "Cliente", s.contact, "Handoff: tema sensible")
            return self._pick("handoff", reason="negociación/postventa/tema especial")

        # 5. Policy Detection (Only if NOT a full data entry)
        # Verify if we have a "Complete Order" from this message (Auto-advance helper)
        # FIX: Remove 'and s.selection' because selection happens later
        if self._check_completion() is None:
            # We have everything, likely a purchase. Skip policies.
            pass 
        else:
            # If text is JUST data (e.g. "CABA"), don't trigger policy unless explicit
            is_pure_data = (s.zone and len(text.split()) < 3)
            policy_resp = self._detect_policies(text)
            if policy_resp and s.state in ["GREET", "SEARCH"] and not is_pure_data:
                return policy_resp

        # 6. Global Catalog/Stock Request (Feature #6)
        # Handle this here so it works even if model is not set (GREET state)
        if contains_any(text.lower(), INTENTS["catalog"]):
            # If we know the model, show specific variants + upsell
            if s.model:
                candidates = self.db.find_matches(s.model, None, None)
                valid = [c for c in candidates if self.db.available_for_sku(c['sku']) > 0]
                
                if not valid:
                    return f"Uhh, el {s.model} se me agotó por completo 😔. ¿Buscás otro modelo?"
                
                # Group by storage and color
                storage_opts = sorted(list(set(c['storage_gb'] for c in valid)))
                
                msg = f"📱 {s.model} disponible en:\n"
                for gb in storage_opts:
                    colors = [c['color'] for c in valid if c['storage_gb'] == gb]
                    msg += f"• {gb}GB: {', '.join(colors)}\n"
                
                # UPSELLING
                base_num = re.search(r'(\d+)', s.model)
                if base_num:
                    num = base_num.group(1)
                    if "Pro" not in s.model:
                        pro_exists = self.db.find_matches(f"Herramienta {num} Pro", None, None)
                        pro_max_exists = self.db.find_matches(f"Herramienta {num} Pro Max", None, None)
                        if pro_exists or pro_max_exists:
                            msg += f"\n💎 ¿Querés subir un poco? También tengo:\n"
                            if pro_exists: msg += f"• Herramienta {num} Pro (mejor cámara)\n"
                            if pro_max_exists: msg += f"• Herramienta {num} Pro Max (pantalla más grande)\n"
                    
                    next_num = str(int(num) + 1)
                    newer = self.db.find_matches(f"Herramienta {next_num}", None, None)
                    if newer: msg += f"\n🚀 O lo último: Herramienta {next_num}\n"
                
                msg += "\n¿Cuál te interesa?"
                return msg
            else:
                # No model, show general list
                all_stock = [s for s in self.db.load_stock() if self.db.available_for_sku(s['sku']) > 0]
                models = sorted(list(set(s['model'] for s in all_stock)))
                msg = "Tengo estos modelos disponibles:\n"
                for m in models[:8]:
                    msg += f"• {m}\n"
                msg += "\n¿Cuál te interesa?"
                return msg

        # 7. State Machine

        if s.state == "GREET":
            if s.model:
                s.state = "SEARCH"
            else:
                return self._pick("ask_variant")

        if s.state == "SEARCH":
            # Smart UPS selling + Stock Display
            if not all([s.model, s.storage_gb, s.color]):
                # If we have a model but missing specs, Auto-Trigger smart display
                if s.model:
                    # Reuse the logical block above effectively by recursion? 
                    # Simpler: just call the function logic or repeat
                    # Repetition for safety and isolation
                    candidates = self.db.find_matches(s.model, None, None)
                    valid = [c for c in candidates if self.db.available_for_sku(c['sku']) > 0]
                    if not valid: return f"Sin stock de {s.model}."
                    
                    storage_opts = sorted(list(set(c['storage_gb'] for c in valid)))
                    msg = f"📱 {s.model} disponible en:\n"
                    for gb in storage_opts:
                        colors = [c['color'] for c in valid if c['storage_gb'] == gb]
                        msg += f"• {gb}GB: {', '.join(colors)}\n"
                    msg += "\n¿Cuál preferís?"
                    return msg
                
                # Regular progress feedback
                have = []
                need = []
                if s.model:
                    have.append(f"✓ Modelo: {s.model}")
                else:
                    need.append("modelo")
                if s.storage_gb:
                    have.append(f"✓ {s.storage_gb}GB")
                else:
                    need.append("capacidad")
                if s.color:

                    have.append(f"✓ {s.color}")
                else:
                    need.append("color")
                
                if have:
                    msg = "Tengo: " + ", ".join(have) + "\n"
                    msg += "Falta: " + ", ".join(need)
                    return msg
                return "Necesito modelo + capacidad + color.\nEj: '16 Pro 256 Negro'"

            # Search for exact match
            matches = self.db.find_matches(s.model, s.storage_gb, s.color)
            
            if not matches:
                # Feature #3: Show Alternatives
                alternatives = self._find_alternatives(s.model, s.storage_gb, s.color)
                if alternatives:
                    msg = f"No tengo {s.model} {s.storage_gb}GB {s.color} 😓\nPero te puedo ofrecer:\n"
                    for i, alt in enumerate(alternatives, 1):
                        avail = alt['available']
                        price = format_money_ars(alt['price_ars'])
                        msg += f"{i}) {alt['model']} {alt['storage_gb']}GB {alt['color']} - {avail} disp - {price}\n"
                    msg += "\n¿Te sirve alguno? (elegí número)"
                    s.options = alternatives
                    s.state = "SELECT"
                    return msg
                return self._pick("no_match")

            # Check availability
            target = matches[0]
            avail = self.db.available_for_sku(target['sku'])
            if avail <= 0:
                return self._pick("no_stock")

            s.selection = target
            
            # Feature #4: Auto-advance if we have all data
            missing = self._check_completion()
            if missing is None:
                # We have everything! Create hold immediately
                res = self.db.create_hold(s.selection['sku'], s.name, s.contact)
                if not res:
                    return "Uhh, sin stock disponible ahora."
                s.hold_id = res['hold_id']
                s.state = "CONFIRM"
                price = format_money_ars(s.selection['price_ars'])
                return f"¡Perfecto! {s.selection['model']} {s.selection['storage_gb']}GB {s.selection['color']} - {price}\n" + self._pick("hold_created", minutes=res['expires_in_minutes'], hold_id=s.hold_id, name=s.name) + "\nEscribí 'confirmar' para cerrar."
            else:
                s.state = "CONTACT"
                return self._pick("stock_info", avail=avail, model=target['model'], gb=target['storage_gb'], color=target['color'], price=format_money_ars(target['price_ars'])) + "\n" + self._pick("ask_name")

        if s.state == "SELECT":
            # User selected from alternatives
            try:
                choice = int(text.strip())
                if 1 <= choice <= len(s.options):
                    s.selection = s.options[choice - 1]
                    s.state = "CONTACT"
                    price = format_money_ars(s.selection['price_ars'])
                    return f"¡Dale! {s.selection['model']} {s.selection['storage_gb']}GB {s.selection['color']} a {price}.\n" + self._pick("ask_name")
            except:
                pass
            return "Elegí un número de las opciones."

        if s.state == "CONTACT":
            if not s.name:
                s.name = text.split()[0] if len(text.split()) < 3 else "Cliente"
            if not s.contact:
                return self._pick("ask_contact", name=s.name)
            s.state = "ZONE"
            return self._pick("ask_zone", name=s.name)

        if s.state == "ZONE":
            if not s.zone:
                s.zone = text
            s.state = "PAYMENT"
            # Fix: Better phrasing for pickup
            if "retiro" in s.zone.lower() or "local" in s.zone.lower():
                return f"Perfecto, retirás en local. ¿Cómo pagás? (Transferencia/Efectivo/MercadoPago)"
            return self._pick("ask_payment", zone=s.zone)

        if s.state == "PAYMENT":
            if not s.payment_method:
                s.payment_method = text
            s.state = "HOLD"
            # Fall through to HOLD

        if s.state == "HOLD":
            res = self.db.create_hold(s.selection['sku'], s.name, s.contact)
            if not res:
                return "Uhh, sin stock disponible ahora."
            s.hold_id = res['hold_id']
            s.state = "CONFIRM"
            return self._pick("hold_created", minutes=res['expires_in_minutes'], hold_id=s.hold_id, name=s.name) + "\nEscribí 'confirmar' para cerrar."

        if s.state == "CONFIRM":
            if "confirm" in text.lower() or "dale" in text.lower():
                ok, msg = self.db.confirm_sale(s.hold_id, s.zone, s.payment_method)
                if ok:
                    price = s.selection['price_ars']
                    name = s.name
                    zone = s.zone
                    payment = s.payment_method
                    self.session = Session()
                    return self._pick("sale_confirmed", name=name, price=format_money_ars(price), zone=zone, payment=payment)
                return f"Error: {msg}"
            return "Esperando confirmación... (escribí 'confirmar')"

        return "No entendí. ¿Qué necesitás?"

# -----------------------------
# Main
# -----------------------------

def main():
    bot = Bot()
    print(f"{C.BOLD}--- iPHONE BOT UTOPIA (V13 FINAL) ---{C.END}")
    print(f"{C.GREY}[System] Loaded {len(bot.db.load_stock())} products from catalog.{C.END}\n")
    
    welcome = bot._pick("greet")
    append_transcript("BOT", welcome)
    print(f"{C.BOT}Bot: {welcome}{C.END}")

    while True:
        try:
            user_text = input(f"{C.USER}Vos: {C.END}").strip()
            if not user_text:
                continue
            if user_text.lower() in ["exit", "salir"]:
                print(f"{C.GREY}Listo. Cerrando.{C.END}")
                break
            
            resp = bot.respond(user_text)
            append_transcript("BOT", resp)
            print(f"{C.BOT}Bot: {resp}{C.END}", flush=True)
            
        except KeyboardInterrupt:
            print(f"\n{C.GREY}Saliendo...{C.END}")
            break
        except Exception as e:
            print(f"{C.ALERT}Error: {e}{C.END}")
            logging.error(f"Crash: {e}")

if __name__ == "__main__":
    main()
