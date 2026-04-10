import logging
from flask import Flask, request, jsonify
from typing import Dict, Any, Optional

class WhatsAppConnector:
    """
    Conector para WhatsApp Business - VERSIÓN MEJORADA
    Soporta: Twilio, Meta Cloud API, y Mock
    """
    
    def __init__(self, provider: str = None, api_token: str = None, 
                 phone_number: str = None, account_sid: str = None):
        """
        Args:
            provider: 'twilio', 'meta', o 'mock'
            api_token: Auth token o access token
            phone_number: Número de WhatsApp
            account_sid: Solo para Twilio
        """
        self.provider = provider or 'mock'
        self.api_token = api_token
        self.phone_number = phone_number
        self.account_sid = account_sid
        self.logger = logging.getLogger(__name__)
        
        if self.provider == 'mock':
            self.logger.info("WhatsApp connector in MOCK mode")
        elif self.provider == 'twilio':
            self._init_twilio()
        elif self.provider == 'meta':
            self._init_meta()
    
    def _init_twilio(self):
        """Inicializa cliente Twilio"""
        try:
            from twilio.rest import Client
            
            if not self.account_sid or not self.api_token:
                self.logger.warning("Twilio credentials missing, falling back to mock")
                self.provider = 'mock'
                return
            
            self.client = Client(self.account_sid, self.api_token)
            self.logger.info(f"Twilio WhatsApp initialized: {self.phone_number}")
        
        except ImportError:
            self.logger.warning("Twilio package not installed. Run: pip install twilio")
            self.provider = 'mock'
        
        except Exception as e:
            self.logger.error(f"Twilio init failed: {e}")
            self.provider = 'mock'
    
    def _init_meta(self):
        """Inicializa Meta Cloud API"""
        import requests
        
        if not self.api_token or not self.phone_number:
            self.logger.warning("Meta credentials missing, falling back to mock")
            self.provider = 'mock'
            return
        
        self.meta_url = f"https://graph.facebook.com/v18.0/{self.phone_number}/messages"
        self.logger.info(f"Meta Cloud API initialized: {self.phone_number}")
    
    def send_message(self, to: str, message: str, media_url: str = None) -> Dict:
        """
        Envía mensaje de WhatsApp
        
        Args:
            to: Número destino (formato: +5491122334455)
            message: Texto del mensaje
            media_url: URL de imagen (opcional)
        
        Returns:
            {'status': 'success'|'error', 'message_id': str}
        """
        # Limpiar número
        to_clean = to.strip().replace(' ', '')
        if not to_clean.startswith('+'):
            to_clean = '+' + to_clean
        
        if self.provider == 'mock':
            return self._mock_send(to_clean, message, media_url)
        
        elif self.provider == 'twilio':
            return self._send_via_twilio(to_clean, message, media_url)
        
        elif self.provider == 'meta':
            return self._send_via_meta(to_clean, message, media_url)
    
    def _mock_send(self, to: str, message: str, media_url: str = None) -> Dict:
        """Mock send"""
        self.logger.info("=" * 60)
        self.logger.info("[MOCK WhatsApp Message]")
        self.logger.info(f"To: {to}")
        self.logger.info(f"Message: {message[:200]}...")
        if media_url:
            self.logger.info(f"Media: {media_url}")
        self.logger.info("=" * 60)
        
        return {
            'status': 'mock_success',
            'message_id': f'mock_{hash(message)}',
            'to': to
        }
    
    def _send_via_twilio(self, to: str, message: str, media_url: str = None) -> Dict:
        """Envía vía Twilio"""
        try:
            # Preparar mensaje
            msg_params = {
                'from_': f'whatsapp:{self.phone_number}',
                'to': f'whatsapp:{to}',
                'body': message
            }
            
            if media_url:
                msg_params['media_url'] = [media_url]
            
            # Enviar
            message_obj = self.client.messages.create(**msg_params)
            
            self.logger.info(f"Twilio message sent: {message_obj.sid}")
            
            return {
                'status': 'success',
                'message_id': message_obj.sid,
                'to': to,
                'provider': 'twilio'
            }
        
        except Exception as e:
            self.logger.error(f"Twilio send failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _send_via_meta(self, to: str, message: str, media_url: str = None) -> Dict:
        """Envía vía Meta Cloud API"""
        import requests
        
        try:
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json'
            }
            
            # Preparar payload
            if media_url:
                # Mensaje con imagen
                payload = {
                    'messaging_product': 'whatsapp',
                    'to': to.replace('+', ''),
                    'type': 'image',
                    'image': {
                        'link': media_url,
                        'caption': message
                    }
                }
            else:
                # Solo texto
                payload = {
                    'messaging_product': 'whatsapp',
                    'to': to.replace('+', ''),
                    'type': 'text',
                    'text': {
                        'body': message
                    }
                }
            
            # Enviar
            response = requests.post(
                self.meta_url,
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                message_id = data.get('messages', [{}])[0].get('id')
                
                self.logger.info(f"Meta message sent: {message_id}")
                
                return {
                    'status': 'success',
                    'message_id': message_id,
                    'to': to,
                    'provider': 'meta'
                }
            else:
                raise Exception(f"Meta API error: {response.status_code} - {response.text}")
        
        except Exception as e:
            self.logger.error(f"Meta send failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def receive_webhook(self, data: Dict) -> Dict[str, Any]:
        """
        Procesa webhook de mensaje entrante
        
        Args:
            data: JSON del webhook (Twilio o Meta)
        
        Returns:
            {
                'from': str,
                'message': str,
                'timestamp': str,
                'message_id': str
            }
        """
        if self.provider == 'twilio':
            return self._parse_twilio_webhook(data)
        elif self.provider == 'meta':
            return self._parse_meta_webhook(data)
        else:
            return self._parse_generic_webhook(data)
    
    def _parse_twilio_webhook(self, data: Dict) -> Dict:
        """Parse Twilio webhook"""
        return {
            'from': data.get('From', '').replace('whatsapp:', ''),
            'to': data.get('To', '').replace('whatsapp:', ''),
            'message': data.get('Body', ''),
            'timestamp': data.get('DateCreated'),
            'message_id': data.get('MessageSid'),
            'media_url': data.get('MediaUrl0')  # Primera imagen si hay
        }
    
    def _parse_meta_webhook(self, data: Dict) -> Dict:
        """Parse Meta Cloud API webhook"""
        try:
            entry = data.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})
            messages = value.get('messages', [])
            
            if messages:
                msg = messages[0]
                
                # Extraer texto según tipo
                message_text = ''
                if msg.get('type') == 'text':
                    message_text = msg.get('text', {}).get('body', '')
                elif msg.get('type') == 'image':
                    message_text = msg.get('image', {}).get('caption', '')
                
                return {
                    'from': msg.get('from'),
                    'message': message_text,
                    'timestamp': msg.get('timestamp'),
                    'message_id': msg.get('id'),
                    'type': msg.get('type')
                }
        except Exception as e:
            self.logger.error(f"Failed to parse Meta webhook: {e}")
        
        return {}
    
    def download_media(self, media_id: str) -> Optional[str]:
        """Download media from Meta API"""
        import requests
        import mimetypes
        from tempfile import NamedTemporaryFile
        
        if self.provider != 'meta':
            return None
            
        try:
            # 1. Get Media URL
            url = f"https://graph.facebook.com/v18.0/{media_id}"
            headers = {'Authorization': f'Bearer {self.api_token}'}
            
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                self.logger.error(f"Failed to get media URL: {resp.text}")
                return None
                
            media_url = resp.json().get('url')
            mime_type = resp.json().get('mime_type')
            
            # 2. Download Media
            media_resp = requests.get(media_url, headers=headers)
            if media_resp.status_code != 200:
                self.logger.error("Failed to download media content")
                return None
                
            # 3. Save to temp file
            ext = mimetypes.guess_extension(mime_type) or '.ogg'
            temp = NamedTemporaryFile(delete=False, suffix=ext)
            temp.write(media_resp.content)
            temp.close()
            
            return temp.name
            
        except Exception as e:
            self.logger.error(f"Media download error: {e}")
            return None
    
    def _parse_generic_webhook(self, data: Dict) -> Dict:
        """Parse genérico para testing"""
        return {
            'from': data.get('from') or data.get('From'),
            'message': data.get('message') or data.get('Body'),
            'timestamp': data.get('timestamp'),
            'message_id': data.get('message_id')
        }
    
    def verify_webhook_twilio(self, signature: str, url: str, params: dict) -> bool:
        """Verifica firma de Twilio webhook"""
        try:
            from twilio.request_validator import RequestValidator
            
            validator = RequestValidator(self.api_token)
            return validator.validate(url, params, signature)
        except:
            return False
    
    def verify_webhook_meta(self, mode: str, token: str, challenge: str, verify_token: str) -> str:
        """Verifica webhook de Meta (GET request)"""
        if mode == 'subscribe' and token == verify_token:
            return challenge
        return None


from flask import Flask, request, jsonify, Blueprint

import concurrent.futures
from cachetools import TTLCache

webhook_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
_processed_webhook_msg_ids = TTLCache(maxsize=10000, ttl=300)

def get_whatsapp_blueprint(bot_instance: Optional[Any], connector: WhatsAppConnector) -> Blueprint:
    """
    Crea Blueprint para webhooks de WhatsApp
    Args:
        bot_instance: Instancia legacy (single tenant) o None para Multi-tenant
        connector: Instancia del conector
    """
    from ..core.tenancy import tenant_manager
    from app.core.config import get_settings
    bp = Blueprint('whatsapp', __name__)
    
    @bp.route('/webhooks/whatsapp', methods=['GET', 'POST'])
    def handle_whatsapp():
        if request.method == 'GET':
            # Verificación de Meta
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')
            
            verify_token = get_settings().META_VERIFY_TOKEN
            
            result = connector.verify_webhook_meta(mode, token, challenge, verify_token)
            if result:
                return result, 200
            return 'Forbidden', 403
        
        # POST - Mensaje entrante
        data = request.get_json() or request.form.to_dict()
        
        # Verificar firma Twilio (opcional)
        if connector.provider == 'twilio':
            signature = request.headers.get('X-Twilio-Signature', '')
            if not connector.verify_webhook_twilio(signature, request.url, request.form):
                return 'Invalid signature', 401
        
        # Parsear mensaje
        parsed = connector.receive_webhook(data)
        
        if parsed and (parsed.get('message') or parsed.get('type') in ['audio', 'image']):
            from_number = parsed.get('from')
            message = parsed.get('message', '')
            msg_type = parsed.get('type')
            msg_id = parsed.get('message_id')
            
            if msg_id:
                if msg_id in _processed_webhook_msg_ids:
                    logging.warning(f"Ignorando webhook duplicado (idempotencia): {msg_id}")
                    return jsonify({'status': 'ok', 'note': 'duplicate'}), 200
                _processed_webhook_msg_ids[msg_id] = True
            
            if message:
                message = message[:4000]
            
            # --- PHASE 1: AUDIO ---
            if msg_type == 'audio' and parsed.get('media_id'):
                try:
                    import os
                    from bot_sales.multimedia import AudioTranscriber
                    
                    audio_path = connector.download_media(parsed['media_id'])
                    if audio_path:
                        transcriber = AudioTranscriber()
                        transcript = transcriber.transcribe(audio_path)
                        try: os.unlink(audio_path) 
                        except: pass
                        
                        if transcript:
                            message = transcript
                            logging.info(f"🎤 Audio transcribed: '{message}'")
                        else:
                            connector.send_message(from_number, "No pude escuchar el audio. ¿Me lo escribís?")
                            return jsonify({'status': 'ok'}), 200
                except Exception as e:
                    logging.error(f"Audio error: {e}")

            # --- PHASE 2: IMAGE ---
            elif msg_type == 'image' and parsed.get('media_id'):
                try:
                    from bot_sales.multimedia import ImageAnalyzer
                    import base64
                    import os as _os

                    image_path = connector.download_media(parsed['media_id'])
                    if image_path:
                        # Convert to base64 data URI — GPT-4o Vision supports this directly
                        with open(image_path, "rb") as img_file:
                            b64_data = base64.b64encode(img_file.read()).decode('utf-8')
                        try:
                            _os.unlink(image_path)
                        except Exception:
                            pass

                        public_url = f"data:image/jpeg;base64,{b64_data}"
                        analyzer = ImageAnalyzer()
                        analysis = analyzer.analyze_product(public_url)

                        if analysis and not analysis.get('error'):
                            user_caption = parsed.get('caption', '')
                            message = f"Vi este producto: {analysis.get('model', '')} color {analysis.get('color', '')}. {user_caption}".strip(". ")
                            logging.info(f"📸 Image analyzed: {analysis}")
                        else:
                            message = parsed.get('caption') or "Te mando una foto."
                    else:
                        message = parsed.get('caption') or "Foto recibida."
                except Exception as e:
                    logging.error(f"Image error: {e}", exc_info=True)
                    message = parsed.get('caption') or "Foto recibida."

            if not message:
                return jsonify({'status': 'ignored'}), 200

            try:
                # --- MULTI-TENANT RESOLUTION ---
                target_bot = bot_instance
                
                # If no forced bot instance, resolve per tenant
                if not target_bot:
                    to_number = parsed.get('to')
                    if to_number:
                        tenant = tenant_manager.resolve_tenant_by_phone(to_number)
                        if not tenant:
                            # Allow runtime onboarding without process restart.
                            tenant_manager.reload()
                            tenant = tenant_manager.resolve_tenant_by_phone(to_number)
                        if tenant:
                            target_bot = tenant_manager.get_bot(tenant.id)
                            logging.info(f"Routed to tenant: {tenant.name} (ID: {tenant.id})")
                        else:
                            # Fallback: Default Tenant
                            default_tenant = tenant_manager.get_default_tenant()
                            if default_tenant:
                                target_bot = tenant_manager.get_bot(default_tenant.id)
                                logging.warning(f"Tenant not found for {to_number}, falling back to default: {default_tenant.name}")
                    else:
                         # No 'to' number (maybe generic webhook?), use default
                         default_tenant = tenant_manager.get_default_tenant()
                         if default_tenant:
                             target_bot = tenant_manager.get_bot(default_tenant.id)

                if not target_bot:
                    logging.error("No bot instance found (Multi-tenant resolution failed)")
                    return jsonify({'status': 'error', 'message': 'No tenant'}), 500

                def process_in_background(t_bot, f_num, msg):
                    try:
                        response = t_bot.process_message(
                            f_num,
                            msg,
                            channel="whatsapp",
                            customer_ref=str(f_num),
                        )
                        connector.send_message(f_num, response)
                    except Exception as e:
                        logging.error(f"Error processing WhatsApp message in background: {e}", exc_info=True)

                webhook_executor.submit(process_in_background, target_bot, from_number, message)
                
                return jsonify({'status': 'ok', 'note': 'async processing started'}), 200
            
            except Exception as e:
                logging.error(f"Error delegating WhatsApp message: {e}", exc_info=True)
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        return jsonify({'status': 'ok'}), 200
    
    return bp

def create_webhook_server(bot_instance, connector: WhatsAppConnector, port: int = 5001):
    """Legacy wrapper for backward compatibility"""
    app = Flask(__name__)
    bp = get_whatsapp_blueprint(bot_instance, connector)
    app.register_blueprint(bp)
    return app


def run_whatsapp_server(bot_instance, provider='mock', port=5001):
    """
    Shortcut para iniciar servidor WhatsApp
    
    Usage:
        from bot_sales.connectors.whatsapp import run_whatsapp_server
        from bot_sales.bot import SalesBot
        
        bot = SalesBot()
        run_whatsapp_server(bot, provider='twilio', port=5001)
    """
    from bot_sales.config import config
    
    # Auto-configurar según .env
    if provider == 'auto':
        provider = config.WHATSAPP_PROVIDER
    
    if provider == 'twilio':
        connector = WhatsAppConnector(
            provider='twilio',
            account_sid=config.TWILIO_ACCOUNT_SID,
            api_token=config.TWILIO_AUTH_TOKEN,
            phone_number=config.TWILIO_WHATSAPP_NUMBER
        )
    elif provider == 'meta':
        connector = WhatsAppConnector(
            provider='meta',
            api_token=config.META_ACCESS_TOKEN,
            phone_number=config.META_PHONE_NUMBER_ID
        )
    else:
        connector = WhatsAppConnector(provider='mock')
    
    app = create_webhook_server(bot_instance, connector, port)
    
    print("=" * 60)
    print(f"🚀 WhatsApp Server Running ({provider.upper()})")
    print(f"   Port: {port}")
    print(f"   Webhook: http://localhost:{port}/webhooks/whatsapp")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
