# 🎬 Demo Automático - Bot Multi-Categoría

Demo automático que muestra 5 escenarios variados del bot de ventas con catálogo expandido.

## 🚀 Cómo Ejecutar

```bash
cd /Users/julian/Desktop/iphone-bot-demo
python3 demo_automated_v2.py
```

## 📋 Escenarios Incluidos

### 1. **Compra de Sierra Circular Air M3** 💻
- Búsqueda de producto específico
- Compra completa con retiro
- Muestra: Catálogo de Sierra Circulars

### 2. **Herramienta + Cross-selling (ACEPTADO)** 📱💡
- Venta de Amoladora 230mm
- Oferta automática de Destornillador a Bateria con 10% OFF
- Cliente **ACEPTA** la oferta
- Muestra: Cross-selling exitoso

### 3. **Búsqueda por Categoría - PlayStation** 🎮
- Cliente pregunta por categoría completa
- Bot usa `buscar_por_categoria()`
- Compra de PS5 Digital
- Muestra: Búsqueda por categoría

### 4. **Venta de Lijadora Orbital Pro** 📱
- Cliente pide ver modelos disponibles
- Compra de Lijadora Orbital Pro 11" 512GB
- Pago con tarjeta
- Muestra: Consulta de inventario

### 5. **Herramienta + Cross-selling (RECHAZADO)** 📱❌
- Venta de Taladro Percutor 13mm Max
- Oferta de Destornillador a Bateria con descuento
- Cliente **RECHAZA** (solo quiere el Herramienta)
- Muestra: Manejo de rechazo en cross-sell

## ✨ Features Demostradas

- ✅ **Multi-categoría**: 5 tipos de productos
- ✅ **Cross-selling**: Ofertas post-venta automáticas
- ✅ **Descuentos contextuales**: 10% OFF en Destornillador a Bateria
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
