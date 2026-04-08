
import pytest
from unittest.mock import MagicMock, patch
from bot_sales.core.business_logic import BusinessLogic
from bot_sales.core.universal_llm import UniversalLLMClient
from bot_sales.bot import SalesBot

class TestRobustness:

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    def test_stock_guardrail_prevents_sale_with_zero_stock(self, mock_db):
        """Test that confirming a sale fails if physical stock is 0"""
        logic = BusinessLogic(mock_db)
        
        # Setup mock: Hold exists, but stock is 0
        mock_db.cursor.execute.return_value.fetchone.return_value = ("SKU-123", "Juan", "1234")
        mock_db.get_product_by_sku.return_value = {"sku": "SKU-123", "stock_qty": 0} # ZERO STOCK
        
        # Action
        result = logic.confirmar_venta("hold_123", "CABA", "Efectivo")
        
        # Assert
        assert result["status"] == "error"
        assert "Sin stock físico" in result["message"] or "Error crítico" in result["message"]
        # Ensure db.confirm_sale was NEVER called
        mock_db.confirm_sale.assert_not_called()

    def test_circuit_breaker_activates_on_llm_failure(self):
        """Test that LLM client falls back to Safe Mode on error"""
        client = UniversalLLMClient(backend='mock') # Start with mock to init
        
        # Inject a fake backend that raises exception
        mock_backend = MagicMock()
        mock_backend.chat_completion.side_effect = Exception("API Timeout")
        client.backend = mock_backend
        client.mock_mode = False # Force it to try the backend
        
        # Action
        messages = [{"role": "user", "content": "Hola"}]
        response = client.send_message(messages)
        
        # Assert
        assert response["role"] == "assistant"
        # Should be a fallback message
        assert "modo de respaldo" in response["content"] or "dificultades técnicas" in response["content"] or "Bienvenido" in response["content"]

    @patch('bot_sales.bot.SalesBot._generate_handoff_summary')
    def test_smart_handoff_includes_summary(self, mock_summary, mock_db):
        """Test that handoff generates and passes a summary"""
        # Setup
        bot = SalesBot()
        bot.logic = MagicMock()
        
        mock_summary.return_value = "Cliente quiere Taladro Percutor 13mm."
        
        # Action
        # Simulate execute_function calling derivar_humano
        bot._execute_function("sess_1", "derivar_humano", {"razon": "test", "contacto": "123"})
        
        # Assert
        bot.logic.derivar_humano.assert_called_with(
            razon="test",
            contacto="123",
            nombre=None,
            resumen="Cliente quiere Taladro Percutor 13mm." # Must include summary
        )
