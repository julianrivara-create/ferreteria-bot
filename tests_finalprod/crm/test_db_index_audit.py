from __future__ import annotations

from sqlalchemy import UniqueConstraint

from app.crm.models import CRMDeal, CRMMessage, CRMTask, CRMWebhookEvent


def _has_index(table, columns: tuple[str, ...]) -> bool:
    for idx in table.indexes:
        idx_columns = tuple(col.name for col in idx.columns)
        if idx_columns == columns:
            return True
    return False


def _has_unique(table, columns: tuple[str, ...]) -> bool:
    for cons in table.constraints:
        if not isinstance(cons, UniqueConstraint):
            continue
        cons_columns = tuple(col.name for col in cons.columns)
        if cons_columns == columns:
            return True
    return False


def test_critical_crm_indexes_and_uniques_are_present():
    assert _has_unique(
        CRMWebhookEvent.__table__,
        ("tenant_id", "source", "event_type", "event_key"),
    ), "Missing unique(tenant_id, source, event_type, event_key) on crm_webhook_events"

    assert _has_index(
        CRMMessage.__table__,
        ("tenant_id", "conversation_id", "created_at"),
    ), "Missing index(tenant_id, conversation_id, created_at) on crm_messages"

    assert _has_index(
        CRMTask.__table__,
        ("tenant_id", "status", "due_at"),
    ), "Missing index(tenant_id, status, due_at) on crm_tasks"

    assert _has_index(
        CRMDeal.__table__,
        ("tenant_id", "stage_id", "last_activity_at"),
    ), "Missing index(tenant_id, stage_id, last_activity_at) on crm_deals"
