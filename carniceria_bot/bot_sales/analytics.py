#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analytics Module
Tracks bot performance metrics and user behavior
"""

import json
import csv
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class Analytics:
    """
    Track and analyze bot performance
    """
    
    def __init__(self, db):
        """
        Initialize analytics with database connection
        
        Args:
            db: Database instance
        """
        self.db = db
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create analytics tables if they don't exist"""
        # Events table
        self.db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                product_sku TEXT,
                product_category TEXT,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Session summary table
        self.db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics_sessions (
                session_id TEXT PRIMARY KEY,
                started_at DATETIME,
                ended_at DATETIME,
                products_queried INTEGER DEFAULT 0,
                sale_completed BOOLEAN DEFAULT 0,
                sale_value INTEGER DEFAULT 0,
                cross_sell_offered BOOLEAN DEFAULT 0,
                cross_sell_accepted BOOLEAN DEFAULT 0,
                cross_sell_value INTEGER DEFAULT 0,
                abandonment_point TEXT,
                total_messages INTEGER DEFAULT 0
            )
        """)
        
        self.db.conn.commit()
    
    def track_event(
        self,
        session_id: str,
        event_type: str,
        product_sku: Optional[str] = None,
        product_category: Optional[str] = None,
        **metadata
    ):
        """
        Track an analytics event
        
        Args:
            session_id: Unique session identifier
            event_type: Type of event (conversation_start, product_query, sale, etc)
            product_sku: Optional product SKU
            product_category: Optional product category
            **metadata: Additional event data
        """
        metadata_json = json.dumps(metadata) if metadata else None
        
        self.db.cursor.execute("""
            INSERT INTO analytics_events 
            (session_id, event_type, product_sku, product_category, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, event_type, product_sku, product_category, metadata_json))
        
        self.db.conn.commit()
    
    def start_session(self, session_id: str):
        """Track new conversation session"""
        self.db.cursor.execute("""
            INSERT OR IGNORE INTO analytics_sessions (session_id, started_at)
            VALUES (?, ?)
        """, (session_id, datetime.now()))
        self.db.conn.commit()
        
        self.track_event(session_id, "conversation_start")
    
    def track_message(self, session_id: str):
        """Increment message count for session"""
        self.db.cursor.execute("""
            UPDATE analytics_sessions 
            SET total_messages = total_messages + 1
            WHERE session_id = ?
        """, (session_id,))
        self.db.conn.commit()
    
    def track_product_query(self, session_id: str, product_sku: str, category: str):
        """Track when user queries a product"""
        self.track_event(session_id, "product_query", product_sku, category)
        
        self.db.cursor.execute("""
            UPDATE analytics_sessions 
            SET products_queried = products_queried + 1
            WHERE session_id = ?
        """, (session_id,))
        self.db.conn.commit()
    
    def track_sale(self, session_id: str, product_sku: str, value: int, category: str):
        """Track completed sale"""
        self.track_event(session_id, "sale_completed", product_sku, category, value=value)
        
        self.db.cursor.execute("""
            UPDATE analytics_sessions 
            SET sale_completed = 1, sale_value = ?
            WHERE session_id = ?
        """, (value, session_id))
        self.db.conn.commit()
    
    def track_cross_sell_offer(self, session_id: str, product_sku: str, category: str):
        """Track when cross-sell is offered"""
        self.track_event(session_id, "cross_sell_offered", product_sku, category)
        
        self.db.cursor.execute("""
            UPDATE analytics_sessions 
            SET cross_sell_offered = 1
            WHERE session_id = ?
        """, (session_id,))
        self.db.conn.commit()
    
    def track_cross_sell_result(
        self, 
        session_id: str, 
        accepted: bool, 
        product_sku: Optional[str] = None,
        value: int = 0
    ):
        """Track cross-sell acceptance/rejection"""
        event_type = "cross_sell_accepted" if accepted else "cross_sell_rejected"
        
        if accepted:
            self.track_event(session_id, event_type, product_sku, value=value)
            self.db.cursor.execute("""
                UPDATE analytics_sessions 
                SET cross_sell_accepted = 1, cross_sell_value = ?
                WHERE session_id = ?
            """, (value, session_id))
        else:
            self.track_event(session_id, event_type)
            self.db.cursor.execute("""
                UPDATE analytics_sessions 
                SET cross_sell_accepted = 0
                WHERE session_id = ?
            """, (session_id,))
        
        self.db.conn.commit()
    
    def track_abandonment(self, session_id: str, point: str):
        """Track where user abandoned conversation"""
        self.track_event(session_id, "abandonment", abandonment_point=point)
        
        self.db.cursor.execute("""
            UPDATE analytics_sessions 
            SET abandonment_point = ?, ended_at = ?
            WHERE session_id = ?
        """, (point, datetime.now(), session_id))
        self.db.conn.commit()
    
    def end_session(self, session_id: str):
        """Mark session as ended"""
        self.db.cursor.execute("""
            UPDATE analytics_sessions 
            SET ended_at = ?
            WHERE session_id = ? AND ended_at IS NULL
        """, (datetime.now(), session_id))
        self.db.conn.commit()
    
    # === METRICS & REPORTS ===
    
    def get_conversion_rate(self) -> float:
        """Get overall conversion rate (sessions → sales)"""
        result = self.db.cursor.execute("""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(CASE WHEN sale_completed = 1 THEN 1 ELSE 0 END) as sales
            FROM analytics_sessions
        """).fetchone()
        
        if result[0] == 0:
            return 0.0
        return (result[1] / result[0]) * 100
    
    def get_cross_sell_stats(self) -> Dict[str, Any]:
        """Get cross-selling performance"""
        result = self.db.cursor.execute("""
            SELECT 
                SUM(CASE WHEN cross_sell_offered = 1 THEN 1 ELSE 0 END) as offers,
                SUM(CASE WHEN cross_sell_accepted = 1 THEN 1 ELSE 0 END) as accepted,
                SUM(cross_sell_value) as total_value
            FROM analytics_sessions
        """).fetchone()
        
        offers = result[0] or 0
        accepted = result[1] or 0
        
        return {
            "total_offers": offers,
            "total_accepted": accepted,
            "acceptance_rate": (accepted / offers * 100) if offers > 0 else 0,
            "total_value": result[2] or 0
        }
    
    def get_cross_sell_by_category(self) -> List[Dict[str, Any]]:
        """Cross-sell performance by product category"""
        rows = self.db.cursor.execute("""
            SELECT 
                product_category,
                COUNT(*) as offers,
                SUM(CASE WHEN event_type = 'cross_sell_accepted' THEN 1 ELSE 0 END) as accepted
            FROM analytics_events
            WHERE event_type IN ('cross_sell_offered', 'cross_sell_accepted')
            AND product_category IS NOT NULL
            GROUP BY product_category
        """).fetchall()
        
        return [
            {
                "category": row[0],
                "offers": row[1],
                "accepted": row[2],
                "acceptance_rate": (row[2] / row[1] * 100) if row[1] > 0 else 0
            }
            for row in rows
        ]
    
    def get_top_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Most queried and sold products"""
        rows = self.db.cursor.execute("""
            SELECT 
                product_sku,
                product_category,
                SUM(CASE WHEN event_type = 'product_query' THEN 1 ELSE 0 END) as queries,
                SUM(CASE WHEN event_type = 'sale_completed' THEN 1 ELSE 0 END) as sales
            FROM analytics_events
            WHERE product_sku IS NOT NULL
            GROUP BY product_sku, product_category
            ORDER BY queries DESC, sales DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        return [
            {
                "sku": row[0],
                "category": row[1],
                "queries": row[2],
                "sales": row[3],
                "conversion": (row[3] / row[2] * 100) if row[2] > 0 else 0
            }
            for row in rows
        ]
    
    def get_abandonment_points(self) -> Dict[str, int]:
        """Where users abandon conversations"""
        rows = self.db.cursor.execute("""
            SELECT abandonment_point, COUNT(*) as count
            FROM analytics_sessions
            WHERE abandonment_point IS NOT NULL
            GROUP BY abandonment_point
            ORDER BY count DESC
        """).fetchall()
        
        return {row[0]: row[1] for row in rows}
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get comprehensive analytics summary"""
        return {
            "conversion_rate": round(self.get_conversion_rate(), 2),
            "cross_sell": self.get_cross_sell_stats(),
            "cross_sell_by_category": self.get_cross_sell_by_category(),
            "top_products": self.get_top_products(5),
            "abandonment_points": self.get_abandonment_points()
        }
    
    def export_to_csv(self, filepath: str = "analytics_export.csv"):
        """Export session data to CSV"""
        rows = self.db.cursor.execute("""
            SELECT * FROM analytics_sessions
            ORDER BY started_at DESC
        """).fetchall()
        
        if not rows:
            return
        
        # Get column names
        columns = [desc[0] for desc in self.db.cursor.description]
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
    
    def print_dashboard(self):
        """Print analytics dashboard to console"""
        stats = self.get_summary_stats()
        
        print("\n" + "="*60)
        print("📊 ANALYTICS DASHBOARD")
        print("="*60)
        
        print(f"\n🎯 Conversion Rate: {stats['conversion_rate']}%")
        
        print(f"\n💡 Cross-Selling:")
        cs = stats['cross_sell']
        print(f"  • Total Offers: {cs['total_offers']}")
        print(f"  • Accepted: {cs['total_accepted']}")
        print(f"  • Acceptance Rate: {cs['acceptance_rate']:.1f}%")
        print(f"  • Total Value: ${cs['total_value']:,}")
        
        print(f"\n📱 Cross-Sell by Category:")
        for cat in stats['cross_sell_by_category']:
            print(f"  • {cat['category']}: {cat['acceptance_rate']:.1f}% " 
                  f"({cat['accepted']}/{cat['offers']})")
        
        print(f"\n🔥 Top Products:")
        for i, prod in enumerate(stats['top_products'], 1):
            print(f"  {i}. {prod['sku']} ({prod['category']}): "
                  f"{prod['queries']} queries, {prod['sales']} sales "
                  f"({prod['conversion']:.0f}%)")
        
        if stats['abandonment_points']:
            print(f"\n⚠️  Abandonment Points:")
            for point, count in list(stats['abandonment_points'].items())[:5]:
                print(f"  • {point}: {count}")
        
        print("\n" + "="*60 + "\n")
