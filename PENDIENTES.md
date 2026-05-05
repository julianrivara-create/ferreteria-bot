# PENDIENTES — follow-up items

**Última actualización:** 2026-05-05
**Estado del bot:** main @ 0ed22a5 (refactor LLM-first 7/7 cerrado)
**Producción:** NO en Railway todavía
**Suite C strict:** 8P/2W/0F estable × 3 corridas
**Fast tests:** 237 PASS (1 pre-existing `test_routing_success`)

---

## 🔴 BUGS DETECTADOS EN TESTING MANUAL (post-refactor)

### Bug 1 — Compound modify+accept se pierde (CRÍTICO)

**Estado:** diagnosticado, plan listo
**Prioridad:** alta — rompe flujo principal de cierre de venta

**Reproducción:**
```
T1: "necesito destornillador philips"        → bot ofrece A/B/C
T2: "la opcion a. Te pido también martillo"  → resuelve + agrega ✓
T3: "la opcion 2 del martillo. cuanto es el total?" → ❌ pierde
T4: "hoy te lo retiro por el local"          → ❌ loop pidiendo datos
```

**Causa probable:** post-T2 el bot queda en `awaiting_customer_confirmation`
y desde ahí todo se procesa como respuesta a esa confirmación, no como
nueva instrucción de modificación/consulta.

**Plan:** B22c-medio (compound modify + accept). Extender handler de
`_process_compound_mixed` para aceptar sub_commands con intents distintos
cuando el global es `quote_modify`. ~1-2h.

---

### Bug 2 — Templates de respuesta muy robóticos

**Estado:** diagnosticado, plan claro
**Prioridad:** alta — UX crítica para WhatsApp

**Reproducción:** cualquier respuesta con producto resuelto + adicionales:
```
**1. Destornillador:**
- **SKU:** PPT1999M10
- **Modelo:** ...
- **Precio:** $6.552
```
En WhatsApp el markdown no renderiza → se ve horrible. No es lenguaje de venta.

**Plan:** refactor de templates en `bot_sales/templates/quote_response.j2`
y/o donde corresponda. Eliminar markdown bullets, formato natural tipo:
"Te dejé el destornillador X a $Y. Para el martillo te tiro 3 opciones:
A) ... B) ... C) ...". ~1h.

---

### Bug 3 — Frases hardcoded de cierre fuera de contexto

**Estado:** diagnosticado, rastreo pendiente
**Prioridad:** media

**Reproducción:** cuando el bot no sabe qué hacer, dispara:
```
"Para cotizarte exacto y avanzar hoy:
 ¿Lo necesitás hoy, esta semana o este mes?
 ¿Pagás por efectivo, transferencia, tarjeta o pasarela digital?"
```

**Causa:** template hardcoded en algún path de cierre/escalación que
se dispara fuera de contexto.

**Plan:** `grep "Para cotizarte exacto"` en el repo, identificar el path,
contextualizar o eliminar. ~30 min.

---

### Bug 4 — apply_clarification no resuelve ítem pendiente

**Estado:** diagnosticado, plan medio
**Prioridad:** media

**Reproducción:**
```
T1: "5 mechas 8mm Bosch?"     → bot pregunta material
T2: "Para madera, por favor"  → ❌ devuelve "Trampa laucha madera"
```

**Causa:** "Para madera" se interpreta como nueva búsqueda en lugar de
respuesta a la clarification del ítem ambiguo abierto.

**Plan:** en `apply_clarification`, cuando hay ítem ambiguo pendiente Y
el mensaje es corto + descriptivo (sin verbo de acción), priorizar
resolución del pendiente sobre nueva búsqueda. ~1-2h.

---

### Bug 5 — UX general muy "asistente IA", poco humano

**Estado:** observación, plan amplio
**Prioridad:** baja

**Causa:** respuestas con emoticones 🛠️, frases largas, formalidad
excesiva. No suena a vendedor de ferretería argentino.

**Plan:** pasada general por templates, sacar emojis, acortar frases,
tono más coloquial argentino. ~2-3h.

---

## ✅ CERRADO EN SESIÓN 2026-05-05 — Refactor LLM-first 7/7

main @ 0ed22a5 · ~1.500 LOC eliminadas · 5 validators fuera · IntentRouter eliminado

### S1 — Suite strict consolidada ✅
Commit 8aa7e7f. 84 casos → 10 casos estrictos. Baseline: 8P/2W/0F.
`scripts/demo_test_suite.py` (StrictRegressionSuite). `demo_test_suite_extended.py` eliminado.

### B24 — IntentRouter eliminado + safety net ✅
Commit 4aeb7d5. `intent_router.py` eliminado. Safety net en `bot.py`:
`_looks_like_escalation_request()` — activa solo cuando `intent=="unknown" AND confidence==0.0`.

### B21 — TurnInterpreter LLM-first ✅
Commit d8bf819. Schema: `compound_message`, `escalation_reason`, `referenced_offer_index`.
V8 (negociación) y V9 (ambigüedad en idle) migrados al prompt del TI.
EscalationHandler lee `interpretation.escalation_reason`.

### B23 — Limpieza pre-route heurística ✅
Commit a595caf. -335 LOC netas. 8 métodos eliminados de `bot.py`.
`looks_like_clarification` eliminado. Guards migrados a señales del TI.

### B25 — Eliminación validators V4-V9 ✅
Validators V4/V5/V7/V8/V9 eliminados. V6 (spec blocker) conservado.
Routing simplificado a TI intent puro.

### B22a — Compound modify handler ✅
Commit 76b4731. `TurnInterpretation.sub_commands: List[str]`. `_process_compound_modify()`.
Bonus: S09 (parser bug pre-existente) resuelto.

### B22b — Compound modify con qty propagation ✅
Commit 670a1ee. `_ADDITIVE_RE` + `sumame/súmame/sumar`. `_extract_qty_from_phrase()`.
Qty propagada al ítem resuelto en option selection.
Gap conocido: `"poneme X"` sin ordinal no es additive (B22c/futuro).

### B22c-min — Compound accept + customer_info ✅
Commit b4ef041. `looks_like_customer_info()`. `_process_compound_mixed()`.
Ejemplo: `"me llevo todo y mandalo a Quilmes"` → cierre + zona guardada en sess.
`customer_delivery_info.raw` en sess (no viaja a quote_store — pendiente follow-up).

### B23-FU — Selección genérica "cualquiera está bien" ✅
Commit e79de10. S08 WARN→PASS.
1. `detect_option_selection`: frases genéricas → index 0
2. `apply_followup_to_open_quote`: gate para 1 item pendiente
3. `classify_followup_message`: strip punctuation en `_FRESH_REQUEST_WORDS`
