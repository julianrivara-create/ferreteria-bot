from datetime import datetime, timedelta

from app.crm.domain.enums import DealStatus, MessageDirection, TaskStatus, UserRole
from app.crm.models import (
    CRMContact,
    CRMConversation,
    CRMDeal,
    CRMMessage,
    CRMPipelineStage,
    CRMTask,
)
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_console_home_and_search_are_tenant_scoped(client, session_factory):
    session = session_factory()
    try:
        _, owner, stage, owner_token = seed_tenant_with_user(
            session, tenant_id="tenant-console", user_id="owner-console", role=UserRole.OWNER
        )
        _, _, other_stage, _ = seed_tenant_with_user(
            session, tenant_id="tenant-other", user_id="owner-other", role=UserRole.OWNER
        )

        contact = CRMContact(
            tenant_id="tenant-console",
            name="Alice Console",
            email="alice-console@example.com",
            phone="+5491111111111",
            source_channel="web",
            owner_user_id=owner.id,
            score=75,
        )
        session.add(contact)
        session.flush()

        deal = CRMDeal(
            tenant_id="tenant-console",
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Console Deal",
            status=DealStatus.OPEN,
            score=80,
            source_channel="web",
            last_activity_at=datetime.utcnow(),
            last_stage_changed_at=datetime.utcnow(),
        )
        session.add(deal)
        session.flush()

        session.add(
            CRMTask(
                tenant_id="tenant-console",
                contact_id=contact.id,
                deal_id=deal.id,
                assigned_to_user_id=owner.id,
                created_by_user_id=owner.id,
                title="Follow up now",
                status=TaskStatus.TODO,
                priority="high",
                due_at=datetime.utcnow() - timedelta(hours=1),
                metadata_json={"kind": "followup"},
            )
        )

        conversation = CRMConversation(
            tenant_id="tenant-console",
            contact_id=contact.id,
            channel="web",
            external_id="web-1",
            is_open=True,
            last_message_at=datetime.utcnow(),
            metadata_json={"unread": True},
        )
        session.add(conversation)
        session.flush()

        session.add(
            CRMMessage(
                tenant_id="tenant-console",
                conversation_id=conversation.id,
                contact_id=contact.id,
                channel="web",
                direction=MessageDirection.INBOUND,
                body="Necesito precio",
                metadata_json={"intent": "price_request", "high_intent": True},
                created_at=datetime.utcnow(),
            )
        )

        other_contact = CRMContact(
            tenant_id="tenant-other",
            name="Alice Other",
            email="alice-other@example.com",
            phone="+5491222222222",
            source_channel="instagram",
            score=10,
        )
        session.add(other_contact)
        session.flush()

        session.add(
            CRMDeal(
                tenant_id="tenant-other",
                contact_id=other_contact.id,
                stage_id=other_stage.id,
                title="Other deal",
                status=DealStatus.OPEN,
                score=20,
            )
        )

        session.commit()

        home_res = client.get("/api/console/home", headers=_auth_headers(owner_token))
        assert home_res.status_code == 200
        home_payload = home_res.get_json()
        assert "sales_today" in home_payload
        assert "action_required" in home_payload
        assert "bot_health" in home_payload
        assert "watchdog" in home_payload

        search_res = client.get("/api/console/search?q=alice", headers=_auth_headers(owner_token))
        assert search_res.status_code == 200
        groups = {group["type"]: group["items"] for group in search_res.get_json()["groups"]}

        contact_items = groups.get("Contact", [])
        assert any(item["label"] == "Alice Console" for item in contact_items)
        assert not any(item["label"] == "Alice Other" for item in contact_items)
    finally:
        session.close()


def test_console_stage_change_rbac(client, session_factory):
    session = session_factory()
    try:
        _, owner, stage, owner_token = seed_tenant_with_user(
            session, tenant_id="tenant-stage", user_id="owner-stage", role=UserRole.OWNER
        )
        _, _, _, readonly_token = seed_tenant_with_user(
            session, tenant_id="tenant-stage", user_id="readonly-stage", role=UserRole.READ_ONLY
        )

        stage_two = CRMPipelineStage(
            id="tenant-stage-qual",
            tenant_id="tenant-stage",
            name="QUALIFIED",
            position=2,
            color="#2563eb",
            is_won=False,
            is_lost=False,
        )
        session.add(stage_two)

        contact = CRMContact(
            tenant_id="tenant-stage",
            name="Stage Contact",
            email="stage-contact@example.com",
            phone="+5491333333333",
            owner_user_id=owner.id,
            score=50,
        )
        session.add(contact)
        session.flush()

        deal = CRMDeal(
            tenant_id="tenant-stage",
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=owner.id,
            title="Stage Move",
            status=DealStatus.OPEN,
            score=60,
        )
        session.add(deal)
        session.commit()

        denied = client.post(
            f"/api/console/deals/{deal.id}/stage",
            json={"stage_id": stage_two.id, "stage_reason": "test"},
            headers=_auth_headers(readonly_token),
        )
        assert denied.status_code == 403

        allowed = client.post(
            f"/api/console/deals/{deal.id}/stage",
            json={"stage_id": stage_two.id, "stage_reason": "test"},
            headers=_auth_headers(owner_token),
        )
        assert allowed.status_code == 200
        assert allowed.get_json()["stage_id"] == stage_two.id
    finally:
        session.close()


def test_watchdog_quick_action_is_owner_admin_only(client, session_factory):
    session = session_factory()
    try:
        seed_tenant_with_user(session, tenant_id="tenant-watchdog", user_id="owner-watchdog", role=UserRole.OWNER)
        _, _, _, sales_token = seed_tenant_with_user(
            session, tenant_id="tenant-watchdog", user_id="sales-watchdog", role=UserRole.SALES
        )
        _, _, _, owner_token = seed_tenant_with_user(
            session, tenant_id="tenant-watchdog", user_id="owner-watchdog-2", role=UserRole.OWNER
        )
        session.commit()

        denied = client.post(
            "/api/console/watchdog/actions/rerun-job",
            json={"job_name": "sla_check"},
            headers=_auth_headers(sales_token),
        )
        assert denied.status_code == 403

        allowed = client.post(
            "/api/console/watchdog/actions/rerun-job",
            json={"job_name": "sla_check"},
            headers=_auth_headers(owner_token),
        )
        assert allowed.status_code == 200
        body = allowed.get_json()
        assert body["ok"] is True
        assert body["action"] == "rerun-job"
    finally:
        session.close()
