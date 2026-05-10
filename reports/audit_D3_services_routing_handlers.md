# Audit D3 — Capa LLM-first (services + routing + handlers + state)

**HEAD:** `9f7369d` — docs: PENDIENTES actualizado — cierre 2026-05-07 (10 bloques)
**Alcance:** `bot_sales/services/` · `bot_sales/routing/` · `bot_sales/handlers/` · `bot_sales/state/`
**Tipo:** Read-only, sin modificaciones al código.

---

## Resumen

**La arquitectura "LLM interpreta, negocio decide" está correctamente diseñada en su núcleo, pero la implementación muestra dos tensiones importantes:**

- **Tensión 1 — Código viejo coexiste**: `fq.looks_like_acceptance()`, `fq.looks_like_reset()` y `AcceptanceDetector` siguen vivos en el grafo de llamadas real. TurnInterpreter no es el único clasificador de intents.
- **Tensión 2 — Dos sistemas de scoring**: `_significant_words` y `_score_product` existen en versiones distintas en `ferreteria_quote.py` y `CatalogSearchService`. El catálogo nuevo tiene scoring más débil (sin synonyms, sin families, sin dimensions).
- **Hallazgo de bugs latentes**: Las constantes `_SINGLE_RESULT_THRESHOLD` y `_OPTIONS_THRESHOLD` en `CatalogSearchService` están definidas pero nunca usadas. El fallback DT-18 no es "SalesFlowManager responde sin contexto" — es una cascada de tres handlers.
- **AcceptanceDetector** (`routing/acceptance_detector.py`) está huérfano: no se importa en bot.py desde que TurnInterpreter maneja quote_accept/reject.
- Los campos de estado `confirmed_constraints`, `rejected_options`, `pending_questions`, `last_search_query_struct`, `acceptance_pending` existen en `ConversationStateV2` pero ningún servicio nuevo los escribe.

---

## 1. Inventario de archivos

| Archivo | LOC | Clases | Funciones públicas | Rol |
|---|---|---|---|---|
| **routing/turn_interpreter.py** | 518 | `EntityBundle`, `QuoteReference`, `TurnInterpretation`, `TurnInterpreter` | `interpret`, `from_dict`, `to_dict`, `is_low_confidence`, `unknown` | Clasificador único por turno: intent + entidades + tono + quote context |
| **routing/acceptance_detector.py** | 139 | `AcceptanceDetector` | `detect` | ⚠️ Huérfano — LLM + keyword fallback para accept/reject. Reemplazado por TI |
| **services/catalog_search_service.py** | 297 | `ProductNeed`, `CatalogSearchResult`, `CatalogSearchService` | `search`, `from_turn_interpretation`, `to_dict` | Pipeline determinístico de búsqueda de productos (3 modos) |
| **services/search_validator.py** | 301 | _(solo funciones)_ | `validate_query_specs`, `validate_search_match` | Anti-alucinación: L1 pre-búsqueda (specs imposibles), L2 post-búsqueda (claims vs catálogo) |
| **services/quote_service.py** | 254 | `QuoteService` | `save_quote_snapshot`, `mark_reset`, `load_active_quote`, `can_accept_quote`, `derive_quote_status`, `build_runtime_items_from_lines` | Persistencia de quotes: runtime ↔ DB, lifecycle management |
| **services/quote_automation_service.py** | 232 | `QuoteAutomationService`, `QuoteAutomationError` | `refresh_quote_automation`, `send_quote_ready_followup`, `block_automation`, `reset_automation`, `list_eligible_quotes` | Automatización post-quote: evaluación de elegibilidad + envío WhatsApp |
| **services/policy_service.py** | 114 | `PolicyService` | `get_snippet_for_topic`, `get_guardrails_prompt`, `build_turn_policy_context`, `infer_topic_from_message` | Parsea policies.md en secciones; sirve contexto por topic en el turno |
| **services/handoff_service.py** | 61 | `HandoffService` | `create_review_handoff` | Crea handoff record + envía email alert cuando se acepta un quote |
| **services/pending_guard.py** | 25 | _(solo funciones)_ | `contains_pending_marker`, `sanitize_response` | Detecta `[PENDIENTE...]` en respuestas LLM y reemplaza con fallback seguro |
| **services/price_validator.py** | 134 | _(solo funciones)_ | `extract_prices_from_response`, `has_approximate_language`, `detect_hallucinated_prices` | R2: compara precios en respuesta LLM contra precios de catálogo del turno |
| **handlers/escalation_handler.py** | 85 | `EscalationHandler` | `handle`, `should_escalate_on_frustration` | Dispara escalación a humano; actualiza state a "escalated"; llama HandoffService |
| **handlers/offtopic_handler.py** | 85 | `OfftopicHandler` | `handle` | Responde off_topic/small_talk con canned o LLM redirect |
| **handlers/policy_handler.py** | 51 | `PolicyHandler` | `handle` | Obtiene snippet de PolicyService, lo inyecta como system message, llama LLM |
| **state/conversation_state.py** | 139 | `CustomerProfile`, `ConversationStateV2`, `StateStore` | `transition`, `validate_state`, `to_dict`, `from_dict`, `from_json`, `from_legacy_session`, `StateStore.load`, `StateStore.save` | Estructura de estado V2: 9 estados válidos, compat con legacy session dict |

---

## 2. TurnInterpreter (routing/turn_interpreter.py)

### Schema de salida (TurnInterpretation)

```
intent            : str  — 10 valores: product_search | policy_faq | quote_modify | 
                            quote_accept | quote_reject | escalate | off_topic | 
                            small_talk | customer_info | unknown
confidence        : float  — [0.0, 1.0]; < 0.55 = is_low_confidence()
tone              : str  — neutral | frustrated | urgent
policy_topic      : str?  — horario | envio | garantia | factura | devolucion | reserva | pago | None
search_mode       : str?  — exact | browse | by_use | None
entities          : EntityBundle
  .product_terms  : List[str]
  .use_case       : str?
  .material       : str?
  .dimensions     : Dict[str, Any]
  .qty            : int?
  .brand          : str?
  .budget         : float?
quote_reference   : QuoteReference
  .references_existing_quote : bool
  .line_hints     : List[str]
reset_signal      : bool
compound_message  : bool  — 2+ comandos distintos en el mismo turno (B21)
escalation_reason : str?  — explicit_request | negotiation | frustration | None
referenced_offer_index : int?  — índice 0-based del producto ofrecido referenciado
sub_commands      : List[str]  — comandos individuales cuando compound_message=true (max 5)
items             : List[str]?  — lista de ítems pre-extraída cuando el mensaje ES una lista (L2)
```

### Reglas hardcodeadas en el system prompt (no en código Python)

| Regla | Trigger | Resultado |
|---|---|---|
| V8 (negociación) | "me bajás", "más barato", "descuento", "qué hacés" | intent=escalate, escalation_reason=negotiation, conf≥0.75 |
| V9 (ambigüedad) | Query genérica + current_state condiciona resultado | search_mode=browse vs quote_reference según estado |
| Specs absurdas | "martillo de 500kg", "taladro de 64GB" | intent=unknown, conf<0.4 |
| referenced_offer_index | "el primero", "el de Bosch", "el más barato" | índice 0-based en TurnInterpretation |
| compound_message | 2+ comandos en un turno | compound_message=true + sub_commands |
| quote_modify en awaiting_clarification | "cualquiera", "sí", "ese" | quote_modify (NO quote_accept) |
| ITEMS | Lista numerada/bullets o 4+ productos | items=["5 mechas 6mm", ...] |

### Mecánica de llamada

- Modelo: `gpt-4o-mini` hardcodeado vía mutación temporal de `self.llm.model`, `max_tokens=1024`, `temperature=0.0`
- Contexto: últimos 3 turnos (6 mensajes), estado actual, productos ofrecidos en el turno previo
- **Riesgo de concurrencia**: el patrón save/override/restore de `self.llm.model` es thread-unsafe si el LLM client es compartido entre sesiones. En un servidor single-threaded (Gunicorn workers separados) es inofensivo, pero es frágil.

### Fallbacks cuando el LLM falla

```python
except Exception as exc:
    logger.warning("TurnInterpreter failed: %s", exc)
    return TurnInterpretation.unknown()  # intent="unknown", confidence=0.0
```

El resultado `unknown` + `confidence=0.0` es el trigger del escalation safety-net en bot.py:835-856.

### Análisis del DT-18

**DT-18** describe: "TI failure → SalesFlowManager responde sin contexto".

El path real es una **cascada de 3 capas**:

```
TI falla
  └→ TurnInterpretation.unknown() devuelta a _try_ferreteria_intent_route
       └→ Escalation safety-net (B24): si el mensaje parece escalación, maneja y retorna.
            └→ Si no, retorna None → _try_ferreteria_pre_route() corre (deterministic handlers:
                 looks_like_reset, looks_like_acceptance, lookup de catálogo legacy, etc.)
                  └→ Si pre_route retorna None → _run_sales_intelligence()
                       └→ SalesFlowManager.process_input() [si inicializado]
                            └→ Si flow_manager=None → _chat_with_functions() [LLM con tools]
```

**El SalesFlowManager NO es el fallback terminal**. Si falla o no está inicializado, el bot cae a `_chat_with_functions` con el LLM completo y función calling. El problema reportado en DT-18 ("¿Me podés repetir?") viene del `SalesFlowManager.process_input` que sí responde eso cuando no tiene contexto suficiente.

**Gap concreto**: el DT-18 debería atacarse interceptando en `_try_ferreteria_intent_route` cuando `intent="unknown" and confidence==0.0` y el contexto indica que había un carrito activo — en ese caso un "Tuve un problema técnico, ¿podés repetir lo que necesitás?" explícito sería mejor que seguir la cascada.

---

## 3. CatalogSearchService

### Cómo busca

```
input: ProductNeed (from TurnInterpretation)
  ├── search_mode="exact"  → _search_exact()
  │     query = join(raw_terms + use_case + material + brand + dim values)
  │     → db.find_matches_hybrid(model=query) OR db.find_matches(model=query)
  │     → _score_and_filter() → _apply_post_filters() → _build_result()
  ├── search_mode="by_use" → _search_by_use()
  │     query = join(use_case + material) — sin raw_terms
  │     → misma cadena de score/filter
  └── search_mode="browse" → _search_browse()
        family = family_hint OR raw_terms[0]
        → db.list_by_category(family) OR db.find_matches(model=family)
        → devuelve top MAX_CANDIDATES=5 sin scoring
```

### Scoring (_score_product)

| Condición | Puntos |
|---|---|
| Overlap palabras significativas ≥ 50% | +5.0 |
| Overlap > 0 pero < 50% | +3.0 |
| Sin overlap | -3.0 |
| Precio > budget | -4.0 |
| Brand match | +2.0 |

Método de matching: **word overlap** sobre `_significant_words()` (lowercased, stop-words removed, len>2). **No hay TF-IDF, no hay embeddings, no hay fuzzy**. El scoring de `ferreteria_quote.py` (legacy) es considerablemente más rico: conoce families, dimensions, synonyms, y singularización.

### Constantes definidas pero no usadas

```python
_SINGLE_RESULT_THRESHOLD = 7.0   # ← NUNCA REFERENCIADO en _determine_status
_OPTIONS_THRESHOLD = 2.0          # ← NUNCA REFERENCIADO en _determine_status
```

`_determine_status` solo mira `len(candidates)` y `missing_fields`. Las constantes son **dead code** — probablemente planeadas para una transición de status basada en score que nunca se implementó.

### Determinación de status

```
candidates vacíos → "no_match"
missing_fields Y len>1 → "clarify"
len==1 → "resolved"
else → "options"
```

El `"clarify"` solo se activa cuando `search_mode="exact"` y faltan `dimensions` o `brand`. Si hay 3 candidatos con distintos materiales, el sistema devuelve `"options"` en vez de `"clarify"` — el LLM decide cómo presentarlos.

### Gaps

- Sin synonym expansion (ferreteria_quote.py tiene knowledge-based `_build_search_terms`)
- Sin fuzzy matching (DT-13 agregó JaroWinkler en `ferreteria_language.py`, no aquí)
- Sin singularización (ferreteria_quote.py tiene `_singularize()`)
- `_search_browse` no puntúa candidatos — primer 5 del catálogo, sin ordenar por relevancia
- Brand hard-fail (`if not result and need.brand: return []`) podría devolver vacío cuando el catálogo tiene el producto bajo marca diferente

---

## 4. SearchValidator (V1–V6)

| Validator | Nivel | Qué chequea | Cómo | Si falla |
|---|---|---|---|---|
| **V1** | L1 (pre-búsqueda) | Peso imposible para herramienta manual conocida | `_extract_weight_kg()` + `_has_word()` por 7 tipos de herramienta; compara contra max_kg por tipo | Retorna `(False, reason)` → status="no_match", reason_code="impossible_spec" |
| **V2** | L1 | Diámetro de broca/mecha > 60mm | `_has_word(text, _DRILL_KWS)` + `_extract_mm_value()` | Igual |
| **V3** | L1 | Largo de fijación (tornillo/clavo/perno) > 800mm | `_has_word(text, _FASTENER_KWS)` + `_extract_mm_value()` | Igual |
| **V6** | L1 | Potencia imposible para herramienta eléctrica | `_extract_watts()` + tabla `_TOOL_WATT_LIMITS`; sierra circular con lógica especial (dos palabras) | Igual |
| **L2 weight** | L2 (post-búsqueda) | Ningún producto del catálogo coincide con el peso reclamado | `_product_matches_weight()`: busca peso en nombre del producto ±3× del reclamo | Retorna `(False, reason)` → status="no_match", reason_code="spec_mismatch" |

**Validators removidos (migrados a TurnInterpreter vía LLM rules):**
V4 (colores preciosos), V5 (almacenamiento digital), V7 (adjetivos imposibles), V8 (negociación), V9 (ambigüedad). Decisión correcta — el LLM generaliza mejor que regex para semántica.

### Robustez y gaps

- `_extract_mm_value` extrae **el primer** valor de medida en el texto. Si el usuario dice "necesito 5 tornillos de 10mm", extrae 10mm correctamente. Pero "10 tornillos de 900mm de largo" extrae 10mm (el "10" antes de "tornillos") y falla en detectar el 900mm. **Falso negativo posible.**
- `_has_word` usa `re.search(r"\b" + kw + r"s?\b")` — cubre singular y plural regular español. No cubre: "mechas" desde "mecha" cuando la keyword es "mecha" (sí funciona), pero no cubre formas irregulares ("alicates" desde "alicate" — sí funciona también, tiene trailing `s?`).
- L2 weight: el factor 3× de tolerancia es generoso. Un martillo de 3kg podría matchear un producto de 1kg (1kg * 3 = 3). Podría generar falsos negativos.
- No hay V para: voltaje (18V baterías), presión (herramientas neumáticas), longitud de cable.

---

## 5. Quote services

### Lifecycle de un quote

```
[mensaje de cliente]
   │
   ├─ save_quote_snapshot(accepted=False) → status="open"
   │     Si hay blocking lines → status="waiting_customer_input"
   │
   ├─ save_quote_snapshot(accepted=True) → status="review_requested"
   │     + event "quote_accepted"
   │     + HandoffService.create_review_handoff()
   │
   ├─ mark_reset() → status="closed_cancelled"
   │     + event "quote_reset"
   │
   └─ QuoteAutomationService.send_quote_ready_followup()
         → automation_state="awaiting_customer_confirmation"
         → WhatsApp enviado
```

### QuoteService — mapeo de status

| Runtime status | Persisted line_status | Descripción |
|---|---|---|
| `resolved` (sin pack_note) | `resolved_high_confidence` | Producto encontrado sin ambigüedad |
| `resolved` (con pack_note) | `resolved_needs_confirmation` | Producto con presentación especial |
| `ambiguous` | `ambiguous` | Múltiples opciones sin elegir |
| `unresolved` | `unresolved` | No encontrado |
| `blocked_by_missing_info` | `blocked_by_missing_info` | Faltan specs críticas |

Quote-level status: `open`, `waiting_customer_input`, `review_requested`, `closed_cancelled`. No hay TTL/expiración.

### QuoteAutomationService — gaps

- `list_eligible_quotes` filtra por `status="ready_for_followup"` — este valor **no aparece en `QuoteService.derive_quote_status()`** (que solo produce: open, waiting_customer_input, review_requested). **Posible schema drift**: o bien es un estado asignado manualmente por el dashboard, o la constante está desactualizada.
- `send_quote_ready_followup` importa `WhatsAppMeta` directamente — no hay abstracción de canal; si se agrega email channel, requiere modificar este método.
- `evaluate_quote_automation` y `build_quote_ready_followup` se importan de `ferreteria_automation` (no auditado) — la lógica de elegibilidad vive fuera del servicio.

---

## 6. PolicyService

### Cómo carga policies

```python
PolicyService(policies_text: str)  # texto plano en string, pasado al constructor
```

- Fuente de verdad: **archivo markdown** (`policies.md` leído en `SalesBot._load_policies()`)
- Sin DB, sin versionado, sin hot-reload — requiere restart para actualizar políticas
- Parseo: split por headers `##` o `#` → dict `{section_name: content}`
- Matching de topic: primero key match directo; si falla, keyword score via `POLICY_TOPICS`

### `build_turn_policy_context`

```
topic dado (de TurnInterpretation.policy_topic)
  └→ get_snippet_for_topic(topic) → snippet de la sección relevante
       └→ f"{GUARDRAILS}\n\nPOLÍTICA RELEVANTE ({TOPIC}):\n{snippet}"
            └→ PolicyHandler inyecta esto como system message final
```

Diseño correcto: guardrails siempre presentes, snippet solo cuando es relevante. Evita inflar el prompt con policies.md completo.

### Gap

`infer_topic_from_message` en PolicyService es un **clasificador heurístico de topic que duplica la responsabilidad del TurnInterpreter**. PolicyHandler llama a esto solo cuando `interpretation.policy_topic is None`. En la práctica, si TI funciona, este código nunca debería ejecutarse. Si TI falla, este heurístico puede rescatar la respuesta — pero no está claro que sea el comportamiento deseado vs. devolver guardrails sin snippet.

---

## 7. Handlers

### EscalationHandler

**Cuándo se dispara** (bot.py:820-833):
```
(interpretation.intent == "escalate" OR should_escalate_on_frustration(interp))
AND NOT is_low_confidence()
```

`should_escalate_on_frustration`: `tone == "frustrated" AND confidence >= 0.55`

**Flujo**: transition(state_v2, "escalated") → HandoffService.create_handoff() → respuesta diferenciada por reason (negotiation → _NEGOTIATION_RESPONSE, else → _GENERIC_HANDOFF_RESPONSE).

**Escalation safety-net** (bot.py:840-856): cuando TI devuelve unknown+0.0, `_looks_like_escalation_request()` (keyword-based) puede aún disparar EscalationHandler. Doble cobertura correcta.

### OfftopicHandler

**Cuándo se dispara**: `interpretation.intent in ("off_topic", "small_talk")` (inferido del flujo en bot.py:568-572).

**Flujo**: small_talk → try canned response (greeting/farewell/thanks) → si no matchea, cae a LLM. off_topic → LLM directo con redirect prompt. Fallback si LLM falla: "Ese tema está fuera de lo que manejo."

**Gap**: el método `handle` acepta `messages` y `system_prompt` pero los ignora en la rama de small_talk. En off_topic los ignora también — construye sus propios `redirect_messages` desde cero, sin contexto de la conversación.

### PolicyHandler

**Cuándo se dispara**: `interpretation.intent == "policy_faq" AND NOT is_low_confidence()` (bot.py:796).

**Flujo**: obtiene `topic` de `interpretation.policy_topic` → fallback a `policy_service.infer_topic_from_message()` → `build_turn_policy_context(topic)` → append como system message al final de `messages` → LLM call.

**Gap**: el método recibe `messages` (historial) pero la rama de error de LLM devuelve string genérico sin logging del topic ni del error al usuario. El error se loggea pero el cliente recibe mensaje vago.

---

## 8. ConversationStateV2

### Estructura

```python
ConversationStateV2:
  state: str                          # FSM: idle | browsing | quote_drafting | 
                                      #       awaiting_clarification | awaiting_customer_confirmation |
                                      #       review_requested | escalated | closed
  active_quote_id: str?               # ID en QuoteStore
  pending_questions: List[str]        # ← NEVER WRITTEN by new service layer
  last_interpretation: Dict?          # último TurnInterpretation serializado
  confirmed_constraints: Dict         # ← NEVER WRITTEN by new service layer
  rejected_options: List[str]         # ← NEVER WRITTEN by new service layer
  last_search_query_struct: Dict?     # ← NEVER WRITTEN by new service layer
  last_candidate_skus: List[str]      # ← NEVER WRITTEN by new service layer
  customer_profile: CustomerProfile   # name, contact, email, zone
    # customer_info intent → no hay path claro que lo llene en handlers nuevos
  acceptance_pending: bool            # ← No referenciado en handler flow leído
  escalation_status: str?             # se escribe en EscalationHandler.handle()
  handoff_id: str?                    # se escribe en EscalationHandler.handle()
  
  # Legacy compat (no serializados):
  _legacy_active_quote: List?         # read-only durante migración
  _legacy_quote_state: str?
```

### Persistencia

`StateStore.save()` escribe en `sess["_state_v2"]` (in-memory dict) **y** mantiene legacy keys en sync:
- `sess["quote_state"]` ← mapeado desde V2 state (browsing → "open", escalated → "open")
- `sess["active_quote"]` ← solo si `_legacy_active_quote is not None`

La persistencia real (DB) ocurre por el mecanismo de sesión existente que persiste `sess`.

### Gaps

- **`browsing` state sin transiciones**: existe en `VALID_STATES` pero ningún handler transiciona hacia él. `_detect_ferreteria_browse_category` en bot.py detecta browse pero no transiciona el estado.
- **5 campos nunca escritos por código nuevo**: `pending_questions`, `confirmed_constraints`, `rejected_options`, `last_search_query_struct`, `last_candidate_skus` son schema aspiracional sin implementación.
- **`customer_info` intent sin handler**: TurnInterpreter clasifica `customer_info` correctamente (nombre, empresa, teléfono) pero no hay handler dedicado en `_try_ferreteria_intent_route` — cae a `_try_ferreteria_pre_route` / legacy flow.
- **`acceptance_pending`**: definido en el dataclass pero no referenciado en el handler flow auditado.
- **`from_legacy_session` no migra items**: solo mapea el estado string. El `active_quote` (lista de QuoteItems legacy) queda en `_legacy_active_quote` sin conversión a `active_quote_id`.

---

## 9. Duplicación con código viejo

| Función nueva | Función vieja equivalente | Estado |
|---|---|---|
| `TurnInterpretation` (intent, tone, entities) | `IntentRouter` + per-turn heuristics en bot.py | ✅ Migración completa — IntentRouter no se importa en bot.py |
| `TurnInterpretation.quote_accept/reject` | `AcceptanceDetector.detect()` | ⚠️ AcceptanceDetector en `routing/acceptance_detector.py` HUÉRFANO — no importado en bot.py. `fq.looks_like_acceptance()` aún se llama en pre_route (línea 932) |
| `TurnInterpretation.reset_signal` | `fq.looks_like_reset()` | 🔴 DUPLICACIÓN ACTIVA — `looks_like_reset` se llama en bot.py líneas 786, 954, 1020, 1969, 2035. TI tiene `reset_signal` pero no reemplazó todos los call sites |
| `CatalogSearchService._significant_words()` | `fq._significant_words()` (línea 303) | 🔴 FORK — implementaciones diferentes. fq tiene stop-words más ricas; CSS tiene lista distinta. Ambas activas en producción |
| `CatalogSearchService._score_product()` (simple) | `fq._score_product()` (línea 361, ~85 LOC) | 🔴 DOS SISTEMAS — fq._score_product conoce families, dimensions, synonyms, singularización. CSS solo hace word overlap. Ambos activos |
| `TurnInterpretation.policy_topic` | `PolicyService.infer_topic_from_message()` | ⚠️ FALLBACK ACTIVO — PolicyHandler llama `infer_topic_from_message` si TI no detecta topic. Duplicación intencional pero no documentada |
| `TurnInterpretation.escalation_reason="negotiation"` | V8 validator (removido) | ✅ Migrado correctamente — V8 eliminado de search_validator.py, regla en TI prompt |
| `TurnInterpretation.search_mode="browse"` | V9 validator (removido) | ✅ Migrado correctamente |
| `QuoteService.save_quote_snapshot()` | Persistencia ad-hoc en `fq` + `bot.py` | 🟡 PARCIAL — QuoteService es el path nuevo; bot.py aún accede a `sess["active_quote"]` directamente para compatibilidad |

---

## 10. Gaps de la arquitectura LLM-first

### Paths que esquivan los servicios nuevos

1. **`fq.looks_like_reset()` ejecuta antes y después de TI**: en `_try_ferreteria_intent_route` (línea 786) se llama `fq.looks_like_reset()` ANTES de que `reset_signal` del TI sea el decisor. Si el regex detecta reset, se actúa sin pasar por TI intent. El `reset_signal` del TI también puede disparar el reset (línea 677). Doble path activo, sin coordinación explícita.

2. **`fq.looks_like_acceptance()` coexiste con TI**: en `_try_ferreteria_pre_route` (línea 932), cuando `interpretation.intent == "quote_modify"`, el código además llama `fq.looks_like_acceptance()`. Si esta función dice "sí", overridea la clasificación de TI. TI puede decir "quote_modify", pero si el texto matchea un accept pattern, se procesa como accept. Posible conflicto.

3. **`_chat_with_functions()` es un LLM path paralelo**: cuando intent_route y pre_route retornan None, el bot ejecuta `_chat_with_functions` con OpenAI function calling (buscar_stock, etc.). Este path NO usa TurnInterpreter para clasificar — el LLM recibe el historial y decide libremente qué tools llamar. Es el fallback terminal pero también un classifier implícito.

4. **`customer_info` intent sin handler dedicado**: TI detecta "soy de empresa X", "mi nombre es Y" como `customer_info`, pero `_try_ferreteria_intent_route` no tiene un branch para este intent. Cae a pre_route → sales_intelligence → llm_fallback. El LLM puede o no capturar el dato en `customer_profile`.

5. **SalesFlowManager como segundo clasificador**: `_run_sales_intelligence()` corre siempre que pre_route devuelve None. `SalesFlowManager.process_input()` tiene su propio classificador de intents (`SalesIntent`) y state machine paralela. Esto significa que para cualquier mensaje que no matchea intent_route ni pre_route, **hay dos sistemas de estado** activos: ConversationStateV2 + SalesFlowManager interno state.

6. **Búsqueda de catálogo solo en `product_search` de alta confianza**: si TI clasifica `quote_modify` (el cliente modifica carrito) pero el producto referenciado no está en el carrito, no hay fallback a `CatalogSearchService`. La resolución del producto queda en manos del LLM en `_chat_with_functions`.

7. **`compound_message` sin decomposición completa**: TI extrae `sub_commands` para compound messages. `_process_compound_modify` y `_process_compound_mixed` los procesan. Pero si TI classifica `compound_message=true` con `intent="product_search"`, no hay handler compound — cae al path normal de un solo search.

---

## 11. Top 10 oportunidades

| # | Oportunidad | Impacto | Esfuerzo |
|---|---|---|---|
| **1** | **Eliminar `AcceptanceDetector`** (orphaned) — el archivo ya no es necesario con TI. Borrar `routing/acceptance_detector.py` | Limpieza, reduce confusion | Bajo |
| **2** | **Unificar `_significant_words` y `_score_product`** — extraer a `bot_sales/utils/text_scoring.py` con la versión rica de fq; que CatalogSearchService la importe | Mejora calidad de búsqueda nueva; elimina fork | Medio |
| **3** | **Centralizar reset en TI `reset_signal`** — reemplazar los 5 call sites de `fq.looks_like_reset()` en bot.py por verificación de `reset_signal` del TurnInterpretation cacheado. Desactivar la heurística como decisor primario | Elimina duplicación activa | Medio |
| **4** | **DT-18: respuesta explícita en TI failure** — cuando `intent="unknown" and confidence==0.0` Y hay `active_quote`, retornar mensaje claro ("Tuve un problema técnico, ¿podés repetirme qué necesitás?") en vez de entrar a la cascada SalesFlowManager | UX en outage de OpenAI | Bajo |
| **5** | **Eliminar constantes dead code en CatalogSearchService** — `_SINGLE_RESULT_THRESHOLD` y `_OPTIONS_THRESHOLD` nunca se usan. O implementarlos o borrarlos | Claridad | Bajo |
| **6** | **Handler para `customer_info` intent** — agregar branch en `_try_ferreteria_intent_route` que extraiga name/contact de `interpretation.entities` y los persista en `ConversationStateV2.customer_profile` | Funcionalidad nueva real | Bajo-Medio |
| **7** | **`QuoteAutomationService.list_eligible_quotes` status corrección** — verificar si `"ready_for_followup"` es un status válido; si no, corregir al status real del schema (`"review_requested"` o similar) | Bug latente en automation pipeline | Bajo |
| **8** | **Limpiar campos fantasma de ConversationStateV2** — `pending_questions`, `confirmed_constraints`, `rejected_options`, `last_search_query_struct`, `last_candidate_skus` nunca se escriben. O implementarlos (alta deuda) o removerlos del dataclass | Reduce confusión del modelo de estado | Bajo |
| **9** | **Synonym expansion en CatalogSearchService** — integrar el knowledge-based `_build_search_terms` de ferreteria_quote.py o `ferreteria_language.py` (JaroWinkler, DT-13) en el path de CSS | Mejora calidad de búsqueda nueva | Alto |
| **10** | **`fq.looks_like_acceptance()` vs TI `quote_accept`** — documentar explícitamente cuándo cada path gana, o consolidar: si TI classifica `quote_accept`, confiar en TI y saltear `fq.looks_like_acceptance()` en pre_route | Elimina lógica dual conflictiva | Medio |

---

## 12. Dudas para Julian

1. **¿`AcceptanceDetector` tiene uso fuera de bot.py?** El archivo está en `routing/` pero no se importa en bot.py. ¿Hay algún test o script externo que lo use directo? Si no, ¿confirmás que se puede eliminar?

2. **¿El estado `browsing` tiene algún plan de uso?** Existe en `VALID_STATES` pero ningún código transiciona hacia él. ¿Es para una feature futura o es un leftover del diseño inicial?

3. **`QuoteAutomationService.list_eligible_quotes` filtra por `status="ready_for_followup"`** que no es un valor que produce `QuoteService.derive_quote_status()`. ¿Ese status se asigna manualmente desde el dashboard? ¿O hay un bug acá?

4. **¿El `SalesFlowManager` (planning/flow_manager.py) está activo en producción o es experimental?** Se inicializa en el constructor de SalesBot pero en Railway no está claro si `planning.flow_manager` resuelve correctamente. Si hay error de import, `self.flow_manager = None` y se usa la rama `_chat_with_functions`. ¿Es este el comportamiento intencional?

5. **`CatalogSearchService._search_browse` no puntúa candidatos** — devuelve los primeros 5 que retorna `db.list_by_category`. ¿El orden de `list_by_category` es confiable (por relevancia/popularidad) o es arbitrario?

6. **La fuente de `policies.md` es un archivo en disco leído al arranque.** ¿Nacho edita ese archivo directo? ¿Hay algún plan de moverlo a DB para edición sin restart?

7. **`customer_profile` en ConversationStateV2**: ¿el intent `customer_info` (cuando el cliente dice "soy de empresa X") debería persistir en `customer_profile.name/contact`? Si sí, ¿en qué branch de código debería hacerse? Actualmente no hay handler.
