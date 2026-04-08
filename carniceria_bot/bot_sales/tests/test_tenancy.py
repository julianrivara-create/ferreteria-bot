import os
import unittest
import tempfile
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from bot_sales.core.tenancy import TenantManager, TenantConfig

# Mock environment
os.environ["TEST_VAR"] = "test_value"

class TestTenantManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "tenants.yaml")
        
        with open(self.config_path, 'w') as f:
            f.write("""
tenants:
  - id: "test_tenant"
    name: "Test Store"
    phone_numbers: ["+123456789"]
    api_keys:
      test_key: "${TEST_VAR}"
    """)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_tenant_loading(self):
        manager = TenantManager(self.config_path)
        
        # Test loading
        tenant = manager.get_tenant("test_tenant")
        self.assertIsNotNone(tenant)
        self.assertEqual(tenant.id, "test_tenant")
        self.assertEqual(tenant.name, "Test Store")
        self.assertEqual(tenant.get_api_key("test_key"), "test_value")
        
        # Test resolution
        resolved = manager.resolve_tenant_by_phone("+123456789")
        self.assertEqual(resolved, tenant)
        
        # Test unmatched
        self.assertIsNone(manager.resolve_tenant_by_phone("+000"))

if __name__ == "__main__":
    unittest.main()
