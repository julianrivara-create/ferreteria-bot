# PENDIENTES — follow-up items

## Cerrado hoy (2026-05-06)

### B23-FU ✅ (commit e79de10, 2026-05-05)
S08 WARN→PASS. Ver commit para detalle.

### Bloque U ✅ (merge da5ea28)
UX: eliminado markdown bold, emojis, hardcoded phrases, header cleanup.

### Bloque F4 + D5 ✅ (merge d62314a)
apply_clarification fixes + fix crítico sandbox: `_load_active_quote_from_store`
clobberaba el state en modo sandbox. Guard: `if not self.quote_service or self.sandbox_mode: return`.

### Bloque F1 ✅ (merge 8098c10)
Compound clarif + additive en single turn ("la opcion a. te pido también un martillo").
Guard en section 3.5 post-apply_followup. Usa detect_option_selection para option letters,
apply_clarification para dimension clarifs.

### Bloque L1 ✅ (merge post-F1)
Normalizer de listas con bullets/guiones antes del parser multi-item.
`_is_structured_list` + `_normalize_list_to_items` con fallback seguro.

### Bloque L2 ✅ (merge post-L1)
TurnInterpreter extendido con campo `items[]` para listados de productos.
Gate: solo en product_search sin carrito activo. L1 sigue como fallback.
Smoke test final: lista de obra 7/7 items procesados correctamente.

### Bloque D1 ✅ (merge post-L2)
Dashboard training: white-space pre-wrap en burbujas + evento paste en textarea.
Archivos: app/ui/templates/ferreteria_training/base.html:286,
          app/ui/templates/ferreteria_training/sandbox.html:324

---

## Deudas técnicas — priorizadas

### 🔴 Alta prioridad

**DT-01 — L2 pierde contexto de material en normalización**
Cuando el cliente dice "3 mechas 6mm para hormigon", L2 normaliza a
"3 mechas 6mm" soltando el "para hormigon". El bot pregunta el material
de vuelta. Fix: mejorar el prompt de _normalize_list_to_items para
preservar especificaciones de material/uso.

**DT-02 — Preguntas no transaccionales rompen el state machine**
"cuál es la diferencia entre la A y la B?" → bot responde con
"¿Eso es para X o para Y?" mezclando queries previas.
El bot debería detectar que es una pregunta de info y responder
en base a los productos ya ofrecidos.

### 🟡 Media prioridad

**DT-03 — apply_additive auto-pickea primer match**
Cuando el cliente dice "te pido también un martillo" sin specs,
el bot autopickea el primero del catálogo en vez de ofrecer A/B/C.
Inconsistente con el comportamiento de T1 (que sí ofrece opciones).
Fix: paridad entre apply_additive y el resolver inicial.

**DT-04 — Catálogo gap: mechas y otros productos básicos**
"mecha 6mm", "mecha 8mm para metal", "cinta de carrocero" no se
encuentran. Verificar si son gaps del catálogo real o del matcher.
Involucrar al cuñado para auditar el catálogo con los productos
más pedidos en la ferretería.

**DT-05 — Bug _QTY_RE con "un X" donde X empieza con "m"**
"un martillo" parsea como qty="un" unit="m" rest="artillo".
Workaround activo en F1 (prepend "también"). Bug raíz en el regex
_QTY_RE. Afecta: un metro, un mango, un molde, etc.

**DT-06 — Negación y filtros no soportados**
"no quiero Bahco", "menos de $10000", "mostrame los nacionales"
se ignoran completamente. El bot muestra todo el catálogo igual.
Feature missing, no bug. Requiere diseño de cómo el matcher
aplica filtros negativos/de precio/de origen.

### 🟢 Baja prioridad

**DT-07 — "Con el A" masculino no matchea D3**
Regex D3 cubre "con la A/B/C" (femenino) pero no "con el A" (masculino).
Trivial de extender.

**DT-08 — Render qty=1 redundante**
"1 × X — $Y/u → $Y" muestra unit price = total cuando qty=1.
Cosmético: omitir "/u → $Y" cuando qty=1.

**DT-09 — Re-validar bugs diagnosticados antes de D5**
Algunos bugs reportados via dashboard antes del fix D5 pueden ser
artefactos del sandbox (state se reseteaba). Re-testear con el
path de producción.

**DT-10 — Diferencia path Python directo vs dashboard**
En algunos casos el agente veía resultado distinto via get_runtime_bot
vs el dashboard real. Investigar si hay post-processing diferente
entre los dos paths.

**DT-11 — Preguntas operativas ignoradas silenciosamente**
Cuando el cliente mezcla una pregunta de logística con un pedido
("necesito esto... también saben si hacen envío?"), el bot procesa
los productos e ignora la pregunta sin acuse de recibo.
El cliente queda sin respuesta sobre algo que preguntó.
Fix: detectar preguntas operativas (envío, retiro, pago, horario,
stock) y responder con texto fijo + derivar al equipo, antes o
después de mostrar el presupuesto.

---

## Dashboard — próximos bloques

**D2 — AJAX + panel debug toggle + sesiones con nombre (3-4h)**
- AJAX para enviar mensajes sin reload de página
- Panel debug con toggle (Julian): muestra intent TI, quote_state,
  items parseados, path, tokens, costo por mensaje
- Sesiones recientes con preview del primer mensaje + timestamp

**D3 — (no tocar por ahora)**
Formulario de revisión con taxonomía pedido por el cuñado.
No modificar hasta nueva instrucción.

---

## Plan mañana

1. **DT-01** (L2 pierde material) — fix en prompt de _normalize_list_to_items.
   Quick win, 30-60 min.

2. **DT-04** (catálogo gap) — auditoría con el cuñado.
   Sin esto los tests de mechas siempre van a fallar.

3. **DT-02** (preguntas no transaccionales) — requiere diseño.
   Definir: ¿el bot responde con info de los productos ya ofrecidos,
   o deriva a humano, o ignora y repregunta?

4. **D2** (dashboard AJAX + debug) — arrancar si hay tiempo.
