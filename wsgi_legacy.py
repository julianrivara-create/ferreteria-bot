#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WSGI Entry Point for Production (Railway/Gunicorn)
Integrates both WhatsApp Bot and Admin Dashboard in a single Flask App.
"""

import sys
import os
from flask import Flask, redirect, request, send_from_directory
from bot_sales.bot import SalesBot
from bot_sales.connectors.whatsapp import get_whatsapp_blueprint, WhatsAppConnector
from bot_sales.connectors.instagram import get_instagram_connector, run_instagram_webhook
from bot_sales.connectors.slack import get_slack_connector, run_slack_webhook
from bot_sales.connectors.storefront_api import storefront_bp
from bot_sales.config import BASE_DIR, config
from bot_sales.core.health import register_health_checks
from bot_sales.core.logger import setup_logging
from dashboard.app import dashboard_bp
from bot_sales.core.tenancy import tenant_manager

# Setup logging
setup_logging(level='INFO')

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY', 'default-dev-key-change-in-prod')

    # Register health/readiness/metrics endpoints early for platform probes.
    register_health_checks(app)
    
    # 1. Initialize default bot resources for non-tenant channels.
    print("🤖 Initializing Sales Bot resources...")
    default_tenant = tenant_manager.get_default_tenant()
    if default_tenant:
        bot = tenant_manager.get_bot(default_tenant.id)
    else:
        bot = SalesBot()
    
    # 2. Initialize Connector
    provider = config.WHATSAPP_PROVIDER
    print(f"🔌 Initializing WhatsApp Connector: {provider}")
    
    if provider == 'twilio':
        connector = WhatsAppConnector(
            provider='twilio',
            account_sid=config.TWILIO_ACCOUNT_SID,
            api_token=config.TWILIO_AUTH_TOKEN,
            phone_number=config.TWILIO_WHATSAPP_NUMBER
        )
    elif provider == 'meta':
        connector = WhatsAppConnector(
            provider='meta',
            api_token=config.META_ACCESS_TOKEN,
            phone_number=config.META_PHONE_NUMBER_ID
        )
    else:
        connector = WhatsAppConnector(provider='mock')
    
    # 3. Register Blueprints
    
    # Dashboard (tenant-aware)
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    # Storefront API (tenant-aware + legacy aliases)
    app.register_blueprint(storefront_bp)

    # Bot Webhook (/webhooks/whatsapp)
    whatsapp_bp = get_whatsapp_blueprint(None, connector)
    app.register_blueprint(whatsapp_bp)

    website_dir = os.path.join(BASE_DIR, "website")

    @app.get("/")
    def root():
        return redirect("/dashboard")

    @app.get("/website/<path:asset_path>")
    def website_assets(asset_path: str):
        return send_from_directory(website_dir, asset_path)

    @app.get("/t/<tenant_slug>")
    def tenant_storefront(tenant_slug: str):
        return redirect(f"/website/index.html?tenant={tenant_slug}")

    @app.get("/t/<tenant_slug>/product")
    def tenant_product(tenant_slug: str):
        model = request.args.get("model", "")
        target = f"/website/product.html?tenant={tenant_slug}"
        if model:
            target += f"&model={model}"
        return redirect(target)
    
    # 4. Instagram Webhook (if configured)
    instagram_connector = get_instagram_connector()
    if instagram_connector:
        run_instagram_webhook(app, bot, instagram_connector)
        print("📸 Instagram connector enabled")
    else:
        print("⚠️  Instagram not configured (set INSTAGRAM_ACCESS_TOKEN to enable)")
    
    # 5. Slack Webhook (if configured)
    slack_connector = get_slack_connector()
    if slack_connector:
        run_slack_webhook(app, bot, slack_connector)
        print("💬 Slack connector enabled")
    else:
        print("⚠️  Slack not configured (set SLACK_BOT_TOKEN to enable)")
    
    print("✅ Application configured successfully")
    return app

# Expose app for Gunicorn
app = create_app()

if __name__ == "__main__":
    # Local dev support
    port = int(os.getenv("PORT", 5001))
    print(f"🚀 Starting Monolith Server on port {port}")
    app.run(host="0.0.0.0", port=port)
