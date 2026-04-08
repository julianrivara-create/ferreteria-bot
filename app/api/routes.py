
from flask import Blueprint, request, jsonify
from app.core.security import verify_mp_signature, idempotent_webhook
from app.services.payment_service import PaymentService
from app.services.order_service import OrderService
from app.db.session import SessionLocal
from app.db.models import OrderStatus, Order, Product
import structlog
import uuid

logger = structlog.get_logger()
webhooks = Blueprint('webhooks', __name__)

# --- MercadoPago Webhook ---
@webhooks.route('/mp', methods=['POST'])
@verify_mp_signature
@idempotent_webhook
def mercado_pago_webhook():
    data = request.get_json()
    topic = data.get("type")
    entity_id = data.get("data", {}).get("id")
    
    if topic == "payment":
        payment_service = PaymentService()
        session = SessionLocal()
        try:
            payment_info = payment_service.get_payment_status(entity_id)
            if not payment_info:
                return jsonify({"error": "Payment not found"}), 404
            
            external_ref = payment_info.get("external_reference")
            status = payment_info.get("status")
            
            if not external_ref: return jsonify({"status": "ignored"}), 200
            
            order = session.query(Order).filter(Order.id == external_ref).first()
            if not order: return jsonify({"error": "Order not found"}), 404
            
            new_status = None
            if status == 'approved': new_status = OrderStatus.PAID
            elif status == 'rejected': new_status = OrderStatus.PAYMENT_PENDING
            
            if new_status and order.status != new_status:
                OrderService.transition_status(session, order.id, new_status, {"mp_id": entity_id})
                session.commit()
            
            return jsonify({"status": "processed"}), 200
        finally:
            session.close()
    return jsonify({"status": "ignored"}), 200

# --- Public API Routes (Including Stock Batch FIX) ---
api = Blueprint('api', __name__) # If we separate API blueprint later

# Since we use app register, let's put it here or better, add a general routes file
# For now, adding the batch endpoint to `webhooks` file is messy.
# Let's create `app/api/stock_routes.py`? No, let's reuse channels.py for public API or keep it in main routes?
# The user wants "get_stock_batch".
# I'll create a new blueprint 'public_api' in app/api/public_routes.py
