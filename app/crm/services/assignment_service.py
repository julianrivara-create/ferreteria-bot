from __future__ import annotations

from sqlalchemy.orm import Session

from app.crm.models import CRMAssignmentCursor, CRMContact, CRMDeal, CRMLeadAssignmentRule, CRMUser


class AssignmentError(Exception):
    pass


class AssignmentService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def assign_lead(
        self,
        *,
        contact_id: str,
        channel: str,
        deal_id: str | None = None,
        preferred_user_id: str | None = None,
    ) -> CRMUser:
        if preferred_user_id:
            user = self._get_user(preferred_user_id)
            if user is None:
                raise AssignmentError("Preferred user not found")
            self._apply_assignment(contact_id=contact_id, deal_id=deal_id, user_id=user.id)
            return user

        rules = (
            self.session.query(CRMLeadAssignmentRule)
            .filter(
                CRMLeadAssignmentRule.tenant_id == self.tenant_id,
                CRMLeadAssignmentRule.channel == channel,
                CRMLeadAssignmentRule.active.is_(True),
            )
            .order_by(CRMLeadAssignmentRule.sort_order.asc(), CRMLeadAssignmentRule.created_at.asc())
            .all()
        )

        if not rules:
            rules = (
                self.session.query(CRMLeadAssignmentRule)
                .filter(
                    CRMLeadAssignmentRule.tenant_id == self.tenant_id,
                    CRMLeadAssignmentRule.active.is_(True),
                )
                .order_by(CRMLeadAssignmentRule.sort_order.asc(), CRMLeadAssignmentRule.created_at.asc())
                .all()
            )

        if not rules:
            raise AssignmentError("No active assignment rules configured")

        cursor = (
            self.session.query(CRMAssignmentCursor)
            .filter(CRMAssignmentCursor.tenant_id == self.tenant_id, CRMAssignmentCursor.channel == channel)
            .with_for_update()
            .first()
        )
        if cursor is None:
            cursor = CRMAssignmentCursor(tenant_id=self.tenant_id, channel=channel, next_index=0)
            self.session.add(cursor)
            self.session.flush()

        idx = cursor.next_index % len(rules)
        selected_rule = rules[idx]
        user = self._get_user(selected_rule.user_id)
        if user is None:
            raise AssignmentError("Selected user not found")

        cursor.next_index = (idx + 1) % len(rules)
        cursor.last_assigned_user_id = user.id

        self._apply_assignment(contact_id=contact_id, deal_id=deal_id, user_id=user.id)
        self.session.flush()
        return user

    def _get_user(self, user_id: str) -> CRMUser | None:
        return (
            self.session.query(CRMUser)
            .filter(CRMUser.tenant_id == self.tenant_id, CRMUser.id == user_id, CRMUser.is_active.is_(True))
            .first()
        )

    def _apply_assignment(self, *, contact_id: str, deal_id: str | None, user_id: str) -> None:
        contact = (
            self.session.query(CRMContact)
            .filter(CRMContact.tenant_id == self.tenant_id, CRMContact.id == contact_id)
            .first()
        )
        if contact is None:
            raise AssignmentError("Contact not found")
        contact.owner_user_id = user_id

        if deal_id:
            deal = (
                self.session.query(CRMDeal)
                .filter(CRMDeal.tenant_id == self.tenant_id, CRMDeal.id == deal_id)
                .first()
            )
            if deal:
                deal.owner_user_id = user_id
