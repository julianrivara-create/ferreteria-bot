from __future__ import annotations

from app.crm.domain.enums import UserRole


class Permission:
    CONTACTS_READ = "contacts.read"
    CONTACTS_WRITE = "contacts.write"
    CONTACTS_DELETE = "contacts.delete"

    DEALS_READ = "deals.read"
    DEALS_WRITE = "deals.write"
    DEALS_DELETE = "deals.delete"
    DEALS_STAGE_CHANGE = "deals.stage_change"

    TASKS_READ = "tasks.read"
    TASKS_WRITE = "tasks.write"
    TASKS_BULK = "tasks.bulk"

    CONVERSATIONS_READ = "conversations.read"
    MESSAGES_WRITE = "messages.write"

    AUTOMATIONS_READ = "automations.read"
    AUTOMATIONS_WRITE = "automations.write"

    REPORTS_READ = "reports.read"
    EXPORTS_RUN = "exports.run"

    SETTINGS_READ = "settings.read"
    SETTINGS_WRITE = "settings.write"

    USERS_READ = "users.read"
    USERS_WRITE = "users.write"
    USERS_ROLES = "users.roles"


ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.OWNER: {
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.CONTACTS_DELETE,
        Permission.DEALS_READ,
        Permission.DEALS_WRITE,
        Permission.DEALS_DELETE,
        Permission.DEALS_STAGE_CHANGE,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.TASKS_BULK,
        Permission.CONVERSATIONS_READ,
        Permission.MESSAGES_WRITE,
        Permission.AUTOMATIONS_READ,
        Permission.AUTOMATIONS_WRITE,
        Permission.REPORTS_READ,
        Permission.EXPORTS_RUN,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.USERS_ROLES,
    },
    UserRole.ADMIN: {
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.CONTACTS_DELETE,
        Permission.DEALS_READ,
        Permission.DEALS_WRITE,
        Permission.DEALS_STAGE_CHANGE,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.TASKS_BULK,
        Permission.CONVERSATIONS_READ,
        Permission.MESSAGES_WRITE,
        Permission.AUTOMATIONS_READ,
        Permission.AUTOMATIONS_WRITE,
        Permission.REPORTS_READ,
        Permission.EXPORTS_RUN,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.USERS_ROLES,
    },
    UserRole.SALES: {
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.DEALS_READ,
        Permission.DEALS_WRITE,
        Permission.DEALS_STAGE_CHANGE,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.CONVERSATIONS_READ,
        Permission.MESSAGES_WRITE,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
    },
    UserRole.SUPPORT: {
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.DEALS_READ,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.CONVERSATIONS_READ,
        Permission.MESSAGES_WRITE,
        Permission.SETTINGS_READ,
    },
    UserRole.ANALYST: {
        Permission.CONTACTS_READ,
        Permission.DEALS_READ,
        Permission.TASKS_READ,
        Permission.CONVERSATIONS_READ,
        Permission.AUTOMATIONS_READ,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
        Permission.USERS_READ,
    },
    UserRole.READ_ONLY: {
        Permission.CONTACTS_READ,
        Permission.DEALS_READ,
        Permission.TASKS_READ,
        Permission.CONVERSATIONS_READ,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
    },
}


def has_permission(role: UserRole | str, permission: str) -> bool:
    normalized_role = UserRole(role)
    allowed = ROLE_PERMISSIONS.get(normalized_role, set())
    return permission in allowed
