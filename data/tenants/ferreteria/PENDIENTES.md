# PENDIENTES — Bot Ferretería

**Última actualización:** 2026-05-04
**Estado del bot:** main @ 6772b73 (Fix A merged)
**Producción:** NO en Railway todavía
**Cliente:** datos pendientes (cuestionarios enviados, sin respuesta)

---

## 🚨 BUG CRÍTICO PARA PRÓXIMA SESIÓN — Matcher base

**Descubierto:** 2026-05-03 (testing manual post-Fix A merge)
**Estado:** diagnóstico completo, fix NO aplicado (Fix A solo arregla fallback ciego)
**Bloquea:** producción + demo viable
**Tiempo estimado:** 4-6 horas (1 sesión enfocada)

### Síntoma
El matcher devuelve productos que comparten keywords con la query pero NO son ese
producto. Verificado con código actualizado (post-Fix A) en testing manual:

| Query | Bot devuelve | Debería devolver |
|---|---|---|
| "5 mechas 8mm Bosch" | Accesorio GDE $345k, Acople Atornillador $210k, Acople Broca $57k | Brocas Bosch reales (existen 26 en catálogo) |
| "destornillador philips" | Cerradura Gabinete Destornillador $22k | Stanley Destornillador Basic Philips Nro 1 |
| "taladros?" (anterior test) | Adaptador Taladro SDS, Aparejo Diamantado | Taladros Bosch/Makita/Milwaukee |
| "llaves de paso" (anterior test) | Adaptador Llaves Combinadas | Llave 20mm Paso Total Acqua System |
| "sellador siliconado" (anterior test) | Anteojo con Silicona | Adhesivo Sellador Genrod |
| "codos 90 grados" (anterior test) | (no encuentra) | Alemite Codo 90° |
| "cuplas" (anterior test) | (no encuentra, substring "cupla" en "recuplast") | Bronce cupla 1/4 |
| "martillo Stanley 500kg" (anterior test) | Adaptador Stanley | (V1 debería bloquear pre-LLM) |

**Productos correctos SÍ existen en catálogo.** El bug es del matcher.

### Causas raíz (3 bugs independientes)

**Bug 1 — find_matches() OR logic (CRÍTICO)**
- Ubicación: db/...find_matches
- Usa `any(token in haystack)` lógica permisiva
- "philips" matchea iluminación Philips Home (1243 resultados)
- "90" matchea abrazaderas con rango 70-90 (2085 resultados)
- "cupla" hace substring match con "recuplast" → pinturas Sinteplast

**Bug 2 — buscar_stock() no aplica scoring (CRÍTICO)**
- Ubicación: bot_sales/core/business_logic.py::buscar_stock
- Llama find_matches_hybrid y filtra por available > 0
- NO llama a _score_product
- Devuelve resultados en orden alfabético del catálogo
- Resultado: siempre "Abrazadera", "Adaptador", "Aplique" primero
- _score_product YA EXISTE en ferreteria_quote.py y funciona — solo no se conecta

**Bug 3 — Validator desconectado**
- search_validator.validate_query_specs("martillo 500kg") retorna (False, "peso imposible")
- Pero buscar_stock no llama al validator
- El path LLM→buscar_stock no pasa por search_validator
- Solo _try_ferreteria_pre_route y _try_ferreteria_intent_route Phase 7 lo invocan

### Verificación post-Fix A

Testing manual con bot REINICIADO confirmó:
- ✅ Fix A funciona: NO devuelve productos al azar del catálogo entero como alternativas
- ❌ Bug del matcher persiste: devuelve productos no relacionados que comparten keyword
- Conclusión: Fix A es necesario pero insuficiente. Bug central es matcher base.

### Plan de ataque (próxima sesión)

**Pre-flight (30 min) — CRÍTICO ANTES DE CODEAR:**
1. Verificar item_family_map.yaml cubre plomería:
   - "codo", "cupla", "niple", "llave de paso", "ramal", "tee"
2. Si faltan, agregarlas (puede arreglar varios casos sin tocar código)
3. Verificar también herramientas: "destornillador philips", "taladro" como families

**Fase 1 — Bug 2 (más impacto, hacer primero):**
En business_logic.buscar_stock, después de matches = self.db.find_matches_hybrid(...):
```python
from bot_sales.ferreteria_quote import _score_product, _SCORE_LOW
scored = [(_score_product(m, modelo, knowledge), m) for m in matches]
scored.sort(key=lambda x: x[0], reverse=True)
matches = [m for score, m in scored if score > _SCORE_LOW][:5]
```

**Fase 2 — Bug 1 (estrictar el OR):**
En db.find_matches:
```python
if all(token in haystack for token in tokens):
    matches.append(...)
elif sum(1 for t in tokens if t in haystack) >= len(tokens) // 2 + 1:
    matches.append(...)  # mayoría, no any
```

**Fase 3 — Bug 3 (conectar validator):**
Al inicio de buscar_stock:
```python
from bot_sales.services.search_validator import validate_query_specs
valid, reason = validate_query_specs(modelo)
if not valid:
    return {"status": "no_match", "reason": reason, "_search_query": modelo}
```

**Fase 4 — Test obligatoria:**
- Las 8 queries de la tabla arriba (manualmente, con bot reiniciado)
- Extended suite completo (los 53 casos)
- Smoke tests 17/17
- Verificar que C29, E05 (acople-broca), E08, E01 NO regresionen

### Trampas a evitar
- NO hacer Bug 1 sin Bug 2 (queries quedarían con 0 resultados)
- NO atacar Fix B (mecha→broca alias) hasta que Bug 2 esté funcionando — esa fue la trampa de hoy
- NO confiar solo en suite — los checkers son tolerantes
- IMPORTANTE: REINICIAR el bot después de cualquier cambio de código (auto-reload puede no funcionar)
- _score_product depende de infer_families — si plomería no está en map, va a fallar igual

### Archivos a tocar
- bot_sales/core/business_logic.py (Bug 2, Bug 3)
- bot_sales/db/[archivo de find_matches] (Bug 1)
- data/tenants/ferreteria/knowledge/item_family_map.yaml (pre-flight)
- bot_sales/tests/test_matcher_base.py (NUEVO archivo, tests específicos)

---

## ✅ Cerrados en sesión 2026-05-03

### Fix A — Safe alternatives fallback (CRÍTICO post-cierre)
Commits: 7196752 (fix), 6772b73 (merge)
- bot_sales/core/business_logic.py: buscar_alternativas() ya no hace
  load_stock() ciego cuando no encuentra match relacionado
- Verificado funciona: el bot ya no devuelve productos al azar como alternativas
- Test: bot_sales/tests/test_alternatives_safety.py (5 tests)
- NOTA: NO arregla el bug central del matcher (ver sección 🚨)

### A1 — Anti-alucinación (intento prompt-only)
Commit: cda9377
- Reglas en template_v2.j2 + inyección de _search_query en bot.py
- Resultado parcial: arregló C13 (mecha 8mm) y C20 (SKU AAAAA)
- NO arregló C19 (martillo 500kg) — el LLM ignoraba reglas de peso en el prompt

### A2 — Matcher dimensional + plurales
Commit: 205edb1
- Cross-unit penalty (-4.0) en `_score_dimension_alignment`
- Plural normalization en producto (llaves→llave, francesas→francesa) separada de query
- Question mark stripping del input

### B1 — Fix de regresiones de A2
Commit: f55cdf3
- `normalize_for_product_text()` separada para no degradar matches de producto
- `filter_para_context_families()` para context-of-use (ej: "mecha para taladro" no sugiere taladros)
- Arregló C12 (llave francesa) y C22 (typo llave francesa), mantuvo C29 igual

### B2 — Anti-alucinación robusta (validación pre-LLM)
Commit: b68f12c
- `bot_sales/services/search_validator.py` con 5 validadores (V1-V5)
- V1: peso por familia (martillo >5kg, destornillador >0.8kg, etc.)
- V2: diámetro broca/mecha >60mm
- V3: longitud tornillo/clavo/perno >800mm
- V4: color precioso (dorado/rosa/turquesa/oro) en herramienta metálica manual (segment-based)
- V5: especificación de storage digital (GB/TB/MB) en hardware físico
- Level 2: validación post-búsqueda (spec numérica sin producto coincidente → no_match)
- Inyección en 3 puntos de bot.py (product_search, get_product_info, check_stock)
- Arregló C19 finalmente (martillo 500kg → bloqueado por V1)

### C1 — Extended failures + V6/V7
Commit: dd9b985 (merge), 2a29fdd (fix)
- V6: límite de watts por familia eléctrica:
  taladro 2000W, amoladora/esmeriladora 2500W, sierra circular 2500W,
  lijadora 1500W, aspiradora 2500W, soldadora 5000W
- V7a: adjetivos universalmente imposibles (cuántico, virtual, holográfico, volador,
  telepático, mágico) bloquean con cualquier herramienta del catálogo
- V7b: pares bloqueados específicos (láser+destornillador/martillo/alicate,
  inflable+alicate/martillo/destornillador/taladro, digital+martillo)
- E09 checker fix en `demo_test_suite_extended.py`: distingue precios legítimos de otros
  ítems del mismo pedido vs. alucinación de PP-R
- Suite extendido de 53 casos commiteado: `scripts/demo_test_suite_extended.py`
- 9 tests V6 + 8 tests V7 agregados a `bot_sales/tests/test_search_validator.py`

---

## 📊 Estado del bot al cierre

### Suite original (31 casos) — `scripts/demo_test_suite.py`
- **PASS**: ~21 / 31 (68%) — medido post-B2, pre-C1
- **WARN**: ~6 (19%)
- **FAIL**: ~4 (13%)
- C1 no impacta significativamente el suite original (sus fixes apuntan a specs no-numéricas)

### Suite extendido (53 casos) — `scripts/demo_test_suite_extended.py`
- **Pre-C1** (según reports/extended_test_results_2026-05-03.md):
  39 PASS (74%), 10 WARN, 4 FAIL (E09, E33, E35, E38)
- **Post-C1**: E09, E33, E35, E38 confirmados PASS en corridas de validación
- **Nota E01/E08**: fallan intermitentemente por rate limits de OpenAI (TPM 30K) cuando
  se corren los 53 casos seguidos — verificado que el comportamiento es idéntico
  con/sin los fixes de C1 (no son regresiones del código)

### Tests unitarios — `bot_sales/tests/`
- **100 passed**, 5 deselected (slow) — medido post-C1
- 60 `test_search_validator.py` (V1-V7)
- 19 `test_a2_regressions.py`
- 16 `test_matcher_dimensional.py`
- 5 `test_anti_hallucination.py`

### Smoke tests — `scripts/smoke_ferreteria.py`
- **16 OK / 1 FAIL pre-existente** — medido post-C1
- FAIL: `routing proyecto` — el bot pide especificación ante query ambiguo de "baño" en vez de routear directamente; bug pre-existente no relacionado con C1

---

## 🔴 Bugs críticos para producción (bloquean Railway)

### 1. Performance lenta en pedidos multi-item
- Tiempo de respuesta: ~30s para queries con 5+ ítems
- Inviable para producción real (clientes esperan 5-10s max)
- Hipótesis: latencia LLM acumulada + búsquedas secuenciales en catálogo de 60K SKUs
- Acción: investigar paralelización de búsquedas, caching de embeddings, batch LLM calls

### 2. E01/E08 intermitentes (parser multi-item bajo rate limits)
- "lista obra: caño/codos/cuplas/llaves/ramales" y "Bahco sets + taladros + amoladoras"
  fallan intermitentemente al correr el suite completo de 53 casos
- Causa raíz: OpenAI TPM 30K + posible fragilidad del parser con listas largas bajo presión
- El bug existe pre-fixes (verificado con git stash, 3 runs c/u)
- Para producción: necesitamos mayor TPM o procesamiento más eficiente

### 4. Matcher base con keyword overlap simple (ver sección 🚨 al inicio)
- El bot devuelve productos no relacionados que comparten keywords
- Bloquea demo viable y producción real
- Plan completo en sección crítica al inicio del archivo
- Verificado con testing manual post-Fix A

### 3. Datos del cliente pendientes
- El cuñado no respondió los cuestionarios todavía
- Sin estos datos, `profile.yaml` tiene placeholders que la `pending_guard` intercepta
- **Necesario antes de demo real**: políticas de descuento, horarios, datos de contacto,
  condiciones mayoristas, zonas de envío, medios de pago
- Ver checklist completo al final de este archivo

---

## ⚠️ Limitación crítica de los test suites

### El problema
Los checkers de demo_test_suite.py y demo_test_suite_extended.py verifican
respuestas con keyword matching simple. Esto causa FALSOS POSITIVOS:

- "destornillador philips" → bot devuelve "Cerradura Cierre Gabinete Destornillador"
- Checker: respuesta contiene "destornillador" → PASS ✅
- Realidad: producto NO es un destornillador → FAIL real

### Impacto
Los suites reportan 74-77% PASS pero el bot tiene bugs sistémicos.
Solo testing manual los detecta.

### Plan de mejora (próxima sesión, junto con matcher fix)
1. Cambiar checkers a verificar **categoría del producto retornado**, no solo keywords
2. Para queries de "destornillador", verificar que producto.category == "Herramientas Manuales > Destornilladores"
3. Para queries con marca, verificar marca real, no solo presencia de palabra
4. Tests de NO-MATCH: verificar que productos NO relacionados (cerraduras, adaptadores, accesorios) NO aparezcan en respuestas

---

## 🟠 Bugs importantes (no bloquean producción)

### Matcher
- **C29** (mecha 8mm para taladro — precio $2.4M) — WARN persistente
  - Causa: "mecha para taladro" matchea bocallave en contexto equivocado
  - Fix Plan A (definitivo): re-tag catálogo con LLM (costoso pero correcto)
  - Fix Plan B: tabla de antagonistas (mecha vs bocallave en mismo query)
  - Estado: `filter_para_context_families()` mitiga pero no elimina el problema

- **Llaves francesas interrogativa** — FAIL en suite original
  - Query: "tienen llaves francesas?" — el `?` triggeraba matching incorrecto
  - Question mark stripping (A2) mejoró esto; verificar si aún falla

### Anti-alucinación
- **E22** (descuento por volumen) — WARN
  - "si llevo 100 me bajás?" — el bot no menciona la política de descuento por volumen
  - Fix: agregar mención a política mayorista cuando detecta pregunta de volumen

- **E28** (reposición de stock) — WARN
  - "cuándo te llega más mercadería?" — no escala a humano
  - Fix: reconocer pregunta de reposición y escalar

### Multiturno largo (E40-E43) — WARNs
- Secuencias de 5 turnos: el cierre de pedido/carrito sigue siendo frágil
- E43 (reserva con datos de cliente) y E42 (factura A en total) son features no implementadas
- E40, E41: carrito parcialmente incompleto en turno 5

---

## 🟡 Mejoras / nice to have

- **Rate limit en suite**: Agregar `time.sleep(2)` entre casos en `demo_test_suite_extended.py`
  para evitar TPM overflow en corridas completas
- **Embeddings semánticos**: post-MVP, para matcher más robusto (reemplaza keyword matching)
- **Catálogo — categorización**: 7 llaves esféricas en "General" en vez de "Plomería"
  (ver sección de gaps al final)
- **Decisión técnica pendiente**: ¿búsqueda del bot menos restrictiva por categoría?
  (ver sección de gaps al final)

---

## 📋 Próximas sesiones

### Sesión N+1 (cuando responda el cliente)
- Cargar datos reales en `profile.yaml` (ver checklist al final)
- Actualizar `data/tenants/ferreteria/knowledge/faqs.yaml` con horarios, pagos, envíos
- Re-correr suites para verificar PASS rate con datos reales

### Sesión N+2 (preparación demo)
- Grabar video Loom para el cuñado
- Mostrar suite original + extendido como evidencia de robustez
- Preparar guion de casos a demostrar en vivo
- Decidir si mostrar los WARNs como "casos edge esperados" o intentar arreglarlos antes

### Sesión N+3 (deploy)
- Investigar y arreglar performance (30s → <10s)
- Cleanup de worktrees mergeados (ver sección técnica)
- Deploy a Railway (`railway up` desde main)
- Monitoreo de errores en producción

---

## 🛠 Notas técnicas (importantes)

### OpenAI rate limits
- Tier actual: TPM 30K (tokens por minuto)
- Suite extendido (53 casos) excede TPM ocasionalmente cuando se corre todo seguido
- Para tests confiables: agregar `time.sleep(2)` entre casos o splitear suite en 2 corridas
- Para producción: necesitamos plan superior o implementar batch processing

### Worktrees del repo (cleanup pendiente)
Al cierre de sesión existen estos worktrees — todos mergeados a main, listos para remover:
```
ferreteria-A1   fix/anti-hallucination        264e402  mergeada ✓
ferreteria-A2   fix/matcher-dimensional        c395363  mergeada ✓
ferreteria-B1   fix/a2-regressions             d76979a  mergeada ✓
ferreteria-B2   fix/anti-hallucination-strict  a075411  mergeada ✓
ferreteria-C1   fix/extended-failures          2a29fdd  mergeada ✓
```
Cleanup (desde ferreteria/):
```bash
for wt in ferreteria-A1 ferreteria-A2 ferreteria-B1 ferreteria-B2 ferreteria-C1; do
  git worktree remove ../Bots/$wt
done
```

### Comandos de test
```bash
# Suite original (31 casos, ~3-4 min)
PYTHONPATH=. python3 scripts/demo_test_suite.py

# Suite extendido (53 casos, ~10 min con rate limits)
PYTHONPATH=. python3 scripts/demo_test_suite_extended.py

# Tests unitarios (sin LLM, <1 seg)
PYTHONPATH=. python3 -m pytest bot_sales/tests/ -v -m "not slow"

# Smoke tests (~2 min)
PYTHONPATH=. python3 scripts/smoke_ferreteria.py
```

---

## 📋 Checklist datos del cliente (PENDIENTE de respuesta)

Completar estos datos ANTES de mostrar el bot a clientes reales.
Todos los campos marcados `[PENDIENTE...]` en `profile.yaml` quedan bloqueados por
la guardia en `bot_sales/services/pending_guard.py`.

### Contacto
- [ ] **Teléfono / WhatsApp real** (ej: `+54 9 11 1234-5678`)
- [ ] **Dirección física del local** (ej: `Av. Corrientes 1234, CABA`)
- [ ] **Ciudad / Barrio / Zona** (para contextualizar envíos)
- [ ] **Link Google Maps**

### Horarios
- [ ] **Horario lunes a viernes**
- [ ] **Horario sábado**
- [ ] **¿Abren domingos o feriados?**

### Medios de pago
- [ ] **Métodos aceptados** (efectivo, transferencia, MercadoPago, Naranja X, tarjetas, cheque)
- [ ] **Cuotas** (¿sin interés? ¿qué tarjetas? ¿cuántas cuotas?)

### Condiciones mayoristas
- [ ] **Monto mínimo de compra mayorista** (ej: `$50.000 ARS`)
- [ ] **Cuenta corriente** (¿otorgan? ¿condiciones?)

### Envíos y logística
- [ ] **Zonas de envío cubiertas**
- [ ] **Plazo de entrega habitual**
- [ ] **¿Envío gratis a partir de cierto monto?**

### Identidad del negocio
- [ ] **Nombre completo / razón social** (hoy figura como "Ferreteria Central" — ¿correcto?)
- [ ] **Años en el mercado / historia breve**
- [ ] **Especialidades o rubros fuertes**

### Decisión técnica pendiente
- [ ] **Duración de reservas (hold_minutes)**:
  `policies.md` dice 45 min vs. configuración 1440 min (24h) — confirmar con cliente

---

## 🗂 Gaps detectados en el catálogo

### Categorización
- 7 llaves esféricas (1/2", 3/4", 20mm, 25mm, gas) están en "General" en vez de "Plomería"
  - Pregunta para el cliente: ¿mover a Plomería, o correcto así?

### Productos faltantes
- Caños de termofusión PP-R no están en el catálogo (solo accesorios/boquillas)
  - Pregunta: ¿los vende y faltan cargar, o no los vende?

### Decisión técnica
- El bot busca por categoría primero. Si un producto está mal categorizado no lo encuentra.
  Opciones:
  (a) Arreglar la categorización (recomendado si son pocos productos)
  (b) Hacer la búsqueda menos restrictiva sobre categoría
  (c) Combinación de ambos

---

*Sesión 2026-05-03 cerrada. 5 merges completados (A1+A2+B1+B2+C1). Bot estable, 100 tests unitarios pasando, suite extendido operativo.*
