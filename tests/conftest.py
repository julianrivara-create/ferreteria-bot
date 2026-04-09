"""
PyTest Configuration and Core Tests
Run with: pytest tests/ -v --cov=bot_sales --cov-report=html
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def sample_product():
    """Sample product data for testing"""
    return {
        'sku': 'IP15-128-BLK',
        'category': 'Herramienta',
        'model': 'Taladro Percutor 13mm',
        'storage_gb': 128,
        'color': 'Black',
        'stock_qty': 5,
        'price_ars': 1200000
    }


@pytest.fixture(autouse=True)
def isolate_unresolved_log(tmp_path, monkeypatch):
    """Keep test runs from mutating the tracked unresolved-term log."""
    monkeypatch.setenv("FERRETERIA_UNRESOLVED_LOG", str(tmp_path / "unresolved_terms.jsonl"))


@pytest.fixture
def sample_customer():
    """Sample customer data for testing"""
    return {
       'nombre': 'Test User',
        'email': 'test@example.com',
        'contacto': '+541122334455',
        'dni': '12345678'
    }


@pytest.fixture
def mock_chatgpt_client():
    """Mock ChatGPT client for testing"""
    from bot_sales.core.chatgpt import ChatGPTClient
    
    # Create client in mock mode
    client = ChatGPTClient(api_key="mock_key", model="gpt-4")
    client.mock_mode = True
    
    return client


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing"""
    from bot_sales.core.database import Database
    
    db_file = tmp_path / "test_store.db"
    # Create empty catalog file
    catalog_file = tmp_path / "test_catalog.csv"
    with open(catalog_file, 'w') as f:
        f.write("SKU,Category,Model,StorageGB,Color,StockQty,PriceARS\n")
        f.write("IP15-128-BLK,Herramienta,Taladro Percutor 13mm,128,Black,10,1000000\n")
    
    log_file = tmp_path / "test_bot.log"
    
    db = Database(str(db_file), str(catalog_file), str(log_file))
    yield db
    db.close()
