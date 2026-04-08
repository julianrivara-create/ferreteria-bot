from enum import Enum


class UserRole(str, Enum):
    OWNER = "Owner"
    ADMIN = "Admin"
    SALES = "Sales"
    SUPPORT = "Support"
    ANALYST = "Analyst"
    READ_ONLY = "ReadOnly"


class DealStatus(str, Enum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"
    DRAFT = "draft"


class AutomationTrigger(str, Enum):
    MESSAGE_RECEIVED = "message_received"
    INTENT_DETECTED = "intent_detected"
    QUOTE_SENT = "quote_sent"
    STAGE_CHANGED = "stage_changed"
    INACTIVITY_TIMER = "inactivity_timer"
    ORDER_DELIVERED = "order_delivered"


class AutomationAction(str, Enum):
    CREATE_TASK = "create_task"
    CHANGE_STAGE = "change_stage"
    ADD_TAG = "add_tag"
    INTERNAL_NOTIFICATION = "internal_notification"
    SCHEDULE_OUTBOUND_DRAFT = "schedule_outbound_draft"
    CREATE_ORDER = "create_order"
    CREATE_REMINDER = "create_reminder"


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    WEB = "web"
    EMAIL = "email"
    INSTAGRAM = "instagram"


class TagScope(str, Enum):
    CONTACT = "contact"
    DEAL = "deal"
    BOTH = "both"


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    STAGE_CHANGE = "stage_change"
    PERMISSION_CHANGE = "permission_change"
    LOGIN = "login"
