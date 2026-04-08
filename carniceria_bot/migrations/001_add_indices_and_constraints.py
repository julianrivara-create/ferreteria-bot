#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database Migrations - Add Indices and Check Constraints
Run this to optimize database performance and enforce data integrity
"""

import sqlite3
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def apply_migrations(db_path: str = 'data/iphone_store.db') -> None:
    """
    Apply database optimizations:
    1. Add indices for common queries
    2. Add check constraints for data integrity
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    logging.info(f"Starting database migrations on: {db_path}")
    
    try:
        # ===== INDICES for PERFORMANCE =====
        
        indices = [
            # Stock table indices
            ("idx_stock_sku", "CREATE INDEX IF NOT EXISTS idx_stock_sku ON stock(sku)"),
            ("idx_stock_model", "CREATE INDEX IF NOT EXISTS idx_stock_model ON stock(model)"),
            ("idx_stock_category", "CREATE INDEX IF NOT EXISTS idx_stock_category ON stock(category)"),
            
            # Holds table indices
            ("idx_holds_sku", "CREATE INDEX IF NOT EXISTS idx_holds_sku ON holds(sku)"),
            ("idx_holds_expires", "CREATE INDEX IF NOT EXISTS idx_holds_expires ON holds(expires_at)"),
            ("idx_holds_created", "CREATE INDEX IF NOT EXISTS idx_holds_created ON holds(created_at)"),
            
            # Sales table indices
            ("idx_sales_sku", "CREATE INDEX IF NOT EXISTS idx_sales_sku ON sales(sku)"),
            ("idx_sales_confirmed", "CREATE INDEX IF NOT EXISTS idx_sales_confirmed ON sales(confirmed_at)"),
            ("idx_sales_hold", "CREATE INDEX IF NOT EXISTS idx_sales_hold ON sales(hold_id)"),
            ("idx_sales_payment", "CREATE INDEX IF NOT EXISTS idx_sales_payment ON sales(payment_method)"),
            
            # Leads table indices
            ("idx_leads_created", "CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at)"),
        ]
        
        for idx_name, idx_sql in indices:
            logging.info(f"Creating index: {idx_name}")
            cursor.execute(idx_sql)
        
        logging.info(f"✅ Created {len(indices)} indices")
        
        # ===== CHECK CONSTRAINTS =====
        # Note: SQLite doesn't support adding constraints to existing tables easily
        # Need to recreate tables with constraints
        
        # Check if stock_with_constraints table exists (migration flag)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_with_constraints'")
        if cursor.fetchone():
            logging.info("⚠️  Constraints migration already applied, skipping")
        else:
            logging.info("Applying check constraints by recreating tables...")
            
            # Clean invalid data FIRST before applying constraints
            logging.info("Cleaning invalid data...")
            cursor.execute("UPDATE stock SET storage_gb = 128 WHERE storage_gb IS NULL OR storage_gb <= 0")
            cursor.execute("UPDATE stock SET stock_qty = 0 WHERE stock_qty IS NULL OR stock_qty < 0")
            cursor.execute("UPDATE stock SET price_ars = 1000 WHERE price_ars IS NULL OR price_ars <= 0")
            conn.commit()
            
            # Create new stock table with constraints
            cursor.execute('''
                CREATE TABLE stock_with_constraints (
                    sku TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'iPhone',
                    model TEXT NOT NULL,
                    storage_gb INTEGER CHECK(storage_gb > 0),
                    color TEXT,
                    stock_qty INTEGER CHECK(stock_qty >= 0) DEFAULT 0,
                    price_ars INTEGER CHECK(price_ars > 0)
                )
            ''')
            
            # Copy data
            cursor.execute('''
                INSERT INTO stock_with_constraints
                SELECT * FROM stock
            ''')
            
            # Drop old, rename new
            cursor.execute('DROP TABLE stock')
            cursor.execute('ALTER TABLE stock_with_constraints RENAME TO stock')
            
            logging.info("✅ Applied check constraints to 'stock' table")
            
            # Re-create indices after table recreation
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_sku ON stock(sku)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_model ON stock(model)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_category ON stock(category)")
        
        # ===== ADD DEFAULT VALUES =====
        
        # Add email column to sales if not exists (for future use)
        try:
            cursor.execute("SELECT email FROM sales LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'email' column to sales table")
            cursor.execute("ALTER TABLE sales ADD COLUMN email TEXT")
        
        # Add email column to holds if not exists
        try:
            cursor.execute("SELECT email FROM holds LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'email' column to holds table")
            cursor.execute("ALTER TABLE holds ADD COLUMN email TEXT")
        
        conn.commit()
        
        # ===== VACUUM and ANALYZE =====
        logging.info("Running VACUUM to reclaim space...")
        cursor.execute("VACUUM")
        
        logging.info("Running ANALYZE to update query planner statistics...")
        cursor.execute("ANALYZE")
        
        logging.info("✅ All migrations completed successfully!")
        
        # Print database stats
        cursor.execute("SELECT COUNT(*) FROM stock")
        stock_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM sales")
        sales_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM holds WHERE expires_at > ?", (time.time(),))
        active_holds = cursor.fetchone()[0]
        
        logging.info(f"""
Database Stats:
- Products: {stock_count}
- Sales: {sales_count}
- Active Holds: {active_holds}
        """)
        
    except Exception as e:
        logging.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import time
    import argparse
    
    parser = argparse.ArgumentParser(description='Run database migrations')
    parser.add_argument('--db', default='data/iphone_store.db', help='Path to database file')
    parser.add_argument('--dry-run', action='store_true', help='Preview migrations without applying')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logging.info("DRY RUN MODE - No changes will be made")
        logging.info(f"Would apply migrations to: {args.db}")
    else:
        apply_migrations(args.db)
