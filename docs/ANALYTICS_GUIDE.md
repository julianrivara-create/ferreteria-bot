# 📊 Analytics Module - Guía de Uso

## 🎯 ¿Qué hace?

El módulo de Analytics trackea automáticamente todo lo que pasa en el bot:
- Conversiones (conversaciones → ventas)
- Performance de cross-selling
- Productos más consultados vs vendidos
- Puntos de abandono de clientes
- Métricas por categoría

---

## 💻 Uso Básico

### Ver Dashboard en Consola

```python
from bot_sales.bot import SalesBot

bot = SalesBot()
bot.analytics.print_dashboard()
```

**Output:**
```
============================================================
📊 ANALYTICS DASHBOARD
============================================================

🎯 Conversion Rate: 60.0%

💡 Cross-Selling:
  • Total Offers: 3
  • Accepted: 2
  • Acceptance Rate: 66.7%
  • Total Value: $519,000

📱 Cross-Sell by Category:
  • Herramienta: 50.0% (1/2)
  • PlayStation: 100.0% (1/1)

🔥 Top Products:
  1. IP16P-256-BLK (Herramienta): 5 queries, 3 sales (60%)
  2. PS5-DISC (PlayStation): 4 queries, 2 sales (50%)
  ...
```

### Exportar a CSV

```python
bot.analytics.export_to_csv("reporte_mensual.csv")
```

Genera CSV con todas las sesiones para analizar en Excel/Google Sheets.

---

## 📈 Métricas Disponibles

### 1. Conversion Rate
```python
rate = bot.analytics.get_conversion_rate()
print(f"Conversion: {rate}%")
```

### 2. Cross-Selling Stats
```python
stats = bot.analytics.get_cross_sell_stats()
# {
#   "total_offers": 10,
#   "total_accepted": 6,
#   "acceptance_rate": 60.0,
#   "total_value": 2430000
# }
```

### 3. Cross-Sell por Categoría
```python
by_cat = bot.analytics.get_cross_sell_by_category()
# [
#   {"category": "Herramienta", "offers": 5, "accepted": 3, "acceptance_rate": 60},
#   {"category": "PlayStation", "offers": 2, "accepted": 2, "acceptance_rate": 100}
# ]
```

### 4. Top Products
```python
top = bot.analytics.get_top_products(limit=10)
# [
#   {"sku": "IP16P-256", "queries": 20, "sales": 15, "conversion": 75},
#   ...
# ]
```

### 5. Abandonment Points
```python
abandon = bot.analytics.get_abandonment_points()
# {
#   "after_product_query": 5,
#   "after_price_quote": 3,
#   "after_shipping_info": 2
# }
```

---

## 🔧 Tracking Manual

Si necesitás trackear eventos custom:

```python
# Nuevo evento personalizado
bot.analytics.track_event(
    session_id="session_123",
    event_type="custom_event",
    product_sku="PROD-001",
    product_category="Herramienta",
    extra_data="valor custom"
)
```

---

## 📊 Estructura de Base de Datos

### Tabla: `analytics_events`
```sql
id              | INTEGER (PK)
session_id      | TEXT
event_type      | TEXT (conversation_start, product_query, sale, etc)
product_sku     | TEXT (nullable)
product_category| TEXT (nullable)
metadata        | TEXT (JSON)
timestamp       | DATETIME
```

### Tabla: `analytics_sessions`
```sql
session_id          | TEXT (PK)
started_at          | DATETIME
ended_at            | DATETIME
products_queried    | INTEGER
sale_completed      | BOOLEAN
sale_value          | INTEGER
cross_sell_offered  | BOOLEAN
cross_sell_accepted | BOOLEAN
cross_sell_value    | INTEGER
abandonment_point   | TEXT
total_messages      | INTEGER
```

---

## 🎯 Casos de Uso

### 1. Reporte Diario Automático

```python
# Crear script: daily_report.py
from bot_sales.bot import SalesBot

bot = SalesBot()
stats = bot.analytics.get_summary_stats()

# Enviar por email/Slack
print(f"""
📊 Reporte Diario
- Conversion: {stats['conversion_rate']}%
- Ventas Cross-sell: ${stats['cross_sell']['total_value']:,}
- Top Producto: {stats['top_products'][0]['sku']}
""")
```

### 2. Detectar Problemas

```python
# Ver dónde se pierden clientes
abandon = bot.analytics.get_abandonment_points()

# Si muchos abandonan en "shipping_info" → revisar precios envío
if abandon.get("after_shipping_info", 0) > 10:
    print("⚠️ Muchos abandonos en shipping - revisar costos")
```

### 3. Optimizar Cross-Selling

```python
# Ver qué categorías aceptan más cross-sell
by_cat = bot.analytics.get_cross_sell_by_category()

for cat in by_cat:
    if cat['acceptance_rate'] < 30:
        print(f"⚠️ {cat['category']} tiene baja aceptación: {cat['acceptance_rate']}%")
        # Ajustar descuento o mensaje
```

### 4. Identificar Best-Sellers

```python
top = bot.analytics.get_top_products(limit=5)

# Asegurar stock de top productos
for prod in top:
    db_prod = bot.db.get_product_by_sku(prod['sku'])
    if db_prod['stock_qty'] < 5:
        print(f"⚠️ Bajo stock en best-seller: {prod['sku']}")
```

---

## 📅 Automatización

### Cron Job Diario (Linux/Mac)

```bash
# Editar crontab
crontab -e

# Agregar línea (ejecuta a las 9 AM diario)
0 9 * * * cd /path/to/bot && python3 daily_report.py
```

### Task Scheduler (Windows)

1. Crear script: `daily_report.bat`
```bat
cd C:\path\to\bot
python daily_report.py
```

2. Agregar a Task Scheduler para ejecutar diario

---

## 🚀 Próximas Mejoras

Features planeadas:
- [ ] Dashboard web interactivo
- [ ] Gráficos con matplotlib
- [ ] Exportar a Google Sheets automático
- [ ] Alertas por Slack/Telegram
- [ ] Comparaciones semana/mes
- [ ] Forecast de ventas con ML

---

## ✅ Testing

```bash
# Test completo del módulo
python3 test_analytics.py

# Verificar que funciona
# Debe mostrar dashboard con métricas
```

---

## 💡 Tips

1. **Exportar semanalmente** a CSV para backup
2. **Revisar conversion rate** diario (objetivo: >40%)
3. **Optimizar cross-sell** donde acceptance rate < 50%
4. **Monitorear abandonment** para detectar friction points
5. **Trackear productos de temporada** separadamente

---

## 📞 Soporte

Si algo no funciona:
1. Verificar que tablas existan: `bot.analytics._ensure_tables()`
2. Revisar logs en `events.log`
3. Chequear permisos de escritura en DB

¡Analytics automáticos funcionando! 📊
