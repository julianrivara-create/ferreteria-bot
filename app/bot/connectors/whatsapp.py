import logging
import os
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
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning("twilio_signature_validation_error: %s", exc)
            return False
    
    def verify_webhook_meta(self, mode: str, token: str, challenge: str, verify_token: str) -> str:
        """Verifica webhook de Meta (GET request)"""
        if mode == 'subscribe' and token == verify_token:
            return challenge
        return None


from flask import Flask, request, jsonify, Blueprint

def get_whatsapp_blueprint(bot_instance, connector: WhatsAppConnector) -> Blueprint:
    """
    Crea Blueprint para webhooks de WhatsApp
    """
    bp = Blueprint('whatsapp', __name__)
    
    @bp.route('/webhooks/whatsapp', methods=['GET', 'POST'])
    def handle_whatsapp():
        if request.method == 'GET':
            # Verificación de Meta
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')
            
            from app.bot.config import config as bot_config
            verify_token = bot_config.META_VERIFY_TOKEN
            
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
            # Datos básicos
            from_number = parsed.get('from')
            message = parsed.get('message', '')
            msg_type = parsed.get('type')
            
            # --- PHASE 1: AUDIO ---
            if msg_type == 'audio' and parsed.get('media_id'):
                try:
                    import os
                    from app.bot.multimedia import AudioTranscriber
                    
                    audio_path = connector.download_media(parsed['media_id'])
                    if audio_path:
                        transcriber = AudioTranscriber()
                        transcript = transcriber.transcribe(audio_path)
                        try:
                            os.unlink(audio_path)
                        except OSError as exc:
                            logging.warning("audio_tempfile_cleanup_failed path=%s error=%s", audio_path, exc)
                        
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
                    from app.bot.multimedia import ImageAnalyzer
                    
                    # Need public URL for GPT-4o Vision
                    # Meta API returns a private URL that requires headers.
                    # We can't pass that directly to OpenAI. 
                    # Workaround: Download -> (Upload to temp public storage or describe simply).
                    # BETTER: For MVP, assume we can get a signed URL or handle via download.
                    # Actually, for Image Analysis we might need to send base64 or download it locally first.
                    
                    # Currently `download_media` downloads to local file.
                    # GPT-4o API supports base64 data URIs.
                    pass # We will implement download + analysis inside the try block
                    
                    image_path = connector.download_media(parsed['media_id'])
                    if image_path:
                        # Convert to base64 data URI for OpenAI
                        import base64
                        with open(image_path, "rb") as img_file:
                            b64_data = base64.b64encode(img_file.read()).decode('utf-8')
                        
                        try:
                            os.unlink(image_path)
                        except OSError as exc:
                            logging.warning("image_tempfile_cleanup_failed path=%s error=%s", image_path, exc)
                        
                        public_url = f"data:image/jpeg;base64,{b64_data}" # OpenAI supports this
                        
                        analyzer = ImageAnalyzer()
                        analysis = analyzer.analyze_product(public_url)
                        
                        if analysis and not analysis.get('error'):
                            # Construct a "fake" user message based on analysis
                            user_caption = parsed.get('caption', '')
                            message = f"Hola, vi este producto: {analysis.get('model')} color {analysis.get('color')}. {user_caption}"
                            logging.info(f"📸 Image analyzed: {analysis}")
                        else:
                            message = parsed.get('caption') or "Te mando una foto."
                            
                except Exception as e:
                    logging.error(f"Image error: {e}")
                    message = parsed.get('caption') or "Foto recibida."

            if not message:
                return jsonify({'status': 'ignored'}), 200

            try:
                response = bot_instance.process_message(from_number, message)
                
                # Enviar respuesta
                connector.send_message(from_number, response)
                
                return jsonify({'status': 'ok'}), 200
            
            except Exception as e:
                logging.error(f"Error processing WhatsApp message: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        return jsonify({'status': 'ok'}), 200
    
    return bp

def create_webhook_server(bot_instance, connector: WhatsAppConnector, port: int = 5001):
    """Legacy wrapper for backward compatibility"""
    app = Flask(__name__)
    bp = get_whatsapp_blueprint(bot_instance, connector)
    app.register_blueprint(bp)
    return app


def run_whatsapp_server(bot_instance, provider='mock', port=5001, instagram_connector=None):
    """
    Shortcut para iniciar servidor multi-canal (WhatsApp + Instagram + Web)
    """
    from app.bot.config import config
    
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
    
    # Registrar Instagram webhook si está configurado
    if instagram_connector:
        from app.bot.connectors.instagram import run_instagram_webhook
        run_instagram_webhook(app, bot_instance, instagram_connector)
        print("   ✅ Instagram webhook registered")
    
    print("=" * 60)
    print(f"🚀 Multi-Channel Server Running")
    print(f"   WhatsApp: {provider.upper()}")
    print(f"   Instagram: {'Enabled' if instagram_connector else 'Disabled'}")
    print(f"   Port: {port}")
    print(f"   WhatsApp Webhook: http://localhost:{port}/webhooks/whatsapp")
    if instagram_connector:
        print(f"   Instagram Webhook: http://localhost:{port}/webhook/instagram")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
