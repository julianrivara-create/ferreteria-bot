import sys
import os
import logging
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot_sales.connectors.whatsapp import WhatsAppConnector, get_whatsapp_blueprint
from bot_sales.bot import SalesBot
from flask import Flask

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("MultimediaTester")

def test_audio_flow():
    logger.info("="*60)
    logger.info("🧪 TESTING AUDIO FLOW (Simulated)")
    logger.info("="*60)
    
    # 1. Mock dependencies
    with patch('bot_sales.connectors.whatsapp.WhatsAppConnector.download_media') as mock_download, \
         patch('bot_sales.multimedia.audio_transcriber.AudioTranscriber.transcribe') as mock_transcribe, \
         patch('bot_sales.bot.SalesBot.process_message') as mock_bot_process:
        
        # Setup Mocks
        mock_download.return_value = "/tmp/fake_audio.ogg"
        mock_transcribe.return_value = "Hola, tenés stock del iPhone 15?"
        mock_bot_process.return_value = "Sí, tengo stock del iPhone 15 en negro. ¿Te interesa?"
        
        # Setup Server with Mock Bot (Avoid init side effects)
        bot = MagicMock()
        bot.process_message.return_value = mock_bot_process.return_value
        
        # Use provider='meta' to trigger correct parsing logic
        connector = WhatsAppConnector(provider='meta', api_token='fake', phone_number='123')
        
        app = Flask(__name__)
        app.register_blueprint(get_whatsapp_blueprint(bot, connector))
        client = app.test_client()
        
        # 2. Simulate Webhook (Audio Message)
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '5491122334455',
                            'id': 'wamid.HBgLM...',
                            'timestamp': '1706038200',
                            'type': 'audio',
                            'audio': {
                                'mime_type': 'audio/ogg; codecs=opus',
                                'sha256': '...',
                                'id': 'MEDIA_ID_123'
                            }
                        }]
                    }
                }]
            }]
        }
        
        # 3. Fire Request
        logger.info("📡 Sending Webhook (Audio)...")
        response = client.post('/webhooks/whatsapp', json=payload)
        
        # 4. Verify
        if response.status_code == 200:
            logger.info("✅ Webhook received 200 OK")
            
            # Check if download was called
            if mock_download.called:
                logger.info("✅ generic Audio Downloaded (Mocked)")
            else:
                logger.error("❌ Audio NOT Downloaded")
                
            # Check if transcribe was called
            if mock_transcribe.called:
                logger.info(f"✅ Transcribed: '{mock_transcribe.return_value}'")
            else:
                logger.error("❌ Transcription Skipped")
                
            # Check if bot processed the text
            if mock_bot_process.called:
                args = mock_bot_process.call_args
                logger.info(f"✅ Bot processed text: '{args[0][1]}'")
                logger.info(f"🤖 Bot replied: '{mock_bot_process.return_value}'")
            else:
                logger.error("❌ Bot logic not triggered")
        else:
            logger.error(f"❌ Webhook failed: {response.status_code}")

def test_image_flow():
    logger.info("\n" + "="*60)
    logger.info("🧪 TESTING IMAGE FLOW (Simulated)")
    logger.info("="*60)
    
    # 1. Mock dependencies
    with patch('bot_sales.connectors.whatsapp.WhatsAppConnector.download_media') as mock_download, \
         patch('bot_sales.multimedia.image_analyzer.ImageAnalyzer.analyze_product') as mock_analyze, \
         patch('bot_sales.bot.SalesBot.process_message') as mock_bot_process, \
         patch('builtins.open', new_callable=MagicMock): # Mock open for image reading
        
        # Setup Mocks
        mock_download.return_value = "/tmp/fake_image.jpg"
        mock_analyze.return_value = {
            'model': 'iPhone 14 Pro',
            'color': 'Deep Purple',
            'category': 'iPhone'
        }
        mock_bot_process.return_value = "Veo que te interesa el iPhone 14 Pro Deep Purple. Tengo 2 en stock."
        
        # Setup Server with Mock Bot
        bot = MagicMock()
        bot.process_message.return_value = mock_bot_process.return_value
        
        connector = WhatsAppConnector(provider='meta', api_token='fake', phone_number='123')
        
        app = Flask(__name__)
        app.register_blueprint(get_whatsapp_blueprint(bot, connector))
        client = app.test_client()
        
        # 2. Simulate Webhook (Image Message)
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '5491122334455',
                            'id': 'wamid.HBgLM...',
                            'timestamp': '1706038200',
                            'type': 'image',
                            'image': {
                                'mime_type': 'image/jpeg',
                                'sha256': '...',
                                'id': 'MEDIA_ID_456',
                                'caption': 'Cuanto sale este?'
                            }
                        }]
                    }
                }]
            }]
        }
        
        # 3. Fire Request
        logger.info("📡 Sending Webhook (Image)...")
        response = client.post('/webhooks/whatsapp', json=payload)
        
        # 4. Verify
        if response.status_code == 200:
            logger.info("✅ Webhook received 200 OK")
            
            if mock_download.called:
                logger.info("✅ Image Downloaded (Mocked)")
            
            if mock_analyze.called:
                logger.info(f"✅ GPT-4o Analyzed: {mock_analyze.return_value}")
            
            if mock_bot_process.called:
                args = mock_bot_process.call_args
                logger.info(f"✅ Bot received message: '{args[0][1]}'")
                logger.info(f"🤖 Bot replied: '{mock_bot_process.return_value}'")
        else:
            logger.error(f"❌ Webhook failed: {response.status_code}")

if __name__ == "__main__":
    print("Running Multimedia Mock Tests...\n")
    test_audio_flow()
    test_image_flow()
    print("\nTests Finished.")
