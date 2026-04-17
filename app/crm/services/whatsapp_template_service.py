from __future__ import annotations

from sqlalchemy.orm import Session

from app.crm.models import CRMWhatsAppTemplate, CRMWhatsAppTemplateApproval
from app.crm.time import utc_now_naive


class WhatsAppTemplateService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def list(self, status: str | None = None) -> list[CRMWhatsAppTemplate]:
        query = self.session.query(CRMWhatsAppTemplate).filter(CRMWhatsAppTemplate.tenant_id == self.tenant_id)
        if status:
            query = query.filter(CRMWhatsAppTemplate.status == status)
        return query.order_by(CRMWhatsAppTemplate.created_at.desc()).all()

    def get(self, template_id: str) -> CRMWhatsAppTemplate | None:
        return (
            self.session.query(CRMWhatsAppTemplate)
            .filter(CRMWhatsAppTemplate.tenant_id == self.tenant_id, CRMWhatsAppTemplate.id == template_id)
            .first()
        )

    def create(self, payload: dict, requested_by_user_id: str) -> CRMWhatsAppTemplate:
        row = CRMWhatsAppTemplate(tenant_id=self.tenant_id, **payload)
        self.session.add(row)
        self.session.flush()

        approval = CRMWhatsAppTemplateApproval(
            tenant_id=self.tenant_id,
            template_id=row.id,
            requested_by_user_id=requested_by_user_id,
            decision="pending",
        )
        self.session.add(approval)
        self.session.flush()
        return row

    def update(self, row: CRMWhatsAppTemplate, payload: dict, requested_by_user_id: str) -> CRMWhatsAppTemplate:
        for key, value in payload.items():
            setattr(row, key, value)
        row.current_version += 1
        row.status = payload.get("status") or "pending_approval"

        approval = CRMWhatsAppTemplateApproval(
            tenant_id=self.tenant_id,
            template_id=row.id,
            requested_by_user_id=requested_by_user_id,
            decision="pending",
        )
        self.session.add(approval)
        self.session.flush()
        return row

    def approve(self, template_id: str, decision: str, reviewer_user_id: str, comment: str | None) -> CRMWhatsAppTemplate:
        row = self.get(template_id)
        if row is None:
            raise ValueError("Template not found")

        approval = (
            self.session.query(CRMWhatsAppTemplateApproval)
            .filter(
                CRMWhatsAppTemplateApproval.tenant_id == self.tenant_id,
                CRMWhatsAppTemplateApproval.template_id == template_id,
                CRMWhatsAppTemplateApproval.decision == "pending",
            )
            .order_by(CRMWhatsAppTemplateApproval.created_at.desc())
            .first()
        )
        if approval is None:
            approval = CRMWhatsAppTemplateApproval(
                tenant_id=self.tenant_id,
                template_id=template_id,
                requested_by_user_id=reviewer_user_id,
                decision="pending",
            )
            self.session.add(approval)

        approval.decision = decision
        approval.reviewed_by_user_id = reviewer_user_id
        approval.comment = comment
        approval.reviewed_at = utc_now_naive()

        if decision == "approved":
            row.status = "approved"
            row.approved_by_user_id = reviewer_user_id
            row.approved_at = utc_now_naive()
        else:
            row.status = "rejected"

        self.session.flush()
        return row

    def render(self, template: CRMWhatsAppTemplate, variables: dict[str, str] | None = None) -> str:
        content = template.body_template
        variables = variables or {}
        for key, value in variables.items():
            content = content.replace("{{" + key + "}}", str(value))
        return content
