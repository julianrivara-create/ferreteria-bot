import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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
    
    # Database
    # Railway/production should set DATABASE_URL explicitly.
    # Local default enables zero-config bootstrapping for demos/onboarding.
    DATABASE_URL: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/finalprod_local.db")
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
        if value is None:
            return False
        normalized = value.strip()
        if not normalized:
            return False
        return normalized not in UNSAFE_SECRET_VALUES and normalized.lower() not in UNSAFE_SECRET_VALUES_LOWER

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"production", "prod"}

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

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
        if not settings.is_secret_configured(settings.SECRET_KEY):
            raise ValueError(
                "SECRET_KEY must be set to a secure random value in production. "
                "Set the SECRET_KEY environment variable."
            )
        if "*" in settings.cors_origins:
            warnings.append("CORS_ORIGINS is '*' in production. Restrict allowed origins.")

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
