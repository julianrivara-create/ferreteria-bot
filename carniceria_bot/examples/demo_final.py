#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DEMO FINAL COMPLETADO
Muestra TODAS las features avanzadas implementadas:
1. FAQ System (0 tokens)
2. Bundles (Packs y Promos)
3. Recommendations (IA contextual)
4. Analytics (Tracking invisible)
5. Cross-selling inteligente
"""

import sys
import time
import threading
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, '.')

from bot_sales.bot import SalesBot
from bot_sales.core.database import Database

# ANSI colors
class C:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GREY = '\033[90m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header():
    print(f"\n{C.HEADER}{C.BOLD}" + "="*60)
    print("🤖 IPHONE SALES BOT - DEMO FINAL")
    print("============================================================" + f"{C.END}")
    print(f"{C.GREY}Features activas:{C.END}")
    print(f"{C.GREEN}✅ Analytics & Tracking{C.END}")
    print(f"{C.GREEN}✅ FAQ System (Zero-Token){C.END}")
    print(f"{C.GREEN}✅ Bundles y Promos{C.END}")
    print(f"{C.GREEN}✅ Smart Recommendations{C.END}")
    print(f"{C.GREEN}✅ Contextual Cross-Selling{C.END}")
    print("="*60 + "\n")

def simulate_typing(message: str):
    """Simulate typing effect"""
    sys.stdout.write(f"{C.BOLD}Bot:{C.END} ")
    sys.stdout.flush()
    time.sleep(0.5)
    
    # Print analyzing thinking steps if relevant
    if "CONSULTANDO BASE DE DATOS" in message:
        print(f"{C.GREY}🔍 Consultando base de datos...{C.END}")
        time.sleep(0.5)
        return

    # Print message
    for char in message:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.005) # Fast typing for demo
    print("\n")

def run_scenario(name: str, conversation: List[str]):
    print(f"\n{C.YELLOW}▶️  ESCENARIO: {name}{C.END}")
    print(f"{C.GREY}" + "-"*40 + f"{C.END}\n")
    
    bot = SalesBot()
    session_id = f"demo_{int(time.time())}"
    
    # Process conversation
    for user_msg in conversation:
        print(f"{C.BLUE}Vos:{C.END} {user_msg}")
        time.sleep(0.5)
        
        # Get bot response
        response = bot.process_message(session_id, user_msg)
        
        # Display response
        print(f"{C.GREEN}Bot:{C.END} {response}")
        print()
        
    bot.close()
    print(f"{C.GREY}✅ Escenario finalizado{C.END}\n")
    time.sleep(1)

def main():
    print_header()
    
    # SCENARIO 1: FAQ + Recommendations
    run_scenario("FAQ & Recomendaciones", [
        "Hola! Cómo es el tema del envío?",
        "Ah genial. Y qué tenés para recomendarme si busco algo Apple?",
        "Me interesa el Pack Apple Student. Qué trae?",
        "Buenísimo. Tienen garantía?"
    ])
    
    # SCENARIO 2: Bundle Sale + Cross-sell
    run_scenario("Venta de Bundle + FAQ de Pagos", [
        "Buenas, busco algún combo de Play 5",
        "Me interesa el Pack Gamer Básico. Lo tenés?",
        "Dale, lo quiero. Se puede pagar en cuotas?",
        "Perfecto. Soy Julian, cel 1122334455",
        "Soy de Palermo",
        "Pago con MercadoPago",
        "Confirmado!"
    ])

    # SCENARIO 3: Objections & Smart Recommendations
    run_scenario("Manejo de Objeciones (Precio & Competencia)", [
        "Hola, tenés el iPhone 16 Pro?",
        "Uff está muy caro che. Vi uno más barato en otro lado.",
        "Bueno, pero igual se me va de presupuesto.",
        "Dejame pensarlo y te aviso."
    ])

    # SCENARIO 4: Smart Upselling
    run_scenario("Upselling Inteligente (Sugerencia Proactiva)", [
        "Hola, me interesa el iPhone 15 de 128GB.",
        "Mmm a ver... contame más.",
        "Dale, me copa la oferta. Lo llevo."
    ])

    # SCENARIO 5: Email Notification Flow
    run_scenario("Notificaciones por Email (Mock)", [
        "Quiero comprar el iPhone 13 de 128GB Midnight",
        "Dale, te paso mis datos: Julian, 11223344, julian@demo.com",
        "Soy de CABA",
        "Efectivo"
    ])

    # SCENARIO 6: MercadoPago Integration (Mock Link)
    run_scenario("Pago con MercadoPago", [
        "Quiero el iPhone 14 Pro 128GB",
        "Mis datos: Ana, 11556677, ana@demo.com",
        "Vivo en Palermo",
        "Confirmar con MercadoPago"
    ])
    
    print(f"\n{C.HEADER}{C.BOLD}🎉 DEMO FINAL COMPLETADO{C.END}\n")

if __name__ == "__main__":
    main()
