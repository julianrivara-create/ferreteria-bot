from __future__ import annotations

import pytest

from app.crm.domain.enums import UserRole
from app.crm.models import CRMPipelineStage
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture
def rbac_context(session_factory, client):
    session = session_factory()
    try:
        tenant_id = "tenant-rbac-hardening"
        role_tokens: dict[str, str] = {}
        users: dict[str, str] = {}

        _, owner_user, stage, owner_token = seed_tenant_with_user(
            session, tenant_id=tenant_id, user_id="owner-rbac-hard", role=UserRole.OWNER
        )
        role_tokens[UserRole.OWNER.value] = owner_token
        users[UserRole.OWNER.value] = owner_user.id

        for role in [UserRole.ADMIN, UserRole.SALES, UserRole.SUPPORT, UserRole.ANALYST, UserRole.READ_ONLY]:
            _, user, _, token = seed_tenant_with_user(
                session,
                tenant_id=tenant_id,
                user_id=f"{role.value.lower()}-rbac-hard",
                role=role,
            )
            role_tokens[role.value] = token
            users[role.value] = user.id

        stage_two = CRMPipelineStage(
            id="tenant-rbac-hardening-stage-2",
            tenant_id=tenant_id,
            name="Qualified",
            position=2,
            color="#2563eb",
            is_won=False,
            is_lost=False,
            sla_hours=24,
        )
        session.add(stage_two)
        session.commit()

        # Seed one contact/deal/task using owner privileges.
        create_contact = client.post(
            "/api/crm/contacts",
            json={
                "name": "RBAC Contact",
                "phone": "+14155554001",
                "email": "rbac-contact@test.dev",
                "owner_user_id": owner_user.id,
                "source_channel": "whatsapp",
            },
            headers=_auth_headers(owner_token),
        )
        assert create_contact.status_code == 201
        contact_id = create_contact.get_json()["id"]

        create_deal = client.post(
            "/api/crm/deals",
            json={
                "contact_id": contact_id,
                "title": "RBAC Deal",
                "stage_id": stage.id,
                "owner_user_id": owner_user.id,
                "currency": "USD",
                "source_channel": "whatsapp",
            },
            headers=_auth_headers(owner_token),
        )
        assert create_deal.status_code == 201
        deal_id = create_deal.get_json()["id"]

        create_task = client.post(
            "/api/crm/tasks",
            json={
                "title": "RBAC Task",
                "contact_id": contact_id,
                "deal_id": deal_id,
                "assigned_to_user_id": owner_user.id,
            },
            headers=_auth_headers(owner_token),
        )
        assert create_task.status_code == 201
        task_id = create_task.get_json()["id"]

        yield {
            "tenant_id": tenant_id,
            "tokens": role_tokens,
            "users": users,
            "contact_id": contact_id,
            "deal_id": deal_id,
            "task_id": task_id,
            "stage_1": stage.id,
            "stage_2": stage_two.id,
        }
    finally:
        session.close()


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 201),
        (UserRole.ADMIN.value, 201),
        (UserRole.SALES.value, 201),
        (UserRole.SUPPORT.value, 201),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_contacts_write(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    owner_id = rbac_context["users"][UserRole.OWNER.value]
    suffix_by_role = {
        UserRole.OWNER.value: "4001",
        UserRole.ADMIN.value: "4002",
        UserRole.SALES.value: "4003",
        UserRole.SUPPORT.value: "4004",
        UserRole.ANALYST.value: "4005",
        UserRole.READ_ONLY.value: "4006",
    }
    res = client.post(
        "/api/crm/contacts",
        json={
            "name": f"Contact-{role}",
            "phone": f"+14155555{suffix_by_role[role]}",
            "email": f"{role.lower()}-contact@rbac.test",
            "owner_user_id": owner_id,
            "source_channel": "web",
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 200),
        (UserRole.ADMIN.value, 200),
        (UserRole.SALES.value, 200),
        (UserRole.SUPPORT.value, 403),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_deal_stage_change(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.patch(
        f"/api/crm/deals/{rbac_context['deal_id']}",
        json={"stage_id": rbac_context["stage_2"]},
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 201),
        (UserRole.ADMIN.value, 201),
        (UserRole.SALES.value, 201),
        (UserRole.SUPPORT.value, 201),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_tasks_create(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    owner_id = rbac_context["users"][UserRole.OWNER.value]
    res = client.post(
        "/api/crm/tasks",
        json={
            "title": f"Task-{role}",
            "contact_id": rbac_context["contact_id"],
            "deal_id": rbac_context["deal_id"],
            "assigned_to_user_id": owner_id,
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 200),
        (UserRole.ADMIN.value, 200),
        (UserRole.SALES.value, 200),
        (UserRole.SUPPORT.value, 200),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_tasks_complete(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.patch(
        f"/api/crm/tasks/{rbac_context['task_id']}",
        json={"status": "done"},
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 201),
        (UserRole.ADMIN.value, 201),
        (UserRole.SALES.value, 403),
        (UserRole.SUPPORT.value, 403),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_automations_edit(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.post(
        "/api/crm/automations",
        json={
            "name": f"A-{role}",
            "trigger_type": "quote_sent",
            "conditions_json": {},
            "actions_json": [{"type": "create_task", "title": "Follow up"}],
            "enabled": True,
            "cooldown_minutes": 0,
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 200),
        (UserRole.ADMIN.value, 200),
        (UserRole.SALES.value, 403),
        (UserRole.SUPPORT.value, 403),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_automations_run_dry(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.post(
        "/api/crm/automations/evaluate",
        json={
            "trigger_type": "quote_sent",
            "event": {
                "contact_id": rbac_context["contact_id"],
                "deal_id": rbac_context["deal_id"],
                "channel": "whatsapp",
                "score": 50,
            },
            "trigger_event_key": f"dry-{role}",
        },
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 200),
        (UserRole.ADMIN.value, 200),
        (UserRole.SALES.value, 403),
        (UserRole.SUPPORT.value, 403),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_exports_restricted(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.get("/api/crm/reports/export.csv", headers=_auth_headers(token))
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 200),
        (UserRole.ADMIN.value, 200),
        (UserRole.SALES.value, 403),
        (UserRole.SUPPORT.value, 403),
        (UserRole.ANALYST.value, 403),
        (UserRole.READ_ONLY.value, 403),
    ],
)
def test_rbac_settings_changes(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.patch(
        "/api/crm/settings",
        json={"currency": "USD"},
        headers=_auth_headers(token),
    )
    assert res.status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER.value, 200),
        (UserRole.ADMIN.value, 200),
        (UserRole.SALES.value, 200),
        (UserRole.SUPPORT.value, 403),
        (UserRole.ANALYST.value, 200),
        (UserRole.READ_ONLY.value, 200),
    ],
)
def test_rbac_reports_read(role, expected, rbac_context, client):
    token = rbac_context["tokens"][role]
    res = client.get("/api/crm/reports/dashboard", headers=_auth_headers(token))
    assert res.status_code == expected


def test_readonly_cannot_create_notes(rbac_context, client):
    token = rbac_context["tokens"][UserRole.READ_ONLY.value]
    res = client.post(
        "/api/crm/notes",
        json={"contact_id": rbac_context["contact_id"], "body": "internal note"},
        headers=_auth_headers(token),
    )
    assert res.status_code == 403
