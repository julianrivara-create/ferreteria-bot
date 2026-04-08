# Quick Start - Scripts de Utilidad

📦 **Scripts útiles para desarrollo local**

## 🎨 Pretty CLI

```bash
# Demo del CLI bonito
python -m bot_sales.core.pretty_cli

# Usar en tus scripts
from bot_sales.core.pretty_cli import *

print_header("Mi Script", "Subtitle opcional")
print_success("Operación exitosa!")
print_error("Algo falló")

# Tabla bonita
print_products_table(products)
```

## 🎲 Fake Data Generator

```bash
# Generar datos de prueba
python scripts/generate_fake_data.py

# Esto crea:
# - fake_customers.json (50 clientes)
# - fake_products.csv (100 productos)
# - fake_sales.json (200 ventas)
# - fake_conversations.json (30 conversaciones)
```

### Uso programático:

```python
from scripts.generate_fake_data import DataGenerator

gen = DataGenerator(seed=42)  # Reproducible

# Generar clientes
customers = gen.generate_customers(100)

# Generar productos por categoría
phones = [gen.generate_product('electronics') for _ in range(20)]
clothes = [gen.generate_product('clothing') for _ in range(30)]

# Generar ventas
sales = gen.generate_sales(500, customers, phones)

# Guardar
gen.save_to_json(customers, 'my_customers.json')
gen.save_to_csv(phones, 'my_products.csv')
```

## 📝 Seed Database

```bash
# Poblar database con datos realistas
python scripts/seed_database.py --customers 50 --products 100 --sales 200

# O solo productos
python scripts/seed_database.py --products-only --count 500
```

## 🧪 Run All Tests

```bash
# Tests con output bonito
python scripts/run_tests.py

# Con coverage
python scripts/run_tests.py --coverage

# Solo un archivo
python scripts/run_tests.py --file test_validators.py
```

## 📊 Generate Reports

```bash
# Reporte de ventas (PDF)
python scripts/generate_report.py --type sales --period weekly --format pdf

# Analytics dashboard (HTML)
python scripts/generate_report.py --type analytics --format html
```

## ✅ Validate Everything

```bash
# Validar toda la configuración
python scripts/validate_all.py

# Checklist:
# - Config files valid
# - Database schema correct
# - Catalog CSV format
# - All imports working
# - Environment variables set
```

## 🔍 Find Issues

```bash
# Buscar problemas comunes
python scripts/find_issues.py

# Reporta:
# - Productos sin stock
# - Precios inconsistentes
# - Reservas expiradas
# - Clientes duplicados
```

---

## 🎁 Extras

### Pretty Output en Cualquier Script

```python
# add to any script
import sys
sys.path.insert(0, '.')

from bot_sales.core.pretty_cli import console, print_success, print_table

# Now use it!
console.print("[bold green]Hello![/bold green]")
print_success("It works!")
```

### Demo Interactivo

```bash
# Demo interactivo completo
python scripts/interactive_demo.py

# Muestra:
# - Products catalog (tabla bonita)
# - Search simulation
# - Order flow
# - Dashboard preview
```

---

📚 Ver código fuente para más ejemplos
