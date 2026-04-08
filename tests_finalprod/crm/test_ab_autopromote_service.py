from __future__ import annotations

from datetime import datetime, timedelta

from app.crm.domain.enums import MessageDirection
from app.crm.models import CRMContact, CRMConversation, CRMMessage, CRMMessageEvent, CRMTenant
from app.crm.services.ab_variant_service import ABVariantService
from tests.crm.utils import seed_tenant_with_user


def _seed_ab_segment(session, *, tenant_id: str, contact_id: str, conversation_id: str) -> None:
    contact = CRMContact(
        id=contact_id,
        tenant_id=tenant_id,
        name="Lead AB",
        phone="+5491111111111",
        email="ab@test.local",
        source_channel="web",
        status="lead",
        score=85,
    )
    conv = CRMConversation(
        id=conversation_id,
        tenant_id=tenant_id,
        contact_id=contact_id,
        channel="web",
        external_id="ab-conv",
        is_open=True,
    )
    session.add(contact)
    session.add(conv)
    session.flush()

    for idx in range(150):
        msg_a = CRMMessage(
            id=f"msg-a-{idx}",
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
            channel="web",
            direction=MessageDirection.OUTBOUND,
            body=f"A-{idx}",
            metadata_json={},
        )
        msg_b = CRMMessage(
            id=f"msg-b-{idx}",
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
            channel="web",
            direction=MessageDirection.OUTBOUND,
            body=f"B-{idx}",
            metadata_json={},
        )
        session.add(msg_a)
        session.add(msg_b)
        session.flush()

        session.add(
            CRMMessageEvent(
                id=f"evt-a-{idx}",
                tenant_id=tenant_id,
                message_id=msg_a.id,
                conversation_id=conversation_id,
                event_type="salesbot_outbound",
                status="sent",
                ab_variant="A",
                variant_key=f"k-a-{idx}",
                objection_type="PRICE_OBJECTION",
                stage_at_send="NEGOTIATING",
                replied_within_24h=False,
                stage_progress_within_7d=False,
                final_outcome="won" if idx < 45 else "lost",
                payload={},
            )
        )
        session.add(
            CRMMessageEvent(
                id=f"evt-b-{idx}",
                tenant_id=tenant_id,
                message_id=msg_b.id,
                conversation_id=conversation_id,
                event_type="salesbot_outbound",
                status="sent",
                ab_variant="B",
                variant_key=f"k-b-{idx}",
                objection_type="PRICE_OBJECTION",
                stage_at_send="NEGOTIATING",
                replied_within_24h=False,
                stage_progress_within_7d=False,
                final_outcome="won" if idx < 36 else "lost",
                payload={},
            )
        )


def test_ab_autopromote_promotes_winner_after_three_stable_days(session_factory):
    Session = session_factory
    with Session() as session:
        tenant, *_ = seed_tenant_with_user(session, tenant_id="tenant-ab-auto", user_id="owner-ab-auto")
        tenant.integration_settings = {"sales_policy": {"ab_autopromote_enabled": True, "ab_min_sample": 150}}
        _seed_ab_segment(session, tenant_id=tenant.id, contact_id="contact-ab", conversation_id="conv-ab")
        session.commit()

    day_1 = datetime(2026, 2, 1, 0, 20, 0)
    day_2 = day_1 + timedelta(days=1)
    day_3 = day_2 + timedelta(days=1)

    with Session() as session:
        service = ABVariantService(session, "tenant-ab-auto")
        result_1 = service.evaluate(apply=True, now=day_1)
        session.commit()
        assert result_1["enabled"] is True
        assert result_1["winners"] == {}

    with Session() as session:
        service = ABVariantService(session, "tenant-ab-auto")
        result_2 = service.evaluate(apply=True, now=day_2)
        session.commit()
        assert result_2["winners"] == {}

    with Session() as session:
        service = ABVariantService(session, "tenant-ab-auto")
        result_3 = service.evaluate(apply=True, now=day_3)
        session.commit()
        segment_key = "web|NEGOTIATING|PRICE_OBJECTION"
        assert result_3["winners"].get(segment_key) == "A"

        tenant = session.query(CRMTenant).filter(CRMTenant.id == "tenant-ab-auto").first()
        policy = (tenant.integration_settings or {}).get("sales_policy", {})
        assert policy.get("ab_winners", {}).get(segment_key) == "A"


def test_ab_autopromote_can_be_disabled(session_factory):
    Session = session_factory
    with Session() as session:
        tenant, *_ = seed_tenant_with_user(session, tenant_id="tenant-ab-disabled", user_id="owner-ab-disabled")
        tenant.integration_settings = {"sales_policy": {"ab_autopromote_enabled": False}}
        session.commit()

    with Session() as session:
        result = ABVariantService(session, "tenant-ab-disabled").evaluate(apply=True, now=datetime(2026, 2, 1, 0, 0, 0))
        assert result["enabled"] is False
