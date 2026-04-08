from __future__ import annotations

from typing import Any, Dict, Optional

from .store import TrainingStore


class TrainingReviewService:
    def __init__(self, store: TrainingStore):
        self.store = store

    def save_review(
        self,
        *,
        session_id: str,
        bot_message_id: str,
        review_label: str,
        failure_tag: Optional[str] = None,
        failure_detail_tag: Optional[str] = None,
        expected_behavior_tag: Optional[str] = None,
        clarification_dimension: Optional[str] = None,
        expected_answer: Optional[str] = None,
        what_was_wrong: Optional[str] = None,
        missing_clarification: Optional[str] = None,
        suggested_family: Optional[str] = None,
        suggested_canonical_product: Optional[str] = None,
        operator_notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.store.upsert_review(
            session_id,
            bot_message_id,
            review_label=review_label,
            failure_tag=failure_tag,
            failure_detail_tag=failure_detail_tag,
            expected_behavior_tag=expected_behavior_tag,
            clarification_dimension=clarification_dimension,
            expected_answer=expected_answer,
            what_was_wrong=what_was_wrong,
            missing_clarification=missing_clarification,
            suggested_family=suggested_family,
            suggested_canonical_product=suggested_canonical_product,
            operator_notes=operator_notes,
            created_by=created_by,
            status="submitted",
        )

    def get_case_detail(self, review_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_case_detail(review_id)

    def list_cases(self, **filters: Any) -> list[Dict[str, Any]]:
        return self.store.list_cases(**filters)

    def list_reviews(self, **filters: Any) -> list[Dict[str, Any]]:
        return self.store.list_reviews(**filters)
