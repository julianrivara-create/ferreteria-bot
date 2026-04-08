"""
Configuración centralizada del bot
Lee variables de entorno y provee defaults
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env si existe
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

class Config:
    """Configuración global"""
    
    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
    
    # Gemini
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-pro')
    
    # Email
    SMTP_HOST = os.getenv('SMTP_HOST')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD') or os.getenv('SMTP_PASS')
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
    META_PHONE_NUMBER_ID = os.getenv('META_PHONE_NUMBER_ID') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
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
    SLACK_ENABLE_HANDOFF = os.getenv('SLACK_ENABLE_HANDOFF', 'true').lower() == 'true'
    HANDOFF_AMOUNT_THRESHOLD = int(os.getenv('HANDOFF_AMOUNT_THRESHOLD', 5000))
    HANDOFF_SENTIMENT_THRESHOLD = float(os.getenv('HANDOFF_SENTIMENT_THRESHOLD', -0.5))
    SLACK_ALERT_EMAIL_ENABLED = os.getenv('SLACK_ALERT_EMAIL_ENABLED', 'false').lower() == 'true'
    SLACK_ALERT_EMAIL = os.getenv('SLACK_ALERT_EMAIL', '')
    SLACK_ALERT_WHATSAPP_ENABLED = os.getenv('SLACK_ALERT_WHATSAPP_ENABLED', 'false').lower() == 'true'
    SLACK_ALERT_WHATSAPP = os.getenv('SLACK_ALERT_WHATSAPP', '')
    REQUIRE_APPROVAL_DISCOUNT_OVER = int(os.getenv('REQUIRE_APPROVAL_DISCOUNT_OVER', 10))
    REQUIRE_APPROVAL_HOLD_OVER = int(os.getenv('REQUIRE_APPROVAL_HOLD_OVER', 60))
    AUTO_APPROVE_DISCOUNT_UNDER = int(os.getenv('AUTO_APPROVE_DISCOUNT_UNDER', 5))
    APPROVAL_TIMEOUT_MINUTES = int(os.getenv('APPROVAL_TIMEOUT_MINUTES', 5))
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

    # Bank transfer details
    TRANSFER_CVU = os.getenv('TRANSFER_CVU', '0000003100007806886850')
    TRANSFER_ALIAS = os.getenv('TRANSFER_ALIAS', '')
    TRANSFER_ACCOUNT_NAME = os.getenv('TRANSFER_ACCOUNT_NAME', '')
    
    # Redis
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')
    ENABLE_CACHE = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR = os.getenv('LOG_DIR', 'logs')
    SENTRY_DSN = os.getenv('SENTRY_DSN', '')
    
    # Database
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/ferreteria.db')
    
    # Server
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8080))
    
    # Admin Dashboard
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    
    # Business Logic
    HOLD_MINUTES = int(os.getenv('HOLD_MINUTES', 30))
    LITE_MODE = os.getenv('LITE_MODE', 'false').lower() == 'true'
    ENABLE_DEBUG_COMMANDS = os.getenv('ENABLE_DEBUG_COMMANDS', 'false').lower() == 'true'
    
    # Features
    ENABLE_FRAUD_DETECTION = os.getenv('ENABLE_FRAUD_DETECTION', 'true').lower() == 'true'
    ENABLE_SENTIMENT_ANALYSIS = os.getenv('ENABLE_SENTIMENT_ANALYSIS', 'true').lower() == 'true'
    ENABLE_AB_TESTING = os.getenv('ENABLE_AB_TESTING', 'false').lower() == 'true'
    
    @classmethod
    def is_production(cls):
        """Check if running in production"""
        return os.getenv('ENVIRONMENT', 'development') == 'production'
    
    @classmethod
    def print_config(cls):
        """Print active configuration (sin secrets)"""
        print("=" * 60)
        print("BOT CONFIGURATION")
        print("=" * 60)
        print(f"OpenAI: {'✅ Configured' if cls.OPENAI_API_KEY else '❌ Missing'}")
        print(f"Gemini: {'✅ Configured' if cls.GEMINI_API_KEY else '❌ Missing'}")
        print(f"Email: {'✅ SMTP' if not cls.EMAIL_MOCK_MODE else '⚠️  Mock mode'}")
        print(f"Google Sheets: {'✅ API' if not cls.SHEETS_MOCK_MODE else '⚠️  Mock mode'}")
        print(f"WhatsApp: {'✅ ' + cls.WHATSAPP_PROVIDER.upper() if cls.WHATSAPP_PROVIDER != 'mock' else '⚠️  Mock mode'}")
        print(f"MercadoPago: {'✅ Configured' if not cls.MP_MOCK_MODE else '⚠️  Mock mode'}")
        print(f"Cache: {'✅ Enabled' if cls.ENABLE_CACHE else '❌ Disabled'}")
        print(f"Log Level: {cls.LOG_LEVEL}")
        print("=" * 60)

# Singleton
config = Config()

# Backward compatibility & Exports for bot_gemini.py
OPENAI_API_KEY = config.OPENAI_API_KEY
OPENAI_MODEL = config.OPENAI_MODEL
OPENAI_TEMPERATURE = 0.7
OPENAI_MAX_TOKENS = 1000
MAX_CONTEXT_MESSAGES = 10
HOLD_MINUTES = config.HOLD_MINUTES
LITE_MODE = config.LITE_MODE
ENABLE_DEBUG_COMMANDS = config.ENABLE_DEBUG_COMMANDS

# Gemini Exports
GEMINI_API_KEY = config.GEMINI_API_KEY
GEMINI_MODEL = config.GEMINI_MODEL

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILE = os.path.join(BASE_DIR, config.DATABASE_PATH)
CATALOG_CSV = os.path.join(BASE_DIR, 'config', 'catalog.csv')
POLICIES_FILE = os.path.join(BASE_DIR, 'config', 'policies.md')
LOG_PATH = os.path.join(BASE_DIR, config.LOG_DIR, 'bot.log')
