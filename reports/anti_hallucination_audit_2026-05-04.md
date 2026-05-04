# Auditoría Anti-Alucinación de Precios — 2026-05-04

**Branch**: `audit/anti-hallucination`
**Scope**: Solo lectura. Cero modificaciones al código.
**Objetivo**: Mapear todos los paths donde el bot puede mencionar precios, clasificar riesgos, y proveer un plan de fix accionable.

---

## Resumen ejecutivo

Se encontraron **3 riesgos críticos** y **3 importantes** en el manejo de precios del bot.

El path determinístico (quote builder de ferretería) está bien protegido: los precios siempre provienen del catálogo, y cuando no hay precio, se muestra "precio a confirmar". Sin embargo, existen dos paths críticos sin protección:

1. **`flow_manager._build_offer_options()`** construye precios inventados (90% y 105% del presupuesto declarado por el cliente), no del catálogo. Estos aparecen en respuestas al cliente cuando el sistema no puede clasificar bien el intent.
2. **El path LLM free-text** no tiene validación post-respuesta que verifique que los precios mencionados sean reales del catálogo.

**Recomendación**: Resolver R1 (flow_manager) primero, ya que es totalmente determinístico y no requiere llamadas LLM para arreglar. Luego R2 (post-response guard). El resto puede ir en una segunda sesión.

---

## 1. Mapa de paths de precio

### Origen → Destino (flujo completo)

```
CSV (config/catalog.csv)
  └─→ Database.load_catalog()
        └─→ stock table: price_ars INTEGER (NULL → 0)
              │
              ├─→ PATH A: Quote Builder Determinístico (ferreteria_quote.py)
              │     buscar_stock() → scored matches → best_product
              │     → _compute_subtotal() → _parse_price(product["price_ars"])
              │     → _format_price(value) → "precio a confirmar" si value=None
              │     → generate_quote_response() → texto al cliente
              │     STATUS: ✅ SEGURO (100% catálogo, sin LLM en el path de precio)
              │
              ├─→ PATH B: LLM con Function Calling (_chat_with_functions)
              │     LLM decide llamar buscar_stock(modelo) → _execute_function()
              │     → _slim_function_result() mantiene price_ars + price_formatted
              │     → resultado en contexto → LLM genera respuesta libre
              │     STATUS: ⚠️ PROTECCIÓN PARCIAL
              │     (prompt prohíbe inventar, pero sin validación post-respuesta)
              │
              ├─→ PATH C: flow_manager._build_offer_options()
              │     user_message con budget → entities["budget_value"]
              │     → offer_a_price = f"USD {int(budget_value * 0.9)}"
              │     → offer_b_price = f"USD {int(budget_value * 1.05)}"
              │     → reply_text incluye precio → cliente
              │     STATUS: 🔴 CRÍTICO (precio 100% inventado, nunca del catálogo)
              │
              └─→ PATH D: Cross-sell/Upsell en confirmar_venta()
                    obtener_cross_sell_offer() → DB real → format_money_ars()
                    → mensaje hardcoded con precio real del catálogo
                    STATUS: ✅ SEGURO
```

### Archivos involucrados por path

| Path | Archivos clave |
|------|---------------|
| A — Quote builder | `bot_sales/ferreteria_quote.py` (L1051-L1078, L1207-L1290) |
| B — LLM free-text | `bot_sales/bot.py` (L1824-L1892), `bot_sales/data/prompts/template_v2.j2` |
| C — flow_manager | `bot_sales/planning/flow_manager.py` (L474-L506, L412-L415) |
| D — Cross-sell | `bot_sales/core/business_logic.py` (L450-L532, L389) |

---

## 2. Riesgos identificados

### 🔴 CRÍTICOS

| ID | Archivo:línea | Descripción | Impacto | Fix sugerido |
|----|--------------|-------------|---------|--------------|
| R1 | `flow_manager.py:486-487` | `offer_a_price = f"USD {int(budget_value * 0.9)}"` — precio construido del budget del usuario, nunca del catálogo. Además usa "USD" en vez de "ARS". | Cliente recibe precio inventado y en moneda equivocada. Ocurre cuando TurnInterpreter es low-confidence y el usuario menciona un presupuesto. | Eliminar `price` de `_build_offer_options()` o consultar catálogo antes. El `reply_text` (L415) incorpora este precio directamente. |
| R2 | `bot.py:1824-1892` (`_chat_with_functions`) | El LLM genera respuesta libre sin validación post-respuesta de precios. Prompt dice "NUNCA inventes precios" pero no hay código que lo verifique. | LLM puede hallucinar precio post `no_match` ("algo similar costaría ~$X") o re-usar precio de memoria en `quote_modify`. | Agregar regex extractor de precios en la respuesta; comparar contra lista de precios del último `buscar_stock` call en el turno. |
| R3 | `bot.py:873`, `ferreteria_quote.py:832-883` | Precios en `active_quote` (session) nunca se re-validan contra catálogo en turnos subsiguientes. `unit_price` y `subtotal` almacenados son estáticos. | En multiturno largo o con precios que cambiaron, el cliente ve un precio obsoleto sin advertencia. | Re-consultar `buscar_stock` para cada item resuelto antes de mostrar el quote, o marcar la fecha de resolución y avisar si es antigua. |

### 🟠 IMPORTANTES

| ID | Archivo:línea | Descripción | Impacto | Fix sugerido |
|----|--------------|-------------|---------|--------------|
| R4 | `database.py:287` + `ferreteria_quote.py:1051-1058` | `price_ars = row["price_ars"] or 0` convierte NULL a 0. Luego `_parse_price(0)` → retorna `0.0`, y `_format_price(0.0)` → `"$0"`. Contrario a `format_money_ars(0)` → `"A confirmar"`. | Producto sin precio en DB aparece como "$0" en el quote builder, lo que es un precio incorrecto visible al cliente. | En `_parse_price()`, retornar `None` si `val == 0` (igual que si no hay valor). Alinear comportamiento con `format_money_ars`. |
| R5 | `bot.py:1856-1868` | Cada resultado de función con `price_ars`/`price_formatted` se acumula en `self.contexts[session_id]`. En `quote_modify`, el LLM tiene acceso a precios de turnos anteriores y puede re-usarlos sin re-llamar `buscar_stock`. | Precio obsoleto puede aparecer en respuesta de `quote_modify` sin nueva consulta al catálogo. | Inyectar instrucción en contexto: "Los precios solo son válidos si vienen del resultado de buscar_stock de ESTE turno. No uses precios de mensajes anteriores." |
| R6 | `business_logic.py:127-132` | Cuando `no_stock`, `buscar_stock()` retorna `products: matches` (sin formato, sin `price_formatted`, con `price_ars: 0` para productos sin precio). El LLM ve estos datos crudos. | LLM podría decir "Ese producto está sin stock, precio base $0" o interpretar precio=0 como gratuito. | En el path `no_stock`, no incluir los productos en `products` (o limpiar el campo `price_ars` si es 0). |

### 🟡 MENORES

| ID | Archivo:línea | Descripción | Impacto |
|----|--------------|-------------|---------|
| R7 | `ferreteria_quote.py:1241-1250` | Precio de alternativa se muestra para items ambiguos: `alt_price = _parse_price(alt)`. Son precios de catálogo PERO para un producto distinto al pedido, sin disclaimer claro. | Cliente puede creer que el precio de la alternativa corresponde a lo que pedió. |
| R8 | `policies.md:14` | La política dice "Los precios publicados son finales en pesos argentinos" pero no hay instrucción explícita para escalar si no se conoce el precio. Solo el prompt habla de no inventar. | Si el prompt no funciona, no hay segunda línea de defensa a nivel política. |

---

## 3. Cobertura actual de protecciones

### ✅ Bien protegido

- **Prompt template_v2.j2 (L10)**: Regla absoluta #1: "NUNCA inventes productos, precios, stock, marcas ni especificaciones."
- **Prompt template_v2.j2 (L62)**: "NUNCA presentés precios de un producto distinto al pedido sin aclarar primero que no tenés el original."
- **Prompt template_v2.j2 (L9, L27)**: Si `no_match` → "No tenemos [X] en catálogo." antes de ofrecer alternativas.
- **Search validator (L1-L2 en bot.py:_execute_function)**: Valida specs imposibles antes y después del catálogo (L1: antes de búsqueda, L2: valida match devuelto).
- **`_format_price(None)` → "precio a confirmar"**: Path determinístico siempre muestra fallback si no hay precio.
- **`format_money_ars(0)` → "A confirmar"**: En path de `buscar_stock`, precio 0 se formatea correctamente.
- **`_score_product` + `_SCORE_LOW` threshold**: Filtra matches de baja relevancia que podrían traer precios incorrectos.
- **`PolicyService` system prompt (policy_service.py:24)**: "Nunca inventes precios, stock, medidas, plazos ni condiciones."
- **`DynamicPrompts.BASE_IDENTITY` (planning/prompts.py:10)**: "No inventes stock. No inventes precios."
- **`pending_guard.sanitize_response()`**: Bloquea respuestas con `[PENDIENTE]` como fallback de respuestas incompletas.

### ⚠️ Protección parcial

- **LLM free-text**: Prompt instruye no inventar, pero no hay validación programática post-respuesta.
- **Multiturno quote display**: Precios almacenados son del catálogo al momento de resolución, pero no se re-validan en turnos posteriores.
- **no_stock path**: `buscar_stock` devuelve productos crudos (sin price_formatted) que el LLM ve.

### ❌ Sin protección

- **`flow_manager._build_offer_options()`**: Genera precios completamente fuera del catálogo. Cero validación.
- **Validación post-respuesta de precios**: No existe ningún código que extraiga precios del texto final del bot y los compare contra el catálogo.
- **Precios en `active_quote` no expiran**: No hay TTL ni re-validación para precios guardados en sesión.

---

## 4. Tests existentes

### Tests de anti-alucinación existentes

| Test | Archivo | Qué cubre | Estado |
|------|---------|-----------|--------|
| `case_18_anti_aluc_canos_ppr` | `scripts/demo_test_suite.py:508` | Caños PP-R → no inventar precios | Cubre R2 (LLM path) |
| `case_19_anti_aluc_producto_absurdo` | `scripts/demo_test_suite.py:530` | Martillo Stanley dorado 500kg → no inventar | Cubre R2 (LLM path) |
| `case_20_anti_aluc_sku_falso` | `scripts/demo_test_suite.py:551` | SKU "AAAAA" → no inventar | Cubre R2 (LLM path) |
| `case_21_regresion_precio_mecha` | `scripts/demo_test_suite.py:574` | 10 mechas 8mm → precio razonable (no $400k+) | Cubre R4 / matcher |
| `test_prev_referential_price_not_shown_as_committed` | `tests/test_ferreteria_setup.py:532` | Items ambiguos no muestran subtotal comprometido | Cubre R3 parcialmente |
| `test_open_quote_price_objection_stays_consultative` | `tests/test_ferreteria_setup.py:144` | Objeción de precio no da precio inventado | Cubre R2 parcialmente |
| `TestPriceValidation` | `tests/test_validators.py:148` | Validación de rangos de precio en DB | No cubre hallucination |

### Gaps detectados (tests que NO existen y deberían estar)

1. **Test para `flow_manager` con budget → sin precios inventados**: No existe ningún test que verifique que si el usuario dice "tengo $50.000", el bot no responda con precios calculados como "USD 45.000".

2. **Test multiturno: precio stale en active_quote**: No existe test que verifique que en turno 3 de una conversación, el precio mostrado coincide con el catálogo actual (o es marcado como referencial).

3. **Test post-response price validation**: No existe test que extraiga precios del texto del bot y los compare contra `buscar_stock()` para el mismo query.

4. **Test para `price_ars=0` en quote builder**: No existe test que verifique que un producto con price_ars=0 muestra "precio a confirmar" y no "$0".

5. **Test para `no_stock` con precio=0 en contexto LLM**: No existe test que verifique que el LLM no menciona "$0" cuando ve un producto no_stock.

---

## 5. Resultado de pruebas empíricas (Phase 3)

Ejecución sobre catálogo real (63,360 rows). Se testea directamente `BusinessLogic.buscar_stock()` (sin LLM):

```
✅ [absurdo total] Query: 'tornillo galactico de plutonio'
   status=no_match | validator_blocked=False | filtered_by_scoring=False
   → CORRECTO: no devolvió productos, ni precios.

✅ [marca+especif inventada] Query: 'destornillador de mango azul Bosch modelo X99'
   status=no_match | validator_blocked=False | filtered_by_scoring=False
   → CORRECTO: query demasiado específica sin match real.

✅ [especif imposible] Query: 'taladro con pantalla LCD y WiFi'
   status=no_match | validator_blocked=False | filtered_by_scoring=False
   → CORRECTO: sin matches.

⚠️  [producto no en catalogo] Query: 'cano PP-R termofusion 20mm'
   status=no_stock | validator_blocked=False | filtered_by_scoring=False
   → Productos devueltos: 'Tapa Termofusion 20 mm' ARS $0 | 'Tapa Termofusion 25 mm' ARS $0
   → PARCIAL: encontró productos de termofusión (no caños PP-R sino tapas), con price_ars=0.
     El LLM verá estos con price_ars=0 en el contexto. Status es no_stock, lo cual es correcto.
     Riesgo: LLM podría mencionar "$0" o confundir "tapa" con "caño".
     (Ilustra R6 y R4)

✅ [peso imposible] Query: 'martillo Stanley dorado 500kg'
   status=no_match | validator_blocked=True | filtered_by_scoring=False
   → CORRECTO: bloqueado por search validator L1 (specs imposibles).
```

**Conclusión empírica**: El path de `buscar_stock()` resiste bien las queries inventadas. El punto débil comprobado es el caso PP-R: el catálogo tiene productos de termofusión con `price_ars=0` que se entregan al LLM como `no_stock`. La protección depende 100% de que el LLM respete el prompt.

---

## 6. Recomendaciones para fix (priorizadas)

### Prioridad 1 — R1: Eliminar precios inventados en `flow_manager`

**Ubicación**: `bot_sales/planning/flow_manager.py:486-487` + `L529-530`

**Problema**: `offer_a_price = f"USD {int(budget_value * 0.9)}"` — precio fuera del catálogo, moneda incorrecta.

**Fix sugerido** (mínimo, sin romper estructura):
```python
# ANTES (L486-487):
offer_a_price = f"USD {int(budget_value * 0.9)}" if budget_value else None
offer_b_price = f"USD {int(budget_value * 1.05)}" if budget_value else None

# DESPUÉS:
offer_a_price = None  # precio siempre se obtiene del catálogo, no del budget del cliente
offer_b_price = None
```

Y en `_recommendation_line` (L529-530): el bloque `if offer_a.price: line += f" ({offer_a.price})"` ya no ejecutaría porque `price` sería `None`.

**Estimación**: 3 líneas de código. Bajo riesgo.

---

### Prioridad 2 — R2: Post-response price validation guard

**Ubicación**: `bot_sales/bot.py` — en `_chat_with_functions()` (L1874-1888) o en `_append_assistant_turn()` (L365-378)

**Problema**: El LLM puede mencionar precios que no provienen del catálogo.

**Fix sugerido**: Al finalizar `_chat_with_functions()`, antes de retornar, extraer precios del texto de respuesta y validar que cada precio exista en los productos devueltos en el turno actual. Si se detecta precio no encontrado en catálogo → escalar o reemplazar con "precio a confirmar".

```python
# Pseudo-código del guard:
def _validate_response_prices(self, response_text: str, session_id: str) -> str:
    """Extrae precios del texto de respuesta; verifica contra catálogo del turno."""
    # 1. Extraer todos los precios del texto ($X.XXX)
    # 2. Obtener precios válidos del último buscar_stock result en contexto
    # 3. Si algún precio del texto no está en catálogo → trigger escalation o replace
    ...
```

**Estimación**: ~50 líneas. Requiere regex extractor (ya existe en `demo_test_suite.py:75-83`). Riesgo medio (puede generar falsos positivos si el regex no es preciso).

---

### Prioridad 3 — R4: Alinear `_parse_price(0)` con `format_money_ars(0)`

**Ubicación**: `bot_sales/ferreteria_quote.py:1051-1058`

**Problema**: `_parse_price()` retorna `0.0` para price_ars=0, causando que `_format_price(0.0)` muestre "$0".

**Fix sugerido**:
```python
def _parse_price(product: Dict[str, Any]) -> Optional[float]:
    for field in ("price_ars", "price", "precio"):
        val = product.get(field)
        if val is not None:
            try:
                parsed = float(str(val).replace("$", "").replace(".", "").replace(",", ".").strip())
                if parsed <= 0:   # ← AGREGAR: tratar 0 como sin precio
                    return None
                return parsed
            except (ValueError, TypeError):
                pass
    return None
```

**Estimación**: 2 líneas. Bajo riesgo.

---

### Prioridad 4 — R3/R5: Stale price guard en multiturno

**Ubicación**: `bot_sales/bot.py` — `_try_ferreteria_pre_route()` donde se recarga `active_quote`

**Fix sugerido**: Agregar timestamp al `unit_price` al resolver; antes de mostrar, verificar si el precio tiene más de N minutos y agregarlo como referencial/a confirmar.

**Estimación**: ~20 líneas. Riesgo bajo.

---

### Prioridad 5 — R6: No exponer price_ars=0 en no_stock response

**Ubicación**: `bot_sales/core/business_logic.py:127-132`

**Fix sugerido**: En el path `no_stock`, filtrar o limpiar `price_ars=0` en los productos devueltos.

**Estimación**: 3 líneas. Bajo riesgo.

---

## 7. Plan de tests adicionales recomendados

```python
# test_anti_hallucination_prices.py

def test_flow_manager_with_budget_no_invented_price():
    """Si el usuario menciona budget, el bot no responde con precio calculado del budget."""
    bot = build_ferreteria_bot(tmp_path)
    r = bot.process_message("sid", "Tengo hasta $50.000 para comprar herramientas de plomería")
    prices = _extract_prices(r)
    # 45000 = 50000 * 0.9 (el precio inventado), 52500 = 50000 * 1.05
    assert 45000 not in prices, "Bot calculó precio como 90% del budget (no del catálogo)"
    assert 52500 not in prices, "Bot calculó precio como 105% del budget (no del catálogo)"

def test_zero_price_product_shows_confirmar_not_zero():
    """Producto con price_ars=0 en DB muestra 'precio a confirmar', no '$0'."""
    # Insertar producto con precio 0 en DB de test
    # Verificar que _parse_price retorna None y el quote muestra "precio a confirmar"
    ...

def test_multiturno_price_not_from_previous_context():
    """En turno 3, el precio mencionado por el bot debe coincidir con buscar_stock(),
    no con precios en el contexto de turnos anteriores."""
    bot = build_ferreteria_bot(tmp_path)
    r1 = bot.process_message("sid", "silicona blanca")   # buscar_stock → $X
    r2 = bot.process_message("sid", "para baño, exterior")  # clarificación
    r3 = bot.process_message("sid", "cuánto me sale la silicona?")
    prices_r3 = _extract_prices(r3)
    # Verificar que prices_r3 coincide con el precio real del catálogo
    # y no es un precio inventado o calculado
    ...

def test_no_match_response_has_no_invented_price():
    """Después de no_match, el bot no menciona precios estimados."""
    bot = build_ferreteria_bot(tmp_path)
    r = bot.process_message("sid", "quiero caños PP-R termofusion 20mm")
    prices = _extract_prices(r)
    rl = r.lower()
    if "pp-r" in rl or "termofusi" in rl:
        assert not prices, f"Bot mencionó precios para caños PP-R: {prices}"

def test_no_stock_price_zero_not_shown():
    """Producto no_stock con price_ars=0 no se muestra como precio válido."""
    # Setup: producto en DB con stock=0, price_ars=0
    # Verificar que el LLM no menciona "$0" en la respuesta
    ...
```

---

## Appendix A: Activación del flow_manager en ferretería

El `SalesFlowManager` se inicializa siempre (`bot.py:182`). Se activa en `process_message()` cuando:
1. `_try_ferreteria_intent_route()` retorna `None` (intent no manejado o low-confidence)
2. `_try_ferreteria_pre_route()` retorna `None` (no es una operación sobre la quote)
3. `_should_bypass_sales_intelligence()` retorna `False`

Escenarios típicos donde **flow_manager se activa**:
- "Tengo $50.000, qué me recomendás?" (TurnInterpreter: low confidence)
- "Algo con buena relación precio/calidad" (vago, sin producto específico)
- "Dame opciones" (sin contexto suficiente)

En estos casos, si el usuario mencionó un monto, `budget_value` se extrae y el precio inventado aparece.

---

## Appendix B: Archivos auditados (solo lectura)

| Archivo | Auditado |
|---------|----------|
| `bot_sales/bot.py` | ✅ |
| `bot_sales/core/business_logic.py` | ✅ |
| `bot_sales/core/database.py` | ✅ |
| `bot_sales/ferreteria_quote.py` | ✅ |
| `bot_sales/data/prompts/template_v2.j2` | ✅ |
| `bot_sales/planning/flow_manager.py` | ✅ |
| `bot_sales/planning/prompts.py` | ✅ |
| `bot_sales/services/pending_guard.py` | ✅ |
| `bot_sales/services/policy_service.py` | ✅ |
| `bot_sales/services/catalog_search_service.py` | ✅ |
| `bot_sales/connectors/storefront_api.py` | ✅ |
| `bot_sales/persistence/quote_store.py` | ✅ |
| `data/tenants/ferreteria/policies.md` | ✅ |
| `data/tenants/ferreteria/profile.yaml` | via estructura |
| `tests/test_ferreteria_setup.py` | ✅ |
| `tests/test_validators.py` | ✅ |
| `scripts/demo_test_suite.py` | ✅ |

**Cero modificaciones realizadas a ningún archivo de código.**

---

*Generado: 2026-05-04 | Branch: audit/anti-hallucination | Por: Claude Sonnet 4.6*
