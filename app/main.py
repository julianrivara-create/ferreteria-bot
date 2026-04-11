
from flask import Flask, g, jsonify, request, send_from_directory, redirect
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.api.routes import webhooks
from app.api.admin_routes import admin
from app.api.ferreteria_admin_routes import ferreteria_admin_api
from app.api.ferreteria_training_routes import ferreteria_training_api
from app.api.channels import channels
from app.api.public_routes import public_api
from app.api.console_routes import console_api
from app.crm.api.routes import crm_api
from app.crm.ui.routes import crm_ui
from app.ui.ferreteria_admin_routes import ferreteria_admin_ui
from app.ui.ferreteria_training_routes import ferreteria_training_ui
from app.services.mep_rate_scheduler import start_mep_rate_scheduler
from app.services.holds_scheduler import start_holds_scheduler
import structlog
import uuid
import os
import hmac
from flask_cors import CORS

def create_app() -> Flask:
    """Application factory for Flask"""
    settings = get_settings()
    configure_logging()
    logger = structlog.get_logger()
    
    website_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../website"))
    app = Flask(__name__, static_folder=website_dir)
    app.config['SECRET_KEY'] = settings.SECRET_KEY
    
    allowed_origins = settings.cors_origins
    if "*" in allowed_origins:
        if settings.is_production:
            logger.warning("cors_wildcard_enabled_in_production")
        CORS(app, origins="*", supports_credentials=False)
    elif allowed_origins:
        CORS(app, origins=allowed_origins, supports_credentials=True)
    elif not settings.is_production:
        # Dev: allow all for easy local testing
        CORS(app, origins="*", supports_credentials=False)
    else:
        # Production with no explicit CORS_ORIGINS: allow all origins without credentials.
        # Set CORS_ORIGINS env var to restrict to specific client domains when needed.
        logger.warning("cors_no_origins_configured_allowing_all_without_credentials")
        CORS(app, origins="*", supports_credentials=False)

    # Register Blueprints
    app.register_blueprint(webhooks, url_prefix='/webhooks')
    app.register_blueprint(admin, url_prefix='/api/admin')  # Changed from /admin to /api/admin
    app.register_blueprint(ferreteria_admin_api, url_prefix='/api/admin/ferreteria')
    app.register_blueprint(ferreteria_training_api, url_prefix='/api/admin/ferreteria')
    app.register_blueprint(channels, url_prefix='/webhooks')
    app.register_blueprint(public_api, url_prefix='/api') # /api/stock/batch, /api/chat
    app.register_blueprint(crm_api, url_prefix='/api/crm')
    app.register_blueprint(console_api, url_prefix='/api/console')
    app.register_blueprint(crm_ui)
    app.register_blueprint(ferreteria_admin_ui)
    app.register_blueprint(ferreteria_training_ui)

    @app.before_request
    def before_request():
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        g.request_id = request_id
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy', 'version': '2.0.3-DIAG'})

    # --- USER DIAGNOSTIC BLOCK START ---
    from urllib.parse import urlparse

    def _diag_authorized() -> bool:
        token = request.headers.get("X-Admin-Token") or ""
        if not settings.is_secret_configured(settings.ADMIN_TOKEN):
            logger.error("admin_token_not_configured")
            return False
        return hmac.compare_digest(token, settings.ADMIN_TOKEN)

    @app.route("/diag/db", methods=["GET"])
    def diag_db():
        if not _diag_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        v = os.getenv("DATABASE_URL", "")
        u = urlparse(v) if v else None
        return jsonify({
            "has_DATABASE_URL": bool(v),
            "db_host": (u.hostname if u else None),
            "db_port": (u.port if u else None),
            "db_name": (u.path if u else None),
            "railway_environment": os.getenv("RAILWAY_ENVIRONMENT"),
            "railway_service_name": os.getenv("RAILWAY_SERVICE_NAME"),
        })
    # --- USER DIAGNOSTIC BLOCK END ---

    @app.route('/catalog', methods=['GET'])
    def root_catalog():
        """Alias for /api/catalog"""
        return redirect('/api/catalog')

    @app.route('/')
    def serve_index():
        if os.path.exists(os.path.join(website_dir, 'index.html')):
            return send_from_directory(website_dir, 'index.html')
        return "Lumen V2 API Running", 200

    @app.route('/<path:path>')
    def serve_static(path):
        return send_from_directory(website_dir, path)

    start_mep_rate_scheduler()
    start_holds_scheduler()

    # Ensure DB schema is created (idempotent — safe to call every startup)
    from app.services.runtime_bootstrap import ensure_runtime_bootstrap
    try:
        result = ensure_runtime_bootstrap()
        logger.info("runtime_bootstrap_ok", **result)
    except Exception as exc:
        logger.error("runtime_bootstrap_failed", error=str(exc))
        if settings.is_production:
            raise ValueError(f"Runtime bootstrap failed in production: {exc}") from exc

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8000)
