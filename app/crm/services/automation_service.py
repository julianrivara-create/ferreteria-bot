from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crm.domain.enums import AutomationAction, AutomationTrigger, DealStatus, TaskStatus
from app.crm.models import (
    CRMAutomation,
    CRMAutomationRun,
    CRMContactTag,
    CRMDeal,
    CRMDealEvent,
    CRMInternalNotification,
    CRMOrder,
    CRMOutboundDraft,
    CRMTenant,
    CRMTag,
    CRMTask,
)
from app.crm.repositories.automations import AutomationRepository
from app.crm.services.condition_eval import matches_conditions
from app.crm.time import utc_now_naive


class AutomationService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = AutomationRepository(session, tenant_id)

    def run_trigger(
        self,
        trigger: AutomationTrigger | str,
        event: dict[str, Any],
        *,
        trigger_event_id: str | None = None,
        trigger_event_key: str | None = None,
        dry_run: bool = False,
    ) -> list[CRMAutomationRun]:
        if self._is_automation_loop(event):
            return []

        automations = sorted(self.repo.list_for_trigger(trigger), key=lambda a: (a.created_at or datetime.min, a.id))
        runs: list[CRMAutomationRun] = []
        max_actions_per_minute = self._tenant_action_cap()

        for automation in automations:
            if not self._is_allowed_by_cooldown(automation):
                continue

            if not matches_conditions(automation.conditions_json or {}, event):
                continue

            run_key = self._run_key(automation.id, trigger, trigger_event_key or trigger_event_id, event)
            existing = (
                self.session.query(CRMAutomationRun)
                .filter(
                    CRMAutomationRun.tenant_id == self.tenant_id,
                    CRMAutomationRun.automation_id == automation.id,
                    CRMAutomationRun.run_key == run_key,
                )
                .first()
            )
            if existing is not None:
                # Already processed for this rule + event.
                continue

            actions_payload = automation.actions_json or []
            planned_count = len(actions_payload)
            throttled = (not dry_run) and (self._actions_executed_last_minute() + planned_count > max_actions_per_minute)

            run = self.repo.add_run(
                {
                    "automation_id": automation.id,
                    "trigger_type": str(trigger),
                    "trigger_event_id": trigger_event_id,
                    "trigger_event_key": trigger_event_key,
                    "run_key": run_key,
                    "dry_run": dry_run,
                    "matched_rule_ids": [automation.id],
                    "actions_count": 0,
                    "status": "pending",
                    "event_payload": event,
                    "result_payload": {},
                }
            )

            try:
                if throttled:
                    run.status = "throttled"
                    run.result_payload = {
                        "actions": [],
                        "reason": "tenant_action_cap_exceeded",
                        "max_actions_per_minute": max_actions_per_minute,
                    }
                elif dry_run:
                    run.status = "dry_run"
                    run.result_payload = {
                        "actions": self._preview_actions(actions_payload, event),
                    }
                else:
                    result = self._apply_actions(actions_payload, event)
                    run.status = "success"
                    run.result_payload = result
                    run.actions_count = len(result.get("actions", []))
                    automation.last_run_at = utc_now_naive()
            except Exception as exc:  # pragma: no cover - defensive path
                run.status = "failed"
                run.error_message = str(exc)

            runs.append(run)

        self.session.flush()
        return runs

    def _is_allowed_by_cooldown(self, automation: CRMAutomation) -> bool:
        if not automation.cooldown_minutes or not automation.last_run_at:
            return True
        threshold = utc_now_naive() - timedelta(minutes=automation.cooldown_minutes)
        return automation.last_run_at <= threshold

    def _is_automation_loop(self, event: dict[str, Any]) -> bool:
        source = str(event.get("source") or "")
        if source == "automation":
            hop = int(event.get("automation_hop") or 0)
            return hop >= 1
        return False

    def _tenant_action_cap(self) -> int:
        # Optional per-tenant cap under tenant.integration_settings.
        # Falls back to a safe default.
        from app.crm.models import CRMTenant

        tenant = self.session.query(CRMTenant).filter(CRMTenant.id == self.tenant_id).first()
        raw = (tenant.integration_settings or {}).get("max_automation_actions_per_minute") if tenant else None
        try:
            cap = int(raw)
        except (TypeError, ValueError):
            cap = 120
        return max(1, cap)

    def _actions_executed_last_minute(self) -> int:
        since = utc_now_naive() - timedelta(minutes=1)
        value = (
            self.session.query(func.coalesce(func.sum(CRMAutomationRun.actions_count), 0))
            .filter(
                CRMAutomationRun.tenant_id == self.tenant_id,
                CRMAutomationRun.dry_run.is_(False),
                CRMAutomationRun.executed_at >= since,
                CRMAutomationRun.status == "success",
            )
            .scalar()
        )
        return int(value or 0)

    def _run_key(
        self,
        automation_id: str,
        trigger: AutomationTrigger | str,
        trigger_event_key: str | None,
        event: dict[str, Any],
    ) -> str:
        payload = {
            "trigger": str(trigger),
            "trigger_event_key": trigger_event_key,
            "event": event,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"{automation_id}:{digest}"

    def _tenant_followup_policy(self) -> dict[str, Any]:
        tenant = self.session.query(CRMTenant).filter(CRMTenant.id == self.tenant_id).first()
        timezone_name = (tenant.timezone if tenant else "UTC") or "UTC"
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("UTC")
            timezone_name = "UTC"

        quiet_start = (tenant.quiet_hours_start if tenant else "22:00") or "22:00"
        quiet_end = (tenant.quiet_hours_end if tenant else "08:00") or "08:00"
        try:
            min_interval = int(tenant.followup_min_interval_minutes if tenant else 60)
        except (TypeError, ValueError):
            min_interval = 60
        return {
            "timezone": timezone_name,
            "tz": tz,
            "quiet_start": quiet_start,
            "quiet_end": quiet_end,
            "min_interval_minutes": max(1, min_interval),
        }

    @staticmethod
    def _is_followup_payload(payload: dict[str, Any], *, default: bool = False) -> bool:
        if "is_followup" in payload:
            return bool(payload.get("is_followup"))
        kind = str(payload.get("kind") or "").strip().lower()
        if kind:
            return kind == "followup"
        title = str(payload.get("title") or "").strip().lower()
        if "follow-up" in title or "followup" in title:
            return True
        return default

    @staticmethod
    def _parse_hhmm(raw: str) -> tuple[int, int] | None:
        try:
            hh, mm = str(raw).split(":", 1)
            h, m = int(hh), int(mm)
        except Exception:
            return None
        if h < 0 or h > 23 or m < 0 or m > 59:
            return None
        return h, m

    def _shift_out_of_quiet_hours(self, due_utc_naive: datetime, policy: dict[str, Any]) -> datetime:
        start = self._parse_hhmm(policy["quiet_start"])
        end = self._parse_hhmm(policy["quiet_end"])
        if not start or not end:
            return due_utc_naive

        tz: ZoneInfo = policy["tz"]
        due_local = due_utc_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        local_time = (due_local.hour, due_local.minute)
        start_time = start
        end_time = end

        crosses_midnight = start_time > end_time
        in_quiet = False
        if crosses_midnight:
            in_quiet = local_time >= start_time or local_time < end_time
        else:
            in_quiet = start_time <= local_time < end_time
        if not in_quiet:
            return due_utc_naive

        if crosses_midnight and local_time >= start_time:
            next_day = due_local + timedelta(days=1)
            allowed_local = next_day.replace(hour=end_time[0], minute=end_time[1], second=0, microsecond=0)
        else:
            allowed_local = due_local.replace(hour=end_time[0], minute=end_time[1], second=0, microsecond=0)
            if not crosses_midnight and local_time >= end_time:
                allowed_local = allowed_local + timedelta(days=1)

        return allowed_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    def _find_recent_followup(
        self,
        *,
        conversation_id: str | None,
        deal_id: str | None,
        window_from: datetime,
    ) -> CRMOutboundDraft | CRMTask | None:
        if not conversation_id and not deal_id:
            return None

        draft_query = self.session.query(CRMOutboundDraft).filter(CRMOutboundDraft.tenant_id == self.tenant_id)
        if conversation_id:
            draft_query = draft_query.filter(CRMOutboundDraft.conversation_id == conversation_id)
        drafts = (
            draft_query.filter(
                CRMOutboundDraft.created_at >= window_from,
                CRMOutboundDraft.status.in_(["draft", "scheduled", "sent"]),
            )
            .order_by(CRMOutboundDraft.created_at.desc())
            .all()
        )
        for draft in drafts:
            if str((draft.metadata_json or {}).get("kind") or "").lower() == "followup":
                return draft

        task_query = self.session.query(CRMTask).filter(CRMTask.tenant_id == self.tenant_id)
        if deal_id:
            task_query = task_query.filter(CRMTask.deal_id == deal_id)
        tasks = (
            task_query.filter(
                CRMTask.created_at >= window_from,
                CRMTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]),
            )
            .order_by(CRMTask.created_at.desc())
            .all()
        )
        for task in tasks:
            if str((task.metadata_json or {}).get("kind") or "").lower() == "followup":
                return task
        return None

    @staticmethod
    def _priority_for_followup(payload: dict[str, Any], event: dict[str, Any]) -> str:
        requested = str(payload.get("priority", "medium") or "medium").lower()
        if requested not in {"low", "medium", "high"}:
            requested = "medium"

        intent = str(event.get("intent") or "").upper()
        score = 0
        try:
            score = int(float(event.get("score", 0) or 0))
        except (TypeError, ValueError):
            score = 0
        stock_available = 0
        try:
            stock_available = int(float(event.get("stock_available", event.get("quantity_available", 0)) or 0))
        except (TypeError, ValueError):
            stock_available = 0

        if intent in {"HIGH_INTENT_SIGNAL", "BUYING_SIGNAL"}:
            return "high"
        if score >= 85:
            return "high"
        if stock_available > 0 and stock_available <= 3:
            return "high"
        if score >= 60 and requested == "low":
            return "medium"
        return requested

    def _preview_actions(self, actions: list[dict[str, Any]], event: dict[str, Any]) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        for action in actions:
            action_type = action.get("type")
            previews.append(
                {
                    "type": action_type,
                    "target_contact_id": action.get("contact_id") or event.get("contact_id"),
                    "target_deal_id": action.get("deal_id") or event.get("deal_id"),
                }
            )
        return previews

    def _apply_actions(self, actions: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
        outputs: dict[str, Any] = {"actions": []}
        for action_payload in actions:
            action_name = action_payload.get("type")
            if action_name == AutomationAction.CREATE_TASK.value:
                row = self._action_create_task(action_payload, event)
                if row is not None:
                    outputs["actions"].append({"type": action_name, "task_id": row.id})
                else:
                    outputs["actions"].append({"type": action_name, "status": "suppressed_by_cooldown"})
            elif action_name == AutomationAction.CHANGE_STAGE.value:
                row = self._action_change_stage(action_payload, event)
                outputs["actions"].append({"type": action_name, "deal_id": row.id})
            elif action_name == AutomationAction.ADD_TAG.value:
                row = self._action_add_tag(action_payload, event)
                outputs["actions"].append({"type": action_name, "tag_id": row.id})
            elif action_name == AutomationAction.INTERNAL_NOTIFICATION.value:
                row = self._action_internal_notification(action_payload, event)
                outputs["actions"].append({"type": action_name, "notification_id": row.id})
            elif action_name == AutomationAction.SCHEDULE_OUTBOUND_DRAFT.value:
                row = self._action_schedule_draft(action_payload, event)
                if row is not None:
                    outputs["actions"].append({"type": action_name, "draft_id": row.id})
                else:
                    outputs["actions"].append({"type": action_name, "status": "suppressed_by_cooldown"})
            elif action_name == AutomationAction.CREATE_ORDER.value:
                row = self._action_create_order(action_payload, event)
                outputs["actions"].append({"type": action_name, "order_id": row.id})
            elif action_name == AutomationAction.CREATE_REMINDER.value:
                row = self._action_create_reminder(action_payload, event)
                if row is not None:
                    outputs["actions"].append({"type": action_name, "task_id": row.id})
                else:
                    outputs["actions"].append({"type": action_name, "status": "suppressed_by_cooldown"})
        return outputs

    def _action_create_task(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMTask | None:
        due_minutes = int(payload.get("due_in_minutes", 60))
        assigned_user_id = payload.get("assigned_to_user_id") or event.get("owner_user_id") or event.get("actor_user_id") or "system"
        creator_user_id = event.get("actor_user_id") or assigned_user_id
        now_utc = utc_now_naive()
        due_at = now_utc + timedelta(minutes=due_minutes)
        reminder_at = now_utc + timedelta(minutes=max(1, due_minutes - 15))
        is_followup = self._is_followup_payload(payload, default=False)
        conversation_id = payload.get("conversation_id") or event.get("conversation_id")
        deal_id = payload.get("deal_id") or event.get("deal_id")
        policy = None
        priority = payload.get("priority", "medium")
        if is_followup:
            policy = self._tenant_followup_policy()
            due_at = self._shift_out_of_quiet_hours(due_at, policy)
            reminder_at = self._shift_out_of_quiet_hours(reminder_at, policy)
            window_from = now_utc - timedelta(minutes=policy["min_interval_minutes"])
            recent = self._find_recent_followup(conversation_id=conversation_id, deal_id=deal_id, window_from=window_from)
            if recent is not None:
                return None
            priority = self._priority_for_followup(payload, event)

        row = CRMTask(
            tenant_id=self.tenant_id,
            title=payload.get("title", "Follow-up"),
            description=payload.get("description"),
            status=TaskStatus.TODO,
            priority=priority,
            due_at=due_at,
            reminder_at=reminder_at,
            assigned_to_user_id=assigned_user_id,
            created_by_user_id=creator_user_id,
            contact_id=event.get("contact_id"),
            deal_id=deal_id,
            metadata_json={
                "source": "automation",
                "event": event,
                "kind": "followup" if is_followup else "task",
                "conversation_id": conversation_id,
                "policy": (
                    {
                        "timezone": policy["timezone"],
                        "quiet_hours_start": policy["quiet_start"],
                        "quiet_hours_end": policy["quiet_end"],
                        "followup_min_interval_minutes": policy["min_interval_minutes"],
                    }
                    if policy
                    else None
                ),
            },
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _action_change_stage(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMDeal:
        deal_id = payload.get("deal_id") or event.get("deal_id")
        stage_id = payload.get("stage_id")
        if not deal_id or not stage_id:
            raise ValueError("change_stage requires deal_id and stage_id")

        deal = (
            self.session.query(CRMDeal)
            .filter(CRMDeal.tenant_id == self.tenant_id, CRMDeal.id == deal_id)
            .first()
        )
        if deal is None:
            raise ValueError("deal not found")

        from_stage = deal.stage_id
        deal.stage_id = stage_id

        if payload.get("mark_won"):
            deal.status = DealStatus.WON
            deal.closed_at = utc_now_naive()

        self.session.add(
            CRMDealEvent(
                tenant_id=self.tenant_id,
                deal_id=deal.id,
                actor_user_id=event.get("actor_user_id"),
                event_type="stage_changed",
                stage_reason="automation_change_stage",
                payload={"from_stage": from_stage, "to_stage": stage_id, "source": "automation"},
            )
        )
        self.session.flush()
        return deal

    def _action_add_tag(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMTag:
        tag_name = payload.get("tag")
        if not tag_name:
            raise ValueError("add_tag requires tag")

        tag = (
            self.session.query(CRMTag)
            .filter(CRMTag.tenant_id == self.tenant_id, CRMTag.name == tag_name)
            .first()
        )
        if tag is None:
            tag = CRMTag(
                tenant_id=self.tenant_id,
                name=tag_name,
                color=payload.get("color", "#2563eb"),
                scope=payload.get("scope", "both"),
                created_by_user_id=event.get("actor_user_id"),
            )
            self.session.add(tag)
            self.session.flush()

        contact_id = payload.get("contact_id") or event.get("contact_id")
        if contact_id:
            exists = (
                self.session.query(CRMContactTag)
                .filter(
                    CRMContactTag.tenant_id == self.tenant_id,
                    CRMContactTag.contact_id == contact_id,
                    CRMContactTag.tag_id == tag.id,
                )
                .first()
            )
            if exists is None:
                self.session.add(CRMContactTag(tenant_id=self.tenant_id, contact_id=contact_id, tag_id=tag.id))

        self.session.flush()
        return tag

    def _action_internal_notification(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMInternalNotification:
        row = CRMInternalNotification(
            tenant_id=self.tenant_id,
            user_id=payload.get("user_id") or event.get("owner_user_id"),
            title=payload.get("title", "CRM Automation"),
            body=payload.get("body", "Automation executed"),
            severity=payload.get("severity", "info"),
            metadata_json={"event": event},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _action_schedule_draft(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMOutboundDraft | None:
        schedule_minutes = int(payload.get("schedule_in_minutes", 0))
        now_utc = utc_now_naive()
        scheduled_for = now_utc + timedelta(minutes=schedule_minutes)
        conversation_id = payload.get("conversation_id") or event.get("conversation_id")
        deal_id = payload.get("deal_id") or event.get("deal_id")
        is_followup = self._is_followup_payload(payload, default=True)
        policy = None
        if is_followup:
            followup_priority = self._priority_for_followup(payload, event)
            if followup_priority == "high":
                schedule_minutes = min(schedule_minutes, 15)
                scheduled_for = now_utc + timedelta(minutes=schedule_minutes)
            policy = self._tenant_followup_policy()
            scheduled_for = self._shift_out_of_quiet_hours(scheduled_for, policy)
            window_from = now_utc - timedelta(minutes=policy["min_interval_minutes"])
            recent = self._find_recent_followup(conversation_id=conversation_id, deal_id=deal_id, window_from=window_from)
            if recent is not None:
                return None

        row = CRMOutboundDraft(
            tenant_id=self.tenant_id,
            contact_id=payload.get("contact_id") or event.get("contact_id"),
            conversation_id=conversation_id,
            channel=payload.get("channel") or event.get("channel") or "whatsapp",
            body=payload.get("body", ""),
            scheduled_for=scheduled_for,
            status="scheduled" if schedule_minutes > 0 else "draft",
            metadata_json={
                "source": "automation",
                "event": event,
                "kind": "followup" if is_followup else "draft",
                "deal_id": deal_id,
                "policy": (
                    {
                        "timezone": policy["timezone"],
                        "quiet_hours_start": policy["quiet_start"],
                        "quiet_hours_end": policy["quiet_end"],
                        "followup_min_interval_minutes": policy["min_interval_minutes"],
                    }
                    if policy
                    else None
                ),
            },
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _action_create_order(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMOrder:
        row = CRMOrder(
            tenant_id=self.tenant_id,
            deal_id=payload.get("deal_id") or event.get("deal_id"),
            contact_id=payload.get("contact_id") or event.get("contact_id"),
            status=payload.get("status", "created"),
            payment_status=payload.get("payment_status", "pending"),
            total_amount=float(payload.get("total_amount", event.get("amount_estimated", 0) or 0)),
            currency=payload.get("currency", event.get("currency", "USD")),
            delivery_name=payload.get("delivery_name"),
            delivery_phone=payload.get("delivery_phone"),
            delivery_address=payload.get("delivery_address"),
            metadata_json={"source": "automation", "event": event},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _action_create_reminder(self, payload: dict[str, Any], event: dict[str, Any]) -> CRMTask | None:
        reminder_minutes = int(payload.get("remind_in_minutes", 120))
        assigned_user_id = payload.get("assigned_to_user_id") or event.get("owner_user_id") or event.get("actor_user_id") or "system"
        creator_user_id = event.get("actor_user_id") or assigned_user_id
        now_utc = utc_now_naive()
        due_at = now_utc + timedelta(minutes=reminder_minutes)
        is_followup = self._is_followup_payload(payload, default=False)
        conversation_id = payload.get("conversation_id") or event.get("conversation_id")
        deal_id = payload.get("deal_id") or event.get("deal_id")
        policy = None
        priority = payload.get("priority", "medium")
        if is_followup:
            policy = self._tenant_followup_policy()
            due_at = self._shift_out_of_quiet_hours(due_at, policy)
            window_from = now_utc - timedelta(minutes=policy["min_interval_minutes"])
            recent = self._find_recent_followup(conversation_id=conversation_id, deal_id=deal_id, window_from=window_from)
            if recent is not None:
                return None
            priority = self._priority_for_followup(payload, event)

        row = CRMTask(
            tenant_id=self.tenant_id,
            title=payload.get("title", "Reminder"),
            description=payload.get("description", "Automated reminder"),
            status=TaskStatus.TODO,
            priority=priority,
            due_at=due_at,
            reminder_at=due_at,
            assigned_to_user_id=assigned_user_id,
            created_by_user_id=creator_user_id,
            contact_id=event.get("contact_id"),
            deal_id=deal_id,
            metadata_json={
                "source": "automation_reminder",
                "event": event,
                "kind": "followup" if is_followup else "reminder",
                "conversation_id": conversation_id,
            },
        )
        self.session.add(row)
        self.session.flush()
        return row
