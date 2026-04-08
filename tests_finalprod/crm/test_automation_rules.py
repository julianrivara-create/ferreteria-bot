from app.crm.domain.enums import AutomationTrigger, DealStatus
from app.crm.models import CRMAutomation, CRMContact, CRMDeal, CRMPipelineStage, CRMTask
from app.crm.services.automation_service import AutomationService
from tests.crm.utils import seed_tenant_with_user


def test_automation_engine_evaluates_conditions_and_actions(session_factory):
    session = session_factory()
    try:
        tenant, user, stage, _ = seed_tenant_with_user(
            session, tenant_id="tenant-automation", user_id="admin-auto"
        )

        contact = CRMContact(
            tenant_id=tenant.id,
            name="Lead One",
            phone="+5491199990001",
            email="lead1@example.com",
            source_channel="whatsapp",
            status="lead",
            score=35,
            owner_user_id=user.id,
            metadata_json={},
        )
        session.add(contact)
        session.flush()

        deal = CRMDeal(
            tenant_id=tenant.id,
            contact_id=contact.id,
            stage_id=stage.id,
            owner_user_id=user.id,
            title="Deal One",
            status=DealStatus.OPEN,
            score=40,
            amount_estimated=1500,
            currency="USD",
            source_channel="whatsapp",
            metadata_json={},
        )
        session.add(deal)

        automation = CRMAutomation(
            tenant_id=tenant.id,
            name="Follow quote on high score",
            description="Create task on quote sent when score >= 30",
            trigger_type=AutomationTrigger.QUOTE_SENT,
            enabled=True,
            cooldown_minutes=0,
            conditions_json={"min_score": 30, "channels": ["whatsapp"]},
            actions_json=[
                {
                    "type": "create_task",
                    "title": "Follow quote in 30m",
                    "priority": "high",
                    "due_in_minutes": 30,
                }
            ],
            created_by_user_id=user.id,
        )
        session.add(automation)
        session.commit()

        service = AutomationService(session, tenant.id)
        runs = service.run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "deal_id": deal.id,
                "channel": "whatsapp",
                "score": 45,
                "actor_user_id": user.id,
                "owner_user_id": user.id,
            },
        )
        session.commit()

        assert len(runs) == 1
        assert runs[0].status == "success"

        tasks = session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id, CRMTask.deal_id == deal.id).all()
        assert len(tasks) == 1
        assert tasks[0].title == "Follow quote in 30m"
        assert tasks[0].priority == "high"

        # Condition mismatch: no additional task should be created.
        runs_miss = service.run_trigger(
            AutomationTrigger.QUOTE_SENT,
            {
                "contact_id": contact.id,
                "deal_id": deal.id,
                "channel": "web",
                "score": 10,
                "actor_user_id": user.id,
                "owner_user_id": user.id,
            },
        )
        session.commit()

        assert len(runs_miss) == 0
        tasks_after = session.query(CRMTask).filter(CRMTask.tenant_id == tenant.id, CRMTask.deal_id == deal.id).count()
        assert tasks_after == 1
    finally:
        session.close()
