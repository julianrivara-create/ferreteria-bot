#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🎬 DEMO SIMULADO - Bot de Ventas
Conversaciones completamente pre-programadas que funcionan SIN API
"""

import time
import sys

# Colores
class C:
    BOT = '\033[92m'
    USER = '\033[96m'
    TITLE = '\033[95m'
    GREY = '\033[90m'
    END = '\033[0m'
    BOLD = '\033[1m'

def type_text(text, delay=0.03):
    """Simulate typing"""
    for char in text:
        print(char, end='', flush=True)
        time.sleep(delay)
    print()

def print_scenario(num, title):
    print(f"\n{C.TITLE}{'='*70}{C.END}")
    print(f"{C.TITLE}{C.BOLD}ESCENARIO {num}: {title}{C.END}")
    print(f"{C.TITLE}{'='*70}{C.END}\n")
    time.sleep(1)

def chat(user_msg, bot_msg):
    print(f"{C.USER}Vos: {C.END}", end='')
    type_text(user_msg)
    time.sleep(0.8)
    print(f"{C.BOT}Bot: {C.END}", end='')
    type_text(bot_msg, delay=0.02)
    time.sleep(1.5)

# ============================================================================
# ESCENARIO 1: Compra de Sierra Circular
# ============================================================================
print_scenario(1, "Compra de Sierra Circular Air M3")

chat(
    "Hola!",
    "¡Buenas! 👋 ¿Qué producto estás buscando?"
)

chat(
    "Busco una Sierra Circular Air",
    "Dale! Tenemos Sierra Circular Air M2 y M3. ¿Cuál te interesa?"
)

chat(
    "La M3 de 256GB en gris",
    "Perfecto! 💻 Sierra Circular Air M3 256GB Space Gray - $2.200.000\n"
    "Tengo 4 unidades disponibles.\n"
    "¿Te la llevo? Dame tu nombre y contacto"
)

chat(
    "Soy Martina, mi WhatsApp es 1144556677",
    "Genial Martina! ¿Dónde te la mando? (CABA/AMBA/Interior o Retiro en local)"
)

chat(
    "CABA",
    "Perfecto, CABA gratis en moto 24-48hs. ¿Cómo pagás? (Transferencia/Efectivo/MercadoPago/Tarjeta)"
)

chat(
    "Transferencia",
    "Dale! 💳 Resumen:\n"
    "Sierra Circular Air M3 256GB Space Gray - $2.200.000\n"
    "Envío CABA: Gratis\n"
    "Pago: Transferencia\n"
    "¿Confirmamos?"
)

chat(
    "Dale, confirmo",
    "🎉 ¡Listo! Reserva creada por 30 minutos.\n"
    "Te mando los datos de transferencia al 1144556677.\n"
    "¡Gracias Martina!"
)

# ============================================================================
# ESCENARIO 2: Herramienta + Cross-sell ACEPTADO
# ============================================================================
print_scenario(2, "Herramienta + Cross-selling (Destornillador a Bateria con descuento)")

chat(
    "Hola",
    "¡Buenas! 👋 ¿Qué Herramienta estás buscando?"
)

chat(
    "Amoladora 115mm Pro 256 Black",
    "Excelente elección! 📱 Amoladora 115mm Pro 256GB Black - $2.000.000\n"
    "Tengo 1 unidad disponible. ¿Te lo llevás? Dame nombre y contacto"
)

chat(
    "Perfecto! Me llamo Lucas, cel 1155443322",
    "Genial Lucas! ¿Dónde te lo mando?"
)

chat(
    "Retiro en local",
    "Dale! ¿Cómo pagás?"
)

chat(
    "MercadoPago",
    "Perfecto! 📱 Resumen:\n"
    "Amoladora 115mm Pro 256GB Black - $2.000.000\n"
    "Retiro en local (coordinamos horario)\n"
    "Pago: MercadoPago\n"
    "¿Confirmamos?"
)

chat(
    "Confirmar",
    "🎉 ¡Venta confirmada!\n\n"
    "💡 Ey Lucas, ahora que compraste el Herramienta, te tengo una promo EXCLUSIVA:\n"
    "Destornillador a Bateria Bosch a $405.000 (10% OFF - solo para esta compra)\n"
    "¿Los sumamos?"
)

chat(
    "Dale, agrego los Destornillador también",
    "🎉 ¡Genial! Destornillador agregado con 10% descuento.\n"
    "Total: Herramienta + Destornillador a Bateria = $2.405.000\n"
    "Te coordino todo al 1155443322. ¡Gracias Lucas!"
)

# ============================================================================
# ESCENARIO 3: Nivel Laser 5 - Búsqueda por categoría
# ============================================================================
print_scenario(3, "Nivel Laser 5 - Búsqueda por categoría")

chat(
    "Buenas",
    "¡Hola! 👋 ¿Qué estás buscando?"
)

chat(
    "Qué tenés de Nivel Laser?",
    "🎮 Nivel Laser:\n"
    "• PS5 Disc White - $950.000 (3 unidades)\n"
    "• PS5 Digital White - $850.000 (4 unidades)\n"
    "• DualSense Controller White - $120.000 (10 unidades)\n"
    "• DualSense Controller Black - $120.000 (8 unidades)\n"
    "¿Cuál te interesa?"
)

chat(
    "La PS5 digital",
    "Excelente! 🎮 PS5 Digital White - $850.000\n"
    "Tengo 4 disponibles. ¿Te la llevás? Dame nombre y contacto"
)

chat(
    "Sí. Carolina 1198765432",
    "Genial Carolina! ¿Dónde te la mando?"
)

chat(
    "AMBA",
    "Dale! AMBA consultar costo, 48-72hs. ¿Cómo pagás?"
)

chat(
    "Efectivo",
    "Perfecto! 🎮 Resumen:\n"
    "PS5 Digital White - $850.000\n"
    "Envío AMBA (consultamos costo)\n"
    "Pago: Efectivo\n"
    "¿Confirmamos?"
)

chat(
    "Sí, confirmo",
    "🎉 ¡Reserva creada!\n\n"
    "💡 Carolina, para jugar de a dos te ofrezco:\n"
    "DualSense Controller extra a $114.000 (5% OFF, solo para esta compra)\n"
    "¿Lo sumamos?"
)

chat(
    "Dale, vamos con el joystick también",
    "🎉 ¡Genial! Controller agregado con 5% descuento.\n"
    "Total: PS5 + Controller = $964.000\n"
    "Te contacto al 1198765432 para coordinar.\n"
    "¡Gracias Carolina!"
)

# ============================================================================
# ESCENARIO 4: Lijadora - Consulta de modelos
# ============================================================================
print_scenario(4, "Lijadora - Consulta de modelos disponibles")

chat(
    "Hola",
    "¡Buenas! 👋 ¿Buscás algo específico?"
)

chat(
    "Busco un Lijadora",
    "Dale! ¿Qué modelo te interesa? Tengo Lijadora 10, Lijadora Air y Lijadora Pro"
)

chat(
    "Qué modelos tenés disponibles?",
    "📱 Lijadoras disponibles:\n"
    "• Lijadora 10 64GB - $700.000 (5 unidades)\n"
    "• Lijadora Air 11 256GB - $1.300.000 (3 unidades)\n"
    "• Lijadora Pro 11 512GB - $1.900.000 (2 unidades)\n"
    "• Lijadora Pro 12.9 512GB - $2.200.000 (2 unidades)\n"
    "¿Cuál te gusta?"
)

chat(
    "El Lijadora Pro 11 de 512GB gris",
    "Excelente! 📱 Lijadora Pro 11 512GB Space Gray - $1.900.000\n"
    "Tengo 2 disponibles. Dame nombre y contacto"
)

chat(
    "Dale. Soy Federico, 1177889900",
    "Genial Federico! ¿Dónde te lo mando?"
)

chat(
    "Interior",
    "Dale! Interior por Correo/Andreani 3-5 días. ¿Cómo pagás?"
)

chat(
    "Tarjeta",
    "Perfecto! Con tarjeta hay recargo según cuotas, lo confirmamos antes.\n"
    "📱 Resumen:\n"
    "Lijadora Pro 11 512GB - $1.900.000 + recargo tarjeta\n"
    "Envío Interior\n"
    "¿Confirmamos?"
)

chat(
    "Confirmar",
    "🎉 ¡Reserva creada! Te contacto al 1177889900 para los datos.\n"
    "¡Gracias Federico!"
)

# ============================================================================
# ESCENARIO 5: Herramienta + Cross-sell RECHAZADO
# ============================================================================
print_scenario(5, "Herramienta + Cross-selling rechazado")

chat(
    "Hola!",
    "¡Buenas! 👋 ¿Qué Herramienta buscás?"
)

chat(
    "Taladro Percutor 13mm Pro Max 512 Natural",
    "📱 Taladro Percutor 13mm Pro Max 512GB Natural Titanium - $2.200.000\n"
    "Tengo 1 unidad. ¿Te lo llevás? Nombre y contacto"
)

chat(
    "Sí, lo quiero. Valeria 1166554433",
    "Genial Valeria! ¿Dónde te lo mando?"
)

chat(
    "CABA",
    "Perfecto! ¿Cómo pagás?"
)

chat(
    "Transfer",
    "Dale! 📱 Resumen:\n"
    "Taladro Percutor 13mm Pro Max 512GB - $2.200.000\n"
    "CABA gratis 24-48hs\n"
    "Transferencia\n"
    "¿Confirmo?"
)

chat(
    "Dale",
    "🎉 ¡Venta confirmada!\n\n"
    "💡 Valeria, te ofrezco Destornillador a Bateria a $405.000 (10% OFF, solo ahora)\n"
    "¿Los sumamos al pedido?"
)

chat(
    "No gracias, solo el Herramienta",
    "Perfecto, sin drama! 👍\n"
    "Te contacto al 1166554433 con los datos.\n"
    "¡Gracias Valeria!"
)

# ============================================================================
# RESUMEN
# ============================================================================
print(f"\n{C.TITLE}{'='*70}{C.END}")
print(f"{C.TITLE}{C.BOLD}✅ DEMO COMPLETADO{C.END}")
print(f"{C.TITLE}{'='*70}{C.END}\n")

print(f"{C.GREY}Escenarios demostrados:{C.END}")
print(f"{C.GREY}1. ✅ Sierra Circular Air M3 - Compra completa{C.END}")
print(f"{C.GREY}2. ✅ Herramienta + Cross-sell ACEPTADO (Destornillador a Bateria 10% OFF){C.END}")
print(f"{C.GREY}3. ✅ Nivel Laser 5 + Cross-sell ACEPTADO (Controller 5% OFF){C.END}")
print(f"{C.GREY}4. ✅ Lijadora Pro - Consulta de modelos{C.END}")
print(f"{C.GREY}5. ✅ Herramienta + Cross-sell RECHAZADO{C.END}")

print(f"\n{C.GREY}Features mostradas:{C.END}")
print(f"{C.GREY}  📱 Multi-categoría (Herramienta, Sierra Circular, Lijadora, Destornillador a Bateria, Nivel Laser){C.END}")
print(f"{C.GREY}  💡 Cross-selling INTELIGENTE:{C.END}")
print(f"{C.GREY}     • Herramienta/Mac/Lijadora → Destornillador a Bateria (10% OFF){C.END}")
print(f"{C.GREY}     • Nivel Laser → Controller (5% OFF){C.END}")
print(f"{C.GREY}  🔍 Búsqueda por categoría{C.END}")
print(f"{C.GREY}  📋 Consulta de modelos disponibles{C.END}")
print(f"{C.GREY}  🎯 Flujos completos de compra{C.END}")

print(f"\n{C.BOLD}🎉 Perfecto para filmar!{C.END}\n")
