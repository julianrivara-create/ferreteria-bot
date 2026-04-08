import json
from datetime import datetime, timedelta

from sqlalchemy import text

from app.crm.domain.enums import UserRole
from tests.crm.utils import seed_tenant_with_user


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_maintenance_tables(session) -> None:
    session.execute(
        text(
            """
            CREATE TABLE maintenance_runs (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                process_name TEXT NOT NULL,
                service_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                started_at DATETIME NOT NULL,
                finished_at DATETIME NOT NULL,
                consecutive_fail_count INTEGER,
                first_seen_at DATETIME,
                last_seen_at DATETIME,
                schema_version TEXT,
                code_version TEXT,
                summary_json TEXT
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE maintenance_state (
                tenant_id TEXT NOT NULL,
                process_name TEXT NOT NULL,
                service_id TEXT NOT NULL,
                previous_fingerprint TEXT,
                previous_outcome TEXT,
                consecutive_fail_count INTEGER,
                first_seen_at DATETIME,
                last_seen_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    session.commit()


def test_watchdog_health_prefers_maintenance_runs_with_staged_thresholds(client, session_factory):
    session = session_factory()
    try:
        tenant, _, _, token = seed_tenant_with_user(
            session, tenant_id="tenant-maint-v2-health", user_id="owner-maint-v2-health", role=UserRole.OWNER
        )
        _create_maintenance_tables(session)

        now = datetime.utcnow()
        session.execute(
            text(
                """
                INSERT INTO maintenance_runs (
                    id, tenant_id, process_name, service_id, outcome, started_at, finished_at,
                    consecutive_fail_count, first_seen_at, last_seen_at, schema_version, code_version, summary_json
                ) VALUES (
                    :id, :tenant_id, :process_name, :service_id, :outcome, :started_at, :finished_at,
                    :consecutive_fail_count, :first_seen_at, :last_seen_at, :schema_version, :code_version, :summary_json
                )
                """
            ),
            {
                "id": "run-runner-ok",
                "tenant_id": tenant.id,
                "process_name": "runner",
                "service_id": "svc-runner",
                "outcome": "OK",
                "started_at": now - timedelta(minutes=72),
                "finished_at": now - timedelta(minutes=70),
                "consecutive_fail_count": 0,
                "first_seen_at": None,
                "last_seen_at": None,
                "schema_version": "2.2",
                "code_version": "abc123",
                "summary_json": json.dumps({"checks": {"http": {"status": "OK"}}}),
            },
        )
        session.execute(
            text(
                """
                INSERT INTO maintenance_runs (
                    id, tenant_id, process_name, service_id, outcome, started_at, finished_at,
                    consecutive_fail_count, first_seen_at, last_seen_at, schema_version, code_version, summary_json
                ) VALUES (
                    :id, :tenant_id, :process_name, :service_id, :outcome, :started_at, :finished_at,
                    :consecutive_fail_count, :first_seen_at, :last_seen_at, :schema_version, :code_version, :summary_json
                )
                """
            ),
            {
                "id": "run-watchdog-ok",
                "tenant_id": tenant.id,
                "process_name": "watchdog",
                "service_id": "svc-watchdog",
                "outcome": "OK",
                "started_at": now - timedelta(minutes=9),
                "finished_at": now - timedelta(minutes=8),
                "consecutive_fail_count": 0,
                "first_seen_at": None,
                "last_seen_at": None,
                "schema_version": "2.2",
                "code_version": "abc123",
                "summary_json": json.dumps(
                    {
                        "checks": {
                            "watchdog_staleness": {
                                "status": "WARN",
                                "stale_warn_minutes": 60,
                                "stale_fail_minutes": 180,
                            }
                        }
                    }
                ),
            },
        )
        session.commit()

        response = client.get("/api/console/watchdog/health", headers=_auth_headers(token))
        assert response.status_code == 200
        payload = response.get_json()

        workers = payload["checks"]["workers"]
        assert workers["heartbeat_source"] == "maintenance_runs_ok"
        assert workers["stale_warn_minutes"] == 60
        assert workers["stale_fail_minutes"] == 180
        assert workers["status"] == "Needs action"
    finally:
        session.close()


def test_watchdog_alerts_report_dependency_error_from_runner_outcome(client, session_factory):
    session = session_factory()
    try:
        tenant, _, _, token = seed_tenant_with_user(
            session, tenant_id="tenant-maint-v2-alerts", user_id="owner-maint-v2-alerts", role=UserRole.OWNER
        )
        _create_maintenance_tables(session)

        now = datetime.utcnow()
        session.execute(
            text(
                """
                INSERT INTO maintenance_runs (
                    id, tenant_id, process_name, service_id, outcome, started_at, finished_at,
                    consecutive_fail_count, first_seen_at, last_seen_at, schema_version, code_version, summary_json
                ) VALUES (
                    :id, :tenant_id, :process_name, :service_id, :outcome, :started_at, :finished_at,
                    :consecutive_fail_count, :first_seen_at, :last_seen_at, :schema_version, :code_version, :summary_json
                )
                """
            ),
            {
                "id": "run-runner-dep",
                "tenant_id": tenant.id,
                "process_name": "runner",
                "service_id": "svc-runner",
                "outcome": "DEPENDENCY_ERROR",
                "started_at": now - timedelta(minutes=6),
                "finished_at": now - timedelta(minutes=5),
                "consecutive_fail_count": 0,
                "first_seen_at": None,
                "last_seen_at": None,
                "schema_version": "2.2",
                "code_version": "abc123",
                "summary_json": json.dumps({"dependency": {"domain": "railway_metrics"}}),
            },
        )
        session.commit()

        response = client.get("/api/console/watchdog/alerts", headers=_auth_headers(token))
        assert response.status_code == 200
        payload = response.get_json()
        rows = payload["items"]

        dep_alert = next(row for row in rows if row["type"] == "maintenance_status_fail")
        assert "DEPENDENCY_ERROR" in dep_alert["message"]
        assert dep_alert["status"] == "Needs action"
    finally:
        session.close()
