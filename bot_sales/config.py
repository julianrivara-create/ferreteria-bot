"""
Configuración centralizada del bot (System & Default Tenant)
Refactored for Multi-Tenancy:
- System Config (Server, Redis, Logging) remains global.
- Tenant Config (Keys, Models) should be accessed via `core.tenancy_manager`.
- Global variables here act as "Default Tenant" for backward compatibility.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env si existe (System Level)
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Paths System Level
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.getenv('LOG_DIR', 'logs')
LOG_PATH = os.path.join(BASE_DIR, LOG_DIR, 'bot.log')

class Config:
    """Configuración global del Sistema y Default Tenant"""
    
    # --- SYSTEM CONFIG ---
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8080))
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    
    # Redis (System Service)
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')
    ENABLE_CACHE = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR = LOG_DIR
    SENTRY_DSN = os.getenv('SENTRY_DSN', '')
    
    # Admin Dashboard
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    
    # --- DEFAULT TENANT BACKWARD COMPATIBILITY ---
    # These should ideally come from TenantConfig
    
    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
    
    # Gemini
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-pro')
    
    # Email
    SMTP_HOST = os.getenv('SMTP_HOST')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    EMAIL_MOCK_MODE = not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD])
    
    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
    GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
    SHEETS_MOCK_MODE = not all([GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEET_ID])
    
    # WhatsApp - Twilio
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    # WhatsApp - Meta
    META_ACCESS_TOKEN = os.getenv('META_ACCESS_TOKEN')
    META_PHONE_NUMBER_ID = os.getenv('META_PHONE_NUMBER_ID')
    META_VERIFY_TOKEN = os.getenv('META_VERIFY_TOKEN', '')
    
    # Instagram
    INSTAGRAM_ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN', '')
    INSTAGRAM_VERIFY_TOKEN = os.getenv('INSTAGRAM_VERIFY_TOKEN', '')
    
    # Slack
    SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN', '')
    SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET', '')
    SLACK_APP_TOKEN = os.getenv('SLACK_APP_TOKEN', '')
    
    # Slack Advanced Features
    SLACK_ADMIN_CHANNEL = os.getenv('SLACK_ADMIN_CHANNEL', '')
    SLACK_REPORTS_CHANNEL = os.getenv('SLACK_REPORTS_CHANNEL', '')
    SLACK_APPROVAL_CHANNEL = os.getenv('SLACK_APPROVAL_CHANNEL', '')
    SLACK_ADMIN_USERS = os.getenv('SLACK_ADMIN_USERS', '')
    
    # Handoff Rules
    SLACK_ENABLE_HANDOFF = os.getenv('SLACK_ENABLE_HANDOFF', 'true').lower() == 'true'
    HANDOFF_AMOUNT_THRESHOLD = int(os.getenv('HANDOFF_AMOUNT_THRESHOLD', 5000))
    HANDOFF_SENTIMENT_THRESHOLD = float(os.getenv('HANDOFF_SENTIMENT_THRESHOLD', -0.5))
    
    # Multi-Channel Alerts
    SLACK_ALERT_EMAIL_ENABLED = os.getenv('SLACK_ALERT_EMAIL_ENABLED', 'false').lower() == 'true'
    SLACK_ALERT_EMAIL = os.getenv('SLACK_ALERT_EMAIL', '')
    SLACK_ALERT_WHATSAPP_ENABLED = os.getenv('SLACK_ALERT_WHATSAPP_ENABLED', 'false').lower() == 'true'
    SLACK_ALERT_WHATSAPP = os.getenv('SLACK_ALERT_WHATSAPP', '')
    
    # Approval Rules
    REQUIRE_APPROVAL_DISCOUNT_OVER = int(os.getenv('REQUIRE_APPROVAL_DISCOUNT_OVER', 10))
    REQUIRE_APPROVAL_HOLD_OVER = int(os.getenv('REQUIRE_APPROVAL_HOLD_OVER', 60))
    AUTO_APPROVE_DISCOUNT_UNDER = int(os.getenv('AUTO_APPROVE_DISCOUNT_UNDER', 5))
    APPROVAL_TIMEOUT_MINUTES = int(os.getenv('APPROVAL_TIMEOUT_MINUTES', 5))
    
    # Automated Reports
    SLACK_ENABLE_AUTO_REPORTS = os.getenv('SLACK_ENABLE_AUTO_REPORTS', 'true').lower() == 'true'
    SLACK_DAILY_REPORT_TIME = os.getenv('SLACK_DAILY_REPORT_TIME', '09:00')
    SLACK_WEEKLY_REPORT_DAY = os.getenv('SLACK_WEEKLY_REPORT_DAY', 'monday')
    
    # CRM Integration
    CRM_PROVIDER = os.getenv('CRM_PROVIDER', '')
    SALESFORCE_API_KEY = os.getenv('SALESFORCE_API_KEY', '')
    SALESFORCE_INSTANCE_URL = os.getenv('SALESFORCE_INSTANCE_URL', '')
    HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY', '')
    
    # Analytics & A/B Testing
    ANALYTICS_CHART_STORAGE = os.getenv('ANALYTICS_CHART_STORAGE', 'slack_files')
    AB_TESTING_ENABLED = os.getenv('AB_TESTING_ENABLED', 'true').lower() == 'true'
    SENTIMENT_PROVIDER = os.getenv('SENTIMENT_PROVIDER', 'textblob')
    SENTIMENT_ALERT_THRESHOLD = float(os.getenv('SENTIMENT_ALERT_THRESHOLD', -0.3))
    
    # Determinar provider de WhatsApp
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        WHATSAPP_PROVIDER = 'twilio'
    elif META_ACCESS_TOKEN and META_PHONE_NUMBER_ID:
        WHATSAPP_PROVIDER = 'meta'
    else:
        WHATSAPP_PROVIDER = 'mock'
    
    # MercadoPago
    MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    MERCADOPAGO_PUBLIC_KEY = os.getenv('MERCADOPAGO_PUBLIC_KEY')
    MERCADOPAGO_WEBHOOK_SECRET = os.getenv('MERCADOPAGO_WEBHOOK_SECRET', '')
    MP_MOCK_MODE = not MERCADOPAGO_ACCESS_TOKEN
    
    # Database (Default)
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/ferreteria.db')
    
    # Business Logic
    HOLD_MINUTES = int(os.getenv('HOLD_MINUTES', 30))
    LITE_MODE = os.getenv('LITE_MODE', 'false').lower() == 'true'
    
    # Features
    ENABLE_FRAUD_DETECTION = os.getenv('ENABLE_FRAUD_DETECTION', 'true').lower() == 'true'
    ENABLE_SENTIMENT_ANALYSIS = os.getenv('ENABLE_SENTIMENT_ANALYSIS', 'true').lower() == 'true'
    ENABLE_AB_TESTING = os.getenv('ENABLE_AB_TESTING', 'false').lower() == 'true'
    
    # --- STORE CONFIGURATION (MULTI-PRODUCT) ---
    STORE_NAME = os.getenv('STORE_NAME', 'Ferretería')
    STORE_TYPE = os.getenv('STORE_TYPE', 'ferretería')
    STORE_COUNTRY = os.getenv('STORE_COUNTRY', 'Argentina')
    
    # Product Categories (auto-detect if empty)
    _PRODUCT_CATEGORIES = os.getenv('PRODUCT_CATEGORIES', '')
    
    @classmethod
    def get_product_categories(cls):
        """Get product categories from config or auto-detect from catalog."""
        if cls._PRODUCT_CATEGORIES:
            return [cat.strip() for cat in cls._PRODUCT_CATEGORIES.split(',')]
        
        # Auto-detect from catalog
        try:
            from bot_sales.core.database import Database
            db = Database(
                db_file=cls.DATABASE_PATH,
                catalog_csv=CATALOG_CSV,
                log_path=LOG_PATH
            )
            return db.get_unique_categories()
        except Exception as e:
            logging.warning(f"Could not auto-detect categories: {e}")
            return ['productos']
    
    # Cross-sell categories
    _CROSSSELL_CATEGORIES = os.getenv('CROSSSELL_CATEGORIES', '')
    
    @classmethod
    def get_crosssell_categories(cls):
        """Get categories eligible for cross-selling."""
        if cls._CROSSSELL_CATEGORIES:
            return [cat.strip() for cat in cls._CROSSSELL_CATEGORIES.split(',')]
        # Default: all categories
        return cls.get_product_categories()
    
    DEFAULT_CATEGORY = os.getenv('DEFAULT_CATEGORY', '')
    
    # Business Rules
    ENABLE_UPSELLING = os.getenv('ENABLE_UPSELLING', 'true').lower() == 'true'
    ENABLE_CROSSSELLING = os.getenv('ENABLE_CROSSSELLING', 'true').lower() == 'true'
    ENABLE_BUNDLES = os.getenv('ENABLE_BUNDLES', 'true').lower() == 'true'

    @classmethod
    def is_production(cls):
        """Check if running in production"""
        return os.getenv('ENVIRONMENT', 'development') == 'production'
    
    @classmethod
    def print_config(cls):
        """Print active configuration (sin secrets)"""
        print("=" * 60)
        print("SYSTEM CONFIGURATION")
        print("=" * 60)
        print(f"Log Level: {cls.LOG_LEVEL}")
        print(f"Server: {cls.HOST}:{cls.PORT}")
        print(f"Cache: {'✅ Enabled' if cls.ENABLE_CACHE else '❌ Disabled'}")
        print("-" * 60)
        print("DEFAULT TENANT CONFIG (Deprecated for Multi-tenant)")
        print("-" * 60)
        print(f"OpenAI: {'✅ Configured' if cls.OPENAI_API_KEY else '❌ Missing'}")
        print(f"Gemini: {'✅ Configured' if cls.GEMINI_API_KEY else '❌ Missing'}")
        print(f"WhatsApp Provider: {cls.WHATSAPP_PROVIDER.upper()}")
        print("=" * 60)

# Singleton
config = Config()

# Exports for backward compatibility
# WARNING: These are now considered "Default Tenant" values.
OPENAI_API_KEY = config.OPENAI_API_KEY
OPENAI_MODEL = config.OPENAI_MODEL
OPENAI_TEMPERATURE = 0.7
OPENAI_MAX_TOKENS = 1000
MAX_CONTEXT_MESSAGES = 10

HOLD_MINUTES = config.HOLD_MINUTES
LITE_MODE = config.LITE_MODE

GEMINI_API_KEY = config.GEMINI_API_KEY
GEMINI_MODEL = config.GEMINI_MODEL

# Paths
DB_FILE = os.path.join(BASE_DIR, config.DATABASE_PATH)
CATALOG_CSV = os.path.join(BASE_DIR, 'config', 'catalog.csv')
POLICIES_FILE = os.path.join(BASE_DIR, 'config', 'policies.md')

