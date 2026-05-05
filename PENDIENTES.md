# PENDIENTES — follow-up items

## B23-FU: apply_clarification debe resolver frases genericas de seleccion

**Contexto:** Regression S08 (E41, 5-turn flow: dest→cualquiera→martillo→stanley→presupuesto).

**Fixes aplicados (commit bcb932e):**
1. `bot.py` seccion 0.5: guard `intent != "quote_modify"` evita que `looks_like_acceptance`
   marque aceptacion cuando TI clasifica `quote_modify`.
2. `ferreteria_quote.py` `_ADDITIVE_RE`: agregado "agregame" para que T3 dispare additive path.

**Gap restante (S08 = WARN, no PASS):**
T2 "cualquiera esta bien" llega a `apply_clarification` (o al LLM fallback equivalente) con un
item ambiguo en el carrito. El bot no interpreta "cualquiera" como seleccion automatica del
primer item — devuelve la pregunta de calificacion. Resultado: ambos items quedan en estado
`ambiguous` al llegar a T5, por lo que el presupuesto final muestra pregunta de desambiguacion
en lugar de lineas con precio.

**Fix requerido:**
En `apply_clarification` (o donde se procese la respuesta a una oferta A/B/C), detectar frases
como "cualquiera", "el que sea", "cualquiera esta bien", "me da igual" y auto-seleccionar la
primera opcion de la ultima lista ofrecida. Alternativa: responder "elegi la opcion A para vos"
y marcar el item como resolved.

**Criterio de exito:** S08 pasa de WARN a PASS en suite C (T5 contiene ambos items con precios).

**Archivos probables:** `bot_sales/ferreteria_quote.py` (seccion `apply_clarification`),
posiblemente `bot_sales/bot.py` seccion 4 (clarification path).

**Regresion de referencia:** `bot_sales/tests/test_b23_acceptance_guard.py`
(actualmente: T2+T3+T5 palabras pass, sin precio — ajustar assertion al completar este fix).
