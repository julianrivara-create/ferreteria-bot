"""Tenant profile loader and prompt renderer."""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False


class TenantConfig:
    """Tenant configuration wrapper used to render dynamic prompts."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        config_data: Optional[Dict[str, Any]] = None,
        prompts_dir: Optional[str] = None,
    ):
        base_dir = Path(__file__).parent.parent
        self.config_path = Path(config_path) if config_path else None

        if config_data is not None:
            self.config = self._normalize_profile(config_data)
        else:
            if self.config_path is None:
                self.config_path = base_dir / "data" / "tenant_config.yaml"
            self.config = self._normalize_profile(self._load_config_from_path(self.config_path))

        if prompts_dir:
            prompt_root = Path(prompts_dir)
        else:
            prompt_root = base_dir / "data" / "prompts"

        if HAS_JINJA2:
            self.jinja_env = Environment(
                loader=FileSystemLoader(prompt_root),
                autoescape=select_autoescape(),
            )
        else:
            self.jinja_env = None

    def _load_config_from_path(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return self._get_default_config()

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _normalize_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Support both legacy tenant_config.yaml and new profile.yaml shape."""
        if not data:
            return self._get_default_config()

        business = data.get("business", {}) if isinstance(data.get("business"), dict) else {}
        personality = data.get("personality", {}) if isinstance(data.get("personality"), dict) else {}

        merged = {
            "store_name": data.get("store_name") or business.get("name") or "TechStore",
            "store_description": data.get("store_description") or business.get("description") or "Tienda",
            "store_type": data.get("store_type") or business.get("industry") or "general",
            "country": data.get("country") or business.get("country") or "Argentina",
            "personality_style": data.get("personality_style") or personality.get("tone") or "Profesional",
            "emojis": data.get("emojis") or personality.get("emojis") or "✅",
            "target_audience": data.get("target_audience") or business.get("target_audience") or "clientes",
            "product_categories": data.get("product_categories") or business.get("visible_categories") or ["productos"],
            "cross_sell_rules": data.get("cross_sell_rules") or business.get("cross_sell_rules") or [],
            "comparison_features": data.get("comparison_features") or ["price_ars", "category"],
            "enable_upselling": data.get("enable_upselling", True),
            "enable_crossselling": data.get("enable_crossselling", True),
            "hold_minutes": data.get("hold_minutes", 30),
            "placeholder_names": data.get("placeholder_names")
            or ["juan", "juan perez", "ejemplo", "usuario", "cliente", "example", "test"],
            "placeholder_phones": data.get("placeholder_phones") or ["123456", "1111111", "0000000"],
        }

        return merged

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            "store_name": "TechStore",
            "store_description": "Tienda de Tecnología",
            "store_type": "tecnología",
            "country": "Argentina",
            "personality_style": "Argentino informal (vos, che, dale, etc.)",
            "emojis": "📱 💳 ✅",
            "target_audience": "Compradores",
            "product_categories": ["productos"],
            "cross_sell_rules": [],
            "comparison_features": ["price_ars", "category"],
            "enable_upselling": True,
            "enable_crossselling": True,
            "hold_minutes": 30,
            "placeholder_names": ["juan", "juan perez", "ejemplo", "usuario", "cliente", "example", "test"],
            "placeholder_phones": ["123456", "1111111", "0000000"],
        }

    def get(self, key: str, default: Any = None):
        return self.config.get(key, default)

    def render_prompt(self, template_name: str = "template_v2.j2", policies: str = "") -> str:
        if not self.jinja_env:
            return (
                f"Sos un vendedor de {self.config['store_name']}.\n"
                f"Vendés: {', '.join(self.config['product_categories'])}.\n"
                "Usá las funciones disponibles para ayudar al cliente.\n\n"
                f"POLÍTICAS:\n{policies}\n"
            )

        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(
                store_name=self.config.get("store_name", "Store"),
                store_description=self.config.get("store_description", ""),
                personality_style=self.config.get("personality_style", "Informal"),
                emojis=self.config.get("emojis", ""),
                product_categories=self.config.get("product_categories", []),
                policies=policies,
            )
        except Exception:
            return (
                f"Sos un asesor de ventas para {self.config.get('store_name', 'Store')}.\n"
                f"Categorías: {', '.join(self.config.get('product_categories', ['productos']))}.\n"
                "Nunca inventes stock o precios.\n\n"
                f"POLÍTICAS:\n{policies}"
            )

    def get_cross_sell_rules(self) -> list:
        return self.config.get("cross_sell_rules", [])

    def get_comparison_features(self) -> list:
        return self.config.get("comparison_features", ["price_ars", "category"])

    def get_placeholder_names(self) -> list:
        return self.config.get("placeholder_names", ["juan", "juan perez", "ejemplo", "usuario", "cliente", "example", "test"])

    def get_placeholder_phones(self) -> list:
        return self.config.get("placeholder_phones", ["123456", "1111111", "0000000"])


# Path/data keyed cache for lightweight reuse.
_config_cache: Dict[str, TenantConfig] = {}


def get_tenant_config(config_path: Optional[str] = None, config_data: Optional[Dict[str, Any]] = None) -> TenantConfig:
    """Get tenant config from data or cached path."""
    if config_data is not None:
        return TenantConfig(config_data=config_data)

    cache_key = str(config_path or "__default__")
    if cache_key not in _config_cache:
        _config_cache[cache_key] = TenantConfig(config_path=config_path)
    return _config_cache[cache_key]
