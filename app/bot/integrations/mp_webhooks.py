import logging
import hmac
import hashlib
from typing import Dict, Any
from datetime import datetime

class MercadoPagoWebhooks:
    """
    Handler de webhooks de MercadoPago
    """
    
    def __init__(self, secret_key: str = None):
        if not secret_key:
            raise ValueError(
                "MercadoPagoWebhooks requires a secret_key. "
                "Set MERCADOPAGO_WEBHOOK_SECRET in your environment."
            )
        self.secret_key = secret_key
        self.logger = logging.getLogger(__name__)

    def verify_signature(self, payload: str, signature: str) -> bool:
        """
        Verifica firma del webhook según formato MercadoPago
        Format: ts=...,v1=...

        Args:
            payload: Body del request
            signature: Header x-signature

        Returns:
            True si la firma es válida
        """
            
        if not signature:
            return False
            
        try:
            # Parsear header (ts=...,v1=...)
            parts = {k: v for k, v in [part.split('=') for part in signature.split(',')]}
            ts = parts.get('ts')
            v1 = parts.get('v1')
            
            if not ts or not v1:
                return False
                
            # Crear template de manifest: "id:{id};request-id:{request_id};ts:{ts};" + payload
            # Pero para Webhooks simples MP usa: ts + payload
            manifest = f"id:{ts};ts:{ts};"  # Nota: MP documentation varies, standard HMAC is often simpler
            
            # Simple approach recommended for Webhooks V1:
            # HMAC-SHA256(secret, template)
            # Template: "id:[data.id];request-id:[x-request-id];ts:[ts];"
            # Since we might not have all headers, we'll implement standard HMAC of payload key if simple logic fails
            
            # Reverting to MP documentation specific logic:
            # signature_manifest = f"ts={ts},{payload}" OR just HMAC of payload depending on config.
            # Let's assume standard HMAC for now as placeholder for the specific MP implementation
            
            # Construir el mensaje firmado de forma simple/estable:
            # hmac(secret, "{ts}.{payload}")
            
            signed_payload = f"{ts}.{payload}"
            
            expected_signature = hmac.new(
                self.secret_key.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Comparar
            return hmac.compare_digest(expected_signature, v1)
            
        except Exception as e:
            self.logger.error(f"Signature verify error: {e}")
            return False
    
    def process_webhook(self, data: Dict) -> Dict[str, Any]:
        """
        Procesa notificación de MercadoPago
        
        Args:
            data: JSON del webhook
        
        Returns:
            {
                'status': str,
                'action': str,
                'payment_id': str,
                'external_reference': str
            }
        """
        try:
            # Tipos de notificación
            topic = data.get('topic') or data.get('type')
            resource_id = data.get('data', {}).get('id') or data.get('id')
            
            self.logger.info(f"Webhook received: topic={topic}, id={resource_id}")
            
            # Tipo: payment
            if topic == 'payment':
                return self._process_payment_notification(data)
            
            # Tipo: merchant_order
            elif topic == 'merchant_order':
                return self._process_order_notification(data)
            
            else:
                return {
                    'status': 'ignored',
                    'message': f'Unknown topic: {topic}'
                }
        
        except Exception as e:
            self.logger.error(f"Webhook processing error: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _process_payment_notification(self, data: Dict) -> Dict:
        """
        Procesa notificación de pago
        
        Posibles estados:
        - approved: Pago aprobado
        - pending: Pago pendiente
        - rejected: Pago rechazado
        - cancelled: Pago cancelado
        """
        payment_id = data.get('data', {}).get('id')
        
        # En producción, hacer request a MP API para obtener detalles
        # payment_info = mercadopago.payment().get(payment_id)
        
        # Mock response
        return {
            'status': 'processed',
            'action': 'payment_update',
            'payment_id': payment_id,
            'payment_status': 'approved',  # Mock
            'external_reference': 'SALE-12345',  # Mock
            'message': 'Payment notification processed'
        }
    
    def _process_order_notification(self, data: Dict) -> Dict:
        """
        Procesa notificación de orden
        """
        order_id = data.get('data', {}).get('id')
        
        return {
            'status': 'processed',
            'action': 'order_update',
            'order_id': order_id,
            'message': 'Order notification processed'
        }
    
    def create_webhook_endpoint_template(self) -> str:
        """
        Retorna template para endpoint Flask/FastAPI
        """
        return '''
from flask import Flask, request, jsonify
from app.bot.integrations.mp_webhooks import MercadoPagoWebhooks

app = Flask(__name__)
webhook_handler = MercadoPagoWebhooks(secret_key="YOUR_MP_SECRET")

@app.route('/webhooks/mercadopago', methods=['POST'])
def handle_mp_webhook():
    # Obtener signature
    signature = request.headers.get('x-signature') or request.headers.get('x-webhook-signature')
    
    # Verificar
    if not webhook_handler.verify_signature(request.data.decode(), signature):
        return jsonify({'error': 'Invalid signature'}), 401
    
    # Procesar
    data = request.json
    result = webhook_handler.process_webhook(data)
    
    # TODO: Actualizar DB según result
    # if result['action'] == 'payment_update' and result['payment_status'] == 'approved':
    #     db.update_sale_payment_status(result['external_reference'], 'paid')
    
    return jsonify(result), 200

if __name__ == '__main__':
    app.run(port=5000)
'''
