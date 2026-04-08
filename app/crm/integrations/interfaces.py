from __future__ import annotations

from typing import Protocol


class WhatsAppProvider(Protocol):
    def send_message(self, *, to: str, body: str, metadata: dict | None = None) -> dict:
        ...


class EmailProvider(Protocol):
    def send_email(self, *, to: str, subject: str, html: str, metadata: dict | None = None) -> dict:
        ...


class PaymentProvider(Protocol):
    def create_payment(self, *, order_id: str, amount: float, currency: str, metadata: dict | None = None) -> dict:
        ...


class ExternalCRMExporter(Protocol):
    def export_contacts(self, *, tenant_id: str, contacts: list[dict]) -> dict:
        ...
