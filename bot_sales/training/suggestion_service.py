from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales.knowledge.validators import KnowledgeValidationError

from .store import TrainingStore


class TrainingSuggestionService:
    _ALLOWED_TRANSITIONS = {
        "draft": {"approved", "rejected"},
        "approved": {"applied"},
        "rejected": set(),
        "applied": set(),
    }

    def __init__(self, store: TrainingStore, loader: KnowledgeLoader):
        self.store = store
        self.loader = loader

    def create_suggestion(
        self,
        *,
        review_id: str,
        domain: str,
        summary: Optional[str],
        source_message: Optional[str],
        repeated_term: Optional[str],
        suggested_payload: Dict[str, Any],
        created_by: Optional[str],
    ) -> Dict[str, Any]:
        self._validate_payload(domain, suggested_payload)
        return self.store.create_suggestion(
            review_id=review_id,
            domain=domain,
            summary=summary,
            source_message=source_message,
            repeated_term=repeated_term,
            suggested_payload=suggested_payload,
            created_by=created_by,
        )

    # Alias for API routes that call .create() instead of .create_suggestion()
    def create(
        self,
        *,
        review_id: str,
        domain: str,
        summary: Optional[str],
        source_message: Optional[str],
        repeated_term: Optional[str],
        suggested_payload: Dict[str, Any],
        created_by: Optional[str],
    ) -> Dict[str, Any]:
        """Alias for create_suggestion — maintained for backward compatibility."""
        return self.create_suggestion(
            review_id=review_id,
            domain=domain,
            summary=summary,
            source_message=source_message,
            repeated_term=repeated_term,
            suggested_payload=suggested_payload,
            created_by=created_by,
        )

    def list_suggestions(self, **filters: Any) -> list[Dict[str, Any]]:
        return self.store.list_suggestions(**filters)

    def get_suggestion(self, suggestion_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_suggestion(suggestion_id)

    def approve(self, suggestion_id: str, *, acted_by: Optional[str], reason: Optional[str] = None) -> Dict[str, Any]:
        suggestion = self._must_get(suggestion_id)
        self._assert_transition(suggestion, "approved")
        with self.store.transaction():
            self.store.update_suggestion(suggestion_id, status="approved")
            self.store.add_approval(
                suggestion_id,
                action="approve",
                acted_by=acted_by,
                reason=reason,
                before={"status": suggestion["status"]},
                after={"status": "approved"},
            )
        return self._must_get(suggestion_id)

    def reject(self, suggestion_id: str, *, acted_by: Optional[str], reason: Optional[str] = None) -> Dict[str, Any]:
        suggestion = self._must_get(suggestion_id)
        self._assert_transition(suggestion, "rejected")
        with self.store.transaction():
            self.store.update_suggestion(suggestion_id, status="rejected")
            self.store.add_approval(
                suggestion_id,
                action="reject",
                acted_by=acted_by,
                reason=reason,
                before={"status": suggestion["status"]},
                after={"status": "rejected"},
            )
        return self._must_get(suggestion_id)

    def apply(self, suggestion_id: str, *, acted_by: Optional[str], reason: Optional[str] = None) -> Dict[str, Any]:
        suggestion = self._must_get(suggestion_id)
        self._assert_transition(suggestion, "applied")
        before, after, target_domain, entity_key = self._apply_to_knowledge(suggestion)
        with self.store.transaction():
            self.store.update_suggestion(suggestion_id, status="applied")
            self.store.add_approval(
                suggestion_id,
                action="apply",
                acted_by=acted_by,
                reason=reason,
                before=before,
                after=after,
            )
            self.store.record_knowledge_change(
                domain=target_domain,
                entity_key=entity_key,
                action="update",
                before=before,
                after=after,
                changed_by=acted_by,
                change_reason=reason or f"applied training suggestion {suggestion_id}",
            )
        return self._must_get(suggestion_id)

    def export_regression_case(self, review_id: str, *, exported_by: Optional[str]) -> Dict[str, Any]:
        detail = self.store.get_case_detail(review_id)
        if not detail:
            raise KnowledgeValidationError("Training case not found")
        payload = {
            "user_input": detail.get("user_input"),
            "expected_answer": detail.get("expected_answer") or detail.get("bot_response"),
            "review_label": detail.get("review_label"),
            "route_source": detail.get("route_source"),
            "suggested_family": detail.get("suggested_family"),
            "suggested_canonical_product": detail.get("suggested_canonical_product"),
        }
        fixture_name = f"training_case_{review_id[:8]}"
        return self.store.create_regression_export(
            review_id=review_id,
            fixture_name=fixture_name,
            export_format="json",
            payload=payload,
            exported_by=exported_by,
        )

    def create_regression_candidate(
        self,
        review_id: str,
        *,
        created_by: Optional[str],
        payload_override: Optional[Dict[str, Any]] = None,
        status: str = "draft",
    ) -> Dict[str, Any]:
        detail = self.store.get_case_detail(review_id)
        if not detail:
            raise KnowledgeValidationError("Training case not found")
        payload = {
            "user_input": detail.get("user_input"),
            "expected_answer": detail.get("expected_answer") or detail.get("bot_response"),
            "review_label": detail.get("review_label"),
            "route_source": detail.get("route_source"),
            "suggested_family": detail.get("suggested_family"),
            "suggested_canonical_product": detail.get("suggested_canonical_product"),
        }
        if payload_override:
            payload.update(payload_override)
        fixture_name = f"candidate_{review_id[:8]}"
        return self.store.create_regression_candidate(
            review_id=review_id,
            fixture_name=fixture_name,
            payload=payload,
            created_by=created_by,
            status=status,
        )

    def _validate_payload(self, domain: str, payload: Dict[str, Any]) -> None:
        domain = str(domain or "").strip()
        if domain == "synonym":
            if not str(payload.get("canonical") or "").strip():
                raise KnowledgeValidationError("synonym suggestion requires canonical")
            aliases = payload.get("aliases")
            if not isinstance(aliases, list) or not [value for value in aliases if str(value).strip()]:
                raise KnowledgeValidationError("synonym suggestion requires at least one alias")
            return
        if domain == "faq":
            if not str(payload.get("id") or "").strip():
                raise KnowledgeValidationError("faq suggestion requires id")
            if not str(payload.get("question") or "").strip():
                raise KnowledgeValidationError("faq suggestion requires question")
            if not str(payload.get("answer") or "").strip():
                raise KnowledgeValidationError("faq suggestion requires answer")
            keywords = payload.get("keywords")
            if not isinstance(keywords, list) or not [value for value in keywords if str(value).strip()]:
                raise KnowledgeValidationError("faq suggestion requires keywords")
            return
        if domain == "clarification_rule":
            if not str(payload.get("family") or "").strip():
                raise KnowledgeValidationError("clarification suggestion requires family")
            if not str(payload.get("prompt") or "").strip():
                raise KnowledgeValidationError("clarification suggestion requires prompt")
            return
        if domain == "family_rule":
            if not str(payload.get("family") or payload.get("family_id") or "").strip():
                raise KnowledgeValidationError("family rule suggestion requires family")
            categories = payload.get("allowed_categories")
            if not isinstance(categories, list) or not [value for value in categories if str(value).strip()]:
                raise KnowledgeValidationError("family rule suggestion requires allowed_categories")
            return
        if domain == "blocked_term":
            if not str(payload.get("term") or "").strip():
                raise KnowledgeValidationError("blocked term suggestion requires term")
            if not str(payload.get("reason") or "").strip():
                raise KnowledgeValidationError("blocked term suggestion requires reason")
            return
        if domain == "complementary_rule":
            if not str(payload.get("source") or "").strip():
                raise KnowledgeValidationError("complementary suggestion requires source")
            targets = payload.get("targets")
            if not isinstance(targets, list) or not [value for value in targets if str(value).strip()]:
                raise KnowledgeValidationError("complementary suggestion requires targets")
            return
        if domain == "substitute_rule":
            if not str(payload.get("group_id") or "").strip():
                raise KnowledgeValidationError("substitute rule suggestion requires group_id")
            for field in ("source_families", "allowed_targets"):
                value = payload.get(field)
                if not isinstance(value, list) or not [entry for entry in value if str(entry).strip()]:
                    raise KnowledgeValidationError(f"substitute rule suggestion requires {field}")
            return
        if domain == "language_pattern":
            if not str(payload.get("section") or "").strip():
                raise KnowledgeValidationError("language pattern suggestion requires section")
            if not str(payload.get("key") or "").strip():
                raise KnowledgeValidationError("language pattern suggestion requires key")
            return
        if domain == "unresolved_term_mapping":
            resolution_type = str(payload.get("resolution_type") or "").strip()
            if resolution_type == "blocked_term":
                self._validate_payload("blocked_term", payload)
                return
            if resolution_type == "language_pattern":
                self._validate_payload("language_pattern", payload)
                return
            self._validate_payload("synonym", payload)
            return
        if domain == "test_case_only":
            if not str(payload.get("user_input") or "").strip():
                raise KnowledgeValidationError("test_case_only suggestion requires user_input")
            if not str(payload.get("expected_answer") or "").strip():
                raise KnowledgeValidationError("test_case_only suggestion requires expected_answer")
            return
        raise KnowledgeValidationError(f"Unsupported suggestion domain: {domain}")

    def _apply_to_knowledge(self, suggestion: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = str(suggestion.get("domain") or "").strip()
        payload = deepcopy(suggestion.get("suggested_payload") or {})
        if domain == "synonym":
            return self._apply_synonym(payload)
        if domain == "faq":
            return self._apply_faq(payload)
        if domain == "clarification_rule":
            return self._apply_clarification(payload)
        if domain == "blocked_term":
            return self._apply_blocked_term(payload)
        if domain == "complementary_rule":
            return self._apply_complementary(payload)
        if domain == "family_rule":
            return self._apply_family_rule(payload)
        if domain == "language_pattern":
            return self._apply_language_pattern(payload)
        if domain == "substitute_rule":
            return self._apply_substitute_rule(payload)
        if domain == "unresolved_term_mapping":
            resolution_type = str(payload.get("resolution_type") or "").strip()
            if resolution_type == "blocked_term":
                return self._apply_blocked_term(payload)
            if resolution_type == "language_pattern":
                return self._apply_language_pattern(payload)
            return self._apply_synonym(payload)
        if domain == "test_case_only":
            raise KnowledgeValidationError("test_case_only suggestions do not modify active knowledge")
        raise KnowledgeValidationError(f"Unsupported suggestion domain: {domain}")

    def _apply_synonym(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "synonyms"
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        entries = after.setdefault("entries", [])
        canonical = str(payload.get("canonical") or "").strip()
        aliases = [str(value).strip() for value in payload.get("aliases", []) if str(value).strip()]
        family = str(payload.get("family") or "").strip() or canonical
        if not canonical or not aliases:
            raise KnowledgeValidationError("synonym suggestion requires canonical and aliases")
        for entry in entries:
            if str(entry.get("canonical") or "").strip().lower() == canonical.lower():
                merged = []
                seen = set()
                for alias in [*entry.get("aliases", []), *aliases]:
                    key = str(alias).strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        merged.append(str(alias).strip())
                entry["aliases"] = merged
                entry["family"] = family
                saved = self.loader.save_domain(domain, after)
                return before, saved, domain, canonical
        entries.append(
            {
                "canonical": canonical,
                "family": family,
                "aliases": aliases,
                "misspellings": payload.get("misspellings") or [],
                "brand_generic": bool(payload.get("brand_generic", False)),
                "maps_dimensions": payload.get("maps_dimensions") or {},
                "context_terms": payload.get("context_terms") or [],
            }
        )
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, canonical

    def _apply_faq(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "faqs"
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        entries = after.setdefault("entries", [])
        faq_id = str(payload.get("id") or "").strip()
        if not faq_id:
            raise KnowledgeValidationError("faq suggestion requires id")
        updated = False
        for index, entry in enumerate(entries):
            if str(entry.get("id") or "").strip() == faq_id:
                entries[index] = payload
                updated = True
                break
        if not updated:
            entries.append(payload)
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, faq_id

    def _apply_clarification(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "clarifications"
        family = str(payload.get("family") or "").strip()
        if not family:
            raise KnowledgeValidationError("clarification suggestion requires family")
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        rules = after.setdefault("rules", {})
        rules[family] = {
            "prompt": payload.get("prompt"),
            "short_prompt": payload.get("short_prompt") or payload.get("prompt"),
            "examples": payload.get("examples") or [],
            "required_dimensions": payload.get("required_dimensions") or [],
            "question_order": payload.get("question_order") or [],
            "prompt_by_missing_dimensions": payload.get("prompt_by_missing_dimensions") or {},
            "examples_by_dimension": payload.get("examples_by_dimension") or {},
            "stop_when_dimensions_present": payload.get("stop_when_dimensions_present") or [],
            "blocked_if_missing": payload.get("blocked_if_missing") or [],
        }
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, family

    def _apply_blocked_term(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "blocked_terms"
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        terms = after.setdefault("terms", [])
        term = str(payload.get("term") or "").strip()
        if not term:
            raise KnowledgeValidationError("blocked term suggestion requires term")
        normalized = {
            "term": term,
            "reason": str(payload.get("reason") or "").strip(),
            "redirect_prompt": str(payload.get("redirect_prompt") or "").strip(),
            "family_hint": str(payload.get("family_hint") or "").strip() or None,
            "block_if_no_dimensions": payload.get("block_if_no_dimensions") or [],
            "block_if_used_alone": bool(payload.get("block_if_used_alone", False)),
        }
        replaced = False
        for index, existing in enumerate(terms):
            if str(existing.get("term") or "").strip().lower() == term.lower():
                terms[index] = normalized
                replaced = True
                break
        if not replaced:
            terms.append(normalized)
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, term

    def _apply_complementary(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "complementary"
        source = str(payload.get("source") or "").strip()
        if not source:
            raise KnowledgeValidationError("complementary suggestion requires source")
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        rules = after.setdefault("rules", {})
        rules[source] = {
            "targets": payload.get("targets") or [],
            "max_suggestions": int(payload.get("max_suggestions") or len(payload.get("targets") or [])),
            "required_source_status": payload.get("required_source_status") or "resolved",
            "required_dimensions": payload.get("required_dimensions") or [],
            "blocked_when_missing": payload.get("blocked_when_missing") or [],
            "compatible_families": payload.get("compatible_families") or [],
        }
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, source

    def _apply_family_rule(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "families"
        family = str(payload.get("family") or payload.get("family_id") or "").strip()
        if not family:
            raise KnowledgeValidationError("family rule suggestion requires family")
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        rules = after.setdefault("families", {})
        family_payload = deepcopy(payload)
        family_payload.pop("family", None)
        family_payload.pop("family_id", None)
        rules[family] = family_payload
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, family

    def _apply_language_pattern(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "language_patterns"
        section = str(payload.get("section") or "").strip()
        key = str(payload.get("key") or "").strip()
        value = payload.get("value")
        if not section or not key:
            raise KnowledgeValidationError("language pattern suggestion requires section and key")
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        target = after.setdefault(section, {})
        if isinstance(target, dict):
            target[key] = value
        else:
            raise KnowledgeValidationError(f"language pattern section '{section}' is not editable as a mapping")
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, f"{section}:{key}"

    def _apply_substitute_rule(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, str]:
        domain = "substitute_rules"
        group_id = str(payload.get("group_id") or "").strip()
        if not group_id:
            raise KnowledgeValidationError("substitute rule suggestion requires group_id")
        before = self.loader.get_domain(domain)
        after = deepcopy(before)
        rules = after.setdefault("rules", [])
        replaced = False
        for index, existing in enumerate(rules):
            if str(existing.get("group_id") or "").strip() == group_id:
                rules[index] = payload
                replaced = True
                break
        if not replaced:
            rules.append(payload)
        saved = self.loader.save_domain(domain, after)
        return before, saved, domain, group_id

    def _must_get(self, suggestion_id: str) -> Dict[str, Any]:
        suggestion = self.store.get_suggestion(suggestion_id)
        if not suggestion:
            raise KnowledgeValidationError("Suggestion not found")
        return suggestion

    def _assert_transition(self, suggestion: Dict[str, Any], target_status: str) -> None:
        current = str(suggestion.get("status") or "").strip()
        allowed = self._ALLOWED_TRANSITIONS.get(current, set())
        if target_status not in allowed:
            raise KnowledgeValidationError(
                f"Invalid suggestion transition: {current or 'unknown'} -> {target_status}"
            )
