#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stock Updater from Email
------------------------
Automates stock updates by fetching the latest email with an attachment.

Usage:
    python scripts/update_stock_from_email.py

Configuration (.env):
    EMAIL_IMAP_SERVER=imap.gmail.com
    EMAIL_USER=your_email@gmail.com
    EMAIL_PASSWORD=your_app_password
    EMAIL_SEARCH_SUBJECT="Stock Update"
    EMAIL_SENDER_FILTER=supplier@example.com (optional)
"""

import os
import sys
import imaplib
import email
import csv
import logging
from email.header import decode_header
from pathlib import Path
from tempfile import NamedTemporaryFile

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot_sales.config import config
from bot_sales.core.database import Database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("StockUpdater")

def connect_imap():
    """Connect to IMAP server"""
    server = os.getenv('EMAIL_IMAP_SERVER', 'imap.gmail.com')
    user = os.getenv('EMAIL_USER')
    password = os.getenv('EMAIL_PASSWORD')
    
    if not user or not password:
        logger.error("Missing EMAIL_USER or EMAIL_PASSWORD in .env")
        return None
        
    try:
        mail = imaplib.IMAP4_SSL(server)
        mail.login(user, password)
        logger.info(f"Connected to {server} as {user}")
        return mail
    except Exception as e:
        logger.error(f"IMAP Connection failed: {e}")
        return None

def find_latest_email(mail):
    """Find latest matching email"""
    mail.select("inbox")
    
    subject_query = os.getenv('EMAIL_SEARCH_SUBJECT', 'Stock')
    sender_query = os.getenv('EMAIL_SENDER_FILTER', '')
    
    # Build search criteria
    criteria = f'(SUBJECT "{subject_query}")'
    if sender_query:
        criteria += f' (FROM "{sender_query}")'
        
    status, messages = mail.search(None, criteria)
    
    if status != "OK" or not messages[0]:
        logger.info("No matching emails found.")
        return None
        
    # Get latest
    latest_id = messages[0].split()[-1]
    logger.info(f"Found email ID: {latest_id.decode()}")
    
    status, msg_data = mail.fetch(latest_id, "(RFC822)")
    
    for response_part in msg_data:
        if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])
            return msg
            
    return None

def get_attachment(msg):
    """Extract CSV attachment from email"""
    subject, encoding = decode_header(msg["Subject"])[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding or "utf-8")
        
    logger.info(f"Processing email: {subject}")
    
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue
            
        filename = part.get_filename()
        if not filename:
            continue
            
        if filename.lower().endswith(".csv"):
            logger.info(f"Found CSV attachment: {filename}")
            
            # Save to temp file
            temp = NamedTemporaryFile(delete=False, suffix=".csv")
            temp.write(part.get_payload(decode=True))
            temp.close()
            return temp.name
            
    logger.warning("No CSV attachment found in email.")
    return None

def update_db_from_csv(csv_path):
    """Update database from CSV file"""
    db = Database(config.DATABASE_PATH, 'config/catalog.csv', 'logs/bot.log')
    updated_count = 0
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Normalize headers (lowercase)
            reader.fieldnames = [name.lower() for name in reader.fieldnames]
            
            for row in reader:
                try:
                    # Map columns (adjust logic as needed)
                    sku = row.get('sku') or row.get('codigo')
                    qty = row.get('stock') or row.get('cantidad') or row.get('qty')
                    price = row.get('price') or row.get('precio') or row.get('price_ars')
                    
                    if sku and qty is not None:
                        # Normalize data for UPSERT
                        category = row.get('category') or row.get('categoria') or 'General'
                        model = row.get('model') or row.get('modelo') or row.get('nombre') or 'Unknown'
                        color = row.get('color') or 'Standard'
                        storage = row.get('storage') or row.get('capacidad') or row.get('storage_gb') or 0
                        
                        # Clean storage (remove 'GB')
                        if isinstance(storage, str):
                            storage = ''.join(filter(str.isdigit, storage)) or 0
                        
                        # UPSERT (Insert or Update)
                        db.cursor.execute("""
                            INSERT INTO stock (sku, category, model, storage_gb, color, stock_qty, price_ars)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(sku) DO UPDATE SET
                                stock_qty = excluded.stock_qty,
                                price_ars = excluded.price_ars,
                                category = COALESCE(excluded.category, stock.category),
                                model = COALESCE(excluded.model, stock.model)
                        """, (
                            sku, 
                            category, 
                            model, 
                            int(storage), 
                            color, 
                            int(qty), 
                            int(float(price or 0))
                        ))
                            
                        if db.cursor.rowcount > 0:
                            updated_count += 1
                            
                except ValueError:
                    continue
                    
            db.conn.commit()
            logger.info(f"Successfully updated {updated_count} products.")
            
    except Exception as e:
        logger.error(f"Error updating DB: {e}")
    finally:
        db.close()
        os.unlink(csv_path)  # Cleanup temp file

def main():
    logger.info("Starting Stock Update Process...")
    
    # 1. Connect
    mail = connect_imap()
    if not mail:
        return
    
    # 2. Find Email
    msg = find_latest_email(mail)
    if not msg:
        mail.logout()
        return
        
    # 3. Get Attachment
    csv_file = get_attachment(msg)
    mail.logout()
    
    if not csv_file:
        return
        
    # 4. Update DB
    update_db_from_csv(csv_file)
    logger.info("Process finished.")

if __name__ == "__main__":
    main()
