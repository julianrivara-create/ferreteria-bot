# PENDIENTES — follow-up items

## B23-FU ✅ CERRADO (commit e79de10, 2026-05-05)

S08 WARN→PASS. Tres fixes aplicados:
1. `detect_option_selection`: frases genéricas ("cualquiera", "me da igual") → index 0
2. `apply_followup_to_open_quote`: param `ti_ref_idx` + gate para 1 item pendiente
3. `classify_followup_message`: strip trailing punctuation en `_FRESH_REQUEST_WORDS` check
   ("presupuesto?" ya no se clasifica como followup → llega a seccion 4 → muestra quote parcial)

Suite C: S08 ✅ PASS × 3/3 runs post-fix.
