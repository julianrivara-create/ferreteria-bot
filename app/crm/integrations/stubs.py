from __future__ import annotations

from app.crm.integrations.interfaces import EmailProvider, ExternalCRMExporter, PaymentProvider, WhatsAppProvider


class StubWhatsAppProvider(WhatsAppProvider):
    def send_message(self, *, to: str, body: str, metadata: dict | None = None) -> dict:
        return {"status": "stubbed", "provider": "whatsapp", "to": to, "body": body, "metadata": metadata or {}}


class StubEmailProvider(EmailProvider):
    def send_email(self, *, to: str, subject: str, html: str, metadata: dict | None = None) -> dict:
        return {
            "status": "stubbed",
            "provider": "email",
            "to": to,
            "subject": subject,
            "metadata": metadata or {},
        }


class StubPaymentProvider(PaymentProvider):
    def create_payment(self, *, order_id: str, amount: float, currency: str, metadata: dict | None = None) -> dict:
        return {
            "status": "stubbed",
            "provider": "payments",
            "order_id": order_id,
            "amount": amount,
            "currency": currency,
            "metadata": metadata or {},
        }


class StubExternalCRMExporter(ExternalCRMExporter):
    def export_contacts(self, *, tenant_id: str, contacts: list[dict]) -> dict:
        return {"status": "stubbed", "provider": "external_crm", "tenant_id": tenant_id, "count": len(contacts)}
