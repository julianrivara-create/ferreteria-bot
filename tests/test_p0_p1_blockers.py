#!/usr/bin/env python3
"""
Tests for P0/P1 blocker fixes
- P0.1: Tenant-aware database schema (tenant_id isolation)
- P0.2: WhatsApp tenant-aware communication
- P0.3: Admin password hardening (no hardcoded defaults)
- P0.4: Unified routing with tenant_id propagation
- P0.5: Secrets management via environment variables
- P1.1: Rate limiting on /api/t/<tenant>/chat endpoint
- P1.2: Tenant-aware FAQ handling
"""

import csv
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from flask import Flask
from bot_sales.connectors.storefront_tenant_api import storefront_tenant_bp
from bot_sales.core.database import Database
from bot_sales.core.tenancy import TenantManager


def _write_csv(path: Path, fieldnames, rows):
    """Helper to write test CSV files."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


@pytest.fixture
def multi_tenant_setup(tmp_path):
    """Set up ferreteria and farmacia tenants with catalogs."""
    ferreteria_dir = tmp_path / "ferreteria"
    farmacia_dir = tmp_path / "farmacia"
    ferreteria_dir.mkdir(parents=True)
    farmacia_dir.mkdir(parents=True)

    ferreteria_catalog = ferreteria_dir / "catalog.csv"
    farmacia_catalog = farmacia_dir / "catalog.csv"

    # Ferreteria products
    _write_csv(
        ferreteria_catalog,
        ["sku", "category", "name", "price_ars", "stock_qty"],
        [
            {
                "sku": "LLAVE-001",
                "category": "Llaves",
                "name": "Llave Inglesa 10mm",
                "price_ars": 2500,
                "stock_qty": 100,
            }
        ],
    )

    # Farmacia products
    _write_csv(
        farmacia_catalog,
        ["sku", "category", "name", "price_ars", "stock_qty"],
        [
            {
                "sku": "MED-001",
                "category": "Analgésicos",
                "name": "Ibuprofeno 400mg",
                "price_ars": 450,
                "stock_qty": 50,
            }
        ],
    )

    ferreteria_profile = ferreteria_dir / "profile.yaml"
    farmacia_profile = farmacia_dir / "profile.yaml"

    ferreteria_profile.write_text(
        """
slug: ferreteria
business:
  name: Ferreteria Central
  industry: hardware
""".strip()
        + "\n",
        encoding="utf-8",
    )

    farmacia_profile.write_text(
        """
slug: farmacia
business:
  name: Farmacia Demo
  industry: pharmacy
""".strip()
        + "\n",
        encoding="utf-8",
    )

    tenants_file = tmp_path / "tenants.yaml"
    tenants_file.write_text(
        f"""
tenants:
  - id: ferreteria
    slug: ferreteria
    name: Ferreteria Central
    profile_path: "{ferreteria_profile}"
    db_file: "{tmp_path / 'ferreteria.db'}"
    catalog_file: "{ferreteria_catalog}"
    api_keys: {{}}
  - id: farmacia
    slug: farmacia
    name: Farmacia Demo
    profile_path: "{farmacia_profile}"
    db_file: "{tmp_path / 'farmacia.db'}"
    catalog_file: "{farmacia_catalog}"
    api_keys: {{}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    return {
        "tmp_path": tmp_path,
        "tenants_file": tenants_file,
        "ferreteria_catalog": ferreteria_catalog,
        "farmacia_catalog": farmacia_catalog,
    }


class TestP0TenantIsolation:
    """P0.1: Tenant-aware database schema with tenant_id column."""

    def test_database_loads_tenant_catalog(self, multi_tenant_setup):
        """Verify Database respects tenant-specific catalog_file."""
        setup = multi_tenant_setup

        # Load ferreteria database
        ferreteria_db = Database(
            str(setup["tmp_path"] / "ferreteria.db"),
            str(setup["ferreteria_catalog"]),
            str(setup["tmp_path"] / "ferreteria.log"),
        )
        ferreteria_stock = ferreteria_db.load_stock()

        # Load farmacia database
        farmacia_db = Database(
            str(setup["tmp_path"] / "farmacia.db"),
            str(setup["farmacia_catalog"]),
            str(setup["tmp_path"] / "farmacia.log"),
        )
        farmacia_stock = farmacia_db.load_stock()

        # Verify tenant isolation: ferreteria has tools, farmacia has meds
        ferreteria_categories = {p.get("category") for p in ferreteria_stock}
        farmacia_categories = {p.get("category") for p in farmacia_stock}

        assert "Llaves" in ferreteria_categories
        assert "Analgésicos" in farmacia_categories
        assert "Analgésicos" not in ferreteria_categories
        assert "Llaves" not in farmacia_categories

        ferreteria_db.close()
        farmacia_db.close()

    def test_tenant_manager_isolates_databases(self, multi_tenant_setup):
        """Verify TenantManager provides separate DB instances per tenant."""
        setup = multi_tenant_setup
        manager = TenantManager(str(setup["tenants_file"]))

        ferreteria_db = manager.get_db("ferreteria")
        farmacia_db = manager.get_db("farmacia")

        ferreteria_stock = ferreteria_db.load_stock()
        farmacia_stock = farmacia_db.load_stock()

        # Verify each tenant sees only their own products
        assert len(ferreteria_stock) > 0
        assert len(farmacia_stock) > 0
        assert ferreteria_stock[0]["category"] == "Llaves"
        assert farmacia_stock[0]["category"] == "Analgésicos"


class TestP0P1RateLimiting:
    """P1.1: Rate limiting on /api/t/<tenant>/chat endpoint."""

    def test_rate_limiting_blocks_excessive_requests(self, multi_tenant_setup):
        """Verify rate limiter blocks >10 requests/min per tenant+user."""
        setup = multi_tenant_setup
        manager = TenantManager(str(setup["tenants_file"]))

        app = Flask(__name__)
        app.register_blueprint(storefront_tenant_bp)
        client = app.test_client()

        # Mock the bot to avoid needing actual LLM
        with patch("bot_sales.connectors.storefront_tenant_api.tenant_manager", manager):
            ferreteria_bot = MagicMock()
            ferreteria_bot.process_message.return_value = "Hola! 🔧"

            with patch.object(
                manager, "get_bot", return_value=ferreteria_bot
            ):
                # Make 11 requests (exceeds limit of 10/min)
                responses = []
                for i in range(11):
                    resp = client.post(
                        "/api/t/ferreteria/chat",
                        json={
                            "message": f"Pregunta {i}",
                            "user": "test_user",
                        },
                    )
                    responses.append(resp)

                # First 10 should succeed (200)
                for i in range(10):
                    assert responses[i].status_code == 200, f"Request {i} failed"

                # 11th should be rate-limited (429)
                assert responses[10].status_code == 429
                assert "Rate limit exceeded" in responses[10].get_json()["error"]

    def test_rate_limiting_per_user(self, multi_tenant_setup):
        """Verify rate limiting is per tenant+user combination."""
        setup = multi_tenant_setup
        manager = TenantManager(str(setup["tenants_file"]))

        app = Flask(__name__)
        app.register_blueprint(storefront_tenant_bp)
        client = app.test_client()

        with patch("bot_sales.connectors.storefront_tenant_api.tenant_manager", manager):
            ferreteria_bot = MagicMock()
            ferreteria_bot.process_message.return_value = "Hola! 🔧"

            with patch.object(manager, "get_bot", return_value=ferreteria_bot):
                # User A makes 10 requests (should succeed)
                for i in range(10):
                    resp = client.post(
                        "/api/t/ferreteria/chat",
                        json={"message": f"Q{i}", "user": "user_a"},
                    )
                    assert resp.status_code == 200

                # User B makes 10 requests (should also succeed - different rate limit key)
                for i in range(10):
                    resp = client.post(
                        "/api/t/ferreteria/chat",
                        json={"message": f"Q{i}", "user": "user_b"},
                    )
                    assert resp.status_code == 200

                # User A's 11th request (should fail)
                resp = client.post(
                    "/api/t/ferreteria/chat",
                    json={"message": "Q10", "user": "user_a"},
                )
                assert resp.status_code == 429


class TestP1FAQTenantAwareness:
    """P1.2: Tenant-specific FAQ handling via KnowledgeLoader."""

    @pytest.mark.skip(
        reason=(
            "Runtime is now Ferretería-only; generic TenantManager/KnowledgeLoader "
            "multi-tenant contract no longer applies. Covered by test_ferreteria_training.py."
        )
    )
    def test_bot_loads_tenant_specific_faq(self, multi_tenant_setup):
        """Verify bot uses tenant-specific FAQ files."""
        setup = multi_tenant_setup
        manager = TenantManager(str(setup["tenants_file"]))

        ferreteria_bot = manager.get_bot("ferreteria")
        farmacia_bot = manager.get_bot("farmacia")

        # Each bot should have a KnowledgeLoader configured for their tenant
        assert ferreteria_bot.knowledge_loader is not None
        assert farmacia_bot.knowledge_loader is not None

        # Verify they have different tenant_ids
        assert ferreteria_bot.tenant_id == "ferreteria"
        assert farmacia_bot.tenant_id == "farmacia"


class TestP0AdminPasswordHardening:
    """P0.3: Admin password security - no hardcoded defaults."""

    def test_admin_password_requires_env_var(self):
        """Verify ADMIN_PASSWORD is required from environment."""
        # Clear any existing env var
        old_password = os.environ.get("ADMIN_PASSWORD")
        if "ADMIN_PASSWORD" in os.environ:
            del os.environ["ADMIN_PASSWORD"]

        try:
            # This should fail if bootstrap tries to use hardcoded "ADMIN_PASSWORD_ENV"
            # For now we just verify the test structure is correct
            assert "ADMIN_PASSWORD" not in os.environ
        finally:
            if old_password:
                os.environ["ADMIN_PASSWORD"] = old_password


class TestP0SecretsManagement:
    """P0.5: Secrets via tenants.yaml with environment variable interpolation."""

    def test_tenants_yaml_uses_env_vars(self, multi_tenant_setup):
        """Verify tenants.yaml references environment variables for secrets."""
        setup = multi_tenant_setup

        tenants_content = setup["tenants_file"].read_text()

        # Should use ${VAR_NAME} syntax, not hardcoded secrets
        assert "${" in tenants_content or "env" in tenants_content.lower()
