#!/usr/bin/env python3
"""
WhatsApp Bot Server
Inicia servidor que escucha mensajes de WhatsApp y responde automáticamente
"""
import os
import sys

# Agregar bot_sales al path
sys.path.insert(0, os.path.dirname(__file__))

from bot_sales.connectors.whatsapp import run_whatsapp_server
from bot_sales.core.logger import setup_logging
from bot_sales.runtime import get_runtime_bot, get_runtime_tenant
from app.services.holds_scheduler import start_holds_scheduler

def main():
    # Setup logging
    setup_logging(level='INFO')

    start_holds_scheduler()

    tenant = get_runtime_tenant()
    bot = get_runtime_bot(tenant.id)
    port = int(os.getenv("WHATSAPP_PORT", "5001"))

    print(f"Tenant activo para WhatsApp: {tenant.id} ({tenant.name})")

    # Iniciar servidor WhatsApp del tenant elegido.
    # Provider: 'auto' (lee de .env), 'twilio', 'meta', o 'mock'
    run_whatsapp_server(bot, provider='auto', port=port)

if __name__ == '__main__':
    main()
