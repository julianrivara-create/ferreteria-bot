try:
    import mercadopago
except Exception:  # pragma: no cover - optional dependency in local mode
    mercadopago = None
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

class PaymentService:
    def __init__(self):
        self.mock_mode = mercadopago is None or not settings.MERCADOPAGO_ACCESS_TOKEN
        self.sdk = None if self.mock_mode else mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

    def get_payment_status(self, payment_id):
        if self.mock_mode:
            logger.info("payment_service_mock_mode", payment_id=str(payment_id))
            return None
        try:
            response = self.sdk.payment().get(payment_id)
            if response["status"] == 200:
                payment = response["response"]
                return {
                    "status": payment.get("status"),
                    "external_reference": payment.get("external_reference"),
                    "transaction_amount": payment.get("transaction_amount"),
                    "payment_method_id": payment.get("payment_method_id")
                }
            return None
        except Exception as e:
            logger.error("payment_service_error", error=str(e))
            return None
