# Ferreteria Central Bot

Bot de ventas para WhatsApp con interfaz interna de entrenamiento. Proyecto en `/Users/julian/Desktop/Cerrados/Ferreteria`.

## Estado actual

- Tenant `ferreteria` operativo y validado
- Catálogo con herramientas, fijaciones, pinturería, plomería y seguridad
- Políticas y FAQs cargadas (ventas, pagos, envíos, factura, cambios)
- Bot de WhatsApp listo con routing multi-tenant
- Interfaz web de entrenamiento con flujo simple A → B → C
- Demo local generado desde `bootstrap_training_demo.py`

---

## Arranque rápido

```bash
cd /Users/julian/Desktop/Cerrados/Ferreteria
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Variables de entorno mínimas (copiar `.env.example` si existe, o crear `.env`):

```
DATABASE_URL=...
SECRET_KEY=...
ADMIN_TOKEN=...
ADMIN_PASSWORD=...
OPENAI_API_KEY=...
```

Arrancar el servidor:

```bash
gunicorn wsgi:app
# o en desarrollo:
python3 wsgi.py
```

---

## Interfaz de entrenamiento

Acceso: `/ops/ferreteria/training`

Requiere contraseña (`ADMIN_PASSWORD`). Una vez adentro, el flujo tiene tres pasos:

| Paso | Pantalla | Qué hacés |
|---|---|---|
| **A** | Hablar con el bot | Probás una conversación y marcás la primera respuesta que se desvió |
| **B** | Esto estuvo mal | Le explicás qué tendría que haber hecho; el sistema arma el borrador |
| **C** | Cambios listos | Revisás el antes/después y activás el cambio |

**Más herramientas** (`/ops/ferreteria/training/tools`) agrupa vistas de apoyo: términos sin resolver, impacto, uso, historial de sesiones y colas avanzadas.

Demo local:

```bash
python3 scripts/bootstrap_training_demo.py
python3 -m http.server 8033 --directory tmp/training_demo/snapshots
```

Guía completa de uso para operadores: `docs/guia_operativa_entrenamiento_ferreteria.md`

---

## WhatsApp

```bash
# Arranque de producción via wsgi
gunicorn wsgi:app

# Variables necesarias
FERRETERIA_WHATSAPP_PHONE_NUMBER_ID=...
META_VERIFY_TOKEN=...
META_ACCESS_TOKEN=...
```

El webhook de Meta apunta a: `/webhooks/meta`

---

## Validaciones y smoke tests

```bash
# Validar configuración del tenant
python3 scripts/validate_tenant.py --slug ferreteria

# Smoke del flujo de negocio sin web
python3 scripts/smoke_ferreteria.py

# Smoke rápido de la interfaz de entrenamiento
python3 scripts/smoke_training_ui.py

# Preflight antes de deployar a staging/producción
python3 scripts/preflight_production.py --mode staging
python3 scripts/preflight_production.py --mode production
```

Suite de tests (señal principal de release):

```bash
# Suite focalizada Ferretería — esta es la señal válida
pytest -q tests/test_ferreteria_setup.py tests/test_ferreteria_vnext.py \
  tests/test_ferreteria_phase2_families.py tests/test_ferreteria_phase4_continuity.py \
  tests/test_ferreteria_phase5_automation.py tests/test_ferreteria_training.py \
  tests/test_ferreteria_training_smoke.py app/bot/tests/test_tenancy.py \
  app/bot/tests/test_routing.py

# Suite completa (requiere JWT_SECRET y ADMIN_PASSWORD en el entorno)
JWT_SECRET=... ADMIN_PASSWORD=... pytest -q tests app/bot/tests
```

---

## Archivos clave

| Archivo | Para qué |
|---|---|
| `wsgi.py` | Entrypoint de producción |
| `bot_sales/runtime.py` | Runtime del tenant ferretería |
| `app/ui/ferreteria_training_routes.py` | Rutas UI de entrenamiento |
| `data/tenants/ferreteria/catalog.csv` | Catálogo de productos |
| `data/tenants/ferreteria/` | Perfil, políticas, FAQ y conocimiento del tenant |
| `docs/guia_operativa_entrenamiento_ferreteria.md` | Guía para operadores |
| `scripts/preflight_production.py` | Validación pre-deploy |
| `scripts/staging_smoke.py` | Smoke contra endpoints en vivo |

---

## Deploy

El servidor está configurado para Railway/cualquier plataforma con `gunicorn wsgi:app`.

Antes de promover a producción:

```bash
python3 scripts/preflight_production.py --mode production
```

Después de deployar:

```bash
python3 scripts/staging_smoke.py --base-url https://tu-app.railway.app \
  --admin-token $ADMIN_TOKEN --tenant-slug ferreteria
```
