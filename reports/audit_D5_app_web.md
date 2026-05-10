# Audit D5 — app/ (web/API/Flask)

**HEAD:** 9f7369d
**Fecha:** 2026-05-09
**Archivos auditados:** 135 archivos .py (excluido app/ui/)

---

## Resumen ejecutivo

- La capa web es Flask con application factory (`create_app`). El runtime canónico es `ferreteria-bot` desplegado en Railway. La versión declarada en el health endpoint es `2.0.3-DIAG`.
- Hay **11 blueprints registrados** cubriendo webhooks de Meta/MP, APIs públicas de catálogo, APIs de administración, CRM completo (API + UI), training, console y storefront multi-tenant.
- La capa CRM (`app/crm/`) está **completamente viva y en producción**: tiene ~4 100 líneas de rutas, modelos propios, scheduler de jobs y auth JWT con RBAC fino.
- El módulo `app/mail/` es **funcional a nivel M0** (OAuth, lectura de inbox, CLI) pero sin integración Flask ni endpoints REST — es un tooling CLI standalone.
- `app/bot/` y `bot_sales/` comparten **4 módulos con misma clase principal** (`Analytics`, `BundleManager`, `FAQHandler`, `RecommendationEngine`) y configs paralelas — riesgo de divergencia silenciosa.
- **Gap crítico de seguridad:** `POST /api/crm/auth/register-owner` solo tiene rate-limit (5 req/min), sin token de administrador ni whitelist de IPs — cualquiera puede crear un tenant+owner en producción.
- La gestión de sesiones SQLAlchemy usa `NullPool` + cierre manual en `finally` (patrón correcto para serverless/containers), pero no hay `scoped_session` en endpoints: algunos bloques de admin no hacen `session.rollback()` en el `except`.
- La única migración explícita es un script ad-hoc (`migrations/001_add_indices_and_constraints.py`); el esquema principal se crea con `create_all()` en `runtime_bootstrap` — sin Alembic, sin versionado de esquema.

---

## 1. app/main.py — entrypoint

### Blueprints registrados

| Nombre | Prefijo URL | Archivo fuente |
|--------|-------------|----------------|
| `webhooks` | `/webhooks` | `app/api/routes.py` |
| `admin` | `/api/admin` | `app/api/admin_routes.py` |
| `ferreteria_admin_api` | `/api/admin/ferreteria` | `app/api/ferreteria_admin_routes.py` |
| `ferreteria_training_api` | `/api/admin/ferreteria` | `app/api/ferreteria_training_routes.py` |
| `channels` | `/webhooks` | `app/api/channels.py` |
| `public_api` | `/api` | `app/api/public_routes.py` |
| `storefront_tenant_bp` | (sin prefijo — `/api/t/<slug>/...`) | `bot_sales/connectors/storefront_tenant_api.py` |
| `crm_api` | `/api/crm` | `app/crm/api/routes.py` |
| `console_api` | `/api/console` | `app/api/console_routes.py` |
| `crm_ui` | (sin prefijo — `/crm/...`) | `app/crm/ui/routes.py` |
| `ferreteria_admin_ui` | (sin prefijo) | `app/ui/ferreteria_admin_routes.py` |
| `ferreteria_training_ui` | (sin prefijo) | `app/ui/ferreteria_training_routes.py` |

**Nota:** `ferreteria_admin_api` y `ferreteria_training_api` comparten el mismo `url_prefix='/api/admin/ferreteria'`. No hay colisión hoy porque sus paths internos son diferentes (`/quotes/...` vs `/training/...`), pero esto es frágil si se agregan rutas en ambos blueprints con el mismo nombre.

### Schedulers / background jobs

Dos schedulers se arrancan en el mismo proceso web (`create_app`), usando threads daemon:

| Scheduler | Frecuencia | Función |
|-----------|-----------|---------|
| `start_mep_rate_scheduler()` | Configurable (envar) | Refresco periódico del tipo de cambio MEP |
| `start_holds_scheduler()` | Cada 60 segundos (lock-based) | Libera reservas de stock expiradas |

Ambos usan un patrón de lock en DB para evitar doble-disparo si hay múltiples instancias. El `app/worker/scheduler.py` (proceso separado) duplica el job de `expire_holds` y agrega `stock_sync` — hay riesgo de doble-ejecución si ambos corren en paralelo.

### Middlewares / hooks

- `@app.before_request`: inyecta `X-Request-Id` (o genera uno) en `structlog.contextvars` y en `g.request_id`. No hace nada de auth global.
- `flask_cors.CORS`: configurado en `create_app` con lógica de 4 ramas según `CORS_ORIGINS`. En producción sin `CORS_ORIGINS` configurado, cae a wildcard con log de warning — no falla duro.

### Comportamiento de fallback / legacy

- `ALLOW_LEGACY_FALLBACK` en producción lanza `ValueError` y mata el startup (correcto).
- El endpoint `POST /api/chat` intenta primero el bot multi-tenant; si falla, cae silenciosamente a `BotCore.reply_with_meta()` (fallback legacy), logueando solo a nivel `WARNING`.
- El static server sirve `/website/index.html` por defecto; si no existe, responde `"Lumen V2 API Running"`.

---

## 2. Endpoints expuestos (mapa completo)

### Rutas directas en main.py

| Método | Path | Auth requerida |
|--------|------|----------------|
| GET | `/health` | No |
| GET | `/diag/db` | `X-Admin-Token` (hmac) |
| GET | `/diag/runtime-integrity` | `X-Admin-Token` (hmac) |
| GET | `/diag/request-ip` | `X-Admin-Token` (hmac) |
| GET | `/catalog` | No (redirect a `/api/catalog`) |
| GET | `/` | No |
| GET | `/<path:path>` | No (static files) |

### Blueprint: webhooks (`/webhooks`)

| Método | Path | Auth requerida |
|--------|------|----------------|
| POST | `/webhooks/mp` | `verify_mp_signature` (HMAC-SHA256 + ts) |
| GET | `/webhooks/meta` | `hub.verify_token` (hmac) |
| POST | `/webhooks/meta` | `verify_meta_signature` (X-Hub-Signature-256) |

### Blueprint: admin (`/api/admin`)

| Método | Path | Auth requerida |
|--------|------|----------------|
| POST | `/api/admin/cache/clear` | `admin_required` (X-Admin-Token) |
| POST | `/api/admin/idempotency/cleanup` | `admin_required` |
| POST | `/api/admin/stock/sync-sheet` | `admin_required` |
| POST | `/api/admin/products/fix-model-names` | `admin_required` |

### Blueprint: ferreteria_admin_api (`/api/admin/ferreteria`)

| Método | Path | Auth requerida |
|--------|------|----------------|
| GET | `/api/admin/ferreteria/quotes` | `admin_required` |
| GET | `/api/admin/ferreteria/quotes/<id>` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/status` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/claim` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/note` | `admin_required` |
| GET | `/api/admin/ferreteria/unresolved-terms` | `admin_required` |
| POST | `/api/admin/ferreteria/unresolved-terms/<id>/review` | `admin_required` |
| GET | `/api/admin/ferreteria/knowledge/<domain>` | `admin_required` |
| PUT | `/api/admin/ferreteria/knowledge/<domain>` | `admin_required` |
| POST | `/api/admin/ferreteria/knowledge/reload` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/automation/evaluate` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/automation/send` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/automation/block` | `admin_required` |
| POST | `/api/admin/ferreteria/quotes/<id>/automation/reset` | `admin_required` |

### Blueprint: ferreteria_training_api (`/api/admin/ferreteria`)

Todos los endpoints tienen `@admin_required`. Paths internos: `/training/sessions`, `/training/cases`, `/training/reviews`, `/training/suggestions`, `/training/usage`, `/training/impact`, `/training/unresolved-terms/suggest` — total 18 endpoints.

### Blueprint: public_api (`/api`)

| Método | Path | Auth requerida |
|--------|------|----------------|
| POST | `/api/stock/batch` | No (requiere tenant_id en body) |
| POST | `/api/chat` | No (rate-limit por IP, 60 req/min) |
| GET | `/api/storefront` | No |
| GET | `/api/health` | No |
| GET | `/api/catalog` | No |
| GET | `/api/diag` | `X-Admin-Token` (hmac) |
| GET | `/api/products` | No (alias de /api/catalog) |
| GET | `/api/catalog/grouped` | No |
| GET | `/api/catalog/variant` | No |
| GET | `/api/catalog/detail` | No |

### Blueprint: crm_api (`/api/crm`) — selección principal

| Método | Path | Auth requerida |
|--------|------|----------------|
| POST | `/api/crm/auth/login` | No (rate-limited 10/min) |
| POST | `/api/crm/auth/register-owner` | No (rate-limited 5/min) |
| POST | `/api/crm/messages/webhook` | Webhook secret (token o HMAC, por tenant) |
| POST | `/api/crm/messages/inbound` | Webhook secret (alias del anterior) |
| GET/POST | `/api/crm/contacts` | JWT + CONTACTS_READ / CONTACTS_WRITE |
| PATCH/DELETE | `/api/crm/contacts/<id>` | JWT + CONTACTS_WRITE / CONTACTS_DELETE |
| GET/POST/PATCH | `/api/crm/deals`, `/api/crm/deals/<id>` | JWT + DEALS_READ / DEALS_WRITE |
| GET/POST/PATCH | `/api/crm/tasks`, bulk-* | JWT + TASKS_READ / TASKS_WRITE / TASKS_BULK |
| GET/POST/PATCH | `/api/crm/automations`, evaluate, runs | JWT + (no permission check en evaluate) |
| GET/POST | `/api/crm/segments`, export.csv | JWT + CONTACTS_READ / EXPORTS_RUN |
| GET/POST | `/api/crm/conversations`, messages | JWT + CONVERSATIONS_READ / MESSAGES_WRITE |
| GET/POST/PATCH | `/api/crm/settings`, pipeline-stages, scoring-rules | JWT + SETTINGS_READ / SETTINGS_WRITE |
| GET/POST/PATCH | `/api/crm/users`, `/api/crm/users/<id>` | JWT + (sin permission explícita visible en grep) |
| GET/POST/PATCH | `/api/crm/playbooks` | JWT + (sin permission explícita visible en grep) |
| GET/PUT | `/api/crm/assignment/rules` | JWT |
| POST | `/api/crm/assignment/assign-lead` | JWT |
| GET/POST | `/api/crm/sla/*` | JWT |
| GET/POST/PATCH | `/api/crm/whatsapp/templates/*` | JWT |
| POST | `/api/crm/inventory/signals` | JWT |
| GET | `/api/crm/reports/clv`, dashboard, ab-variants | JWT + REPORTS_READ |
| GET | `/api/crm/orders` | JWT + DEALS_READ |

### Blueprint: console_api (`/api/console`)

Todos los endpoints tienen `@crm_auth_required + @permission_required(...)`. Paths: `/home`, `/search`, `/conversations`, `/conversation/<id>`, `/contacts/<id>`, `/deals`, `/deals/<id>/stage`, `/tasks`, `/tasks/bulk-*`, `/watchdog/health`, `/watchdog/alerts`, `/watchdog/actions/<action>`, `/reports/kpi`, `/reports/ab-variants`, `/settings/tenant` — total 18 endpoints.

### Blueprint: crm_ui (sin prefijo)

Páginas HTML: `/crm/login`, `/crm`, `/crm/dashboard`, `/crm/contacts`, `/crm/contacts/<id>`, `/crm/deals`, `/crm/tasks`, `/crm/conversations`, `/crm/automations`, `/crm/reports`, `/crm/settings`. Sin auth en el blueprint (la auth se maneja client-side con JWT en el SPA).

---

## 3. app/core/config.py

### Variables de entorno requeridas

Sin valor explícito, el sistema usa defaults inseguros pero **no falla en startup** (excepto en producción donde hay validaciones extras):

| Variable | Propósito |
|----------|-----------|
| `DATABASE_URL` | Conexión a base de datos (default: sqlite local) |
| `SECRET_KEY` | Clave Flask (default: `dev-secret-key-change-in-production`) |
| `OPENAI_API_KEY` | LLM principal |
| `META_VERIFY_TOKEN` | Validación handshake webhook Meta |
| `META_ACCESS_TOKEN` | Envío de mensajes Meta Cloud API |
| `MERCADOPAGO_ACCESS_TOKEN` | Pagos MP |
| `MERCADOPAGO_WEBHOOK_SECRET` | Firma webhooks MP |
| `ADMIN_TOKEN` | Auth endpoints `/api/admin/*` y `/diag/*` |
| `CRM_JWT_SECRET` | Firma tokens JWT del CRM |
| `CRM_WEBHOOK_SECRET` | Firma webhooks entrantes al CRM |

### Variables opcionales con defaults

| Variable | Default |
|----------|---------|
| `PORT` | 8000 |
| `ENVIRONMENT` | `development` |
| `LOG_LEVEL` | `INFO` |
| `OPENAI_MODEL` | `gpt-4o` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `HOLD_MINUTES` | 15 |
| `PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE` | 60 |
| `CRM_JWT_TTL_MINUTES` | 720 (12 horas) |
| `CORS_ORIGINS` | vacío (equivale a wildcard en producción) |
| `WHATSAPP_PROVIDER` | auto-detect (`meta`, `twilio` o `mock`) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | vacío (sync desactivado) |

### Validaciones de producción (raises, asserts, sys.exit)

- `raise ValueError` si `DATABASE_URL` no está configurada explícitamente en producción.
- `raise ValueError` si `SECRET_KEY` es el valor por defecto inseguro en producción.
- `raise ValueError` si `ALLOW_LEGACY_FALLBACK` está activo en producción.
- `sys.exit(1)` en `app/db/session.py` si `DATABASE_URL` es vacío.
- Warnings (no raises) para: `ADMIN_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET`, `META_VERIFY_TOKEN`, `CRM_WEBHOOK_SECRET` inseguros, CORS wildcard en producción, `WHATSAPP_PROVIDER=mock`, nombre de servicio Railway incorrecto.

### Comportamiento ALLOW_LEGACY_FALLBACK

Sólo existe como guardrail negativo: si está activo en producción, el startup explota. No hay código que lo use para activar funcionalidad alternativa — es una trampa de seguridad.

### Clase de valores inseguros bloqueados (`UNSAFE_SECRET_VALUES`)

El sistema rechaza: `""`, `"REDACTED"`, `"MOCK_SECRET"`, `"change-me"`, `"changeme"`, `"my_verify_token"`, `"dev-secret-key-change-in-production"`. La comparación es case-insensitive.

---

## 4. app/api/

| Archivo | Blueprint | Endpoints (método + path resumido) |
|---------|-----------|-------------------------------------|
| `routes.py` | `webhooks` | POST `/webhooks/mp` |
| `channels.py` | `channels` | GET + POST `/webhooks/meta` |
| `admin_routes.py` | `admin` | POST ×4 (`/cache/clear`, `/idempotency/cleanup`, `/stock/sync-sheet`, `/products/fix-model-names`) |
| `ferreteria_admin_routes.py` | `ferreteria_admin_api` | GET/POST/PUT ×14 (quotes, knowledge, automation, unresolved-terms) |
| `ferreteria_training_routes.py` | `ferreteria_training_api` | GET/POST ×18 (training sessions, cases, reviews, suggestions, impact) |
| `public_routes.py` | `public_api` | GET/POST ×10 (chat, catalog, stock/batch, storefront, health, diag) |
| `console_routes.py` | `console_api` | GET/POST ×18 (home, search, conversations, deals, tasks, watchdog, reports, settings) — **2 700+ líneas** |

---

## 5. app/services/

| Archivo | Clase/función principal | Responsabilidad | Duplica bot_sales/services/? |
|---------|------------------------|-----------------|-------------------------------|
| `bot_core.py` | `SimpleFallbackBot`, `BotCore` | Orquestador legacy fallback; wrapper tenant-aware | No |
| `catalog_service.py` | `CatalogService` | Lee catálogo de Google Sheets con caché en memoria | Funcional diferente de `CatalogSearchService` en bot_sales (semántica vs lectura raw) |
| `channels/whatsapp_meta.py` | `WhatsAppMeta` | Handler de mensajes entrantes WhatsApp Cloud API | No |
| `channels/instagram_meta.py` | `InstagramMeta` | Handler de mensajes entrantes Instagram | No |
| `database.py` | (funciones) | Helpers de acceso a DB legacy | No |
| `email/sendgrid_client.py` | `SendGridClient` | Envío de emails transaccionales | No |
| `exceptions.py` | Excepciones custom | Excepciones del dominio | No |
| `fallback_bot.py` | `FallbackService` | Bot FAQ estático de respaldo | No |
| `holds_scheduler.py` | `start_holds_scheduler` | Thread daemon: libera holds expirados cada 60 s | No (worker/jobs.py tiene la misma lógica para proceso separado) |
| `inventory_service.py` | `InventoryService` | CRUD de inventario con eventos de auditoría | No |
| `media_processor.py` | `MediaProcessor` | Descarga y procesamiento de media WhatsApp | No |
| `mep_rate_scheduler.py` | `start_mep_rate_scheduler` | Thread daemon: refresca tipo de cambio MEP | No |
| `order_service.py` | `OrderService` | Creación y gestión de órdenes con stock-hold | No |
| `payment_service.py` | `PaymentService` | Integración MercadoPago payments | No |
| `runtime_bootstrap.py` | `ensure_runtime_bootstrap` | `create_all()` de modelos al startup | No |
| `runtime_integrity.py` | `evaluate_runtime_integrity` | Diagnóstico de salud del runtime | No |
| `stock_sheet_sync.py` | `StockSheetSync` | Sync de stock desde Google Sheets a DB | Mismo nombre que clase en `app/services/stock_sync.py` — ver sección 11 |
| `stock_sync.py` | `StockSheetSync` | Versión anterior del mismo sync | Duplicado interno — ver sección 11 |

**Nota sobre `stock_sheet_sync.py` vs `stock_sync.py`:** Ambos definen `class StockSheetSync`. El primero es la versión nueva "robusta"; el segundo es legacy. Se importa el nuevo en todos los lugares excepto posiblemente en código legacy no auditado. Esto es un smell activo.

---

## 6. app/db/

### Models encontrados

| Modelo | Tabla | Clave primaria | Notas |
|--------|-------|----------------|-------|
| `Product` | `products` | `(tenant_id, sku)` compuesta | Tiene `available_qty` como property |
| `Order` | `orders` | UUID | FK a products vía OrderItem |
| `OrderItem` | `order_items` | UUID | FK compuesta `(tenant_id, sku)` |
| `Payment` | `payments` | String (MP payment id) | FK a orders |
| `IdempotencyKey` | `idempotency_keys` | String (255) | Tiene `expires_at`, `locked_until` |
| `InventoryEvent` | `inventory_events` | UUID | Audit trail de cambios de stock |
| `Lead` | `leads` | UUID | Handoff a agente humano |

`OrderStatus` es un Python `enum.Enum` mapeado a `SQLEnum`.

Los modelos del CRM son un universo aparte definido en `app/crm/models.py` (861 líneas), usando su propio `CRMBase = declarative_base()`.

### Patrón de sesiones SQLAlchemy

- Engine configurado con `NullPool` — correcto para serverless/containers (no reutiliza conexiones entre requests).
- Pool con `pool_pre_ping=True` y `pool_recycle=300`.
- Se auto-agrega `sslmode=require` si la URL contiene `rlwy.net`.
- El patrón de uso es `session = SessionLocal(); try: ...; finally: session.close()`. Se expone también `ScopedSession = scoped_session(SessionLocal)` pero no se usa en los endpoints auditados.
- **Inconsistencia:** `admin_routes.py` en `fix_model_names` hace `session.rollback()` en except, pero `cleanup_idempotency` no lo hace — si falla la query, la sesión queda sucia hasta el `finally: session.close()`.

### Relación con migraciones (alembic)

Sin Alembic. El esquema se crea con `Base.metadata.create_all()` y `CRMBase.metadata.create_all()` en cada startup (idempotente solo si el esquema no cambia). Hay un script manual en `migrations/001_add_indices_and_constraints.py`. No hay versionado ni rollback de esquema.

---

## 7. app/crm/

**Estado: VIVO — activamente en producción.**

El módulo CRM es la pieza más grande del codebase después del bot. Estructura:

| Subdirectorio | Contenido |
|---------------|-----------|
| `api/routes.py` | ~4 100 líneas, 60+ endpoints REST |
| `api/auth.py` | `crm_auth_required`, `permission_required`, `rate_limited` |
| `models.py` | 861 líneas, todos los modelos CRM con `CRMBase` |
| `db.py` | 3 líneas — solo re-exporta el engine de `app.db.session` |
| `repositories/` | 7 repos: contacts, deals, tasks, automations, users, webhooks, base |
| `services/` | 18 servicios: scoring, SLA, CLV, normalization, playbook, assignment, automation, etc. |
| `jobs/scheduler.py` | 5 jobs: SLA scan (10 min), inactivity automations (5 min), scoring recompute (30 min), daily rollups (00:10), AB autopromote (00:20) |
| `ui/routes.py` | 11 rutas de páginas HTML para el SPA del CRM |
| `integrations/` | `interfaces.py` + `stubs.py` — abstracciones para integraciones futuras |
| `domain/` | enums, permissions, schemas Pydantic |

**Integración con main.py:** `crm_api` registrado en `/api/crm`, `crm_ui` sin prefijo (sirve `/crm/*`). El scheduler CRM (`run_crm_scheduler`) **no se llama desde main.py** — debe correr como proceso separado (no está documentado en el entrypoint).

---

## 8. app/mail/ — Estado M0

### Archivos y roles

| Archivo | Rol |
|---------|-----|
| `gmail_client.py` | OAuth2 installed-app flow; refresh automático; `get_service()` → Gmail API resource |
| `mail_reader.py` | `MailReader`: lista unread, fetch full mail con parsing MIME y strip de quoted-reply |
| `types.py` | `MailMetadata` (dataclass), `ParsedMail` (dataclass) |
| `__main__.py` | CLI: `python -m app.mail login|list|show|logout` |
| `__init__.py` | Vacío |

### Qué está implementado (M0)

- Autenticación OAuth2 con token persistido en `token.json`.
- Lectura de inbox (`list_unread`, `get_full_mail`).
- Parsing completo: headers, body multipart, HTML→texto, strip de quoted-reply, conteo de attachments.
- CLI funcional para uso manual.
- Scopes correctos: `gmail.readonly` + `gmail.modify` (para marcar como leído en M1+).

### Qué falta para M1 (stubs, TODOs, NotImplemented)

- No hay endpoint Flask que exponga `/api/mail/*` — el módulo es completamente standalone.
- No hay `mark_as_read()` implementado (el scope `gmail.modify` está declarado pero no usado).
- No hay `send_reply()` ni `send_email()`.
- No hay integración con el CRM (no crea contactos ni notas desde emails entrantes).
- `credentials.json` se busca por path relativo — problemático en producción containerizada.
- Los dos `pass` en `gmail_client.py` son estructuralmente correctos (excepción vacía intencional para re-flujo de OAuth), no son stubs.

### Recomendaciones

1. Mover `credentials.json` y `token.json` a paths configurables por envar.
2. Implementar `mark_as_read()` antes de M1.
3. Crear `app/mail/routes.py` con un blueprint de mail (GET `/api/mail/inbox`, POST `/api/mail/mark-read/<id>`).
4. El parsing es sólido — se puede usar directamente en M1.

---

## 9. app/worker/

### Tasks / schedulers encontrados

**`app/worker/scheduler.py`** — proceso separado (`python -m app.worker.scheduler` o similar):

| Task | Frecuencia | Descripción |
|------|-----------|-------------|
| `expire_holds_job` | Cada 60 segundos | Libera reservas de stock expiradas |
| `cleanup_idempotency_keys_job` | Diario 03:00 UTC | Elimina idempotency keys con más de 30 días |
| `stock_sync_job` | 15:00 UTC y 23:00 UTC | Sync stock desde Google Sheets a DB (12:00 PM y 20:00 ART) |

**`app/worker/jobs.py`** — implementación de los 3 jobs anteriores.

**Problema detectado:** `expire_holds_job` existe tanto en `app/worker/jobs.py` (worker process) como en `app/services/holds_scheduler.py` (thread en web process). Si ambos corren simultáneamente, hay riesgo de doble-decremento de `reserved_qty`. El scheduler del worker usa `session.query().with_for_update()` en el product, lo que debería prevenir el race en Postgres, pero no en SQLite.

**`app/crm/jobs/scheduler.py`** — proceso CRM separado (no invocado desde main.py):

| Task | Frecuencia | Descripción |
|------|-----------|-------------|
| `_run_sla_scan` | Cada 10 min | Detecta breaches de SLA |
| `_run_inactivity_automations` | Cada 5 min | Dispara automatizaciones por inactividad |
| `_run_scoring_recompute` | Cada 30 min | Recalcula scores de deals/contacts |
| `_run_daily_rollups` | 00:10 diario | Métricas de resumen diario |
| `_run_ab_autopromote` | 00:20 diario | Promueve variantes AB con mejor performance |

---

## 10. app/bot/

**¿Existe `app/bot/bot.py`?** NO — el bot principal del sistema vive en `bot_sales/bot.py` (`class SalesBot`).

`app/bot/` contiene módulos auxiliares que mayormente **duplican** o **preceden** a los de `bot_sales/`:

| Archivo en app/bot/ | Estado | Relación con bot_sales/ |
|---------------------|--------|------------------------|
| `bot_gemini.py` | Experimental — usa GeminiClient de `app/bot/core/` | Sin equivalente en bot_sales/ (bot_sales usa OpenAI) |
| `analytics.py` | Clase `Analytics` idéntica en nombre a `bot_sales/analytics.py` | Posible divergencia |
| `analytics_engine.py` | Solo en app/bot/ | Sin equivalente en bot_sales/ |
| `bundles.py` | Clase `BundleManager` | Duplicado de `bot_sales/bundles.py` |
| `config.py` | Clase `Config` | Duplicado de `bot_sales/config.py` (con diferencias en defaults) |
| `faq.py` | Clase `FAQHandler` | Duplicado de `bot_sales/faq.py` |
| `recommendations.py` | Clase `RecommendationEngine` | Duplicado de `bot_sales/recommendations.py` |
| Subdirectorios: `connectors/`, `experiments/`, `i18n/`, `integrations/`, `intelligence/`, `maintenance/`, `multimedia/`, `security/` | Mayormente vivos pero no integrados al runtime principal | Sin equivalente directo en bot_sales/ |

**Conclusión:** `app/bot/` es un experimento de refactoring que nunca se completó. El runtime de producción usa `bot_sales/bot.py`. Los módulos en `app/bot/` no son llamados desde el entrypoint principal excepto `bot_gemini.py` (experimental). La mayoría son código muerto potencial.

---

## 11. Duplicación app/ vs bot_sales/

No hay colisión de nombres de archivo entre `app/services/` y `bot_sales/services/` (las responsabilidades son complementarias, no iguales). La duplicación real está en otro nivel:

| Módulo en app/ | Módulo en bot_sales/ | Tipo de conflicto |
|----------------|---------------------|-------------------|
| `app/bot/analytics.py` — clase `Analytics` | `bot_sales/analytics.py` — clase `Analytics` | Misma clase, implementaciones que pueden divergir |
| `app/bot/bundles.py` — clase `BundleManager` | `bot_sales/bundles.py` — clase `BundleManager` | Misma clase, sin garantía de paridad |
| `app/bot/config.py` — clase `Config` | `bot_sales/config.py` — clase `Config` | Misma clase, defaults distintos (`MAX_CONTEXT_MESSAGES`: 10 vs 20) |
| `app/bot/faq.py` — clase `FAQHandler` | `bot_sales/faq.py` — clase `FAQHandler` | Misma clase |
| `app/bot/recommendations.py` — clase `RecommendationEngine` | `bot_sales/recommendations.py` — clase `RecommendationEngine` | Misma clase |
| `app/services/stock_sheet_sync.py` — clase `StockSheetSync` | `app/services/stock_sync.py` — clase `StockSheetSync` | Duplicado interno — mismo nombre, misma responsabilidad |
| `app/services/holds_scheduler.py` — `expire_holds` thread | `app/worker/jobs.py` — `expire_holds_job` function | Misma lógica de negocio ejecutada en dos procesos distintos |

---

## 12. Endpoint security audit

### Endpoints protegidos

| Path | Mecanismo de auth |
|------|-------------------|
| `/api/admin/*` (4 endpoints) | `admin_required`: X-Admin-Token + `hmac.compare_digest` |
| `/api/admin/ferreteria/*` (14 endpoints) | `admin_required` |
| `/api/admin/ferreteria/training/*` (18 endpoints) | `admin_required` |
| `/diag/db`, `/diag/runtime-integrity`, `/diag/request-ip` | `_diag_authorized`: X-Admin-Token + `hmac.compare_digest` |
| `/api/diag` | `_diag_authorized` (misma lógica, duplicada en `public_routes.py`) |
| `/webhooks/mp` | `verify_mp_signature`: HMAC-SHA256 + timestamp staleness check |
| `/webhooks/meta` (POST) | `verify_meta_signature`: X-Hub-Signature-256 |
| `/api/crm/messages/webhook`, `/api/crm/messages/inbound` | Webhook secret por tenant (token o HMAC, configurable) + `rate_limited(120/min)` |
| `/api/crm/*` (excepto login, register-owner, webhook/inbound) | JWT Bearer (`crm_auth_required`) + RBAC (`permission_required`) |
| `/api/console/*` | JWT Bearer + RBAC |

### Endpoints SIN protección aparente

| Path | Riesgo estimado |
|------|-----------------|
| `POST /api/crm/auth/register-owner` | **ALTO** — Cualquiera puede crear un tenant nuevo con owner en producción. Solo tiene rate-limit de 5/min. No requiere admin token ni whitelist. |
| `GET /api/catalog`, `/api/catalog/grouped`, `/api/catalog/variant`, `/api/catalog/detail` | **BAJO** — Datos públicos de catálogo, por diseño. |
| `GET /api/storefront` | **BAJO** — Datos de branding público, por diseño. |
| `POST /api/stock/batch` | **BAJO-MEDIO** — Requiere `tenant_id` válido pero no auth. Expone niveles de stock. |
| `POST /api/chat` | **BAJO** — Rate-limited por IP (60/min). Expone al LLM a input no validado (XSS no aplica por ser API JSON, pero sí prompt injection). |
| `GET /api/crm/auth/login` | **BAJO** — Rate-limited (10/min), es correcto que sea público. |
| `GET /health`, `GET /api/health` | **NINGUNO** — Por diseño. |
| `GET /`, `GET /<path:path>` | **NINGUNO** — Static files. |
| `/crm/*` (UI pages) | **NINGUNO** — Auth es client-side (SPA con JWT). La ruta de login `/crm/login` es correctamente pública. |

### Endpoints con input sin validación obvia

| Path | Input sin validar |
|------|-------------------|
| `POST /api/chat` | `user_message` se pasa directamente al LLM sin sanitización ni límite de longitud explícito |
| `GET /api/catalog/detail` | `slug` se pasa a `slugify()` que es segura, pero se usa en comparación fuzzy (`slug in p_slug or p_slug in slug`) — no es un riesgo de inyección pero sí de false-positives |
| `POST /api/crm/auth/register-owner` | `tenant_id` acepta cualquier string y se usa como PK directamente en DB — si hay tenants preexistentes, devuelve 409, pero el flujo de creación de tenant si no existe no tiene validación de formato |
| `PUT /api/admin/ferreteria/knowledge/<domain>` | `domain` es un path param libre; el handler lo usa para determinar qué YAML reescribir — depende de la implementación interna de `KnowledgeLoader` |

---

## 13. Top 10 oportunidades de mejora

1. **[CRÍTICO] Proteger `POST /api/crm/auth/register-owner` con admin token.** El endpoint permite crear tenants desde internet sin autenticación. Opciones: requerir `X-Admin-Token`, o una clave de invitación de un solo uso, o deshabilitar en producción y crear tenants solo por CLI.

2. **[ALTO] Consolidar los dos schedulers de `expire_holds`.** El thread en `holds_scheduler.py` (web process) y el job en `worker/jobs.py` (worker process) implementan la misma lógica. Estandarizar a uno solo con lock en DB para multi-instancia, eliminar el otro.

3. **[ALTO] Adoptar Alembic para versionado de esquema.** `create_all()` en startup es correcto para desarrollo pero en producción no aplica ALTER TABLE. Cada cambio de esquema requiere intervención manual. Con Alembic se gana rollback, auditoría y CI/CD seguro.

4. **[ALTO] Limpiar `app/bot/` o promoverlo.** Los 5 módulos duplicados (`analytics`, `bundles`, `config`, `faq`, `recommendations`) respecto a `bot_sales/` son una bomba de tiempo: un fix en uno no se propaga al otro. Decisión: eliminar `app/bot/` y dejarlo en `bot_sales/`, o mover los módulos compartidos a un `app/shared/` y hacer que ambos importen desde ahí.

5. **[ALTO] Eliminar `app/services/stock_sync.py`.** Dos clases `StockSheetSync` en el mismo package. La versión nueva (`stock_sheet_sync.py`) ya reemplaza la vieja. Eliminar la legacy antes de que alguien la importe por error.

6. **[MEDIO] Configurar `CORS_ORIGINS` explícitamente en producción.** El fallback actual (wildcard sin credentials) es tolerado pero no recomendado. Documentar el envar en el Readme de despliegue y agregar una validación dura en `is_production`.

7. **[MEDIO] Registrar el scheduler CRM en el entrypoint.** `run_crm_scheduler()` en `app/crm/jobs/scheduler.py` no se llama desde ningún lugar en el código auditado. Si el proceso separado no se está iniciando, los 5 jobs CRM (SLA, scoring, automations) no corren.

8. **[MEDIO] Integrar `app/mail/` con Flask para M1.** El módulo es sólido a nivel M0 pero está completamente aislado. Crear un blueprint `mail_api` con endpoints mínimos y un job/worker que procese el inbox periódicamente y alimente el CRM.

9. **[BAJO] Unificar el helper `_diag_authorized` duplicado.** La función aparece copiada en `app/main.py` y en `app/api/public_routes.py` con lógica idéntica. Mover a `app/core/security.py` y reusar.

10. **[BAJO] Agregar `session.rollback()` en `cleanup_idempotency` de `admin_routes.py`.** El bloque `except` está ausente. En caso de error de DB, la sesión queda en estado sucio hasta el `finally`. Seguir el mismo patrón que `expire_holds_job`.

---

## 14. Dudas para Julian

1. **¿El `run_crm_scheduler()` está corriendo como proceso separado en Railway?** No está en `main.py` ni en ningún `Procfile` auditado. Si no corre, SLA, scoring y automations están silenciosamente muertos.

2. **¿`app/bot/bot_gemini.py` (`SalesBotGemini`) está en uso en algún tenant?** Importa desde `app/bot/core/gemini` pero el runtime multi-tenant usa `bot_sales/bot.py` (`SalesBot` con OpenAI). ¿Es un experimento abandonado o hay un tenant Gemini activo?

3. **¿`app/services/stock_sync.py` (la versión legacy de `StockSheetSync`) puede eliminarse?** Necesito confirmar que ningún código externo al `app/` auditado la importe.

4. **`POST /api/crm/auth/register-owner` sin admin auth — ¿es intencional?** Por ejemplo, si el flujo de onboarding de nuevos clientes pasa por esta ruta desde un frontend público, el rate-limit de 5/min puede ser insuficiente. Si es solo para uso interno, debería requerir `X-Admin-Token`.

5. **¿Hay un `Procfile` o `railway.toml` que defina cuántos procesos corren?** El análisis muestra 3 procesos posibles: web (`app/main.py`), worker (`app/worker/scheduler.py`), crm-scheduler (`app/crm/jobs/scheduler.py`). Necesito saber cuál de los tres está activo en Railway.

6. **`app/services/holds_scheduler.py` (thread en web) vs `app/worker/jobs.py` (proceso worker) — ¿los dos están activos en producción?** Si ambos corren, hay riesgo teórico de doble-decremento de `reserved_qty` en ventanas de <1 segundo.

7. **¿Hay planes para `app/mail/` más allá del CLI?** La infraestructura de M0 está bien hecha. Si el objetivo es M1 (procesamiento automático de emails entrantes), conviene definir el trigger: ¿polling en el worker, o push via Gmail pub/sub?
