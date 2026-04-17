from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB

from app.crm.db import CRMBase
from app.crm.domain.enums import (
    AutomationTrigger,
    DealStatus,
    MessageDirection,
    TagScope,
    TaskStatus,
    UserRole,
)
from app.crm.time import utc_now_naive


def _uuid() -> str:
    return str(uuid.uuid4())


JSONType = JSON().with_variant(JSONB, "postgresql")


class TimeStampedMixin:
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class SoftDeleteMixin:
    deleted_at = Column(DateTime, nullable=True, index=True)


class CRMTenant(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_tenants"

    id = Column(String(36), primary_key=True, default=_uuid)
    business_name = Column(String(255), nullable=False)
    timezone = Column(String(64), nullable=False, default="America/Argentina/Buenos_Aires")
    currency = Column(String(3), nullable=False, default="USD")
    channels = Column(JSONType, nullable=False, default=list)
    integration_settings = Column(JSONType, nullable=False, default=dict)
    pipeline_config = Column(JSONType, nullable=False, default=list)
    data_retention_days = Column(Integer, nullable=False, default=365)
    quiet_hours_start = Column(String(5), nullable=False, default="22:00")
    quiet_hours_end = Column(String(5), nullable=False, default="08:00")
    followup_min_interval_minutes = Column(Integer, nullable=False, default=60)
    webhook_auth_mode = Column(String(16), nullable=False, default="token")
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("followup_min_interval_minutes >= 1", name="ck_crm_tenants_followup_min_interval_positive"),
        CheckConstraint(
            "webhook_auth_mode IN ('token', 'hmac', 'both')",
            name="ck_crm_tenants_webhook_auth_mode_valid",
        ),
    )


class CRMUser(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_users"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(32), nullable=True)
    role = Column(SQLEnum(UserRole, name="crm_user_role"), nullable=False, default=UserRole.SALES)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_users_tenant_id_id"),
        UniqueConstraint("tenant_id", "email", name="uq_crm_users_tenant_email"),
    )


class CRMPipelineStage(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_pipeline_stages"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    position = Column(Integer, nullable=False)
    is_won = Column(Boolean, nullable=False, default=False)
    is_lost = Column(Boolean, nullable=False, default=False)
    sla_hours = Column(Integer, nullable=True)
    color = Column(String(16), nullable=False, default="#1f6feb")

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_pipeline_stages_tenant_id_id"),
        UniqueConstraint("tenant_id", "name", name="uq_crm_pipeline_stages_tenant_name"),
        UniqueConstraint("tenant_id", "position", name="uq_crm_pipeline_stages_tenant_position"),
    )


class CRMTag(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_tags"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    color = Column(String(16), nullable=False, default="#1f6feb")
    scope = Column(SQLEnum(TagScope, name="crm_tag_scope"), nullable=False, default=TagScope.BOTH)
    created_by_user_id = Column(String(36), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_tags_tenant_id_id"),
        UniqueConstraint("tenant_id", "name", name="uq_crm_tags_tenant_name"),
    )


class CRMContact(CRMBase, TimeStampedMixin, SoftDeleteMixin):
    __tablename__ = "crm_contacts"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    external_ref = Column(String(120), nullable=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(32), nullable=True)
    email = Column(String(255), nullable=True)
    source_channel = Column(String(32), nullable=True)
    status = Column(String(32), nullable=False, default="lead")
    score = Column(Integer, nullable=False, default=0)
    owner_user_id = Column(String(36), nullable=True)
    primary_deal_id = Column(String(36), nullable=True, index=True)
    last_activity_at = Column(DateTime, nullable=True, index=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_contacts_tenant_id_id"),
        UniqueConstraint("tenant_id", "phone", name="uq_crm_contacts_tenant_phone"),
        UniqueConstraint("tenant_id", "email", name="uq_crm_contacts_tenant_email"),
        Index("ix_crm_contacts_tenant_last_activity", "tenant_id", "last_activity_at"),
        Index("ix_crm_contacts_tenant_created", "tenant_id", "created_at"),
    )


class CRMConversation(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_conversations"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    channel = Column(String(32), nullable=False, index=True)
    external_id = Column(String(255), nullable=True)
    started_at = Column(DateTime, nullable=False, default=utc_now_naive)
    last_message_at = Column(DateTime, nullable=True, index=True)
    is_open = Column(Boolean, nullable=False, default=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_conversations_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["crm_contacts.tenant_id", "crm_contacts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "channel", "external_id", name="uq_crm_conversations_tenant_channel_external"),
        Index("ix_crm_conversations_tenant_channel", "tenant_id", "channel"),
    )


class CRMMessage(CRMBase):
    __tablename__ = "crm_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    channel = Column(String(32), nullable=False, index=True)
    direction = Column(SQLEnum(MessageDirection, name="crm_message_direction"), nullable=False)
    body = Column(Text, nullable=True)
    external_message_id = Column(String(255), nullable=True)
    idempotency_key = Column(String(255), nullable=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_messages_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["crm_conversations.tenant_id", "crm_conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["crm_contacts.tenant_id", "crm_contacts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "external_message_id", name="uq_crm_messages_tenant_external"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_crm_messages_tenant_idempotency"),
        Index("ix_crm_messages_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"),
        Index("ix_crm_messages_tenant_contact_created", "tenant_id", "contact_id", "created_at"),
        Index("ix_crm_messages_tenant_created", "tenant_id", "created_at"),
    )


class CRMAttachment(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_attachments"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    message_id = Column(String(36), nullable=True, index=True)
    contact_id = Column(String(36), nullable=True, index=True)
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=True)
    storage_url = Column(String(500), nullable=False)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["crm_messages.tenant_id", "crm_messages.id"],
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["crm_contacts.tenant_id", "crm_contacts.id"],
            ondelete="SET NULL",
        ),
    )


class CRMDeal(CRMBase, TimeStampedMixin, SoftDeleteMixin):
    __tablename__ = "crm_deals"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    stage_id = Column(String(36), nullable=False, index=True)
    owner_user_id = Column(String(36), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    status = Column(SQLEnum(DealStatus, name="crm_deal_status"), nullable=False, default=DealStatus.OPEN)
    score = Column(Integer, nullable=False, default=0)
    amount_estimated = Column(Float, nullable=True)
    amount_final = Column(Float, nullable=True)
    currency = Column(String(3), nullable=False, default="USD")
    source_channel = Column(String(32), nullable=True)
    expected_close_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True, index=True)
    last_stage_changed_at = Column(DateTime, nullable=True, index=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_deals_tenant_id_id"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["tenant_id", "stage_id"],
            ["crm_pipeline_stages.tenant_id", "crm_pipeline_stages.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_crm_deals_tenant_stage", "tenant_id", "stage_id"),
        Index("ix_crm_deals_tenant_status", "tenant_id", "status"),
        Index("ix_crm_deals_tenant_owner", "tenant_id", "owner_user_id"),
        Index("ix_crm_deals_tenant_created", "tenant_id", "created_at"),
        Index("ix_crm_deals_tenant_contact_created", "tenant_id", "contact_id", "created_at"),
        Index("ix_crm_deals_tenant_stage_last_activity", "tenant_id", "stage_id", "last_activity_at"),
    )


class CRMTask(CRMBase, TimeStampedMixin, SoftDeleteMixin):
    __tablename__ = "crm_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=True, index=True)
    deal_id = Column(String(36), nullable=True, index=True)
    assigned_to_user_id = Column(String(36), nullable=False, index=True)
    created_by_user_id = Column(String(36), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(TaskStatus, name="crm_task_status"), nullable=False, default=TaskStatus.TODO)
    priority = Column(String(16), nullable=False, default="medium")
    due_at = Column(DateTime, nullable=True, index=True)
    reminder_at = Column(DateTime, nullable=True, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_tasks_tenant_id_id"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="SET NULL"),
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="SET NULL"),
        Index("ix_crm_tasks_tenant_due_status", "tenant_id", "due_at", "status"),
        Index("ix_crm_tasks_tenant_status_due", "tenant_id", "status", "due_at"),
        Index("ix_crm_tasks_tenant_created", "tenant_id", "created_at"),
        Index("ix_crm_tasks_tenant_assigned_status", "tenant_id", "assigned_to_user_id", "status"),
    )


class CRMNote(CRMBase, TimeStampedMixin, SoftDeleteMixin):
    __tablename__ = "crm_notes"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=True, index=True)
    deal_id = Column(String(36), nullable=True, index=True)
    author_user_id = Column(String(36), nullable=False, index=True)
    body = Column(Text, nullable=False)
    pinned = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="CASCADE"),
    )


class CRMContactTag(CRMBase):
    __tablename__ = "crm_contact_tags"

    tenant_id = Column(String(36), primary_key=True)
    contact_id = Column(String(36), primary_key=True)
    tag_id = Column(String(36), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "tag_id"], ["crm_tags.tenant_id", "crm_tags.id"], ondelete="CASCADE"),
    )


class CRMDealTag(CRMBase):
    __tablename__ = "crm_deal_tags"

    tenant_id = Column(String(36), primary_key=True)
    deal_id = Column(String(36), primary_key=True)
    tag_id = Column(String(36), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "tag_id"], ["crm_tags.tenant_id", "crm_tags.id"], ondelete="CASCADE"),
    )


class CRMProductInterest(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_product_interests"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    deal_id = Column(String(36), nullable=True, index=True)
    model = Column(String(120), nullable=False)
    variant = Column(String(120), nullable=True)
    options_json = Column(JSONType, nullable=False, default=dict)
    priority = Column(String(16), nullable=False, default="medium")
    last_seen_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_product_interests_tenant_id_id"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="SET NULL"),
        Index("ix_crm_product_interests_tenant_model", "tenant_id", "model"),
    )


class CRMPriceQuote(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_price_quotes"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    deal_id = Column(String(36), nullable=True, index=True)
    product_interest_id = Column(String(36), nullable=True, index=True)
    quoted_by_user_id = Column(String(36), nullable=True)
    quoted_price = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    valid_until = Column(DateTime, nullable=True)
    status = Column(String(24), nullable=False, default="sent")
    quote_payload = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="SET NULL"),
        ForeignKeyConstraint(
            ["tenant_id", "product_interest_id"],
            ["crm_product_interests.tenant_id", "crm_product_interests.id"],
            ondelete="SET NULL",
        ),
    )


class CRMOrder(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_orders"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    deal_id = Column(String(36), nullable=True, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="created", index=True)
    payment_status = Column(String(24), nullable=False, default="pending", index=True)
    total_amount = Column(Float, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="USD")
    delivery_name = Column(String(200), nullable=True)
    delivery_phone = Column(String(32), nullable=True)
    delivery_address = Column(String(400), nullable=True)
    delivery_eta = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_orders_tenant_id_id"),
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="SET NULL"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="RESTRICT"),
    )


class CRMOrderItem(CRMBase):
    __tablename__ = "crm_order_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    order_id = Column(String(36), nullable=False, index=True)
    product_sku = Column(String(120), nullable=True)
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    metadata_json = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "order_id"], ["crm_orders.tenant_id", "crm_orders.id"], ondelete="CASCADE"),
    )


class CRMAutomation(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_automations"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    trigger_type = Column(SQLEnum(AutomationTrigger, name="crm_automation_trigger"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    cooldown_minutes = Column(Integer, nullable=False, default=0)
    conditions_json = Column(JSONType, nullable=False, default=dict)
    actions_json = Column(JSONType, nullable=False, default=list)
    created_by_user_id = Column(String(36), nullable=True)
    last_run_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_automations_tenant_id_id"),
        Index("ix_crm_automations_tenant_trigger_enabled", "tenant_id", "trigger_type", "enabled"),
    )


class CRMAutomationRun(CRMBase):
    __tablename__ = "crm_automation_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    automation_id = Column(String(36), nullable=False, index=True)
    trigger_type = Column(String(64), nullable=False, index=True)
    trigger_event_id = Column(String(255), nullable=True, index=True)
    trigger_event_key = Column(String(255), nullable=True, index=True)
    run_key = Column(String(255), nullable=False)
    dry_run = Column(Boolean, nullable=False, default=False)
    matched_rule_ids = Column(JSONType, nullable=False, default=list)
    actions_count = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="success", index=True)
    event_payload = Column(JSONType, nullable=False, default=dict)
    result_payload = Column(JSONType, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "automation_id"], ["crm_automations.tenant_id", "crm_automations.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "automation_id", "run_key", name="uq_crm_automation_runs_tenant_automation_run_key"),
        Index("ix_crm_automation_runs_tenant_executed", "tenant_id", "executed_at"),
    )


class CRMScoringRule(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_scoring_rules"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    signal_key = Column(String(80), nullable=False, index=True)
    points = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    conditions_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_scoring_rules_tenant_id_id"),
        UniqueConstraint("tenant_id", "name", name="uq_crm_scoring_rules_tenant_name"),
    )


class CRMDealScoreEvent(CRMBase):
    __tablename__ = "crm_deal_score_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    deal_id = Column(String(36), nullable=False, index=True)
    rule_id = Column(String(36), nullable=True, index=True)
    signal_key = Column(String(80), nullable=False)
    delta = Column(Integer, nullable=False)
    previous_score = Column(Integer, nullable=False)
    new_score = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    metadata_json = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "rule_id"], ["crm_scoring_rules.tenant_id", "crm_scoring_rules.id"], ondelete="SET NULL"),
    )


class CRMDealEvent(CRMBase):
    __tablename__ = "crm_deal_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    deal_id = Column(String(36), nullable=False, index=True)
    actor_user_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    stage_reason = Column(String(255), nullable=True, index=True)
    payload = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="CASCADE"),
        Index("ix_crm_deal_events_tenant_deal_created", "tenant_id", "deal_id", "created_at"),
    )


class CRMTaskEvent(CRMBase):
    __tablename__ = "crm_task_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    task_id = Column(String(36), nullable=False, index=True)
    actor_user_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    payload = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "task_id"], ["crm_tasks.tenant_id", "crm_tasks.id"], ondelete="CASCADE"),
        Index("ix_crm_task_events_tenant_task_created", "tenant_id", "task_id", "created_at"),
    )


class CRMMessageEvent(CRMBase):
    __tablename__ = "crm_message_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    message_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="sent", index=True)
    ab_variant = Column(String(8), nullable=True, index=True)
    variant_key = Column(String(255), nullable=True, index=True)
    objection_type = Column(String(64), nullable=True, index=True)
    stage_at_send = Column(String(32), nullable=True, index=True)
    replied_within_24h = Column(Boolean, nullable=True, index=True)
    stage_progress_within_7d = Column(Boolean, nullable=True, index=True)
    final_outcome = Column(String(16), nullable=True, index=True)
    payload = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["crm_messages.tenant_id", "crm_messages.id"], ondelete="CASCADE"),
        Index(
            "ix_crm_message_events_tenant_stage_objection_variant",
            "tenant_id",
            "stage_at_send",
            "objection_type",
            "ab_variant",
        ),
    )


class CRMAuditLog(CRMBase):
    __tablename__ = "crm_audit_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), nullable=True, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    before_data = Column(JSONType, nullable=True)
    after_data = Column(JSONType, nullable=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)
    request_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        Index("ix_crm_audit_logs_tenant_entity_created", "tenant_id", "entity_type", "created_at"),
    )


class CRMWebhookEvent(CRMBase):
    __tablename__ = "crm_webhook_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(64), nullable=False, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    event_key = Column(String(255), nullable=False)
    payload = Column(JSONType, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="received", index=True)
    duplicate_count = Column(Integer, nullable=False, default=0)
    last_received_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "event_type", "event_key", name="uq_crm_webhook_events_tenant_source_type_key"),
        Index("ix_crm_webhook_events_tenant_status_created", "tenant_id", "status", "created_at"),
    )


class CRMOutboundDraft(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_outbound_drafts"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=True, index=True)
    automation_run_id = Column(String(36), nullable=True, index=True)
    channel = Column(String(32), nullable=False, default="whatsapp")
    body = Column(Text, nullable=False)
    scheduled_for = Column(DateTime, nullable=True, index=True)
    status = Column(String(24), nullable=False, default="draft")
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
    )


class CRMPlaybook(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_playbooks"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    objection_key = Column(String(64), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    channel = Column(String(32), nullable=False, default="whatsapp")
    suggested_response = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "objection_key", "channel", "title", name="uq_crm_playbooks_tenant_objection_title"),
    )


class CRMSLABreach(CRMBase):
    __tablename__ = "crm_sla_breaches"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    deal_id = Column(String(36), nullable=False, index=True)
    stage_id = Column(String(36), nullable=False, index=True)
    threshold_hours = Column(Integer, nullable=False)
    breached_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)
    resolved_at = Column(DateTime, nullable=True, index=True)
    status = Column(String(24), nullable=False, default="open", index=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "deal_id"], ["crm_deals.tenant_id", "crm_deals.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "stage_id"], ["crm_pipeline_stages.tenant_id", "crm_pipeline_stages.id"], ondelete="CASCADE"),
        Index("ix_crm_sla_breaches_tenant_status", "tenant_id", "status"),
    )


class CRMLeadAssignmentRule(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_lead_assignment_rules"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    channel = Column(String(32), nullable=False, default="whatsapp", index=True)
    sort_order = Column(Integer, nullable=False, default=1)
    weight = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["crm_users.tenant_id", "crm_users.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "channel", "user_id", name="uq_crm_assignment_rule_tenant_channel_user"),
    )


class CRMAssignmentCursor(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_assignment_cursors"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(32), nullable=False, default="whatsapp")
    next_index = Column(Integer, nullable=False, default=0)
    last_assigned_user_id = Column(String(36), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_crm_assignment_cursor_tenant_channel"),
    )


class CRMWhatsAppTemplate(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_whatsapp_templates"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(64), nullable=False)
    language = Column(String(16), nullable=False, default="es_AR")
    body_template = Column(Text, nullable=False)
    variables_json = Column(JSONType, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="draft", index=True)
    current_version = Column(Integer, nullable=False, default=1)
    approved_by_user_id = Column(String(36), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_crm_whatsapp_templates_tenant_id_id"),
        UniqueConstraint("tenant_id", "name", "language", name="uq_crm_whatsapp_template_tenant_name_lang"),
    )


class CRMWhatsAppTemplateApproval(CRMBase):
    __tablename__ = "crm_whatsapp_template_approvals"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    template_id = Column(String(36), nullable=False, index=True)
    requested_by_user_id = Column(String(36), nullable=False, index=True)
    reviewed_by_user_id = Column(String(36), nullable=True, index=True)
    decision = Column(String(24), nullable=False, default="pending", index=True)
    comment = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "template_id"], ["crm_whatsapp_templates.tenant_id", "crm_whatsapp_templates.id"], ondelete="CASCADE"),
    )


class CRMInventorySignal(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_inventory_signals"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    product_sku = Column(String(120), nullable=False, index=True)
    model = Column(String(120), nullable=True, index=True)
    variant = Column(String(120), nullable=True, index=True)
    in_stock = Column(Boolean, nullable=False, default=False, index=True)
    quantity_available = Column(Integer, nullable=False, default=0)
    notified_contacts = Column(JSONType, nullable=False, default=list)
    metadata_json = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_crm_inventory_signal_tenant_model_stock", "tenant_id", "model", "in_stock"),
    )


class CRMCustomerValueSnapshot(CRMBase):
    __tablename__ = "crm_customer_value_snapshots"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=False, index=True)
    cohort = Column(String(32), nullable=False, index=True)
    total_orders = Column(Integer, nullable=False, default=0)
    total_revenue = Column(Float, nullable=False, default=0)
    clv_value = Column(Float, nullable=False, default=0)
    as_of_date = Column(DateTime, nullable=False, default=utc_now_naive, index=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["crm_contacts.tenant_id", "crm_contacts.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "contact_id", "as_of_date", name="uq_crm_customer_value_snapshot"),
    )


class CRMSegment(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_segments"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    filters_json = Column(JSONType, nullable=False, default=dict)
    created_by_user_id = Column(String(36), nullable=True, index=True)
    last_exported_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_crm_segments_tenant_name"),
    )


class CRMDailyKpiRollup(CRMBase):
    __tablename__ = "crm_daily_kpi_rollups"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    bucket_date = Column(DateTime, nullable=False, index=True)
    timezone = Column(String(64), nullable=False)
    payload_json = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint("tenant_id", "bucket_date", name="uq_crm_daily_kpi_rollups_tenant_bucket"),
        Index("ix_crm_daily_kpi_rollups_tenant_bucket", "tenant_id", "bucket_date"),
    )


class CRMInternalNotification(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_internal_notifications"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    severity = Column(String(16), nullable=False, default="info")
    read_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSONType, nullable=False, default=dict)


class CRMRetentionPolicy(CRMBase, TimeStampedMixin):
    __tablename__ = "crm_retention_policies"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("crm_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    retention_days = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", name="uq_crm_retention_tenant_entity"),
        CheckConstraint("retention_days > 0", name="ck_crm_retention_days_positive"),
    )
