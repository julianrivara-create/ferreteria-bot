"""Tenant-only storefront API for multi-industry mode.

This module intentionally exposes only `/api/t/<tenant_slug>/...` routes
to avoid collisions with Final Production legacy `/api/...` endpoints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from ..core.tenancy import tenant_manager
from app.crm.services.rate_limiter import rate_limiter


storefront_tenant_bp = Blueprint("storefront_tenant_api", __name__)


def _load_branding(tenant) -> Dict[str, Any]:
    branding_file = tenant.branding_file or (tenant.profile or {}).get("paths", {}).get("branding")
    if not branding_file:
        return {}

    path = Path(branding_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent.parent / branding_file

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _tenant_or_default(slug: str = ""):
    if slug:
        tenant = tenant_manager.get_tenant_by_slug(slug)
        if not tenant:
            tenant_manager.reload()
            tenant = tenant_manager.get_tenant_by_slug(slug)
    else:
        tenant = tenant_manager.get_default_tenant()

    if not tenant:
        raise ValueError("No tenant configured")
    return tenant


def _get_products_for_tenant(slug: str) -> List[Dict[str, Any]]:
    tenant = _tenant_or_default(slug)
    db = tenant_manager.get_db(tenant.id)
    return db.load_stock()


def _to_storefront_payload(slug: str) -> Dict[str, Any]:
    tenant = _tenant_or_default(slug)
    profile = tenant.profile or {}
    business = profile.get("business", {}) if isinstance(profile, dict) else {}
    branding = _load_branding(tenant)

    products = _get_products_for_tenant(slug)
    categories = sorted({p.get("category", "") for p in products if p.get("category")})

    return {
        "tenant_id": tenant.id,
        "slug": tenant.get_slug(),
        "store_name": business.get("name") or tenant.name,
        "store_description": business.get("description") or "Catalogo multi-industria",
        "industry": business.get("industry") or "generic",
        "language": business.get("language") or "es",
        "currency": business.get("currency") or "ARS",
        "country": business.get("country") or "AR",
        "categories": categories,
        "branding": branding,
        "product_count": len(products),
    }


def _get_model_detail(slug: str, model: str) -> Dict[str, Any]:
    products = _get_products_for_tenant(slug)
    if not products:
        return {}

    model_lower = (model or "").strip().lower()
    exact = [p for p in products if str(p.get("model", "")).strip().lower() == model_lower]
    variants = exact or [p for p in products if model_lower in str(p.get("model", "")).lower()]

    if not variants:
        return {}

    canonical = variants[0]["model"]
    same_model = [p for p in products if p.get("model") == canonical]

    colors = sorted({p.get("color") for p in same_model if p.get("color")})
    storage_opts = sorted({int(p.get("storage_gb", 0)) for p in same_model if int(p.get("storage_gb", 0)) > 0})
    base_price = min(int(p.get("price_ars", 0) or 0) for p in same_model)

    return {
        "model": canonical,
        "name": canonical,
        "category": same_model[0].get("category", "General"),
        "price_ars": base_price,
        "base_price": base_price,
        "currency": same_model[0].get("currency", "ARS"),
        "colors": colors,
        "storage_options": storage_opts,
        "conditions": ["Nuevo"],
        "variants": [
            {
                "sku": p.get("sku"),
                "model": p.get("model"),
                "category": p.get("category"),
                "color": p.get("color"),
                "storage_gb": int(p.get("storage_gb", 0) or 0),
                "stock_qty": int(p.get("stock_qty", 0) or 0),
                "price_ars": int(p.get("price_ars", 0) or 0),
                "currency": p.get("currency", "ARS"),
                "attributes": p.get("attributes", {}),
            }
            for p in same_model
        ],
    }


@storefront_tenant_bp.route("/api/t/<tenant_slug>/storefront", methods=["GET"])
def api_storefront(tenant_slug: str):
    try:
        return jsonify(_to_storefront_payload(tenant_slug))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@storefront_tenant_bp.route("/api/t/<tenant_slug>/products", methods=["GET"])
def api_products(tenant_slug: str):
    try:
        return jsonify(_get_products_for_tenant(tenant_slug))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@storefront_tenant_bp.route("/api/t/<tenant_slug>/product", methods=["GET"])
def api_product_detail(tenant_slug: str):
    model = request.args.get("model", "")
    if not model:
        return jsonify({"error": "Missing model"}), 400

    detail = _get_model_detail(tenant_slug, model)
    if not detail:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(detail)


@storefront_tenant_bp.route("/api/t/<tenant_slug>/product/price", methods=["GET"])
def api_product_price(tenant_slug: str):
    model = request.args.get("model", "")
    if not model:
        return jsonify({"error": "Missing model"}), 400

    detail = _get_model_detail(tenant_slug, model)
    if not detail:
        return jsonify({"error": "Product not found"}), 404

    color = request.args.get("color")
    storage = request.args.get("storage")

    variants = detail.get("variants", [])
    filtered = []
    for v in variants:
        if color and str(v.get("color", "")).lower() != color.lower():
            continue
        if storage:
            try:
                if int(v.get("storage_gb", 0) or 0) != int(storage):
                    continue
            except ValueError:
                continue
        filtered.append(v)

    target = filtered[0] if filtered else variants[0]
    return jsonify(
        {
            "sku": target.get("sku"),
            "price": target.get("price_ars", 0),
            "currency": target.get("currency", "ARS"),
            "stock": target.get("stock_qty", 0),
        }
    )


@storefront_tenant_bp.route("/api/t/<tenant_slug>/chat", methods=["POST"])
def api_chat(tenant_slug: str):
    payload = request.get_json(silent=True) or {}

    # P1: Require a stable per-visitor identifier to prevent context cross-contamination.
    user = (payload.get("user") or payload.get("session_id") or "").strip()
    if not user:
        return jsonify({"error": "Missing user or session_id. Provide a stable per-visitor identifier."}), 400

    # P1.1: Rate limiting per tenant+user (10 msgs/min)
    rate_key = f"chat:{tenant_slug}:{user}"
    if not rate_limiter.allow(rate_key, limit=10, window_seconds=60):
        return jsonify({"error": "Rate limit exceeded. Max 10 messages per minute."}), 429

    try:
        tenant = _tenant_or_default(tenant_slug)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    message = payload.get("message", "").strip()

    if not message:
        return jsonify({"error": "Missing message"}), 400

    bot = tenant_manager.get_bot(tenant.id)
    content = bot.process_message(str(user), message, tenant_id=tenant_slug)
    return jsonify({"content": content, "tenant": tenant.get_slug()})

