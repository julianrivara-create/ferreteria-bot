# Audit D2 — bot_sales/ferreteria_quote.py

**HEAD:** `9f7369d`
**LOC totales:** 2366
**Estado:** Pieza histórica en transición a `bot_sales/services/`

---

## Resumen

- El archivo es **un módulo funcional puro** sin clases propias. ~68 funciones/helpers a nivel módulo.
- Concentra **6 responsabilidades distintas** que deberían vivir en módulos separados: parsing, resolución, scoring, formateo de respuestas, detección de intent, mutación de cart.
- **Ninguna mutación es in-place**: todos los `apply_*` retornan listas nuevas. Diseño funcional limpio.
- El **único LLM call** es opcional y con fallback apropiado (`looks_like_acceptance`). El docstring dice "no LLM calls" pero aplica a la ruta principal — es técnicamente correcto pero engañoso.
- **Dos funciones son paralelas con services/**: `_score_product` y `_significant_words` existen también en `catalog_search_service.py`. No son copias exactas pero comparten el mismo algoritmo.
- **Deuda de transición significativa**: todo el formatter (`generate_quote_response`, `generate_sales_guidance_response`), los detection helpers (`looks_like_*`), y los knowledge map accessors deberían estar fuera de este archivo.
- **Más de 40 strings de cliente hardcodeados** en el cuerpo de las funciones — sin template layer.
- `resolve_quote_item` (340 LOC, 7 ramas de retorno) es el mayor riesgo de mantenimiento del proyecto.

---

## 1. Mapa de clases y funciones

**No hay clases.** El archivo es 100% funciones a nivel módulo.

### Constantes de módulo
| Constante | Línea | Valor | Candidata a config |
|---|---|---|---|
| `STALE_PRICE_THRESHOLD_MINUTES` | 86 | 30 | Sí |
| `_SCORE_HIGH` | 434 | 5.0 | Sí |
| `_SCORE_LOW` | 436 | 2.0 | Sí |
| `_FUZZY_CUTOFF` | 476 | 0.82 | Sí |
| `_SIGNIFICANT_WORDS_MIN_LEN` | 270 | 3 | Sí |
| `_DISTINCTIVE_BOOST` | 1880 | 1.5 | Sí |
| `_MARGIN_MIN` | 1881 | 0.2 | Sí |
| `_EXACT_DISTINCTIVE_BONUS` | 1882 | 0.45 | Sí |
| `BROAD_REQUEST_REPLY` | 1282 | string | Sí (template) |
| `MERGE_VS_REPLACE_QUESTION` | 2350 | string | Sí (template) |

### Tabla de funciones

| # | Función | Línea | LOC | Visibilidad | Responsabilidad |
|---|---|---|---|---|---|
| 1 | `_now_iso` | 89 | 3 | privada | Helper timestamp UTC |
| 2 | `is_price_stale` | 94 | 23 | **pública** | Detección precio vencido |
| 3 | `refresh_stale_prices` | 119 | 58 | **pública** | Re-validar precios obsoletos |
| 4 | `_knowledge_map` | 184 | 2 | privada | Accessor knowledge dict |
| 5 | `_synonym_entries` | 188 | 2 | privada | Accessor sinónimos |
| 6 | `_family_rules` | 192 | 2 | privada | Accessor reglas de familia |
| 7 | `_clarification_rules` | 196 | 2 | privada | Accessor reglas clarificación |
| 8 | `_blocked_terms` | 200 | 2 | privada | Accessor términos bloqueados |
| 9 | `_complementary_rules` | 204 | 2 | privada | Accessor reglas complementarias |
| 10 | `_acceptance_patterns` | 208 | 4 | privada | Accessor patrones aceptación |
| 11 | `_normalize` | 213 | 2 | privada | Thin wrapper normalize_basic |
| 12 | `_knowledge_map_item_family` | 217 | 11 | privada | Merge item_family_map con defaults |
| 13 | `_knowledge_map_category_aliases` | 229 | 4 | privada | Merge category_aliases con defaults |
| 14 | `_detect_category` | 235 | 15 | privada | Infer categoría desde texto |
| 15 | `_get_expected_families` | 252 | 12 | privada | Union familias aceptables por keywords |
| 16 | `_singularize` | 281 | 20 | privada | Plural→singular español conservador |
| 17 | `_significant_words` | 303 | 7 | privada | Extrae tokens significativos |
| 18 | `_product_text` | 312 | 10 | privada | Concatena campos producto para scoring |
| 19 | `_is_mm_dim` | 324 | 2 | privada | Guard dimensión en mm |
| 20 | `_is_fraction_dim` | 328 | 2 | privada | Guard dimensión fraccionaria |
| 21 | `_score_dimension_alignment` | 332 | 27 | privada | Score alineación dimensional |
| 22 | `_score_product` | 361 | 70 | privada | Score de matching producto-query |
| 23 | `_families_without_para_context` | 446 | 24 | privada | Filtra familias de contexto "para X" |
| 24 | `_build_search_terms` | 479 | 37 | privada | Expande query con sinónimos/fuzzy |
| 25 | `_needs_variant_clarification` | 518 | 5 | privada | Detecta si familia necesita dimensión |
| 26 | `get_complementary_suggestions` | 531 | 39 | **pública** | Sugerencias complementarias catalog-verified |
| 27 | `get_cross_sell_suggestions` | 572 | 70 | **pública** | Cross-sell basado en categorías |
| 28 | `_extract_qty_and_item` | 699 | 11 | privada | Extrae qty+item desde texto raw |
| 29 | `_extract_qty_from_phrase` | 718 | 15 | **semi-pública** | Extrae qty embebida en frase |
| 30 | `parse_quote_items` | 739 | 46 | **pública** | Parsea mensaje multi-ítem |
| 31 | `resolve_quote_item` | 791 | 340 | **pública** | Core: resuelve ítem contra catálogo |
| 32 | `_ambiguity_clarification` | 1137 | 11 | privada | Genera prompt clarificación |
| 33 | `_parse_price` | 1154 | 9 | privada | Parsea precio de producto dict |
| 34 | `_compute_subtotal` | 1165 | 9 | privada | Calcula subtotal precio×qty |
| 35 | `_format_price` | 1176 | 6 | privada | Formatea precio en ARS |
| 36 | `_match_known_phrase` | 1188 | 3 | privada | Match de frase contra lista |
| 37 | `looks_like_acceptance` | 1193 | 28 | **pública** | Detecta intención de aceptar |
| 38 | `looks_like_customer_info` | 1236 | 3 | **pública** | Detecta datos de cliente |
| 39 | `generate_acceptance_response` | 1241 | 35 | **pública** | Genera respuesta de aceptación |
| 40 | `_resolved_family_set` | 1300 | 6 | privada | Set de familias resueltas |
| 41 | `_pending_quote_items` | 1308 | 6 | privada | Filtra ítems pendientes |
| 42 | `_quote_intro_line` | 1316 | 9 | privada | Elige frase de apertura de cotización |
| 43 | `_quote_next_step_line` | 1327 | 12 | privada | Elige frase de cierre/CTA |
| 44 | `_clean_header_label` | 1362 | 4 | privada | Limpia header para display |
| 45 | `generate_quote_response` | 1368 | 159 | **pública** | Genera respuesta WhatsApp de cotización |
| 46 | `_resolved_snapshot_lines` | 1529 | 16 | privada | Líneas resumidas de ítems resueltos |
| 47 | `_focus_resolved_item` | 1547 | 6 | privada | Último ítem resuelto como foco |
| 48 | `_cheapest_alternative` | 1555 | 16 | privada | Alternativa más barata de un ítem |
| 49 | `_sales_use_phrase` | 1573 | 11 | privada | Frase de uso según preferencias |
| 50 | `_budget_fits` | 1586 | 4 | privada | Guard precio vs presupuesto |
| 51 | `_format_budget` | 1592 | 2 | privada | Formatea budget_cap |
| 52 | `generate_sales_guidance_response` | 1596 | 170 | **pública** | Genera respuesta de venta guiada |
| 53 | `looks_like_reset` | 1787 | 4 | **pública** | Detecta "nuevo presupuesto" |
| 54 | `looks_like_additive` | 1793 | 2 | **pública** | Detecta "agregame/sumame" |
| 55 | `detect_option_selection` | 1797 | 41 | **pública** | Detecta selección de opción A/B |
| 56 | `needs_disambiguation` | 1840 | 16 | **pública** | Detecta si falta target de ítem |
| 57 | `_word_weight` | 1886 | 3 | privada | Peso de token para scoring de línea |
| 58 | `_match_words` | 1891 | 19 | privada | Token set para line-targeting |
| 59 | `_match_to_line` | 1912 | 65 | privada | Matchea mensaje con QuoteItem más cercano |
| 60 | `apply_clarification` | 1979 | 97 | **pública** | Aplica clarificación a ítem pendiente |
| 61 | `_is_increment_request` | 2089 | 14 | privada | Detecta "otro X / 2 más" |
| 62 | `_increment_existing_line` | 2105 | 10 | privada | Incrementa qty de línea existente |
| 63 | `apply_additive` | 2117 | 99 | **pública** | Agrega ítems/incrementa qty |
| 64 | `_primary_sku` *(nested)* | 2165 | 3 | privada | SKU del producto principal |
| 65 | `_primary_model` *(nested)* | 2169 | 6 | privada | Model del producto principal |
| 66 | `_same_catalog_product` *(nested)* | 2176 | 11 | privada | Compara ítems por SKU+model |
| 67 | `generate_updated_quote_response` | 2218 | 9 | **pública** | Thin wrapper de generate_quote_response |
| 68 | `session_guard_response` | 2229 | 12 | **pública** | Respuesta guard con menú de opciones |
| 69 | `looks_like_remove` | 2255 | 2 | **pública** | Detecta intención de quitar ítem |
| 70 | `apply_remove` | 2259 | 22 | **pública** | Remueve ítem del presupuesto |
| 71 | `looks_like_replace` | 2296 | 2 | **pública** | Detecta "cambiá X por Y" |
| 72 | `apply_replace` | 2300 | 44 | **pública** | Reemplaza ítem en presupuesto |
| 73 | `looks_like_merge_answer` | 2357 | 4 | **pública** | Detecta respuesta "sumalo" |
| 74 | `looks_like_new_answer` | 2363 | 4 | **pública** | Detecta respuesta "nuevo" |

---

## 2. Top 10 funciones más largas — análisis detallado

### 1. `resolve_quote_item` — 340 LOC (L791–L1130)

**Signature:** `(parsed: Dict, logic: Any, knowledge: Optional[Dict]) -> QuoteItem`

El corazón histórico del archivo. Es literalmente un motor de decisión con 7 ramas de retorno distintas:
1. `blocked_term` → queda bloqueado por término amplio
2. `qty_presentation` → unidad de presentación sin qty individual (DT-16)
3. `resolved` → match de alta confianza, no ambiguo
4. `variant_ambiguity` → dos productos de la misma familia con score similar
5. `blocked_by_missing_info` + match → autopick bloqueado por dimensión
6. `ambiguous` (weak_match) → score plausible pero bajo
7. `category_fallback` → sin match por term, fallback por categoría
8. `blocked_by_missing_info` sin match → familia conocida pero sin dimensión
9. `unresolved` → sin match ni categoría

**Problemas:**
- Función demasiado larga para testear de manera aislada por rama (aunque existen tests)
- La construcción de los 9 dicts de QuoteItem es repetitiva — hay ~300 líneas de literales dict casi idénticos con diferente `status` y `issue_type`
- Los hardcodes de familia ("tarugo", "taco", "silicona", "teflon" en L915–920) son reglas de negocio enterradas en el resolver
- La deduplicación por SKU (L901–911) debería ser una función separada
- `scored`, `deduped`, `safe_alts` como vars intermedias hacen el flujo difícil de seguir

**Oportunidad:** Extraer un `_build_quote_item(status, ...)` constructor para eliminar los 9 dict literales. Separar la lógica de scoring en un `ScoreResult` dataclass.

---

### 2. `generate_sales_guidance_response` — 170 LOC (L1596–L1765)

**Signature:** `(open_items: List[QuoteItem], *, mode: str, sales_preferences: Optional[Dict]) -> str`

Genera respuestas de venta guiada para 3 modos (`price`, `comparison`, `recommendation`). Función triple: cada modo es casi una función entera, unidas por una firma común.

**Problemas:**
- Strings del cliente completamente hardcodeados ("Entiendo, vamos a cuidar el numero sin mandarte a algo que despues no te sirva", "Hoy lo compararia asi", etc.)
- Lógica de `budget_cap` y `decision_style` duplicada en los 3 modos
- Actúa como un template engine ad-hoc con string concatenation
- No tiene tests directos verificados (testear los strings exactos es frágil)

**Oportunidad:** Separar en 3 funciones privadas (`_price_mode_response`, `_comparison_mode_response`, `_recommendation_mode_response`) y mover los strings a un módulo de templates.

---

### 3. `generate_quote_response` — 159 LOC (L1368–L1526)

**Signature:** `(resolved_items: List[QuoteItem], complementary: Optional[List], is_update: bool) -> str`

El formatter principal de cotización WhatsApp. Acumula líneas en listas (`resolved_lines`, `ambiguous_data`, `blocked_questions`, `unresolved_lines`) y luego los ensambla.

**Problemas:**
- Strings de cliente inline: "Te armé esto:", "Actualicé esto:", "Válido 24hs · ¿Confirmás?", "También suelen llevar:", etc.
- La lógica de `grand_total` y `stale` está mezclada con el formateo
- El ensamblado final (L1436–1526) tiene ~90 LOC de if/elif/append — difícil de seguir el flujo de secciones
- La constante `STALE_PRICE_THRESHOLD_MINUTES` aparece en el texto del footnote: si cambia el threshold, el texto no actualiza automáticamente (usa f-string sí, pero el texto en español es hardcode)

**Oportunidad:** Separar en sub-renderers: `_render_resolved_section`, `_render_ambiguous_section`, `_render_footer`. Mover strings a templates.

---

### 4. `apply_additive` — 99 LOC (L2117–L2215)

**Signature:** `(message: str, open_items: List[QuoteItem], logic: Any, knowledge: Optional[Dict]) -> List[QuoteItem]`

Gestiona agregar ítems al carrito activo. Dos caminos: (1) incremento de qty sobre línea existente, (2) parse de nuevos ítems + dedup por frase+SKU (DT-17/17b).

**Problemas:**
- Tiene 3 funciones nested (`_primary_sku`, `_primary_model`, `_same_catalog_product`) que deberían ser helpers de módulo
- La lógica de dedup en L2188–2214 tiene dos capas (norm phrase + SKU) que se solapan conceptualmente con el loop de incremento de L2134–2157
- El comentario en L2182 referencia un fixture de test: "guards against test fixtures that reuse a sentinel SKU" — lógica de producción condicionada por tests

**Oportunidad:** Extraer las funciones nested, separar `_handle_increment` y `_merge_or_append_items`.

---

### 5. `apply_clarification` — 97 LOC (L1979–L2075)

**Signature:** `(clarification_text: str, open_items: List[QuoteItem], logic: Any, target_line_id: Optional[str], knowledge: Optional[Dict]) -> List[QuoteItem]`

Aplica la respuesta de un usuario a un ítem pendiente. Usa `_match_to_line` para encontrar el target, combina el texto de clarificación con el texto original, y re-resuelve via `resolve_quote_item`.

**Problemas:**
- La lógica de construcción de `combined` (L2012–2017) mezcla heurísticas de string que son frágiles
- El `qty_override` path (DT-16, L2018–2034) es correcto pero su comentario de dos líneas es el único indicio de por qué existe
- `improved` (L2046–2051) calcula progreso pero la condición es compleja y podría ocultar regresiones sutiles

**Sano:** El patrón de "devuelve lista nueva sin mutar" está bien aplicado aquí.

---

### 6. `_score_product` — 70 LOC (L361–L430)

**Signature:** `(product: Dict, requested_normalized: str, requested_families: Optional[List], requested_dimensions: Optional[Dict], knowledge: Optional[Dict]) -> float`

Scoring multidimensional: overlap de palabras, gate de familia, alineación dimensional, vector score bonus. Retorna 0–10 clampado.

**Problemas:**
- La fórmula del vector score bonus (L427: `(vector_score - 0.7) * 16.6`) tiene un comentario aclaratorio pero el 16.6 es un magic number derivado de `5/(1.0-0.7)` — no obvio
- Las penalidades hardcoded (-8 para familia wrong, -4 cross-unit, -3 sin overlap, -2 first-word mismatch) deberían ser constantes nombradas
- Existe una versión casi idéntica en `CatalogSearchService._score_product` (ver §4)

---

### 7. `get_cross_sell_suggestions` — 70 LOC (L572–L641)

**Signature:** `(resolved_items: List[QuoteItem], logic: Any, cross_sell_rules: Optional[List[Dict]]) -> List[str]`

Busca productos de categorías complementarias basándose en `cross_sell_rules` del perfil. Tiene acceso directo a `logic.db.find_by_category`.

**Problema:**
- Único lugar del archivo que accede a `logic.db` directamente (L623) — el resto accede via `logic.buscar_stock` y `logic.buscar_por_categoria`. Viola la abstracción del `logic` object.
- `except Exception: continue` (L624-625) silencia errores de DB

---

### 8. `_match_to_line` — 65 LOC (L1912–L1976)

**Signature:** `(message: str, lines: List[QuoteItem], min_overlap: float, min_margin: float) -> Optional[QuoteItem]`

Scoring de mejor línea para un mensaje. Usa `_DISTINCTIVE_TOKENS` para dar peso extra a tokens de dimensión/material. Retorna `None` si el margen entre el mejor y segundo es menor que `_MARGIN_MIN`.

**Sano:** Bien encapsulado, lógica de scoring clara, el "refuse to guess" con margen es un buen diseño defensivo.

---

### 9. `refresh_stale_prices` — 58 LOC (L119–L176)

**Signature:** `(active_quote: List[QuoteItem], lookup_fn: Callable, threshold_minutes: int) -> Tuple[List[QuoteItem], List[str]]`

Re-valida precios vencidos contra el catálogo. Retorna lista actualizada + mensajes de notificación.

**Problema destacado (L133–137):** El docstring dice explícitamente que **no está conectado al flujo del bot.py** — es código completo pero no activo ("a pending task for after the Slang/bot.py merge"). Es deuda de integración, no de código.

---

### 10. `parse_quote_items` — 46 LOC (L739–L784)

**Signature:** `(message: str) -> List[Dict[str, Any]]`

Parsea un mensaje multi-ítem en lista de dicts. Strip de saludos/fillers, split por delimitadores (coma, punto y coma, "y", "+", "/"), dedup, extracción de qty.

**Sano:** Relativamente conciso, bien testeado (`test_quote_parser.py`). El regex inline L753 (`re.split(r"\s*(?:,|;|:|\by\b|\be\b|\+|/)\s*", ...)`) podría ser constante nombrada.

---

## 3. Regex centralizadas

| Regex | Línea | Propósito | Duplicación |
|---|---|---|---|
| `_PARA_CONTEXT_WORD_RE` | 443 | Captura la palabra después de "para" para filtrar familias de contexto de uso | Única |
| `_GREETING_RE` | 648 | Strip de saludos al inicio del mensaje | Única. Candidata a `ferreteria_language.py` |
| `_FILLER_RE` | 654 | Strip de verbos de intención ("quiero", "necesito", "busco") | Única. Candidata a `ferreteria_language.py` |
| `_QTY_RE` | 691 | Extrae cantidad + unidad al inicio de un ítem ("2 latas de X") | Única |
| `_QTY_SCAN_RE` | 712 | Busca un número cardinal en cualquier posición del texto | Única |
| `_CUSTOMER_INFO_RE` | 1224 | Detecta "soy", "me llamo", "dirección", teléfono, etc. | Única |
| `_HEADER_CLEANUP_RE` | 1342 | Strip de frases de intent al inicio de headers de display | Única. Candidata a formatter module |
| `_HEADER_ARTICLE_RE` | 1356 | Strip de artículos iniciales en headers ("el/la/los/las") | Única |
| `_ADDITIVE_RE` | 1779 | Detecta verbos de adición ("agrega", "suma", "también necesito") | Única |
| `_INCREMENT_RE` | 2082 | Detecta patrones "otro X", "2 más", "del mismo" | Única |
| `_REMOVE_RE` | 2247 | Detecta verbos de remoción ("sacá", "quitá", "eliminá") | Única |
| `_REPLACE_RE` | 2287 | Detecta reemplazos "cambiá X por Y" | Única. **Bug potencial: incluye "best" (inglés) en L2288** |

**No hay regex duplicadas dentro del archivo.**

**Observación sobre `_REPLACE_RE`:** En la línea 2288, la alternativa `best` aparece en la lista de verbos españoles:
```python
r"^(?:cambia|cambiá|reemplaza|reemplazá|mejor pone|mejor pon|en vez de|best)\s+"
```
"best" en inglés no tiene sentido aquí — parece un remanente de debugging o un error de edición.

---

## 4. Redundancia con bot_sales/services/

| Función en `ferreteria_quote.py` | Equivalente en `services/` | Estado de migración |
|---|---|---|
| `_score_product` (L361, ~70 LOC) | `CatalogSearchService._score_product` (catalog_search_service.py:197) | **Paralelo, no unificado.** fq agrega dimension alignment, family gate, vector bonus. El service es una versión más simple. |
| `_significant_words` (L303, ~7 LOC) | `CatalogSearchService._significant_words` (catalog_search_service.py:294) | **Duplicado funcional.** fq agrega singularización; service no. Mismo algoritmo de stop-words. |
| `_parse_price` (L1154, ~9 LOC) | `price_validator._parse_ars_value` (price_validator.py:30) | **Similar pero propósito diferente.** `_parse_ars_value` parsea texto de respuesta LLM; `_parse_price` parsea dicts de producto. No son duplicados directos. |
| `is_price_stale` / `refresh_stale_prices` | — | **Sin equivalente en services/.** Es lógica de dominio pendiente de conectar a bot.py |
| `get_complementary_suggestions` | — | **Sin equivalente.** Candidata a `complementary_service.py` |
| `get_cross_sell_suggestions` | — | **Sin equivalente.** Candidata a `cross_sell_service.py` |
| `looks_like_acceptance` / `looks_like_customer_info` | `quote_automation_service` (indirectamente) | **Sin equivalente directo.** Deberían estar en un `intent_classifier.py` |
| `looks_like_reset` / `looks_like_additive` / `looks_like_remove` / `looks_like_replace` | — | **Sin equivalente.** Los `looks_like_*` son un intent detection layer disperso |
| `generate_quote_response` / `generate_sales_guidance_response` / `generate_acceptance_response` | — | **Sin equivalente.** Todo el formatter vive aquí — debería ser `quote_formatter.py` |
| `apply_clarification` / `apply_additive` / `apply_remove` / `apply_replace` | — | **Sin equivalente.** Candidatos a `quote_mutation_service.py` |
| `_knowledge_map` + 6 accessors | — | **Sin equivalente.** Deberían ser un `KnowledgeRegistry` o accesados via `knowledge_service` |

**Núcleo legítimo que debería quedarse (o ser el destino de la migración):**
- `resolve_quote_item` — el motor de resolución. No tiene equivalente en services/, es la razón de ser del archivo.
- `parse_quote_items` — el parser específico de WhatsApp/ferretería.
- Toda la lógica de scoring dimensional (`_score_dimension_alignment`, `_singularize`, `_families_without_para_context`) — es conocimiento de dominio que no existe en ningún service.

---

## 5. Mutaciones de quote/state/cart

**Todas las operaciones son funcionales (no mutan en-place). Patrón sano.**

| Función | Patrón | Notas |
|---|---|---|
| `resolve_quote_item` | Crea QuoteItem nuevo | Constructor puro |
| `apply_clarification` | Retorna `List[QuoteItem]` nueva | Preserva line_id |
| `apply_additive` | Retorna `List[QuoteItem]` nueva | Agrega o incrementa |
| `apply_remove` | Retorna `(List[QuoteItem], str)` | Filter por line_id |
| `apply_replace` | Retorna `(List[QuoteItem], str)` | Swap por line_id |
| `refresh_stale_prices` | Retorna `(List[QuoteItem], List[str])` | No conectado aún |
| `_increment_existing_line` | Retorna `dict(line)` modificado | `dict()` copy explícita |

El único estado que persiste hacia afuera es a través del caller (`bot.py`) que guarda en sesión. Este archivo no toca la sesión directamente.

**Riesgo latente:** `apply_additive` usa `result = list(open_items)` pero luego hace list comprehensions que crean nuevos dicts — correcto. Sin embargo, los dicts de QuoteItem son referencias; si alguien modifica un QuoteItem externamente después de recibir la lista, podría corromper el estado en caller. Es una deuda de inmutabilidad suave (no hay dataclass frozen).

---

## 6. Llamadas a LLM

**Una sola llamada, condicional y con fallback:**

```python
# L1207-1218 — looks_like_acceptance()
if chatgpt_client is not None:
    try:
        from bot_sales.routing.acceptance_detector import AcceptanceDetector
        detector = AcceptanceDetector(chatgpt_client, acceptance_patterns=patterns)
        result = detector.detect(message)
        if result.get("action") == "accept" and result.get("confidence", 0.0) >= 0.5:
            return True
        if result.get("action") in ("reject", "none") and result.get("confidence", 0.0) >= 0.5:
            return False
        # Low-confidence → fall through to keyword check
    except Exception:
        pass  # keyword fallback below
```

**Veredicto:** Apropiado. La ruta principal es determinística (keyword matching). El LLM es un enhancement opcional, no un dependency. El `except Exception: pass` aquí es razonablemente justificado — si el LLM falla, el sistema degrada gracefully a reglas.

**Inconsistencia:** El módulo docstring (L24) dice explícitamente "No NLP / LLM calls / external deps beyond stdlib and business_logic." Esta llamada viola esa declaración. El LLM es un external dep que entra por `chatgpt_client` — técnicamente el módulo no lo importa directamente, pero sí lo usa. El docstring debería actualizarse.

---

## 7. Try/except amplios

| Ubicación | Exceptions capturadas | Justificación |
|---|---|---|
| L109-116 (`is_price_stale`) | `(ValueError, TypeError)` | Específico. Parseo de timestamp ISO — apropiado. |
| L622-625 (`get_cross_sell_suggestions`) | `Exception` | **Broad.** Cubre cualquier error de `logic.db.find_by_category`. Justificado por ser acceso DB externo, pero silencia errores de programación también. |
| L1158-1161 (`_parse_price`) | `(ValueError, TypeError)` | Específico. Parseo de float/string — apropiado. |
| L1208-1218 (`looks_like_acceptance`) | `Exception` | **Broad.** Safety gate para LLM call con fallback. El `pass` silencioso es intencional y documentado. |

Solo 2 de 4 son verdaderamente broad (L622 y L1218). Ambos tienen justificación contextual. No hay `except Exception: raise` ocultos ni swallows de errores de lógica.

---

## 8. Hardcoded business strings

### Mensajes al cliente hardcodeados (deberían ser templates)

| Línea | Contenido | Función |
|---|---|---|
| 871 | `"¿Cuántas unidades necesitás?"` | `resolve_quote_item` — DT-16 |
| 1001 | `"Falta una dimensión clave..."` | `resolve_quote_item` |
| 1028 | `"Encontre opciones relacionadas. Confirma el tipo exacto."` | `resolve_quote_item` |
| 1071 | `f"Opciones en categoria {category}"` | `resolve_quote_item` |
| 1096 | `"Conozco la familia, pero falta una dimensión clave..."` | `resolve_quote_item` |
| 1121 | `"No encontre una coincidencia clara en el catalogo."` | `resolve_quote_item` |
| 1249-1255 | Bloque de aceptación con pending | `generate_acceptance_response` |
| 1257-1261 | `"✓ *Recibimos tu pedido para revisión.*..."` | `generate_acceptance_response` |
| 1282-1288 | `BROAD_REQUEST_REPLY` (multi-línea) | constante de módulo |
| 1319-1324 | Frases de intro de cotización | `_quote_intro_line` |
| 1332-1338 | Frases de next-step | `_quote_next_step_line` |
| 1444-1445 | `"Te armé esto:" / "Actualicé esto:"` | `generate_quote_response` |
| 1506-1513 | Closings de cotización + "Válido 24hs" | `generate_quote_response` |
| 1520-1523 | `"También suelen llevar:"` | `generate_quote_response` |
| 1606-1619 | Fallbacks sin focus_item | `generate_sales_guidance_response` |
| 1636-1763 | Todo el bloque de sales guidance text | `generate_sales_guidance_response` |
| 2232-2239 | `session_guard_response` — menú de opciones | `session_guard_response` |
| 2269-2275 | Error messages de `apply_remove` | `apply_remove` |
| 2310-2312 | Error message de `apply_replace` | `apply_replace` |
| 2350-2354 | `MERGE_VS_REPLACE_QUESTION` | constante de módulo |

### Umbrales/constantes de negocio que deberían estar en config

| Constante | Línea | Valor | Motivo |
|---|---|---|---|
| `STALE_PRICE_THRESHOLD_MINUTES` | 86 | 30 | Política de negocio, debería ser tenant-configurable |
| `_SCORE_HIGH` | 434 | 5.0 | Umbral de decisión scoring |
| `_SCORE_LOW` | 436 | 2.0 | Umbral de decisión scoring |
| `_FUZZY_CUTOFF` | 476 | 0.82 | Cutoff de difflib — tunable |
| `_DISTINCTIVE_BOOST` | 1880 | 1.5 | Peso de tokens distintivos |
| `_MARGIN_MIN` | 1881 | 0.2 | Margen mínimo para no adivinar |
| Score penalties | 396–427 | -8, -4, -3, -2, +5, +3 | Todos magic numbers |
| `2` (máx sugerencias) | 638 | 2 | `get_cross_sell_suggestions` |
| `3` (límite snapshot) | 1529 | 3 | `_resolved_snapshot_lines` default |
| `5` (candidatos en scored) | 893 | 5 | Top N de buscar_stock |
| `[:1]`, `[:2]`, `[:3]` | múltiples | varios | Límites de productos para display |

---

## 9. apply_clarification, apply_additive, _process_compound_modify

### `apply_clarification` (DT-16, DT-16b)

**Dónde:** `ferreteria_quote.py` L1979–L2075

**Qué hace:** Recibe el texto de respuesta del cliente a una pregunta de clarificación. Encuentra el ítem pendiente correcto (vía `target_line_id` o `_match_to_line`), combina el texto del cliente con el texto original del ítem, y re-resuelve via `resolve_quote_item`.

**DT-16 fix (L2018–2025):** Para ítems bloqueados por `qty_presentation` (ej: "1 caja de tornillos" sin qty individual), extrae la cantidad del texto de clarificación. Antes de DT-16, el usuario decía "100 unidades" y el sistema re-buscaba "100 unidades tornillos" en el catálogo — fallaba.

**DT-16b fix (L2026–2034):** Cuando se extrae un `qty_override`, el texto de búsqueda al catálogo usa el `original` del ítem, no el texto combinado. Evita que el número "100" contamine la query de catálogo ("100 tornillos para drywall" es ambiguo; "tornillos para drywall" es preciso).

**Riesgo actual:** La heurística de `combined` (L2012–2017):
```python
if norm_clar.startswith(target_norm):
    combined = norm_clar
elif target_norm and target_norm in norm_clar.split():
    combined = norm_clar
else:
    combined = f"{target_norm} {norm_clar}".strip()
```
El `target_norm in norm_clar.split()` compara una frase multi-palabra contra tokens individuales — nunca será `True` si `target_norm` tiene más de una palabra (que es el caso habitual). La tercera rama es la que siempre ejecuta.

---

### `apply_additive` (DT-17, DT-17b)

**Dónde:** `ferreteria_quote.py` L2117–L2215

**DT-17 fix (L2117–2157):** Antes, si el usuario decía "agregame otro teflón" y ya había un teflón, se ignoraba el mensaje (dedup silencioso). Ahora `_is_increment_request` detecta "otro/2 más/del mismo" y llama a `_increment_existing_line` en lugar de agregar una línea nueva.

**DT-17b fix (L2176–2214):** Agrega dedup por SKU+model sobre la dedup por frase normalizada. Antes: "tornillos para drywall" y "caja de tornillos drywall" se detectaban como productos distintos aunque resolvieran al mismo SKU. Ahora `_same_catalog_product` los unifica y el qty se incrementa.

**Los 3 helpers nested** (`_primary_sku`, `_primary_model`, `_same_catalog_product`) son candidatos inmediatos a ser helpers de módulo — están acoplados solo a QuoteItem, no a `apply_additive`.

**Comentario en L2182** que referencia fixtures de test es una señal de que la lógica de negocio fue condicionada para hacer pasar tests, no para reflejar el dominio real.

---

### `_process_compound_modify`

**Dónde:** `bot_sales/bot.py` L1976 — **NO está en `ferreteria_quote.py`**

**Qué hace:** Es el orchestrator en el bot que procesa turnos compuestos ("agregame tornillos y sacame el taladro"). Itera sobre `sub_commands` del `TurnInterpreter` y despacha a `fq.apply_additive`, `fq.apply_remove`, `fq.looks_like_reset`, `fq.detect_option_selection`. Mantiene una copia del cart al inicio y restaura en caso de fallo.

**Relación con fq:** `_process_compound_modify` trata a `ferreteria_quote` como un toolkit de funciones puras. No llama a `resolve_quote_item` directamente — eso lo delega a `apply_additive` / `apply_clarification`. Esta separación es correcta en diseño.

**Observación:** La función tiene su propio `try/except` para cada sub-comando (L2008 implícito en la estructura) — robust. Pero la condición de "real progress" en additive (L2018–2028) es compleja y podría simplificarse.

---

## 10. Top 10 oportunidades de mejora

| # | Oportunidad | Impacto | Esfuerzo |
|---|---|---|---|
| 1 | **Unificar `_significant_words`** — la versión en fq y la de `CatalogSearchService` comparten algoritmo. Mover a `ferreteria_language.py` o un `text_utils.py` compartido. | Medio | Bajo |
| 2 | **Extraer `_build_quote_item(status, ...)`** — los 9 constructores de QuoteItem dict en `resolve_quote_item` son idénticos salvo 3-4 campos. Un constructor con defaults eliminaría ~200 LOC repetidas y centralizaría la definición del schema. | Alto | Bajo |
| 3 | **Corregir bug en `_REPLACE_RE` (L2288)** — `"best"` es inglés y no pertenece a la lista de verbos españoles. | Alto | Trivial |
| 4 | **Conectar `refresh_stale_prices` al flujo bot.py** — la función está completa pero el docstring dice explícitamente que no está wired. Es deuda de integración, no de código. | Alto | Bajo |
| 5 | **Mover strings de cliente a un módulo de templates** — ~40 strings hardcodeados impiden i18n, A/B testing y ajuste de tono sin tocar lógica. Crear `bot_sales/templates/quote_messages.py`. | Medio | Medio |
| 6 | **Mover los 3 nested helpers de `apply_additive` a nivel módulo** — `_primary_sku`, `_primary_model`, `_same_catalog_product` son reutilizables y testables por separado. | Bajo | Trivial |
| 7 | **Nombrar los magic numbers del scoring** — los penalties (-8, -4, -3, -2, +5, +3) y el factor `16.6` deberían ser constantes nombradas con sus fórmulas documentadas. | Bajo | Trivial |
| 8 | **Corregir la heurística muerta en `apply_clarification` (L2014)** — `target_norm in norm_clar.split()` nunca es `True` para frases multi-palabra. Debería ser `any(w in norm_clar for w in target_norm.split())` o simplemente eliminar la rama. | Medio | Trivial |
| 9 | **Mover `_GREETING_RE` y `_FILLER_RE` a `ferreteria_language.py`** — son preprocessing de lenguaje, no lógica de cotización. El módulo de lenguaje ya existe (`ferreteria_language.py`). | Bajo | Trivial |
| 10 | **Actualizar docstring del módulo (L24)** — "No NLP / LLM calls" es incorrecto desde que `looks_like_acceptance` acepta `chatgpt_client`. | Bajo | Trivial |

---

## 11. Plan tentativo de extinción

El objetivo no es eliminar el archivo sino reducirlo al **núcleo irreducible**: `resolve_quote_item` + su infraestructura de scoring dimensional.

### Fase 1 — Extracciones sin riesgo (sin cambio de lógica)
1. **`ferreteria_language.py`** ← `_GREETING_RE`, `_FILLER_RE`, `_FILLER_WORDS`, `_SENSITIVE_INTENT_WORDS`, `_normalize` wrapper
2. **`bot_sales/templates/quote_messages.py`** ← Todos los strings hardcodeados de `generate_acceptance_response`, `generate_quote_response`, `generate_sales_guidance_response`, `session_guard_response`, `BROAD_REQUEST_REPLY`, `MERGE_VS_REPLACE_QUESTION`
3. **Nivel módulo de `apply_additive`** ← `_primary_sku`, `_primary_model`, `_same_catalog_product`

### Fase 2 — Nuevos módulos (splitting funcional)
4. **`bot_sales/quote_formatter.py`** ← `generate_quote_response`, `generate_updated_quote_response`, `generate_acceptance_response`, `generate_sales_guidance_response`, `session_guard_response` + sus helpers (`_format_price`, `_parse_price`, `_clean_header_label`, etc.)
5. **`bot_sales/intent_classifier.py`** ← Todos los `looks_like_*` + `detect_option_selection` + `needs_disambiguation`
6. **`bot_sales/quote_mutation_service.py`** ← `apply_clarification`, `apply_additive`, `apply_remove`, `apply_replace`, `_match_to_line`, `_match_words`, `_word_weight`, `refresh_stale_prices`

### Fase 3 — Unificación de scoring (requiere coordinación con services/)
7. **`catalog_search_service.py` o nuevo `scoring.py`** ← `_score_product` unificado (fq + service), `_significant_words` unificado, `_singularize`
8. **`bot_sales/knowledge/registry.py`** ← Los 8 accessors `_knowledge_map_*`

### Fase 4 — El núcleo resultante
Después de Fase 1-3, `ferreteria_quote.py` debería quedar con:
- `resolve_quote_item` (~200 LOC si se extrae el constructor de QuoteItem)
- `parse_quote_items` (~46 LOC)
- `_build_search_terms` + infraestructura de scoring dimensional
- `is_price_stale` (si no fue al quote_mutation_service)
- Tipos y constantes de scoring

**Target:** ~500–600 LOC desde 2366. Sin cambios de comportamiento.

---

## 12. Dudas para Julian

1. **`_REPLACE_RE` con "best"** (L2288): ¿Es un bug o hay un caso de uso donde el cliente escribe en inglés? Si es bug, es un fix trivial.

2. **`refresh_stale_prices` no conectado** (L133–137): El docstring dice "pending task for after the Slang/bot.py merge". ¿Ese merge ya ocurrió? ¿Es un bloqueo activo o se descartó la feature?

3. **`get_cross_sell_suggestions` accede `logic.db` directamente** (L623): El resto del archivo usa la abstracción `logic.buscar_*`. ¿Hay una razón por la que esta función necesita acceso directo al DB, o fue un shortcut?

4. **`_needs_variant_clarification`** (L518): La función existe pero no hay ninguna llamada a ella en el archivo. ¿Se usa desde bot.py o tests? Si no tiene caller activo, podría ser dead code.

5. **`_get_expected_families`** (L252): Tampoco tiene llamadas visibles en este archivo. Mismo caso que el punto anterior — ¿es dead code o la usa otro módulo?

6. **`generate_sales_guidance_response` sin tests directos visibles**: ¿Está cubierta por tests de integración? Los strings hardcodeados hacen que los tests unitarios sean frágiles — ¿hay tests de comportamiento en su lugar?

7. **El `_score_product` de `CatalogSearchService` vs el de `ferreteria_quote`**: ¿El service fue creado antes o después que el de fq? ¿Hay intención de unificarlos o se mantienen paralelos intencionalmente por tener propósitos distintos (catalog browse vs quote resolution)?

8. **Los penalty values** (`-8`, `-4`, `-3`, `-2`, `+5`, `+3`): ¿Están documentados en algún lugar sus fundamentos? ¿Hay un dataset de evaluación con el que se calibraron, o son empíricos? Si son empíricos, el riesgo de tocarlos es alto.
