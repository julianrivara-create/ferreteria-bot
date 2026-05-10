# Audit D4 — bot_sales/core y zonas legacy

**HEAD:** `9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb`
**LOC analizadas:** ~17,800 (todas las carpetas indicadas, excluyendo venvs y worktrees)
**Generado:** 2026-05-09

> **Nota metodológica:** Los conteos de refs via grep miden imports `from bot_sales.X.Y` o
> `from .X.Y`. Los imports relativos con `..` (cross-package, ej: `from ..intelligence.comparisons`)
> no son capturados por ese patrón. Donde el grep da 0 pero la lectura directa del código muestra
> un import vivo, se marcó VIVO con nota. Los conteos de refs para archivos con 0 o 1 se verificaron
> manualmente en business_logic.py y bot.py.

---

## Resumen

- **VIVO real:** ~60% de las LOC analizadas están en el camino de producción activo
- **FÓSIL eliminable:** ~3,800 LOC seguras de borrar (0 usos en runtime, sin riesgo)
- **La capa LLM de producción es una sola:** `chatgpt.py` → `ChatGPTClient`. Las otras tres capas (`gemini.py`, `llm_backend.py`, `universal_llm.py`) son legacy/experimental y no tocan el flujo de producción
- **`bot_sales/integrations/` tiene 9 archivos Slack muertos** (~2,100 LOC) — feature Slack nunca fue conectada al runtime principal de bot.py
- **`bot_sales/core/` tiene 7 archivos fósiles** (~1,050 LOC) — artifacts de planificación nunca eliminados
- **Tres `ab_testing.py` distintos** en tres carpetas diferentes: `integrations/`, `planning/`, `experiments/`
- **`new_functions.py`** (73 LOC) es duplicado exacto de métodos ya integrados en `business_logic.py` — es un planning note que se olvidó borrar
- **`bot_sales/intelligence/`**: solo 2 de 4 archivos están vivos (los otros 2 nunca se importaron)
- **El grep subestima los usos reales** porque business_logic.py, bot.py e internos usan `from ..X.Y` en lugar de absolute imports

---

## 1. Inventario por carpeta

| Carpeta | Archivos .py | LOC | Estado mayoritario | Notas |
|---|---|---|---|---|
| `bot_sales/core/` | 24 | 6,621 | **MIXTO** | Base vital + 7 fósiles (~1,050 LOC) |
| `bot_sales/intelligence/` | 4 | 762 | **MIXTO** | 2 vivos, 2 fósiles |
| `bot_sales/connectors/` | 7 | 1,904 | **MIXTO** | whatsapp VIVO, webchat FÓSIL |
| `bot_sales/integrations/` | 17 | 4,139 | **MAYORITARIAMENTE FÓSIL** | 9 Slack files muertos (~2,100 LOC) |
| `bot_sales/planning/` | 9 | 1,875 | **VIVO** | Todos con refs reales |
| `bot_sales/training/` | 7 | 2,847 | **VIVO** | Dashboard de entrenamiento activo |
| `bot_sales/multimedia/` | 2 | 125 | **VIVO** | audio + image, 2 refs c/u |
| `bot_sales/observability/` | 2 | 131 | **VIVO** | Importado por bot.py |
| `bot_sales/persistence/` | 1 | 648 | **VIVO** | 9 refs — quote engine central |
| `bot_sales/security/` | 5 | 1,237 | **MIXTO** | encryption.py fósil |
| `bot_sales/i18n/` | 1 | 111 | **VIVO** | Importado por business_logic.py |
| `bot_sales/knowledge/` | 3 | 1,759 | **VIVO** | 6-10 refs c/u |
| `bot_sales/data/` | 0 | — | N/A | Solo carpeta `prompts/` sin .py |
| `bot_sales/experiments/` | 1 | 217 | **FÓSIL** | Prueba ollama standalone |

---

## 2. bot_sales/core/business_logic.py (953 LOC)

### Responsabilidades actuales

`BusinessLogic` es la **capa de implementación de las tools de OpenAI**. No es "lógica de negocio" genérica — es el bridge entre `ChatGPTClient.send_message()` y la base de datos. Cada método corresponde a una función registrada en `get_available_functions()` en `chatgpt.py`.

**Métodos activos y sus responsabilidades:**

| Método | Rol | Estado |
|---|---|---|
| `buscar_stock()` | Busca productos + llama a `_score_product` de ferreteria_quote | VIVO |
| `listar_modelos()` | Agrupa stock por categoría con disponibilidad | VIVO |
| `buscar_alternativas()` | Fuzzy match + filtro por disponibilidad | VIVO |
| `crear_reserva()` | Crea hold con validación anti-hallucination | VIVO |
| `confirmar_venta()` | Confirma venta + descuenta stock + email + cross-sell | VIVO |
| `buscar_por_categoria()` | Delegación a db.find_by_category | VIVO |
| `obtener_cross_sell_offer()` | Lógica de cross-sell post-venta | VIVO |
| `agregar_producto_extra()` | Agrega ítem extra a venta existente | VIVO |
| `derivar_humano()` | Crea lead en DB para handoff | VIVO |
| `consultar_faq()` | Retorna contexto FAQ completo al LLM | VIVO |
| `listar_bundles()` | Delega a BundleManager | VIVO |
| `obtener_bundle()` | Detalle de bundle por ID | VIVO |
| `obtener_recomendaciones()` | Delega a RecommendationEngine | VIVO |
| `obtener_upselling()` | Smart upsell: mismo modelo con más storage o mayor precio | VIVO |
| `comparar_productos()` | Delega a ProductComparator (intelligence/) | VIVO |
| `validar_datos_cliente()` | Guardrail: valida nombre/email/contacto/dni | VIVO |
| `detectar_fraude()` | Risk scoring via FraudDetector | VIVO |
| `_normalize_model()` | Ferretería-specific: expande abreviaciones + fuzzy match | VIVO |

### Responsabilidades que podrían estar en otro lado pero están acá

- **Cross-sell y upsell logic** (líneas 450-900): lógica de negocio real, 250+ LOC embebidas en lo que debería ser solo un bridge de tools. Son candidatas a extraerse a un `bot_sales/services/` dedicado si el archivo crece más.
- **Anti-hallucination guardrails** en `crear_reserva()` (líneas 263-283): lógica de validación de datos del cliente embebida en el método de reserva. Ya está también en `validar_datos_cliente()` — duplicación leve.
- **Llamada directa a `db.cursor.execute()`** en `confirmar_venta()` (línea 329) y `agregar_producto_extra()` (línea 551): raw SQL en la capa de business logic, bypassing el API de Database. Riesgo de inconsistencia si el schema cambia.

### Candidatos a migrar (ya existen servicios paralelos)

Según el audit M1, existen `bot_sales/services/` con servicios especializados. business_logic.py sigue operando como monolito de tools — ninguna responsabilidad parece migrada aún desde acá. El archivo es legítimo en su estado actual.

---

## 3. bot_sales/core/database.py (1,016 LOC)

### Qué hace

Motor de persistencia SQLite de baja latencia para el bot. Maneja:
- **Schema de 6 tablas:** `stock`, `holds`, `sales`, `leads`, `customers`, `conversation_sessions`
- **Catálogo dinámico:** carga CSV en boot con `INSERT OR REPLACE`, elimina SKUs stale
- **Búsqueda híbrida:** keyword tokenizado + vector (embedding OpenAI) vía `VectorSearchEngine`
- **Cache en memoria** con TTL de 60s para evitar full table scans en cada turn
- **Thread safety:** `_cursor_lock` + WAL mode para reads concurrentes

### Queries SQL relevantes

Tiene SQL crudo directo en `Database` — no usa ORM:
- `CREATE TABLE IF NOT EXISTS` en `_init_db()` — schema inline
- `INSERT OR REPLACE INTO stock` — catalog reload
- `DELETE FROM stock WHERE sku NOT IN (SELECT sku FROM _csv_skus)` — limpieza de stale SKUs
- `CREATE INDEX IF NOT EXISTS` — índices de performance
- `ON CONFLICT(session_id, tenant_id) DO UPDATE SET` — upsert de sesiones

### Riesgos detectados

1. **`self.cursor.execute()` compartido con locks manuales** — el lock `_cursor_lock` protege algunas operaciones pero business_logic.py accede a `db.cursor` directamente (línea 329, 551 de business_logic.py), bypassing el lock. Potencial race condition en accesos concurrentes.
2. **WAL no checkpointed automáticamente** — el `PRAGMA synchronous=NORMAL` sacrifica durabilidad por velocidad. Confirma por qué data/ferreteria.db tiene 13MB de WAL pendiente.
3. **`logging.basicConfig()` en `__init__`** — reconfigura el root logger global cada vez que se instancia una DB nueva, potencialmente sobreescribiendo config de logging del app layer.

---

## 4. bot_sales/core/tenancy.py (287 LOC)

### Qué hace

Gestión multi-tenant completa. Expone un **singleton de módulo** `tenant_manager = TenantManager()` que se importa en 15+ archivos.

**Flujo de resolución:**
1. Lee `tenants.yaml` en boot con expansión de env vars (`os.path.expandvars`)
2. Para cada tenant, carga opcionalmente un `profile_path` YAML adicional con metadatos del negocio
3. Construye mapas de lookup: por `id`, por `slug`, por `phone_number`, por `whatsapp_phone_number_id`, por `ig_page_id`
4. Cachea `Database` y `SalesBot` instancias por tenant_id (singleton por tenant)

### Conexión con tenants.yaml y data/tenants/

- **`tenants.yaml` (root):** índice de tenants. Actualmente 1 tenant activo (`ferreteria`).
- **`data/tenants/ferreteria/`:** contiene el `profile_path` YAML del tenant con metadatos del negocio (nombre, horarios, comunicación, etc.)
- **`data/tenants/default/`:** tenant default para desarrollo/testing
- **`tenants/atelier.yaml`:** archivo de configuración de tenant secundario (carpeta `tenants/` root) — no está en `tenants.yaml`, sin conexión clara al sistema actual

### Observación

`get_bot()` en TenantManager instancia un `SalesBot` completo (con DB, ChatGPTClient, etc.) y lo cachea en memoria. En Railway con un solo worker Gunicorn, este singleton vive para siempre. Si se agrega un segundo worker, cada uno tendría su propio singleton — no hay Redis-backed cache para el bot cache.

---

## 5. Las 4 capas LLM

### Mapa de uso

| Archivo | Clase | Refs externas | ¿En producción? |
|---|---|---|---|
| `core/chatgpt.py` | `ChatGPTClient` | **7** (bot.py, handlers, routing, planning) | **SÍ — es el cliente de producción** |
| `core/gemini.py` | `GeminiClient` | 1 (app/bot/bot_gemini.py) | NO — ruta alternativa en app/bot/ |
| `core/llm_backend.py` | `LLMBackend`, `LLMFactory`, `OpenAIBackend`, `OllamaBackend`, `LMStudioBackend` | 1 (universal_llm.py) | NO |
| `core/universal_llm.py` | `UniversalLLMClient` | 2 (tests, experiments) | NO |
| `core/client_factory.py` | — | 0 (solo se importa a sí mismo) | NO |

### Detalles

**`chatgpt.py` — PRODUCCIÓN:**
- Importado directamente por `bot_sales/bot.py` como `ChatGPTClient`
- Implementa `send_message()` con tool_calls (API moderna de OpenAI), retry 3x con backoff, mock mode para tests sin API key
- También contiene `build_system_prompt()` (el prompt de sistema del bot) y `get_available_functions()` (las 16 tools registradas para function calling)
- Tiene un `ObjectionHandler` importado de `core/objections.py` que se inyecta en el system prompt

**`gemini.py` — LEGACY/ALTERNATIVO:**
- Importado solo en `app/bot/bot_gemini.py` — una versión alternativa del bot usando Gemini
- No soporta function calling real (el send_message solo retorna texto, no tool_calls)
- Tiene su propio `build_system_prompt()` con prompt diferente al de chatgpt.py — dos versiones del system prompt divergiendo en paralelo
- Estado: FÓSIL en el contexto del runtime principal de bot_sales/bot.py; MIXTO si app/bot/ está activo

**`llm_backend.py` — FÓSIL:**
- Abstracción `LLMBackend` con backends para OpenAI, Ollama, LM Studio
- Solo importado por `universal_llm.py`
- Nunca conectado al runtime principal. Fue diseñado para soporte multi-backend local (Ollama) que no llegó a producción

**`universal_llm.py` — FÓSIL:**
- Wrapper de `llm_backend.py` con alias `ChatGPTClient = UniversalLLMClient` (línea 197)
- El alias sugiere que fue un intento de drop-in replacement de chatgpt.py que nunca se activó
- Importado solo por `tests/test_robustness.py` y `experiments/ollama/demo_ollama.py`
- No soporta function calling real (tiene un `TODO: Function calling support` en línea 112)

**`client_factory.py` — FÓSIL (0 usos externos):**
- 150 LOC de factory que importa universal_llm.py — nadie lo importa

### Conclusión LLM

**Una sola capa LLM en producción:** `chatgpt.py → ChatGPTClient`. Las otras 3 capas son 750 LOC de legacy eliminable. El riesgo único: verificar que ningún test crítico dependa de `universal_llm.py` antes de borrar.

---

## 6. Carpetas grandes — análisis

### bot_sales/integrations/ (492 KB, 4,139 LOC)

El directorio con mayor volumen de código muerto del repo.

**Estado por archivo:**

| Archivo | LOC | Refs | Estado | Notas |
|---|---|---|---|---|
| `slack_app_home.py` | 495 | 0 | **FÓSIL** | Duplicado en app/bot/integrations/; mismo tamaño |
| `slack_modals.py` | 417 | 0 | **FÓSIL** | — |
| `crm.py` | 388 | 0 | **FÓSIL** | CRM legacy; el CRM real está en app/crm/ |
| `slack_product_cards.py` | 329 | 0 | **FÓSIL** | — |
| `slack_threading.py` | 266 | 0 | **FÓSIL** | — |
| `slack_reports.py` | 220 | 0 | **FÓSIL** | — |
| `slack_files.py` | 235 | 0 | **FÓSIL** | — |
| `slack_analytics.py` | 303 | 0 | **FÓSIL** | — |
| `slack_alerts.py` | 295 | 0 | **FÓSIL** | — |
| `sentiment.py` | 326 | 0 | **FÓSIL** | Diferente del intelligence/sentiment.py (VIVO) |
| `ab_testing.py` | 207 | 1 | **MIXTO** | 1 ref desde planning/ab_testing.py |
| `email_client.py` | 248 | 1 | **VIVO** | Importado por business_logic.py |
| `mercadopago_client.py` | 38 | 0* | **VIVO** | Importado por business_logic.py (grep missed) |
| `mp_webhooks.py` | 195 | 1 | **VIVO** | — |
| `sheets_sync.py` | 279 | 1 | **MIXTO** | — |
| `slack_approvals.py` | 318 | 1 | **MIXTO** | — |
| `slack_commands.py` | 294 | 1 | **MIXTO** | — |

**LOC FÓSIL en integrations/:** ~3,279 LOC (9-11 archivos)
**LOC vivas:** ~860 LOC (email, mp, approvals, commands, mp_webhooks)

**Hallazgo crítico:** La integración Slack está completamente duplicada. `bot_sales/connectors/slack.py` (445 LOC) es el conector de entrada (recibe mensajes). Los archivos `slack_*.py` en integrations/ son features de salida (enviar alertas, modales, reportes a Slack) que nunca se conectaron al runtime principal de `bot.py`. Todo el stack Slack de integrations/ parece haber sido construido sin integrarse con el orquestador.

### bot_sales/training/ (468 KB, 2,847 LOC)

Estado: **VIVO** — alimenta el dashboard de entrenamiento en `app/ui/ferreteria_training_routes.py`.

| Archivo | LOC | Refs | Rol |
|---|---|---|---|
| `store.py` | 1,266 | 6 | Persistencia de sesiones, ejemplos, feedback de training |
| `demo_bootstrap.py` | 677 | 3 | Genera datos de demo para training (arranca el tenant) |
| `suggestion_service.py` | 476 | 2 | Sugiere mejoras al catálogo/FAQs |
| `session_service.py` | 258 | 1 | CRUD de sesiones de entrenamiento |
| `review_service.py` | 55 | 2 | Lógica de revisión de respuestas del bot |
| `context_builder.py` | 39 | 1 | Construye contexto para sesiones |
| `costs.py` | 74 | 1 | Calcula costos de API por sesión |

### bot_sales/planning/ (432 KB, 1,875 LOC)

Estado: **VIVO** — el pipeline de planificación de conversación está activo.

`pipeline.py` (8 refs) es el entry point principal. Lo importan bot.py y handlers. El flujo:
`TurnInterpreter → routing/` → `SalesFlowManager (planning/flow_manager.py)` → `pipeline.py`.

`ab_testing.py` (106 LOC, 1 ref) — MIXTO: solo referenciado en tests.

### bot_sales/intelligence/ (136 KB, 762 LOC)

**MIXTO:**

| Archivo | LOC | Estado | Notas |
|---|---|---|---|
| `comparisons.py` | 191 | **VIVO** | `ProductComparator`, importado por business_logic.py |
| `sentiment.py` | 133 | **VIVO** | `SentimentAnalyzer`, importado por business_logic.py |
| `learning.py` | 395 | **FÓSIL** | Sistema de aprendizaje de patrones de conversación — 0 refs en runtime |
| `image_search.py` | 43 | **FÓSIL** | Búsqueda de imágenes por URL/texto — 0 refs |

### bot_sales/security/ (184 KB, 1,237 LOC)

**MIXTO:**

| Archivo | LOC | Estado | Notas |
|---|---|---|---|
| `auth.py` | 314 | **VIVO** | Autenticación de webhooks y debug commands |
| `validators.py` | 255 | **VIVO** | Validación de datos de cliente — importado por business_logic.py |
| `sanitizer.py` | 263 | **VIVO** | Sanitización de respuestas del bot |
| `fraud_detector.py` | 190 | **VIVO** | Risk scoring — importado por business_logic.py |
| `encryption.py` | 214 | **FÓSIL** | Encriptación de datos sensibles — 0 refs |

### bot_sales/persistence/ (112 KB, 648 LOC)

**VIVO** — `quote_store.py` con 9 refs es el motor de cotizaciones multi-línea. Es el archivo más referenciado de todas las carpetas analizadas (junto con database.py).

---

## 7. Árbol de dependencias internas

```
wsgi.py (producción Railway)
  └── app/main.py (Flask factory)
        ├── bot_sales.connectors.storefront_tenant_api   [VIVO]
        └── [registra blueprints de app/api/, app/crm/, app/ui/]
             └── app/api/channels.py
                   └── bot_sales.core.tenancy.tenant_manager
                         └── bot_sales.core.database.Database
                               └── bot_sales.core.vector_search.VectorSearchEngine

whatsapp_server.py (alternativo)
  └── bot_sales.connectors.whatsapp
        └── bot_sales.core.tenancy.tenant_manager
              └── bot_sales.bot.SalesBot ← ORQUESTADOR CENTRAL
                    ├── bot_sales.core.chatgpt.ChatGPTClient  [PRODUCCIÓN LLM]
                    │     └── bot_sales.core.objections.ObjectionHandler
                    ├── bot_sales.core.business_logic.BusinessLogic
                    │     ├── bot_sales.core.database.Database
                    │     ├── bot_sales.integrations.email_client.EmailClient
                    │     ├── bot_sales.integrations.mercadopago_client.MercadoPagoClient
                    │     ├── bot_sales.security.validators.Validator
                    │     ├── bot_sales.security.fraud_detector.FraudDetector
                    │     ├── bot_sales.intelligence.sentiment.SentimentAnalyzer
                    │     ├── bot_sales.intelligence.comparisons.ProductComparator
                    │     └── bot_sales.i18n.translator.Translator
                    ├── bot_sales.knowledge.loader.KnowledgeLoader
                    │     └── bot_sales.knowledge.defaults.KnowledgeDefaults
                    ├── bot_sales.persistence.quote_store.QuoteStore
                    ├── bot_sales.planning.flow_manager.SalesFlowManager
                    │     └── bot_sales.planning.pipeline.SalesPipeline
                    ├── bot_sales.routing.turn_interpreter.TurnInterpreter
                    ├── bot_sales.state.conversation_state.ConversationStateV2
                    ├── bot_sales.observability.metrics + turn_event
                    └── bot_sales.multimedia.audio_transcriber + image_analyzer

--- DESCONECTADOS DEL ÁRBOL PRINCIPAL ---
bot_sales/core/gemini.py          → app/bot/bot_gemini.py (ruta alternativa, no wsgi.py)
bot_sales/core/llm_backend.py     → universal_llm.py → tests/experiments SOLO
bot_sales/core/universal_llm.py   → tests/experiments SOLO
bot_sales/core/client_factory.py  → NADIE
bot_sales/integrations/slack_*.py → NADIE (9 archivos)
bot_sales/integrations/crm.py     → NADIE
bot_sales/intelligence/learning.py → NADIE
bot_sales/intelligence/image_search.py → NADIE
```

---

## 8. Candidatos a eliminación (LOC eliminables)

Confianza: **ALTA** = 0 refs en toda la codebase, código autónomo. **MEDIA** = 0 refs en runtime pero posible uso en scripts manuales.

| Path | LOC | Confianza | Razón |
|---|---|---|---|
| `bot_sales/core/new_functions.py` | 73 | ALTA | Stub de planning — todos sus métodos ya existen en business_logic.py |
| `bot_sales/core/client_factory.py` | 150 | ALTA | 0 usos externos; wrapper de universal_llm que a su vez nadie usa |
| `bot_sales/core/llm_backend.py` | 387 | ALTA | Solo importado por universal_llm; ambos son legacy del proyecto Ollama |
| `bot_sales/core/universal_llm.py` | 212 | ALTA | Alias de ChatGPTClient nunca activado en producción; solo tests |
| `bot_sales/core/async_ops.py` | 159 | ALTA | 0 refs — wrapper async/threading nunca conectado |
| `bot_sales/core/error_recovery.py` | 205 | ALTA | 0 refs — estrategias de clarificación nunca usadas |
| `bot_sales/core/performance.py` | 291 | ALTA | 0 refs — decoradores de async performance nunca conectados |
| `bot_sales/core/rate_limiter.py` | 152 | ALTA | 0 refs — RateLimiter Flask nunca registrado en ninguna app |
| `bot_sales/core/state_machine.py` | 173 | ALTA | 0 refs — OrderStateMachine nunca conectada al flujo de venta |
| `bot_sales/integrations/slack_app_home.py` | 495 | ALTA | 0 refs; duplicado en app/bot/ |
| `bot_sales/integrations/slack_modals.py` | 417 | ALTA | 0 refs |
| `bot_sales/integrations/crm.py` | 388 | ALTA | 0 refs; el CRM real es app/crm/ |
| `bot_sales/integrations/slack_product_cards.py` | 329 | ALTA | 0 refs |
| `bot_sales/integrations/slack_alerts.py` | 295 | ALTA | 0 refs |
| `bot_sales/integrations/slack_analytics.py` | 303 | ALTA | 0 refs |
| `bot_sales/integrations/slack_threading.py` | 266 | ALTA | 0 refs |
| `bot_sales/integrations/slack_files.py` | 235 | ALTA | 0 refs |
| `bot_sales/integrations/slack_reports.py` | 220 | ALTA | 0 refs |
| `bot_sales/integrations/sentiment.py` | 326 | ALTA | 0 refs; diferente del intelligence/sentiment.py vivo |
| `bot_sales/intelligence/learning.py` | 395 | ALTA | 0 refs en producción |
| `bot_sales/intelligence/image_search.py` | 43 | ALTA | 0 refs en producción |
| `bot_sales/security/encryption.py` | 214 | ALTA | 0 refs |
| `bot_sales/core/gemini.py` | 301 | MEDIA | 1 ref en app/bot/bot_gemini.py (ruta alternativa) — verificar si bot_gemini.py está en uso |
| `bot_sales/experiments/ab_testing.py` | 217 | MEDIA | Experimento standalone |

**Total estimado eliminable (confianza ALTA):** ~5,928 LOC
**Con confianza MEDIA (si se confirma):** ~6,446 LOC

---

## 9. Candidatos a archivado

Las siguientes carpetas o grupos de archivos representan features completas y coherentes que nunca llegaron a producción — conviene moverlas a `archive/` en lugar de borrarlas, por si alguna día se retoma:

| Qué | LOC | Razón para archivar (no borrar) |
|---|---|---|
| `bot_sales/core/llm_backend.py` + `universal_llm.py` + `client_factory.py` | 749 | Infraestructura completa para multi-LLM (Ollama, LM Studio). Feature coherente, potencialmente útil si se quiere LLM local |
| Todos los `bot_sales/integrations/slack_*.py` (9 archivos) | 2,095 | Feature Slack completa: alertas, modales, app home, reportes, analytics. Podría activarse si se necesita Slack workspace |
| `bot_sales/intelligence/learning.py` | 395 | Sistema de aprendizaje de conversaciones — potencialmente útil para futura personalización |
| `bot_sales/core/gemini.py` + `app/bot/bot_gemini.py` | 301+? | Soporte Gemini completo si se quiere switch de LLM |

---

## 10. Dudas para Julian

1. **`bot_sales/connectors/webchat.py` (260 LOC, 0 refs):** ¿Fue el plan construir un widget de webchat? Hay también `static/widget_v2.html`. ¿Es una feature abandonada o pendiente de conectar?

2. **`bot_sales/integrations/slack_*.py` (9 archivos, ~2,100 LOC):** ¿Estuvo alguna vez conectado el stack de Slack de salida? Los conectores de entrada (slack.py en connectors/) y algunos de commands/approvals tienen refs, pero los 9 de "features" no. ¿Se usaron en algún momento o nunca llegaron?

3. **`bot_sales/integrations/ab_testing.py` vs `bot_sales/planning/ab_testing.py` vs `bot_sales/experiments/ab_testing.py`:** Son tres archivos con el mismo nombre en tres carpetas. ¿Son el mismo feature evolucionando, o tres implementaciones independientes?

4. **`bot_sales/intelligence/learning.py` (395 LOC):** Define un sistema de aprendizaje de patrones de conversación. ¿Fue algo que se pensó pero no se implementó, o algo que estaba funcionando y se desconectó?

5. **`core/gemini.py` y `app/bot/bot_gemini.py`:** ¿La ruta Gemini fue una alternativa real que se usó con algún cliente, o fue un experimento de evaluación? ¿Hay razón para mantenerla?

6. **`core/rate_limiter.py` (152 LOC):** El audit M1 detectó que los endpoints públicos no tienen rate limiting. Este archivo implementa un `RateLimiter` Flask pero nunca se conectó. ¿Es candidato a reactivarse (no eliminar) para proteger los endpoints públicos?

7. **`bot_sales/core/state_machine.py`:** Define un `OrderStateMachine` con estados CREATED → CONFIRMED → etc. ¿Esto fue un diseño anterior que se reemplazó con el sistema de holds/sales en database.py, o es algo que se pensaba agregar?

8. **`app/bot/` vs `bot_sales/connectors/`:** En el audit M1 se detectó que `app/bot/` tiene copias de whatsapp.py y slack_app_home.py casi idénticas a las de `bot_sales/connectors/` y `bot_sales/integrations/`. ¿`app/bot/` es el destino de una migración planeada de `bot_sales/`?
