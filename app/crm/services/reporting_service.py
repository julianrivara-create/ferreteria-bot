from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crm.domain.enums import DealStatus
from app.crm.models import (
    CRMContact,
    CRMDailyKpiRollup,
    CRMDeal,
    CRMDealEvent,
    CRMMessage,
    CRMOrder,
    CRMProductInterest,
    CRMTask,
)
from app.crm.time import utc_now_naive


class ReportingService:
    def __init__(self, session: Session, tenant_id: str, timezone_name: str):
        self.session = session
        self.tenant_id = tenant_id
        self.tz = ZoneInfo(timezone_name)

    def _localize(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=self.tz)
        return value.astimezone(self.tz)

    def _to_utc_bounds(self, date_from: datetime | None, date_to: datetime | None) -> tuple[datetime | None, datetime | None]:
        if date_from is None and date_to is None:
            return None, None

        start = self._localize(date_from).astimezone(ZoneInfo("UTC")) if date_from else None

        end = None
        if date_to:
            local_end = self._localize(date_to)
            # Date-only semantics: [from, to) by full local day.
            if (
                local_end.hour == 0
                and local_end.minute == 0
                and local_end.second == 0
                and local_end.microsecond == 0
            ):
                local_end = local_end + timedelta(days=1)
            end = local_end.astimezone(ZoneInfo("UTC"))
        return start, end

    @staticmethod
    def _apply_bounds(query, column, start_utc: datetime | None, end_utc: datetime | None):
        if start_utc:
            query = query.filter(column >= start_utc)
        if end_utc:
            query = query.filter(column < end_utc)
        return query

    def dashboard(self, date_from: datetime | None = None, date_to: datetime | None = None) -> dict:
        start_utc, end_utc = self._to_utc_bounds(date_from, date_to)

        contact_query = self.session.query(func.count(CRMContact.id)).filter(
            CRMContact.tenant_id == self.tenant_id,
            CRMContact.deleted_at.is_(None),
        )
        contact_query = self._apply_bounds(contact_query, CRMContact.created_at, start_utc, end_utc)
        leads_created = contact_query.scalar() or 0

        deal_query = self.session.query(CRMDeal).filter(
            CRMDeal.tenant_id == self.tenant_id,
            CRMDeal.deleted_at.is_(None),
        )
        deal_query = self._apply_bounds(deal_query, CRMDeal.created_at, start_utc, end_utc)
        deals = deal_query.all()

        deals_by_stage_rows = (
            self._apply_bounds(
                self.session.query(CRMDeal.stage_id, func.count(CRMDeal.id).label("count")).filter(
                    CRMDeal.tenant_id == self.tenant_id,
                    CRMDeal.deleted_at.is_(None),
                ),
                CRMDeal.created_at,
                start_utc,
                end_utc,
            )
            .group_by(CRMDeal.stage_id)
            .all()
        )
        deals_by_stage = {stage: count for stage, count in deals_by_stage_rows}

        won_deals = [d for d in deals if d.status == DealStatus.WON]
        lost_deals = [d for d in deals if d.status == DealStatus.LOST]
        open_deals = [d for d in deals if d.status == DealStatus.OPEN]

        conversion_rate = (len(won_deals) / len(deals) * 100.0) if deals else 0.0

        won_orders_query = self.session.query(CRMOrder).filter(
            CRMOrder.tenant_id == self.tenant_id,
            CRMOrder.status.in_(["won", "confirmed", "delivered"]),
        )
        won_orders_query = self._apply_bounds(won_orders_query, CRMOrder.created_at, start_utc, end_utc)
        won_orders = won_orders_query.all()
        revenue = sum(float(o.total_amount or 0) for o in won_orders)
        avg_ticket = (revenue / len(won_orders)) if won_orders else 0.0

        task_query = self.session.query(CRMTask).filter(
            CRMTask.tenant_id == self.tenant_id,
            CRMTask.deleted_at.is_(None),
        )
        task_query = self._apply_bounds(task_query, CRMTask.created_at, start_utc, end_utc)

        followup_total = task_query.filter(CRMTask.due_at.is_not(None)).count()
        followup_ok = task_query.filter(
            CRMTask.due_at.is_not(None),
            CRMTask.completed_at.is_not(None),
            CRMTask.completed_at <= CRMTask.due_at,
        ).count()
        followup_compliance = (followup_ok / followup_total * 100.0) if followup_total else 0.0

        top_products = (
            self._apply_bounds(
                self.session.query(CRMProductInterest.model, func.count(CRMProductInterest.id).label("count")).filter(
                    CRMProductInterest.tenant_id == self.tenant_id,
                ),
                CRMProductInterest.created_at,
                start_utc,
                end_utc,
            )
            .group_by(CRMProductInterest.model)
            .order_by(func.count(CRMProductInterest.id).desc())
            .limit(10)
            .all()
        )

        channel_perf = (
            self._apply_bounds(
                self.session.query(CRMDeal.source_channel, func.count(CRMDeal.id).label("count")).filter(
                    CRMDeal.tenant_id == self.tenant_id,
                    CRMDeal.deleted_at.is_(None),
                ),
                CRMDeal.created_at,
                start_utc,
                end_utc,
            )
            .group_by(CRMDeal.source_channel)
            .all()
        )

        avg_response_seconds = self._avg_response_time_seconds(start_utc, end_utc)
        avg_time_per_stage_hours = self._avg_time_per_stage_hours(start_utc, end_utc)

        return {
            "leads_created": leads_created,
            "deals_by_stage": deals_by_stage,
            "conversion_rate": round(conversion_rate, 2),
            "deals_summary": {
                "open": len(open_deals),
                "won": len(won_deals),
                "lost": len(lost_deals),
            },
            "revenue": round(revenue, 2),
            "avg_ticket": round(avg_ticket, 2),
            "response_time_seconds": avg_response_seconds,
            "followup_compliance": round(followup_compliance, 2),
            "avg_time_per_stage_hours": avg_time_per_stage_hours,
            "top_products_interest": [{"model": m, "count": c} for m, c in top_products],
            "channel_performance": [{"channel": c or "unknown", "count": n} for c, n in channel_perf],
            "daily_leads": self._daily_leads_series(start_utc, end_utc),
        }

    def _avg_response_time_seconds(self, start_utc: datetime | None, end_utc: datetime | None) -> float:
        query = self.session.query(CRMMessage).filter(CRMMessage.tenant_id == self.tenant_id)
        query = self._apply_bounds(query, CRMMessage.created_at, start_utc, end_utc)

        messages = query.order_by(CRMMessage.conversation_id, CRMMessage.created_at.asc()).all()
        if not messages:
            return 0.0

        waits: list[float] = []
        last_inbound_by_conv: dict[str, datetime] = {}

        for msg in messages:
            direction = msg.direction.value if hasattr(msg.direction, "value") else str(msg.direction)
            if direction == "inbound":
                last_inbound_by_conv[msg.conversation_id] = msg.created_at
                continue

            if direction == "outbound" and msg.conversation_id in last_inbound_by_conv:
                delta = (msg.created_at - last_inbound_by_conv[msg.conversation_id]).total_seconds()
                if delta >= 0:
                    waits.append(delta)
                del last_inbound_by_conv[msg.conversation_id]

        if not waits:
            return 0.0
        return round(sum(waits) / len(waits), 2)

    def _avg_time_per_stage_hours(self, start_utc: datetime | None, end_utc: datetime | None) -> dict[str, float]:
        query = self.session.query(CRMDealEvent).filter(
            CRMDealEvent.tenant_id == self.tenant_id,
            CRMDealEvent.event_type == "stage_changed",
        )
        query = self._apply_bounds(query, CRMDealEvent.created_at, start_utc, end_utc)

        events = query.order_by(CRMDealEvent.deal_id.asc(), CRMDealEvent.created_at.asc()).all()
        if not events:
            return {}

        durations_by_stage: dict[str, list[float]] = {}
        last_stage_by_deal: dict[str, str] = {}
        last_time_by_deal: dict[str, datetime] = {}

        for evt in events:
            payload = evt.payload or {}
            prev_stage = payload.get("from_stage") or last_stage_by_deal.get(evt.deal_id)
            next_stage = payload.get("to_stage")

            if prev_stage and evt.deal_id in last_time_by_deal:
                delta_h = (evt.created_at - last_time_by_deal[evt.deal_id]).total_seconds() / 3600.0
                if delta_h >= 0:
                    durations_by_stage.setdefault(prev_stage, []).append(delta_h)

            if next_stage:
                last_stage_by_deal[evt.deal_id] = next_stage
                last_time_by_deal[evt.deal_id] = evt.created_at

        now = utc_now_naive()
        for deal_id, stage in last_stage_by_deal.items():
            started = last_time_by_deal.get(deal_id)
            if not started:
                continue
            delta_h = (now - started).total_seconds() / 3600.0
            if delta_h >= 0:
                durations_by_stage.setdefault(stage, []).append(delta_h)

        return {stage: round(sum(values) / len(values), 2) for stage, values in durations_by_stage.items() if values}

    def _daily_leads_series(self, start_utc: datetime | None, end_utc: datetime | None) -> list[dict]:
        query = self.session.query(CRMContact).filter(
            CRMContact.tenant_id == self.tenant_id,
            CRMContact.deleted_at.is_(None),
        )
        query = self._apply_bounds(query, CRMContact.created_at, start_utc, end_utc)

        buckets: dict[str, int] = {}
        for row in query.all():
            local_day = row.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(self.tz).date().isoformat()
            buckets[local_day] = buckets.get(local_day, 0) + 1
        return [{"day": day, "leads": buckets[day]} for day in sorted(buckets.keys())]

    def export_dashboard_csv(self, date_from: datetime | None = None, date_to: datetime | None = None) -> str:
        return "".join(self.stream_dashboard_csv(date_from=date_from, date_to=date_to))

    def stream_dashboard_csv(self, date_from: datetime | None = None, date_to: datetime | None = None):
        dashboard = self.dashboard(date_from=date_from, date_to=date_to)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "value"])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        rows = [
            ["leads_created", dashboard["leads_created"]],
            ["conversion_rate", dashboard["conversion_rate"]],
            ["revenue", dashboard["revenue"]],
            ["avg_ticket", dashboard["avg_ticket"]],
            ["response_time_seconds", dashboard["response_time_seconds"]],
            ["followup_compliance", dashboard["followup_compliance"]],
        ]
        for item in dashboard["top_products_interest"]:
            rows.append([f"top_product:{item['model']}", item["count"]])
        for item in dashboard["channel_performance"]:
            rows.append([f"channel:{item['channel']}", item["count"]])

        for row in rows:
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    def upsert_daily_rollup(self, bucket_date: datetime, *, date_from: datetime, date_to: datetime) -> CRMDailyKpiRollup:
        payload = self.dashboard(date_from=date_from, date_to=date_to)
        row = (
            self.session.query(CRMDailyKpiRollup)
            .filter(CRMDailyKpiRollup.tenant_id == self.tenant_id, CRMDailyKpiRollup.bucket_date == bucket_date)
            .first()
        )
        if row is None:
            row = CRMDailyKpiRollup(
                tenant_id=self.tenant_id,
                bucket_date=bucket_date,
                timezone=str(self.tz),
                payload_json=payload,
            )
            self.session.add(row)
        else:
            row.timezone = str(self.tz)
            row.payload_json = payload

        self.session.flush()
        return row
