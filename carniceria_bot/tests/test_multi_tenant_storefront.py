import csv
from pathlib import Path

from flask import Flask

import bot_sales.connectors.storefront_api as storefront_api
from bot_sales.core.database import Database
from bot_sales.core.tenancy import TenantManager


def _write_csv(path: Path, fieldnames, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_new_catalog_loader_supports_attributes_json(tmp_path):
    db_file = tmp_path / "store.db"
    log_file = tmp_path / "bot.log"
    catalog_file = tmp_path / "catalog.csv"

    _write_csv(
        catalog_file,
        ["sku", "category", "name", "price", "currency", "stock", "size", "material", "color"],
        [
            {
                "sku": "CLO-001",
                "category": "Remeras",
                "name": "Remera Basica",
                "price": 18000,
                "currency": "ARS",
                "stock": 10,
                "size": "M",
                "material": "Algodon",
                "color": "Black",
            }
        ],
    )

    db = Database(str(db_file), str(catalog_file), str(log_file))

    stock = db.load_stock()
    assert len(stock) == 1
    assert stock[0]["model"] == "Remera Basica"
    assert stock[0]["currency"] == "ARS"
    assert stock[0]["attributes"]["size"] == "M"

    # Match against extra attribute from flexible JSON payload.
    matches = db.find_matches("algodon", None, None)
    assert len(matches) == 1
    assert matches[0]["sku"] == "CLO-001"

    db.close()


def test_storefront_products_are_tenant_scoped(tmp_path, monkeypatch):
    tenants_file = tmp_path / "tenants.yaml"

    farmacia_dir = tmp_path / "farmacia"
    ropa_dir = tmp_path / "ropa"
    farmacia_dir.mkdir(parents=True)
    ropa_dir.mkdir(parents=True)

    farmacia_catalog = farmacia_dir / "catalog.csv"
    ropa_catalog = ropa_dir / "catalog.csv"

    _write_csv(
        farmacia_catalog,
        ["sku", "category", "name", "price", "currency", "stock", "active_ingredient"],
        [
            {
                "sku": "MED-001",
                "category": "Analgésicos",
                "name": "Ibuprofeno 400mg",
                "price": 450,
                "currency": "ARS",
                "stock": 50,
                "active_ingredient": "Ibuprofeno",
            }
        ],
    )

    _write_csv(
        ropa_catalog,
        ["sku", "category", "name", "price", "currency", "stock", "size", "color"],
        [
            {
                "sku": "CLO-001",
                "category": "Remeras",
                "name": "Remera Basica",
                "price": 18000,
                "currency": "ARS",
                "stock": 20,
                "size": "M",
                "color": "Black",
            }
        ],
    )

    farmacia_profile = farmacia_dir / "profile.yaml"
    ropa_profile = ropa_dir / "profile.yaml"

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

    ropa_profile.write_text(
        """
slug: ropa
business:
  name: Ropa Demo
  industry: clothing
""".strip()
        + "\n",
        encoding="utf-8",
    )

    tenants_file.write_text(
        f"""
tenants:
  - id: farmacia
    slug: farmacia
    name: Farmacia Demo
    profile_path: "{farmacia_profile}"
    db_file: "{tmp_path / 'farmacia.db'}"
    catalog_file: "{farmacia_catalog}"
    api_keys: {{}}
  - id: ropa
    slug: ropa
    name: Ropa Demo
    profile_path: "{ropa_profile}"
    db_file: "{tmp_path / 'ropa.db'}"
    catalog_file: "{ropa_catalog}"
    api_keys: {{}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manager = TenantManager(str(tenants_file))
    monkeypatch.setattr(storefront_api, "tenant_manager", manager)

    app = Flask(__name__)
    app.register_blueprint(storefront_api.storefront_bp)
    client = app.test_client()

    farmacia_resp = client.get("/api/t/farmacia/products")
    ropa_resp = client.get("/api/t/ropa/products")

    assert farmacia_resp.status_code == 200
    assert ropa_resp.status_code == 200

    farmacia_products = farmacia_resp.get_json()
    ropa_products = ropa_resp.get_json()

    assert farmacia_products[0]["category"] == "Analgésicos"
    assert ropa_products[0]["category"] == "Remeras"
