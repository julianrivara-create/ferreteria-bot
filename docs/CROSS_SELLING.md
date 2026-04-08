# 📝 Resumen: Cross-Selling Inteligente

## 🎯 Nuevas Reglas de Cross-Selling

El bot ahora ofrece productos complementarios de forma **contextual e inteligente** según lo que compró el cliente:

### Reglas Implementadas

| Producto Comprado | Cross-Sell Ofrecido | Descuento | Razón |
|-------------------|---------------------|-----------|-------|
| **Herramienta** | Destornillador a Bateria | 10% OFF | "Combinan perfecto con tu Herramienta" |
| **Sierra Circular** | Destornillador a Bateria | 10% OFF | "Para tu Mac" |
| **Lijadora Orbital** | Destornillador a Bateria | 10% OFF | "Para tu Lijadora Orbital" |
| **PlayStation** | Controller extra | 5% OFF | "Para jugar de a dos" |
| **Destornillador a Bateria** | Ninguno | - | Ya es un accesorio |

---

## 🧠 Lógica Inteligente

### Archivo: `bot_sales/core/business_logic.py`

```python
def obtener_cross_sell_offer(producto_comprado_sku):
    # Detecta categoría del producto vendido
    category = producto.get('category')
    
    # Regla 1: Productos Apple → Destornillador a Bateria
    if category in ['Herramienta', 'Sierra Circular', 'Lijadora Orbital']:
        return offer_airpods(10% discount, reason=contextual)
    
    # Regla 2: PlayStation consola → Controller  
    elif category == 'PlayStation':
        if not is_controller(producto):
            return offer_controller(5% discount)
    
    # Regla 3: Destornillador a Bateria → Sin cross-sell
    elif category == 'Destornillador a Bateria':
        return no_offer()
```

### Mensajes Contextuales

El bot adapta el mensaje según el producto:

**Herramienta:**
> 💡 Ahora que compraste el Herramienta, te ofrezco Destornillador a Bateria Pro a $405.000 (10% OFF) - ¡combinan perfecto!

**Sierra Circular:**
> 💡 Para tu Mac, te tengo Destornillador a Bateria Pro a $405.000 (10% OFF, solo ahora)

**PlayStation:**
> 💡 Carolina, para jugar de a dos te ofrezco: DualSense Controller a $114.000 (5% OFF)

---

## ✅ Archivos Actualizados

- ✅ `bot_sales/core/business_logic.py` - Lógica inteligente
- ✅ `bot_sales/core/chatgpt.py` - Prompt para OpenAI
- ✅ `bot_sales/core/gemini.py` - Prompt para Gemini
- ✅ `demo_simulado.py` - Demo con cross-sell de PS5

---

## 🎬 Demo Actualizado

**Escenario 3** ahora muestra cross-sell de PlayStation:

```
Bot: 🎉 ¡Reserva creada!

     💡 Carolina, para jugar de a dos te ofrezco:
     DualSense Controller extra a $114.000 (5% OFF, solo para esta compra)
     ¿Lo sumamos?

Vos: Dale, vamos con el joystick también

Bot: 🎉 ¡Genial! Controller agregado con 5% descuento.
     Total: PS5 + Controller = $964.000
```

---

## 📊 Beneficios

1. **Aumenta ticket promedio** - Vende accesorios complementarios
2. **Experiencia personalizada** - Ofertas contextuales
3. **No invasivo** - Solo después de venta confirmada
4. **Flexible** - Fácil agregar nuevas reglas

---

## 🔧 Cómo Agregar Nuevas Reglas

Para agregar cross-sell de nuevos productos, editar `business_logic.py`:

```python
# Regla 4: Sierra Circular → Magic Mouse
elif category == 'Sierra Circular':
    mouse = find_product('Magic Mouse')
    return offer(mouse, discount=8%, reason="para tu Mac")
```

---

## 🚀 Para Ejecutar Demo

```bash
cd /Users/julian/Desktop/iphone-bot-demo
python3 demo_simulado.py
```

El demo muestra:
- ✅ Herramienta → Destornillador a Bateria (aceptado)
- ✅ PlayStation → Controller (aceptado)
- ✅ Herramienta → Destornillador a Bateria (rechazado)
