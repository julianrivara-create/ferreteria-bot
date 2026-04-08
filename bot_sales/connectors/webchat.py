import logging
from typing import Dict, Any
from flask import Flask, request, jsonify
from flask_cors import CORS

class WebChatAPI:
    """
    API REST para Web Chat Widget
    """
    
    def __init__(self, bot_instance, port: int = 8080):
        self.bot = bot_instance
        self.port = port
        self.logger = logging.getLogger(__name__)
        
        # Crear app Flask
        self.app = Flask(__name__)
        CORS(self.app)  # Permitir CORS para widget
        
        # Registrar endpoints
        self._register_routes()
    
    def _register_routes(self):
        """Registra endpoints de la API"""
        
        @self.app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'ok'}), 200
        
        @self.app.route('/chat/message', methods=['POST'])
        def send_message():
            """
            Envía mensaje y recibe respuesta del bot
            
            Body:
            {
                "session_id": "user-123",
                "message": "Hola"
            }
            
            Response:
            {
                "response": "¡Hola! ¿En qué te puedo ayudar?",
                "session_id": "user-123"
            }
            """
            try:
                data = request.json
                session_id = data.get('session_id')
                message = data.get('message')
                
                if not session_id or not message:
                    return jsonify({'error': 'Missing session_id or message'}), 400
                
                # Procesar con bot
                response = self.bot.process_message(session_id, message)
                
                return jsonify({
                    'response': response,
                    'session_id': session_id
                }), 200
            
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/chat/history/<session_id>', methods=['GET'])
        def get_history(session_id):
            """
            Obtiene historial de conversación
            
            Response:
            {
                "session_id": "user-123",
                "messages": [
                    {"role": "user", "content": "Hola"},
                    {"role": "assistant", "content": "¡Hola!"}
                ]
            }
            """
            try:
                history = self.bot.contexts.get(session_id, [])
                
                # Filtrar solo mensajes de user y assistant
                messages = [
                    msg for msg in history
                    if msg.get('role') in ['user', 'assistant']
                ]
                
                return jsonify({
                    'session_id': session_id,
                    'messages': messages
                }), 200
            
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/widget', methods=['GET'])
        def serve_widget():
            """Sirve el widget HTML"""
            return self._get_widget_html()
    
    def run(self):
        """Inicia el servidor"""
        self.logger.info(f"Starting Web Chat API on port {self.port}")
        self.app.run(host='0.0.0.0', port=self.port, debug=False)
    
    def _get_widget_html(self) -> str:
        """Retorna HTML del widget"""
        return '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Chat Widget</title>
    <style>
        #chat-widget {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 350px;
            height: 500px;
            border: 1px solid #ccc;
            border-radius: 10px;
            background: white;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            font-family: Arial, sans-serif;
        }
        
        #chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 10px 10px 0 0;
            font-weight: bold;
        }
        
        #chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
        }
        
        .message {
            margin: 10px 0;
            padding: 10px;
            border-radius: 8px;
            max-width: 80%;
        }
        
        .message.user {
            background: #667eea;
            color: white;
            margin-left: auto;
        }
        
        .message.bot {
            background: #f0f0f0;
            color: #333;
        }
        
        #chat-input-container {
            display: flex;
            padding: 10px;
            border-top: 1px solid #eee;
        }
        
        #chat-input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 20px;
            outline: none;
        }
        
        #send-btn {
            margin-left: 10px;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
        }
        
        #send-btn:hover {
            background: #5568d3;
        }
    </style>
</head>
<body>
    <div id="chat-widget">
        <div id="chat-header">
            💬 Chat de Ventas
        </div>
        <div id="chat-messages"></div>
        <div id="chat-input-container">
            <input type="text" id="chat-input" placeholder="Escribí tu mensaje...">
            <button id="send-btn">Enviar</button>
        </div>
    </div>
    
    <script>
        const API_URL = 'http://localhost:8080';
        const sessionId = 'web-' + Math.random().toString(36).substr(2, 9);
        
        const messagesContainer = document.getElementById('chat-messages');
        const input = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        
        function addMessage(text, isUser) {
            const msg = document.createElement('div');
            msg.className = 'message ' + (isUser ? 'user' : 'bot');
            msg.textContent = text;
            messagesContainer.appendChild(msg);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        async function sendMessage() {
            const message = input.value.trim();
            if (!message) return;
            
            addMessage(message, true);
            input.value = '';
            
            try {
                const response = await fetch(API_URL + '/chat/message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_id: sessionId,
                        message: message
                    })
                });
                
                const data = await response.json();
                addMessage(data.response, false);
            } catch (error) {
                addMessage('Error: ' + error.message, false);
            }
        }
        
        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        
        // Mensaje inicial
        addMessage('¡Hola! ¿En qué te puedo ayudar?', false);
    </script>
</body>
</html>
        '''
