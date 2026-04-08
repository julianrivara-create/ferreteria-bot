"""Operationally safe handoff service for accepted quotes."""

from __future__ import annotations

import os
from typing import Optional

from ..integrations.email_client import EmailClient
from ..persistence.quote_store import QuoteStore


class HandoffService:
    """Create review handoffs and send lightweight alerts."""

    def __init__(self, store: QuoteStore, *, side_effects_enabled: bool = True):
        self.store = store
        self.side_effects_enabled = side_effects_enabled
        self.alert_email = os.getenv("FERRETERIA_HANDOFF_EMAIL_TO") or os.getenv("HANDOFF_EMAIL_TO") or ""
        self.email_client = EmailClient(
            smtp_host=os.getenv("HANDOFF_SMTP_HOST") or os.getenv("SMTP_HOST"),
            smtp_port=int(os.getenv("HANDOFF_SMTP_PORT") or os.getenv("SMTP_PORT") or 587),
            smtp_user=os.getenv("HANDOFF_SMTP_USER") or os.getenv("SMTP_USER"),
            smtp_password=os.getenv("HANDOFF_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD"),
            mock_mode=not bool(os.getenv("HANDOFF_SMTP_HOST") or os.getenv("SMTP_HOST")),
        )

    def create_review_handoff(self, quote_id: str, customer_ref: Optional[str]) -> None:
        if not self.side_effects_enabled:
            return
        queue_id = self.store.create_handoff(
            quote_id=quote_id,
            destination_type="admin_queue",
            destination_ref=customer_ref,
            status="queued",
        )
        self.store.append_event(quote_id, "handoff_created", "system", payload={"handoff_id": queue_id, "destination_type": "admin_queue"})

        if not self.alert_email:
            return

        email_id = self.store.create_handoff(
            quote_id=quote_id,
            destination_type="email",
            destination_ref=self.alert_email,
            status="queued",
        )
        result = self.email_client._send_email(
            self.alert_email,
            f"[Ferreteria] Quote review requested {quote_id}",
            (
                f"Quote {quote_id} was accepted by the customer and is waiting for internal review.\n"
                f"Customer reference: {customer_ref or 'sin referencia'}"
            ),
            None,
        )
        if str(result.get("status", "")).startswith("mock") or result.get("status") == "sent":
            self.store.update_handoff(email_id, status="alert_sent")
            self.store.append_event(quote_id, "handoff_alert_sent", "system", payload={"handoff_id": email_id, "destination_type": "email"})
        else:
            self.store.update_handoff(email_id, status="queued", last_error=str(result))
            self.store.append_event(quote_id, "handoff_alert_failed", "system", payload={"handoff_id": email_id, "destination_type": "email", "error": str(result)})
