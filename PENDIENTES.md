# PENDIENTES — follow-up items

## Cerrado hoy (2026-05-11) — Fase 2 audit cleanup

Cerramos los bugs latentes catalogados como B.1–B.11 a partir del
`reports/audit_total_2026-05-09.md`. Trabajo sobre `main`, un commit
por bug, con tests adicionales donde correspondió.

### Commits

| Bug | SHA | Resumen |
|-----|-----|---------|
| B.3 | `70ff78d` | Remove dead English token "best" from `_REPLACE_RE`. |
| B.2 | `bd9e502` | Remove unused `tenant_manager` import from `bot_sales/bot.py`. |
| B.1 | `ec5b568` | Merge duplicate `SalesBot.close()` definitions (L215 + L2805). |
| B.4 | `fefd434` | Fix dead multi-word heuristic in `apply_clarification` + tests. |
| B.9 | `baa734f` | Acquire `_cursor_lock` around direct `db.cursor` reads in `business_logic`. |
| B.10 | `ac78b6b` | Parametrize hold duration in i18n `create_reservation` string + tests. |
| B.6 | `e76cd67` | Consolidate reset detection behind `_reset_signaled` helper + tests. |

### Resueltos sin commit

- **B.11** — `app/bot/security/sanitizer.py` era un duplicado idéntico
  de `bot_sales/security/sanitizer.py` pero estaba untracked (resucitado
  del cleanup F1B `5d0c575`). Se eliminó del filesystem; no hubo commit
  porque no estaba versionado. `bot_sales/security/sanitizer.py`
  permanece (usado por `tests/test_sanitizer.py`).

### Falsos positivos del audit (NO se aplicó fix)

- **B.5 — AcceptanceDetector "huérfano"**: en realidad tiene un caller
  vivo. `bot_sales/ferreteria_quote.py:1209` lo importa lazy desde
  `looks_like_acceptance(message, chatgpt_client=...)`, que se llama
  desde `bot.py:932` con `chatgpt_client=self.chatgpt`. Eliminarlo
  rompería el camino LLM de detección de aceptación. Worktree
  `../ferreteria-B5` rama `fix/B5-acceptance-detector` queda creado
  vacío por si más adelante se decide revisar.
- **B.7 — `ready_for_followup` "nunca producido"**: es un gate
  human-in-the-loop intencional. El status se setea manualmente desde
  la UI admin (`app/api/ferreteria_admin_routes.py`,
  `app/ui/templates/ferreteria_admin/quote_detail.html`) antes del
  auto-followup. `derive_quote_status()` no lo emite a propósito —
  cambiar el filtro de `list_eligible_quotes` desactivaría la
  revisión humana previa.

### Saltado a pedido

- **B.8 — handler de intent `customer_info`**: TurnInterpreter ya
  clasifica el intent (`turn_interpreter.py:23,214,249`) pero
  `_try_ferreteria_intent_route` no tiene branch dedicado para
  persistir `entities.contact/name/company` en `customer_profile`.
  Queda pendiente como **DT-21 — customer_info handler**.

### Cleanup adicional realizado

- `rm` de los 6 archivos untracked autorizados en `app/bot/`:
  `analytics.py`, `analytics_engine.py`, `bot_gemini.py`, `bundles.py`,
  `connectors/cli_gemini.py`, `security/sanitizer.py`. Todos eran
  resucitados del commit F1B `5d0c575`.

### Cleanup completo (2026-05-11, tarde)

Eliminados 41 archivos untracked adicionales con el mismo patrón
(permisos `-rw-------` + mtimes viejas + presentes en `git log
--diff-filter=D` de commits `F1*`). Distribuidos por commit que
los eliminó originalmente:

- `5d0c575` (F1B `app/bot/ legacy`): 6 archivos.
- `fc5c6f6` (F1A `Slack duplicate stack + integrations orphans`):
  18 archivos.
- `bd66fa6` (F1E `miscellaneous orphans`): 3 archivos.
- `7c527d8` (F1C `bot_sales/core/ orphans + obsolete tests`): 11
  archivos.
- `440b099` (F1D `intelligence + security orphan modules`): 3
  archivos.

Total Fase 2 + post-Fase 2: **47 archivos resucitados borrados**
(6 dentro del cierre B.1–B.11 + 41 en este pasaje). `git status`
queda limpio. No hubo commit por el `rm` (eran untracked, no
había nada que versionar).

### Worktrees preparados (sin commits)

- `../ferreteria-B5` rama `fix/B5-acceptance-detector` (base
  `0508891`).
- `../ferreteria-B9` rama `fix/B9-cursor-lock` (base `ec5b568`).

### Seguridad

- **Token de GitHub rotado** el 2026-05-11. PAT viejo
  (`ghp_lSFRYZQ3fcww…`) revocado en `github.com/settings/tokens`.
  Remote `origin` reseteado a URL sin token embebido
  (`git remote set-url origin https://github.com/julianrivara-create/ferreteria-bot.git`).
  El nuevo token se guarda en macOS Keychain vía
  `git config --global credential.helper osxkeychain`.

### Estado de tests

Suite oficial (`pytest` con `testpaths = tests, bot_sales/tests`).

| | Pre-Fase 2 (`bny0xgoid`) | Post-Fase 2 + cleanup (`bpbyaejot`) | Δ |
|---|-----:|-----:|-----:|
| passed | 684 | 701 | **+17** |
| failed | 48 | 47 | **−1** |
| skipped | 26 | 26 | 0 |
| errors | 2 | 2 | 0 |
| tiempo | 19:49 | 18:46 | −63s |

- **+17 passed** = 16 tests nuevos de Fase 2 (B.4: 6, B.10: 3,
  B.6: 7) + 1 test que pasó de failing a passing.
- **0 regresiones**: ningún test que antes pasaba ahora falla.
- **Improvement**:
  `tests/test_ferreteria_setup.py::test_struct_12_accepted_quote_not_mutated_by_short_input`
  ahora pasa. La hipótesis es el fix B.6 (`_reset_signaled`):
  entradas cortas como `"ok"` después de una acceptance ya no
  caen al regex `looks_like_reset` por el camino determinístico
  legacy. Los 41 archivos borrados eran todos `.py`, ningún
  archivo de datos — la hipótesis "el bot agarraba data por
  fallback" queda descartada.

Los 47 failures restantes siguen siendo pre-existentes (causa
principal: falta `data/products.csv` → fallback al legacy
`config/catalog.csv` sin precios).

---

## DTs viejos — estado al 2026-05-11

| DT | Estado |
|----|--------|
| DT-01 | ✅ cerrado el 2026-05-07. |
| DT-02 | Abierto — requiere diseño antes de fix. |
| DT-03 | Abierto — revalidar tras DT-17. |
| DT-04 | Abierto — atado a Nacho + DT-14 (catálogo). |
| DT-05 | Abierto. |
| DT-06 | Abierto. |
| DT-07 | Abierto. |
| DT-08 | Abierto. |
| DT-09 | Abierto — auditoría tras fixes recientes. |
| DT-10 | Abierto — workaround vigente. |
| DT-11 | Abierto. |
| DT-12 | ✅ cerrado el 2026-05-07. |
| DT-13 | ✅ cerrado el 2026-05-07. |
| DT-14 | Abierto 🔴 — esperando info de catálogo de Nacho. |
| DT-15 | ✅ cerrado el 2026-05-07. |
| DT-16/16b | ✅ cerrado el 2026-05-07. |
| DT-17/17b | ✅ cerrado el 2026-05-07. |
| DT-18 | Abierto 🔴 — TI failure → SalesFlowManager. |
| DT-19 | Abierto 🟢 — pre-existente, baja prio. |
| DT-20 | Abierto 🟡 — optimización TI bypass. |
| DT-21 | Nuevo — customer_info handler (de B.8 saltado). |

---

## Próximos hitos (del audit_total_2026-05-09.md)

1. **Mié-Jue (2026-05-13/14) — sesiones con Nacho**: completar el
   cuestionario sobre catálogo y profile.yaml (19 campos `[PENDIENTE]`),
   destrabar DT-14 y DT-04.
2. **Vie (2026-05-15) — Fase 4 selectiva**:
   - DT-04 catálogo conectando `language_patterns.yaml` al CSV.
   - **DT-21 customer_info handler** (B.8 saltado en la Fase 2; queda
     para esta tanda).
3. **Semana 2 — Fase 4 resto + deuda arquitectónica**: resto de DTs
   abiertos, audit cleanup de los ~36 untracked, rotación de
   `ADMIN_PASSWORD` / `ADMIN_TOKEN` / `SECRET_KEY` pre-deploy.

---

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
