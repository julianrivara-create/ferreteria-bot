from app.crm.domain.enums import UserRole
from app.crm.models import CRMUser
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_rbac_enforces_permissions(client, session_factory):
    session = session_factory()
    try:
        _, _, stage, admin_token = seed_tenant_with_user(
            session, tenant_id="tenant-rbac", user_id="admin-user", role=UserRole.ADMIN
        )
        _, sales_user, _, sales_token = seed_tenant_with_user(
            session, tenant_id="tenant-rbac", user_id="sales-user", role=UserRole.SALES
        )
        _, _, _, readonly_token = seed_tenant_with_user(
            session, tenant_id="tenant-rbac", user_id="readonly-user", role=UserRole.READ_ONLY
        )
        session.commit()

        create_contact_payload = {
            "name": "Juan Perez",
            "phone": "+5491111111111",
            "email": "juan@example.com",
            "source_channel": "whatsapp",
            "owner_user_id": sales_user.id,
        }

        sales_res = client.post(
            "/api/crm/contacts",
            json=create_contact_payload,
            headers=_auth_headers(sales_token),
        )
        assert sales_res.status_code == 201

        ro_res = client.post(
            "/api/crm/contacts",
            json={
                "name": "No Perm",
                "phone": "+5491122222222",
                "email": "noperm@example.com",
                "source_channel": "whatsapp",
            },
            headers=_auth_headers(readonly_token),
        )
        assert ro_res.status_code == 403

        sales_user_create = client.post(
            "/api/crm/users",
            json={
                "full_name": "Another User",
                "email": "another@example.com",
                "phone": "+5491133333333",
                "role": "Sales",
                "password": "secret1234",
            },
            headers=_auth_headers(sales_token),
        )
        assert sales_user_create.status_code == 403

        admin_user_create = client.post(
            "/api/crm/users",
            json={
                "full_name": "Created By Admin",
                "email": "created@example.com",
                "phone": "+5491144444444",
                "role": "Support",
                "password": "secret1234",
            },
            headers=_auth_headers(admin_token),
        )
        assert admin_user_create.status_code == 201

        created_email = admin_user_create.get_json()["email"]
        assert created_email == "created@example.com"

        created_count = (
            session.query(CRMUser)
            .filter(CRMUser.tenant_id == "tenant-rbac", CRMUser.email == "created@example.com")
            .count()
        )
        assert created_count == 1
    finally:
        session.close()
