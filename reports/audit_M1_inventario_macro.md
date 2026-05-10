# Audit M1 — Inventario macro y por carpeta

**HEAD:** `9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb`
**Generado:** 2026-05-09

---

## Resumen

- **Dos paquetes dominantes** (`bot_sales/` + `app/`) concentran ~70,766 LOC (~73% del total real de ~96,831 LOC), y son los únicos VIVOS a nivel de runtime de producción.
- **`Planning/` (root) es un fósil duplicado** de `bot_sales/planning/`: mismo contenido pero divergido en 3 puntos clave; las pruebas de `tests_finalprod/` testean el código VIEJO de `Planning/`, no el live.
- **466 MB en `data/`**, casi todo `ferreteria.db` (338 MB) con su WAL sin checkpointear (13 MB) — señal de shutdown sucio o WAL muy activo. Hay también DBs de farmacia, ropa, iphone_store y default, sugiriendo historia multi-rubro.
- **8 worktrees de Claude** abandonados en `.claude/worktrees/` — copias completas del código, no afectan runtime pero consumen espacio en disco.
- **`app/bot/` y `bot_sales/connectors/`** comparten archivos aparentemente duplicados (`whatsapp.py`, `slack_app_home.py`) con tamaños idénticos o casi idénticos.
- **`wsgi_legacy.py`** sigue cargado como fallback en `wsgi.py` (producción) — deuda técnica activa que puede enmascarar errores de inicialización.
- **`bot_sales/maintenance/`** existe como carpeta pero está vacía excepto por `__pycache__` — hay un `maintenance/` top-level separado que sí está VIVO.

---

## 1. Estado git

```
Branch: main (up to date with origin/main)
Working tree: clean — nothing to commit

Commits recientes:
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

**Patrón observable:** Los últimos 10 commits son todos hotfixes DT-XX sobre el motor de cotización (`ferreteria_quote.py`). El repo está en modo estabilización/bugfix, no en feature development activo.

---

## 2. Tamaños top-level

| Carpeta | Tamaño | Descripción inferida |
|---|---|---|
| `data/` | **466 MB** | SQLite DBs de runtime (ferreteria.db=338MB, farmacia, ropa, iphone_store) + WAL files |
| `bot_sales/` | 6.1 MB | Paquete core del bot: lógica de conversación, quote engine, connectors |
| `app/` | 5.1 MB | Flask server, CRM completo, API, UI admin, workers |
| `output/` | 2.3 MB | Screenshots Playwright + imágenes de demo de training UI |
| `tests/` | 2.2 MB | Suite principal de tests |
| `tmp/` | 1.8 MB | Archivos temporales |
| `tests_finalprod/` | 868 KB | Suite de tests de producción final (separada) |
| `scripts/` | 476 KB | Tooling de dev/ops: bootstrap, smoke, seed, validación |
| `config/` | 704 KB | catalog.csv + faqs.json + policies.md (sin .py) |
| `maintenance/` | 404 KB | Watchdog, health checks, remediación automática |
| `docs/` | 304 KB | Documentación, guías, pitches (sin .py) |
| `Planning/` | 188 KB | **DUPLICADO FÓSIL** de `bot_sales/planning/` |
| `website/` | 148 KB | Landing page + checkout HTML/CSS/JS (1 .py de 25 LOC) |
| `reports/` | 120 KB | Reportes de auditoría generados durante desarrollo |
| `examples/` | 84 KB | Scripts demo offline (no importados por runtime) |
| `archive/` | 80 KB | Scripts PowerShell archivados |
| `dashboard/` | 80 KB | Dashboard Flask (2 .py, 612 LOC) |
| `experiments/` | 40 KB | Exploración Ollama (1 .py, 338 LOC) |
| `template-generator/` | 44 KB | Generador de scaffolding para nuevos bots |
| `static/` | 16 KB | `widget_v2.html` |
| `__pycache__/` | 16 KB | Cache Python root |
| `migrations/` | 8 KB | Alembic (1 .py, 174 LOC) |
| `tenants/` | 4 KB | `atelier.yaml` — config de tenant |
| `state/` | 4 KB | `state.json` — estado runtime serializado |

---

## 3. Archivos sueltos en root

### Archivos `.py` en root

| Archivo | LOC | Rol |
|---|---|---|
| `wsgi.py` | 137 | **Entrypoint de producción** — carga `app.main`, fallback a `wsgi_legacy` |
| `wsgi_legacy.py` | 122 | Entrypoint legacy (Flask directo sobre `bot_sales.bot`), solo referenciado por `wsgi.py` |
| `generate_pptx.py` | 86 | Generador de presentación PowerPoint (pitch/demo) — herramienta standalone |
| `whatsapp_server.py` | 34 | Entrypoint alternativo: servidor WhatsApp directo (sin CRM/app stack) |
| `gunicorn.conf.py` | 6 | Configuración Gunicorn (workers, timeout) |
| `bot_cli.py` | 8 | CLI para interactuar con el bot desde terminal |

### Archivos no-`.py` en root

| Archivo | Tipo | Rol |
|---|---|---|
| `README.md` | Markdown | Documentación principal |
| `PENDIENTES.md` | Markdown | Backlog/TO-DOs activos |
| `CHANGELOG.md` | Markdown | Historial de cambios |
| `PLAN_FASE1_2.md` | Markdown | Plan de fases de desarrollo |
| `P0_P1_COMPLETION.md` | Markdown | Estado de tareas P0/P1 |
| `ANALYSIS.md` | Markdown | Análisis técnico |
| `SECURITY_AUDIT.md` | Markdown | Auditoría de seguridad |
| `CONTRIBUTING.md` | Markdown | Guía de contribución |
| `QUICKSTART.md` | Markdown | Guía de arranque rápido |
| `context.md` | Markdown | Contexto del proyecto |
| `SESSION_SUMMARY_2026-05-01.md` | Markdown | Resumen de sesión dev |
| `SESSION_SUMMARY_2026-05-03.md` | Markdown | Resumen de sesión dev |
| `docker-compose.yml` | YAML | Config Docker local (bot + redis + dashboard) |
| `railway.json` | JSON | Config deploy Railway (gunicorn → `wsgi:app`) |
| `tenants.yaml` | YAML | Config multi-tenant |
| `faqs.json` | JSON | FAQs del bot (duplica `config/faqs.json`?) |
| `requirements.txt` | Text | Dependencias producción |
| `requirements-dev.txt` | Text | Dependencias desarrollo |
| `requirements_enterprise.txt` | Text | Dependencias versión enterprise |
| `pytest.ini` | INI | Configuración pytest |
| `alembic.ini.finalprod` | INI | Config Alembic renombrada (no es `alembic.ini` estándar) |
| `.env.example` | Env | Template de variables de entorno |
| `Dockerfile` | Docker | Build de la imagen |
| `analytics_test_export.csv` | CSV | Export de datos analytics |
| `platform_features_presentation.html` | HTML | Presentación de features |
| `platform_features.pdf` | PDF | Versión PDF de la presentación |
| `demo_conversacion_dificil.mp4` | Video | Grabación de demo |

---

## 4. Top 30 archivos `.py` más grandes

(Excluyendo `.venv/`, `.venv-test/`, `.benchmarks/`, `.claude/worktrees/`)

| # | Path | LOC |
|---|---|---|
| 1 | `app/crm/api/routes.py` | 4,078 |
| 2 | `bot_sales/bot.py` | 2,809 |
| 3 | `app/api/console_routes.py` | 2,778 |
| 4 | `bot_sales/ferreteria_quote.py` | 2,366 |
| 5 | `app/ui/ferreteria_training_routes.py` | 2,206 |
| 6 | `bot_sales/training/store.py` | 1,266 |
| 7 | `bot_sales/core/database.py` | 1,016 |
| 8 | `bot_sales/core/business_logic.py` | 953 |
| 9 | `scripts/demo_test_suite.py` | 936 |
| 10 | `template-generator/create_bot.py` | 875 |
| 11 | `app/crm/models.py` | 861 |
| 12 | `examples/demo_cli_offline.py` | 765 |
| 13 | `bot_sales/core/chatgpt.py` | 748 |
| 14 | `bot_sales/training/demo_bootstrap.py` | 677 |
| 15 | `bot_sales/persistence/quote_store.py` | 648 |
| 16 | `maintenance/watchdog.py` | 643 |
| 17 | `app/crm/services/automation_service.py` | 620 |
| 18 | `bot_sales/planning/flow_manager.py` | 611 |
| 19 | `Planning/flow_manager.py` | 611 ⚠️ DUPLICADO DIVERGIDO |
| 20 | `bot_sales/routing/turn_interpreter.py` | 518 |
| 21 | `tests/test_ferreteria_setup.py` | 1,026 |
| 22 | `tests/test_ferreteria_training.py` | 1,039 |
| 23 | `bot_sales/knowledge/defaults.py` | 1,152 |
| 24 | `app/bot/connectors/whatsapp.py` | 515 |
| 25 | `bot_sales/connectors/whatsapp.py` | 555 |
| 26 | `bot_sales/integrations/slack_app_home.py` | 495 |
| 27 | `app/bot/integrations/slack_app_home.py` | 495 ⚠️ MISMO TAMAÑO |
| 28 | `maintenance/watchdog.py` | 643 |
| 29 | `maintenance/runner.py` | 542 |
| 30 | `bot_sales/tests/test_turn_interpreter_v2.py` | 513 |

**Total LOC real (sin venvs/worktrees):** ~96,831

---

## 5. Por carpeta principal

| Carpeta | .py count | LOC | Rol | Estado | Duplicación con |
|---|---|---|---|---|---|
| `app/` | 138 | 30,191 | Flask server + CRM completo + API + UI admin + webhooks + workers | **VIVO** — es el entrypoint de producción (`app/main.py → wsgi.py`) | `app/bot/` duplica parte de `bot_sales/connectors/` |
| `bot_sales/` | 163 | 40,575 | Core bot runtime: conversación, quote engine, training, connectors, persistence, observabilidad | **VIVO** — importado por `app/`, `wsgi.py`, `whatsapp_server.py` | `bot_sales/planning/` duplicada en `Planning/` root |
| `dashboard/` | 2 | 612 | Dashboard Flask thin (viejo) | **MIXTO** — importado por `wsgi.py`, `app/main.py`, tests; muy pequeño (2 archivos) | — |
| `tests/` | 37 | 6,591 | Suite principal de tests | **VIVO** — pytest activo, tests recientes | Solapa con `tests_finalprod/` |
| `tests_finalprod/` | 28 | 4,407 | Suite de tests "final prod" (separada) | **MIXTO** — referencia `Planning/` (fósil), no `bot_sales/planning/` | `tests/` |
| `scripts/` | 29 | 5,533 | Tooling de dev/ops: bootstrap, smoke, seed, validación, deployment | **MIXTO** — no importado por runtime, usado manualmente | — |
| `data/` | 0 | — | SQLite DBs de runtime + WAL files + logs | **VIVO** — directorio de datos en vivo | — |
| `config/` | 0 | — | catalog.csv + faqs.json + policies.md | **VIVO** — consumido por knowledge loader de `bot_sales/` | `faqs.json` existe también en root |
| `docs/` | 0 | — | Documentación técnica, pitches, guías, roadmaps | **FÓSIL** (código) — solo .md/.pdf, no importado | — |
| `maintenance/` | 21 | 3,588 | Watchdog, health checks, DB maintenance, métricas, remediación | **VIVO** — importado por `app/api/console_routes.py` | `bot_sales/maintenance/` (vacía, confusa) |
| `archive/` | 0 | — | Scripts PowerShell archivados | **FÓSIL** — no importado, no .py | — |
| `examples/` | 6 | 1,919 | CLI offline demo, ejemplos de uso | **FÓSIL** — no importado por runtime | — |
| `experiments/` | 1 | 338 | Exploración Ollama/LLM local | **FÓSIL** — standalone, no integrado | `bot_sales/experiments/` (1 archivo `ab_testing.py`) |
| `template-generator/` | 1 | 875 | Scaffolding para crear nuevos bots desde template | **FÓSIL** (para este repo) — herramienta standalone | — |
| `website/` | 1 | 25 | Landing page pública + checkout HTML/CSS/JS | **VIVO** — servida por `app/main.py` como static folder | — |
| `tenants/` | 0 | — | `atelier.yaml` — config de un tenant | **MIXTO** — solo 1 archivo; config principal en `tenants.yaml` root y `data/tenants/` | `data/tenants/`, `tenants.yaml` root |
| `migrations/` | 1 | 174 | Alembic DB migrations | **MIXTO** — existe pero `alembic.ini` renombrado a `.finalprod`; flujo no estándar | — |
| `static/` | 0 | — | `widget_v2.html` — widget embebible | **MIXTO** — existe pero desconectado del flow claro | — |
| `state/` | 0 | — | `state.json` — estado runtime serializado | **MIXTO** — existe pero `bot_sales/state/` maneja estado en memoria/DB | — |
| `reports/` | 0 | — | Reportes de auditoría y baseline de tests generados durante desarrollo | **FÓSIL** (código) — artifacts de desarrollo | — |
| `Planning/` | 9 | 1,610 | **COPIA VIEJA** de `bot_sales/planning/` | **FÓSIL** — solo referenciada por `tests_finalprod/`; contenido divergido del live | `bot_sales/planning/` |

---

## 6. Hallazgos críticos

1. **`Planning/` root es una copia fósil divergida de `bot_sales/planning/`**
   - Los archivos son *casi* idénticos pero `flow_manager.py` divergió en 3 puntos: wording de preguntas, campos de entidades (`storage`/`condition` vs variantes genéricas), y texto de CTA.
   - `tests_finalprod/` apunta a `Planning/` (versión vieja) — significa que los tests de prod testean código que YA NO corre en producción.

2. **`app/bot/` dentro de `app/` duplica `bot_sales/connectors/`**
   - `app/bot/connectors/whatsapp.py` (515 LOC) vs `bot_sales/connectors/whatsapp.py` (555 LOC)
   - `app/bot/integrations/slack_app_home.py` (495 LOC) vs `bot_sales/integrations/slack_app_home.py` (495 LOC — mismo tamaño exacto)
   - No queda claro cuál está en uso real en el entrypoint `app/main.py`.

3. **`ferreteria.db` en `data/` pesa 338 MB con WAL sin checkpointear (13 MB)**
   - WAL activo o shutdown no limpio. Posible pérdida de datos en el último crash/restart si el WAL no se checkpointed.
   - Archivos "ferreteria 2.db-shm" y "ferreteria 2.db-wal" con 0 bytes — referencias zombi.

4. **8 worktrees de Claude en `.claude/worktrees/`** (`elated-hodgkin`, `focused-shtern`, `nervous-shtern`, `recursing-swartz`, `bold-babbage`, `heuristic-mclean`, `priceless-wiles`, `xenodochial-meitner`)
   - Copias completas del repo (incluyendo código) abandonadas. No afectan runtime pero consumen espacio y confunden herramientas de búsqueda/grep que no filtren `.claude/`.

5. **`wsgi_legacy.py` como fallback activo en producción**
   - `wsgi.py` tiene un try/except que cae a `wsgi_legacy` si `app.main` falla. En prod Railway, un error silencioso en el stack nuevo lo haría correr la versión legacy sin ningún aviso.

6. **`bot_sales/maintenance/` existe pero está vacía** (solo `__pycache__` de módulos que ya no existen — `backup.py`, `__init__.py` borrados pero cache presente)
   - La carpeta `maintenance/` real es top-level, no dentro de `bot_sales/`.

7. **`alembic.ini` renombrado a `alembic.ini.finalprod`** en root
   - El comando estándar `alembic upgrade head` no funciona sin pasar `-c alembic.ini.finalprod` explícitamente. Las migrations están probablemente corriendo con comandos no-estándar o directamente desde Python.

8. **Múltiples `requirements*.txt`** (3 archivos: `requirements.txt`, `requirements-dev.txt`, `requirements_enterprise.txt`)
   - Sin ver el contenido, no queda claro qué usa Railway en producción vs cuál es el correcto.

9. **`faqs.json` existe en dos lugares**: root (`./faqs.json`) y `config/faqs.json`
   - Posible desincronización si el bot lee de uno y el entrenamiento escribe en el otro.

10. **DBs de otras verticales en `data/`**: `farmacia.db` (13 MB), `ropa.db` (13 MB), `iphone_store.db` — con WAL activos o pesados. Si el bot actual es solo "ferreteria", estas podrían ser residuos de testing multi-rubro que conviene limpiar.

---

## 7. Dudas para Julian

1. **`app/bot/` vs `bot_sales/connectors/`**: ¿`app/bot/` es una refactorización que va a reemplazar `bot_sales/connectors/` o son dos caminos paralelos mantenidos a propósito? Los archivos de WhatsApp y Slack tienen tamaños casi idénticos, ¿son los mismos?

2. **`Planning/` (root) vs `bot_sales/planning/`**: ¿La carpeta `Planning/` en root fue alguna vez la fuente de verdad y luego se movió a `bot_sales/planning/`? Si ya está muerta, ¿se puede borrar? (El único que la usa es `tests_finalprod/`, que aparentemente testea el código viejo.)

3. **`tests/` vs `tests_finalprod/`**: ¿Cuál es la suite canónica que se corre en CI? ¿`tests_finalprod/` va a reemplazar `tests/` o conviven? Los nombres sugieren que `tests_finalprod/` es "la" suite final pero el tamaño es menor (4,407 vs 6,591 LOC).

4. **`data/ferreteria.db` de 338 MB**: ¿Es producción real o datos de testing/desarrollo? Un WAL de 13 MB sin checkpointear en 338 MB de DB sugiere que la última sesión no hizo checkpoint limpio.

5. **`faqs.json` en root vs `config/faqs.json`**: ¿Cuál lee el bot en runtime? ¿Son el mismo archivo o divergieron?

6. **`maintenance/` top-level**: ¿Es el sistema de watchdog activo que corre en Railway, o es una herramienta que se ejecuta manualmente? El `runner.py` (542 LOC) y `watchdog.py` (643 LOC) sugieren un proceso independiente.

7. **`bot_sales/maintenance/`** vacía con `__pycache__` de `backup.py`: ¿Hubo alguna vez un módulo de backup ahí que se borró del código pero no del cache? ¿Existe backup logic en otro lugar?

8. **Los 8 worktrees en `.claude/worktrees/`**: ¿Se pueden borrar? Son copias del repo de sesiones anteriores de Claude Code, no afectan nada pero ocupan espacio y pueden confundir greps globales.
