from __future__ import annotations

from collections import defaultdict
from sqlalchemy.orm import Session

from app.crm.models import CRMCustomerValueSnapshot, CRMOrder
from app.crm.time import utc_now_naive


class CLVService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def compute_snapshots(self) -> list[CRMCustomerValueSnapshot]:
        orders = (
            self.session.query(CRMOrder)
            .filter(
                CRMOrder.tenant_id == self.tenant_id,
                CRMOrder.status.in_(["won", "confirmed", "delivered"]),
            )
            .order_by(CRMOrder.created_at.asc())
            .all()
        )

        by_contact: dict[str, list[CRMOrder]] = defaultdict(list)
        for order in orders:
            by_contact[order.contact_id].append(order)

        snapshots: list[CRMCustomerValueSnapshot] = []
        now = utc_now_naive()

        for contact_id, rows in by_contact.items():
            total_orders = len(rows)
            total_revenue = sum(r.total_amount for r in rows)
            first_order = rows[0]
            cohort = first_order.created_at.strftime("%Y-%m")
            clv_value = total_revenue / total_orders if total_orders else 0

            snapshot = CRMCustomerValueSnapshot(
                tenant_id=self.tenant_id,
                contact_id=contact_id,
                cohort=cohort,
                total_orders=total_orders,
                total_revenue=total_revenue,
                clv_value=clv_value,
                as_of_date=now,
            )
            self.session.add(snapshot)
            snapshots.append(snapshot)

        self.session.flush()
        return snapshots

    def cohort_report(self) -> dict:
        snapshots = (
            self.session.query(CRMCustomerValueSnapshot)
            .filter(CRMCustomerValueSnapshot.tenant_id == self.tenant_id)
            .order_by(CRMCustomerValueSnapshot.as_of_date.desc())
            .all()
        )

        if not snapshots:
            snapshots = self.compute_snapshots()

        cohort_data: dict[str, dict] = defaultdict(lambda: {"customers": 0, "revenue": 0.0, "avg_clv": 0.0})

        for snap in snapshots:
            row = cohort_data[snap.cohort]
            row["customers"] += 1
            row["revenue"] += snap.total_revenue
            row["avg_clv"] += snap.clv_value

        for cohort, row in cohort_data.items():
            if row["customers"]:
                row["avg_clv"] = round(row["avg_clv"] / row["customers"], 2)
            row["revenue"] = round(row["revenue"], 2)

        return {
            "cohorts": [{"cohort": cohort, **data} for cohort, data in sorted(cohort_data.items())],
            "generated_at": utc_now_naive().isoformat(),
        }
