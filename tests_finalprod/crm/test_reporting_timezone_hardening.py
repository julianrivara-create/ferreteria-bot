from __future__ import annotations

from datetime import datetime

from app.crm.models import CRMContact
from app.crm.services.reporting_service import ReportingService
from tests.crm.utils import seed_tenant_with_user


def test_reporting_respects_tenant_timezone_day_boundaries(session_factory):
    session = session_factory()
    try:
        tenant, user, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-report-tz",
            user_id="owner-report-tz",
        )
        tenant.timezone = "America/Argentina/Buenos_Aires"

        # UTC times mapped to local AR time (UTC-3).
        contacts = [
            CRMContact(
                tenant_id=tenant.id,
                name="C1",
                phone="+14155558001",
                email="c1@tz.test",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=0,
                metadata_json={},
                created_at=datetime(2026, 2, 17, 2, 30, 0),  # 2026-02-16 23:30 local
            ),
            CRMContact(
                tenant_id=tenant.id,
                name="C2",
                phone="+14155558002",
                email="c2@tz.test",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=0,
                metadata_json={},
                created_at=datetime(2026, 2, 17, 3, 0, 0),  # 2026-02-17 00:00 local
            ),
            CRMContact(
                tenant_id=tenant.id,
                name="C3",
                phone="+14155558003",
                email="c3@tz.test",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=0,
                metadata_json={},
                created_at=datetime(2026, 2, 17, 4, 0, 0),  # 2026-02-17 01:00 local
            ),
        ]
        session.add_all(contacts)
        session.commit()

        service = ReportingService(session, tenant.id, tenant.timezone)

        day_16 = service.dashboard(date_from=datetime(2026, 2, 16), date_to=datetime(2026, 2, 16))
        day_17 = service.dashboard(date_from=datetime(2026, 2, 17), date_to=datetime(2026, 2, 17))

        assert day_16["leads_created"] == 1
        assert day_17["leads_created"] == 2
    finally:
        session.close()


def test_reporting_daily_series_groups_by_local_day(session_factory):
    session = session_factory()
    try:
        tenant, user, _, _ = seed_tenant_with_user(
            session,
            tenant_id="tenant-report-series",
            user_id="owner-report-series",
        )
        tenant.timezone = "America/Argentina/Buenos_Aires"

        session.add(
            CRMContact(
                tenant_id=tenant.id,
                name="Series-1",
                phone="+14155558004",
                email="series-1@tz.test",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=0,
                metadata_json={},
                created_at=datetime(2026, 2, 17, 2, 59, 0),  # Local 16th
            )
        )
        session.add(
            CRMContact(
                tenant_id=tenant.id,
                name="Series-2",
                phone="+14155558005",
                email="series-2@tz.test",
                source_channel="web",
                owner_user_id=user.id,
                status="lead",
                score=0,
                metadata_json={},
                created_at=datetime(2026, 2, 17, 3, 1, 0),  # Local 17th
            )
        )
        session.commit()

        data = ReportingService(session, tenant.id, tenant.timezone).dashboard()
        series = {row["day"]: row["leads"] for row in data["daily_leads"]}

        assert series["2026-02-16"] == 1
        assert series["2026-02-17"] == 1
    finally:
        session.close()
