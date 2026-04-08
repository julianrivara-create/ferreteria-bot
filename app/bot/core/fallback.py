
"""
Fallback Service
Handles basic FAQ responses when the main LLM is unavailable (offline/no credits).
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import unicodedata

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_TENANTS_DIR = Path(__file__).resolve().parents[3] / "data" / "tenants"


class FallbackService:
    def __init__(self, faq_path: str = None):
        if faq_path is None:
            faq_path = str(_DATA_DIR / "fallback_faq.json")

        self.faq_data = self._load_faq(faq_path)

    def _load_faq(self, path: str) -> Dict[str, Any]:
        """Load FAQ data from JSON file"""
        try:
            if not os.path.exists(path):
                logging.warning(f"Fallback FAQ file not found at {path}")
                return {"faq": [], "default_response": "Servicio no disponible momentáneamente."}

            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading Fallback FAQ: {e}")
            return {"faq": [], "default_response": "Error interno en servicio de respaldo."}

    def get_response(self, user_input: str) -> str:
        """Get a fallback response based on keywords match"""
        if not user_input:
            return self.faq_data.get("default_response", "")

        text = self._normalize(user_input)

        for item in self.faq_data.get("faq", []):
            for keyword in item.get("keywords", []):
                if self._normalize(keyword) in text:
                    return item.get("answer", "")

        return self.faq_data.get("default_response", "")

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(text or ""))
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        return normalized.lower().strip()


# Per-tenant cache (tenant_id → FallbackService instance)
_fallback_cache: Dict[str, FallbackService] = {}


def _tenant_faq_path(tenant_id: str) -> Optional[str]:
    """Look for a tenant-specific fallback_faq.json in data/tenants/<id>/."""
    if not tenant_id:
        return None
    candidate = _TENANTS_DIR / tenant_id / "fallback_faq.json"
    return str(candidate) if candidate.exists() else None


def get_fallback_service(tenant_id: str = "") -> FallbackService:
    """Return a tenant-scoped FallbackService, falling back to the default."""
    cache_key = tenant_id or "__default__"
    if cache_key not in _fallback_cache:
        path = _tenant_faq_path(tenant_id) if tenant_id else None
        _fallback_cache[cache_key] = FallbackService(faq_path=path)
    return _fallback_cache[cache_key]
