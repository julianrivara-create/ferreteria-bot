
import requests
from app.core.config import get_settings
from app.services.bot_core import BotCore
import structlog

logger = structlog.get_logger()
settings = get_settings()

class InstagramMeta:
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    @staticmethod
    def handle_inbound(messaging, tenant_id: str = ""):
        sender_id = messaging.get('sender', {}).get('id')
        message = messaging.get('message', {})
        text = message.get('text', '')

        if not tenant_id:
            logger.warning("instagram_handle_inbound_missing_tenant_id", sender_id=sender_id)
            return

        if text:
            reply = BotCore.reply("instagram", sender_id, text, tenant_id=tenant_id)
            InstagramMeta.send_reply(sender_id, reply)

    @staticmethod
    def send_reply(recipient_id, text):
        url = f"{InstagramMeta.BASE_URL}/me/messages"
        payload = {"recipient": {"id": recipient_id}, "message": {"text": text[:1000]}}
        headers = {"Authorization": f"Bearer {settings.META_ACCESS_TOKEN}", "Content-Type": "application/json"}
        try:
            requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception as e:
            logger.error("instagram_send_error", error=str(e))
