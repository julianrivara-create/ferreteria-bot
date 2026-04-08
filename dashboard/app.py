"""Tenant-aware dashboard blueprint."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from flask import Blueprint, Flask, abort, jsonify, redirect, render_template, request, session, url_for

from bot_sales.core.tenancy import tenant_manager


dashboard_bp = Blueprint("dashboard", __name__, template_folder="templates")


def _admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin")


_DASHBOARD_SALT = b"ferreteria-dashboard-v1"
_PBKDF2_ITERATIONS = 260_000


def _admin_password_hash() -> bytes:
    raw = os.getenv("ADMIN_PASSWORD")
    if not raw:
        raise RuntimeError("ADMIN_PASSWORD env var is required to run the dashboard.")
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), _DASHBOARD_SALT, _PBKDF2_ITERATIONS)


def _login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_logged_in"):
            return redirect(url_for("dashboard.login", next=request.path))
        return fn(*args, **kwargs)

    return wrapped


def _get_tenant(tenant_slug: str):
    tenant = tenant_manager.get_tenant_by_slug(tenant_slug)
    if not tenant:
        tenant_manager.reload()
        tenant = tenant_manager.get_tenant_by_slug(tenant_slug)
    if not tenant:
        abort(404, description=f"Tenant not found: {tenant_slug}")
    return tenant


def _tenant_context(tenant_slug: str) -> Dict[str, Any]:
    tenant = _get_tenant(tenant_slug)
    store_name = tenant.name
    profile = tenant.profile or {}
    business = profile.get("business", {}) if isinstance(profile, dict) else {}
    if business.get("name"):
        store_name = business["name"]

    return {
        "tenant": tenant,
        "tenant_slug": tenant.get_slug(),
        "store_name": store_name,
    }


@dashboard_bp.route("/")
def root_redirect():
    default_tenant = tenant_manager.get_default_tenant()
    slug = default_tenant.get_slug() if default_tenant else "default"
    return redirect(url_for("dashboard.index_tenant", tenant_slug=slug))


@dashboard_bp.route("/login", methods=["GET", "POST"])
def login():
    next_path = request.args.get("next") or url_for("dashboard.root_redirect")

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        password_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), _DASHBOARD_SALT, _PBKDF2_ITERATIONS)

        if username == _admin_username() and hmac.compare_digest(password_hash, _admin_password_hash()):
            session["dashboard_logged_in"] = True
            session["username"] = username
            return redirect(next_path)

        return render_template("login.html", error="Invalid credentials", next=next_path)

    return render_template("login.html", next=next_path)


@dashboard_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard.login"))


@dashboard_bp.route("/t/<tenant_slug>")
@_login_required
def index_tenant(tenant_slug: str):
    return render_template("index.html", **_tenant_context(tenant_slug))


@dashboard_bp.route("/t/<tenant_slug>/sales")
@_login_required
def sales_page(tenant_slug: str):
    return render_template("sales.html", **_tenant_context(tenant_slug))


@dashboard_bp.route("/t/<tenant_slug>/products")
@_login_required
def products_page(tenant_slug: str):
    return render_template("products.html", **_tenant_context(tenant_slug))


@dashboard_bp.route("/t/<tenant_slug>/conversations")
@_login_required
def conversations_page(tenant_slug: str):
    return render_template("conversations.html", **_tenant_context(tenant_slug))


@dashboard_bp.route("/api/t/<tenant_slug>/products")
@_login_required
def api_products(tenant_slug: str):
    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)
    return jsonify(db.load_stock())


@dashboard_bp.route("/api/t/<tenant_slug>/stats")
@_login_required
def api_stats(tenant_slug: str):
    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)

    try:
        total_sales = db.cursor.execute("SELECT COUNT(*) AS total FROM sales").fetchone()["total"]
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        sales_today = db.cursor.execute(
            "SELECT COUNT(*) AS count FROM sales WHERE confirmed_at >= ?",
            (start_of_day,),
        ).fetchone()["count"]

        total_revenue = db.cursor.execute(
            """
            SELECT COALESCE(SUM(s.price_ars), 0) AS revenue
            FROM sales sa
            JOIN stock s ON s.sku = sa.sku
            """
        ).fetchone()["revenue"]

        revenue_today = db.cursor.execute(
            """
            SELECT COALESCE(SUM(s.price_ars), 0) AS revenue
            FROM sales sa
            JOIN stock s ON s.sku = sa.sku
            WHERE sa.confirmed_at >= ?
            """,
            (start_of_day,),
        ).fetchone()["revenue"]

        # Optional table for conversion metrics.
        try:
            total_sessions = db.cursor.execute(
                "SELECT COUNT(DISTINCT session_id) AS sessions FROM conversation_history"
            ).fetchone()["sessions"]
        except Exception:
            total_sessions = 0

        conversion_rate = round((total_sales / total_sessions * 100), 2) if total_sessions > 0 else 0.0

        top_row = db.cursor.execute(
            """
            SELECT sku, COUNT(*) AS count
            FROM sales
            GROUP BY sku
            ORDER BY count DESC
            LIMIT 1
            """
        ).fetchone()
        top_product = top_row["sku"] if top_row else "N/A"

        return jsonify(
            {
                "total_sales": total_sales,
                "sales_today": sales_today,
                "total_revenue": total_revenue,
                "revenue_today": revenue_today,
                "conversion_rate": conversion_rate,
                "top_product": top_product,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/api/t/<tenant_slug>/analytics/sales-by-day")
@_login_required
def api_sales_by_day(tenant_slug: str):
    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)

    rows = db.cursor.execute(
        """
        SELECT
            DATE(datetime(confirmed_at, 'unixepoch', 'localtime')) AS date,
            COUNT(*) AS count
        FROM sales
        WHERE confirmed_at >= strftime('%s', 'now', '-30 day')
        GROUP BY DATE(datetime(confirmed_at, 'unixepoch', 'localtime'))
        ORDER BY date ASC
        """
    ).fetchall()

    return jsonify([dict(row) for row in rows])


@dashboard_bp.route("/api/t/<tenant_slug>/analytics/top-products")
@_login_required
def api_top_products(tenant_slug: str):
    limit = request.args.get("limit", 10, type=int)

    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)

    rows = db.cursor.execute(
        """
        SELECT
            sa.sku AS product_sku,
            COUNT(*) AS sales_count,
            COALESCE(SUM(s.price_ars), 0) AS total_revenue
        FROM sales sa
        LEFT JOIN stock s ON s.sku = sa.sku
        GROUP BY sa.sku
        ORDER BY sales_count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return jsonify([dict(row) for row in rows])


@dashboard_bp.route("/api/t/<tenant_slug>/sales")
@_login_required
def api_sales(tenant_slug: str):
    limit = request.args.get("limit", 50, type=int)
    status = request.args.get("status", "all")

    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)

    rows = db.cursor.execute(
        """
        SELECT sale_id, sku, name, zone, payment_method, confirmed_at
        FROM sales
        ORDER BY confirmed_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    sales = []
    for row in rows:
        item = {
            "id": row["sale_id"],
            "product_sku": row["sku"],
            "customer_name": row["name"],
            "total_ars": (db.get_product_by_sku(row["sku"]) or {}).get("price_ars", 0),
            "metodo_pago": row["payment_method"],
            "zona": row["zone"],
            "status": "confirmed",
            "timestamp": row["confirmed_at"],
        }
        if status in ("all", item["status"]):
            sales.append(item)

    return jsonify(sales)


@dashboard_bp.route("/api/t/<tenant_slug>/conversations")
@_login_required
def api_conversations(tenant_slug: str):
    limit = request.args.get("limit", 20, type=int)
    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)

    try:
        rows = db.cursor.execute(
            """
            SELECT session_id, MAX(timestamp) AS last_message, COUNT(*) AS message_count
            FROM conversation_history
            GROUP BY session_id
            ORDER BY last_message DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except Exception:
        rows = []

    return jsonify([dict(row) for row in rows])


@dashboard_bp.route("/api/t/<tenant_slug>/conversations/<session_id>")
@_login_required
def api_conversation_detail(tenant_slug: str, session_id: str):
    tenant = _get_tenant(tenant_slug)
    db = tenant_manager.get_db(tenant.id)

    try:
        rows = db.cursor.execute(
            """
            SELECT * FROM conversation_history
            WHERE session_id = ?
            ORDER BY timestamp ASC
            """,
            (session_id,),
        ).fetchall()
    except Exception:
        rows = []

    return jsonify([dict(row) for row in rows])


# Backward-compatible local run.
def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "change-this-in-production")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    return app


if __name__ == "__main__":
    app = create_app()
    print("=" * 60)
    print("Dashboard running")
    print("URL: http://localhost:5001/dashboard")
    print("User: admin")
    print("Pass: (set via ADMIN_PASSWORD env var)")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=True)
