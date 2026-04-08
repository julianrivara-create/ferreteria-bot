import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from bot_sales.connectors.whatsapp import get_whatsapp_blueprint, WhatsAppConnector
from bot_sales.core.tenancy import TenantManager, TenantConfig

class TestRouting(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.connector = MagicMock(spec=WhatsAppConnector)
        self.connector.provider = 'twilio'
        
        # Mock tenant manager
        self.tenant_patch = patch('bot_sales.core.tenancy.tenant_manager')
        self.mock_tm = self.tenant_patch.start()
        
        # Setup mock tenant
        self.mock_tenant = TenantConfig(
            id="tenant_a",
            name="Tenant A",
            phone_numbers=["whatsapp:+123456"],
            db_file="data/tenant_a.db",
            catalog_file="config/catalog.csv",
            api_keys={"openai": "sk-mock"}
        )
        
        # Mock behavior
        self.mock_tm.resolve_tenant_by_phone.return_value = self.mock_tenant
        self.mock_bot = MagicMock()
        self.mock_bot.process_message.return_value = "Response from Tenant A"
        self.mock_tm.get_bot.return_value = self.mock_bot
        
        # Register blueprint
        # We pass bot_instance=None to enable multi-tenant routing
        bp = get_whatsapp_blueprint(None, self.connector)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tenant_patch.stop()

    def test_routing_success(self):
        # Mock webhook data parse
        self.connector.receive_webhook.return_value = {
            'from': 'whatsapp:+999',
            'to': 'whatsapp:+123456',
            'message': 'Hola',
            'type': 'text'
        }
        
        # Simulate request
        response = self.client.post('/webhooks/whatsapp', json={'key': 'val'})
        
        # Assertions
        self.assertEqual(response.status_code, 200)
        
        # Verify tenant resolution was called with 'whatsapp:+123456'
        self.mock_tm.resolve_tenant_by_phone.assert_called_with('whatsapp:+123456')
        
        # Verify bot was dispatched
        self.mock_tm.get_bot.assert_called_with('tenant_a')
        self.mock_bot.process_message.assert_called_with('whatsapp:+999', 'Hola')
        
        # Verify connector sent response
        self.connector.send_message.assert_called_with('whatsapp:+999', "Response from Tenant A")

if __name__ == "__main__":
    unittest.main()
