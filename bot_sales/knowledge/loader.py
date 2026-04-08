"""Tenant knowledge loader with lightweight file-backed caching."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .defaults import (
    DEFAULT_ACCEPTANCE_PATTERNS,
    DEFAULT_BLOCKED_TERMS,
    DEFAULT_CLARIFICATION_RULES,
    DEFAULT_COMPLEMENTARY_RULES,
    DEFAULT_FAQ_FALLBACK_PATH,
    DEFAULT_FAMILY_RULES,
    DEFAULT_LANGUAGE_PATTERNS,
    DEFAULT_SUBSTITUTE_RULES,
    DEFAULT_SYNONYM_ENTRIES,
)
from .validators import (
    KnowledgeValidationError,
    validate_acceptance_patterns,
    validate_blocked_terms,
    validate_clarification_rules,
    validate_complementary_rules,
    validate_faqs,
    validate_family_rules,
    validate_language_patterns,
    validate_substitute_rules,
    validate_synonyms,
)


class KnowledgeLoader:
    """Load tenant-editable ferreteria knowledge from YAML files."""

    def __init__(self, tenant_id: str = "ferreteria", tenant_profile: Optional[Dict[str, Any]] = None):
        self.tenant_id = tenant_id
        self.tenant_profile = tenant_profile or {}
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_mtimes: Dict[str, float] = {}
        self.base_dir = self._resolve_base_dir()

    def _resolve_base_dir(self) -> Path:
        profile_paths = self.tenant_profile.get("paths", {}) if isinstance(self.tenant_profile, dict) else {}
        catalog = profile_paths.get("catalog")
        if catalog:
            catalog_path = Path(catalog)
            if not catalog_path.is_absolute():
                catalog_path = Path(__file__).resolve().parents[2] / catalog_path
            return catalog_path.parent / "knowledge"
        return Path(__file__).resolve().parents[2] / "data" / "tenants" / self.tenant_id / "knowledge"

    def _path(self, filename: str) -> Path:
        return self.base_dir / filename

    @staticmethod
    def _backup_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.bak")

    def _read_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise KnowledgeValidationError(f"{path.name} must contain a mapping")
        return data

    def _read_fallback_faqs(self) -> Dict[str, Any]:
        faq_path = Path(__file__).resolve().parents[2] / DEFAULT_FAQ_FALLBACK_PATH
        if not faq_path.exists():
            return {"entries": []}
        raw = json.loads(faq_path.read_text(encoding="utf-8"))
        entries = []
        for faq_id, data in (raw.get("preguntas_frecuentes", {}) or {}).items():
            entries.append({
                "id": faq_id,
                "question": str(data.get("pregunta", "")).strip(),
                "answer": str(data.get("respuesta", "")).strip(),
                "keywords": [str(x).strip() for x in data.get("keywords", []) if str(x).strip()],
                "active": True,
                "tags": [],
            })
        return {"entries": entries}

    @staticmethod
    def _merge_rules_by_key(defaults: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = deepcopy(defaults)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _merge_entries_by_key(defaults: list[Dict[str, Any]], override: list[Dict[str, Any]], key_field: str) -> list[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {
            str(entry.get(key_field)): deepcopy(entry)
            for entry in defaults
            if entry.get(key_field)
        }
        for entry in override:
            key = str(entry.get(key_field) or "").strip()
            if not key:
                continue
            if isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **entry}
            else:
                merged[key] = deepcopy(entry)
        return list(merged.values())

    def _current_mtimes(self) -> Dict[str, float]:
        files = (
            "synonyms.yaml",
            "clarification_rules.yaml",
            "family_rules.yaml",
            "blocked_terms.yaml",
            "complementary_rules.yaml",
            "substitute_rules.yaml",
            "language_patterns.yaml",
            "acceptance_patterns.yaml",
            "faqs.yaml",
        )
        mtimes = {}
        for filename in files:
            path = self._path(filename)
            mtimes[filename] = path.stat().st_mtime if path.exists() else -1.0
        return mtimes

    def invalidate(self) -> None:
        self._cache = None
        self._cache_mtimes = {}

    def get_paths(self) -> Dict[str, str]:
        return {
            "synonyms": str(self._path("synonyms.yaml")),
            "clarifications": str(self._path("clarification_rules.yaml")),
            "families": str(self._path("family_rules.yaml")),
            "blocked_terms": str(self._path("blocked_terms.yaml")),
            "complementary": str(self._path("complementary_rules.yaml")),
            "substitute_rules": str(self._path("substitute_rules.yaml")),
            "language_patterns": str(self._path("language_patterns.yaml")),
            "acceptance": str(self._path("acceptance_patterns.yaml")),
            "faqs": str(self._path("faqs.yaml")),
        }

    def load(self, force: bool = False) -> Dict[str, Any]:
        mtimes = self._current_mtimes()
        if not force and self._cache is not None and mtimes == self._cache_mtimes:
            return deepcopy(self._cache)

        families_yaml = self._read_yaml(self._path("family_rules.yaml"))
        families_payload = {
            "families": self._merge_rules_by_key(
                DEFAULT_FAMILY_RULES,
                (families_yaml or {}).get("families", {}),
            )
        }
        families = validate_family_rules(families_payload)

        synonym_payload = self._read_yaml(self._path("synonyms.yaml")) or {"entries": DEFAULT_SYNONYM_ENTRIES}

        clarification_yaml = self._read_yaml(self._path("clarification_rules.yaml"))
        clarification_payload = {
            "rules": self._merge_rules_by_key(
                DEFAULT_CLARIFICATION_RULES,
                (clarification_yaml or {}).get("rules", {}),
            )
        }

        blocked_yaml = self._read_yaml(self._path("blocked_terms.yaml"))
        blocked_payload = {
            "terms": self._merge_entries_by_key(
                DEFAULT_BLOCKED_TERMS,
                (blocked_yaml or {}).get("terms", []),
                "term",
            )
        }

        complementary_yaml = self._read_yaml(self._path("complementary_rules.yaml"))
        complementary_payload = {
            "rules": self._merge_rules_by_key(
                DEFAULT_COMPLEMENTARY_RULES,
                (complementary_yaml or {}).get("rules", {}),
            )
        }

        knowledge = {
            "tenant_id": self.tenant_id,
            "synonyms": validate_synonyms(synonym_payload),
            "families": families,
            "clarifications": validate_clarification_rules(
                clarification_payload,
                family_rules=families["families"],
            ),
            "blocked_terms": validate_blocked_terms(blocked_payload),
            "complementary": validate_complementary_rules(complementary_payload),
            "substitute_rules": validate_substitute_rules(
                self._read_yaml(self._path("substitute_rules.yaml")) or DEFAULT_SUBSTITUTE_RULES,
                family_rules=families["families"],
            ),
            "language_patterns": validate_language_patterns(
                self._read_yaml(self._path("language_patterns.yaml")) or DEFAULT_LANGUAGE_PATTERNS
            ),
            "acceptance": validate_acceptance_patterns(self._read_yaml(self._path("acceptance_patterns.yaml")) or DEFAULT_ACCEPTANCE_PATTERNS),
            "faqs": validate_faqs(self._read_yaml(self._path("faqs.yaml")) or self._read_fallback_faqs()),
        }

        self._cache = deepcopy(knowledge)
        self._cache_mtimes = mtimes
        return knowledge

    def get_domain(self, domain: str) -> Dict[str, Any]:
        data = self.load()
        return deepcopy(data.get(domain, {}))

    def _write_yaml_atomically(self, path: Path, payload: Dict[str, Any]) -> None:
        rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)

            if path.exists():
                shutil.copy2(path, self._backup_path(path))

            temp_path.replace(path)
        except OSError as exc:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise KnowledgeValidationError(
                f"Could not safely write {path.name}: {exc}"
            ) from exc

    def save_domain(
        self,
        domain: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.base_dir.mkdir(parents=True, exist_ok=True)

        if domain == "synonyms":
            validated = validate_synonyms(payload)
            path = self._path("synonyms.yaml")
        elif domain == "clarifications":
            families = self.get_domain("families").get("families", {})
            validated = validate_clarification_rules(payload, family_rules=families)
            path = self._path("clarification_rules.yaml")
        elif domain == "families":
            validated = validate_family_rules(payload)
            path = self._path("family_rules.yaml")
        elif domain == "blocked_terms":
            validated = validate_blocked_terms(payload)
            path = self._path("blocked_terms.yaml")
        elif domain == "complementary":
            validated = validate_complementary_rules(payload)
            path = self._path("complementary_rules.yaml")
        elif domain == "substitute_rules":
            families = self.get_domain("families").get("families", {})
            validated = validate_substitute_rules(payload, family_rules=families)
            path = self._path("substitute_rules.yaml")
        elif domain == "language_patterns":
            validated = validate_language_patterns(payload)
            path = self._path("language_patterns.yaml")
        elif domain == "acceptance":
            validated = validate_acceptance_patterns(payload)
            path = self._path("acceptance_patterns.yaml")
        elif domain == "faqs":
            validated = validate_faqs(payload)
            path = self._path("faqs.yaml")
        else:
            raise KnowledgeValidationError(f"Unknown knowledge domain: {domain}")

        try:
            self._write_yaml_atomically(path, validated)
        except KnowledgeValidationError:
            raise
        except Exception as exc:
            raise KnowledgeValidationError(
                f"Could not persist {domain} knowledge: {exc}"
            ) from exc
        self.invalidate()
        return validated
