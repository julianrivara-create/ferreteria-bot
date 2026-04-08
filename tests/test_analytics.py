#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test Analytics Module
"""

import sys
sys.path.insert(0, '.')

from bot_sales.core.database import Database
from bot_sales.analytics import Analytics

# Initialize
db = Database('ferreteria.db', 'catalog_extended.csv', 'events.log')
analytics = Analytics(db)

print("🧪 Testing Analytics Module...")
print()

# Simulate some sessions
print("Creating test sessions...")

# Session 1: Successful sale with cross-sell accepted
analytics.start_session("test_1")
analytics.track_product_query("test_1", "IP16P-256-BLK", "Herramienta")
analytics.track_sale("test_1", "IP16P-256-BLK", 2000000, "Herramienta")
analytics.track_cross_sell_offer("test_1", "AP-PRO2", "Destornillador")
analytics.track_cross_sell_result("test_1", True, "AP-PRO2", 405000)
analytics.end_session("test_1")

# Session 2: Sale with cross-sell rejected
analytics.start_session("test_2")
analytics.track_product_query("test_2", "IP15PM-512-NAT", "Herramienta")
analytics.track_sale("test_2", "IP15PM-512-NAT", 2200000, "Herramienta")
analytics.track_cross_sell_offer("test_2", "AP-PRO2", "Destornillador")
analytics.track_cross_sell_result("test_2", False)
analytics.end_session("test_2")

# Session 3: PlayStation sale with controller cross-sell
analytics.start_session("test_3")
analytics.track_product_query("test_3", "PS5-DISC", "PlayStation")
analytics.track_sale("test_3", "PS5-DISC", 950000, "PlayStation")
analytics.track_cross_sell_offer("test_3", "CTRL-WHITE", "PlayStation")
analytics.track_cross_sell_result("test_3", True, "CTRL-WHITE", 114000)
analytics.end_session("test_3")

# Session 4: Abandoned after product query
analytics.start_session("test_4")
analytics.track_product_query("test_4", "MBA-M3-256-SG", "Sierra Circular")
analytics.track_abandonment("test_4", "after_product_query")

# Session 5: Just browsing
analytics.start_session("test_5")
analytics.track_message("test_5")
analytics.track_message("test_5")
analytics.track_abandonment("test_5", "after_greeting")

print("✅ Test sessions created")
print()

# Display dashboard
analytics.print_dashboard()

# Export to CSV
analytics.export_to_csv("analytics_test_export.csv")
print("📁 Exported to analytics_test_export.csv")
print()

# Close
db.close()
print("✅ Analytics test complete!")
