"""
Integration Tests
Tests end-to-end flows
"""

import pytest
from bot_sales.core.database import Database
from bot_sales.core.business_logic import BusinessLogic
from bot_sales.core.cart import ShoppingCart, get_cart_manager
from bot_sales.core.state_machine import get_state_machine


class TestE2EFlow:
    """End-to-end flow tests"""
    
    @pytest.fixture
    def setup(self, tmp_path):
        """Setup test environment"""
        db_file = tmp_path / "test.db"
        catalog_csv = "data/products.csv"
        log_file = tmp_path / "test.log"
        
        db = Database(str(db_file), catalog_csv, str(log_file))
        bl = BusinessLogic(db)
        
        return {'db': db, 'bl': bl}
    
    def test_complete_purchase_flow(self, setup):
        """Test complete flow: search → hold → confirm → state transitions"""
        bl = setup['bl']
        
        # 1. Search products
        search_result = bl.buscar_stock("iPhone 15")
        assert search_result['status'] in ['found', 'no_stock']
        
        if search_result['status'] != 'found':
            pytest.skip("No products found")
        
        product = search_result['products'][0]
        sku = product['sku']
        
        # 2. Create hold
        hold_result = bl.crear_reserva(
            sku=sku,
            nombre="Test User",
            contacto="1122334455",
            email="test@example.com"
        )
        
        assert hold_result['status'] == 'success'
        hold_id = hold_result['hold_id']
        
        # 3. Confirm sale
        sale_result = bl.confirmar_venta(
            hold_id=hold_id,
            zona="CABA",
            metodo_pago="Efectivo"
        )
        
        assert sale_result['status'] == 'success'
        
        # 4. Verify state transitions
        sm = get_state_machine()
        is_valid, _ = sm.validate_transition('CREATED', 'CONFIRMED')
        assert is_valid is True
    
    def test_cart_to_checkout(self):
        """Test multi-product cart flow"""
        cart_manager = get_cart_manager()
        cart = cart_manager.get_or_create_cart("test_user_123")
        
        # Add multiple items
        cart.add_item("IP15-128-BLK", "iPhone 15 128GB", 1200000, quantity=1)
        cart.add_item("AIRP-PRO2", "AirPods Pro 2", 450000, quantity=2)
        
        # Verify cart
        assert cart.get_item_count() == 3
        assert cart.get_total() == 1200000 + (450000 * 2)
        
        # Update quantity
        result = cart.update_quantity("AIRP-PRO2", 1)
        assert result['status'] == 'updated'
        assert cart.get_total() == 1200000 + 450000
        
        # Remove item
        result = cart.remove_item("AIRP-PRO2")
        assert result['status'] == 'removed'
        assert cart.get_item_count() == 1
