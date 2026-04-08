"""
Unit Tests for Business Logic
"""

import pytest
from bot_sales.core.database import Database
from bot_sales.core.business_logic import BusinessLogic


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing"""
    db_file = tmp_path / "test.db"
    catalog_csv = "data/products.csv"
    log_file = tmp_path / "test.log"
    
    db = Database(str(db_file), catalog_csv, str(log_file))
    return db


@pytest.fixture
def business_logic(temp_db):
    """Create BusinessLogic instance with temp database"""
    return BusinessLogic(temp_db)


class TestBuscarStock:
    """Tests for buscar_stock"""
    
    def test_search_by_model(self, business_logic):
        result = business_logic.buscar_stock("Taladro Percutor 13mm")
        
        assert result['status'] in ['found', 'no_stock', 'no_match']
        if result['status'] == 'found':
            assert 'products' in result
            assert len(result['products']) > 0
    
    def test_search_with_storage(self, business_logic):
        result = business_logic.buscar_stock("Taladro Percutor 13mm", storage_gb=128)
        
        if result['status'] == 'found':
            for product in result['products']:
                assert product['storage_gb'] == 128
    
    def test_search_no_match(self, business_logic):
        result = business_logic.buscar_stock("NonExistentModel")
        
        assert result['status'] == 'no_match'
        assert 'message' in result


class TestCrearReserva:
    """Tests for crear_reserva"""
    
    def test_create_valid_hold(self, business_logic, temp_db):
        # Get a valid SKU first
        products = temp_db.get_all_products()
        if not products:
            pytest.skip("No products in test database")

        # Find a product with actual stock; fallback catalog may have stock_qty=0
        in_stock = [p for p in products if (p.get("stock_qty") or 0) > 0]
        if not in_stock:
            pytest.skip("All products in fallback catalog have stock_qty=0")

        sku = in_stock[0]['sku']
        
        result = business_logic.crear_reserva(
            sku=sku,
            nombre="Test User",
            contacto="1122334455",
            email="test@example.com"
        )
        
        assert result['status'] == 'success'
        assert 'hold_id' in result
        assert result['expires_in_minutes'] == 30
    
    def test_create_hold_invalid_sku(self, business_logic):
        result = business_logic.crear_reserva(
            sku="INVALID-SKU",
            nombre="Test User",
            contacto="1122334455"
        )
        
        assert result['status'] == 'error'


class TestListarModelos:
    """Tests for listar_modelos"""
    
    def test_list_models(self, business_logic):
        result = business_logic.listar_modelos()
        
        assert result['status'] == 'success'
        assert 'models' in result
        assert isinstance(result['models'], list)


class TestConsultarFAQ:
    """Tests for consultar_faq"""
    
    def test_faq_match(self, business_logic):
        result = business_logic.consultar_faq("¿Cuánto demora el envío?")
        
        assert result['status'] in ['found', 'not_found']
        if result['status'] == 'found':
            assert 'respuesta' in result
            assert len(result['respuesta']) > 0
    
    def test_faq_no_match(self, business_logic):
        result = business_logic.consultar_faq("Random question that won't match")
        
        assert result['status'] == 'not_found'


class TestDerivarHumano:
    """Tests for derivar_humano"""
    
    def test_handoff_to_human(self, business_logic):
        result = business_logic.derivar_humano(
            razon="Cliente insatisfecho",
            contacto="1122334455",
            nombre="Test User"
        )
        
        assert result['status'] == 'success'
        assert 'lead_id' in result
