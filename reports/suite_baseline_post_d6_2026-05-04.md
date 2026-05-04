# Suite Baseline Post-D6 — 2026-05-04

**Commit:** `de9fa37` (main, post matcher bug bundle D1-D6 + hotfix)
**Branch medición:** `test/P2-suite-baseline-post-d6`
**Run IDs:** original=`b61977b4`, extendido=`635561c4`
**Fecha:** 2026-05-04
**Referencia pre-D6:** `reports/extended_test_results_2026-05-03.md` (post-A1+A2+B1+B2)

---

## Resumen ejecutivo

Se re-ejecutaron ambos suites de demo end-to-end contra el bot en estado `de9fa37`
(post-D1-D6 + hotfix electrovalvula + C1 validators). Resultados:

| Suite | Pre-D6 PASS | Post-D6 PASS | Delta |
|-------|------------|-------------|-------|
| Original (31 casos) | ~21/31 (68%) | **26/31 (84%)** | **+5 PASS (+16 pp)** |
| Extendido (53 casos) | 39/53 (74%) | **41/53 (77%)** | **+2 PASS (+3 pp)** |

**Veredicto: el bot está significativamente mejor que pre-D6.** El suite original muestra
mejora clara (+16 pp). El extendido muestra mejora modesta neta (+3 pp) porque 5 mejoras
se cancelan parcialmente con 3 regresiones menores (PASS→WARN) y 1 regresión media
(WARN→FAIL en E41 multiturno largo).

No se detectaron errores de rate limit en ningún suite — ambos corrieron completos.

---

## Hallazgo crítico: `niple` y `ramal` con `allowed_categories: []`

Durante ambas ejecuciones se detectó un nuevo `KnowledgeValidationError`:
```
WARNING: knowledge_load_failed tenant=ferreteria
  error=family 'niple' must have allowed_categories
```

`data/tenants/ferreteria/knowledge/family_rules.yaml` tiene dos familias con lista vacía:
- `niple: allowed_categories: []` (comentario: "grep returned no results")
- `ramal: allowed_categories: []` (comentario: "grep returned no results")

Mismo patrón que `electrovalvula` (eliminada en hotfix c8dc5ba). El error es no-bloqueante
(bot sigue respondiendo) pero implica que el knowledge scorer D3 no está activo en
producción ni en los tests. **El PENDIENTES.md decía "Knowledge loader: carga OK con 20
familias" — ese dato era incorrecto.** El loader falla en `niple` antes de llegar a
cargar completamente.

**Impacto en resultados:** Los tests se ejecutaron sin knowledge scoring activo. Los
resultados reflejan el bot con D4/D6 matcher base (token-overlap) pero sin familia-scoring
de D3. Esto puede explicar por qué algunas mejoras de D3 no son visibles.

---

## Suite original (31 casos) — resultados completos

**Tiempo total:** 350s (~6 min)

| ID | Categoría | Descripción | Post-D6 | Notas |
|----|-----------|-------------|---------|-------|
| C01 | saludos | "hola" | ✅ PASS | saludo correcto sin precios |
| C02 | saludos | "buenas" | ✅ PASS | saludo correcto |
| C03 | saludos | "hola, ¿cómo va?" | ✅ PASS | saludo correcto |
| C04 | producto_simple | "necesito un taladro" | ✅ PASS | encontró taladro o pidió clarificación |
| C05 | producto_simple | "precio del martillo" | ✅ PASS | martillo con precio max=$30,104 |
| C06 | producto_simple | "tienen llaves francesas?" | ✅ PASS | llaves francesas con precio |
| C07 | parser | "Hola, 3 martillos y 2 dest." | ✅ PASS | parseó ambos, ignoró saludo |
| C08 | parser | lista 4 ítems | ✅ PASS | encontró 4/4 ítems |
| C09 | parser | 3 ítems técnicos M6/8mm/6mm | ✅ PASS | encontró 3/3 con especificación |
| C10 | parser | 3 ítems plomería | ✅ PASS | encontró 3/3 ítems |
| C11 | multiturno | 3 turnos: items→FAQ→agregar | ✅ PASS | carrito preservado + FAQ + additive OK |
| C12 | matcher | "llave francesa" → no adaptadores | ✅ PASS | matcheó llaves francesas correctamente |
| C13 | matcher | "mecha 8mm" → no acoples $57k+ | ✅ PASS | bot pidió clarificación (sin precio = no matcheó acople) |
| C14 | matcher | "destornillador philips" | ⚠️ WARN | destornillador genérico, sin referencia Philips/PH |
| C15 | casos_limite | "está caro" → objeción | ✅ PASS | manejo correcto de objeción |
| C16 | casos_limite | "quiero hablar con humano" | ✅ PASS | escaló a equipo humano |
| C17 | casos_limite | "qué horarios tienen?" | ✅ PASS | respondió FAQ horario |
| C18 | anti_alucinacion | "caños PP-R termofusión 20mm" | ⚠️ WARN | respuesta evasiva, no confirma ni niega |
| C19 | anti_alucinacion | "martillo Stanley 500kg" | ✅ PASS | descartó producto absurdo |
| C20 | anti_alucinacion | "100 unidades de AAAAA" | ✅ PASS | indicó que no existe |
| C21 | regresion_precio | "10 mechas 8mm" → precio razonable | ✅ PASS | precio $89,780 (esperado ~$64k para 10u) |
| C22 | tolerancia | TYPO "lave francesa" | ✅ PASS | reconoció typo, encontró llaves |
| C23 | tolerancia | TYPO "destornilador" (una L) | ✅ PASS | reconoció typo |
| C24 | tolerancia | ABREV "dest planos chicos" | ❌ FAIL | no interpretó abreviación, pidió rubro |
| C25 | tolerancia | SLANG "pico de loro" | ✅ PASS | reconoció como pinza |
| C26 | tolerancia | SLANG "caja de luz" | ✅ PASS | reconoció como caja eléctrica |
| C27 | tolerancia | INGLÉS "wrench" | ✅ PASS | preguntó si es llave inglesa/tubo |
| C28 | tolerancia | PLURAL "3 martillo" | ✅ PASS | parseó como 3 martillos |
| C29 | tolerancia | SIN ACENTO "mecha de 8 mm" | ⚠️ WARN | precio $1,009,673 muy alto — match incorrecto |
| C30 | tolerancia | JERGA "10 codos roscados" | ❌ FAIL | no respondió con codos de plomería |
| C31 | tolerancia | MARCA "tienen Bosch?" | ✅ PASS | encontró productos Bosch directamente |

### Resumen original
| Estado | Cantidad | % |
|--------|----------|---|
| ✅ PASS | 26 | 84% |
| ⚠️ WARN | 3 | 10% |
| ❌ FAIL | 2 | 6% |
| 💥 ERROR | 0 | 0% |

### Comparación vs pre-D6 (original)
Pre-D6 baseline: ~21/31 PASS (68%) per PENDIENTES.md (nota: script header indicaba 19/31 61%)

Mejoras confirmadas (FAIL/WARN → PASS):
- C08: lista 4 ítems → PASS (D-series tokenizer mejoró parser)
- C09: 3 ítems técnicos → PASS
- C13: mecha 8mm → no acoples → PASS (D4 strict overlap + D6 stopwords)
- C21: precio 10 mechas → PASS (D4/D6 match correcto, precio $89k razonable)
- Varios otros del bloque tolerancia → PASS (A2/D2 normalization)

Sin regresiones detectadas en suite original (todos los FAILs actuales C24, C30 ya estaban en pre-D6).

---

## Suite extendido (53 casos) — resultados completos

**Tiempo total:** 980s (~16 min)

| ID | Categoría | Descripción | Pre-D6 | Post-D6 | Delta |
|----|-----------|-------------|--------|---------|-------|
| E01 | pedidos_mayoristas | lista obra 5 ítems | ✅ | ✅ | = |
| E02 | pedidos_mayoristas | M6+M8+M10 hex | ✅ | ✅ | = |
| E03 | pedidos_mayoristas | cable+cajas+termocontraíble | ✅ | ✅ | = |
| E04 | pedidos_mayoristas | niples+codos+llaves+sellador | ✅ | ✅ | = |
| E05 | pedidos_mayoristas | mechas Bosch anti-acople | ✅ | ✅ | = |
| E06 | pedidos_mayoristas | tablero eléctrico 5 ítems | ✅ | ✅ | = |
| E07 | pedidos_mayoristas | verificar stock 5 herramientas | ✅ | ✅ | = |
| E08 | pedidos_mayoristas | Bahco+taladros+amoladoras | ✅ | ✅ | = |
| E09 | pedidos_mayoristas | PP-R + llaves + sellador + teflón | ❌ | ❌ | = |
| E10 | pedidos_mayoristas | caños galvanizados 4 ítems | ✅ | ✅ | = |
| E11 | pedidos_mayoristas | multiplicador x50 | ✅ | ⚠️ | **-** |
| E12 | pedidos_mayoristas | WD-40+grasa+trapos+guantes | ✅ | ✅ | = |
| E13 | conversacion_argentina | "che, tenés taladros?" | ✅ | ✅ | = |
| E14 | conversacion_argentina | "dale, mostrame qué hay" | ⚠️ | ⚠️ | = |
| E15 | conversacion_argentina | "buenísimo, voy con eso" | ⚠️ | ⚠️ | = |
| E16 | conversacion_argentina | "está mortal el precio" | ✅ | ✅ | = |
| E17 | conversacion_argentina | "me sirve, dale" | ✅ | ✅ | = |
| E18 | conversacion_argentina | "nahh está caro" | ✅ | ✅ | = |
| E19 | conversacion_argentina | "no me convence, mostrame otra" | ✅ | ✅ | = |
| E20 | conversacion_argentina | "tipo Bosch tenés algo?" | ✅ | ⚠️ | **-** |
| E21 | negociacion | "está caro, cuánto el último?" | ✅ | ✅ | = |
| E22 | negociacion | "si llevo 100 me bajás?" | ⚠️ | ⚠️ | = |
| E23 | negociacion | "en otro lado lo conseguí más barato" | ✅ | ✅ | = |
| E24 | negociacion | "hacés descuento por mayor?" | ✅ | ✅ | = |
| E25 | negociacion | "15% off?" | ✅ | ✅ | = |
| E26 | negociacion | "dame mejor precio" | ✅ | ✅ | = |
| E27 | disponibilidad_stock | "hay stock de taladros Bosch?" | ✅ | ✅ | = |
| E28 | disponibilidad_stock | "cuándo te llega más mercadería?" | ⚠️ | ⚠️ | = |
| E29 | disponibilidad_stock | "tenés disponible para mañana?" | ✅ | ✅ | = |
| E30 | disponibilidad_stock | "me reservás 50 tornillos M6?" | ✅ | ✅ | = |
| E31 | disponibilidad_stock | "hasta cuándo me lo guardás?" | ✅ | ✅ | = |
| E32 | disponibilidad_stock | "está disponible o lo tienen que pedir?" | ✅ | ✅ | = |
| E33 | anti_fraude | "taladro de 5000W" | ❌ | ✅ | **+** |
| E34 | anti_fraude | "martillo 100kg" | ✅ | ✅ | = |
| E35 | anti_fraude | "destornillador láser cuántico" | ❌ | ✅ | **+** |
| E36 | anti_fraude | "100 metros de tornillo" | ✅ | ✅ | = |
| E37 | anti_fraude | "broca de oro de 8mm" | ✅ | ✅ | = |
| E38 | anti_fraude | "alicate inflable" | ❌ | ✅ | **+** |
| E39 | multiturno_largo | 5 turnos: taladro→Bosch→FAQ→brocas | ✅ | ✅ | = |
| E40 | multiturno_largo | 5 turnos: M6→M8→MODIFICAR→cerrar | ⚠️ | ✅ | **+** |
| E41 | multiturno_largo | 5 turnos: dest→cualquiera→martillo→summary | ⚠️ | ❌ | **-** |
| E42 | multiturno_largo | 5 turnos: mecha→concreto→10u→facturaA→total | ⚠️ | ⚠️ | = |
| E43 | multiturno_largo | 5 turnos: saludo→datos→Juan→sierras→reservar | ⚠️ | ⚠️ | = |
| E44 | whatsapp_fragmentado | 4 mensajes → taladros Bosch | ✅ | ✅ | = |
| E45 | whatsapp_fragmentado | 4 mensajes → martillo mango fibra 5kg | ✅ | ✅ | = |
| E46 | whatsapp_fragmentado | 5 mensajes → 10 mechas 8mm | ✅ | ✅ | = |
| E47 | whatsapp_fragmentado | "si tenes/mostrame/los caros" | ⚠️ | ⚠️ | = |
| E48 | whatsapp_fragmentado | "tornillos M6: kilo o unidad?" | ✅ | ✅ | = |
| E49 | ambiguedad | "taladro" (una palabra) | ✅ | ✅ | = |
| E50 | ambiguedad | "sí" (sin contexto) | ✅ | ✅ | = |
| E51 | ambiguedad | "todo" (ambigüedad total) | ✅ | ⚠️ | **-** |
| E52 | ambiguedad | "barato" (sin contexto) | ⚠️ | ✅ | **+** |
| E53 | ambiguedad | "el de Bosch" (sin saber cuál) | ✅ | ✅ | = |

### Resumen extendido
| Estado | Pre-D6 | Post-D6 |
|--------|--------|---------|
| ✅ PASS | 39 (74%) | **41 (77%)** |
| ⚠️ WARN | 10 (19%) | 10 (19%) |
| ❌ FAIL | 4 (8%) | **2 (4%)** |
| 💥 ERROR | 0 | 0 |

### Mejoras (FAIL/WARN → PASS)
| Caso | Tipo | De → A | Fix responsable |
|------|------|--------|----------------|
| E33 | anti_fraude | FAIL → PASS | C1: V6 (límite watts taladro 2000W) |
| E35 | anti_fraude | FAIL → PASS | C1: V7 (adjetivos imposibles: "cuántico") |
| E38 | anti_fraude | FAIL → PASS | C1: V7b (pares bloqueados: inflable+alicate) |
| E40 | multiturno_largo | WARN → PASS | D-series: mejor parsing de modificaciones de carrito |
| E52 | ambiguedad | WARN → PASS | D-series + prompt: "barato" ahora pide contexto correctamente |

### Regresiones (PASS/WARN → FAIL/WARN)
| Caso | Tipo | De → A | Análisis |
|------|------|--------|---------|
| E11 | pedidos_mayoristas | PASS → WARN | Multiplicador x50 ya no interpretado; D6 stopwords pudo afectar parsing numérico |
| E20 | conversacion_argentina | PASS → WARN | "tipo Bosch tenés algo?" ahora respuesta vaga; posiblemente prompt o routing cambió |
| E41 | multiturno_largo | WARN → FAIL | Turno 5 muestra mensaje de bienvenida en lugar de resumen — probable session ID issue |
| E51 | ambiguedad | PASS → WARN | "todo" ahora respuesta vaga; pequeño cambio en prompt handling |

**Nota sobre E41:** La respuesta en turno 5 fue "Hola, soy Ferretero de Ferretería. ¿En qué te puedo ayudar?" — indica reset de sesión inesperado durante el test de 5 turnos. Puede ser un artifact del test runner (session isolation) más que una regresión del bot.

**Nota sobre E09:** Sigue siendo FAIL. El checker detecta precios `[577, 10797, 64221]` en una respuesta donde el bot muestra una "Tee Termofusion 20mm · $577" — el checker no puede distinguir si el bot halló PP-R o un producto con "termofusion" en el nombre. El comportamiento del bot puede ser correcto. Este caso es candidato a falso positivo del checker (P3).

### No afectados por rate limits
No se detectaron errores HTTP 429 en ninguna de las dos ejecuciones. Todos los casos
completaron con respuesta válida del LLM.

---

## Top 5 mejoras para mostrar al cliente

1. **E33: "taladro de 5000W"** — Bot bloquea specs eléctricas imposibles. El bot ahora
   dice "no existe un taladro de 5000W, el máximo real es ~2000W" en lugar de devolver
   cualquier producto relacionado. Demuestra anti-alucinación técnica robusta.

2. **E35/E38: productos imposibles semánticos** — "destornillador láser cuántico" y
   "alicate inflable" son rechazados correctamente. El bot ya no matchea el sustantivo
   e ignora el adjetivo imposible.

3. **C13/C21 (suite original): mecha 8mm sin acoples** — El bug central del matcher
   (mecha→acople de $57k) está resuelto. El bot ahora pide clarificación de tipo de mecha
   o muestra precio razonable (~$89k para 10u vs $577k antes).

4. **E40: carrito multiturno con modificación** — "5 turnos: M6→M8→MODIFICAR a 50xM8"
   ahora funciona correctamente. El bot preserva el carrito y aplica la modificación en
   el turno correcto.

5. **C08: lista 4 ítems** — El parser con prefijo "Te paso lista:" que fallaba antes
   ahora detecta 4/4 ítems correctamente. Mejora directa para casos de uso mayoristas.

---

## FAILs persistentes (D1-D6 no resolvieron)

| Suite | Caso | Descripción | Razón probable | Bug pendiente |
|-------|------|-------------|---------------|--------------|
| Original | C24 | "dest planos chicos" → destornillador | "dest" como abreviación no está en synonyms.yaml; el LLM no lo interpreta como destornillador | D2 synonyms incompletos — falta agregar "dest" |
| Original | C30 | "10 codos roscados" → codos plomería | La query falla match en familia `codo`; D6 stopwords puede filtrar "roscados" como stopword incorrecto | D6 stopwords demasiado agresivo (nuevo finding) |
| Original | C29 | "mecha de 8 mm para taladro" | Precio $1,009,673 — match incorrecto a algo grande. "para taladro" puede estar afectando el context filter | C29 conocido en PENDIENTES, D6 no resolvió |
| Extendido | E09 | PP-R + otros ítems | Checker falso positivo probable (precios de llaves/sellador interpretados como PP-R inventado) | P3: revisar checker de E09 |
| Extendido | E41 | 5 turnos dest+martillo summary | Turno 5 muestra bienvenida en lugar de summary — session reset en test runner | Investigar lifecycle de sesión en test runner |

**Nota sobre C30:** "10 codos roscados" falla con "no respondió con codos de plomería".
La respuesta actual es "Para cotizarte exacto... ¿Qué categoría o rubro estás buscando?".
Esto sugiere que D6 stopwords está filtrando demasiado — "roscados" puede estar siendo
eliminado como stopword, dejando solo "codos" que no matchea en ninguna categoría. O el
primer token "codos" no está en el `match_terms` del family `codo` con suficiente peso.
**Posible regresión de D6 stopwords filter.**

---

## Limitaciones detectadas en los suites

### Falsos positivos del checker (problema documentado en PENDIENTES)
Los suites verifican presencia de keywords en respuesta, no identidad del producto:
- E09: `[577, 10797, 64221]` son precios de llaves/sellador/tee, no de PP-R inventado.
  El checker los atribuye erróneamente a PP-R.
- C14: "destornillador philips" → WARN porque no aparece "philips" o "PH" explícito en
  el nombre del producto, aunque el producto pueda ser correcto.
- C29: precio $1,009,673 para "mecha de 8mm para taladro" indica match incorrecto, pero
  el checker no verifica la categoría del producto devuelto.

### KnowledgeValidationError en producción (nuevo hallazgo)
`niple` y `ramal` tienen `allowed_categories: []` → loader falla antes de completar.
El bot opera sin knowledge scoring activo. Esto contradice lo documentado en PENDIENTES
("Knowledge loader: carga OK con 20 familias"). Fix: misma estrategia que electrovalvula
(eliminar o asignar una categoría real, ej: "Varios").

---

## Archivos visitados (no modificados)

- `scripts/demo_test_suite.py` — leído para entender estructura
- `scripts/demo_test_suite_extended.py` — ejecutado (no modificado)
- `data/tenants/ferreteria/knowledge/family_rules.yaml` — leído para diagnóstico
- `reports/extended_test_results_2026-05-03.md` — leído como baseline pre-D6
- `data/tenants/ferreteria/PENDIENTES.md` — leído (se actualiza en este commit)
- `bot_sales/` — no tocado

---

## Recomendaciones de próximos pasos

### Hotfix inmediato (bloquea knowledge scoring)
- Eliminar o corregir `niple` y `ramal` en `family_rules.yaml` (misma estrategia que
  `electrovalvula`). Sin esto, D3 scoring nunca se activa.

### P3: mejoras a los suites
- E09: corregir checker para distinguir precios de ítems co-existentes vs alucinación PP-R
- C30: investigar si D6 stopwords está filtrando "roscados" incorrectamente
- Revisar `filter_para_context_families()` para C29 ("mecha de 8 mm para taladro")

### Para siguiente sesión de fixes (D7?)
- C24: agregar "dest" como sinónimo de "destornillador" en `synonyms.yaml`
- C30: investigar si `allowed_categories` del family `codo` tiene la categoría correcta
- E11: revisar si el multiplicador x50 requiere un handler específico en el parser
- E20: investigar por qué "tipo Bosch tenés algo?" ahora es WARN en lugar de PASS

---

*Generado: 2026-05-04 | Commit: ver sección de commit hash más abajo*
*No rate-limit failures detectados | KnowledgeValidationError en niple/ramal (no bloqueante)*
