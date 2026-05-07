# PENDIENTES — follow-up items

## Cerrado hoy (2026-05-07)

### Tooling ✅
restart-dashboard.sh + post-merge hook que auto-reinicia el server tras cada merge.
Hook usa `lsof -ti :5001` para matar el proceso real (no pkill por pattern).
Server arranca con `from app.main import create_app; app.run(...)`.
Archivos: scripts/restart-dashboard.sh, scripts/git-hooks/post-merge, scripts/install-hooks.sh.

### DT-01 ✅
_normalize_list_to_items preserva specs de material/uso ("para hormigon",
"para metal", "para drywall") en cada item normalizado.
Archivo: bot_sales/bot.py.

### DT-12 ✅
"drywall: durlock" agregado a regional_terms en
data/tenants/ferreteria/knowledge/language_patterns.yaml.

### DT-13 ✅
Fuzzy matching en lookup de regional_terms con JaroWinkler.
Threshold 0.90 best / 0.85 ambiguity, min 4 chars.
Cubre typos como "drywal" → "drywall" → "durlock", "mehca" → "mecha".
Archivo: bot_sales/ferreteria_language.py. Lib: rapidfuzz.

### M0 ✅
Gmail OAuth scaffolding: app/mail/ con gmail_client.py, mail_reader.py,
types.py, __main__.py. CLI: python -m app.mail login|list-unread|show|logout.
Doc: docs/MAIL_SETUP.md (instrucciones para Nacho).
Pendiente: credentials.json del cuñado para arrancar M1.

### DT-15 ✅
Eliminado mensaje fantasma "Atención: se vende por x N" que regex inferia
del nombre del producto. El "25" del "Tornillo 3.5 x 25 mm" se reportaba
como presentación falsa. Eliminado: _PACK_RE, _detect_pack(), _pack_note().
Bonus: arregla bug que suprimía subtotal cuando había pack "detectado".

### DT-17 ✅
apply_additive incrementa qty cuando el producto ya está en el carrito,
en vez de dedup silencioso. También fix complementario en
_process_compound_modify para validar progreso real (success=True solo
si el carrito cambió).
Archivos: bot_sales/ferreteria_quote.py, bot_sales/bot.py.

### DT-17b ✅
Consolidación de líneas usa SKU/model del catálogo en lugar de frase
normalizada del usuario. Antes: "una caja de tornillos" + "5 tornillos"
creaba 2 líneas porque el normalized differia. Ahora: 1 línea con qty=6.
Archivo: bot_sales/ferreteria_quote.py.

### DT-16 ✅
Clarification de qty cuando hay palabra de presentación sin cantidad
explícita. _PRESENTATION_BLOCK_WORDS: caja, cajas, rollo, rollos, lata,
latas, bolsa, bolsas. Mensaje: "¿Cuántas unidades necesitás?".
Archivo: bot_sales/ferreteria_quote.py (resolve_quote_item + apply_clarification).

### DT-16b ✅
Fix follow-up: apply_clarification con qty_override no contamina texto
de búsqueda. Antes: "tornillos durlock" + "100" se mandaba al catálogo
como "tornillos durlock 100". Ahora: usa target.normalized original
cuando hay qty_override.

---

## Deudas técnicas — priorizadas

### 🔴 Alta prioridad

**DT-14 — Catálogo no tiene campo de presentación**
El CSV solo tiene SKU, categoría, nombre, precio, moneda, stock. Sin
"unidades por caja". Hasta resolverlo el bot tiene que preguntar qty
para "caja"/"rollo"/"lata"/"bolsa". Solución: extender schema +
auditoría con Nacho. Pendiente: respuesta de Nacho sobre si tiene
info digital de presentaciones.

**DT-18 — TI failure → fallback al SalesFlowManager legacy**
Cuando el LLM del TI falla (timeout, API down) o devuelve intent=unknown,
el bot cae al SalesFlowManager que responde "¿Me podés repetir qué
necesitás?" sin contexto. En mail autónomo es disaster. Fix sugerido:
retry con backoff, o fallback explícito que diga "tuve un problema
técnico, dame un momento".

**DT-02 — Preguntas no transaccionales rompen el state machine** (de ayer)
"cuál es la diferencia entre la A y la B?" → bot mezcla queries previas.
Requiere diseño antes de fix.

### 🟡 Media prioridad

**DT-20 — Bypass del TI para respuestas cortas en awaiting_clarification**
Cuando hay un item en awaiting_clarification, las respuestas chicas
(números, "A"/"B"/"C") tardan 4-5s en pasar por el TI. Optimización:
detectar respuesta corta + estado clarification → llamar
apply_clarification directo. Ahorra tokens y latencia.

**DT-16c — Parser no extrae qty del rest cuando hay número**
"una caja de 50 tornillos" → bot pregunta "¿cuántas unidades?" en vez
de tomar 50 directo. Mejora del parser para extraer qty del rest cuando
hay número, antes del guard de presentación.

**DT-03 — apply_additive auto-pickea primer match** (de ayer)
Re-validar tras DT-17 si sigue siendo válido o ya está cubierto.

**DT-04 — Catálogo gap: mechas y otros productos básicos** (de ayer)
"mecha 6mm", "mecha 8mm para metal", "cinta de carrocero" no se encuentran.
Atar al laburo con Nacho cuando audite catálogo (también linked a DT-14).

**DT-11 — Preguntas operativas ignoradas silenciosamente** (de ayer)
"hacen envío?" se ignora. Pendiente.

### 🟢 Baja prioridad

**DT-19 — SIGSEGV en suite full**
pysqlite_cursor_iternext crashea con Python 3.14 + ThreadPoolExecutor.
Pre-existente. Tests específicos pasan limpio. Investigar para CI futuro.

**DT-05** — Bug _QTY_RE con "un X" donde X empieza con "m" (de ayer)
**DT-06** — Negación y filtros no soportados (de ayer)
**DT-07** — "Con el A" masculino no matchea D3 (de ayer)
**DT-08** — Render qty=1 redundante (de ayer)
**DT-09** — Re-validar bugs pre-D5 — algunos pueden estar cubiertos por
los fixes de hoy (DT-12, 13, 15, 16, 17). Auditoría pendiente.
**DT-10** — Diferencia path Python directo vs dashboard. Lo seguimos
manejando con merge + smoke en dashboard.

---

## Mail — bloques planificados

**M0** ✅ scaffolding mergeado hoy.

**M1 — Parsing del mail entrante al pipeline del bot**
Bloqueado por credentials.json de Nacho. Cuando llegue:
- Conectar mail_reader al pipeline existente (TI + parser + resolver)
- Estructura del mail crudo → contexto del bot
- Polling vs push: investigar Gmail push notifications
- ~3-4h estimado

**M2 — Composer HTML profesional + sender + modo aprobación**
- HTML inline-styled (Gmail-friendly), template con header/cotización/footer
- Modo aprobación: bandeja de borradores pendientes para revisar antes de mandar
- Se manda con gmail.send (actualizar scopes en M0)
- ~4-5h estimado

**M-anexos — Lectura de PDF/Word adjuntos**
Algunos pedidos llegan como adjuntos. Extracción con pdfplumber +
python-docx. Pasar texto al pipeline existente. ~3h estimado.

**M3 — Threading básico**
Detectar replies del cliente (in_reply_to / references), agrupar por thread.
~2-3h estimado.

---

## Dashboard — bloques pendientes

**D2 — AJAX + panel debug toggle + sesiones con nombre** (de ayer)
- AJAX para enviar mensajes sin reload
- Panel debug toggle: intent TI, quote_state, items parseados, tokens, costo
- Sesiones recientes con preview + timestamp

**D3 — Formulario de revisión** (de ayer)
No tocar hasta nueva instrucción de Nacho.

---

## Plan próxima sesión

1. **Si llegó credentials.json de Nacho** → arrancar M1.
2. **Si llegó info de catálogo de Nacho** → arrancar DT-14 (extender schema).
3. **Si nada de Nacho** → DT-18 (TI failure handling) o DT-20 (bypass
   para respuestas cortas). Ambos importantes para mail autónomo.
4. Eventualmente DT-02 (preguntas no transaccionales) cuando charlemos diseño.
5. D2 (dashboard AJAX + debug) si queda tiempo.
