from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.crm.models import CRMContact, CRMInternalNotification, CRMInventorySignal, CRMOutboundDraft, CRMProductInterest


class InventorySignalService:
    def __init__(self, session: Session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def process_stock_signal(self, payload: dict) -> dict:
        row = CRMInventorySignal(
            tenant_id=self.tenant_id,
            product_sku=payload["product_sku"],
            model=payload.get("model"),
            variant=payload.get("variant"),
            in_stock=payload.get("in_stock", True),
            quantity_available=payload.get("quantity_available", 0),
            metadata_json=payload.get("metadata", {}),
        )
        self.session.add(row)
        self.session.flush()

        if not row.in_stock:
            return {"signal_id": row.id, "notified": 0, "drafts": []}

        interests_query = self.session.query(CRMProductInterest).filter(CRMProductInterest.tenant_id == self.tenant_id)
        if row.model:
            interests_query = interests_query.filter(CRMProductInterest.model == row.model)
        if row.variant:
            interests_query = interests_query.filter(CRMProductInterest.variant == row.variant)

        interests = interests_query.all()

        notified_contact_ids = []
        drafts = []
        for interest in interests:
            contact = (
                self.session.query(CRMContact)
                .filter(CRMContact.tenant_id == self.tenant_id, CRMContact.id == interest.contact_id)
                .first()
            )
            if contact is None:
                continue

            body = (
                f"¡Volvió stock de {row.model or interest.model}! "
                f"Te aviso porque habías mostrado interés. ¿Querés que te lo reserve ahora?"
            )
            draft = CRMOutboundDraft(
                tenant_id=self.tenant_id,
                contact_id=contact.id,
                conversation_id=None,
                channel="web",
                body=body,
                scheduled_for=datetime.utcnow() + timedelta(minutes=5),
                status="scheduled",
                metadata_json={"source": "inventory_signal", "signal_id": row.id, "product_sku": row.product_sku},
            )
            self.session.add(draft)
            drafts.append(draft)
            notified_contact_ids.append(contact.id)

        if notified_contact_ids:
            self.session.add(
                CRMInternalNotification(
                    tenant_id=self.tenant_id,
                    user_id=None,
                    title="Inventory signal processed",
                    body=f"Prepared {len(notified_contact_ids)} outbound drafts for restocked item {row.product_sku}.",
                    severity="info",
                    metadata_json={"signal_id": row.id, "product_sku": row.product_sku},
                )
            )

        row.notified_contacts = notified_contact_ids
        self.session.flush()

        return {
            "signal_id": row.id,
            "notified": len(notified_contact_ids),
            "drafts": [d.id for d in drafts],
        }
