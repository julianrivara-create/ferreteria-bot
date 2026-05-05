# Auditoría de tests — pre-Bloque 2
**Fecha**: 2026-05-05
**Branch**: research/B2-test-audit
**Autor**: Claude Sonnet 4.6 (research agent)

---

## Resumen ejecutivo

| Métrica | Valor |
|---------|-------|
| Total tests existentes (bot_sales/tests/ + tests/) | ~570 |
| Tests que se **BORRAN** (junto a código eliminado) | ~60 |
| Tests que necesitan **MIGRARSE / REESCRIBIRSE** | 4 |
| Tests **NUEVOS a crear** (estimado) | ~20 |
| Tests E2E con riesgo de regresión | 15 archivos |
| Casos E2E strict (demo_test_suite.py) | 10 — todos siguen válidos |

### Distribución actual (bot_sales/tests/)
| Archivo | Tests | Tamaño |
|---------|-------|--------|
| test_search_validator.py | 84 | 395 líneas |
| test_ambiguity_clarification.py | 44 | 327 líneas |
| test_stale_prices.py | 29 | 297 líneas |
| test_price_validator.py | 28 | 127 líneas |
| test_a2_regressions.py | 19 | 260 líneas |
| test_matcher_dimensional.py | 16 | 209 líneas |
| test_anti_hallucination.py | 10 | 181 líneas |
| test_flow_manager_no_hallucination.py | 9 | 172 líneas |
| test_matcher_base.py | 8 | 378 líneas |
| test_handoff_negotiation.py | 6 | 149 líneas |
| test_turn_interpreter_multi_item.py | 5 | 219 líneas |
| test_r3_integration.py | 5 | 161 líneas |
| test_r2_integration.py | 5 | 150 líneas |
| test_quote_parser.py | 5 | 69 líneas |
| test_max_workers_override.py | 5 | 46 líneas |
| test_alternatives_safety.py | 5 | 87 líneas |
| test_tenancy.py | 1 | 52 líneas |
| test_routing.py | 1 | 75 líneas |
| **TOTAL bot_sales/tests/** | **285** | **3354 líneas** |

---

## Por bloque

---

### 2.1 TurnInterpreter

> Alcance: pulir `turn_interpreter.py` + `bot.py:666-700` (dispatch loop).

#### Archivos que tocan TurnInterpreter

| Archivo | Tests | Clases | Contenido |
|---------|-------|--------|-----------|
| `bot_sales/tests/test_turn_interpreter_multi_item.py` | 5 | TestTurnInterpreterMultiItemMocked (2), TestTurnInterpreterMultiItemRealLLM (3 slow) | Regresión max_tokens 200→1024 |
| `tests/test_turn_interpreter_routing.py` | 20 | TestTurnInterpreterParsing (11), TestShouldBypassSalesIntelligence (5), TestCriticalBypassRouting (4) | Parsing JSON, validez de intents, routing integration |

#### Decisiones

**`test_turn_interpreter_multi_item.py`** → **KEEP**
Los 2 tests de TestTurnInterpreterMultiItemMocked son guards de regresión permanentes (max_tokens, JSON parsing). Los 3 slow tests con LLM real son complementarios. No se ven afectados por 2.1.

**`TestTurnInterpreterParsing` (11 tests)** → **KEEP**
Unit tests de `_parse_response` + `TurnInterpretation.from_dict`. Seguirán siendo válidos independientemente del refactor. `test_customer_info_in_valid_intents` valida que `customer_info` esté en `VALID_INTENTS` — si 2.1 reestructura los intents válidos, revisar.

**`TestShouldBypassSalesIntelligence` (5 tests)** → **DELETE en 2.3** *(no en 2.1)*
Pertenece a Block 2.3. Ver detalle abajo.

**`TestCriticalBypassRouting` (4 tests)** → **MIGRATE en 2.3** *(no en 2.1)*
Pertenece a Block 2.3. Ver detalle abajo.

#### Gaps detectados en cobertura de TurnInterpreter

El agente 2.1 DEBE crear tests para:

| Gap | Descripción | Prioridad |
|-----|-------------|-----------|
| `current_state` context | Ningún test pasa `current_quote`, `last_intent`, `open_clarification` al interpreter | ALTA |
| `last_offered_products` | Ningún test valida que el interpreter recibe contexto de productos ofrecidos en turno anterior | ALTA |
| Compound message detection | Ningún test verifica que TurnInterpreter detecta mensajes compuestos ("dame el primero. agregame martillo") | ALTA — depende de 2.2 |
| Confidence fallback path | `test_customer_info_does_not_hit_offtopic_fallback` usa unknown/0.4 pero el fallback chain cambia en 2.3 | MEDIA |
| `escalate` vs `small_talk` disambiguation | No hay test para tono frustrante con confianza borderline (0.54-0.60) | MEDIA |
| `quote_reference` + `line_hints` | Ningún test valida que line_hints se extraen correctamente en mensajes ordinales | MEDIA |

**Recomendación**: El agente 2.1 puede reutilizar el patrón de `TestTurnInterpreterParsing` — mock LLM, JSON fabricado, assert en atributos del resultado. Zero API calls necesarios.

---

### 2.3 Pre-route helpers

> Alcance: eliminar `_looks_like_*`, `_should_bypass_*`, `_update_sales_preferences`, `_normalize_lookup_text`, y los `fq.looks_like_*` usados en `_try_ferreteria_pre_route`.

#### Helpers a eliminar (con ubicación)

| Helper | Archivo | Línea aprox. | Acción |
|--------|---------|-------------|--------|
| `_try_ferreteria_pre_route` | `bot_sales/bot.py` | 920 | Eliminar bloque completo |
| `_normalize_lookup_text` | `bot_sales/bot.py` | 1558 | Eliminar |
| `_looks_like_project_request` | `bot_sales/bot.py` | 1682 | Eliminar |
| `_should_bypass_sales_intelligence` | `bot_sales/bot.py` | 1708 | Eliminar |
| `_looks_like_product_request` | `bot_sales/bot.py` | 1720 | Eliminar |
| `_update_sales_preferences` | `bot_sales/bot.py` | 1828 | Eliminar |
| `_looks_like_price_objection` | `bot_sales/bot.py` | 1855 | Eliminar |
| `_looks_like_recommendation_request` | `bot_sales/bot.py` | 1871 | Eliminar |
| `_looks_like_comparison_request` | `bot_sales/bot.py` | 1889 | Eliminar |
| `fq.looks_like_acceptance` | `bot_sales/bot.py` | 994 (en pre_route) | Migrar a TurnInterpreter |
| `fq.looks_like_reset` | `bot_sales/bot.py` | 1015, 1106 | Migrar a TurnInterpreter |
| `fq.looks_like_additive` | `bot_sales/bot.py` | 770, 1163 | Migrar a TurnInterpreter |
| `fq.looks_like_clarification` | `bot_sales/bot.py` | 772, 1288 | Migrar a TurnInterpreter |
| `fq.looks_like_new_answer` | `bot_sales/bot.py` | 1106 | Migrar a TurnInterpreter |

**Nota**: Los `fq.looks_like_*` viven en `ferreteria_quote.py` — no se borran del módulo fuente (son usados en otras partes del quote state machine). Solo se eliminan los call-sites en `_try_ferreteria_pre_route` / dispatch loop de `bot.py`.

#### Tests afectados

Solo **un archivo** tiene tests de pre-route helpers: `tests/test_turn_interpreter_routing.py`

| Clase | Tests | Decisión | Motivo |
|-------|-------|----------|--------|
| `TestShouldBypassSalesIntelligence` | 5 | **DELETE** | Prueba directamente `bot._should_bypass_sales_intelligence()` que se elimina |
| `TestCriticalBypassRouting` | 4 | **MIGRATE** | Prueba el routing via process_message; el camino cambia cuando se elimina `_should_bypass_sales_intelligence` |

**TestCriticalBypassRouting — análisis detallado**:

| Test | Riesgo | Acción |
|------|--------|--------|
| `test_greeting_routes_to_offtopic_handler` | BAJO — mockea TurnInterpreter → small_talk → OfftopicHandler | Reescribir sin asumir `_should_bypass` |
| `test_customer_info_does_not_hit_offtopic_fallback` | ALTO — el comentario documenta explícitamente que el flujo pasa por `_should_bypass_sales_intelligence("me llamo")`. Ese bypass desaparece. | Reescribir: post-2.3, unknown/low-conf → TurnInterpreter decide si `customer_info` o escalates |
| `test_customer_info_falls_through_to_main_llm` | MEDIO — usa `customer_info` intent, que ya existe en VALID_INTENTS. El flujo cambia pero el resultado esperado es el mismo. | Reescribir sin monkeypatch de `_run_sales_intelligence` |
| `test_handoff_request_triggers_escalation_handler` | BAJO — mockea TurnInterpreter → escalate → EscalationHandler | KEEP sin cambios (el routing de escalate no depende de pre-route helpers) |

**Ningún otro test** en `bot_sales/tests/` ni `tests/` prueba los helpers `_looks_like_*` directamente. Los `fq.looks_like_*` del módulo `ferreteria_quote.py` no tienen tests unitarios propios en el corpus auditado — son testeados implícitamente via tests de multi-turn flow.

---

### 2.5 V4/V5/V7/V8

> Alcance: eliminar validators V4, V5, V7, V8 de `search_validator.py`. Portar reglas de negociación (V8) al prompt del TurnInterpreter.

#### test_search_validator.py — conteo por validator

| Validator | Propósito | Tests BLOCK | Tests PASS | Decisión |
|-----------|-----------|-------------|------------|----------|
| V1 (peso imposible) | Peso imposible para tipo de herramienta | 5 | 5 | **KEEP** |
| V2 (diámetro de broca) | Diámetro >100mm en broca | 2 | 1 (pass_broca_8mm) | **KEEP** |
| V3 (longitud de fijación) | Tornillo >2m | 2 | 1 (pass_tornillo_100mm) | **KEEP** |
| V4 (colores preciados) | Color precioso en herramienta manual metálica | 4 | 6* | **DELETE** |
| V5 (spec de almacenamiento) | GB/TB en herramienta | 2 | 0 | **DELETE** |
| V6 (watts imposibles) | Watts excesivos en eléctrica | 4 | 5 | **KEEP** |
| V7 (adjetivos absurdos) | Combinación imposible (inflable, cuántico, virtual) | 8 | 6 | **DELETE** |
| V8 (negociación) | detect_negotiation_intent regex | 14 DETECT | 7 NO-DETECT | **DELETE** — portar queries |
| L2 (validate_search_match) | Cross-reference post-search | 3 | 6 | KEEP V1-weight, **DELETE V4-color** |

\* Tests PASS de V4: `test_pass_tornillo_dorado`, `test_pass_llave_dorada`, `test_pass_tornillo_dorado_para_martillo`, `test_pass_alicate_mango_lila`, `test_pass_alicate_mango_morado`, `test_pass_bisagra_dorada`

**Conteo total DELETE de test_search_validator.py**:
- V4 block (4) + V4 pass (6) = 10
- V5 block (2) = 2
- V7 block (8) + V7 pass (6) = 14
- V8 detect (14) + V8 no-detect (7) = 21
- L2 color-mismatch (1) + L2 pass-color (1) = 2
- **Subtotal: 49 tests DELETE de test_search_validator.py**

**Conteo total KEEP de test_search_validator.py**:
- 84 total − 49 delete = **35 tests KEEP**

#### test_handoff_negotiation.py — 6 tests → DELETE completo

| Test | Contenido | Acción |
|------|-----------|--------|
| `test_handoff_response_when_negotiation_detected` | V8 dispara pre-LLM | DELETE |
| `test_carrito_preserved_after_handoff` | active_quote sobrevive V8 | DELETE |
| `test_no_counteroffer_in_response` | Sin % ni $ en respuesta V8 | DELETE |
| `test_llm_not_called_on_negotiation` | V8 cortocircuita TurnInterpreter | DELETE |
| `test_handoff_fires_for_all_patterns` | Subtest por patrón de negociación | DELETE |
| `test_no_handoff_for_price_objection` | E18/E21 no disparan V8 | DELETE |

**HANDOFF_RESPONSE tests**: Los dos tests de contenido de respuesta (`test_handoff_response_contains_asesor`, `test_handoff_response_no_price_invented`) en TestV8NegotiationDetection también se borran.

#### Queries de negociación V8 → portar como tests de TurnInterpreter

El agente 2.5 DEBE usar estas queries como base para tests del TurnInterpreter post-refactor. Estas validaban que V8 regex disparaba; ahora deben validar que TurnInterpreter clasifica → `escalate` con tone `negotiation`:

**Queries que DEBEN disparar escalate (14 casos)**:
```
"me hacés un descuento?"
"dan descuentos por volumen?"
"haceme una rebaja"
"podés rebajar el precio?"
"si llevo 100 me bajás?"          ← E22
"me bajas algo?"
"bajáme el precio"
"dame mejor precio"               ← E26
"en otro lado lo conseguí más barato"  ← E23
"consigo mas barato en la competencia"
"15% off?"                        ← E25
"me hacés 10% de descuento?"
"20% menos en efectivo"
"te ofrezco $50000 por todo"
```

**Queries que NO deben disparar escalate (7 casos — deben llegar al LLM)**:
```
"pintura barata"            ← 'barato' solo no es trigger
"está caro"                 ← E18 objeción informal
"nahh está caro"            ← E18 variant
"está caro, ¿cuánto el último?"  ← E21 regateo implícito
"el IVA es del 21%"         ← porcentaje neutral
"dejo el 15% de anticipo"   ← porcentaje neutral
"quiero 5 tornillos 6mm"    ← query normal
```

**Comportamiento nuevo esperado**: TurnInterpreter debe retornar `intent=escalate`, `confidence>=0.8`, `tone=negotiation` para las queries positivas. Los tests deben mockear TurnInterpreter con estas cargas y verificar que `process_message` retorna HANDOFF_RESPONSE (o equivalente TurnInterpreter-driven).

#### V9 (detect_ambiguous_query) — fuera del alcance de 2.5

`test_ambiguity_clarification.py` (44 tests) NO está en el alcance de Bloque 2.5. V9 no aparece en la lista de eliminación. Sin embargo, los 7 integration tests en `TestV9Integration` validan que V9 cortocircuita ANTES de TurnInterpreter (`mock_llm.assert_not_called()`). Si en el futuro V9 también migra al LLM, esos 7 tests mueren. Marcado como **observación** — no acción en 2.5.

**weak coverage flag**: Los tests de `TestV9Integration` parchean `_try_ferreteria_intent_route` pero no parchean `_try_ferreteria_pre_route`. Si V9 vive dentro de `_try_ferreteria_pre_route`, la eliminación de `_try_ferreteria_pre_route` en Block 2.3 puede hacer que V9 deje de disparar aunque los tests sigan pasando (los tests no detectarían esa regresión si V9 se mueve sin tests de integración actualizados).

---

### 2.2 Compound message handler

> Alcance: fix del parser de mensajes compuestos ("dame el primero. agregame también un martillo").

#### Estado actual: ZERO tests específicos

El grep por `compound|multi_item|parser_multi|_parse_multi|split_items` devolvió:
- `bot_sales/tests/test_turn_interpreter_multi_item.py` — es sobre **max_tokens para listas multi-ítem en un pedido**, NO sobre mensajes compuestos con dos comandos. Falso positivo del grep.
- `tests/test_ferreteria_setup.py` — aparece el término "compound" pero en contexto no relevante.

**Ningún test unitario prueba el compound message parser.**

El único test que captura el bug actualmente es **S09** de `scripts/demo_test_suite.py` (E2E, slow, requiere LLM). S09 falla actualmente con "PARSER BUG — T2: 'el primero' spliteado como ítem del pedido".

**Recomendación para el agente 2.2**: Crear tests unitarios desde cero. Pattern sugerido:

```python
# Testear el componente que parsea "dame el primero. agregame también un martillo"
# Debe separar:
#   (1) ordinal selection: "dame el primero" → quote_modify con line_hint=1
#   (2) additive command: "agregame también un martillo" → product_search martillo additive=True
# Tests sin LLM: mockear TurnInterpreter, validar que ambos sub-comandos se procesan.
```

Casos mínimos a crear (8 tests sugeridos):
1. Mensaje con punto separando selección + adición
2. Mensaje con "y también" separando selección + adición
3. Ordinal "el primero" no tratado como nombre de producto
4. Ordinal "el segundo" no tratado como nombre de producto
5. Conector "dale" no spliteado como ítem
6. Mensaje compuesto sin ordinal (dos productos nuevos)
7. Mensaje compuesto donde primer sub-mensaje es aceptación + nuevo ítem
8. Mensaje compuesto donde el compuesto es de UN solo ítem (no se splitea innecesariamente)

---

## Cross-cutting

---

### Tests E2E con process_message

Archivos que llaman `process_message` (o `bot.process`), clasificados por riesgo:

| Archivo | Tests | Riesgo | Motivo |
|---------|-------|--------|--------|
| `tests/test_turn_interpreter_routing.py` | 20 | 🔴 ALTO | TestShouldBypassSalesIntelligence → DELETE; TestCriticalBypassRouting → MIGRATE; el flujo de routing cambia en 2.1+2.3 |
| `bot_sales/tests/test_handoff_negotiation.py` | 6 | 🔴 ALTO | Testea V8 pre-LLM bypass → DELETE completo en 2.5 |
| `bot_sales/tests/test_ambiguity_clarification.py` | 44* | 🟡 MEDIO | 7 integration tests verifican que V9 cortocircuita TurnInterpreter; cambia si V9 migra |
| `tests/test_ferreteria_phase4_continuity.py` | 5 | 🟡 MEDIO | Multi-turn flow tests (followup, escalate, additive). Dependen de `fq.looks_like_additive` / `fq.looks_like_clarification` que se mueven en 2.3 |
| `tests/test_ferreteria_vnext.py` | 13 | 🟡 MEDIO | `test_reset_closes_persisted_quote`, `test_acceptance_*` — usan `looks_like_acceptance` / `looks_like_reset` que se reemplazan en 2.3. Si el LLM no clasifica `quote_accept`/`quote_reject` con suficiente confianza, estos tests regresionan. |
| `tests/test_p0_p1_blockers.py` | 9 | 🟡 MEDIO | Rate limiting + storefront routing; `process_message` es mocked en mayoría → BAJO RIESGO REAL |
| `bot_sales/tests/test_anti_hallucination.py` | 5 slow | 🟡 MEDIO | Tests slow con LLM real; `_execute_function` no cambia en Bloque 2 pero es bueno verificar post-merge |
| `bot_sales/tests/test_routing.py` | 1 | 🟢 BAJO | Testea webhook routing con bot completamente mocked — no se ve afectado |
| `bot_sales/tests/test_r3_integration.py` | 5 | 🟢 BAJO | Tests de stale price wiring; no depende de pre-route helpers |
| `tests/test_ferreteria_phase2_families.py` | 8 | 🟢 BAJO | Tests de familias/categorías; routing agnóstico |
| `tests/test_ferreteria_training.py` | 20 | 🟢 BAJO | Tests de training UI; no process_message del bot |
| `tests/test_ferreteria_phase5_automation.py` | 6 | 🟢 BAJO | Tests de automatización; routing agnóstico |
| `tests/test_fix_loops.py` | 3 | 🟢 BAJO | Fix de loops; depende de LLM response pero no de pre-route |
| `tests/test_public_chat_tenant_routing.py` | 6 | 🟢 BAJO | Tenant routing; bot mocked |

\* Solo 7 de los 44 tests de `test_ambiguity_clarification.py` son de integración (TestV9Integration). Los 37 unit tests del detector son independientes de routing.

#### Flag especial: tests/test_ferreteria_vnext.py

`test_acceptance_creates_review_requested_handoff` y similares dependen de que el bot reconozca "Dale cerralo" como `quote_accept`. Actualmente esto pasa por `fq.looks_like_acceptance(text, ...)` en `_try_ferreteria_pre_route`. Cuando Block 2.3 elimine ese pre-route, el intent `quote_accept` debe llegar via TurnInterpreter. Si el TurnInterpreter tiene el intent correcto en su prompt, estos tests siguen pasando. Si no lo tiene, regresionan.

**Recomendación**: El agente 2.3 debe ejecutar `pytest tests/test_ferreteria_vnext.py` antes y después del refactor como regression check rápido.

---

### Suite C strict — análisis S01-S10

| Caso | Descripción | Bloque que lo impacta | Checker sigue válido | Comportamiento esperado cambia |
|------|-------------|----------------------|---------------------|-------------------------------|
| S01 | Martillo 500kg → V1 blocker | Ninguno (V1 se mantiene) | ✅ SÍ | NO — V1 sigue siendo pre-LLM |
| S02 | SKU AAAAA → no inventar | Ninguno | ✅ SÍ | NO — comportamiento LLM puro |
| S03 | PP-R sin precio inventado | Ninguno | ✅ SÍ | NO — comportamiento LLM puro |
| S04 | Destornillador philips strict | Ninguno | ✅ SÍ | NO — matcher behavior |
| S05 | Mechas 8mm Bosch | Ninguno | ✅ SÍ | NO — matcher behavior |
| S06 | Mecha 8mm para taladro | Ninguno | ✅ SÍ | NO — matcher behavior |
| S07 | Llave francesa strict | Ninguno | ✅ SÍ | NO — matcher behavior |
| S08 | E41 5-turn multiturno | 2.1 + 2.3 (bajo) | ✅ SÍ | BAJO RIESGO — T2 "cualquiera está bien" puede ir ahora via TurnInterpreter → quote_modify en lugar de `fq.looks_like_clarification`. El checker valida T5 output, no el mecanismo de routing. Esperado: PASS se mantiene. |
| S09 | Multi-item stock consistency | **2.2 (alto)** | ✅ SÍ — DISEÑADO para el estado roto | CAMBIA A MEJOR — cuando 2.2 fija el parser de mensajes compuestos, el check T2 (PARSER BUG) deja de disparar y el flujo llega a T4. S09 debería pasar de FAIL a PASS/WARN. El checker NO necesita modificarse — sus guards siguen siendo correctos. |
| S10 | Parser conectores "dale Bosch" | **2.1 (medio)** | ✅ SÍ | MEJORA ESPERADA — post-2.1 LLM-first, TurnInterpreter recibe contexto del turno anterior (last_topic=taladros) + "dale, mostrame los Bosch" → product_search brand=Bosch. S10 debería pasar de WARN a PASS. El checker sigue válido. |

**Resumen Suite C**: Los 10 checkers son correctos y no necesitan modificarse. S09 y S10 están diseñados exactamente para mejorar con Bloque 2. No requieren ajustes de checker — son el test de aceptación natural de los bloques 2.1 y 2.2.

---

## Referencias rápidas

### Archivos a tocar por bloque

```
2.1 toca:
  bot_sales/routing/turn_interpreter.py          (refactor principal)
  bot_sales/bot.py:666-700                        (dispatch loop)
  [NUEVOS tests]: bot_sales/tests/test_turn_interpreter_state_context.py (sugerido)

2.3 toca:
  bot_sales/bot.py:920-1450                       (_try_ferreteria_pre_route + helpers)
  bot_sales/bot.py:1558-1900                      (static helpers)
  [DELETE tests]: tests/test_turn_interpreter_routing.py → TestShouldBypassSalesIntelligence (5 tests)
  [MIGRATE tests]: tests/test_turn_interpreter_routing.py → TestCriticalBypassRouting (4 tests)
  [REGRESSION CHECK]: tests/test_ferreteria_vnext.py (quote_accept/quote_reject)
  [REGRESSION CHECK]: tests/test_ferreteria_phase4_continuity.py (additive/clarification)

2.5 toca:
  bot_sales/services/search_validator.py          (eliminar V4, V5, V7, V8)
  bot_sales/bot.py (inyección de negotiate handler pre-LLM)
  [DELETE tests]: bot_sales/tests/test_search_validator.py → ~49 tests (V4+V5+V7+V8+L2-color)
  [DELETE tests]: bot_sales/tests/test_handoff_negotiation.py → 6 tests
  [NUEVOS tests]: TurnInterpreter tests de negociación (14 queries positivas, 7 negativas)

2.2 toca:
  bot_sales/bot.py (compound message parser — probablemente nuevo método)
  bot_sales/routing/turn_interpreter.py (compound detection si se delega)
  [NUEVOS tests]: bot_sales/tests/test_compound_message_parser.py (sugerido, ~8 tests)
```

### Helpers/funciones a eliminar (bot.py)

```python
# bot_sales/bot.py

bot.py:920    def _try_ferreteria_pre_route(...)         # bloque completo (~400 líneas)
bot.py:1558   def _normalize_lookup_text(text)           # ~20 líneas
bot.py:1682   def _looks_like_project_request(...)       # ~25 líneas
bot.py:1708   def _should_bypass_sales_intelligence(...) # ~12 líneas
bot.py:1720   def _looks_like_product_request(...)       # ~108 líneas
bot.py:1828   def _update_sales_preferences(...)         # ~27 líneas
bot.py:1855   def _looks_like_price_objection(...)       # ~16 líneas
bot.py:1871   def _looks_like_recommendation_request(...)# ~18 líneas
bot.py:1889   def _looks_like_comparison_request(...)    # ~16 líneas

# bot_sales/services/search_validator.py

detect_negotiation_intent(text)       # V8 — eliminar función completa
_V8_NEGOTIATION_PATTERNS              # constante de patterns V8
HANDOFF_NEGOTIATION_RESPONSE          # puede mantenerse como constante de respuesta
validate_query_specs() → V4 branch    # eliminar rama de colores preciados
validate_query_specs() → V5 branch    # eliminar rama de storage specs
validate_query_specs() → V7 branch    # eliminar rama de adjetivos absurdos
_PRECIOUS_COLORS                      # constante V4
_V7_UNIVERSAL_ABSURD                  # constante V7
_V7_BLOCKED_PAIRS                     # constante V7
validate_search_match() → color branch# eliminar L2 color check (depende de V4)
```

---

## FINDINGS ADICIONALES

> Cosas vistas de paso que NO se modifican en este PR. Para otro agente.

1. **`tests/test_turn_interpreter_routing.py` tiene `llm.max_tokens = 200` en `TestTurnInterpreterParsing._make_interpreter`** (línea 98). Esto es un artefacto del bug original. No es un problema funcional (los tests mockean el response), pero puede confundir a alguien revisando el código. Baja prioridad.

2. **`bot_sales/tests/test_routing.py` tiene un solo test que siempre falla** (`test_routing.py:1 test, 1 pre-existing failure` aparece en múltiples baselines). Probablemente es el `test_routing_failure` que aparece en pytest. No relacionado con Bloque 2. Investigar separado.

3. **`tests/test_ferreteria_phase4_continuity.py:test_phase4_recoverable_followup_stays_deterministic_and_skips_sales_intelligence`** — tiene un monkeypatch de `_run_sales_intelligence`. Ese monkeypatch puede fallar si el método se renombra o mueve en Block 2.3. Bajo riesgo pero marcar.

4. **`bot_sales/tests/test_a2_regressions.py` (19 tests, 260 líneas)** — no apareció en ninguna búsqueda de bloque. Es probable que testee comportamiento del matcher (A2 = algorithmic regressions). Revisar si algún test depende de `_normalize_lookup_text` (que se elimina en 2.3). Grep sugerido antes de ejecutar 2.3: `grep -n "_normalize_lookup_text\|looks_like" bot_sales/tests/test_a2_regressions.py`.

5. **V9 (`detect_ambiguous_query`)** — tiene 44 tests que son todos válidos y no en scope de ningún bloque actual. PERO: si Block 2.3 elimina `_try_ferreteria_pre_route` y V9 vive dentro de él, V9 deja de disparar silenciosamente. Confirmar dónde exactamente está el call-site de `detect_ambiguous_query` en `bot.py` antes de ejecutar 2.3. Grep: `grep -n "detect_ambiguous" bot_sales/bot.py`.

6. **`scripts/demo_test_suite.py:S09` es la única prueba del compound message parser** — una vez que 2.2 arregle el bug, S09 puede pasar a validar el comportamiento correcto. Considerar agregar una variante de S09 que pruebe explícitamente el escenario post-fix.
