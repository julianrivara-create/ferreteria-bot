from app.crm.domain.enums import UserRole
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_tenant_isolation_filters_data(client, session_factory):
    session = session_factory()
    try:
        _, user_a, _, token_a = seed_tenant_with_user(
            session, tenant_id="tenant-a", user_id="admin-a", role=UserRole.ADMIN
        )
        _, user_b, _, token_b = seed_tenant_with_user(
            session, tenant_id="tenant-b", user_id="admin-b", role=UserRole.ADMIN
        )
        session.commit()

        res_a_create = client.post(
            "/api/crm/contacts",
            json={
                "name": "Contact A",
                "phone": "+5491111000001",
                "email": "a@contacts.test",
                "source_channel": "whatsapp",
                "owner_user_id": user_a.id,
            },
            headers=_auth_headers(token_a),
        )
        assert res_a_create.status_code == 201
        contact_a_id = res_a_create.get_json()["id"]

        res_b_create = client.post(
            "/api/crm/contacts",
            json={
                "name": "Contact B",
                "phone": "+5491111000002",
                "email": "b@contacts.test",
                "source_channel": "web",
                "owner_user_id": user_b.id,
            },
            headers=_auth_headers(token_b),
        )
        assert res_b_create.status_code == 201
        contact_b_id = res_b_create.get_json()["id"]

        list_a = client.get("/api/crm/contacts", headers=_auth_headers(token_a))
        assert list_a.status_code == 200
        data_a = list_a.get_json()
        ids_a = {row["id"] for row in data_a["items"]}
        assert contact_a_id in ids_a
        assert contact_b_id not in ids_a

        cross_get = client.get(f"/api/crm/contacts/{contact_b_id}", headers=_auth_headers(token_a))
        assert cross_get.status_code == 404

        cross_patch = client.patch(
            f"/api/crm/contacts/{contact_b_id}",
            json={"name": "Not allowed"},
            headers=_auth_headers(token_a),
        )
        assert cross_patch.status_code == 404
    finally:
        session.close()
