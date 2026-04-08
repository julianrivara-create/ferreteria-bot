#!/usr/bin/env python3
"""
WhatsApp Bot Server
Inicia servidor que escucha mensajes de WhatsApp y responde automáticamente
"""
import sys
import os

# Agregar bot_sales al path
sys.path.insert(0, os.path.dirname(__file__))

from bot_sales.connectors.whatsapp import run_whatsapp_server
from bot_sales.core.logger import setup_logging

def main():
    # Setup logging
    setup_logging(level='INFO')
    
    # Iniciar servidor WhatsApp
    # Provider: 'auto' (lee de .env), 'twilio', 'meta', o 'mock'
    # Multi-tenant routing is resolved by incoming destination number.
    run_whatsapp_server(None, provider='auto', port=5001)

if __name__ == '__main__':
    main()
