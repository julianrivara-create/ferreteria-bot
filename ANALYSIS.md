# Análisis completo del codebase — Ferretería Sales Bot

> Generado el 2026-03-19 tras relevamiento real de todos los archivos clave.

---

## 1. Qué hace el sistema (descripción funcional)

Este es un **bot de ventas para una ferretería argentina**, con dos grandes capas:

### 1.1 Bot de ventas (producción)
- Recibe mensajes de clientes vía WhatsApp (Meta/Twilio), web chat o CLI
- Arma presupuestos multi-ítem en lenguaje natural ("necesito mecha 8mm + tornillos fischer")
- Detecta familias de productos, pide aclaraciones cuando faltan datos, sugiere complementos
- Acepta/rechaza presupuestos, persiste quotes en SQLite, genera eventos de revisión interna
- Soporta múltiples tenants (ferretería, carnicería, tienda tech) via YAML profiles
- Dos backends de LLM: OpenAI (ChatGPT) y Google Gemini, con fallback a respuestas mock

### 1.2 GUI de entrenamiento (bot learning interface)
El sistema tiene una **interfaz de entrenamiento** accesible en `/ops/ferreteria/training/` que permite:
1. **Sandbox**: Operadores prueban conversaciones reales sin afectar producción
2. **Revisión de respuestas**: Marcan qué estuvo mal en cada respuesta del bot
3. **Casos**: Los errores revisados se convierten en "casos" de entrenamiento
4. **Correcciones (Suggestions)**: Los casos generan sugerencias de cambio al knowledge base (sinónimos, FAQs, reglas de aclaración, etc.)
5. **Apply**: Las sugerencias aprobadas se escriben atómicamente a los archivos YAML del knowledge base
6. **Regression**: Los casos se pueden exportar como fixtures de pytest para CI
7. **Impacto**: Vista de métricas antes/después de cada corrección aplicada
8. **Términos no resueltos**: Lista de frases de clientes que el bot no pudo identificar

### 1.3 CRM integrado
Sistema completo con contactos, deals, tasks, automations, webhooks, scoring, SLA, reporting.

---

## 2. Arquitectura

```
/
├── bot_sales/               ← Core del bot (multi-tenant)
│   ├── bot.py               ← Orchestrator principal (ChatGPT + ferretería routing)
│   ├── bot_gemini.py        ← Orchestrator alternativo (Gemini)
│   ├── ferreteria_quote.py  ← Motor de presupuestos ferretería
│   ├── core/
│   │   ├── database.py      ← SQLite: stock, holds, sales, sessions
│   │   ├── chatgpt.py       ← Cliente OpenAI con retry + mock fallback
│   │   ├── gemini.py        ← Cliente Gemini con retry + mock fallback
│   │   ├── business_logic.py← Funciones de negocio (buscar_stock, etc.)
│   │   └── tenancy.py       ← Gestión multi-tenant
│   ├── knowledge/
│   │   ├── loader.py        ← Carga YAML del knowledge base con caché mtime
│   │   └── validators.py    ← Validación estricta de cada dominio
│   ├── training/
│   │   ├── store.py         ← SQLite para training: sessions, reviews, suggestions, etc.
│   │   ├── session_service.py ← Ejecución de sandboxes aislados
│   │   ├── suggestion_service.py ← Lifecycle de sugerencias (draft→approved→applied)
│   │   └── review_service.py    ← Gestión de casos revisados
│   └── persistence/
│       └── quote_store.py   ← Persistencia de presupuestos con audit trail
│
├── app/
│   ├── main.py              ← Flask app factory
│   ├── api/
│   │   ├── ferreteria_training_routes.py ← API REST para training
│   │   └── ferreteria_admin_routes.py    ← API REST para admin
│   └── ui/
│       ├── ferreteria_training_routes.py ← Vistas Flask del training GUI
│       └── templates/ferreteria_training/ ← Templates HTML del training
│
├── data/tenants/ferreteria/
│   ├── knowledge/           ← YAML files editables (synonyms, FAQs, etc.)
│   ├── unresolved_terms.jsonl ← Log de términos no identificados
│   └── catalog.csv          ← Catálogo de productos
│
└── scripts/                 ← Herramientas CLI (generate_regression_fixtures, etc.)
```

---

## 3. Estado real del código (qué funciona, qué no)

### 3.1 Lo que ya funciona correctamente (NO tocar)

| Componente | Estado |
|---|---|
| `apply()` en suggestion_service | Escribe YAML atómicamente con fsync + backup. Funcional y testeado. |
| Retry en chatgpt.py | Backoff exponencial 3 reintentos + fallback mock con `logging.error` |
| Retry en gemini.py | Ídem — 3 reintentos con wait 1s/2s/4s + `raise RuntimeError` al agotar |
| Persistencia de sesiones (bot.py) | Usa `db.save_session()` / `db.load_session()` en cada turno |
| Persistencia de sesiones (bot_gemini.py) | Ídem — conectado a SQLite |
| Índices SQLite en database.py | Existen: idx_stock_category, idx_holds_expires, idx_holds_sku, etc. |
| SQL injection fix | `_ensure_stock_schema()` valida DEFAULT_CATEGORY con regex + escape |
| Holds scheduler | `app/services/holds_scheduler.py` completo con lock, atexit, APScheduler |
| `start_holds_scheduler()` en main.py | Sí, llamado en línea 111 |
| Training store schema | Todas las tablas existen: sessions, messages, reviews, suggestions, approvals, usage, regression_exports, knowledge_change_audit |
| generate_regression_fixtures.py | Completo y funcional con template de test, fixture de bot, y deduplicación |
| Unresolved terms UI | `/ops/ferreteria/training/unresolved-terms` — template y vista existen |
| API unresolved terms suggest | Endpoint `POST /training/unresolved-terms/suggest` existe en API routes |

### 3.2 Lo que FALTA implementar (gaps reales)

| Gap | Archivo afectado | Impacto |
|---|---|---|
| `store.get_impact_metrics()` | `bot_sales/training/store.py` | La vista `/training/impact` lanza AttributeError al cargar |
| `store.create_orphan_review()` | `bot_sales/training/store.py` | `suggest_from_unresolved_term()` en API falla con AttributeError |
| `suggestion_service.create()` | `bot_sales/training/suggestion_service.py` | API llama `create()` pero el método se llama `create_suggestion()` |
| Template `impact.html` | `app/ui/templates/ferreteria_training/` | La página de impacto lanza TemplateNotFound |
| `bot.close()` method | `bot_sales/bot.py` | El fixture de regresión llama `bot.close()` — no existe |

---

## 4. Debilidades específicas

### 4.1 Bugs críticos (rompen funcionalidad)
1. **`store.get_impact_metrics()` no existe** → La página `/training/impact` siempre lanza error
2. **`store.create_orphan_review()` no existe** → Crear correcciones desde términos no resueltos falla
3. **`suggestion_service.create()` es un alias roto** → El endpoint llama `create()` pero el método es `create_suggestion()`
4. **`impact.html` no existe** → La vista impacto lanza `TemplateNotFound`
5. **`bot.close()` no existe** → El fixture de regresión generado por `generate_regression_fixtures.py` falla al teardown

### 4.2 Deuda técnica menor
- `MAX_CONTEXT_MESSAGES = 10` en config.py es muy bajo para conversaciones largas
- `bot_gemini.py` no tiene `_is_ferreteria_runtime()` ni el flujo de presupuestos ferretería
- El mock de Gemini en línea 136 tiene `print(f"DEBUG MOCK: ...")` que aparece en logs de producción
- La vista de impacto no tiene datos históricos reales sin `get_impact_metrics()`

### 4.3 Lo que el plan original (PLAN_FASE1_2.md) decía que faltaba pero ya está hecho
- SQL Injection fix (1.1): DONE en database.py
- Persistir sesiones (1.2): DONE en bot.py y bot_gemini.py
- Índices SQLite (1.3): DONE en database.py
- Holds cleanup (1.4): DONE en holds_scheduler.py + main.py
- Mock fallback silencioso (1.5): DONE en chatgpt.py y gemini.py
- Regression fixtures script (2.2): DONE en scripts/generate_regression_fixtures.py
- Unresolved terms UI (2.4): DONE en training_routes.py + unresolved_terms.html

---

## 5. Plan de mejoras — de bueno a excelente

### Fase 1 — Foundation & Core (Bugs críticos)

| Item | Dificultad | Impacto |
|---|---|---|
| 1.1 Agregar `store.get_impact_metrics()` | Media | Desbloquea dashboard de impacto |
| 1.2 Agregar `store.create_orphan_review()` | Baja | Desbloquea flujo desde términos no resueltos |
| 1.3 Agregar alias `suggestion_service.create()` | Muy baja | Desbloquea API de suggest desde términos |
| 1.4 Crear template `impact.html` | Media | Habilita vista de impacto completa |
| 1.5 Agregar `SalesBot.close()` | Muy baja | Fixture de regresión funciona correctamente |
| 1.6 Remover `print()` de debug en gemini.py | Muy baja | Limpieza de logs de producción |

### Fase 2 — Learning & GUI Enhancement

| Item | Dificultad | Impacto |
|---|---|---|
| 2.1 Mejorar `get_impact_metrics()` con ventana temporal | Media | Métricas de calidad más precisas |
| 2.2 Dashboard de impacto con visualización de tendencias | Alta | Feedback loop visible para operadores |
| 2.3 Filtros y búsqueda en lista de términos no resueltos | Baja | UX del flujo de entrenamiento |
| 2.4 Auto-sugerir dominio desde failure_tag en GUI | Media | Reduce fricción al crear correcciones |
| 2.5 Métricas de coverage: % respuestas correctas por semana | Alta | KPI principal del entrenamiento |

### Fase 3 — Productización (futura)

- Migración a PostgreSQL para multi-tenant con aislamiento real
- API de webhooks para notificar cambios de knowledge base
- Integración CI/CD con generate_regression_fixtures en cada deploy
- Dashboard de CRM conectado a métricas de conversión del bot

---

## 6. Conclusión

El sistema está significativamente más completo de lo que el `PLAN_FASE1_2.md` asumía. La mayoría de las mejoras de Fase 1 (SQL injection, persistencia, índices, holds cleanup, mock logging) ya están implementadas. Los gaps reales son **5 bugs puntuales** que bloquean páginas y flujos específicos del training GUI, más la ausencia del template `impact.html`. Implementar estos 5 fixes y el template completa el loop de entrenamiento que es el valor diferencial del sistema.
