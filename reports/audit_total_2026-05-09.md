# Audit total del codebase — 2026-05-09

**HEAD analizado:** 9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb
**Generado por:** Claude Code (audit independiente)
**Archivos versionados:** 616

---

## Resumen ejecutivo

- **El .env tiene secretos reales** (OPENAI_API_KEY, ADMIN_PASSWORD, ADMIN_TOKEN, SECRET_KEY) y NO está versionado en git — esto es correcto. Sin embargo el ADMIN_PASSWORD es trivial ("Aristoteles") y ADMIN_TOKEN es predecible ("ferreteria-token-2024"). Antes del go-live, rotar ambos.
- **~8.100 LOC de código muerto confirmado**: 33 archivos en `bot_sales/` y `app/bot/` con 0 importaciones externas. Principalmente: todo `bot_sales/integrations/slack_*` (8 archivos, ~2.700 LOC), sus duplicados exactos en `app/bot/integrations/slack_*`, módulos placeholder vacíos (`image_search.py`, `encryption.py`, `learning.py`, etc.) y stubs de core nunca conectados (`async_ops.py`, `new_functions.py`, `performance.py`).
- **Duplicación estructural masiva**: `bot_sales/integrations/` y `app/bot/integrations/` son casi-clones (14 de 15 archivos idénticos o con diff mínimo). Lo mismo ocurre con `bot_sales/security/sanitizer.py` vs `app/bot/security/sanitizer.py` (idénticos). Esto es la deuda arquitectónica más grande del repo.
- **Dos catálogos incompatibles coexisten**: `config/catalog.csv` (8.642 líneas, schema: `SKU,Descripcion,Categoria,Proveedor,PriceARS,StockQty`) y `data/tenants/ferreteria/catalog.csv` (63.361 líneas, schema: `sku,category,name,price,currency,stock`). El database loader normaliza ambos en runtime, pero `config/catalog.csv` es un artefacto antiguo que no corresponde al tenant real.
- **profile.yaml tiene 19 campos `[PENDIENTE...]`** incluyendo nombre del negocio, teléfono, dirección, horarios, medios de pago, zonas de envío. El bot no puede dar información de contacto real. El hold_minutes también es `[PENDIENTE]` pero no rompe la funcionalidad porque el bot usa `config.HOLD_MINUTES` (1440) por separado.
- **10 DTs abiertos** (DT-02, DT-03, DT-04, DT-05, DT-06, DT-07, DT-08, DT-09, DT-11, DT-14, DT-18, DT-19, DT-20) según PENDIENTES.md. Hay 3 de alta prioridad: DT-14 (catálogo sin presentación), DT-18 (TI failure fallback al SalesFlowManager legacy), DT-02 (preguntas no transaccionales rompen state machine).
- **`bot_sales/core/tenant_config.py` defaultea `hold_minutes` a 30** (no 1440), pero el bot real usa `HOLD_MINUTES` de `config.py` (env var, default 1440). La discrepancia existe pero no es crítica en producción si el `.env` está bien configurado.
- **`bot_sales/tests/test_routing.py`** y sus tests de `TestRouting` testean la capa `WhatsAppConnector`/blueprint, no el TurnInterpreter. No es obsoleto pero puede confundirse con los tests de routing de la nueva arquitectura.
- **`SalesFlowManager` (bot_sales/planning/) está vivo**: importado por `bot.py` como fallback cuando TurnInterpreter falla (DT-18 lo lista como deuda). 608 LOC activas que no se pueden eliminar todavía.
- **data/ferreteria.db pesa 338 MB** — es la base de datos SQLite de producción local. Está correctamente ignorada por `.gitignore`. No hay datos sensibles comprometidos en el repo.
- **README.md tiene paths incorrectos**: apunta a `/Users/julian/Desktop/Cerrados/Ferreteria` (path viejo, pre-relocalización). Menor, pero cualquier contribuidor nuevo se confundiría.

---

## 1. Inventario macro

### Estado git
```
HEAD: 9f7369d
Branch: main (limpio, up to date con origin/main)
```

### Últimos 10 commits
```
9f7369d docs: PENDIENTES actualizado — cierre 2026-05-07 (10 bloques)
7b3bf53 Merge: DT-16b — apply_clarification no contamina texto de búsqueda con qty
f9298f3 fix(quote): DT-16b — apply_clarification no contamina texto de búsqueda con qty
ce42c2f Merge: DT-16 — clarification de qty cuando hay palabra de presentación
6acafe5 fix(quote): DT-16 — clarification de qty cuando hay palabra de presentación
b95b954 Merge: DT-17b — consolidar líneas duplicadas por SKU/model en lugar de frase normalizada
6e74ae1 fix(quote): DT-17b — consolidar a 1 línea cuando el producto ya está en carrito
dd8a4de Merge: DT-17b — section 4 additive intercept antes de apply_clarification
4736fa6 fix(quote): DT-17b — section 4 additive intercept antes de apply_clarification
7e29d92 Merge: DT-17 — apply_additive incrementa qty (dedup → increment)
```

### Tamaños por carpeta
```
466M   data/           (338M ferreteria.db, 13M farmacia.db, 13M ropa.db, 5.5M catalog.csv — todo gitignored)
6.1M   bot_sales/
5.1M   app/
2.3M   output/         (playwright screenshots, gitignored)
2.2M   tests/
1.8M   tmp/            (gitignored)
868K   tests_finalprod/
704K   config/
476K   scripts/
404K   maintenance/
304K   docs/
188K   Planning/       (gitignored)
148K   website/
120K   reports/
84K    examples/
80K    dashboard/
80K    archive/
44K    template-generator/
40K    experiments/
20K    logs/           (gitignored)
16K    static/
8K     migrations/
4K     tenants/
4K     state/
```

### Top 30 archivos .py por LOC (excluye venvs)

| LOC  | Archivo |
|------|---------|
| 4078 | app/crm/api/routes.py |
| 2809 | bot_sales/bot.py |
| 2778 | app/api/console_routes.py |
| 2366 | bot_sales/ferreteria_quote.py |
| 2206 | app/ui/ferreteria_training_routes.py |
| 1266 | bot_sales/training/store.py |
| 1152 | bot_sales/knowledge/defaults.py |
| 1016 | bot_sales/core/database.py |
|  953 | bot_sales/core/business_logic.py |
|  861 | app/crm/models.py |
|  748 | bot_sales/core/chatgpt.py |
|  677 | bot_sales/training/demo_bootstrap.py |
|  648 | bot_sales/persistence/quote_store.py |
|  620 | app/crm/services/automation_service.py |
|  608 | bot_sales/planning/flow_manager.py |

### Archivos .py en root
```
bot_cli.py
generate_pptx.py
gunicorn.conf.py
whatsapp_server.py
wsgi_legacy.py
wsgi.py
```

### Archivos no-.py en root notables
```
.env                          (secretos locales — gitignored correctamente)
.env.example                  (plantilla pública)
PENDIENTES.md                 (deudas técnicas activas)
README.md                     (tiene paths hardcodeados al path viejo)
ANALYSIS.md, PLAN_FASE1_2.md  (docs de 2026-03-19 — posiblemente obsoletas)
CHANGELOG.md                  (initial commit 2026-04-08, no actualizado)
SECURITY_AUDIT.md             (initial commit — no refleja el estado actual)
P0_P1_COMPLETION.md           (histórico, 2026-03-31)
platform_features.pdf         (0 bytes)
demo_conversacion_dificil.mp4 (8.1 MB — binario commiteado)
docker-compose.yml, Dockerfile, railway.json  (deployment)
requirements.txt, requirements-dev.txt, requirements_enterprise.txt
pytest.ini
```

---

## 2. Inventario por carpeta

| Carpeta | .py count | LOC aprox | Rol | Estado | Duplicación |
|---------|-----------|-----------|-----|--------|-------------|
| `bot_sales/` | 163 | 40.575 | Motor conversacional: bot, quote, catalog, routing, handlers, training | VIVO | Duplica ~60% de `app/bot/` |
| `app/` | 138 | 30.191 | Stack web/API/Flask: CRM, consola, UI, auth, servicios | VIVO | Duplica integraciones de `bot_sales/` |
| `tests/` | 37 | 6.591 | Suite pytest principal (app layer + legacy bot tests) | VIVO (mayormente) | Algunos tests testean arquitectura obsoleta |
| `bot_sales/tests/` | 33 | ~5.000 | Tests del motor conversacional (bot_sales layer) | VIVO | No duplica con `tests/` |
| `tests_finalprod/` | 28 | 4.407 | Tests de hardening del stack CRM/final | VIVO | No duplica |
| `scripts/` | 29 | 5.533 | Scripts de operación, deployment, profiling, bootstrap | MIXTO | `demo_test_suite_extended.py` eliminado; algún script puede estar obsoleto |
| `maintenance/` | 21 | 3.588 | Watchdog, checks DB/HTTP/logs, reportes automáticos | VIVO | Independiente |
| `examples/` | 6 | 1.919 | Demo offline, ejemplos de uso | FÓSIL (probablemente) | Usa `demo_cli_offline.py` con lógica duplicada |
| `dashboard/` | 2 | 612 | Blueprint Flask para dashboard interno | VIVO | Importado por `wsgi_legacy.py` |
| `template-generator/` | 1 | 875 | `create_bot.py` — generador de bots nuevos | FÓSIL (no referenciado) | — |
| `experiments/` | 1 | 338 | Demo Ollama — prueba de modelo local | FÓSIL | — |
| `website/` | 1 | 25 | Script de landing page | FÓSIL | — |
| `migrations/` | — | — | Alembic migrations (no .py encontradas, solo alembic.ini.finalprod) | MIXTO | — |
| `archive/` | 0 | — | Solo `archive/powershell/DailyReport_v5.2.ps1` | FÓSIL | — |
| `tenants/` | 0 | — | Vacío (sin archivos .py ni YAML relevantes) | FÓSIL | — |
| `data/` | 0 | — | Datos: DBs, catálogos, tenant config | N/A | Dos catálogos incompatibles |
| `config/` | 0 | — | Solo `catalog.csv` con schema diferente al real | OBSOLETO | Sí, vs `data/tenants/ferreteria/catalog.csv` |

---

## 3. Código muerto detectado

Criterio: 0 importaciones desde otros archivos .py del proyecto (excluyendo venvs, worktrees, pycache, git).

### bot_sales/ — archivos con 0 usos externos

| Archivo | LOC | Última modificación git | Lectura |
|---------|-----|------------------------|---------|
| `bot_sales/core/async_ops.py` | 159 | 2026-04-08 (initial commit) | Wrappers async genéricos, nunca conectados al bot |
| `bot_sales/core/error_recovery.py` | 205 | 2026-05-06 | Error recovery helpers — ningún archivo los importa |
| `bot_sales/core/new_functions.py` | 73 | 2026-04-08 | Funciones "para agregar a business_logic.py" — nunca agregadas |
| `bot_sales/core/performance.py` | 291 | 2026-04-08 | Profiling/cache stubs — P1 implementó caching directamente en database.py |
| `bot_sales/connectors/webchat.py` | 255 | 2026-04-08 | WebChat API REST — 0 importaciones (template-generator lo menciona como opción) |
| `bot_sales/intelligence/image_search.py` | 43 | 2026-04-08 | Placeholder: "integrar con Google Vision" |
| `bot_sales/intelligence/learning.py` | 395 | 2026-04-08 | Sistema de feedback/analytics — nunca conectado |
| `bot_sales/security/encryption.py` | 214 | 2026-04-08 | PII encryption — nunca importado por nadie |
| `bot_sales/integrations/slack_alerts.py` | 295 | 2026-04-08 | Slack — solo referenced por config como string 'slack_files' |
| `bot_sales/integrations/slack_analytics.py` | 303 | 2026-04-08 | Slack — no importado |
| `bot_sales/integrations/slack_app_home.py` | 495 | 2026-04-08 | Slack — no importado |
| `bot_sales/integrations/slack_files.py` | ~300 | 2026-04-08 | Slack — no importado |
| `bot_sales/integrations/slack_modals.py` | ~300 | 2026-04-08 | Slack — no importado |
| `bot_sales/integrations/slack_product_cards.py` | ~200 | 2026-04-08 | Slack — no importado |
| `bot_sales/integrations/slack_reports.py` | ~250 | 2026-04-08 | Slack — no importado |
| `bot_sales/integrations/slack_threading.py` | ~200 | 2026-04-08 | Slack — no importado |

### app/bot/ — archivos con 0 usos externos

| Archivo | LOC | Última modificación git | Lectura |
|---------|-----|------------------------|---------|
| `app/bot/analytics_engine.py` | 185 | 2026-04-08 | Analytics helpers — 0 importaciones |
| `app/bot/connectors/cli_gemini.py` | 101 | 2026-04-08 | CLI para Gemini — 0 importaciones (Gemini = experimento no activo) |
| `app/bot/connectors/webchat.py` | 255 | 2026-04-08 | WebChat API — 0 importaciones |
| `app/bot/integrations/slack_alerts.py` | 295 | 2026-04-08 | Clon de bot_sales versión, diff ~10 líneas |
| `app/bot/integrations/slack_analytics.py` | 303 | 2026-04-08 | Clon, diff ~4 líneas |
| `app/bot/integrations/slack_app_home.py` | 495 | 2026-04-08 | Clon, diff ~12 líneas |
| `app/bot/integrations/slack_files.py` | ~300 | 2026-04-08 | Clon idéntico |
| `app/bot/integrations/slack_modals.py` | ~300 | 2026-04-08 | Clon, diff ~4 líneas |
| `app/bot/integrations/slack_product_cards.py` | ~200 | 2026-04-08 | Clon idéntico |
| `app/bot/integrations/slack_reports.py` | ~250 | 2026-04-08 | Clon idéntico |
| `app/bot/integrations/slack_threading.py` | ~200 | 2026-04-08 | Clon idéntico |
| `app/bot/intelligence/image_search.py` | 43 | 2026-04-08 | Placeholder idéntico a bot_sales versión |
| `app/bot/intelligence/learning.py` | 395 | 2026-04-08 | Clon de bot_sales versión |
| `app/bot/security/encryption.py` | 214 | 2026-04-08 | Clon de bot_sales versión |
| `app/crm/integrations/stubs.py` | — | 2026-04-08 | Stubs de integración — no importados |
| `app/mail/__main__.py` | — | 2026-05-07 (M0 scaffolding) | Scaffolding M0 recién creado — aún no conectado |
| `app/services/email/sendgrid_client.py` | — | 2026-04-08 | SendGrid — no importado |

### Archivos con 1 uso externo (sospechosos)

Varios archivos en `bot_sales/` tienen solo 1 referencia. Los más sospechosos:
- `bot_sales/bundles.py` — 1 uso, no testeado
- `bot_sales/ferreteria_automation.py` — 1 uso
- `bot_sales/recommendations.py` — 1 uso
- `bot_sales/ferreteria_escalation.py` — 1 uso
- `bot_sales/faq.py` — 1 uso
- `bot_sales/core/state_machine.py` — 1 uso
- `bot_sales/core/objections.py` — 1 uso

**Total LOC eliminables (estimado conservador, solo 0-uso confirmados):** ~8.100 LOC

Si se elimina la capa duplicada de `app/bot/integrations/` completa y los módulos placeholder, el número real está más cerca de 5.000 LOC netas (algunos archivos tienen small diffs que implican evolución divergente intencional).

---

## 4. Heat-map de complejidad/riesgo

### Top 5 archivos críticos

#### 1. `bot_sales/bot.py` — 2.809 LOC
- **Funciones:** 48 definidas; función más grande: `_try_ferreteria_intent_route` (~248 LOC), `process_message` (~164 LOC)
- **Mutaciones de session:** 43 puntos (`sess[...]=`)
- **Llamadas LLM directas:** 0 (delega a `chatgpt.py` y `turn_interpreter.py`)
- **Riesgo:** ALTO. Este archivo es el núcleo de enrutamiento y ha recibido 20+ fixes en 30 días. `_try_ferreteria_intent_route` es una función de 248 líneas que maneja todos los casos de la ferretería; cualquier refactor menor puede introducir regresiones. El estado de la sesión se muta en 43 puntos distribuidos en el archivo — difícil de razonar localmente.
- **Deuda:** DT-18 señala que si TI falla, hay fallback al `SalesFlowManager` legacy (línea ~2350) que puede dar respuestas inconsistentes.

#### 2. `bot_sales/ferreteria_quote.py` — 2.366 LOC
- **Funciones:** 74 definidas (incluyendo funciones módulo-nivel)
- **Mutaciones de session:** 0 directas (recibe dicts inmutables)
- **Llamadas LLM:** 0 directas
- **Riesgo:** MEDIO-ALTO. Contiene toda la lógica de cotización: score de productos, qty parsing, additive/reset/remove detection, clarification, stale prices. Los regexes (`_ADDITIVE_RE`, `_QTY_RE`, `_QTY_SCAN_RE`) son compartidos con `bot.py` por referencia directa (`fq._ADDITIVE_RE`), creando acoplamiento implícito. 4 bugs DT-16/17 arreglados en esta semana indican fragilidad.

#### 3. `app/crm/api/routes.py` — 4.078 LOC
- **Funciones:** 104 definidas
- **Mutaciones de session:** 0 (usa SQLAlchemy, no session dict)
- **Riesgo:** MEDIO. Archivo enorme, pero es el stack CRM completo y está bien separado del bot conversacional. Tiene 104 funciones en un solo archivo — candidato a splitting en blueprints secundarios, pero funcional.

#### 4. `bot_sales/core/database.py` — 1.016 LOC
- **Funciones:** 39 definidas
- **Riesgo:** MEDIO. Contiene el stock cache (P1), find_matches, create_hold. El cache tiene TTL y locks threading. El loader CSV tiene fallback a paths alternativos si el principal no existe (podría silenciar un error de configuración).

#### 5. `bot_sales/core/business_logic.py` — 953 LOC
- **Funciones:** 20 definidas
- **Riesgo:** MEDIO. `_normalize_model` tiene cache per-instance. Usa `HOLD_MINUTES` de `config.py` (correcto). La función `create_hold` llama a `db.create_hold(sku, nombre, contacto, HOLD_MINUTES)` — este HOLD_MINUTES es 1440 (config.py), no el del profile.yaml.

### Duplicación de lógica detectada

1. **Normalización de texto:** hay al menos 12 funciones `_normalize`/`normalize_*`/`sanitize_*` distribuidas en: `bot_sales/ferreteria_quote.py`, `bot_sales/ferreteria_language.py` (3 funciones), `bot_sales/core/database.py`, `bot_sales/core/business_logic.py`, `bot_sales/core/tenant_config.py`, `app/crm/services/normalization.py`, `app/bot/security/sanitizer.py` (≡ `bot_sales/security/sanitizer.py`), `app/crm/domain/schemas.py` (4 funciones), `app/crm/api/routes.py`, `bot_sales/planning/intents.py`, y más. Sin definición canónica única.

2. **`bot_sales/security/sanitizer.py` vs `app/bot/security/sanitizer.py`:** Archivos **idénticos** (263 LOC cada uno, diff 0 líneas). Solo existen para satisfacer los dos namespaces paralelos.

3. **`_ADDITIVE_RE` duplicado:** definido en `bot_sales/ferreteria_quote.py` (línea 1779) y referenciado por `bot_sales/bot.py` con nota explícita "Same alternation as ferreteria_quote._ADDITIVE_RE" (línea 51). El bot accede directamente al regex del módulo como `fq._ADDITIVE_RE`, que es un acoplamiento de implementación interna.

4. **Slack integrations duplicadas:** 14 archivos de `app/bot/integrations/slack_*.py` son clones con diffs menores de los correspondientes en `bot_sales/integrations/slack_*.py`. Divergencia actual: email_client.py (172 líneas de diff), slack_alerts.py (10 líneas), mp_webhooks.py (16 líneas).

---

## 5. Estado de los tests

### Suite oficial (pytest.ini)
```ini
testpaths = tests, bot_sales/tests
norecursedirs = carniceria, archive, .venv, venv
addopts = -ra --import-mode=importlib
markers = slow: tests con LLM real (deseleccionar con -m "not slow")
```

### Archivos de test por carpeta

| Carpeta | Archivos | Estado |
|---------|----------|--------|
| `bot_sales/tests/` | 33 archivos | VIVO — tests recientes DT-12 a DT-17 |
| `tests/` | 37 archivos (incl. subdirs) | MIXTO — algunos potencialmente obsoletos |
| `tests_finalprod/crm/` | ~20 archivos | VIVO — hardening del stack CRM |
| `tests/mail/` | 2 archivos | VIVO — M0 reciente |
| `tests/regression/` | conftest.py solo | MIXTO |

### Tests posiblemente obsoletos o de cobertura dudosa

1. **`tests/test_ferreteria_phase2_families.py`**, **`test_ferreteria_phase4_continuity.py`**, **`test_ferreteria_phase5_automation.py`**, **`test_ferreteria_vnext.py`**: Nombres de "fases" sugieren planificación antigua. Importan `SalesBot`/`process_message` — pueden estar testeando flujos que ya cambiaron con el refactor LLM-first.

2. **`tests/test_fix_loops.py`**: Nombre sugiere fix puntual — ¿sigue siendo relevante?

3. **`bot_sales/tests/test_routing.py`** y **`bot_sales/tests/test_tenancy.py`**: Testean `WhatsAppConnector` y `TenantManager` respectivamente — no son obsoletos en sí, pero están mezclados con tests del motor conversacional.

4. **`tests/test_p0_p1_blockers.py`**: Tiene un `@pytest.mark.skip` (línea 359). Un test skipeado en el suite de regresión es una deuda.

5. **Archivos con `IntentRouter`**: Solo referencias históricas en comentarios (`bot.py:179`, `turn_interpreter.py:2`, `escalation_handler.py:13`). No hay tests que importen `IntentRouter` directamente. Correcto.

### Cobertura estimada

| Area | Cobertura estimada | Observación |
|------|--------------------|-------------|
| `ferreteria_quote.py` (core quote) | Alta | DT-15/16/17 recientes, suite de regresión |
| `turn_interpreter.py` | Media-Alta | test_turn_interpreter_v2, test_turn_interpreter_multi_item |
| `bot.py` (_try_ferreteria_intent_route) | Media | Testeado vía E2E slow, no unitariamente |
| `bot.py` (_process_compound_modify/mixed) | Alta | test_b22a, test_b22c dedicados |
| Slack integrations | CERO | 0 tests para módulos muertos |
| `app/crm/` | Alta | Suite finalprod dedicada |
| `maintenance/` | Baja | No hay tests visibles |

---

## 6. Datos del cliente / tenant

### profile.yaml — placeholders y campos vacíos

**19 campos `[PENDIENTE...]`** en `data/tenants/ferreteria/profile.yaml`:

| Campo | Estado |
|-------|--------|
| `business.name` | `"Ferretería"` + TODO confirmar nombre comercial |
| `contact.phone` | `[PENDIENTE-TEL]` |
| `contact.whatsapp` | `[PENDIENTE-TEL]` |
| `contact.address` | `[PENDIENTE-DIRECCION]` |
| `contact.city` | `[PENDIENTE - ciudad/barrio]` |
| `contact.maps_url` | `[PENDIENTE - link Google Maps]` |
| `hours.weekdays` | `[PENDIENTE-HORARIO]` |
| `hours.saturday` | `[PENDIENTE-HORARIO]` |
| `hours.sunday` | `[PENDIENTE-HORARIO]` |
| `hours.holiday_note` | `[PENDIENTE - feriados/excepciones]` |
| `payment.methods` | `["[PENDIENTE-MEDIOS-DE-PAGO]"]` |
| `payment.installments` | `[PENDIENTE - cuotas disponibles]` |
| `payment.wholesale_min_order` | `[PENDIENTE]` |
| `payment.account_credit` | `[PENDIENTE]` |
| `shipping.zones` | `[PENDIENTE]` |
| `shipping.lead_time` | `[PENDIENTE]` |
| `shipping.free_shipping_threshold` | `[PENDIENTE]` |
| `hold_minutes` | `[PENDIENTE - confirmar con cliente: 45 min vs 24h]` |
| `training.personality` | `""` (vacío) |
| `training.objective` | `""` (vacío) |

**Impacto runtime:** `hold_minutes` como string `[PENDIENTE...]` es almacenado en `tenant_config.config["hold_minutes"]` pero el bot usa `HOLD_MINUTES` de `config.py` (env var 1440) para los holds reales. Sin impacto inmediato, pero si algún código futuro lee `tenant_config.get("hold_minutes")` y lo convierte a int, crasheará.

**El whatsapp_numbers usa placeholder:** `whatsapp:+5493333333333` — número de ejemplo, no real.

### knowledge/*.yaml — estado de cada archivo

| Archivo | LOC | Estado |
|---------|-----|--------|
| `acceptance_patterns.yaml` | 72 | VIVO — patrones de aceptación activos |
| `blocked_terms.yaml` | 6 | VIVO — solo "herramienta" bloqueado |
| `category_aliases.yaml` | 34 | VIVO |
| `clarification_rules.yaml` | 75 | VIVO |
| `complementary_rules.yaml` | 34 | VIVO |
| `family_rules.yaml` | 335 | VIVO — post-fix B1/Q3 |
| `faqs.yaml` | 78 | VIVO — 5 entries (envíos, pagos, facturación, etc.) |
| `item_family_map.yaml` | 81 | VIVO — post-fix Q3 |
| `language_patterns.yaml` | 33 | VIVO — slang, typos, regional |
| `substitute_rules.yaml` | 68 | VIVO |
| `synonyms.yaml` | 167 | VIVO |

Un archivo importante que coexiste en dos lugares: `knowledge/faqs.yaml` (dentro del knowledge loader) y `faqs.json` en el root del repo. El `faqs.json` raíz parece ser un artefacto separado de una etapa anterior — no referenciado en el motor conversacional.

### policies.md y faqs.yaml — estado
- `policies.md`: 38 líneas, vigente. Dice reservas duran **45 minutos** — inconsistente con `config.py` que usa 1440 (24h). Discrepancia visible al cliente.
- `faqs.yaml`: 78 líneas, completo para las preguntas básicas (envíos, pagos, facturación, horarios, garantías).

### Catálogos — comparación y tamaño

| Catálogo | Líneas | Schema | Uso |
|----------|--------|--------|-----|
| `data/tenants/ferreteria/catalog.csv` | 63.361 | `sku,category,name,price,currency,stock` | PRODUCCIÓN — tenant real |
| `config/catalog.csv` | 8.642 | `SKU,Descripcion,Categoria,Proveedor,PriceARS,StockQty` | LEGACY — schema diferente, origen incierto |

El loader de `database.py` normaliza ambos schemas vía `_normalize_key()`. El tenant real usa `data/tenants/ferreteria/catalog.csv` (per `profile.yaml paths.catalog`). `config/catalog.csv` existe pero su contenido (Knipex, BlueTools) podría ser un catálogo distinto o una copia parcial. **Riesgo**: si el fallback en `database._load_catalog_from_csv` usa `config/catalog.csv`, el bot sirve un catálogo diferente.

**Resumen go-live:** Para poder poner esto en producción el cliente necesita proveer:
1. Nombre comercial, teléfono, dirección, ciudad, Google Maps link
2. Horarios reales (lunes-sábado, domingo, feriados)
3. Medios de pago, cuotas, monto mínimo mayorista
4. Zonas de envío, plazo, umbral de envío gratis
5. Número WhatsApp real (actualmente placeholder +5493333333333)
6. Decisión sobre hold_minutes (45 min per policies.md o 24h per config)
7. Actualizar `training.personality` y `training.objective` en profile.yaml

---

## 7. Documentación

| Archivo | Tamaño | Última mod git | Estado |
|---------|--------|----------------|--------|
| `data/tenants/ferreteria/PENDIENTES.md` | 34K | 2026-05-04 | VIGENTE — deudas del tenant |
| `PENDIENTES.md` (root) | ~8K | 2026-05-07 | VIGENTE — deudas técnicas activas |
| `reports/test_audit_2026-05-05.md` | 24K | 2026-05-05 | VIGENTE — auditoría de tests |
| `docs/ferreteria_juli_technical_assessment.md` | 27K | 2026-04-01 | NO_PUEDO_DECIR (pre-refactor) |
| `docs/project/PRODUCTION_GUIDE.md` | 22K | 2026-04-08 | OBSOLETO — no refleja runtime wsgi.py actual |
| `context.md` | 290 líneas | 2026-05-03 | VIGENTE — última actualización reciente |
| `CHANGELOG.md` | 105 líneas | 2026-04-08 (initial) | OBSOLETO — no actualizado |
| `SECURITY_AUDIT.md` | 190 líneas | 2026-04-08 (initial) | OBSOLETO — pre-hardening |
| `P0_P1_COMPLETION.md` | 256 líneas | 2026-04-08 (initial) | HISTÓRICO |
| `PLAN_FASE1_2.md` | 455 líneas | 2026-04-08 (initial) | HISTÓRICO |
| `ANALYSIS.md` | 171 líneas | 2026-04-08 (initial) | OBSOLETO — generado 2026-03-19 |
| `README.md` | 149 líneas | 2026-04-08 | OBSOLETO — path hardcodeado viejo |
| `QUICKSTART.md` | 178 líneas | 2026-04-08 (initial) | PARCIALMENTE OBSOLETO |
| `CONTRIBUTING.md` | 119 líneas | 2026-04-08 (initial) | VIGENTE conceptualmente |
| `platform_features.pdf` | 0 bytes | — | ROTO (archivo vacío) |
| `docs/CLIENT_PITCH.pdf` | 5.6K | 2026-01-24 | NO_PUEDO_DECIR |

---

## 8. Smells y rarezas

### TODOs y FIXMEs

**Total: 22** (excluyendo venvs y worktrees).

La mayoría son usos legítimos de `TaskStatus.TODO` en el CRM (enum). Los TODOs de código real:
- `app/bot/integrations/slack_files.py:169` — "TODO: Save image to storage" (en módulo no importado)
- `app/bot/integrations/slack_files.py:188` — "TODO: Extract text from PDF" (en módulo no importado)
- `app/bot/integrations/slack_files.py:206` — "TODO: Process Excel" (en módulo no importado)
- `bot_sales/core/universal_llm.py:112` — "TODO: Function calling support for open source models"
- `bot_sales/core/performance.py:214` — "TODO: Implementar registro global de cachés" (en módulo no importado)
- `bot_sales/integrations/mp_webhooks.py:187` — "TODO: Actualizar DB según result"

### Archivos binarios commiteados

| Archivo | Tamaño | Observación |
|---------|--------|-------------|
| `demo_conversacion_dificil.mp4` | 8.1 MB | Video de demo commiteado — infla el repo |
| `docs/CLIENT_PITCH.pdf` | 5.6 KB | PDF de pitch al cliente |
| `platform_features.pdf` | 0 bytes | PDF vacío — debería eliminarse |

**Bases de datos locales (gitignored correctamente, pero existentes):**
- `data/ferreteria.db` — 338 MB (SQLite producción local)
- `data/farmacia.db`, `data/ropa.db` — 13 MB cada una (tenants demo)
- `data/default_store.db`, `data/iphone_store.db` — artefactos de otra etapa

### Archivos de 0 bytes (en el repo)

```
app/bot/__init__.py
app/bot/connectors/__init__.py
bot_sales/__init__.py
bot_sales/connectors/__init__.py
bot_sales/core/__init__.py
bot_sales/handlers/__init__.py
bot_sales/observability/__init__.py
bot_sales/state/__init__.py
dashboard/iphone_store.db         (commiteado, vacío)
data/tenants/ferreteria/ferreteria.db  (commiteado, vacío — la DB real está en data/)
platform_features.pdf              (commiteado, vacío)
reports/logs/maintenance.log       (commiteado, vacío)
tests_finalprod/crm/__init__.py
tests/mail/__init__.py
```

**Nota:** `dashboard/iphone_store.db` y `data/tenants/ferreteria/ferreteria.db` son archivos `.db` vacíos commiteados — deberían estar en `.gitignore` (la línea `*.db` en `.gitignore` no los cubre porque ya fueron commiteados antes).

### Archivos .bak / .old / temporales

Los únicos `.bak` están dentro de `.claude/worktrees/` (worktrees de Claude) — no son parte del código real del proyecto. No hay `.bak` en el árbol de trabajo principal.

### Imports sospechosos

- `app/bot/bot_gemini.py`: importa `GeminiClient` — única referencia a Gemini en el proyecto. El archivo tiene 0 usos externos. Es un experimento que se puede eliminar.
- `bot_sales/core/universal_llm.py`: soporte LLM genérico (Ollama, etc.) — solo importado desde 1 lugar, probablemente experiments.

### Strings de placeholder en código/config

Encontrados (legítimos en contexto de test/demo):
- `test@example.com` en varios tests de `tests_finalprod/` — correcto para tests
- `admin@example.com` en `app/bot/security/auth.py:239` — fallback de ADMIN_EMAIL, no crítico
- `whatsapp:+5493333333333` en `profile.yaml` — número real pendiente del cliente
- `example.com` en UI como placeholder de formulario — aceptable

### Secretos hardcodeados (CRITICO)

**El `.env` contiene secretos reales pero NO está versionado en git.** Está correctamente en `.gitignore`. Sin embargo:

| Secreto | Valor | Riesgo |
|---------|-------|--------|
| `OPENAI_API_KEY` | `sk-proj-JpSjrNF-...` (real) | No versionado — correcto. Rotar si fue expuesto en cualquier terminal/log. |
| `ADMIN_PASSWORD` | `Aristoteles` | Trivial — cambiar antes de deploy |
| `ADMIN_TOKEN` | `ferreteria-token-2024` | Predecible, año hardcodeado — cambiar antes de deploy |
| `SECRET_KEY` | `dev-secret-key-ferreteria-juli` | Desarrollo — cambiar por valor random de 32+ bytes en producción |

**No se encontraron secretos hardcodeados en ningún archivo `.py`, `.yaml`, o `.json` versionado.** Todos los accesos usan `os.getenv()` correctamente.

---

## 9. Dudas / preguntas para Julian

1. **`config/catalog.csv` (8.642 líneas)**: ¿Es un catálogo viejo, un catálogo de otro cliente, o una demo? El schema es diferente al real. Si no se usa, debería eliminarse para evitar confusión con el fallback de `database.py`.

2. **`data/farmacia.db` y `data/ropa.db`** (13 MB cada uno): ¿Son bases de datos de tenants demo activos o artefactos de desarrollo? Si son demo, deberían estar en `tmp/` o gitignoreados claramente.

3. **`data/tenants/ferreteria/ferreteria.db` (0 bytes, commiteado)**: Parece que en algún momento se intentó tener la DB dentro de la carpeta tenant. La DB real está en `data/ferreteria.db`. ¿Se puede eliminar este archivo vacío del repo con `git rm`?

4. **`policies.md` dice reservas = 45 minutos, pero `config.py` dice 1440 (24h)**: ¿Cuál es la intención correcta? La discrepancia afecta directamente lo que el bot comunica al cliente sobre reservas.

5. **`demo_conversacion_dificil.mp4` (8.1 MB) commiteado**: ¿Fue intencional? Si es un video de demo/presentación, podría moverse a Google Drive y el repo quedar limpio.

6. **`wsgi_legacy.py`**: Está activo como fallback en `wsgi.py`. ¿Cuándo se planea eliminarlo? DT-18 menciona que TI failure usa SalesFlowManager — ¿está relacionado?

7. **`template-generator/create_bot.py` (875 LOC)**: Generador de nuevos tenants. ¿Sigue siendo la forma canónica de crear un tenant nuevo? Si no, se puede archivar. Si sí, debería tener tests.

8. **`faqs.json` en el root**: ¿Es el mismo contenido que `data/tenants/ferreteria/knowledge/faqs.yaml`? No parece ser usado por el motor conversacional. ¿Artefacto de una etapa anterior?

9. **`bot_sales/core/error_recovery.py` (205 LOC, última modificación 2026-05-06)**: Fue modificado recientemente pero tiene 0 importaciones. ¿Es trabajo en progreso o se olvidaron de conectarlo?

10. **`app/bot/bot_gemini.py` con `GeminiClient`**: ¿El experimento con Gemini está activo o cerrado? Si está cerrado, se puede eliminar junto con `app/bot/connectors/cli_gemini.py` y `experiments/ollama/`.

---

## 10. Recomendaciones priorizadas

| # | Acción | Impacto | Esfuerzo | Riesgo |
|---|--------|---------|----------|--------|
| 1 | **Rotar secretos antes de deploy**: cambiar ADMIN_PASSWORD, ADMIN_TOKEN, SECRET_KEY a valores seguros y random. | CRÍTICO para go-live | Bajo (1h) | Cero — sin cambios de código |
| 2 | **Completar profile.yaml con el cliente**: 19 campos PENDIENTE incluyendo teléfono, dirección, horarios, medios de pago. Sin esto el bot no puede dar info de contacto. | CRÍTICO para go-live | Depende del cliente | Cero (solo datos) |
| 3 | **Resolver discrepancia hold_minutes**: `policies.md` dice 45 min, `config.py` usa 1440 (24h). Decidir y alinear ambos más el campo en `profile.yaml`. | Alto — afecta UX | Bajo (30min) | Bajo |
| 4 | **Eliminar duplicados de `app/bot/integrations/slack_*`**: 8 archivos, 14 de 15 son clones de `bot_sales/integrations/`. Mantener solo uno (probablemente `app/bot/`) o unificar en un paquete compartido. | Medio — limpieza de ~2.700 LOC | Medio (1 sesión) | Bajo (0 importaciones) |
| 5 | **Eliminar módulos placeholder sin importaciones**: `bot_sales/core/{async_ops,new_functions,performance,error_recovery}.py`, `bot_sales/intelligence/{image_search,learning}.py`, `bot_sales/security/encryption.py`, `app/bot/{analytics_engine,bot_gemini}.py`. ~2.000 LOC eliminables sin riesgo. | Medio — reduce confusión | Bajo (30min) | Cero si se confirma 0 usos |
| 6 | **Actualizar README.md y docs/project/PRODUCTION_GUIDE.md**: paths hardcodeados a `/Desktop/Cerrados/Ferreteria` (viejo). Cualquier nuevo colaborador se confunde. | Medio | Bajo (1h) | Cero |
| 7 | **Resolver DT-18 (TI failure → SalesFlowManager fallback)**: cuando TurnInterpreter falla, el bot cae al SalesFlowManager legacy que puede dar respuestas inconsistentes con la arquitectura LLM-first. | Alto — estabilidad | Medio | Medio |
| 8 | **Eliminar `config/catalog.csv`** (schema diferente, 8.642 líneas) y clarificar el fallback en `database._load_catalog_from_csv`. | Bajo-Medio — evita errores de configuración | Bajo (15min) | Bajo (verificar que no hay código que lo use intencionalmente) |
| 9 | **Resolver `data/tenants/ferreteria/ferreteria.db` (0 bytes) y `dashboard/iphone_store.db` (0 bytes)**: eliminar del git con `git rm`. | Bajo — limpieza | Bajo (5min) | Cero |
| 10 | **Auditar tests de la carpeta `tests/`** que testean arquitectura pre-B21: `test_ferreteria_phase*.py`, `test_fix_loops.py` — verificar si aún son válidos o si cubren flujos ya refactorizados. Esto previene falsos positivos de regresión. | Medio — calidad de suite | Medio | Bajo |
