from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.crm.domain.enums import AutomationAction, AutomationTrigger, DealStatus, TagScope, TaskStatus, UserRole
from app.crm.services.normalization import normalize_email, normalize_phone_e164


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    sort_by: str = "created_at"
    sort_dir: str = "desc"


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    source_channel: str | None = Field(default=None, max_length=32)
    owner_user_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone_e164(value)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return normalize_email(value)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    source_channel: str | None = Field(default=None, max_length=32)
    owner_user_id: str | None = None
    score: int | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone_e164(value)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return normalize_email(value)


class DealCreate(BaseModel):
    contact_id: str
    title: str = Field(min_length=1, max_length=255)
    stage_id: str
    owner_user_id: str | None = None
    amount_estimated: float | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    source_channel: str | None = Field(default=None, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    stage_id: str | None = None
    owner_user_id: str | None = None
    amount_estimated: float | None = None
    amount_final: float | None = None
    status: DealStatus | None = None
    expected_close_at: datetime | None = None
    occurred_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    contact_id: str | None = None
    deal_id: str | None = None
    assigned_to_user_id: str
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: str = Field(default="medium", max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    assigned_to_user_id: str | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: str | None = Field(default=None, max_length=16)
    status: TaskStatus | None = None
    metadata: dict[str, Any] | None = None


class NoteCreate(BaseModel):
    contact_id: str | None = None
    deal_id: str | None = None
    body: str = Field(min_length=1)
    pinned: bool = False


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str = Field(default="#1f6feb", max_length=16)
    scope: TagScope = TagScope.BOTH


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    trigger_type: AutomationTrigger
    description: str | None = None
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    actions_json: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True
    cooldown_minutes: int = Field(default=0, ge=0)


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    description: str | None = None
    conditions_json: dict[str, Any] | None = None
    actions_json: list[dict[str, Any]] | None = None
    enabled: bool | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0)


class ScoringRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    signal_key: str = Field(min_length=1, max_length=80)
    points: int = Field(ge=-1000, le=1000)
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class TenantSettingsUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, max_length=3)
    channels: list[str] | None = None
    integration_settings: dict[str, Any] | None = None
    data_retention_days: int | None = Field(default=None, ge=1, le=3650)
    quiet_hours_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    followup_min_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    webhook_auth_mode: Literal["token", "hmac", "both"] | None = None


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=5, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not normalized:
            raise ValueError("email is required")
        return normalized

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone_e164(value)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone_e164(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class PlaybookCreate(BaseModel):
    objection_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=150)
    suggested_response: str = Field(min_length=1)
    channel: str = Field(default="whatsapp", max_length=32)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlaybookUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=150)
    suggested_response: str | None = None
    channel: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class AssignmentRequest(BaseModel):
    contact_id: str
    deal_id: str | None = None
    channel: str = Field(default="whatsapp", max_length=32)
    preferred_user_id: str | None = None


class WhatsAppTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=64)
    language: str = Field(default="es_AR", max_length=16)
    body_template: str = Field(min_length=1)
    variables_json: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="draft", max_length=24)


class WhatsAppTemplateUpdate(BaseModel):
    category: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=16)
    body_template: str | None = None
    variables_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=24)


class WhatsAppTemplateApproval(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = Field(default=None, max_length=500)


class InventorySignalCreate(BaseModel):
    product_sku: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    variant: str | None = Field(default=None, max_length=120)
    in_stock: bool = True
    quantity_available: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
