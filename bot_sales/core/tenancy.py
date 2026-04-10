import os
import re
import yaml
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import Database
from ..config import BASE_DIR, LOG_PATH

logger = logging.getLogger(__name__)


@dataclass
class TenantConfig:
    """Configuration for a single tenant."""

    id: str
    name: str
    phone_numbers: List[str]
    db_file: str = "data/default.db"
    catalog_file: str = "config/catalog.csv"
    api_keys: Dict[str, str] = field(default_factory=dict)
    features: Dict[str, bool] = field(default_factory=dict)

    # New multi-industry metadata
    slug: str = ""
    profile_path: str = ""
    policies_file: str = "config/policies.md"
    branding_file: str = ""
    profile: Dict[str, Any] = field(default_factory=dict)
    whatsapp_phone_number_id: str = ""
    ig_page_id: str = ""

    def get_api_key(self, service: str) -> str:
        """Get API key for a service."""
        return self.api_keys.get(service, "")

    def get_slug(self) -> str:
        return self.slug or self.id


class TenantManager:
    """Manages tenant configurations and tenant-scoped resources."""

    def __init__(self, config_path: str = "tenants.yaml"):
        self.config_path = config_path
        self.tenants: Dict[str, TenantConfig] = {}
        self.slug_map: Dict[str, str] = {}  # slug -> tenant_id
        self.phone_map: Dict[str, str] = {}  # phone -> tenant_id
        self.phone_number_id_map: Dict[str, str] = {}  # whatsapp_phone_number_id -> tenant_id
        self.ig_page_id_map: Dict[str, str] = {}  # ig_page_id -> tenant_id
        self._db_cache: Dict[str, Database] = {}
        self._bot_cache: Dict[str, Any] = {}
        self._load_config()

    def _resolve_path(self, value: str) -> Path:
        p = Path(value)
        if p.is_absolute():
            return p
        return Path(BASE_DIR) / p

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        if not phone:
            return ""
        return re.sub(r"\D", "", phone)

    def _load_profile(self, profile_path: str) -> Dict[str, Any]:
        path = self._resolve_path(profile_path)
        if not path.exists():
            logger.warning("Tenant profile not found: %s", path)
            return {}

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    def _load_config(self):
        """Load tenants from YAML index with env-var substitution."""
        path = self._resolve_path(self.config_path)

        if not path.exists():
            logger.error("Tenant config file not found: %s", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            content_expanded = os.path.expandvars(content)
            data = yaml.safe_load(content_expanded) or {}

            for t_data in data.get("tenants", []):
                profile_path = t_data.get("profile_path", "")
                profile = self._load_profile(profile_path) if profile_path else {}
                paths = profile.get("paths", {}) if isinstance(profile, dict) else {}

                tenant_id = t_data.get("id") or profile.get("id") or profile.get("slug")
                if not tenant_id:
                    logger.warning("Skipping tenant entry without id: %s", t_data)
                    continue

                slug = t_data.get("slug") or profile.get("slug") or tenant_id
                name = t_data.get("name") or profile.get("business", {}).get("name") or tenant_id

                phones = t_data.get("phone_numbers")
                if not phones:
                    phones = (
                        profile.get("communication", {}).get("whatsapp_numbers")
                        or profile.get("phone_numbers")
                        or []
                    )

                wa_phone_number_id = t_data.get("whatsapp_phone_number_id") or ""
                ig_page_id = t_data.get("ig_page_id") or ""

                tenant = TenantConfig(
                    id=tenant_id,
                    slug=slug,
                    name=name,
                    phone_numbers=phones,
                    db_file=t_data.get("db_file") or paths.get("db") or f"data/{slug}.db",
                    catalog_file=t_data.get("catalog_file") or paths.get("catalog") or "config/catalog.csv",
                    policies_file=t_data.get("policies_file") or paths.get("policies") or "config/policies.md",
                    branding_file=t_data.get("branding_file") or paths.get("branding") or "",
                    profile_path=profile_path,
                    profile=profile,
                    api_keys=t_data.get("api_keys", {}),
                    features=t_data.get("features", {}),
                    whatsapp_phone_number_id=wa_phone_number_id,
                    ig_page_id=ig_page_id,
                )

                self.tenants[tenant.id] = tenant
                self.slug_map[tenant.get_slug()] = tenant.id

                for phone in tenant.phone_numbers:
                    self.phone_map[phone] = tenant.id

                if wa_phone_number_id:
                    self.phone_number_id_map[wa_phone_number_id] = tenant.id

                if ig_page_id:
                    self.ig_page_id_map[ig_page_id] = tenant.id

            logger.info("Loaded %d tenants", len(self.tenants))

        except Exception as exc:
            logger.error("Error loading tenant config: %s", exc)
            raise

    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        return self.tenants.get(tenant_id)

    def get_tenant_by_slug(self, slug: str) -> Optional[TenantConfig]:
        if not slug:
            return self.get_default_tenant()
        tenant_id = self.slug_map.get(slug)
        if tenant_id:
            return self.tenants.get(tenant_id)
        return self.tenants.get(slug)

    def get_tenant_by_phone_number_id(self, phone_number_id: str) -> Optional[TenantConfig]:
        """Find tenant by WhatsApp phone_number_id (from Meta webhook metadata)."""
        tenant_id = self.phone_number_id_map.get(phone_number_id or "")
        return self.tenants.get(tenant_id) if tenant_id else None

    def get_tenant_by_ig_page_id(self, ig_page_id: str) -> Optional[TenantConfig]:
        """Find tenant by Instagram page ID (from Meta webhook entry.id)."""
        tenant_id = self.ig_page_id_map.get(ig_page_id or "")
        return self.tenants.get(tenant_id) if tenant_id else None

    def resolve_tenant_by_phone(self, phone: str) -> Optional[TenantConfig]:
        """Find tenant by incoming phone number with strict + normalized fallback."""
        tenant_id = self.phone_map.get(phone)
        if tenant_id:
            return self.tenants.get(tenant_id)

        normalized = self._normalize_phone(phone)
        if not normalized:
            return None

        for raw, tid in self.phone_map.items():
            raw_normalized = self._normalize_phone(raw)
            if raw_normalized and (raw_normalized.endswith(normalized) or normalized.endswith(raw_normalized)):
                return self.tenants.get(tid)

        return None

    def get_default_tenant(self) -> Optional[TenantConfig]:
        if not self.tenants:
            return None

        if "default_tenant" in self.tenants:
            return self.tenants["default_tenant"]

        if "default" in self.slug_map:
            return self.tenants[self.slug_map["default"]]

        return next(iter(self.tenants.values()))

    def get_db(self, tenant_id: str) -> Database:
        if tenant_id in self._db_cache:
            return self._db_cache[tenant_id]

        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")

        db_path = self._resolve_path(tenant.db_file)
        catalog_path = self._resolve_path(tenant.catalog_file)

        os.makedirs(db_path.parent, exist_ok=True)

        db = Database(
            str(db_path),
            str(catalog_path),
            LOG_PATH,
            api_key=tenant.get_api_key("openai"),
        )
        self._db_cache[tenant_id] = db
        return db

    def get_bot(self, tenant_id: str) -> Any:
        """Get (or create) tenant-scoped bot instance."""
        if tenant_id in self._bot_cache:
            return self._bot_cache[tenant_id]

        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")

        db = self.get_db(tenant_id)

        openai_key = tenant.get_api_key("openai")

        # Build prompt/profile context for this tenant instance
        prompt_context = dict(tenant.profile or {})
        prompt_context.setdefault("id", tenant.id)
        prompt_context.setdefault("slug", tenant.get_slug())
        prompt_context.setdefault("name", tenant.name)
        prompt_context.setdefault("paths", {})
        prompt_context["paths"].setdefault("policies", tenant.policies_file)

        from ..bot import SalesBot

        bot = SalesBot(
            db=db,
            api_key=openai_key,
            tenant_id=tenant.id,
            tenant_profile=prompt_context,
        )
        logger.info("Initialized SalesBot (OpenAI/GPT) for tenant %s", tenant_id)

        self._bot_cache[tenant_id] = bot
        return bot

    def reload(self):
        """Reload tenant definitions and clear caches."""
        self.close_all()
        self.tenants.clear()
        self.slug_map.clear()
        self.phone_map.clear()
        self._load_config()

    def close_all(self):
        for db in self._db_cache.values():
            db.close()
        self._db_cache.clear()
        self._bot_cache.clear()


# Module-level singleton used by connectors and tests.
tenant_manager = TenantManager()
