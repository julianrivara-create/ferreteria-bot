from __future__ import annotations

from app.crm.domain.enums import DealStatus, UserRole
from app.crm.models import CRMAuditLog, CRMContact, CRMDeal, CRMScoringRule
from app.crm.services.scoring_service import ScoringService
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _seed_deal(session, tenant_id: str, user_id: str, stage_id: str) -> tuple[CRMContact, CRMDeal]:
    contact = CRMContact(
        tenant_id=tenant_id,
        name="Score Lead",
        phone="+14155559001",
        email="score-lead@test.dev",
        source_channel="whatsapp",
        owner_user_id=user_id,
        status="lead",
        score=0,
        metadata_json={},
    )
    session.add(contact)
    session.flush()

    deal = CRMDeal(
        tenant_id=tenant_id,
        contact_id=contact.id,
        stage_id=stage_id,
        owner_user_id=user_id,
        title="Score Deal",
        status=DealStatus.OPEN,
        score=0,
        amount_estimated=800,
        currency="USD",
        source_channel="whatsapp",
        metadata_json={},
    )
    session.add(deal)
    session.flush()
    return contact, deal


def test_scoring_rules_increment_and_decrement(session_factory):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-score-rules",
            user_id="owner-score-rules",
        )
        _, deal = _seed_deal(session, tenant.id, user.id, stage.id)

        session.add(
            CRMScoringRule(
                tenant_id=tenant.id,
                name="Inbound +10",
                signal_key="inbound_message",
                points=10,
                enabled=True,
                conditions_json={},
            )
        )
        session.add(
            CRMScoringRule(
                tenant_id=tenant.id,
                name="No reply -5",
                signal_key="no_reply",
                points=-5,
                enabled=True,
                conditions_json={},
            )
        )
        session.commit()

        service = ScoringService(session, tenant.id)
        score_after_inbound = service.apply_signal(deal.id, "inbound_message", {"channel": "whatsapp", "score": 1})
        score_after_no_reply = service.apply_signal(deal.id, "no_reply", {"channel": "whatsapp", "score": 1})
        session.commit()

        assert score_after_inbound == 10
        assert score_after_no_reply == 5
    finally:
        session.close()


def test_score_explain_endpoint_returns_signal_history(client, session_factory):
    session = session_factory()
    try:
        tenant, user, stage, token = seed_tenant_with_user(
            session,
            tenant_id="tenant-score-explain",
            user_id="owner-score-explain",
            role=UserRole.ADMIN,
        )
        _, deal = _seed_deal(session, tenant.id, user.id, stage.id)

        session.add(
            CRMScoringRule(
                tenant_id=tenant.id,
                name="Quote +12",
                signal_key="quote_sent",
                points=12,
                enabled=True,
                conditions_json={},
            )
        )
        session.commit()

        ScoringService(session, tenant.id).apply_signal(deal.id, "quote_sent", {"channel": "whatsapp", "score": 5})
        session.commit()

        res = client.get(f"/api/crm/deals/{deal.id}/score-explain", headers=_auth_headers(token))
        assert res.status_code == 200
        body = res.get_json()
        assert body["score"] == 12
        assert len(body["events"]) == 1
        assert body["events"][0]["signal_key"] == "quote_sent"
    finally:
        session.close()


def test_segment_export_writes_audit_log(client, session_factory):
    session = session_factory()
    try:
        tenant, user, _, token = seed_tenant_with_user(
            session,
            tenant_id="tenant-segment-audit",
            user_id="owner-segment-audit",
            role=UserRole.ADMIN,
        )
        session.add(
            CRMContact(
                tenant_id=tenant.id,
                name="Segment Lead",
                phone="+14155559002",
                email="segment-lead@test.dev",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=25,
                metadata_json={},
            )
        )
        session.commit()

        segment_create = client.post(
            "/api/crm/segments",
            json={"name": "hot-leads", "filters": {"min_score": 20}},
            headers=_auth_headers(token),
        )
        assert segment_create.status_code == 201
        segment_id = segment_create.get_json()["id"]

        export_res = client.get(f"/api/crm/segments/{segment_id}/export.csv", headers=_auth_headers(token))
        assert export_res.status_code == 200
        assert "Segment Lead" in export_res.data.decode()

        audit_count = (
            session.query(CRMAuditLog)
            .filter(
                CRMAuditLog.tenant_id == tenant.id,
                CRMAuditLog.entity_type == "segment",
                CRMAuditLog.entity_id == segment_id,
                CRMAuditLog.action == "export",
            )
            .count()
        )
        assert audit_count == 1
    finally:
        session.close()
