# 🎬 Demo Automático - Bot Multi-Categoría

Demo automático que muestra 5 escenarios variados del bot de ventas con catálogo expandido.

## 🚀 Cómo Ejecutar

```bash
cd /Users/julian/Desktop/iphone-bot-demo
python3 demo_automated_v2.py
```

## 📋 Escenarios Incluidos

### 1. **Compra de MacBook Air M3** 💻
- Búsqueda de producto específico
- Compra completa con retiro
- Muestra: Catálogo de MacBooks

### 2. **iPhone + Cross-selling (ACEPTADO)** 📱💡
- Venta de iPhone 16 Pro
- Oferta automática de AirPods con 10% OFF
- Cliente **ACEPTA** la oferta
- Muestra: Cross-selling exitoso

### 3. **Búsqueda por Categoría - PlayStation** 🎮
- Cliente pregunta por categoría completa
- Bot usa `buscar_por_categoria()`
- Compra de PS5 Digital
- Muestra: Búsqueda por categoría

### 4. **Venta de iPad Pro** 📱
- Cliente pide ver modelos disponibles
- Compra de iPad Pro 11" 512GB
- Pago con tarjeta
- Muestra: Consulta de inventario

### 5. **iPhone + Cross-selling (RECHAZADO)** 📱❌
- Venta de iPhone 15 Pro Max
- Oferta de AirPods con descuento
- Cliente **RECHAZA** (solo quiere el iPhone)
- Muestra: Manejo de rechazo en cross-sell

## ✨ Features Demostradas

- ✅ **Multi-categoría**: 5 tipos de productos
- ✅ **Cross-selling**: Ofertas post-venta automáticas
- ✅ **Descuentos contextuales**: 10% OFF en AirPods
- ✅ **Búsqueda por categoría**: `buscar_por_categoria()`
- ✅ **Consulta de modelos**: Listado dinámico
- ✅ **Flujo completo**: Desde búsqueda hasta confirmación

## 🎯 Estadísticas del Demo

Al finalizar, el demo muestra:
- 💰 Total de ventas realizadas
- 📦 Categorías disponibles
- 📊 Productos en catálogo

## 🎥 Perfect para Filmar

- **Efecto typing**: Simula escritura natural
- **Delays programados**: Pausas entre mensajes
- **Colores diferentes**: Usuario vs Bot
- **Duración**: ~3-4 minutos total
- **Variedad**: Múltiples productos y flujos

## ⚠️ Nota

Este demo funciona en **modo mock** (sin API key de OpenAI). Las respuestas son simuladas para demostración.

Para usar con ChatGPT real:
```bash
export OPENAI_API_KEY="sk-tu-key"
python3 demo_automated_v2.py
```

## 📂 Archivos Relacionados

- `demo_automated_v2.py` - Script del demo
- `catalog_extended.csv` - Catálogo con 62 productos
- `bot_sales/` - Código del bot
