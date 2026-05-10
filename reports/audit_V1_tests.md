# Audit V1 — Estado de los tests

**HEAD:** 9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb
**Fecha audit:** 2026-05-09
**Total archivos test analizados:** 91
**Total LOC de tests:** 18 567 (17 458 en suites formales + 1 109 en scripts/demo + scripts/test_multimedia_flow)

## Resumen ejecutivo
- Suite oficial (según pytest.ini): `tests/` + `bot_sales/tests/`
- Total tests en suite oficial: ~759 funciones `test_*` (306 en `tests/`, 453 en `bot_sales/tests/`)
- Tests duplicados detectados: 0 pares (sin colisión de nombres entre carpetas)
- Tests obsoletos (importan módulos muertos): 1 (`tests/test_integration.py` importa `bot_sales.core.state_machine` — módulo existe pero el test usa API legacy)
- Tests skipeados: 1 decorador `@pytest.mark.skip` + 7 `pytest.skip()` condicionales en runtime
- Gaps de cobertura aparente: ~25 archivos de producción sin test directo nombrado (muchos cubiertos indirectamente)
- CI configurado: No

## 1. Inventario

| Carpeta | Archivos test | LOC totales | Estado |
|---------|---------------|-------------|--------|
| tests/ | 32 (30 raíz + 2 subdir) | 6 591 | activa — suite oficial |
| tests_finalprod/ | 25 | 4 407 | activa — CRM hardening + planning; **FUERA** del pytest.ini |
| bot_sales/tests/ | 33 | 6 460 | activa — suite oficial |
| app/bot/tests/ | 0 | — | vacía (solo `__pycache__`) |
| scripts/test_multimedia_flow.py | 1 | 173 | script suelto, no en pytest path |
| scripts/demo_test_suite.py | 1 (10 casos S01-S10) | 936 | suite custom standalone, no pytest |

**Notas:**
- `tests_finalprod/` tiene 94 funciones `test_*` (CRM + planning) pero **no figura en `testpaths`** del `pytest.ini`. Se ejecuta solo si se invoca explícitamente.
- `tests/mail/` (2 archivos, 430 LOC, 27 tests) y `tests/crm/` (sin tests propios, solo `utils.py` de 3 líneas que reexporta desde `tests_finalprod`) están dentro del path oficial pero son subcarpetas de `tests/`.
- `tests/regression/` solo tiene un `conftest.py`; los fixtures de regresión se generan con `scripts/generate_regression_fixtures.py` y al momento del audit no hay archivos `test_*.py` generados.

## 2. Configuración

### pytest.ini
```ini
[pytest]
testpaths =
    tests
    bot_sales/tests
norecursedirs =
    carniceria
    carniceria_bot
    archive
    .venv
    venv
addopts = -ra --import-mode=importlib
markers =
    slow: marks tests that make real LLM API calls (deselect with -m "not slow")
filterwarnings =
    ignore:unclosed database in <sqlite3\.Connection object.*:ResourceWarning
```

**Observaciones:**
- `tests_finalprod/` no está en `testpaths` — sus 94 tests no corren por defecto con `pytest`.
- Solo hay un marker definido: `slow`. El marker `parametrize` es built-in.
- `--import-mode=importlib` evita conflictos de namespace entre carpetas.
- `norecursedirs` excluye `carniceria` y `carniceria_bot` (tenant hermano) pero no excluye `scripts/`.

### conftest.py por carpeta

**`tests/conftest.py`**
- Fixtures: `sample_product`, `sample_customer`, `mock_chatgpt_client`, `temp_db`
- `isolate_unresolved_log` (autouse) — redirige `FERRETERIA_UNRESOLVED_LOG` a `tmp_path` para aislar estado entre runs
- Importa `bot_sales.core.chatgpt.ChatGPTClient` y `bot_sales.core.database.Database` — ambos módulos existen

**`tests_finalprod/crm/conftest.py`**
- Sets env vars mínimas para Flask CRM: `DATABASE_URL`, `SECRET_KEY`, `CRM_JWT_SECRET`, `CRM_WEBHOOK_SECRET` (todos con valores de test hardcodeados, no reales)
- Fixtures: `session_factory` (SQLite in-memory), `app` (Flask test app), `client` (test client)
- Importa directamente los blueprints CRM → si el CRM no inicia, toda la suite `tests_finalprod/crm/` falla en collect

**`tests/regression/conftest.py`**
- Solo docstring: referencia a `scripts/generate_regression_fixtures.py`. Sin fixtures activas.

## 3. Markers

| Marker | Usos | Descripción inferida |
|--------|------|---------------------|
| slow | 33 | Tests que hacen llamadas reales a LLM (OpenAI/Gemini). Se saltean en CI local con `-m "not slow"`. Todos en `bot_sales/tests/` |
| parametrize | 10 | Built-in pytest, uso estándar de parametrización. Presente en `tests/` y `bot_sales/tests/` |
| skip | 1 | Decorador explícito en `tests/test_p0_p1_blockers.py` (ver sección 4) |

**Nota:** El marker `integration` no está registrado ni se usa. No hay `xfail` en ninguna suite.

## 4. Tests skipeados

| Archivo:función | Motivo declarado | Tipo |
|----------------|-----------------|------|
| `tests/test_p0_p1_blockers.py:~359` | "Runtime is now Ferretería-only; generic TenantManager/KnowledgeLoader multi-tenant contract no longer applies. Covered by test_ferreteria_training.py." | `@pytest.mark.skip` permanente |
| `tests/test_integration.py:37` | "No products found" (guard condicional) | `pytest.skip()` condicional |
| `tests/test_business_logic.py:59` | "No products in test database" (guard condicional) | `pytest.skip()` condicional |
| `tests/test_business_logic.py:64` | "All products in fallback catalog have stock_qty=0" | `pytest.skip()` condicional |
| `bot_sales/tests/test_turn_interpreter_v2.py:253` | "OPENAI_API_KEY not set" | `pytest.skip()` condicional |
| `bot_sales/tests/test_turn_interpreter_multi_item.py:136` | "OPENAI_API_KEY not set" | `pytest.skip()` condicional |
| `bot_sales/tests/test_f1_compound_routing.py:166,209,241` | Catálogo sin ítem ambiguo para cubrir ese path (3 guards) | `pytest.skip()` condicional |
| `bot_sales/tests/test_l1_list_normalizer.py:180` | "Runtime bot unavailable" | `pytest.skip()` condicional |
| `bot_sales/tests/test_l2_ti_list_parsing.py:186` | "Runtime bot unavailable" | `pytest.skip()` condicional |

**Evaluación:**
- El skip permanente en `test_p0_p1_blockers.py` debería **eliminarse** (el test está muerto por decisión de diseño; documentar o eliminar la función entera).
- Los skips de `OPENAI_API_KEY not set` son correctos — son guards para no fallar en entornos sin clave.
- Los skips de `f1_compound_routing` son problemáticos: dependen de qué devuelva el catálogo en runtime. Si el catálogo cambia, los tests pueden pasar silenciosamente sin ejercer el path que documentan.

## 5. Duplicación entre carpetas

No se detectaron archivos con nombres idénticos entre `tests/`, `tests_finalprod/` y `bot_sales/tests/`. El comando `uniq -d` no retornó resultados.

**Sin embargo**, hay duplicación semántica (no de nombre) que merece atención:
- `tests/test_auth.py` y `tests_finalprod/crm/test_rbac.py` cubren autenticación/autorización desde ángulos distintos (bot-level vs CRM-level). No es duplicación, es complementariedad.
- `tests/crm/utils.py` es un wrapper de 3 líneas que reexporta `tests_finalprod.crm.utils.seed_tenant_with_user`. Indica acoplamiento entre suites no incluidas en `testpaths`.

## 6. Tests obsoletos

| Test | Importa | Módulo existe | Evaluación |
|------|---------|--------------|------------|
| `tests/test_integration.py` | `bot_sales.core.state_machine.get_state_machine` | Sí — `bot_sales/core/state_machine.py` existe | Módulo vivo pero el test usa API de integración old-style que puede estar desactualizada respecto a la implementación actual. Riesgo: medio. |

**Nota:** No se detectaron imports de módulos realmente eliminados. Los imports a `bot_sales.bot`, `bot_sales.runtime`, `bot_sales.core.database`, etc., apuntan todos a módulos existentes. El caso de `state_machine` es el único donde el test de integración (`test_integration.py`) puede estar ejerciendo un contrato de interfaz obsoleto sin que el módulo haya sido removido.

## 7. Cobertura aparente

### Módulos con test directo

| Archivo vivo | Test directo | Ubicación |
|-------------|-------------|-----------|
| `bot_sales/core/business_logic.py` | `test_business_logic.py` | `tests/` |
| `bot_sales/core/tenancy.py` | `test_tenancy.py` | `bot_sales/tests/` |
| `bot_sales/security/auth.py` | `test_auth.py` | `tests/` |
| `bot_sales/security/validators.py` | `test_validators.py` | `tests/` |
| `bot_sales/security/sanitizer.py` | `test_sanitizer.py` | `tests/` |
| `bot_sales/services/price_validator.py` | `test_price_validator.py` | `bot_sales/tests/` |
| `bot_sales/services/search_validator.py` | `test_search_validator.py` | `bot_sales/tests/` |
| `app/services/runtime_integrity.py` | `test_runtime_integrity.py` | `tests/` |
| `app/services/runtime_bootstrap.py` | `test_runtime_bootstrap_admin_policy.py` + `test_runtime_bootstrap_fail_closed.py` | `tests/` |
| `app/mail/gmail_client.py` | `test_gmail_client.py` | `tests/mail/` |
| `app/mail/mail_reader.py` | `test_mail_reader.py` | `tests/mail/` |
| `bot_sales/core/cache_manager.py` | `test_cache.py`, `test_performance.py` | `tests/` (importación directa) |
| `bot_sales/routing/turn_interpreter.py` | `test_turn_interpreter_v2.py`, `test_turn_interpreter_multi_item.py`, `test_turn_interpreter_routing.py`, `test_l2_ti_list_parsing.py` | múltiples |
| `bot_sales/planning/flow_manager.py` | `test_flow_manager_no_hallucination.py` | `bot_sales/tests/` |
| `bot_sales/ferreteria_dimensions.py` | `test_a2_regressions.py`, `test_matcher_dimensional.py` | `bot_sales/tests/` |
| `bot_sales/ferreteria_substitutions.py` | `test_ferreteria_phase2_families.py` | `tests/` (importación directa) |
| `bot_sales/planning/pipeline.py` | `test_planning_chitchat_guard.py` | `tests/` (importación directa) |

### Gaps — módulos sin test directo ni cobertura indirecta evidente

| Archivo vivo | Gap | Riesgo estimado |
|-------------|-----|----------------|
| `bot_sales/core/state_machine.py` | Sin test dedicado; solo referenciado en `test_integration.py` (API potencialmente desactualizada) | Alto — es la máquina de estados del bot |
| `bot_sales/core/async_ops.py` | Sin test | Medio |
| `bot_sales/core/gemini.py` | Sin test | Medio — backend LLM alternativo |
| `bot_sales/core/error_recovery.py` | Sin test | Alto — manejo de errores crítico en producción |
| `bot_sales/core/monitoring.py` | Sin test | Bajo |
| `bot_sales/core/new_functions.py` | Sin test | Desconocido — nombre vago, requiere inspección |
| `bot_sales/core/objections.py` | Sin test | Medio |
| `bot_sales/connectors/storefront_api.py` | `test_multi_tenant_storefront.py` importa el módulo pero cubre contrato HTTP, no lógica interna | Medio |
| `bot_sales/connectors/storefront_tenant_api.py` | Sin test | Medio |
| `bot_sales/handlers/escalation_handler.py` | Sin test directo (cubierto parcialmente via `test_escalation_safety_net.py`) | Medio |
| `bot_sales/handlers/offtopic_handler.py` | Sin test | Medio |
| `bot_sales/handlers/policy_handler.py` | Sin test | Medio |
| `bot_sales/observability/metrics.py` | Sin test | Bajo |
| `bot_sales/observability/turn_event.py` | Sin test | Bajo |
| `bot_sales/planning/followup_scheduler.py` | Sin test | Medio |
| `bot_sales/planning/playbook_router.py` | Sin test | Medio |
| `bot_sales/planning/intents.py` | Sin test | Medio |
| `bot_sales/training/review_service.py` | Sin test directo (cubierto parcialmente via training tests) | Bajo |
| `bot_sales/training/session_service.py` | Sin test | Medio |
| `bot_sales/persistence/quote_store.py` | Cubierto por importación en `test_ferreteria_vnext.py`, `test_ferreteria_training.py`, `test_ferreteria_phase5_automation.py` | Medio (indirecto) |
| `bot_sales/services/quote_automation_service.py` | Cubierto por importación en `test_ferreteria_phase5_automation.py` | Medio (indirecto) |
| `bot_sales/routing/acceptance_detector.py` | Cubierto via `test_b23_acceptance_guard.py` | Bajo (indirecto) |
| `app/crm/services/ab_variant_service.py` | Cubierto por `tests_finalprod/crm/test_ab_autopromote_service.py` — pero esta suite no está en pytest.ini | Medio |
| `app/crm/services/automation_service.py` | Ídem — cubierto en `tests_finalprod/` únicamente | Alto |
| `app/crm/services/webhook_service.py` | Ídem | Alto |
| `app/api/console_routes.py` | Cubierto por `tests_finalprod/crm/test_console_api.py` — fuera de pytest.ini | Medio |
| `app/services/catalog_service.py` | Sin test | Medio |

## 8. Smoke scripts

| Script | Existe | LOC | Qué cubre | Integrado en CI |
|--------|--------|-----|-----------|-----------------|
| `scripts/smoke_ferreteria.py` | Sí | 181 | Flujo completo del bot (saludo, búsqueda, cotización) sin servidor web; usa `get_runtime_bot` directamente | No |
| `scripts/smoke_runtime.py` | Sí | 67 | Endpoints HTTP vía Flask test client: `/health`, `/api/products`, `/api/t/farmacia/products`, etc. | No |
| `scripts/smoke_training_ui.py` | Sí | 169 | UI de training de ferretería: bootstrap demo, rutas API y UI del panel de entrenamiento, con Flask test client | No |
| `scripts/staging_smoke.py` | Sí | 205 | Checks contra entorno live (staging/producción) via requests HTTP reales con firma HMAC webhook | No |

**Ninguno de los 4 scripts está integrado en CI.** No existe `.github/workflows/`, `.circleci/`, ni `tox.ini`. El `railway.json` solo define build/deploy, sin paso de tests.

## 9. Suites custom

| Script | Existe | Tests/casos | Tipo | Integrado en CI | Estado |
|--------|--------|-------------|------|-----------------|--------|
| `scripts/demo_test_suite.py` | Sí | 10 casos (S01-S10) | Standalone, no pytest | No | Activa — consolidó `demo_test_suite.py` (31 casos) + `demo_test_suite_extended.py` (53 casos). Usa `StrictRegressionSuite` con grupos: anti_alucinacion (3), matcher_quirurgico (4), cierre_venta (3) |
| `scripts/demo_test_suite_extended.py` | No | — | — | — | Eliminado; consolidado en `demo_test_suite.py` según docstring |
| `scripts/test_multimedia_flow.py` | Sí | 2 funciones (`test_audio_flow`, `test_image_flow`) | Script standalone, importable por pytest | No | Legacy — no está en pytest path oficial, usa `MagicMock` para simular WhatsApp/audio |

**Nota sobre `demo_test_suite.py`:** No usa pytest. Sus casos S01-S10 tienen un runner propio (`StrictRegressionSuite`) que produce salida `PASS/WARN/FAIL/ERROR`. Los resultados no se integran en ningún informe de CI.

## 10. CI configuration

No se detectó CI configurado.

- No existe directorio `.github/`
- No existe `.circleci/`
- No existe `.gitlab-ci.yml`
- No existe `tox.ini` ni `Makefile`
- `railway.json` define build con Dockerfile y deploy con gunicorn, sin step de tests
- `docker-compose.yml` tiene healthcheck con curl pero no step de pytest

**Consecuencia:** Los tests solo se ejecutan manualmente. No hay gate de calidad antes de deploy.

## 11. Fixtures y data de tests

### Inventario de fixtures

| Carpeta | Fixtures definidas | Notas |
|---------|-------------------|-------|
| `tests/conftest.py` | 5 (`sample_product`, `isolate_unresolved_log` autouse, `sample_customer`, `mock_chatgpt_client`, `temp_db`) | `isolate_unresolved_log` es autouse — actúa en todos los tests de `tests/` |
| `tests_finalprod/crm/conftest.py` | 3 (`session_factory`, `app`, `client`) | SQLite in-memory; aplica monkeypatching de `SessionLocal` a 3 módulos |
| `tests/test_ferreteria_training.py` | 1 (`training_client`) | Fixture de nivel módulo |
| `tests/test_ferreteria_phase5_automation.py` | 1 (`automation_client`) | Fixture de nivel módulo |
| `tests/test_ferreteria_vnext.py` | 1 (`vnext_client`) | |
| `tests/test_business_logic.py` | 2 (`test_db`, `business_logic`) | |
| `tests/test_p0_p1_blockers.py` | 1 (`sample_db`) | |
| `tests/test_ferreteria_training_smoke.py` | 1 (`smoke_client`) | |
| `tests/test_app_multi_tenant_guards.py` | 1 (`app`) | |
| `tests_finalprod/crm/test_rbac_matrix_hardening.py` | 1 (inline en archivo) | |
| `bot_sales/tests/test_matcher_base.py` | 1 (`catalog_matcher`, scope=module) | |
| **Total** | **18 fixtures** | |

### Datos de test (archivos no-Python)

- No se encontraron archivos `.json`, `.yaml`, `.csv` o `.fixture*` dentro de `tests/` o `tests_finalprod/`.
- Los datos de catálogo se generan dinámicamente via `tmp_path` (pytest) o se leen del catálogo real en `data/tenants/ferreteria/catalog.csv`.
- `tests/regression/` tiene un `conftest.py` que referencia fixtures generadas por script externo, pero **no hay fixtures generadas actualmente** en esa carpeta.

### Datos potencialmente sensibles

- `tests/conftest.py` usa `api_key=""` (string vacío) al instanciar `ChatGPTClient` — correcto.
- `tests_finalprod/crm/conftest.py` hardcodea secrets con prefijo `ferreteria-tests-*` — son valores de test no reales, aceptable.
- Múltiples tests usan `"test-admin-token"` como `X-Admin-Token` — correcto para tests.
- No se detectaron credenciales reales ni API keys hardcodeadas.

### Fixtures duplicadas entre carpetas

- `session_factory` en `tests_finalprod/crm/conftest.py` cumple el mismo rol que `temp_db` en `tests/conftest.py` (base de datos temporal) pero son implementaciones independientes. No es un problema técnico.

## 12. Recomendaciones

### Suite oficial recomendada

Consolidar en **tres tiers claramente diferenciados**:

1. **Tier 1 — pytest oficial** (ya en `testpaths`): `tests/` + `bot_sales/tests/`
   - Agregar `tests_finalprod/` a `testpaths` o moverlo a `tests/crm/` y `tests/planning/`
2. **Tier 2 — smoke pre-deploy** (invocar desde CI antes de Railway deploy): `scripts/smoke_ferreteria.py` + `scripts/smoke_runtime.py`
3. **Tier 3 — regresión E2E manual**: `scripts/demo_test_suite.py` (requiere runtime con OPENAI_API_KEY)

### Tests a eliminar con confianza

- `tests/test_p0_p1_blockers.py` — la función con `@pytest.mark.skip` permanente (línea ~359): el motivo declarado indica que está muerta por diseño y cubierta en otro archivo. Eliminar esa función (no todo el archivo, que tiene 9 tests activos).
- `scripts/test_multimedia_flow.py` — si no se va a integrar a pytest, moverlo a un directorio `tests/connectors/` y hacerlo pytest-compatible, o eliminarlo. Actualmente es código muerto para cualquier runner CI.

### Tests a migrar/consolidar

- `tests_finalprod/crm/` → agregar a `testpaths` en `pytest.ini`. La suite tiene 94 tests de hardening que cubren CRM, webhooks, RBAC, scheduling, PII — módulos de alta criticidad que hoy NO corren con `pytest` a secas.
- `tests/crm/` → tiene solo `utils.py` (wrapper de 3 líneas). No tiene tests. Considerar eliminar el directorio y usar `tests_finalprod.crm.utils` directamente donde se necesite.
- `tests/regression/` → está preparado (conftest.py) pero vacío. Ejecutar `scripts/generate_regression_fixtures.py` y commitear los fixtures generados, o eliminar el directorio si el workflow está abandonado.

### Gaps de cobertura prioritarios

- **`bot_sales/core/error_recovery.py`** — sin test, riesgo alto. Es el módulo que maneja errores en producción.
- **`bot_sales/core/state_machine.py`** — solo cubierto por `test_integration.py` con API posiblemente desactualizada. Agregar tests unitarios directos.
- **`app/crm/services/automation_service.py`** y **`webhook_service.py`** — cubiertos en `tests_finalprod/` pero esa suite no corre por defecto. Solución inmediata: agregar `tests_finalprod` a `testpaths`.
- **`bot_sales/planning/intents.py`** y **`playbook_router.py`** — lógica de routing sin test. Riesgo medio-alto.
- **`app/services/catalog_service.py`** — sin test, módulo de integración con el catálogo real.
- **CI pipeline ausente** — cualquier deploy puede romper tests sin que nadie lo note. Implementar un workflow mínimo de GitHub Actions (o Railway pre-deploy hook) que ejecute `pytest tests/ bot_sales/tests/ -m "not slow"`.

## 13. Dudas para Julian

1. **`tests_finalprod/` intencional fuera de `testpaths`?** No está claro si fue una decisión deliberada (suite de "prod hardening" separada) o un olvido. Si es deliberada, ¿cuándo se ejecuta? ¿Hay un comando documentado en algún lugar?

2. **`tests/regression/`**: El conftest referencia `scripts/generate_regression_fixtures.py`. ¿Ese workflow está activo? ¿Se regeneran los fixtures antes de cada release o está abandonado? Al momento del audit, la carpeta no tiene tests ejecutables.

3. **`bot_sales/core/new_functions.py`**: El nombre es vago y no tiene tests. ¿Es código vivo o un artefacto de refactor a medio terminar?

4. **`app/bot/tests/`**: El directorio existe pero está completamente vacío (solo `__pycache__`). ¿Había tests ahí que fueron migrados? ¿Se puede eliminar el directorio?

5. **`scripts/demo_test_suite.py` vs pytest**: El docstring dice que consolida `demo_test_suite.py` (31 casos) + `demo_test_suite_extended.py` (53 casos) en 10 casos estrictos S01-S10. ¿Es esa reducción de 84 → 10 intencional o se perdieron casos que aún son relevantes?

6. **`tests/test_integration.py` con `state_machine`**: ¿Ese test sigue siendo representativo de cómo se usa `state_machine.py` hoy? Si el contrato de la interfaz cambió, el test puede pasar sin ejercer el comportamiento actual.

7. **CI**: ¿Hay plans de agregar GitHub Actions o un pre-deploy hook en Railway? Sin CI, los 855 tests analizados solo tienen valor si alguien los ejecuta manualmente antes de cada push.
