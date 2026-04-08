# Launch New Bot (15 minutos)

## Alcance
- Este flujo opera solo dentro de `/Users/julian/Desktop/Cerrados/sales-bot-platform`.
- No requiere tocar código de runtime para un nuevo rubro.

## 0) Clonar base completa en 1 comando (opcional, recomendado para nuevo proyecto)
```bash
python3 scripts/clone_full_bot.py \
  --destination /Users/julian/Desktop/Cerrados/bot-ferreteria \
  --with-tenant \
  --tenant-name "Bot Ferreteria" \
  --tenant-slug ferreteria \
  --industry ferreteria \
  --run-checks
```

Resultado esperado:
- Se crea una copia completa de esta plataforma en la carpeta destino.
- Se crea tenant inicial en el clon (`data/tenants/ferreteria/...`).
- Se ejecutan checks base en el clon (si usas `--run-checks`).

## 1) Crear tenant en 1 comando
```bash
python3 scripts/create_tenant.py \
  --non-interactive \
  --name "Mi Negocio" \
  --slug mi-negocio \
  --industry clothing \
  --language es \
  --currency ARS \
  --country AR \
  --tone profesional \
  --phone "+5491112345678"
```

Resultado esperado:
- `data/tenants/<slug>/profile.yaml`
- `data/tenants/<slug>/catalog.csv`
- `data/tenants/<slug>/policies.md`
- `data/tenants/<slug>/branding.json`
- Entrada actualizada en `tenants.yaml`

## 2) Cargar catálogo real
- Editar `data/tenants/<slug>/catalog.csv`
- Formatos soportados:
1. Legacy: `SKU,Category,Model,StorageGB,Color,StockQty,PriceARS`
2. Nuevo: `sku,category,name,price,currency,stock,...extras`

Nota:
- Columnas extra del formato nuevo se guardan en `attributes_json`.

## 3) Ajustar identidad del negocio
- Editar `data/tenants/<slug>/profile.yaml`
- Editar `data/tenants/<slug>/branding.json`
- Editar `data/tenants/<slug>/policies.md`

## 4) Validar tenant
```bash
python3 scripts/validate_tenant.py --slug <slug>
```

Debe terminar con:
- `[OK] <slug>`
- `Validation passed`

## 5) Smoke de runtime
```bash
python3 scripts/smoke_runtime.py
```

Debe responder `OK` en:
- `GET /health`
- `GET /api/products` (legacy)
- `GET /api/t/farmacia/products`
- `GET /api/t/ropa/products`
- `GET /dashboard/login`

## 6) QA suite
```bash
pytest -q
```

## 7) Endpoints y rutas de uso
- Storefront tenant:
  - `/t/<slug>`
  - `/api/t/<slug>/storefront`
  - `/api/t/<slug>/products`
  - `/api/t/<slug>/product?model=...`
  - `/api/t/<slug>/chat`
- Dashboard tenant:
  - `/dashboard/t/<slug>`
- Legacy compat:
  - `/api/products`
  - `/api/chat`

## Definición de listo para deploy
- `validate_tenant.py` pasa para el tenant nuevo.
- `smoke_runtime.py` pasa completo.
- `pytest -q` pasa.
- Web y dashboard renderizan branding/categorías del tenant correcto.
