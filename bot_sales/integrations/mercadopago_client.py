import logging
import uuid

class MercadoPagoClient:
    """
    Client for MercadoPago integration (Mock for Demo)
    """
    def __init__(self, access_token=None):
        self.access_token = access_token
        self.logger = logging.getLogger(__name__)
    
    def create_preference(self, title: str, price: float, quantity: int = 1, external_reference: str = "") -> str:
        """
        Create a payment preference and return the checkout URL
        
        Args:
            title: Product title
            price: Unit price
            quantity: Quantity
            external_reference: Order ID
            
        Returns:
            str: Checkout URL (init_point)
        """
        # MOCK IMPLEMENTATION
        # Generates a realistic-looking link but points to a placeholder or loopback
        
        pref_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
        
        # Real MP links look like: https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=...
        mock_link = f"https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id={pref_id}"
        
        self.logger.info(f"Created MP Preference {pref_id} for {title} (${price})")
        
        # For demo visibility:
        print(f"\n💳 [MOCK MP LINK GENERATED]: {mock_link}")
        
        return mock_link
