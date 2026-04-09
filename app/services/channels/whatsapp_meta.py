
import requests
from app.core.config import get_settings
from app.services.bot_core import BotCore
import structlog

logger = structlog.get_logger()
settings = get_settings()


def _phone_number_id_for_tenant(tenant_id: str) -> str:
    """Resolve the outbound phone_number_id for a tenant.

    Checks the tenant's whatsapp_phone_number_id from tenants.yaml first;
    falls back to the global WHATSAPP_PHONE_NUMBER_ID setting.
    """
    try:
        from bot_sales.core.tenancy import tenant_manager
        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant and tenant.whatsapp_phone_number_id:
            return tenant.whatsapp_phone_number_id
    except Exception:
        pass
    return settings.WHATSAPP_PHONE_NUMBER_ID


class WhatsAppMeta:
    BASE_URL = "https://graph.facebook.com/v18.0"

    @staticmethod
    def handle_inbound(message: dict, metadata: dict, tenant_id: str):
        """Process an inbound WhatsApp message using the tenant-scoped bot.

        Handles text, image, document (PDF/Excel), and audio (future) messages.
        Routes through bot_sales.TenantManager so each tenant uses its own
        SalesBot instance, DB, catalog and profile. Falls back to the legacy
        BotCore only if the tenant-scoped bot cannot be initialised.
        """
        from_number = message.get('from')
        msg_type = message.get('type', '')
        text = ""

        # ── Text message ───────────────────────────────────────────────────
        if msg_type == 'text':
            text = message.get('text', {}).get('body', '')

        # ── Media message (image / document / audio) ───────────────────────
        elif msg_type in ('image', 'document', 'audio'):
            try:
                from app.services.media_processor import MediaProcessor
                processor = MediaProcessor(
                    access_token=settings.META_ACCESS_TOKEN,
                    openai_api_key=settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else "",
                )
                extracted = processor.process_whatsapp_media(message)
                if extracted:
                    text = extracted
                    logger.info(
                        "whatsapp_media_extracted",
                        tenant_id=tenant_id,
                        msg_type=msg_type,
                        chars=len(text),
                    )
                else:
                    # Unsupported media type — inform the customer
                    WhatsAppMeta.send_reply(
                        from_number,
                        "Recibí tu mensaje pero no pude leer ese tipo de archivo. "
                        "Podés enviarme el detalle por texto, o mandar una imagen, PDF o Excel.",
                        tenant_id=tenant_id,
                    )
                    return
            except Exception as exc:
                logger.error("whatsapp_media_processing_error", error=str(exc), msg_type=msg_type)
                WhatsAppMeta.send_reply(
                    from_number,
                    "Tuve un problema leyendo el archivo. ¿Podés reenviar o escribir el detalle por texto?",
                    tenant_id=tenant_id,
                )
                return

        if not text:
            return

        reply_text = None

        # ── Primary: tenant-scoped bot_sales SalesBot ──────────────────────
        try:
            from bot_sales.core.tenancy import tenant_manager
            bot = tenant_manager.get_bot(tenant_id)
            # Pass channel metadata so the bot can tag the quote correctly
            reply_text = bot.process_message(
                str(from_number),
                text,
                channel="whatsapp",
                customer_ref=str(from_number),
            )
        except Exception as exc:
            logger.warning(
                "whatsapp_tenant_bot_failed_using_legacy",
                tenant_id=tenant_id,
                error=str(exc),
            )

        # ── Fallback: legacy global BotCore ────────────────────────────────
        if reply_text is None:
            reply_text = BotCore.reply("whatsapp", from_number, text, tenant_id=tenant_id)

        WhatsAppMeta.send_reply(from_number, reply_text, tenant_id=tenant_id)

    @staticmethod
    def send_reply(to, text, tenant_id: str):
        """Send an outbound message using the tenant's phone_number_id."""
        phone_number_id = _phone_number_id_for_tenant(tenant_id)
        url = f"{WhatsAppMeta.BASE_URL}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp", "to": to, "type": "text",
            "text": {"body": text[:4096]}
        }
        headers = {
            "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code >= 400:
                logger.error(
                    "whatsapp_send_failed",
                    tenant_id=tenant_id,
                    phone_number_id=phone_number_id,
                    status=response.status_code,
                    body=response.text[:500],
                )
                return {"status": "error", "status_code": response.status_code, "body": response.text[:500]}
            return {"status": "sent", "status_code": response.status_code}
        except Exception as e:
            logger.error("whatsapp_send_error", tenant_id=tenant_id, error=str(e))
            return {"status": "error", "error": str(e)}
