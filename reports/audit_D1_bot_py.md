# Audit D1 — bot_sales/bot.py

**HEAD:** 9f7369d  
**LOC totales:** 2809  
**Funciones totales:** 46  
**Fecha:** 2026-05-09

---

## Resumen ejecutivo

- **Complejidad extrema concentrada en dos funciones**: `_try_ferreteria_pre_route` (~835 LOC) y `_try_ferreteria_intent_route` (~248 LOC) constituyen casi el 39% del archivo. Ambas son demasiado grandes para leer, testear o modificar con seguridad.
- **Mutación de sesión sin capa de abstracción**: `sess["active_quote"]`, `sess["quote_state"]`, `sess["pending_decision"]` y `sess["pending_clarification_target"]` se escriben directamente desde ~30 puntos distintos del código, haciendo imposible rastrear transiciones de estado sin leer todo el archivo.
- **Patron de orquestación repetido 14+ veces**: el trío `_get_suggestions → generate_updated_quote_response → _persist_quote_state` aparece en al menos 14 ubicaciones dentro de `_try_ferreteria_pre_route`, con ligeras variaciones. Es el candidato de refactor de mayor impacto.
- **Validador de búsqueda importado 3 veces de forma inline**: `validate_query_specs` / `validate_search_match` se importan con `from bot_sales.services.search_validator import ...` dentro de tres métodos diferentes (L688, L1586, L2436) en lugar de en el encabezado del módulo.
- **`tenant_manager` importado y nunca usado**: el símbolo `tenant_manager` aparece en el `import` del módulo (L20) pero no tiene ninguna referencia en el cuerpo del código — import muerto.
- **Import circular de riesgo moderado**: `whatsapp.py` importa `SalesBot` de forma diferida (`from bot_sales.bot import SalesBot` dentro de una función, L520). Esto evita el ciclo en arranque pero lo activa en runtime; si algún refactor mueve ese import al módulo top-level se rompe el proceso.
- **Dos `close()` definidos**: la clase `SalesBot` tiene dos métodos `def close(self)` (L215 y L2805). El segundo sobreescribe al primero silenciosamente; el primero tiene lógica de cierre de `quote_store` que el segundo no replica.
- **Deuda de strings duplicados**: el mensaje de rechazo de especificaciones imposibles está hardcodeado de forma idéntica en dos lugares (L1594-1596 y L1641-1643); cualquier cambio de copy requiere actualizarlos por separado.

---

## 1. Mapa de funciones

| Función | LOC aprox | Qué hace (1 línea) | Side effects | Riesgo |
|---------|-----------|-------------------|--------------|--------|
| `__init__` | 133 | Inicializa todos los servicios del bot | DB, QuoteStore, analytics, TTLCache, handlers | ALTO |
| `close` (L215) | 19 | Cierra quote_store y db | IO | BAJO |
| `_load_policies` | 8 | Lee archivo Markdown de políticas | IO | BAJO |
| `_resolve_runtime_db_path` | 9 | Resuelve path absoluto de la BD en runtime | - | BAJO |
| `_knowledge` | 7 | Carga KnowledgeLoader y retorna dict | IO | BAJO |
| `_quote_channel` | 4 | Retorna canal de la sesión | - | BAJO |
| `_load_active_quote_from_store` | 16 | Sincroniza quote activo de BD a sess | sess/QuoteStore | MEDIO |
| `_persist_quote_state` | 33 | Guarda snapshot del presupuesto en BD | QuoteStore, QuoteAutomation | MEDIO |
| `_accept_quote_for_review` | 27 | Persiste quote como aceptado y crea handoff | QuoteStore, HandoffService | ALTO |
| `_ensure_session_initialized` | 33 | Carga o crea sesión con contexto y state V2 | DB, TTLCache, analytics | MEDIO |
| `_record_user_turn` | 7 | Agrega turno de usuario al contexto | contexts, analytics | BAJO |
| `_append_assistant_turn` | 14 | Agrega respuesta al contexto y persiste en DB | DB, contexts | MEDIO |
| `_reset_turn_meta` | 13 | Limpia metadatos de turno | sess | BAJO |
| `_handle_lite_mode` | 17 | Respuesta mínima sin LLM completo | - | BAJO |
| `_handle_sales_contract_reply` | 31 | Procesa resultado de SalesFlowManager | HandoffService, contexts | MEDIO |
| `process_message` | 163 | Punto de entrada principal; orquesta todos los handlers | sess/contexts/DB/LLM | ALTO |
| `_try_ferreteria_intent_route` | 248 | Clasifica intent vía LLM y despacha handlers | sess, StateStore, LLM | ALTO |
| `_try_ferreteria_pre_route` | 835 | Router determinístico de quotes multi-turno | sess, StateStore, QuoteStore | ALTO |
| `_is_ferreteria_runtime` | 7 | Bool: ¿es runtime ferretería? | - | BAJO |
| `_normalize_lookup_text` | 13 | Normaliza texto a ASCII minúsculas | - | BAJO |
| `_detect_ferreteria_browse_category` | 62 | Mapea token normalizado a categoría de catálogo | - | BAJO |
| `_is_structured_list` | 17 | Bool: ¿parece lista estructurada? | - | BAJO |
| `_normalize_list_to_items` | 29 | LLM call: convierte lista formateada a CSV | LLM | MEDIO |
| `_parse_quote_items` | 3 | Thin wrapper a `fq.parse_quote_items` | - | BAJO |
| `_resolve_quote_item` | 3 | Thin wrapper a `fq.resolve_quote_item` | - | BAJO |
| `_generate_quote_response` | 13 | Formatea respuesta y inyecta notificaciones de precio | sess | BAJO |
| `_get_suggestions` | 20 | Combina sugerencias complementarias + cross-sell | - | BAJO |
| `_consultative_browse_cta` | 12 | CTA estático según categoría | - | BAJO |
| `_format_ferreteria_products_reply` | 25 | Formatea lista de productos para reply | - | BAJO |
| `_looks_like_escalation_request` | 4 | Bool: ¿el mensaje pide humano? | - | BAJO |
| `_all_sub_commands_look_like_modify` | 20 | Bool: ¿todos los sub-comandos son modify determinístico? | - | BAJO |
| `_process_compound_modify` | 150 | Procesa multi-operación de modificación de carrito atómicamente | sess | ALTO |
| `_process_compound_mixed` | 91 | Procesa aceptación + info de cliente en un turno | sess, QuoteStore, HandoffService | ALTO |
| `_chat_with_functions` | 98 | Loop LLM con function calling (hasta 5 iteraciones) | contexts, LLM | ALTO |
| `_build_sales_intelligence_meta` | 28 | Convierte contrato SI en dict de meta | - | BAJO |
| `_run_sales_intelligence` | 8 | Delega a SalesFlowManager | SalesFlowManager | BAJO |
| `_slim_product_list` | 6 | Recorta lista de productos a campos esenciales | - | BAJO |
| `_slim_function_result` | 47 | Recorta resultado de función para no explotar el contexto | - | MEDIO |
| `_execute_function` | 230 | Dispatcher de 15 funciones de negocio para el LLM | DB, logic, analytics, sess | ALTO |
| `_summarize_context` | 52 | LLM call: resume mensajes viejos en una oración | LLM | MEDIO |
| `_trim_context` | 33 | Trunca contexto y llama a _summarize_context | contexts, LLM | MEDIO |
| `_generate_handoff_summary` | 33 | LLM call: genera resumen para el agente humano | LLM | MEDIO |
| `_get_state` | 4 | Thin wrapper: carga ConversationStateV2 | - | BAJO |
| `_save_state` | 4 | Thin wrapper: persiste ConversationStateV2 | sess | BAJO |
| `_set_last_turn_meta` | 3 | Escribe last_turn_meta en sess | sess | BAJO |
| `get_last_turn_meta` | 3 | Lee last_turn_meta de sess | - | BAJO |
| `reset_session` | 7 | Borra sesión en memoria y BD | DB, contexts, sessions | MEDIO |
| `close` (L2805) | 5 | Cierra quote_store y db (versión 2, incompleta) | IO | BAJO |

---

## 2. Top 10 funciones más largas — análisis detallado

### 2.1 `_try_ferreteria_pre_route` (LOC: ~835)

**Descripción:** Router determinístico central de ferretería. Gestiona el ciclo de vida completo del presupuesto: aceptación, reset, merge-vs-replace, remove, replace, additive, continuación Phase 4, clarificación, nueva solicitud multi-ítem, búsqueda simple, browse por categoría y session guard. Es esencialmente un compilador de intents hard-coded con 8 secciones numeradas (0–7) y múltiples sub-secciones.

**Return paths:** ~25 caminos de retorno explícitos (incluyendo retornos anticipados `None` que dejan caer al siguiente handler)

**LLM calls:** 1 indirecto — llama a `_normalize_list_to_items` (que hace un `chatgpt.send_message`) en L1482/1489, y también a `fq.looks_like_acceptance` que internamente usa `chatgpt_client` (L932)

**Mutaciones de state:**
- `sess["active_quote"]` (escritura en ~15 lugares)
- `sess["quote_state"]` (escritura en ~10 lugares)
- `sess["pending_decision"]` (escritura + pop en ~8 lugares)
- `sess["pending_clarification_target"]` (escritura + pop en ~6 lugares)
- `sess["last_offered_products"]` (vía `_done`)
- `state_v2.transition(...)` (en ~10 lugares)
- `state_v2.acceptance_pending`
- `state_v2.active_quote_id`

**Riesgo:** ALTO — El tamaño hace que cualquier cambio en una sección pueda romper silenciosamente otra. Las 14+ instancias del patrón get_suggestions+generate_response+persist hacen que cada fix de copy o de lógica de persistencia requiera editar múltiples lugares.

**Oportunidad de refactor:** Extraer cada sección numerada (0.5, 1, 1.5, 2, 2.5, 2.7, 2.9, 3, 3.5, 4, 4.0, 4.1, 5, 6, 7) en su propio método privado. Crear un helper `_commit_cart(session_id, updated, event_type, event_payload, user_message)` que encapsule el patrón get_suggestions+generate_response+persist.

---

### 2.2 `_execute_function` (LOC: ~230)

**Descripción:** Dispatcher switch-case para 15 funciones que el LLM puede llamar via function calling. Implementado como cadena de `if/elif`. Incluye validación L1/L2 de search para `buscar_stock`, gestión de sandbox, tracking de analytics y manejo de hold_id en sesión.

**Return paths:** 16 (uno por función más el fallback `else`)

**LLM calls:** 0 directas (delega a `self.logic.*`)

**Mutaciones de state:**
- `self.sessions[session_id]["hold_id"]` en `crear_reserva`
- `self.sessions[session_id]` completo a `{}` en `confirmar_venta` (borra el estado entero)
- `self.sessions[session_id]["cross_sell_offered"]` en `obtener_cross_sell_offer`

**Riesgo:** ALTO — La limpieza total de sesión en `confirmar_venta` (L2557: `self.sessions[session_id] = {}`) puede causar pérdida de datos si hay otros keys de sesión activos. La validación L1/L2 de `buscar_stock` duplica la lógica de L688-722 y L1586-1645.

**Oportunidad de refactor:** Convertir la cadena `if/elif` a un dict de dispatchers `{func_name: handler_fn}`. Extraer la validación L1/L2 a un método privado reutilizable `_validated_stock_search(query, session_id)`.

---

### 2.3 `_try_ferreteria_intent_route` (LOC: ~248)

**Descripción:** Orquestador Phase 6+. Llama al TurnInterpreter (LLM), almacena el resultado, y despacha a handlers especializados (policy, offtopic, escalation, compound_modify, compound_mixed). Contiene también la lógica de búsqueda en catálogo (Phase 7) y la captura de TurnEvent (Phase 10).

**Return paths:** ~12 (incluyendo varios `None` implícitos para caer al siguiente handler)

**LLM calls:** 1 directa (`self.turn_interpreter.interpret`) + 1 adicional en `_process_compound_modify` o `_process_compound_mixed` si despacha allí

**Mutaciones de state:**
- `sess["last_turn_interpretation"]`
- `sess["last_catalog_result"]`
- `sess["last_offered_products"]` (vía `_done` en ningún lugar, pero sí en `_try_ferreteria_pre_route`)
- `state_v2` completo vía reset_signal
- `StateStore.save` después de escalación

**Riesgo:** ALTO — Acoplamiento temporal: el resultado de `turn_interpreter.interpret` debe estar en `sess["last_turn_interpretation"]` para que `_try_ferreteria_pre_route` lo lea. Si el orden de llamada cambia, el comportamiento cambia silenciosamente.

**Oportunidad de refactor:** Pasar `TurnInterpretation` como argumento explícito a `_try_ferreteria_pre_route` en lugar de leerlo de `sess`. Separar el bloque de TurnEvent (Phase 10) en un context manager o decorador.

---

### 2.4 `process_message` (LOC: ~163)

**Descripción:** Punto de entrada público. Valida input, inicializa sesión, recarga quote activo, ejecuta el refresh de precios stale, llama al router de intent, y como fallback: pre_route → sales_intelligence → chat_with_functions. Publica TurnEvent al final de cada path.

**Return paths:** 6 explícitos (ferreteria_route, lite_mode, pre_route, sales_response, llm_fallback, input vacío)

**LLM calls:** 0 directas (todas delegadas)

**Mutaciones de state:**
- `self.sessions[session_id]["channel"]`
- `self.sessions[session_id]["customer_ref"]`
- `self.sessions[session_id]["sales_intelligence_v1"]`
- `_r3_sess["active_quote"]` (refresh de precios)
- `_r3_sess["_stale_price_notifications"]`

**Riesgo:** MEDIO — El bloque de TurnEvent está duplicado 5 veces (log + record_turn + record_latency_bucket antes de cada `return`). Un return olvidado no lo registraría.

**Oportunidad de refactor:** Usar un context manager o `try/finally` para garantizar que TurnEvent.log() siempre se llame, independientemente del path de retorno.

---

### 2.5 `_chat_with_functions` (LOC: ~98)

**Descripción:** Loop de function calling con el LLM (hasta 5 iteraciones). Acumula precios del catálogo para validación anti-alucinación R2. Maneja el formateo de function_call messages hacia el contexto.

**Return paths:** 3 (function call resuelto, respuesta directa, max_iterations)

**LLM calls:** 1 a N (`self.chatgpt.send_message` en loop, hasta 5 veces)

**Mutaciones de state:**
- `self.contexts[session_id]` (append de assistant + function messages)

**Riesgo:** MEDIO — El loop puede hacer hasta 5 llamadas LLM por turno, con costo potencial. No hay timeout explícito más allá de `max_iterations`. El logging usa f-strings (L2255: `logging.info(f"Function called: ...")`) en lugar del patrón `%s` del resto del archivo.

**Oportunidad de refactor:** Extraer el bloque de function call (append a contexts, log, execute, slim) a `_handle_function_call_iteration`. Usar `logging.info("Function called: %s args: %s", func_name, func_args)`.

---

### 2.6 `_process_compound_modify` (LOC: ~150)

**Descripción:** Procesador atómico de multi-operaciones de modificación de carrito. Itera sobre sub_commands de TurnInterpretation y aplica secuencialmente: remove, additive, reset, option_select. Hace rollback al carrito original si cualquier paso falla.

**Return paths:** 4 (exception en step → None, no_progress en step → None, todas exitosas → reply, vacío de sub_commands)

**LLM calls:** 0

**Mutaciones de state:**
- `sess["active_quote"]` al final (commit) o restauración a `original_cart` (rollback)
- `sess["quote_state"]`

**Riesgo:** MEDIO — La lógica de option_select (L2039-2081) duplica casi exactamente la misma lógica de L1291-1318 (sección F1 de `_try_ferreteria_pre_route`). ~40 líneas de código replicado.

**Oportunidad de refactor:** Extraer la lógica de option selection a `_resolve_option_selection(line, opt_idx, qty)` reutilizable.

---

### 2.7 `_slim_function_result` (LOC: ~47)

**Descripción:** Recorta resultados de funciones LLM para no explotar el contexto. Trata `products`, `alternatives`, `recommendations`, `offer.product` y `upsell_product` de forma especial.

**Return paths:** 4

**LLM calls:** 0

**Mutaciones de state:** ninguno

**Riesgo:** BAJO — Lógica clara. La constante `_MAX_RESULT_CHARS = 4_000` puede necesitar ajuste si el modelo cambia.

**Oportunidad de refactor:** Menor — la sección de `offer` y `upsell_product` podría unificarse.

---

### 2.8 `_process_compound_mixed` (LOC: ~91)

**Descripción:** Procesa un turno combinado de quote_accept + customer_info. Almacena la info del cliente, luego intenta la aceptación. Si el carrito tiene ítems bloqueados, hace rollback de la info.

**Return paths:** 5 (no sub_cmds, no info_cmds, no open_quote, blocked → None, success → response)

**LLM calls:** 0 directas (llama a `fq.generate_acceptance_response` y `_accept_quote_for_review`)

**Mutaciones de state:**
- `sess.setdefault("customer_delivery_info", {})`
- `sess["quote_state"]`
- `sess["customer_delivery_info"]` (restauración en rollback)
- `StateStore.save`

**Riesgo:** MEDIO — El campo `delivery["raw"]` acumula texto libre con separador ` | `. No hay validación ni estructura; el reviewer humano recibe un string concatenado que puede crecer indefinidamente.

**Oportunidad de refactor:** Estructurar `customer_delivery_info` con campos explícitos en vez de acumular en `raw`.

---

### 2.9 `__init__` (LOC: ~133)

**Descripción:** Constructor. Inicializa DB, KnowledgeLoader, QuoteStore, QuoteService, HandoffService, QuoteAutomationService, Analytics, BusinessLogic, ChatGPTClient, TurnInterpreter, CatalogSearchService, PolicyService, handlers y SalesFlowManager. Muchos de estos están envueltos en `try/except Exception` individuales que degradan silenciosamente a `None`.

**Return paths:** N/A (constructor)

**LLM calls:** 0

**Mutaciones de state:** inicializa todos los atributos de instancia

**Riesgo:** ALTO — Múltiples bloques `try/except` que asignan `None` a servicios críticos (quote_store, flow_manager) hacen que el bot pueda arrancar "correctamente" pero con funcionalidad reducida sin ningún aviso visible al operador. Los imports diferidos dentro de `__init__` (L166: `from .core.tenant_config import get_tenant_config`, L188-190: handlers) sugieren que hubo problemas de importación circular en el pasado.

**Oportunidad de refactor:** Separar la inicialización en grupos (`_init_storage`, `_init_llm_clients`, `_init_handlers`) para mejorar la legibilidad y facilitar tests unitarios. Añadir un método `health_check()` que liste qué servicios están activos y cuáles degradaron a `None`.

---

### 2.10 `_summarize_context` + `_generate_handoff_summary` (LOC: ~52 y ~33)

**Descripción:** Ambas hacen una llamada LLM con prompts similares para resumir la conversación. `_summarize_context` produce un mensaje de sistema para el contexto; `_generate_handoff_summary` produce texto para el agente humano.

**Return paths:** 2 cada una

**LLM calls:** 1 cada una (`self.chatgpt.send_message`)

**Mutaciones de state:** ninguno

**Riesgo:** MEDIO — Duplicación funcional: ambas hacen la misma tarea (resumir conversación) con prompts levemente distintos. Una falla de LLM en `_summarize_context` usa `return None` (fallback silencioso a truncación); en `_generate_handoff_summary` usa `return "Resumen no disponible"`. Inconsistente.

**Oportunidad de refactor:** Unificar en `_summarize_conversation(messages, mode="context"|"handoff")` con prompt diferenciado según mode.

---

## 3. Mutaciones de session

| Clave de sess | N° de apariciones | Funciones que la tocan |
|--------------|-------------------|----------------------|
| `active_quote` | ~30 escrituras, ~20 lecturas | `_load_active_quote_from_store`, `_persist_quote_state`, `_try_ferreteria_pre_route` (15+), `_process_compound_modify`, `_process_compound_mixed`, `_execute_function` (confirmar_venta), `process_message` (R3) |
| `quote_state` | ~15 escrituras, ~5 lecturas | `_load_active_quote_from_store`, `_try_ferreteria_pre_route` (10+), `_process_compound_modify`, `_process_compound_mixed` |
| `pending_decision` | ~8 escrituras, ~5 pops | `_try_ferreteria_pre_route` (sections 2, 7), `_process_compound_mixed` |
| `pending_clarification_target` | ~7 escrituras, ~5 pops | `_try_ferreteria_pre_route` (sections 2.5, 3.5, 4, 4.0, 4.1), `_process_compound_mixed` |
| `last_turn_interpretation` | ~3 escrituras, ~10 lecturas | `_try_ferreteria_intent_route` (escritura), `_try_ferreteria_pre_route` (múltiples lecturas), `process_message` (lectura) |
| `last_catalog_result` | 1 escritura, 2 lecturas | `_try_ferreteria_intent_route` (escritura), `_chat_with_functions`, `process_message` |
| `last_offered_products` | 1 escritura, 1 lectura | `_try_ferreteria_pre_route` vía `_done`, `_try_ferreteria_intent_route` (lectura) |
| `last_turn_meta` | N escrituras, N lecturas | `_set_last_turn_meta`, `get_last_turn_meta` |
| `channel` | 1 escritura | `process_message` |
| `customer_ref` | 1 escritura, 3 lecturas | `process_message`, `_accept_quote_for_review`, `_persist_quote_state`, escalation handler |
| `customer_delivery_info` | 2 escrituras | `_process_compound_mixed` |
| `_stale_price_notifications` | 1 escritura, 1 pop | `process_message`, `_generate_quote_response` |
| `_state_v2` | vía StateStore | `_ensure_session_initialized`, `_try_ferreteria_pre_route`, `_try_ferreteria_intent_route` |
| `hold_id` | 1 escritura | `_execute_function` (crear_reserva) |
| `cross_sell_offered` | 1 escritura | `_execute_function` (obtener_cross_sell_offer) |
| `sales_intelligence_v1` | 1 escritura | `process_message` |

---

## 4. Llamadas a LLM

| Línea | Función | Contexto / prompt template |
|-------|---------|---------------------------|
| 657 | `_try_ferreteria_intent_route` | `turn_interpreter.interpret(user_message, history, current_state, last_offered_products)` |
| 932 | `_try_ferreteria_pre_route` | `fq.looks_like_acceptance(text, knowledge, chatgpt_client)` — delegado |
| 1482/1489 | `_try_ferreteria_pre_route` | `_normalize_list_to_items(text, self.chatgpt)` — extrae lista de productos CSV |
| 1860 | `_normalize_list_to_items` | `send_message([{user: prompt}])` — prompt hardcoded inline, ~11 líneas |
| 2244 | `_chat_with_functions` | `chatgpt.send_message(contexts[session_id], functions=self.functions)` — loop hasta 5x |
| 2696 | `_summarize_context` | Prompt: "Resumí esta conversación en 2-3 oraciones en español..." |
| 2770 | `_generate_handoff_summary` | Prompt: "Actúa como un asistente senior. Resume esta conversación en 2 líneas..." |

**Total: 5 puntos de llamada LLM directa** (más la cadena de function-calling en `_chat_with_functions` que puede hacer hasta 5 por turno)

---

## 5. Path principal de process_message

```
process_message(session_id, user_message, channel, customer_ref)
├── Guard 0: user_message vacío → "¿En qué te puedo ayudar?" (early return)
├── Guard 1: len > 2000 → truncar a 2000 chars (continúa)
├── Guard 2: sin letras alfabéticas → log warning (continúa, no bloquea)
├── _ensure_session_initialized(session_id)
├── Setear channel/customer_ref en sess
├── Crear TurnEvent
│
├── [Si ferreteria_runtime]:
│   ├── _load_active_quote_from_store(session_id)
│   └── refresh_stale_prices() — puede escribir _r3_sess["active_quote"]
│
├── _record_user_turn / _reset_turn_meta
│
├── [Si ferreteria_runtime]: _try_ferreteria_intent_route(session_id, user_message)
│   ├── Si devuelve str → TurnEvent.log + return ferreteria_route   ← EXIT A
│   └── Si devuelve None → continúa
│
├── _trim_context(session_id)
│
├── [Si LITE_MODE]: _handle_lite_mode(session_id, user_message)
│   └── TurnEvent.log + return result                               ← EXIT B
│
├── _try_ferreteria_pre_route(session_id, user_message)
│   ├── Si devuelve str → _append_assistant_turn + TurnEvent.log + return   ← EXIT C
│   └── Si devuelve None → continúa
│
├── _run_sales_intelligence(session_id, user_message) → sales_contract
├── _handle_sales_contract_reply(session_id, sales_contract) → sales_response
│   ├── Si devuelve str → TurnEvent.log + return sales_response              ← EXIT D
│   └── Si devuelve None → continúa
│
└── _chat_with_functions(session_id) → response_text
    └── _append_assistant_turn + TurnEvent.log + return result              ← EXIT E

Guards identificados:
- L489: `if not user_message` → robusto (strip + empty check)
- L492: `len > 2000` → robusto pero trunca silenciosamente (no avisa al usuario)
- L501: `not re.search(r"[a-z...]")` → FRÁGIL — solo loguea, mensajes puramente numéricos o emoji pasan sin control
- L527: `if self._is_ferreteria_runtime()` → FRÁGIL — condición evaluada dos veces en process_message y una vez en _try_ferreteria_pre_route; si la condición cambia entre llamadas (tenant_profile mutable) puede divergir
- L590: `if LITE_MODE` — import diferido de config en cada turno; leve overhead
- L610: `if sales_response is not None` — FRÁGIL si `_run_sales_intelligence` lanza excepción que no captura (aunque flow_manager envuelve en try/except)
```

---

## 6. Duplicación interna detectada

### 6.1 Patrón `_get_suggestions + generate_updated_quote_response + _persist_quote_state`
Aparece **14 veces** en `_try_ferreteria_pre_route` con variaciones mínimas. Líneas: 990-997, 1006-1014, 1050-1058, 1065-1073, 1083-1091, 1157-1172, 1203-1218, 1231-1246, 1360-1373, 1399-1409, 1443-1451, 1527-1535, 1655-1663, 2108-2119.

Impacto: cualquier cambio en el formato de respuesta requiere 14 ediciones manuales.

### 6.2 Validación L1/L2 de search_validator
Aparece **3 veces** de forma casi idéntica:
- L688-722 (dentro de `_try_ferreteria_intent_route`, rama `product_search`)
- L1586-1645 (dentro de `_try_ferreteria_pre_route`, sección 6)
- L2436-2490 (dentro de `_execute_function`, rama `buscar_stock`)

Cada instancia hace el mismo `import` inline + `validate_query_specs(msg)` + `validate_search_match(msg, products)`.

### 6.3 Lógica de option_select (resolución de ítem ambiguo por índice)
Aparece **2 veces** con código casi idéntico (~40 líneas):
- L1291-1318 (sección F1 de `_try_ferreteria_pre_route`)
- L2039-2081 (`_process_compound_modify`)

Ambas hacen: `_candidates = line.get("products")`, `_chosen = _candidates[opt_idx]`, `_compute_subtotal`, `dict(line).update({...})`.

### 6.4 Strings de rechazo de especificaciones
Mensaje idéntico en L1594-1596 y L1641-1643:
```
"No tenemos ese producto en el catálogo. Las especificaciones indicadas no coinciden con ningún artículo disponible. Si querés, podemos buscar algo similar con especificaciones estándar."
```

### 6.5 Prompts de resumen LLM
`_summarize_context` (L2681-2694) y `_generate_handoff_summary` (L2762-2765) hacen la misma tarea con prompts similares. Cobertura de tests diferente entre ambas.

---

## 7. Deuda implícita

### TODOs y HACs
No se encontraron comentarios `# TODO`, `# HACK`, `# FIXME`, `# DEPRECATED`, `# XXX`, `# old`, `# legacy` en el archivo. El archivo usa comentarios de sección (ej. `# ── 3. Additive ──`) y referencias a fases (Phase 3, Phase 6, Phase 7, Phase 9, Phase 10) y tickets internos (B21, B22a, B22b, B22c, B23, B24, R2, R3, F1, L1, L2, P1) dispersos en el código.

### Variables legacy / nombres sospechosos
- `SalesBot._FILLER_WORDS = fq._FILLER_WORDS` (L1806): el comentario dice "keep for backward compat if referenced elsewhere" — sugiere que fue un atributo de clase propio que se migró a `ferreteria_quote`.
- `interpretation.is_low_confidence()` chequeado 5+ veces — podría ser un filtro único aplicado antes del dispatch.
- `sales_intelligence_v1` como key de sesión (L611) — el sufijo `_v1` sugiere que habrá una v2.
- `_raw_truncated` key en slim_function_result (L2426) — key de emergencia sin documentar en el schema de función.

### Imports sin usar
- **`tenant_manager`** (L20: `from .core.tenancy import tenant_manager`): no aparece ninguna referencia en el cuerpo del archivo más allá de su propia línea de import. **Import muerto confirmado.**
- **`concurrent.futures`** (L12): se usa en L1510 (`concurrent.futures.ThreadPoolExecutor`). OK.
- Todos los demás imports tienen referencias documentadas en el código.

---

## 8. Imports y dependencias

### Imports absolutos (externos/stdlib)
```
os, re, logging, concurrent.futures
pathlib.Path
typing.Dict, Any, List, Optional
cachetools.TTLCache
```

### Imports relativos (del repo)
```
.core.database.Database
.core.chatgpt.ChatGPTClient, get_available_functions
.core.business_logic.BusinessLogic
.core.tenancy.tenant_manager           ← NUNCA USADO
.knowledge.loader.KnowledgeLoader
.persistence.quote_store.QuoteStore
.services.quote_service.QuoteService
.services.handoff_service.HandoffService
.services.quote_automation_service.QuoteAutomationService
.planning.flow_manager.SalesFlowManager
.analytics.Analytics
. ferreteria_quote (as fq)
.ferreteria_continuity.apply_followup_to_open_quote, classify_followup_message
.ferreteria_escalation.assess_quote_recoverability
.state.conversation_state.ConversationStateV2, StateStore
.routing.turn_interpreter.TurnInterpreter, TurnInterpretation
.services.catalog_search_service.CatalogSearchService, ProductNeed
.services.policy_service.PolicyService
.services.pending_guard.sanitize_response
.observability.turn_event.TurnEvent
.observability.metrics.record_turn, record_search, record_escalation, record_latency_bucket
.config.OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE, OPENAI_MAX_TOKENS, DB_FILE, CATALOG_CSV, LOG_PATH, POLICIES_FILE, MAX_CONTEXT_MESSAGES
```

### Imports diferidos (dentro de métodos)
```
.core.tenant_config.get_tenant_config       (__init__, L166)
.handlers.policy_handler.PolicyHandler      (__init__, L188)
.handlers.escalation_handler.EscalationHandler (__init__, L189)
.handlers.offtopic_handler.OfftopicHandler  (__init__, L190)
bot_sales.ferreteria_quote.refresh_stale_prices  (process_message, L533)
.config.LITE_MODE                           (process_message, L590)
bot_sales.services.search_validator.*       (3 funciones distintas: L690, L1586, L2436)
bot_sales.services.price_validator.*        (_chat_with_functions, L2228)
```

### Posibles imports circulares
- `bot_sales/connectors/whatsapp.py` importa `SalesBot` de forma diferida (L520: `from bot_sales.bot import SalesBot`). El import diferido evita el ciclo en módulo-load pero si en algún momento se mueve al top-level del módulo se creará un ciclo real: `bot.py → (vía __init__.py o whatsapp) → whatsapp.py → bot.py`.
- `bot_sales/training/session_service.py` importa `SalesBot` en top-level. Si `bot.py` importa algo de `training/`, habría ciclo.
- `bot_sales/tests/test_*.py` varios importan `SalesBot` o constantes de `bot.py` — no es circular pero requiere que `bot.py` sea importable en contexto de test sin servicios externos (cubierto por `sandbox_mode`).

---

## 9. Try/except amplios

| Línea | Bloque | Veredicto | Razón |
|-------|--------|-----------|-------|
| L114-117 | `except Exception: self.faq_file = "faqs.json"` | OK | Fallback seguro a default. |
| L128-133 | `except Exception as exc: quote_store = None` | SOSPECHOSO | Múltiples servicios críticos (QuoteStore, QuoteService, HandoffService) se desactivan silenciosamente. Solo hay un `logging.warning`. El bot puede arrancar sin persistencia de presupuestos sin aviso operacional claro. |
| L175-176 | `except Exception as e: ... fallback system_prompt` | OK | Fallback razonable al prompt estático. |
| L209-211 | `except Exception as exc: self.flow_manager = None` | SOSPECHOSO | SalesFlowManager None hace que `_run_sales_intelligence` retorne siempre None. Comportamiento cambia sin notificación. |
| L224-225 | `except Exception: logging.debug(...)` en close | OK | Ignorar errores en close es aceptable. |
| L232-233 | `except Exception: logging.debug(...)` en close | OK | Idem. |
| L260-261 | `except Exception: return None` en `_knowledge` | OK | KnowledgeLoader fallando no es fatal. |
| L317-318 | `except Exception: logging.warning` en quote_automation | OK | La automatización es best-effort. |
| L454 | `except Exception: logging.warning` en handoff | OK | Handoff fallido es best-effort. |
| L672-673 | `except Exception: interpretation = TurnInterpretation.unknown()` | SOSPECHOSO | Silencia errores del LLM durante la interpretación. Un error persistente en TurnInterpreter no sería visible en producción. |
| L732 | `except Exception: logging.warning` en catalog_search | OK | Search fallida es best-effort. |
| L1865 | `except Exception: return text` en `_normalize_list_to_items` | OK | Fallback seguro al texto original. |
| L2084 | `except Exception: rollback + return None` en compound_modify | OK | Patrón de rollback atómico correcto. |
| L2209 | `except Exception: rollback + return None` en compound_mixed | OK | Idem. |
| L2354-2356 | `except Exception: return None` en `_run_sales_intelligence` | OK | SalesFlowManager falla → fallback a LLM. |
| L2654-2658 | `except Exception as e` en `_execute_function` | SOSPECHOSO | Captura TODAS las excepciones de las 15 funciones de negocio en un solo bloque. Un error de lógica interno (e.g. KeyError en `confirmar_venta`) devuelve `{"status": "error"}` al LLM que puede responder de forma confusa en lugar de elevar el error. |
| L2707-2710 | `except Exception` en `_summarize_context` | OK | Resumir es best-effort. |
| L2775-2777 | `except Exception` en `_generate_handoff_summary` | OK | Resumen de handoff es best-effort. |

---

## 10. Cobertura aparente de tests

### Funciones CON tests directos visibles
- `process_message` (flujo completo): `test_ferreteria_setup.py` (biz_01..biz_13, struct_01..struct_12, harden_01..harden_07, prev_*), `test_ferreteria_vnext.py`, `test_ferreteria_phase4_continuity.py`
- `_try_ferreteria_pre_route` / `_try_ferreteria_intent_route`: cubiertos indirectamente por los mismos tests de integración
- `_process_compound_modify`: `test_b22a_compound_modify.py`
- `_process_compound_mixed`: `test_b22c_compound_mixed.py`
- `_normalize_list_to_items` / `_is_structured_list`: `test_l1_list_normalizer.py`
- `_ADDITIVE_INLINE_RE`, `_CLARIF_TRAIL_CHARS`: `test_f1_compound_routing.py`, `test_dt17b_section4_additive.py`
- `_ESCALATION_REQUEST_KEYWORDS`: `test_escalation_safety_net.py`
- `_chat_with_functions` (price validator R2): `test_r2_integration.py`
- Refresh stale prices R3: `test_r3_integration.py`, `test_stale_prices.py`

### Funciones SIN tests directos visibles
- `_load_policies` — sin test directo de path no existente
- `_resolve_runtime_db_path` — sin test de path relativo vs absoluto
- `_quote_channel` — sin test
- `_persist_quote_state` — cubierto solo indirectamente
- `_handle_lite_mode` — sin test directo de branch "stock/precio"
- `_handle_sales_contract_reply` — sin test de missing_fields path
- `_detect_ferreteria_browse_category` — sin test de alias individuales
- `_consultative_browse_cta` — sin test
- `_format_ferreteria_products_reply` — sin test de heading override
- `_slim_function_result` — sin test de `offer.product` y `upsell_product` paths
- `_build_sales_intelligence_meta` — sin test
- `_run_sales_intelligence` — sin test de exception path
- `_summarize_context` — sin test
- `_generate_handoff_summary` — sin test de exception path
- `_get_state` / `_save_state` — sin test
- `close` (L215 vs L2805) — sin test de doble close

---

## 11. Top 10 oportunidades de mejora

1. **[IMPACTO ALTO / ESFUERZO ALTO] Descomponer `_try_ferreteria_pre_route`** en 8–10 métodos privados, uno por sección numerada. Crear helper `_commit_cart(session_id, items, event_type, payload, user_message, state_v2)` que encapsule el triplete get_suggestions+generate_response+persist. Elimina ~14 repeticiones.

2. **[IMPACTO ALTO / ESFUERZO MEDIO] Eliminar import muerto `tenant_manager`** (L20). Riesgo cero, reduce confusión para futuros desarrolladores.

3. **[IMPACTO ALTO / ESFUERZO MEDIO] Mover imports de `search_validator` al encabezado del módulo** y extraer la lógica L1/L2 a un método privado `_validated_search(query, session_id)`. Elimina 3 bloques de código idéntico.

4. **[IMPACTO ALTO / ESFUERZO BAJO] Extraer la lógica de option_select** a `_apply_option_selection(cart, pending_lines, opt_idx, qty)`. Elimina ~40 líneas duplicadas entre `_try_ferreteria_pre_route` y `_process_compound_modify`.

5. **[IMPACTO MEDIO / ESFUERZO BAJO] Eliminar el `close()` duplicado** (L2805). El primero (L215) tiene lógica más completa; el segundo solo llama a `quote_store.close()` y `db.close()` directamente. Mantener solo L215 y verificar que todos los callers lo usen.

6. **[IMPACTO MEDIO / ESFUERZO BAJO] Reemplazar el string duplicado de rechazo** (L1594 y L1641) por una constante de módulo `_SPEC_MISMATCH_REPLY`.

7. **[IMPACTO MEDIO / ESFUERZO MEDIO] Usar `try/finally` en `process_message`** para garantizar que `TurnEvent.log()`, `record_turn()` y `record_latency_bucket()` siempre se llamen, independientemente del return path.

8. **[IMPACTO MEDIO / ESFUERZO MEDIO] Unificar `_summarize_context` y `_generate_handoff_summary`** en un único método `_summarize_conversation(messages, mode)` para reducir la deuda de mantenimiento de prompts.

9. **[IMPACTO MEDIO / ESFUERZO BAJO] Convertir `_execute_function` de cadena `if/elif` a dispatch dict** `{func_name: handler}`. Mejora la legibilidad y permite testear cada handler por separado.

10. **[IMPACTO BAJO / ESFUERZO BAJO] Reemplazar f-strings en logging** (L2255, L2590, L2655, L2776) por patrón `%s` para consistencia y para que el mensaje de log no se evalúe cuando el nivel de logging no está activo.

---

## 12. Dudas para Julian

1. **`tenant_manager` (L20)**: ¿fue usado en alguna versión anterior y quedó como import muerto, o hay planes de usarlo? Si no, se puede eliminar sin riesgo.

2. **Doble `close()`** (L215 y L2805): ¿cuál es el `close()` canónico? El de L2805 no llama a `self.quote_store.close()` con el guard de `getattr`, cosa que sí hace el de L215. ¿Hay código externo que depende del segundo?

3. **`sess["customer_delivery_info"]["raw"]`** acumula texto libre sin estructura. ¿El reviewer humano actualmente lee ese campo? ¿Hay planes de parsear `shipping_zone`, `customer_name`, `billing_target` como mencionan los comentarios de L2147?

4. **`confirmar_venta` borra el estado completo de sesión** (`self.sessions[session_id] = {}`). Si en el futuro se agregan datos importantes en sesión antes de confirmar (por ejemplo, `customer_delivery_info`), se perderán. ¿Es esto intencional?

5. **Los imports diferidos de handlers** (`PolicyHandler`, `EscalationHandler`, `OfftopicHandler`) en `__init__` (L188-190) sugieren que hubo un problema de importación circular. ¿Ese problema sigue activo o se puede mover al top-level del módulo?

6. **La constante `MAX_WORKERS_OVERRIDE`** (L1502) documenta un crash de Python 3.14 + ThreadPoolExecutor + SQLite. ¿Hay planes de migrar a Python 3.14 en producción? Si es así, habría que resolver el SIGSEGV de raíz.

7. **Los "phase" markers** (Phase 3, Phase 6–10) y tickets (B22a, R2, etc.) no están documentados fuera del código. ¿Existe un documento de arquitectura externo que mapee estos nombres a decisiones de diseño? Sería muy útil para onboarding.

8. **El guard de `fq.looks_like_acceptance`** (L932) recibe `chatgpt_client` como argumento — ¿eso implica que `looks_like_acceptance` puede hacer una llamada LLM? Si es así, ese costo debería estar documentado en el mapa de llamadas LLM.
