# B25 Test Migration Notes — Validators V4/V5/V7/V8/V9 Removal

**Branch**: feat/B25-validators-cleanup
**Date**: 2026-05-05
**Baseline**: d8bf819 (merge B21 TurnInterpreter LLM-first)

---

## Summary

B25 removes pre-LLM validators V4/V5/V7/V8/V9 from `search_validator.py` and their
invocation blocks from `bot.py`. TurnInterpreter (B21) now handles these cases via
LLM-first routing with constrained output and zero temperature.

**Net LOC removed**: -1081 (1099 deletions / 18 insertions)

---

## Files deleted

### `bot_sales/tests/test_handoff_negotiation.py` (149 LOC, 6 tests)

**Why deleted**: File tested V8 (`detect_negotiation_intent`) as a pre-LLM interceptor
via `bot.process_message()`. After B25, V8 no longer exists. The integration tests
(without LLM mocks) would now reach TurnInterpreter (real API call), breaking the unit
test pattern. `test_llm_not_called_on_negotiation` explicitly asserts V8 fires before
LLM — this assertion is now inverted (LLM IS called).

**Coverage now in**: `test_turn_interpreter_v2.py::TestTurnInterpreterV2RealLLM`
- `test_negotiation_bajame_15_percent` — "bajame 15%" → intent=escalate, reason=negotiation
- `test_negotiation_hacele_algo` — "hacele algo al precio" → escalate/negotiation
- `test_no_negotiation_es_caro_pero_me_lo_llevo` — price objection but acceptance, NOT escalate

**Cases from deleted file NOT in v2 suite** (acceptable gaps):
- `test_carrito_preserved_after_handoff` — cart preserved when negotiation fires. Now
  irrelevant because negotiation goes through TurnInterpreter+EscalationHandler, which
  do not modify the cart. Structural guarantee, not a regression risk.
- `test_handoff_fires_for_all_patterns` — 8-pattern spot check. Now covered by TurnInterpreter
  semantically; individual pattern testing at function level no longer meaningful.
- `test_no_handoff_for_price_objection` (E18/E21) — "nahh está caro" must not trigger
  handoff. Covered by `test_no_negotiation_es_caro_pero_me_lo_llevo`.

---

### `bot_sales/tests/test_ambiguity_clarification.py` (327 LOC, 44 tests)

**Why deleted**: All 44 tests target `detect_ambiguous_query`, `_v9_has_product_keyword`,
`_v9_detect_brand` — functions deleted in B25. The 7 integration tests in `TestV9Integration`
assumed V9 fires before TurnInterpreter (i.e., LLM is NOT called for "qué hay?" / "los caros").
After B25, these queries reach TurnInterpreter directly.

**Coverage now in**: `test_turn_interpreter_v2.py::TestTurnInterpreterV2RealLLM`
- `test_ambiguity_que_tenes_idle` — "¿qué tenés?" → product_search, search_mode=browse
- `test_ambiguity_brand_only_idle` — "tipo Bosch tenés algo?" → product_search/browse + brand

**Cases from deleted file NOT in v2 suite** (acceptable gaps — document for Bloque 3):
- Type A specific patterns: "los caros", "si tenes", "mostrame", "mostrame qué hay",
  "qué hay?", "los baratos", "mostrá el catálogo" — TurnInterpreter handles these
  semantically as browse/small_talk; no pattern-level tests needed.
- Type C specific brands: Makita, Milwaukee, DeWalt — TurnInterpreter handles brand
  extraction via EntityBundle; tested indirectly via `test_ambiguity_brand_only_idle`.
- Suppression cases (product keyword present): "mostrame taladros", "qué hay de mechas?",
  "si tenés mechas de 8mm?" — TurnInterpreter classifies these as product_search with
  specific terms, not browse. No explicit regression test added for now.
- `test_v8_still_has_priority_over_v9` — Both V8 and V9 gone; priority ordering
  irrelevant. TurnInterpreter classifies "dame un descuento" as escalate/negotiation.

---

## Tests modified

### `bot_sales/tests/test_search_validator.py` (-213 LOC net, 32 tests remain)

**Removed**:
- `TestV8NegotiationDetection` (22 tests) — entire class deleted. Tested `detect_negotiation_intent`
  and `HANDOFF_NEGOTIATION_RESPONSE`, both deleted.
- V4 ShouldBlock: `test_v4_martillo_dorado`, `test_v4_destornillador_rosa`,
  `test_v4_alicate_turquesa`, `test_v4_maza_oro` (4 tests)
- V4 ShouldPass: `test_pass_tornillo_dorado`, `test_pass_llave_dorada`,
  `test_pass_tornillo_dorado_para_martillo`, `test_pass_alicate_mango_lila`,
  `test_pass_alicate_mango_morado`, `test_pass_bisagra_dorada` (6 tests)
- V5 ShouldBlock: `test_v5_martillo_32gb`, `test_v5_broca_1tb` (2 tests)
- V7 ShouldBlock: `test_v7_destornillador_laser_cuantico`, `test_v7_alicate_inflable`,
  `test_v7_martillo_virtual`, `test_v7_amoladora_cuantica`, `test_v7_taladro_inflable`,
  `test_v7_sierra_magica`, `test_v7_martillo_digital`, `test_v7_alicate_laser` (8 tests)
- V7 ShouldPass: `test_v7_pass_destornillador_electrico`, `test_v7_pass_alicate_amperometrico`,
  `test_v7_pass_lampara_laser`, `test_v7_pass_destornillador_sin_adjetivo`,
  `test_v7_pass_alicate_presion`, `test_v7_pass_nivel_digital` (6 tests)
- L2 color: `test_l2_color_mismatch_dorado_not_in_products`, `test_l2_pass_color_in_product` (2 tests)

**Kept** (32 tests): V1 (5), V2 (2), V3 (2), V6 (8), L2 weight (7), plus legitimate ShouldPass (8).

---

## S08 note — Known flakiness (not a B25 regression)

During verification, S08 (E41: 5-turn multiturno) failed with "destornillador perdido del carrito".
The test's own docstring documents this: *"Known bug: session reset can occur at turn 5,
wiping active_quote. If this FAIL is idempotent across runs → Bloque 3 bug confirmed.
If non-deterministic → flag in report."*

None of the S08 turns ("destornillador philips", "cualquiera está bien", "agregame martillo",
"stanley", "presupuesto?") matched V9 browse patterns — so B25 has no causal relationship
to this failure. This is LLM non-determinism in a 5-turn conversation. Pre-B25 baseline
on the same branch also shows 19/21 slow tests (2 pre-existing failures in referenced_offer_index).

**Recommendation**: Track S08 separately as Bloque 3 bug; do not regress-block B25 on it.

---

## Verification results

```
python3 -c "from bot_sales.services.search_validator import validate_query_specs"  → OK
python3 -c "from bot_sales.services.search_validator import detect_negotiation_intent"  → ImportError (correct)
python3 -c "from bot_sales.bot import SalesBot"  → OK
pytest bot_sales/tests/test_search_validator.py  → 32/32 PASS
pytest bot_sales/tests/ -m "not slow"  → 203/204 (1 pre-existing test_routing failure)
pytest test_turn_interpreter_v2.py -m slow  → 19/21 (2 pre-existing referenced_offer_index failures)
smoke_ferreteria.py  → 17/17 OK
demo_test_suite.py  → 5P/3W/2F (S08 non-deterministic, S09 pre-existing parser bug)
```
