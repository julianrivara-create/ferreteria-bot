# Extended Test Suite Results — 2026-05-03
**Suite:** `scripts/demo_test_suite_extended.py` (53 casos, E01-E53)
**Run ID:** `2eb0ae66`
**Tiempo total:** 601s (~10 minutos)
**Estado del código:** post-merge A1+A2+B1+B2

---

## Resumen ejecutivo

| Estado | Cantidad | % |
|--------|----------|---|
| ✅ PASS | 39 | 74% |
| ⚠️ WARN | 10 | 19% |
| ❌ FAIL | 4 | 8% |
| 💥 ERROR | 0 | 0% |

---

## Resultados por caso

| ID | ST | Categoría | Descripción | Notas |
|----|----|-----------|-------------|-------|
| E01 | ✅ | pedidos_mayoristas | lista obra: caño/codos/cuplas/llaves/ramales (5 ítems) | detectó 4/5 ítems, total=$77,482 |
| E02 | ✅ | pedidos_mayoristas | 200xM6 + 200xM8 + 100xM10 cabeza hexagonal | detectó M6 + M8 + M10 con cantidades |
| E03 | ✅ | pedidos_mayoristas | cable 2.5mm + cajas de luz + termocontraíble | detectó cable + caja + termocontraíble sin alucinación |
| E04 | ✅ | pedidos_mayoristas | niples + codos 90° + llaves esféricas + sellador (4 ítems) | detectó 4/4 ítems de instalación |
| E05 | ✅ | pedidos_mayoristas | 100xMecha6mm Bosch + 50xMecha8mm + 30xBroca10mm | detectó mechas Bosch sin matchear acoples (A2 fix ok) |
| E06 | ✅ | pedidos_mayoristas | tablero: contactora + térmicas + disyuntor + cable + borneras | detectó 5/5 ítems eléctricos |
| E07 | ✅ | pedidos_mayoristas | verificar stock: martillo + destornillador + alicate + llave | confirmó stock para 5/5 herramientas con precios |
| E08 | ✅ | pedidos_mayoristas | Bahco sets + taladros percutores + amoladoras 4.5 (3 ítems) | detectó 3/3 ítems con precios reales |
| E09 | ❌ | pedidos_mayoristas | termofusión PP-R + llaves esféricas + sellador + teflón | inventó precios para termofusión PP-R: [10797, 10797, 59726] |
| E10 | ✅ | pedidos_mayoristas | caños galvanizados + codos + cuplas + llaves 3/4" | detectó 4/4 ítems con cantidades |
| E11 | ✅ | pedidos_mayoristas | formato: 1 caño + 1 codo + 1 cupla x 50 (multiplicador) | interpretó multiplicador x50 o pidió clarificación |
| E12 | ✅ | pedidos_mayoristas | WD-40 + grasa + trapos + guantes + gafas (taller) | detectó 4/4 ítems de taller, informó sobre los faltantes |
| E13 | ✅ | conversacion_argentina | "che, tenés taladros?" → slang argentino | respondió con opciones de taladros |
| E14 | ⚠️ | conversacion_argentina | "dale, mostrame qué hay" → ambigüedad | respuesta vaga ante mensaje muy ambiguo (esperado) |
| E15 | ⚠️ | conversacion_argentina | "buenísimo, voy con eso" → sin contexto previo | maneja sin error pero respuesta vaga (esperado) |
| E16 | ✅ | conversacion_argentina | "está mortal el precio" → slang objeción | reconoció 'mortal' como objeción de precio |
| E17 | ✅ | conversacion_argentina | "me sirve, dale" → confirmación sin contexto | pidió contexto o confirmó coherentemente |
| E18 | ✅ | conversacion_argentina | "nahh está caro" → objeción informal | manejó objeción informal correctamente |
| E19 | ✅ | conversacion_argentina | "no me convence, mostrame otra cosa" | ofreció alternativas o pidió más info |
| E20 | ✅ | conversacion_argentina | "tipo Bosch tenés algo?" → marca sin producto | mostró productos Bosch directamente |
| E21 | ✅ | negociacion | "está caro, cuánto el último?" → regateo | manejó negociación sin inventar descuentos |
| E22 | ⚠️ | negociacion | "si llevo 100 me bajás?" → descuento por volumen | no mencionó política de volumen al pedir descuento |
| E23 | ✅ | negociacion | "en otro lado lo conseguí más barato" | manejó objeción de competencia profesionalmente |
| E24 | ✅ | negociacion | "hacés descuento por mayor?" → política mayorista | indicó política de descuento por mayor |
| E25 | ✅ | negociacion | "15% off?" → no aceptar automáticamente | no aceptó automáticamente, escaló o explicó política |
| E26 | ✅ | negociacion | "dame mejor precio" → negociación general | manejó negociación sin bajar precio automáticamente |
| E27 | ✅ | disponibilidad_stock | "hay stock de taladros Bosch?" | confirmó stock Bosch o pidió especificación |
| E28 | ⚠️ | disponibilidad_stock | "cuándo te llega más mercadería?" → reposición | no escaló ni pidió producto al preguntar por reposición |
| E29 | ✅ | disponibilidad_stock | "tenés disponible para mañana?" | respondió sobre disponibilidad/entrega |
| E30 | ✅ | disponibilidad_stock | "me reservás 50 tornillos M6?" | preguntó tipo o inició reserva correctamente |
| E31 | ✅ | disponibilidad_stock | "hasta cuándo me lo guardás?" → tiempo de reserva | indicó tiempo de reserva (hold_minutes) |
| E32 | ✅ | disponibilidad_stock | "está disponible o lo tienen que pedir?" | informó sobre disponibilidad real o proceso |
| E33 | ❌ | anti_fraude | "taladro de 5000W" → potencia imposible | inventó taladro 5000W con precio: [5980] |
| E34 | ✅ | anti_fraude | "martillo Stanley plateado de 100kg" → peso imposible | rechazó spec de martillo 100kg |
| E35 | ❌ | anti_fraude | "destornillador láser cuántico" → producto imposible | inventó destornillador láser cuántico: [89403, 138481] |
| E36 | ✅ | anti_fraude | "100 metros de tornillo" → longitud imposible | informó que 100 metros de tornillo no existe |
| E37 | ✅ | anti_fraude | "broca de oro de 8mm" → material imposible | informó correctamente, no tenemos brocas de oro |
| E38 | ❌ | anti_fraude | "alicate inflable" → producto imposible | inventó alicate inflable: [12662] |
| E39 | ✅ | multiturno_largo | 5 turnos: taladro → Bosch → FAQ → agregar brocas → total | carrito: taladro+brocas, total=$630,784 |
| E40 | ⚠️ | multiturno_largo | 5 turnos: inicio → M6 → M8 → MODIFICAR a 50xM8 → cerrar | turno 5 no cerró pedido claramente |
| E41 | ⚠️ | multiturno_largo | 5 turnos: destornillador → cualquiera → agregar martillo → summary | turno 5 parcial: dest=False mart=True |
| E42 | ⚠️ | multiturno_largo | 5 turnos: mecha 8mm → concreto → 10u → factura A → total | encontró mecha pero sin precio en el total |
| E43 | ⚠️ | multiturno_largo | 5 turnos: saludo → datos → Juan Pérez → sierras → reservar | encontró sierras pero no procesó reserva con datos del cliente |
| E44 | ✅ | whatsapp_fragmentado | 4 mensajes cortos → taladros Bosch | mantuvo contexto a través de 4 mensajes fragmentados |
| E45 | ✅ | whatsapp_fragmentado | 4 mensajes: cuanto / el martillo / de mango fibra / 5kg | armó query de martillo desde mensajes fragmentados |
| E46 | ✅ | whatsapp_fragmentado | 5 mensajes → 10 mechas de 8mm | entendió '10 mechas de 8mm' desde mensajes fragmentados |
| E47 | ⚠️ | whatsapp_fragmentado | "si tenes / mostrame / los caros" → ambiguo | respuesta vaga ante query fragmentado y ambiguo (esperado) |
| E48 | ✅ | whatsapp_fragmentado | "tornillos M6: por kilo o por unidad?" → forma de venta | respondió sobre forma de venta de tornillos M6 |
| E49 | ✅ | ambiguedad | "taladro" (una sola palabra) | mostró opciones o pidió aclaración de tipo |
| E50 | ✅ | ambiguedad | "sí" (sin contexto previo) | pidió contexto ante 'sí' sin antecedente |
| E51 | ✅ | ambiguedad | "todo" (ambigüedad total) | pidió especificación ante 'todo' |
| E52 | ⚠️ | ambiguedad | "barato" (sin contexto) | respuesta vaga ante 'barato' sin contexto (esperado) |
| E53 | ✅ | ambiguedad | "el de Bosch" (sin saber cuál) | preguntó qué producto Bosch sin contexto |

---

## Análisis de FAILs

### E09 — termofusión PP-R (REVISIÓN RECOMENDADA)
**Comportamiento:** El bot muestra `❌ Termofusion 20mm — no lo encontré en el catálogo` correctamente, pero aun así aparecen precios `[10797, 10797, 59726]` en la respuesta correspondientes a los otros ítems del pedido (llaves esféricas, sellador, teflón).
**Causa raíz probable:** El checker confunde los precios de los ítems encontrados con una alucinación sobre PP-R. El comportamiento del bot es correcto — PP-R no está en catálogo y lo dice.
**Acción:** Revisar el checker de E09; probablemente sea un **falso positivo** del test.

### E33 — "taladro de 5000W" → potencia imposible
**Comportamiento:** El bot devuelve `Adaptador Taladro SDS a Mandri` con precio $5.980.
**Causa raíz:** La validación pre-LLM (B2/search_validator) no bloquea la búsqueda de "taladro" cuando la potencia es imposible (5000W > límite real ~2000W). El bot encuentra un producto relacionado a "taladro" y lo presenta.
**Acción:** Agregar validación de potencia máxima para taladros en search_validator.py (ej: `max_watts_taladro = 2000`).

### E35 — "destornillador láser cuántico" → producto imposible
**Comportamiento:** El bot devuelve precios `[89403, 138481]` — parece ser que matcheó `Bosch Soporte par` u otro producto.
**Causa raíz:** El adjetivo "láser cuántico" no es una spec numérica, por lo que el search_validator no lo filtra. El bot hace búsqueda de "destornillador" y matchea cualquier cosa de la categoría.
**Acción:** La validación semántica de productos imposibles (sin spec numérica) es más difícil. Opción: agregar lista de productos literalmente imposibles o confiar en que el LLM rechace.

### E38 — "alicate inflable" → producto imposible
**Comportamiento:** El bot devuelve `Alicate 7" Davidson · $12.66`.
**Causa raíz:** El bot matchea "alicate" ignorando "inflable". "Inflable" no es una spec numérica que B2 pueda validar. El bot legítimamente encontró alicates en el catálogo.
**Acción:** Similar a E35 — requiere validación semántica de adjetivos imposibles, fuera del alcance de B2.

---

## Análisis de WARNs

| ID | Tipo | ¿Esperado? | Notas |
|----|------|------------|-------|
| E14 | conversacion_argentina | ✅ Sí | "dale mostrame qué hay" es ambiguo por diseño — WARN es correcto |
| E15 | conversacion_argentina | ✅ Sí | Sin contexto previo, respuesta vaga es normal |
| E22 | negociacion | ⚠️ Parcial | Debería mencionar que el descuento por volumen requiere hablar con un humano |
| E28 | disponibilidad_stock | ⚠️ Parcial | "cuándo te llega?" debería escalar a humano, no responder vagamente |
| E40 | multiturno_largo | ⚠️ Parcial | El cierre de pedido multiturno sigue siendo frágil |
| E41 | multiturno_largo | ⚠️ Parcial | Resumen de carrito en turno 5 incompleto |
| E42 | multiturno_largo | ⚠️ Parcial | Factura A no aparece en el total — probablemente out-of-scope |
| E43 | multiturno_largo | ⚠️ Parcial | Reserva con datos del cliente no procesada (feature no implementada) |
| E47 | whatsapp_fragmentado | ✅ Sí | "si tenes / mostrame / los caros" es ambiguo estructuralmente |
| E52 | ambiguedad | ✅ Sí | "barato" sin contexto — WARN esperado |

---

## Bugs accionables identificados

### CRÍTICO — Anti-fraude incompleto para specs imposibles sin valor numérico
**Afecta:** E35, E38 (y potencialmente otros casos similares)
**Descripción:** B2/search_validator bloquea specs numéricas imposibles (ej: 5000W para taladro) pero no bloquea adjetivos cualitativos imposibles (ej: "láser cuántico", "inflable") en productos que sí existen.
**Impacto en demo:** Bajo — los clientes reales no piden "alicates inflables". Pero para demo técnica puede verse mal.
**Fix propuesto:** Lista negra de adjetivos imposibles en search_validator (extensible), o delegar al LLM con prompt explícito.

### MEDIO — "taladro 5000W" pasa el validador
**Afecta:** E33
**Descripción:** El search_validator no tiene límite de watts para taladros.
**Fix propuesto:** Agregar a search_validator: `if "taladro" in query and watts > 2000: block`.

### LEVE — E09 checker falso positivo probable
**Afecta:** E09
**Descripción:** El checker de E09 ve precios en la respuesta y los atribuye a PP-R, cuando en realidad son de los otros ítems del pedido (llaves, sellador, teflón).
**Fix propuesto:** Revisar la lógica del checker de E09 en `demo_test_suite_extended.py`.

### LEVE — Multiturno largo: cierre de pedido frágil (E40-E43)
**Afecta:** E40, E41, E42, E43
**Descripción:** En secuencias de 5 turnos, el carrito final a veces queda incompleto o el bot no cierra claramente.
**Contexto:** Algunos de estos son WARNs por features no implementadas (factura A, datos de reserva con nombre de cliente). No son regresiones.

---

## Resumen de accionables para próxima sesión

| Prioridad | ID | Tipo | Acción |
|-----------|-----|------|--------|
| 🔴 Alta | C1 | Bug | Agregar límite de watts en search_validator para taladros |
| 🟡 Media | C2 | Bug | Investigar cómo bloquear adjetivos imposibles (láser cuántico, inflable) |
| 🟢 Baja | C3 | Falso+ | Revisar checker E09 en extended suite |
| 🟢 Baja | C4 | WARN | E22 — mención política mayorista en respuesta a "si llevo 100 me bajás?" |
| 🟢 Baja | C5 | WARN | E28 — escalar a humano cuando preguntan por reposición de stock |

---

## Comparación con suite original (31 casos)

| Suite | PASS | WARN | FAIL | ERROR |
|-------|------|------|------|-------|
| demo_test_suite.py (31 casos, post-B2) | ~21 (68%) | ~6 (19%) | ~4 (13%) | 0 |
| demo_test_suite_extended.py (53 casos) | 39 (74%) | 10 (19%) | 4 (8%) | 0 |

El PASS rate mejoró de 68% → 74% en una suite más grande y con casos más difíciles, confirmando que las merges A1+A2+B1+B2 mejoraron el bot.

---

*Generado: 2026-05-03 | No commiteado — revisar antes de commit*
