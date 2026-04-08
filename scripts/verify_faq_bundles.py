#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test FAQ and Bundles
"""

import sys
sys.path.insert(0, '.')

from bot_sales.core.database import Database
from bot_sales.core.business_logic import BusinessLogic

# Initialize
db = Database('ferreteria.db', 'catalog_extended.csv', 'events.log')
logic = BusinessLogic(db)

print("🧪 Testing FAQ and Bundles...")
print()

# === TEST FAQs ===
print("="*60)
print("TEST 1: FAQs")
print("="*60)

test_questions = [
    "Cómo es el envío?",
    "Tienen garantía?",
    "Puedo pagar en cuotas?",
    "Hacen factura A?",
    "Esta pregunta no debería matchear nada"
]

for q in test_questions:
    result = logic.consultar_faq(q)
    print(f"\nPregunta: {q}")
    if result["status"] == "found":
        print(f"✅ FAQ encontrado:")
        print(result["respuesta"])
    else:
        print("❌ No es FAQ")

print()
print()

# === TEST BUNDLES ===
print("="*60)
print("TEST 2: Bundles")
print("="*60)

# List all bundles
bundles_result = logic.listar_bundles()
print(f"\n📦 Total bundlesactivos: {bundles_result['total']}")

for bundle in bundles_result['bundles'][:5]:  # Show first 5
    print(f"\n• {bundle['name']}")
    print(f"  Precio: ${bundle['final_price']:,}")
    print(f"  Descuento: {bundle['discount_percent']}% (ahorrás ${bundle['savings']:,})")
    if bundle['is_seasonal']:
        print(f"  ⏰ PROMO TEMPORAL")

# Get specific bundle
print()
print()
print("="*60)
print("TEST 3: Bundle Específico")
print("="*60)

bundle_detail = logic.obtener_bundle("gamer_basic")
if bundle_detail["status"] == "found":
    print(bundle_detail["formatted_message"])

db.close()
print()
print("✅ FAQ y Bundles test complete!")
