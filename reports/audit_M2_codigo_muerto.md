# Audit M2 — Código muerto cross-repo

**HEAD:** 9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb
**Fecha audit:** 2026-05-09
**Total archivos .py analizados:** 443 (excluye `.venv/`, `.venv-test/`, `.claude/`, `__pycache__/`)

## Resumen ejecutivo

- LOC eliminables con confianza ALTA: 10121
- LOC eliminables con confianza MEDIA: 5596
- LOC eliminables con confianza BAJA: ~450
- **Total LOC eliminables estimados:** ~16167
- Archivos completos a eliminar: 71 (41 ALTA + 30 MEDIA)
- Funciones huérfanas dentro de archivos vivos: 10

**Hallazgo sorprendente:** La carpeta `app/bot/integrations/` contiene 9 archivos Slack (slack_alerts, slack_analytics, slack_app_home, slack_files, slack_modals, slack_product_cards, slack_reports, slack_threading, slack_approvals) que son duplicados casi exactos de sus pares en `bot_sales/integrations/` — ambas copias tienen 0 usos externos. Son 6344 LOC de código Slack muerto en dos namespaces paralelos.

**Hallazgo secundario:** `Planning/` (directorio en `.gitignore`, no trackeado) contiene 9 archivos Python con 1610 LOC que son snapshots desactualizados de `bot_sales/planning/`. No están en git y no corren en producción.

---

## 1. Archivos con 0 usos no-test

| Path | LOC | Última modificación | Categoría | Nota |
|------|-----|---------------------|-----------|------|
| `app/bot/analytics_engine.py` | 185 | 2026-04-08 | LEGACY | Clase `AnalyticsEngine` con métricas. El `app/bot/` original fue superado por `bot_sales/`. 0 imports externos fuera de la propia carpeta. |
| `app/bot/connectors/cli_gemini.py` | 101 | 2026-04-08 | LEGACY | CLI para `SalesBotGemini`. Solo `cli_gemini.py` usa `app/bot/bot_gemini.py`; ningún entry point lo invoca. |
| `app/bot/connectors/webchat.py` | 255 | 2026-04-08 | LEGACY | `WebChatAPI` Flask duplicada. La webchat productiva corre en `bot_sales/connectors/webchat.py`. |
| `app/bot/integrations/slack_alerts.py` | 295 | 2026-04-08 | LEGACY | Duplicado de `bot_sales/integrations/slack_alerts.py`. Solo difiere en el prefijo del import interno. |
| `app/bot/integrations/slack_analytics.py` | 303 | 2026-04-08 | LEGACY | Duplicado de `bot_sales/integrations/slack_analytics.py`. |
| `app/bot/integrations/slack_app_home.py` | 495 | 2026-04-08 | LEGACY | Duplicado. El más grande del grupo Slack. |
| `app/bot/integrations/slack_files.py` | 235 | 2026-04-08 | LEGACY | Duplicado. |
| `app/bot/integrations/slack_modals.py` | 417 | 2026-04-08 | LEGACY | Duplicado. |
| `app/bot/integrations/slack_product_cards.py` | 329 | 2026-04-08 | LEGACY | Duplicado. |
| `app/bot/integrations/slack_reports.py` | 220 | 2026-04-08 | LEGACY | Duplicado. |
| `app/bot/integrations/slack_threading.py` | 266 | 2026-04-08 | LEGACY | Duplicado. |
| `app/bot/intelligence/image_search.py` | 43 | 2026-04-08 | DEPRECATED | Placeholder explícito (`status: not_implemented`). Cuerpo vacío con TODOs. |
| `app/bot/intelligence/learning.py` | 395 | 2026-04-08 | LEGACY | Sistema de feedback SQLite. Duplicado de `bot_sales/intelligence/learning.py`. |
| `app/bot/security/encryption.py` | 214 | 2026-04-08 | LEGACY | Módulo PII con `cryptography.fernet`. Duplicado casi idéntico de `bot_sales/security/encryption.py`. |
| `app/crm/integrations/stubs.py` | 36 | 2026-04-08 | ACCIDENTAL | Stubs de `WhatsApp/Email/Payment/CRM` nunca importados fuera del módulo. Las interfaces reales están en `app/crm/integrations/interfaces.py`. |
| `app/mail/__main__.py` | 117 | 2026-05-07 | NO_PUEDO_DECIR | CLI para `python -m app.mail login/list-unread`. Reciente (07-may). Es un entrypoint manual, no importado por otros módulos. Ver sección 7. |
| `app/services/email/sendgrid_client.py` | 25 | 2026-04-08 | ACCIDENTAL | `EmailService` con SendGrid. Nunca importado. El sistema de mail usa `app/mail/gmail_client.py`. |
| `bot_cli.py` | 8 | 2026-04-08 | ACCIDENTAL | Wrapper de 8 líneas que llama `bot_sales.connectors.cli:main`. No hay ningún caller. El CLI se llama directamente desde `bot_sales/connectors/cli.py`. |
| `bot_sales/connectors/webchat.py` | 260 | 2026-04-10 | EXPERIMENT | WebChat API Flask. Ligeramente distinta de `app/bot/connectors/webchat.py` (método `process_message` con kwargs extras). Nadie la importa. |
| `bot_sales/core/async_ops.py` | 159 | 2026-04-08 | DEPRECATED | Wrappers async (`run_in_background`, `run_async`). El bot usa asyncio nativo. 0 callers. |
| `bot_sales/core/error_recovery.py` | 205 | 2026-05-06 | EXPERIMENT | Clase `ErrorRecovery` con estrategias de recuperación. Modificada reciente (06-may). 0 importaciones. |
| `bot_sales/core/new_functions.py` | 73 | 2026-04-08 | ACCIDENTAL | Funciones sueltas `comparar_productos`, `validar_datos_cliente`, `detectar_fraude` — son un draft de métodos que YA existen en `BusinessLogic` (business_logic.py líneas 902–950). Archivo con docstring "Append these to business_logic.py". Nunca appendeado. |
| `bot_sales/core/performance.py` | 291 | 2026-04-08 | DEPRECATED | Decoradores `async_timed`, `cache_with_timeout`, `lazy_property`. 0 callers. Superpuesto por `bot_sales/core/monitoring.py` que sí se usa. |
| `bot_sales/integrations/slack_alerts.py` | 295 | 2026-04-08 | LEGACY | Par muerto en `bot_sales/` del duplicado Slack. Mismo código, namespace distinto. |
| `bot_sales/integrations/slack_analytics.py` | 303 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/integrations/slack_app_home.py` | 495 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/integrations/slack_files.py` | 235 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/integrations/slack_modals.py` | 417 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/integrations/slack_product_cards.py` | 329 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/integrations/slack_reports.py` | 220 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/integrations/slack_threading.py` | 266 | 2026-04-08 | LEGACY | Ídem. |
| `bot_sales/intelligence/image_search.py` | 43 | 2026-04-08 | DEPRECATED | Placeholder idéntico al de `app/bot/intelligence/image_search.py`. |
| `bot_sales/intelligence/learning.py` | 395 | 2026-04-08 | LEGACY | FeedbackCollector SQLite. Igual a `app/bot/intelligence/learning.py`. |
| `bot_sales/security/encryption.py` | 214 | 2026-04-08 | LEGACY | PIIEncryption. Igual a `app/bot/security/encryption.py`. 0 callers en toda la base. |
| `examples/demo_automated_v2.py` | 203 | 2026-04-08 | EXPERIMENT | Demo automático v2. Nadie lo invoca. |
| `examples/demo_automated.py` | 264 | 2026-04-08 | EXPERIMENT | Demo automático v1. |
| `examples/demo_cli_offline.py` | 765 | 2026-04-08 | EXPERIMENT | El más grande de los ejemplos (765 LOC). Demo offline con mock data. |
| `examples/demo_final.py` | 146 | 2026-04-08 | EXPERIMENT | Demo final de presentación. |
| `examples/demo_gemini.py` | 212 | 2026-04-08 | EXPERIMENT | **IMPORT ROTO**: `from bot_sales.bot_gemini import SalesBotGemini` — `bot_sales/bot_gemini.py` no existe. |
| `examples/demo_simulado.py` | 329 | 2026-04-08 | EXPERIMENT | Demo simulado. |
| `experiments/ollama/demo_ollama.py` | 338 | 2026-04-08 | EXPERIMENT | Demo con Ollama local. |
| `generate_pptx.py` | 86 | 2026-04-08 | ACCIDENTAL | Script para generar PPTX. Reside en la raíz pero sin callers. |
| `gunicorn.conf.py` | 6 | 2026-04-12 | ACCIDENTAL | Archivo gunicorn estándar (bind, workers, timeout) pero el CMD en `Dockerfile` y `railway.json` pasa los flags directamente como args a gunicorn. No se usa. |
| `maintenance/rules.py` | 47 | 2026-04-08 | LEGACY | Función `evaluate_status()` reemplazada por `compute_outcome()` en `maintenance/runner.py`. Ningún módulo la importa. |
| `migrations/001_add_indices_and_constraints.py` | 174 | 2026-04-08 | LEGACY | Migración SQLite standalone. No hay runner de migraciones. Nunca importado. |

**Scripts standalone (0 imports externos, pero son herramientas CLI):** Ver sección 5.

---

## 2. Zonas calientes — análisis detallado

### app/bot/

**Observación clave:** La carpeta `app/bot/` en su conjunto es un "segundo bot" que quedó freezeado en el estado del commit inicial (2026-04-08). El stack productivo migró completamente a `bot_sales/`. Los archivos con "usos" en esta carpeta se auto-referencian (imports internos).

Archivos muertos con 0 usos externos:
- `app/bot/analytics_engine.py` — 185 LOC, clase AnalyticsEngine completa. LEGACY.
- `app/bot/connectors/cli_gemini.py` — 101 LOC. LEGACY.
- `app/bot/connectors/webchat.py` — 255 LOC. LEGACY.
- `app/bot/integrations/slack_alerts.py` — 295 LOC. LEGACY.
- `app/bot/integrations/slack_analytics.py` — 303 LOC. LEGACY.
- `app/bot/integrations/slack_app_home.py` — 495 LOC. LEGACY.
- `app/bot/integrations/slack_files.py` — 235 LOC. LEGACY.
- `app/bot/integrations/slack_modals.py` — 417 LOC. LEGACY.
- `app/bot/integrations/slack_product_cards.py` — 329 LOC. LEGACY.
- `app/bot/integrations/slack_reports.py` — 220 LOC. LEGACY.
- `app/bot/integrations/slack_threading.py` — 266 LOC. LEGACY.
- `app/bot/intelligence/image_search.py` — 43 LOC. DEPRECATED (placeholder).
- `app/bot/intelligence/learning.py` — 395 LOC. LEGACY.
- `app/bot/security/encryption.py` — 214 LOC. LEGACY.

Subtotal zona app/bot/: **3773 LOC**, 14 archivos.

### bot_sales/core/

- `bot_sales/core/async_ops.py` — 159 LOC. DEPRECATED. Wrappers async no usados.
- `bot_sales/core/error_recovery.py` — 205 LOC. EXPERIMENT. Reciente (06-may), 0 callers.
- `bot_sales/core/new_functions.py` — 73 LOC. ACCIDENTAL. Draft no integrado.
- `bot_sales/core/performance.py` — 291 LOC. DEPRECATED. Superpuesto por `monitoring.py`.

Subtotal: **728 LOC**, 4 archivos.

### bot_sales/intelligence/

- `bot_sales/intelligence/image_search.py` — 43 LOC. DEPRECATED. Placeholder explícito.
- `bot_sales/intelligence/learning.py` — 395 LOC. LEGACY. Nunca importado desde `bot_sales/`.

Subtotal: **438 LOC**, 2 archivos.

### bot_sales/integrations/

Los 8 archivos Slack son duplicados exactos (salvo prefijo de import) de sus pares en `app/bot/integrations/`. Ninguno tiene callers:
- `slack_alerts.py` (295), `slack_analytics.py` (303), `slack_app_home.py` (495), `slack_files.py` (235), `slack_modals.py` (417), `slack_product_cards.py` (329), `slack_reports.py` (220), `slack_threading.py` (266)

Subtotal: **2560 LOC**, 8 archivos.

Nota: `slack_approvals.py` (318 LOC) y `slack_commands.py` (294 LOC) **sí tienen** callers en `bot_sales/connectors/slack.py` — no son código muerto.

### bot_sales/connectors/

- `bot_sales/connectors/webchat.py` — 260 LOC. EXPERIMENT. Variante ligeramente distinta del webchat de `app/bot/`. 0 importaciones.

### bot_sales/planning/

Todos los archivos de esta carpeta tienen 2+ usos. No hay código muerto aquí.

### bot_sales/training/

Todos los archivos tienen 1+ usos. No hay código muerto aquí.

### bot_sales/multimedia/

- `bot_sales/multimedia/audio_transcriber.py` — 2 usos.
- `bot_sales/multimedia/image_analyzer.py` — 2 usos.
Ambos usados desde `bot_sales/connectors/whatsapp.py`. No son código muerto.

### examples/ / experiments/ / archive/

**examples/** (todos tienen 0 usos):
- `demo_automated_v2.py` (203), `demo_automated.py` (264), `demo_cli_offline.py` (765), `demo_final.py` (146), `demo_gemini.py` (212, import roto), `demo_simulado.py` (329)
Subtotal: **1919 LOC**, 6 archivos. Clasificación: EXPERIMENT.

**experiments/**:
- `experiments/ollama/demo_ollama.py` — 338 LOC. EXPERIMENT.

**archive/**:
- Contiene `archive/powershell/DailyReport_v5.2.ps1` (PowerShell, no .py) y ningún archivo .py propio.

---

## 3. Funciones huérfanas en archivos vivos

| Archivo | Función | LOC función est. | Comentario |
|---------|---------|-----------------|------------|
| `bot_sales/core/business_logic.py` | `comparar_productos()` | ~6 | Delega a `self.product_comparator`. Solo llamada desde `bot_sales/bot.py`. OK. |
| `app/bot/analytics_engine.py` | `AnalyticsEngine` completa | 185 | El **archivo** tiene 0 usos externos — toda la clase es huérfana. LEGACY. |
| `app/bot/analytics_engine.py` | `generate_daily_report()` | ~15 | Función top-level del mismo archivo muerto. |
| `bot_sales/core/performance.py` | `async_timed()` | ~15 | 0 callers en el repo. |
| `bot_sales/core/performance.py` | `cache_with_timeout()` | ~20 | 0 callers en el repo. |
| `bot_sales/core/performance.py` | `lazy_property` | ~12 | 0 callers en el repo. |
| `bot_sales/core/performance.py` | `ConnectionPool` | ~40 | 0 callers en el repo. |
| `maintenance/rules.py` | `evaluate_status()` | 47 | Reemplazada por `compute_outcome()` en `runner.py`. 0 imports. |
| `bot_sales/core/new_functions.py` | `comparar_productos()` (free fn) | ~5 | Duplica el método de `BusinessLogic`. Draft no integrado. |
| `bot_sales/core/new_functions.py` | `validar_datos_cliente()` (free fn) | ~30 | Ídem. |
| `bot_sales/core/new_functions.py` | `detectar_fraude()` (free fn) | ~25 | Ídem. |

---

## 4. Imports rotos o legacy

| Path:Línea | Import problemático | Problema |
|------------|---------------------|---------|
| `examples/demo_gemini.py:15` | `from bot_sales.bot_gemini import SalesBotGemini` | **ROTO**: `bot_sales/bot_gemini.py` no existe. Sí existe `app/bot/bot_gemini.py`. El módulo es `bot_sales.bot`, no `bot_sales.bot_gemini`. |
| `app/bot/integrations/slack_alerts.py:153` | `from app.bot.integrations.email import EmailSender` | **ROTO**: no existe `app/bot/integrations/email.py`. Existe `email_client.py` (clase `EmailClient`, no `EmailSender`). Está dentro de un `try/except` — falla silenciosa en runtime. |
| `bot_sales/integrations/slack_alerts.py:153` | `from bot_sales.integrations.email import EmailSender` | **ROTO**: misma razón. `bot_sales/integrations/email_client.py` tiene `EmailClient`, no `EmailSender`. Silencioso. |
| `wsgi.py:116` | `from wsgi_legacy import create_app as create_legacy_stack_app` | INTENCIONAL: fallback de seguridad. No es un bug, pero `wsgi_legacy.py` es código que debería eliminarse cuando se confirme la estabilidad de `wsgi.py`. |
| `bot_sales/training/demo_bootstrap.py:14` | `from app.api import admin_routes` | FALSO POSITIVO: funciona vía Python namespace packages (no requiere `__init__.py`). OK. |
| `scripts/smoke_training_ui.py:16` | `from app.api import admin_routes` | FALSO POSITIVO: ídem. OK. |

---

## 5. LOC eliminables — totales por confianza

| Confianza | Archivos | LOC | Criterio |
|-----------|----------|-----|---------|
| ALTA | 41 | 10121 | 0 usos no-test, última modificación ≥1 mes, categoría LEGACY/DEPRECATED/ACCIDENTAL confirmada |
| MEDIA | 30 | 5596 | Scripts standalone (no importados por nadie, pueden ser útiles como herramientas manuales) + archivos EXPERIMENT con modificación reciente (`error_recovery.py`) |
| BAJA | 2 | ~450 | `wsgi_legacy.py` (122 LOC, fallback activo en wsgi.py), `app/mail/__main__.py` (117 LOC, CLI reciente) |
| **TOTAL** | **73** | **~16167** | |

**Detalle MEDIA — scripts/**:

Los 27 scripts + `gunicorn.conf.py` (5131 LOC total) no son importados por nadie, pero varios pueden ser herramientas operativas valiosas (`bootstrap_finalprod_crm.py`, `create_tenant.py`, `preflight_production.py`, `seed_database.py`). Se listan como MEDIA porque la decisión de borrarlos es operativa, no técnica.

Scripts recientes (modificados post 2026-04-20): `check_railway_parity.py` (2026-05-03), `demo_test_suite.py` (2026-05-05), `smoke_ferreteria.py` (2026-05-06), `profile_multi_item.py` (2026-05-04), `error_recovery.py` (2026-05-06).

---

## 6. Recomendaciones

### Borrar con confianza (ALTA)

**Grupo Slack duplicado — 6344 LOC total:**
- `app/bot/integrations/slack_alerts.py`
- `app/bot/integrations/slack_analytics.py`
- `app/bot/integrations/slack_app_home.py`
- `app/bot/integrations/slack_files.py`
- `app/bot/integrations/slack_modals.py`
- `app/bot/integrations/slack_product_cards.py`
- `app/bot/integrations/slack_reports.py`
- `app/bot/integrations/slack_threading.py`
- `bot_sales/integrations/slack_alerts.py`
- `bot_sales/integrations/slack_analytics.py`
- `bot_sales/integrations/slack_app_home.py`
- `bot_sales/integrations/slack_files.py`
- `bot_sales/integrations/slack_modals.py`
- `bot_sales/integrations/slack_product_cards.py`
- `bot_sales/integrations/slack_reports.py`
- `bot_sales/integrations/slack_threading.py`

Razón: duplicados exactos con namespaces distintos, 0 callers en ambas copias.

**Resto del grupo app/bot/ legacy:**
- `app/bot/analytics_engine.py` — no hay analytics vivos en `app/bot/`
- `app/bot/connectors/cli_gemini.py` — Gemini pasó a `bot_sales/core/gemini.py`
- `app/bot/connectors/webchat.py` — webchat no está activo en producción
- `app/bot/intelligence/image_search.py` — placeholder explícito
- `app/bot/intelligence/learning.py` — duplicado de `bot_sales/intelligence/learning.py`
- `app/bot/security/encryption.py` — duplicado de `bot_sales/security/encryption.py`

**bot_sales/ orphans:**
- `bot_sales/core/new_functions.py` — draft no integrado, funciones ya existen en `BusinessLogic`
- `bot_sales/core/async_ops.py` — wrappers no usados
- `bot_sales/core/performance.py` — superpuesto por `monitoring.py`
- `bot_sales/intelligence/image_search.py` — placeholder
- `bot_sales/intelligence/learning.py` — 0 callers
- `bot_sales/security/encryption.py` — 0 callers

**Otros:**
- `app/crm/integrations/stubs.py` — stubs no conectados a nada
- `app/services/email/sendgrid_client.py` — SendGrid no configurado, sistema usa Gmail
- `bot_cli.py` — wrapper de 8 líneas sin razón de existir
- `maintenance/rules.py` — función reemplazada
- `generate_pptx.py` — herramienta de pitch, no del bot
- `migrations/001_add_indices_and_constraints.py` — migración sin runner
- `examples/` (todos los 6 archivos) — demos de desarrollo
- `experiments/ollama/demo_ollama.py` — experimento abandonado

### Discutir antes de borrar (MEDIA)

- `bot_sales/core/error_recovery.py` — 205 LOC, **modificada 2026-05-06**. Puede estar en desarrollo activo o ser un draft reciente descartado. Confirmar con Julian.
- `bot_sales/connectors/webchat.py` — Alternativa de WebChat. ¿Hay planes de canal web?
- `gunicorn.conf.py` — El CMD lo ignoró. Si se quiere usarlo, ajustar `Dockerfile`. Si no, eliminar.
- `scripts/bootstrap_finalprod_crm.py` — Setup de producción. ¿Ya se usó? ¿Sigue siendo necesario?
- `scripts/create_tenant.py` — Creación de tenants. Operativamente útil. ¿O ya está reemplazado por la UI?
- `scripts/seed_database.py` — Carga de datos de prueba. Útil en onboarding.
- `scripts/preflight_production.py` — Checklist pre-deploy. Puede ser valioso.
- `scripts/demo_test_suite.py` — 936 LOC, modificado 2026-05-05. ¿Parte del flujo de CI o manual?

### Investigar más (BAJA)

- `wsgi_legacy.py` — Es el fallback de `wsgi.py` (línea 116). Si la estabilidad de `wsgi.py` está confirmada en producción, se puede eliminar. Si no, es una red de seguridad válida.
- `app/mail/__main__.py` — CLI Gmail actualizado el 07-may. Podría ser que Julian lo usa manualmente. Preguntar.
- `app/bot/connectors/webchat.py` vs `bot_sales/connectors/webchat.py` — ¿Alguna vez se activó el canal WebChat? Si no, ambas son eliminables.

---

## 7. Dudas para Julian

1. **`bot_sales/core/error_recovery.py` (205 LOC, 2026-05-06)**: Fue modificada hace 3 días pero tiene 0 callers. ¿Es un work-in-progress o se descartó? Si se usa en el futuro, ¿no debería tener al menos un test o un caller de prueba?

2. **`app/mail/__main__.py` (117 LOC, 2026-05-07)**: Es un CLI Gmail (`python -m app.mail login/list-unread/show/logout`). Está en el módulo `app/mail` que SÍ está trackeado. ¿Lo usás manualmente para debuggear el canal de mail? Si sí, queda; si no, se puede borrar.

3. **Slack duplicado**: `bot_sales/integrations/` tiene todos los archivos Slack pero ninguno es importado por `bot_sales/connectors/slack.py`. El slack connector usa `slack_sdk` directamente. ¿Hubo alguna vez la intención de integrar estos módulos? ¿O son código de otra era del proyecto?

4. **`wsgi_legacy.py`**: ¿Cuánto tiempo lleva el `wsgi.py` nuevo en producción estable? Si hay meses de uptime sin fallback, se puede eliminar el legacy.

5. **Scripts en `scripts/`**: Hay 27 scripts sin ningún caller. ¿Cuáles de estos se ejecutan manualmente en producción (`create_tenant.py`, `seed_database.py`, `preflight_production.py`)? Los demás podrían moverse a un `scripts/archive/` o borrarse.

6. **`Planning/`** (directorio gitignoreado, no trackeado): Contiene 9 archivos Python con 1610 LOC que son snapshots desactualizados de `bot_sales/planning/`. El diff muestra diferencias en lógica de negocio (fallback_reply con "modelo y capacidad" vs "producto y variante"). ¿Por qué está ahí? ¿Se puede borrar del sistema de archivos local?

7. **`app/bot/` en general**: Todo el árbol `app/bot/` parece ser el bot pre-refactor. Las claves de producción (`wsgi.py`, `railway.json`, `Dockerfile`) apuntan a `bot_sales/`. ¿Está `app/bot/` completamente fuera de uso o hay algún feature específico que todavía lo use?
