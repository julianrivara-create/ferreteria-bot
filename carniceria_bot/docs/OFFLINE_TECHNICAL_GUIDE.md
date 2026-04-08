# 📊 Offline Dashboard - Technical Guide

The system now supports a robust **Offline Mode** for the Admin Dashboard.

## Architecture

1.  **Mock Service** (`mock_service.py`):
    - Generates realistic random data (products, sales, trends).
    - Stateless but consistent (initialized once per server run).
    - Provides specific methods matching API contracts (`get_daily_sales_stats`, `get_dashboard_summary`).

2.  **API Fallback** (`app.py`):
    - Key endpoints (`/api/stats`, `/api/analytics/*`) now have try-except blocks.
    - If DB is empty (`COUNT=0`) or query fails for any reason (missing DB file), it falls back to Mock Service.
    - Seamless experience for the UI (frontend doesn't know it's mock data).

## How to Test

1.  **Empty Database**:
    ```bash
    mv data/iphone_store.db data/iphone_store.db.bak
    python dashboard/app.py
    ```
    - Dashboard will show populated charts and metrics (from mock).

2.  **With Real Data**:
    ```bash
    mv data/iphone_store.db.bak data/iphone_store.db
    python dashboard/app.py
    ```
    - Mock mode disables automatically when real data exists.

## Endpoints Supported

- `/api/stats`: Main KPI cards (Revenue, Sales, Conversion).
- `/api/analytics/sales-by-day`: Chart data.
- `/api/analytics/top-products`: Top selling items table.

This ensures the dashboard is always demo-ready, even right after cloning the repo.
