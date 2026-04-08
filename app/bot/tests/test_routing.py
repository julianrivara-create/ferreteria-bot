from flask import Flask
from unittest.mock import MagicMock

from app.bot.connectors.whatsapp import WhatsAppConnector, get_whatsapp_blueprint


def _build_client(bot_instance, connector):
    app = Flask(__name__)
    app.register_blueprint(get_whatsapp_blueprint(bot_instance, connector))
    return app.test_client()


def test_whatsapp_get_verification():
    connector = MagicMock(spec=WhatsAppConnector)
    connector.provider = "meta"
    connector.verify_webhook_meta.return_value = "challenge-ok"

    client = _build_client(bot_instance=MagicMock(), connector=connector)
    response = client.get(
        "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=tok&hub.challenge=abc123"
    )

    assert response.status_code == 200
    assert response.data.decode() == "challenge-ok"
    connector.verify_webhook_meta.assert_called_once()


def test_whatsapp_post_routes_message_to_bot_and_sends_reply():
    connector = MagicMock(spec=WhatsAppConnector)
    connector.provider = "mock"
    connector.receive_webhook.return_value = {
        "from": "+5491111122233",
        "message": "Hola",
        "type": "text",
    }

    bot = MagicMock()
    bot.process_message.return_value = "Respuesta del bot"

    client = _build_client(bot_instance=bot, connector=connector)
    response = client.post("/webhooks/whatsapp", json={"entry": []})

    assert response.status_code == 200
    assert (response.get_json() or {}).get("status") == "ok"
    bot.process_message.assert_called_once_with("+5491111122233", "Hola")
    connector.send_message.assert_called_once_with("+5491111122233", "Respuesta del bot")
