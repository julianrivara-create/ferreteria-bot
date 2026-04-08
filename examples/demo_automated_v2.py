#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🎬 DEMO AUTOMÁTICO - Bot de Ventas Multi-Categoría
Muestra 5 escenarios variados con las nuevas features
"""

import sys
import time
import os

sys.path.insert(0, '.')

from bot_sales.bot import SalesBot

# Colores
class C:
    BOT = '\033[92m'
    USER = '\033[96m'
    TITLE = '\033[95m'
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
        print(f"{C.BOT}Bot: {C.END}", end='')
        type_text(response, delay=0.02)
        pause(2)
    
    # Reset session for next scenario
    bot.reset_session(session_id)
    pause(2)

def main():
    print(f"\n{C.BOLD}{C.TITLE}🚀 DEMO AUTOMÁTICO - Bot Multi-Categoría{C.END}")
    print(f"{C.GREY}Mostrando 5 escenarios variados con todas las features{C.END}\n")
    pause(2)
    
    # Clean DB for fresh demo
    if os.path.exists("ferreteria.db"):
        os.remove("ferreteria.db")
    
    # Initialize bot
    print(f"{C.GREY}Inicializando bot...{C.END}")
    bot = SalesBot()
    print(f"{C.GREY}✅ Bot listo con 62 productos en 5 categorías{C.END}")
    pause(2)
    
    # ========================================
    # ESCENARIO 1: Compra de Sierra Circular
    # ========================================
    simulate_conversation(
        bot, "demo_1",
        [
            "Hola!",
            "Busco una Sierra Circular Air",
            "La M3 de 256GB en gris",
            "Sí, la quiero. Soy Martina, mi WhatsApp es 1144556677",
            "Para CABA",
            "Transferencia",
            "Dale, confirmo"
        ],
        "Compra de Sierra Circular Air M3"
    )
    
    # ========================================
    # ESCENARIO 2: Venta de Herramienta + Cross-sell ACEPTADO
    # ========================================
    simulate_conversation(
        bot, "demo_2",
        [
            "Hola",
            "Amoladora 115mm Pro 256 Black",
            "Perfecto! Me llamo Lucas, cel 1155443322",
            "Retiro en local",
            "MercadoPago",
            "Confirmar",
            "Dale, agrego los Destornillador también"  # ACEPTA CROSS-SELL
        ],
        "Herramienta + Cross-selling (aceptado)"
    )
    
    # ========================================
    # ESCENARIO 3: Búsqueda por categoría - Nivel Laser
    # ========================================
    simulate_conversation(
        bot, "demo_3",
        [
            "Buenas",
            "Qué tenés de Nivel Laser?",
            "La PS5 digital",
            "Sí. Carolina 1198765432",
            "AMBA",
            "Efectivo",
            "Sí, confirmo"
        ],
        "Búsqueda por Categoría - Nivel Laser 5"
    )
    
    # ========================================
    # ESCENARIO 4: Venta de Lijadora
    # ========================================
    simulate_conversation(
        bot, "demo_4",
        [
            "Hola",
            "Busco un Lijadora",
            "Qué modelos tenés disponibles?",
            "El Lijadora Pro 11 de 512GB gris",
            "Dale. Soy Federico, 1177889900",
            "Interior",
            "Tarjeta",
            "Confirmar"
        ],
        "Venta de Lijadora Pro con consulta de modelos"
    )
    
    # ========================================
    # ESCENARIO 5: Herramienta + Cross-sell RECHAZADO
    # ========================================
    simulate_conversation(
        bot, "demo_5",
        [
            "Hola!",
            "Taladro Percutor 13mm Pro Max 512 Natural",
            "Sí, lo quiero. Valeria 1166554433",
            "CABA",
            "Transfer",
            "Dale",
            "No gracias, solo el Herramienta"  # RECHAZA CROSS-SELL
        ],
        "Herramienta + Cross-selling (rechazado)"
    )
    
    # ========================================
    # Resumen final
    # ========================================
    print(f"\n{C.TITLE}{'='*70}{C.END}")
    print(f"{C.TITLE}{C.BOLD}✅ DEMO COMPLETADO{C.END}")
    print(f"{C.TITLE}{'='*70}{C.END}\n")
    
    print(f"{C.GREY}Escenarios demostrados:{C.END}")
    print(f"{C.GREY}1. ✅ Sierra Circular Air M3 - Compra exitosa{C.END}")
    print(f"{C.GREY}2. ✅ Herramienta + Cross-sell aceptado (Destornillador a Bateria 10% OFF){C.END}")
    print(f"{C.GREY}3. ✅ Nivel Laser 5 - Búsqueda por categoría{C.END}")
    print(f"{C.GREY}4. ✅ Lijadora Pro - Consulta de modelos disponibles{C.END}")
    print(f"{C.GREY}5. ✅ Herramienta + Cross-sell rechazado{C.END}")
    
    print(f"\n{C.GREY}Features mostradas:{C.END}")
    print(f"{C.GREY}  📱 Multi-categoría (5 categorías){C.END}")
    print(f"{C.GREY}  💡 Cross-selling post-venta{C.END}")
    print(f"{C.GREY}  🔍 Búsqueda por categoría{C.END}")
    print(f"{C.GREY}  📋 Consulta de modelos{C.END}")
    print(f"{C.GREY}  🎯 Flujo completo de compra{C.END}")
    
    # Show DB stats
    print(f"\n{C.GREY}Estadísticas:{C.END}")
    from bot_sales.core.database import Database
    db = Database('ferreteria.db', 'catalog_extended.csv', 'events.log')
    
    sales = db.cursor.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    print(f"{C.GREY}  💰 Ventas realizadas: {sales}{C.END}")
    
    categories = db.get_all_categories()
    print(f"{C.GREY}  📦 Categorías: {', '.join(categories)}{C.END}")
    
    db.close()
    bot.close()
    
    print(f"\n{C.BOLD}🎉 Listo para filmar!{C.END}\n")

if __name__ == "__main__":
    main()
