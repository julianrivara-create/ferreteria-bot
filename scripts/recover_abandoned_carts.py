#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Abandoned Cart Recovery Script
------------------------------
Run this via Cron every 30-60 minutes.
Logic:
1. Find holds that expired in the last hour.
2. Check if they were converted to sales (if not, it's abandoned).
3. Send a friendly recovery email with a payment link.
"""

import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot_sales.core.database import Database
from bot_sales.config import Config
from bot_sales.integrations.email_client import EmailClient

# Setup Config
DB_FILE = Config.DATABASE_PATH
CATALOG_CSV = Config.CATALOG_CSV
LOG_PATH = Config.LOG_PATH

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CartRecovery")

def recover_abandoned_carts():
    logger.info("🕵️‍♂️ Hunting for abandoned carts...")
    
    db = Database(DB_FILE, CATALOG_CSV, LOG_PATH)
    email_client = EmailClient(
        smtp_host=Config.SMTP_HOST,
        smtp_port=Config.SMTP_PORT,
        smtp_user=Config.SMTP_USER,
        smtp_password=Config.SMTP_PASSWORD,
        mock_mode=Config.EMAIL_MOCK_MODE
    )
    
    # 1. Inspect recent activity (Simulated via DB queries for expired holds)
    # Ideally, we should query holds that expired recently and are NOT in sales table
    
    # Note: Our current schema deletes holds upon expiry or sale.
    # To track abandoned carts properly, we should have 'soft deleted' them or logged them.
    # For this MVP, we will rely on checking 'holds' that are ABOUT to expire or just expired if we tracked history.
    
    # Better approach given current schema limitations:
    # Use 'events.log' or a new tracking table? 
    # Or simpler: Query ACTIVE holds that have > 15 mins but < 30 mins (Pre-abandonment warning)
    # OR query 'leads' that didn't convert?
    
    # Let's verify DB capabilities.
    # Currently `cleanup_holds` deletes them.
    # Modification: The main bot process calls `cleanup_holds`.
    # We should intercept them BEFORE deletion or log them to an 'abandoned_carts' table.
    
    # STRATEGY FOR NOW:
    # Since we can't travel back in time, let's implement a 'Pre-Abandonment Nudge'.
    # Find holds created > 20 mins ago that are still active.
    
    conn = db.conn
    cursor = conn.cursor()
    
    # Time window: Holds created between 20 and 30 mins ago (assuming 30 min expiration)
    now = time.time()
    warning_window_start = now - (30 * 60) # 30 mins ago
    warning_window_end = now - (15 * 60)   # 15 mins ago
    
    cursor.execute("""
        SELECT hold_id, sku, name, contact, created_at 
        FROM holds 
        WHERE created_at BETWEEN ? AND ?
    """, (warning_window_start, warning_window_end))
    
    carts = cursor.fetchall()
    
    if not carts:
        logger.info("✅ No abandoned carts found in warning window.")
        return

    logger.info(f"⚠️ Found {len(carts)} carts at risk. Sending nudges...")
    
    for cart in carts:
        hold_id, sku, name, contact, created_at = cart
        
        # Check if contact is email
        if "@" not in contact:
            logger.info(f"Skipping {hold_id}: Contact '{contact}' is not an email.")
            continue
            
        # Get Product Info
        product = db.get_product_by_sku(sku)
        prod_name = product['model'] if product else sku
        
        # Send Email
        subject = f"⏳ Tu reserva de {prod_name} expira pronto"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #e53e3e;">¡No pierdas tu reserva! 😱</h2>
            <p>Hola <strong>{name}</strong>,</p>
            <p>Vimos que reservaste un <strong>{prod_name}</strong> pero todavía no completaste el pago.</p>
            <p>Por la alta demanda, el sistema libera el stock automáticamente en <strong>10 minutos</strong>.</p>
            <p>¿Te podemos ayudar con algo? ¿Dudas con el pago?</p>
            <br>
            <a href="#" style="background: #2b6cb0; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                Continuar con la compra
            </a>
            <p style="color: #718096; font-size: 12px; margin-top: 20px;">
                Si ya compraste, desestimá este mensaje.
            </p>
        </body>
        </html>
        """
        
        text_body = f"Hola {name}, tu reserva del {prod_name} expira en 10 minutos. Completá tu compra para no perder el stock."
        
        email_client._send_email(contact, subject, text_body, html_body)
        logger.info(f"📧 Nudge sent to {contact} for hold {hold_id}")

if __name__ == "__main__":
    recover_abandoned_carts()
