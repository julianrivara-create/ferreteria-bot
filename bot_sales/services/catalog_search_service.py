"""
CatalogSearchService — deterministic catalog search pipeline.
AI extracts intent/entities (TurnInterpreter). This service does the actual search.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Scoring constants (same as ferreteria_quote.py for consistency)
_SCORE_STOP_WORDS = frozenset({
    "de", "para", "con", "una", "un", "el", "la", "los", "las",
    "por", "del", "al", "en", "y", "e", "o", "u", "a",
    "interior", "exterior", "blanco", "negro", "rojo", "azul",
    "grande", "chico", "mediano", "nuevo", "extra",
})

_MIN_SCORE = 0.0
_SINGLE_RESULT_THRESHOLD = 7.0
_OPTIONS_THRESHOLD = 2.0


@dataclass
class ProductNeed:
    search_mode: str = "exact"
    family_hint: Optional[str] = None
    use_case: Optional[str] = None
    material: Optional[str] = None
    dimensions: Dict[str, Any] = field(default_factory=dict)
    presentation: Optional[str] = None
    brand: Optional[str] = None
    qty: Optional[int] = None
    budget: Optional[float] = None
    raw_terms: List[str] = field(default_factory=list)

    @classmethod
    def from_turn_interpretation(cls, interp: Any) -> "ProductNeed":
        """Build ProductNeed from a TurnInterpretation instance."""
        e = interp.entities
        return cls(
            search_mode=interp.search_mode or "exact",
            use_case=e.use_case,
            material=e.material,
            dimensions=e.dimensions or {},
            brand=e.brand,
            qty=e.qty,
            budget=e.budget,
            raw_terms=e.product_terms or [],
        )


@dataclass
class CatalogSearchResult:
    status: str  # resolved | options | clarify | no_match
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    applied_filters: Dict[str, Any] = field(default_factory=dict)
    missing_critical_fields: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    top_candidate: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "candidates": self.candidates,
            "applied_filters": self.applied_filters,
            "missing_critical_fields": self.missing_critical_fields,
            "reason_codes": self.reason_codes,
            "top_candidate": self.top_candidate,
        }


class CatalogSearchService:
    """
    Clean, deterministic product search. Separates AI entity extraction from actual DB search.
    """

    MAX_CANDIDATES = 5

    def __init__(self, db):
        self.db = db

    def search(self, need: ProductNeed) -> CatalogSearchResult:
        """Route to the right search strategy based on search_mode."""
        try:
            if need.search_mode == "by_use":
                return self._search_by_use(need)
            elif need.search_mode == "browse":
                return self._search_browse(need)
            else:
                return self._search_exact(need)
        except Exception as exc:
            logger.error("CatalogSearchService.search failed: %s", exc)
            return CatalogSearchResult(status="no_match", reason_codes=["search_error"])

    def _build_query(self, need: ProductNeed) -> str:
        """Build a search query string from the ProductNeed."""
        parts = list(need.raw_terms)
        if need.use_case:
            parts.append(need.use_case)
        if need.material:
            parts.append(need.material)
        if need.brand:
            parts.append(need.brand)
        for v in need.dimensions.values():
            if v:
                parts.append(str(v))
        return " ".join(parts).strip()

    def _search_exact(self, need: ProductNeed) -> CatalogSearchResult:
        """Term-based search using existing DB methods."""
        query = self._build_query(need)
        if not query:
            return CatalogSearchResult(status="no_match", reason_codes=["empty_query"])

        # DB uses `model` as the first positional arg for keyword search
        try:
            if hasattr(self.db, "find_matches_hybrid"):
                raw = self.db.find_matches_hybrid(model=query)
            else:
                raw = self.db.find_matches(model=query)
        except Exception as exc:
            logger.warning("DB search failed: %s", exc)
            return CatalogSearchResult(status="no_match", reason_codes=["db_error"])

        candidates = self._score_and_filter(raw, need)
        candidates = self._apply_post_filters(candidates, need)
        return self._build_result(candidates, need)

    def _search_by_use(self, need: ProductNeed) -> CatalogSearchResult:
        """Broader search when user described a use case instead of a product name."""
        parts = []
        if need.use_case:
            parts.append(need.use_case)
        if need.material:
            parts.append(need.material)
        if not parts:
            # Fall back to exact if no use case info
            return self._search_exact(need)

        query = " ".join(parts)
        try:
            if hasattr(self.db, "find_matches_hybrid"):
                raw = self.db.find_matches_hybrid(model=query)
            else:
                raw = self.db.find_matches(model=query)
        except Exception as exc:
            logger.warning("DB search by_use failed: %s", exc)
            return CatalogSearchResult(status="no_match", reason_codes=["db_error"])

        candidates = self._apply_post_filters(raw[:20], need)
        return self._build_result(candidates, need, applied_mode="by_use")

    def _search_browse(self, need: ProductNeed) -> CatalogSearchResult:
        """List top products in a category/family."""
        family = need.family_hint or (need.raw_terms[0] if need.raw_terms else None)
        if not family:
            return CatalogSearchResult(status="no_match", reason_codes=["no_browse_target"])

        try:
            if hasattr(self.db, "list_by_category"):
                raw = self.db.list_by_category(family)
            else:
                raw = self.db.find_matches(model=family)
        except Exception as exc:
            logger.warning("DB browse failed: %s", exc)
            return CatalogSearchResult(status="no_match", reason_codes=["db_error"])

        candidates = raw[:self.MAX_CANDIDATES]
        if not candidates:
            return CatalogSearchResult(status="no_match", reason_codes=["no_results"])
        return CatalogSearchResult(
            status="options",
            candidates=candidates,
            top_candidate=candidates[0] if candidates else None,
            applied_filters={"browse_family": family},
        )

    def _score_and_filter(self, products: list, need: ProductNeed) -> list:
        """Score products and remove those below minimum threshold."""
        query_words = self._significant_words(self._build_query(need))
        if not query_words:
            return products[:self.MAX_CANDIDATES]

        scored = []
        for p in products:
            score = self._score_product(p, query_words, need)
            if score >= _MIN_SCORE:
                scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:self.MAX_CANDIDATES]]

    def _score_product(self, product: dict, query_words: set, need: ProductNeed) -> float:
        """Score a single product against the query."""
        score = 0.0
        model_words = self._significant_words(
            str(product.get("model", "") or "") + " " + str(product.get("category", "") or "")
        )
        if not model_words:
            return 0.0

        overlap = query_words & model_words
        overlap_ratio = len(overlap) / len(query_words) if query_words else 0

        if overlap_ratio >= 0.5:
            score += 5.0
        elif overlap and overlap_ratio > 0:
            score += 3.0
        else:
            score -= 3.0

        # Budget filter
        if need.budget:
            price = float(product.get("price_ars") or product.get("price") or 0)
            if price > need.budget:
                score -= 4.0

        # Brand match
        if need.brand:
            product_brand = str(product.get("brand") or "").lower()
            if need.brand.lower() in product_brand:
                score += 2.0

        return score

    def _apply_post_filters(self, candidates: list, need: ProductNeed) -> list:
        """Apply stock, brand, and budget filters. H7: always exclude out-of-stock items."""
        in_stock = [p for p in candidates if int(p.get("stock_qty") or 0) > 0]
        # If no items have stock info (legacy catalog without stock_qty), fall through
        filtered = in_stock if in_stock else candidates

        result = []
        for p in filtered:
            if need.budget:
                price = float(p.get("price_ars") or p.get("price") or 0)
                if price > need.budget * 1.1:  # 10% tolerance
                    continue
            if need.brand:
                product_brand = str(p.get("brand") or "").lower()
                if need.brand.lower() not in product_brand:
                    continue
            result.append(p)
        return result if result else filtered  # never return empty if we had matches

    def _build_result(
        self, candidates: list, need: ProductNeed, applied_mode: str = "exact"
    ) -> CatalogSearchResult:
        """Determine status and build the final result."""
        applied_filters = {"mode": applied_mode}
        if need.brand:
            applied_filters["brand"] = need.brand
        if need.budget:
            applied_filters["budget"] = need.budget

        if not candidates:
            return CatalogSearchResult(
                status="no_match",
                reason_codes=["no_results"],
                applied_filters=applied_filters,
            )

        # Determine what critical fields are missing for single-item resolution
        missing = []
        if len(candidates) > 1 and need.search_mode == "exact":
            # Check if dimensions that separate results are unspecified
            if not need.dimensions and not need.brand:
                missing.append("especificacion")

        status = self._determine_status(candidates, missing)
        return CatalogSearchResult(
            status=status,
            candidates=candidates,
            top_candidate=candidates[0] if candidates else None,
            applied_filters=applied_filters,
            missing_critical_fields=missing,
        )

    def _determine_status(self, candidates: list, missing_fields: list) -> str:
        if not candidates:
            return "no_match"
        if missing_fields and len(candidates) > 1:
            return "clarify"
        if len(candidates) == 1:
            return "resolved"
        return "options"

    def _significant_words(self, text: str) -> set:
        """Extract meaningful words from text, excluding stop words."""
        words = str(text).lower().split()
        return {w for w in words if w not in _SCORE_STOP_WORDS and len(w) > 2}
