import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


DEFAULT_DATABASE_URL = "sqlite:///data/finalprod_local.db"
CANONICAL_RAILWAY_SERVICE = "ferreteria-bot"
UNSAFE_SECRET_VALUES = {
    "",
    "REDACTED",
    "MOCK_SECRET",
    "change-me",
    "changeme",
    "my_verify_token",
    "dev-secret-key-change-in-production",
}
UNSAFE_SECRET_VALUES_LOWER = {v.lower() for v in UNSAFE_SECRET_VALUES}


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_secret_value_configured(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return normalized not in UNSAFE_SECRET_VALUES and normalized.lower() not in UNSAFE_SECRET_VALUES_LOWER


def is_database_url_explicit(value: str | None, *, environ: dict[str, str] | None = None) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return False
    current_env = os.environ if environ is None else environ
    if (current_env.get("DATABASE_URL") or "").strip():
        return True
    return candidate != DEFAULT_DATABASE_URL


class Settings(BaseSettings):
    """Application configuration settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )
    
    # Railway-injected vars (prevents ValidationError on deploy)
    PORT: int = Field(default=8000)
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    OPENAI_MODEL: str = Field(default="gpt-4o")
    CANONICAL_RAILWAY_SERVICE: str = Field(default=CANONICAL_RAILWAY_SERVICE)
    RAILWAY_SERVICE_NAME: str = Field(default="")
    RAILWAY_PUBLIC_DOMAIN: str = Field(default="")
    RAILWAY_VOLUME_MOUNT_PATH: str = Field(default="")
    WHATSAPP_PROVIDER: str = Field(default="")
    
    # Database
    # Railway/production should set DATABASE_URL explicitly.
    # Local default enables zero-config bootstrapping for demos/onboarding.
    DATABASE_URL: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    
    # Flask
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production")
    
    # OpenAI
    OPENAI_API_KEY: str = Field(default="REDACTED")
    
    # MercadoPago
    MERCADOPAGO_ACCESS_TOKEN: str = Field(default="REDACTED")
    MERCADOPAGO_WEBHOOK_SECRET: str = Field(default="REDACTED")
    
    # Admin
    ADMIN_TOKEN: str = Field(default="REDACTED")

    # Tenant routing
    DEFAULT_TENANT_ID: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_TENANT_ID", os.getenv("BOT_TENANT_ID", ""))
    )
    
    # Google Sheets Stock Sync (NEW - Robust Implementation)
    GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON: str = Field(default="")  # Full JSON string from GCP
    GOOGLE_SHEETS_SERVICE_ACCOUNT_PATH: str = Field(default="")  # Or file path
    GOOGLE_SHEETS_SPREADSHEET_ID: str = Field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID") or os.getenv("GOOGLE_SHEET_ID", ""))
    GOOGLE_SHEETS_WORKSHEET_STOCK: str = Field(default="STOCK")  # Worksheet name
    
    # Legacy (keep for backward compat with old sync)
    GOOGLE_SHEETS_ENABLED: bool = Field(default=False)
    GOOGLE_SHEETS_CREDENTIALS_PATH: str = Field(default="")
    GOOGLE_SHEET_ID: str = Field(default="")

    # Meta Cloud API (WhatsApp + Instagram)
    META_VERIFY_TOKEN: str = Field(default="REDACTED")
    META_ACCESS_TOKEN: str = Field(default="REDACTED")
    META_APP_SECRET: str = Field(default="")
    WHATSAPP_PHONE_NUMBER_ID: str = Field(default="")
    IG_PAGE_ID: str = Field(default="")
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_WHATSAPP_NUMBER: str = Field(default="")

    # Email (SendGrid)
    SENDGRID_API_KEY: str = Field(default="REDACTED")
    EMAIL_FROM: str = Field(default="noreply@example.com")

    # CORS
    CORS_ORIGINS: str = Field(default="")

    # Business Logic
    HOLD_MINUTES: int = Field(default=15)
    STOCK_API_BATCH_ENDPOINT: str = Field(default="/api/stock/batch")
    PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE: int = Field(default=60)

    # CRM Module
    CRM_JWT_SECRET: str = Field(default="")
    CRM_JWT_TTL_MINUTES: int = Field(default=720)
    CRM_WEBHOOK_SECRET: str = Field(default="REDACTED")

    @staticmethod
    def is_secret_configured(value: str | None) -> bool:
        return is_secret_value_configured(value)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"production", "prod"}

    @property
    def has_explicit_database_url(self) -> bool:
        return is_database_url_explicit(self.DATABASE_URL)

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def whatsapp_provider(self) -> str:
        explicit = self.WHATSAPP_PROVIDER.strip().lower()
        if explicit:
            return explicit

        meta_ready = (
            self.is_secret_configured(self.META_VERIFY_TOKEN)
            and self.is_secret_configured(self.META_ACCESS_TOKEN)
            and bool(self.WHATSAPP_PHONE_NUMBER_ID.strip())
        )
        twilio_ready = bool(self.TWILIO_ACCOUNT_SID.strip() and self.TWILIO_AUTH_TOKEN.strip() and self.TWILIO_WHATSAPP_NUMBER.strip())
        if meta_ready:
            return "meta"
        if twilio_ready:
            return "twilio"
        return "mock"

_settings = None
_warnings_emitted = False


def _emit_security_warnings(settings: Settings) -> None:
    warnings = []
    if not settings.is_secret_configured(settings.ADMIN_TOKEN):
        warnings.append("ADMIN_TOKEN is not configured with a secure value.")
    if not settings.is_secret_configured(settings.MERCADOPAGO_WEBHOOK_SECRET):
        warnings.append("MERCADOPAGO_WEBHOOK_SECRET is not configured with a secure value.")
    if not settings.is_secret_configured(settings.META_VERIFY_TOKEN):
        warnings.append("META_VERIFY_TOKEN is not configured with a secure value.")
    if not settings.is_secret_configured(settings.CRM_WEBHOOK_SECRET):
        warnings.append("CRM_WEBHOOK_SECRET is not configured with a secure value.")

    if settings.is_production:
        if not settings.has_explicit_database_url:
            raise ValueError(
                "DATABASE_URL must be set explicitly in production. "
                "Do not rely on the local SQLite fallback."
            )
        if not settings.is_secret_configured(settings.SECRET_KEY):
            raise ValueError(
                "SECRET_KEY must be set to a secure random value in production. "
                "Set the SECRET_KEY environment variable."
            )
        if "*" in settings.cors_origins:
            warnings.append("CORS_ORIGINS is '*' in production. Restrict allowed origins.")
        if settings.whatsapp_provider == "mock":
            warnings.append("WHATSAPP_PROVIDER resolved to mock in production.")
        if any("ferreteria-bot-clean" in origin for origin in settings.cors_origins):
            warnings.append("CORS_ORIGINS references ferreteria-bot-clean; ferreteria-bot should be canonical.")
        if settings.RAILWAY_SERVICE_NAME and settings.RAILWAY_SERVICE_NAME != settings.CANONICAL_RAILWAY_SERVICE:
            warnings.append(
                f"RAILWAY_SERVICE_NAME={settings.RAILWAY_SERVICE_NAME} does not match canonical {settings.CANONICAL_RAILWAY_SERVICE}."
            )
        if is_truthy(os.getenv("ALLOW_LEGACY_FALLBACK")):
            raise ValueError("ALLOW_LEGACY_FALLBACK must be disabled in production.")

    if warnings:
        logger = logging.getLogger(__name__)
        for msg in warnings:
            logger.warning("config_warning: %s", msg)

def get_settings() -> Settings:
    global _settings, _warnings_emitted
    if _settings is None:
        _settings = Settings()
    if not _warnings_emitted:
        _emit_security_warnings(_settings)
        _warnings_emitted = True
    return _settings
