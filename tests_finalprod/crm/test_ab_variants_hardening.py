from __future__ import annotations

from datetime import datetime

import app.crm.api.routes as crm_routes_module
from app.crm.domain.enums import MessageDirection, UserRole
from app.crm.models import CRMContact, CRMConversation, CRMMessage, CRMMessageEvent
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _seed_salesbot_outbound_event(
    session,
    *,
    tenant_id: str,
    contact_id: str,
    channel: str,
    stage: str,
    objection_type: str,
    variant: str,
    replied: bool,
    progressed: bool,
    outcome: str | None,
) -> None:
    conversation = CRMConversation(
        tenant_id=tenant_id,
        contact_id=contact_id,
        channel=channel,
        external_id=f"conv-{tenant_id}-{channel}-{variant}-{stage}",
        started_at=datetime(2026, 2, 17, 12, 0, 0),
        last_message_at=datetime(2026, 2, 17, 12, 0, 0),
        metadata_json={},
    )
    session.add(conversation)
    session.flush()

    message = CRMMessage(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        contact_id=contact_id,
        channel=channel,
        direction=MessageDirection.OUTBOUND,
        body="outbound",
        created_at=datetime(2026, 2, 17, 12, 0, 0),
        sent_at=datetime(2026, 2, 17, 12, 0, 0),
        metadata_json={},
    )
    session.add(message)
    session.flush()

    event_variant, variant_key = crm_routes_module._deterministic_ab_variant(
        tenant_id=tenant_id,
        contact_id=contact_id,
        stage=stage,
        objection_type=objection_type,
    )
    if event_variant != variant:
        # Keep the deterministic key pattern while forcing test coverage for both variants.
        variant_key = f"{variant_key}:forced:{variant}"

    session.add(
        CRMMessageEvent(
            tenant_id=tenant_id,
            message_id=message.id,
            conversation_id=conversation.id,
            event_type="salesbot_outbound",
            status="sent",
            ab_variant=variant,
            variant_key=variant_key,
            stage_at_send=stage,
            objection_type=objection_type,
            replied_within_24h=replied,
            stage_progress_within_7d=progressed,
            final_outcome=outcome,
            payload={"source": "test"},
            created_at=datetime(2026, 2, 17, 12, 0, 0),
        )
    )


def test_deterministic_variant_assignment_is_stable_for_same_tuple():
    variant_a, key_a = crm_routes_module._deterministic_ab_variant(
        tenant_id="tenant-ab",
        contact_id="contact-1",
        stage="QUOTED",
        objection_type="OBJECTION_PRICE",
    )
    variant_b, key_b = crm_routes_module._deterministic_ab_variant(
        tenant_id="tenant-ab",
        contact_id="contact-1",
        stage="QUOTED",
        objection_type="OBJECTION_PRICE",
    )
    assert variant_a == variant_b
    assert key_a == key_b
    assert variant_a in {"A", "B"}


def test_ab_variants_report_filtering_and_tenant_isolation(client, session_factory):
    session = session_factory()
    try:
        tenant_a, user_a, _, token_a = seed_tenant_with_user(
            session,
            tenant_id="tenant-ab-report-a",
            user_id="owner-ab-report-a",
            role=UserRole.OWNER,
        )
        tenant_b, user_b, _, token_b = seed_tenant_with_user(
            session,
            tenant_id="tenant-ab-report-b",
            user_id="owner-ab-report-b",
            role=UserRole.OWNER,
        )

        contact_a = CRMContact(
            tenant_id=tenant_a.id,
            name="Lead A",
            phone="+14155558010",
            email="lead-a@ab.test",
            source_channel="web",
            owner_user_id=user_a.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        contact_b = CRMContact(
            tenant_id=tenant_b.id,
            name="Lead B",
            phone="+14155558011",
            email="lead-b@ab.test",
            source_channel="web",
            owner_user_id=user_b.id,
            status="lead",
            score=0,
            metadata_json={},
        )
        session.add_all([contact_a, contact_b])
        session.flush()

        # Tenant A segment we will filter on: web + QUOTED + OBJECTION_PRICE.
        _seed_salesbot_outbound_event(
            session,
            tenant_id=tenant_a.id,
            contact_id=contact_a.id,
            channel="web",
            stage="QUOTED",
            objection_type="OBJECTION_PRICE",
            variant="A",
            replied=True,
            progressed=True,
            outcome="won",
        )
        _seed_salesbot_outbound_event(
            session,
            tenant_id=tenant_a.id,
            contact_id=contact_a.id,
            channel="web",
            stage="QUOTED",
            objection_type="OBJECTION_PRICE",
            variant="B",
            replied=False,
            progressed=False,
            outcome="lost",
        )
        # Tenant A different segment, should be excluded by filter.
        _seed_salesbot_outbound_event(
            session,
            tenant_id=tenant_a.id,
            contact_id=contact_a.id,
            channel="instagram",
            stage="NEGOTIATING",
            objection_type="OBJECTION_TRUST",
            variant="A",
            replied=False,
            progressed=False,
            outcome=None,
        )
        # Tenant B same filter values, must be isolated away from tenant A response.
        _seed_salesbot_outbound_event(
            session,
            tenant_id=tenant_b.id,
            contact_id=contact_b.id,
            channel="web",
            stage="QUOTED",
            objection_type="OBJECTION_PRICE",
            variant="A",
            replied=True,
            progressed=False,
            outcome="won",
        )
        session.commit()

        response_a = client.get(
            "/api/crm/reports/ab-variants?channel=web&stage=QUOTED&objection_type=OBJECTION_PRICE",
            headers=_auth_headers(token_a),
        )
        assert response_a.status_code == 200
        payload_a = response_a.get_json()
        assert len(payload_a["items"]) == 1
        segment_a = payload_a["items"][0]
        assert segment_a["channel"] == "web"
        assert segment_a["stage"] == "QUOTED"
        assert segment_a["objection_type"] == "OBJECTION_PRICE"
        assert segment_a["totals"]["sent"] == 2
        assert segment_a["totals"]["reply_24h"] == 1
        assert segment_a["totals"]["stage_progress_7d"] == 1
        assert segment_a["totals"]["won"] == 1
        assert segment_a["totals"]["lost"] == 1
        assert {row["variant"] for row in segment_a["variants"]} == {"A", "B"}

        response_b = client.get(
            "/api/crm/reports/ab-variants?channel=web&stage=QUOTED&objection_type=OBJECTION_PRICE",
            headers=_auth_headers(token_b),
        )
        assert response_b.status_code == 200
        payload_b = response_b.get_json()
        assert len(payload_b["items"]) == 1
        segment_b = payload_b["items"][0]
        assert segment_b["totals"]["sent"] == 1
        assert segment_b["totals"]["won"] == 1
        assert segment_b["totals"]["lost"] == 0
    finally:
        session.close()
