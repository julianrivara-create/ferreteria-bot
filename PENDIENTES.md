# PENDIENTES — follow-up items

**Última actualización:** 2026-05-05
**Estado del bot:** main @ 0ed22a5 (refactor LLM-first 7/7 cerrado)
**Producción:** NO en Railway todavía
**Suite C strict:** 8P/2W/0F estable × 3 corridas

---

## 🔴 BUGS DETECTADOS EN TESTING MANUAL (post-refactor)

### Bug 1 — Compound modify+accept se pierde (CRÍTICO)

**Estado:** diagnosticado, plan listo
**Reproducción:**
```
T1: "necesito destornillador philips"        → bot ofrece A/B/C
T2: "la opcion a. Te pido también martillo"  → resuelve + agrega ✓
T3: "la opcion 2 del martillo. cuanto es el total?" → ❌ pierde
T4: "hoy te lo retiro por el local"          → ❌ loop pidiendo datos
```
**Causa:** post-T2 el bot queda en `awaiting_customer_confirmation` y procesa todo como confirmación, no como nueva instrucción.
**Plan:** B22c-medio. Extender `_process_compound_mixed` para `quote_modify` global. ~1-2h.

---

### Bug 2 — Templates de respuesta muy robóticos

**Estado:** diagnosticado, plan claro
**Reproducción:** respuestas con markdown (`**SKU:**`, `- **Modelo:**`) que en WhatsApp se ven horrible.
**Plan:** refactor de templates en `bot_sales/templates/quote_response.j2`. Formato natural, sin bullets. ~1h.

---

### Bug 3 — Frases hardcoded de cierre fuera de contexto

**Estado:** rastreo pendiente
**Reproducción:** bot dispara "Para cotizarte exacto y avanzar hoy: ¿Lo necesitás hoy...?" fuera de contexto.
**Plan:** `grep "Para cotizarte exacto"` → identificar path → contextualizar o eliminar. ~30 min.

---

### Bug 4 — apply_clarification no resuelve ítem pendiente

**Estado:** diagnosticado, plan medio
**Reproducción:**
```
T1: "5 mechas 8mm Bosch?"     → bot pregunta material
T2: "Para madera, por favor"  → ❌ devuelve "Trampa laucha madera"
```
**Plan:** priorizar resolución del pendiente cuando hay ítem ambiguo abierto y el mensaje es corto + descriptivo. ~1-2h.

---

### Bug 5 — UX general muy "asistente IA", poco humano

**Estado:** observación, baja urgencia
**Causa:** emojis 🛠️, frases largas, formalidad excesiva. No suena a vendedor argentino.
**Plan:** pasada por templates, sacar emojis, tono coloquial. ~2-3h.
