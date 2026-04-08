from app.api.console_routes import _extract_output_contract
from app.crm.domain.enums import MessageDirection
from app.crm.models import CRMMessage


def test_extract_output_contract_reads_sales_intelligence_v1():
    msg = CRMMessage(
        id="msg-1",
        tenant_id="tenant-1",
        conversation_id="conv-1",
        contact_id="contact-1",
        channel="web",
        direction=MessageDirection.INBOUND,
        body="hola",
        metadata_json={
            "sales_intelligence_v1": {
                "intent": "GENERIC_INFO",
                "stage": "NEW",
                "missing_fields": ["model"],
                "objection_type": None,
                "confidence": 0.5,
                "ab_variant": "A",
                "variant_key": "k1",
            }
        },
    )

    data = _extract_output_contract([msg])
    assert data is not None
    assert data.get("intent") == "GENERIC_INFO"
    assert data.get("stage") == "NEW"
