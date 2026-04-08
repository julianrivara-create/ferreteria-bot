from __future__ import annotations

from app.core.logging import pii_masking_processor


def test_pii_masking_processor_masks_email_and_phone_in_log_event():
    event = {
        "event": "crm_webhook_received",
        "message": "Contact john.doe@example.com with phone +14155559999 requested quote",
        "payload": {
            "email": "jane.doe@example.com",
            "phone": "+54 9 11 1234 5678",
            "nested": ["call +14155551111", "mail me@sample.io"],
        },
    }

    sanitized = pii_masking_processor(None, None, event)
    text = str(sanitized)

    assert "john.doe@example.com" not in text
    assert "jane.doe@example.com" not in text
    assert "+14155559999" not in text
    assert "+14155551111" not in text
    assert "@example.com" in text
