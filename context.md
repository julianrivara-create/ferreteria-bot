# Contexto del Proyecto

Actualizado: 2026-04-22

## Que es este repo

Este proyecto es un bot de ventas para ferreteria con foco en WhatsApp, storefront multi-tenant, paneles internos y una capa conversacional que mezcla AI con logica deterministica de negocio.

No es un chatbot greenfield ni un experimento suelto. Es un sistema en evolucion con dos capas que conviven:

- `app/`: stack web/API/productivo en Flask.
- `bot_sales/`: motor conversacional, catalogo, cotizaciones, continuidad y logica comercial.

La direccion tecnica actual es clara:

- la AI interpreta lenguaje, intencion, aceptacion, tono y clarificaciones;
- la verdad de negocio sigue siendo deterministica: precios, stock, quote state, reservas, confirmaciones, politicas duras.

## Runtime canonico hoy

El runtime canonico de produccion entra por:

- [wsgi.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/wsgi.py)

Ese entrypoint hace esto:

1. intenta levantar el stack final por `app.main`;
2. registra extensiones multi-tenant del storefront y dashboard;
3. agrega `X-Runtime-Stack`;
4. solo permite fallback legacy si el entorno lo habilita explicitamente o si es dev/local/test.

En produccion, el objetivo es que corra siempre el stack `final`, no el legacy.

## Servicio canonico en Railway

Servicio oficial de produccion:

- `ferreteria-bot`

Servicio no canonico:

- `ferreteria-bot-clean` no debe ser tratado como produccion principal.

Documentacion operativa actual:

- [docs/RAILWAY_DEPLOY.md](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/docs/RAILWAY_DEPLOY.md)

Puntos importantes de Railway:

- el deploy usa el arbol local actual cuando se hace `railway up`;
- `.env` y `.db` locales no se suben;
- la paridad con produccion se resuelve con variables, volumen y chequeos de integridad;
- si Railway sigue conectado a GitHub, un auto-deploy desde `main` puede pisar un deploy manual y reabrir deriva entre local y remoto.

## Arquitectura de alto nivel

### 1. Capa web / API

Archivo principal:

- [app/main.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/app/main.py)

Responsabilidades:

- crear la app Flask;
- registrar blueprints de admin, training, webhooks, chat publico, CRM y storefront;
- exponer health y endpoints diagnosticos;
- bootstrapping de runtime;
- configurar CORS;
- arrancar schedulers auxiliares.

Endpoints relevantes:

- `/health`
- `/api/health`
- `/api/chat`
- `/api/catalog`
- `/api/t/<tenant>/products`
- `/diag/db`
- `/diag/runtime-integrity`

### 2. Capa conversacional / ferreteria

Archivo orquestador principal:

- [bot_sales/bot.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/bot_sales/bot.py)

Este modulo coordina:

- `ChatGPTClient`
- `BusinessLogic`
- `QuoteStore` y `QuoteService`
- `TurnInterpreter`
- `CatalogSearchService`
- `PolicyService`
- continuidad y automation
- observabilidad por turno

La situacion actual no es un rewrite total. Sigue habiendo piezas historicas como `ferreteria_quote.py`, pero el proyecto ya tiene componentes nuevos que empujan a una arquitectura mas limpia:

- `bot_sales/routing/`
- `bot_sales/handlers/`
- `bot_sales/services/catalog_search_service.py`
- `bot_sales/services/policy_service.py`
- `bot_sales/state/`
- `bot_sales/observability/`

## Filosofia de producto/arquitectura

Regla central:

- si la verdad viene del negocio, debe ser deterministica;
- si viene del lenguaje del cliente, la AI puede interpretar.

### Deterministico

- precios
- stock
- quote state
- reservas y confirmaciones
- politicas duras
- validaciones de datos

### AI / hibrido

- interpretacion de intencion
- aceptacion / rechazo en lenguaje natural
- sintesis de FAQ
- reformulacion natural
- deteccion de frustracion / handoff
- interpretacion de necesidad de producto
- clarificaciones conversacionales

## Product search actual

La busqueda de producto ya no depende solo de matching bruto.

Direccion actual:

- AI interpreta la necesidad;
- un servicio deterministico busca en catalogo real;
- la respuesta final se redacta con datos reales;
- si falta precision, se pide clarificacion.

Pieza nueva relevante:

- [bot_sales/services/catalog_search_service.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/bot_sales/services/catalog_search_service.py)

Pieza historica aun viva:

- [bot_sales/ferreteria_quote.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/bot_sales/ferreteria_quote.py)

Conclusión practica: el repo esta en transicion controlada, no en arquitectura final completamente consolidada. Hay que leer ambas capas antes de tocar flujo comercial.

## Politicas y conocimiento

Fuentes de verdad editoriales:

- [config/policies.md](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/config/policies.md)
- [config/catalog.csv](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/config/catalog.csv)
- [data/tenants/ferreteria/policies.md](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/data/tenants/ferreteria/policies.md)
- [data/tenants/ferreteria/catalog.csv](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/data/tenants/ferreteria/catalog.csv)
- [data/tenants/ferreteria/knowledge/family_rules.yaml](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/data/tenants/ferreteria/knowledge/family_rules.yaml)
- [data/tenants/ferreteria/knowledge/item_family_map.yaml](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/data/tenants/ferreteria/knowledge/item_family_map.yaml)

La AI no deberia inventar politicas ni catalogo. Tiene que sintetizar o interpretar, pero la fuente real vive en esos archivos y en la DB.

## Configuracion de produccion

Archivo clave:

- [app/core/config.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/app/core/config.py)

Estado esperado en produccion:

- `ENVIRONMENT=production`
- `DATABASE_URL` explicita
- `SECRET_KEY` segura
- `ADMIN_TOKEN` seguro
- `OPENAI_API_KEY` presente
- `CORS_ORIGINS` definida
- `ALLOW_LEGACY_FALLBACK` deshabilitado

La proteccion importante que ya existe:

- produccion no debe depender del fallback local de SQLite;
- si falta `DATABASE_URL` explicita, debe fallar;
- si la configuracion critica es insegura, debe advertir o bloquear.

## Estrategia de datos

Hoy el proyecto soporta SQLite y puede convivir con Postgres via `DATABASE_URL`.

En Railway, la estrategia operativa reciente apunta a:

- SQLite sobre volumen montado, no dentro de la imagen;
- catalogo y policies versionados dentro del repo;
- la DB productiva no se copia desde local.

Chequeo diagnostico asociado:

- [app/services/runtime_integrity.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/app/services/runtime_integrity.py)
- [scripts/check_railway_parity.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/scripts/check_railway_parity.py)

## Deploy y verificaciones

Archivos operativos:

- [Dockerfile](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/Dockerfile)
- [railway.json](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/railway.json)
- [scripts/check_railway_parity.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/scripts/check_railway_parity.py)
- [scripts/preflight_production.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/scripts/preflight_production.py)
- [scripts/staging_smoke.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/scripts/staging_smoke.py)

Comandos utiles:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
./.venv/bin/python scripts/check_railway_parity.py --service ferreteria-bot
```

```bash
railway up -s ferreteria-bot -e production -m "Deploy canonical ferreteria bot"
```

Lo que hay que mirar siempre despues de deploy:

- `/health`
- `/api/health`
- header `X-Runtime-Stack=final`
- `/diag/runtime-integrity`

## Tests y señales utiles

Tests recientes de runtime/paridad:

- [tests/test_runtime_integrity.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/tests/test_runtime_integrity.py)
- [tests/test_production_config_validation.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/tests/test_production_config_validation.py)
- [tests/test_runtime_bootstrap_fail_closed.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/tests/test_runtime_bootstrap_fail_closed.py)
- [tests/test_runtime_bootstrap_admin_policy.py](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/tests/test_runtime_bootstrap_admin_policy.py)

Cuando el foco es ferreteria conversacional, tambien conviene mirar:

- `tests/test_ferreteria_*`
- `bot_sales/tests/test_routing.py`
- `bot_sales/tests/test_tenancy.py`

## Estado del repo al momento de este contexto

El repo local no esta limpio. Hay cambios sin commit y modulos nuevos sin trackear.

Eso importa porque:

- un deploy manual puede reflejar tu arbol local;
- un auto-deploy de GitHub no ve esos cambios hasta que se commitean y pushean;
- por lo tanto, local y Railway pueden divergir aunque ambos "funcionen".

Si queres verificar paridad real, no alcanza con mirar health. Hay que correr el checker y confirmar tambien la fuente del deployment.

## Directorios importantes

- [app](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/app): stack web, API, CRM, bootstrapping
- [bot_sales](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/bot_sales): motor conversacional y logica comercial
- [data/tenants/ferreteria](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/data/tenants/ferreteria): conocimiento y datos del tenant
- [config](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/config): catalogo/policies globales
- [docs](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/docs): decisiones y guias operativas
- [scripts](/Users/julian/Desktop/Claude-Cowork/Projects/Automation/Bots/ferreteria/scripts): preflight, smoke, parity, utilidades operativas

## Que no asumir

- no asumir que GitHub y el arbol local son lo mismo;
- no asumir que `ferreteria-bot-clean` es el servicio real;
- no asumir que la AI decide acciones irreversibles;
- no asumir que `ferreteria_quote.py` ya fue reemplazado por completo;
- no asumir que un `200 OK` implica paridad completa.

## Resumen brutal

Este proyecto ya no es solo un bot rigido, pero tampoco termino de salir del estado de transicion. La ruta correcta hoy es:

- runtime final por `wsgi.py -> app.main`;
- servicio canonico `ferreteria-bot`;
- datos/politicas validados por chequeos deterministas;
- AI usada para interpretar lenguaje, no para inventar negocio;
- verificaciones de paridad antes de confiar en que Railway y local son "lo mismo".
