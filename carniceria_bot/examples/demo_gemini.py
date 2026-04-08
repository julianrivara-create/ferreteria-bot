#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🎬 DEMO AUTOMÁTICO - Bot Gemini
Muestra 5 escenarios variados con Gemini (o modo mock si no hay API key)
"""

import sys
import time
import os

sys.path.insert(0, '.')

from bot_sales.bot_gemini import SalesBotGemini

# Colores
class C:
    BOT = '\033[95m'     # Magenta para Gemini
    USER = '\033[96m'
    TITLE = '\033[93m'   # Yellow
    GREY = '\033[90m'
    END = '\033[0m'
    BOLD = '\033[1m'

def type_text(text, delay=0.03):
    """Simulate typing effect"""
    for char in text:
        print(char, end='', flush=True)
        time.sleep(delay)
    print()

def pause(seconds=1.5):
    """Pause between messages"""
    time.sleep(seconds)

def print_scenario_header(num, title):
    """Print scenario header"""
    print(f"\n{C.TITLE}{'='*70}{C.END}")
    print(f"{C.TITLE}{C.BOLD}ESCENARIO {num}: {title}{C.END}")
    print(f"{C.TITLE}{'='*70}{C.END}\n")
    pause(1)

def simulate_conversation(bot, session_id, messages, scenario_title):
    """Simulate a conversation with typing effects"""
    print_scenario_header(session_id[-1], scenario_title)
    
    for user_msg in messages:
        # User message
        print(f"{C.USER}Vos: {C.END}", end='')
        type_text(user_msg)
        pause()
        
        # Bot response
        response = bot.process_message(session_id, user_msg)
        print(f"{C.BOT}Bot Gemini: {C.END}", end='')
        type_text(response, delay=0.02)
        pause(2)
    
    # Reset session for next scenario
    bot.reset_session(session_id)
    pause(2)

def main():
    print(f"\n{C.BOLD}{C.TITLE}🚀 DEMO AUTOMÁTICO - Bot con Google Gemini{C.END}")
    
    # Check API key
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print(f"{C.GREY}⚠️  Modo MOCK activado (no hay GEMINI_API_KEY){C.END}")
        print(f"{C.GREY}Las respuestas son simuladas para demostración{C.END}\n")
    else:
        print(f"{C.GREY}✅ Usando API Key de Gemini{C.END}\n")
    
    pause(2)
    
    # Clean DB for fresh demo
    if os.path.exists("iphone_store.db"):
        os.remove("iphone_store.db")
    
    # Initialize bot
    print(f"{C.GREY}Inicializando bot Gemini...{C.END}")
    bot = SalesBotGemini()
    print(f"{C.GREY}✅ Bot listo con 62 productos en 5 categorías{C.END}")
    pause(2)
    
    # ========================================
    # ESCENARIO 1: Compra de iPad
    # ========================================
    simulate_conversation(
        bot, "demo_1",
        [
            "Hola, busco un iPad", 
            "El iPad Air 11 de 256GB azul",
            "Perfecto. Soy Ana, WhatsApp 1199887766",
            "CABA",
            "Transferencia",
            "Dale, confirmo la compra"
        ],
        "Compra de iPad Air - Gemini"
    )
    
    # ========================================
    # ESCENARIO 2: PlayStation 5 con consulta
    # ========================================
    simulate_conversation(
        bot, "demo_2",
        [
            "Buenas",
            "Qué PlayStation tenés?",
            "La PS5 disc blanca",
            "Sí. Diego 1177665544",
            "Retiro en local",
            "Efectivo",
            "Confirmar"
        ],
        "PlayStation 5 - Búsqueda por categoría"
    )
    
    # ========================================
    # ESCENARIO 3: AirPods directo
    # ========================================
    simulate_conversation(
        bot, "demo_3",
        [
            "Hola!",
            "AirPods Pro 2da gen",
            "Dale, me los llevo. Laura 1188776655",
            "AMBA",
            "MercadoPago",
            "Sí"
        ],
        "AirPods Pro - Compra rápida"
    )
    
    # ========================================
    # ESCENARIO 4: MacBook con alternativas
    # ========================================
    simulate_conversation(
        bot, "demo_4",
        [
            "Hola",
            "MacBook Pro 16 M3 Max 1TB Space Black",
            "Mostrame alternativas",
            "La MacBook Pro 14 512",
            "Perfecto. Martín 1166554433",
            "Interior",
            "Tarjeta con cuotas",
            "Confirmo"
        ],
        "MacBook - Con alternativas"
    )
    
    # ========================================
    # ESCENARIO 5: iPhone + Derivación a humano
    # ========================================
    simulate_conversation(
        bot, "demo_5",
        [
            "Hola",
            "iPhone 16 Pro Max 1TB",
            "Necesito factura A y negociar el precio",
            "Claudia, empresa Tech SRL, 1155443322"
        ],
        "iPhone - Derivación a humano (factura A)"
    )
    
    # ========================================
    # Resumen final
    # ========================================
    print(f"\n{C.TITLE}{'='*70}{C.END}")
    print(f"{C.TITLE}{C.BOLD}✅ DEMO GEMINI COMPLETADO{C.END}")
    print(f"{C.TITLE}{'='*70}{C.END}\n")
    
    print(f"{C.GREY}Escenarios demostrados con Gemini:{C.END}")
    print(f"{C.GREY}1. ✅ iPad Air - Compra estándar{C.END}")
    print(f"{C.GREY}2. ✅ PlayStation 5 - Búsqueda por categoría{C.END}")
    print(f"{C.GREY}3. ✅ AirPods Pro - Compra rápida{C.END}")
    print(f"{C.GREY}4. ✅ MacBook - Con sugerencia de alternativas{C.END}")
    print(f"{C.GREY}5. ✅ iPhone - Derivación a humano (factura A){C.END}")
    
    print(f"\n{C.GREY}Features mostradas:{C.END}")
    print(f"{C.GREY}  📱 Multi-categoría (5 tipos de productos){C.END}")
    print(f"{C.GREY}  🔍 Búsqueda por categoría{C.END}")
    print(f"{C.GREY}  💡 Sugerencias inteligentes{C.END}")
    print(f"{C.GREY}  👤 Derivación a humano para casos especiales{C.END}")
    print(f"{C.GREY}  🎯 Flujo completo de compra{C.END}")
    
    # Show DB stats
    print(f"\n{C.GREY}Estadísticas:{C.END}")
    from bot_sales.core.database import Database
    db = Database('iphone_store.db', 'catalog_extended.csv', 'events.log')
    
    categories = db.get_all_categories()
    print(f"{C.GREY}  📦 Categorías: {', '.join(categories)}{C.END}")
    
    total_products = len(db.load_stock())
    print(f"{C.GREY}  🛍️  Total productos: {total_products}{C.END}")
    
    db.close()
    bot.close()
    
    if not api_key:
        print(f"\n{C.BOLD}📝 Nota:{C.END} Este demo corrió en modo MOCK")
        print(f"{C.GREY}Para usar Gemini real:{C.END}")
        print(f"{C.GREY}  1. export GEMINI_API_KEY='tu-key'{C.END}")
        print(f"{C.GREY}  2. python demo_gemini.py{C.END}")
    
    print(f"\n{C.BOLD}🎉 Listo para filmar con Gemini!{C.END}\n")

if __name__ == "__main__":
    main()
