# Audit V2 — Datos del cliente

**HEAD:** 9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb
**Fecha:** 2026-05-09

---

## Resumen ejecutivo

- **9 campos con placeholders `[PENDIENTE-X]`** en `profile.yaml` — datos de contacto, horarios, pagos, envíos y nombre comercial.
- **1 número sintético** en `communication.whatsapp_numbers` (`+5493333333333`) que también aparece en `tenants.yaml`.
- **`training.personality` y `training.objective` vacíos** (`""`).
- **`hold_minutes` es placeholder** — discrepancia entre `policies.md` (45 min) y `config/policies.md` (24h hábiles) no resuelta.
- **`knowledge/faqs.yaml`**: horario hardcodeado (08:00–18:00 L-V, 08:30–13:00 S) — puede ser real o ficticio; necesita confirmación del cliente.
- **`config/faqs.json`**: datos genéricos / divergentes del `faqs.yaml` (zonas geográficas CABA/AMBA/Interior que no fueron confirmadas, cuotas MercadoPago sin confirmar).
- **`branding.json`**: contiene nombre comercial `"Ferreteria Central"` — no confirmado.
- **Bloqueantes de producción del lado del cliente**: 14 ítems de datos sin respuesta del cuñado (Nacho).
- **Bloqueantes de producción del lado técnico**: 3 bugs críticos de código (TurnInterpreter, pérdida de contexto multiturno, parser de conectores) independientes de los datos del cliente.

---

## 1. profile.yaml — estado campo por campo

| Sección | Campo | Valor actual | Estado |
|---|---|---|---|
| raíz | `id` | `ferreteria` | COMPLETO |
| raíz | `slug` | `ferreteria` | COMPLETO |
| raíz | `bot_name` | `"Ferretero"` | COMPLETO |
| business | `name` | `"Ferretería"` + comment `# TODO confirmar nombre comercial [PENDIENTE-NOMBRE-COMERCIAL]` | PLACEHOLDER |
| business | `description` | Herramientas, fijaciones, pinturería y soluciones para obra, taller y hogar. | COMPLETO |
| business | `industry` | `ferreteria` | COMPLETO |
| business | `language` | `es` | COMPLETO |
| business | `currency` | `ARS` | COMPLETO |
| business | `country` | `AR` | COMPLETO |
| business | `tone` | asesor comercial argentino, cercano, vendedor consultivo... | COMPLETO |
| business | `target_audience` | clientes de hogar, mantenimiento y obra | COMPLETO |
| business | `visible_categories` | 13 categorías listadas | COMPLETO |
| personality | `tone` | Argentino informal con vos/che/dale... | COMPLETO |
| personality | `emojis` | 🔧 🔩 💳 ✅ 🚚 | COMPLETO |
| contact | `phone` | `"[PENDIENTE-TEL]"` | PLACEHOLDER |
| contact | `whatsapp` | `"[PENDIENTE-TEL]"` | PLACEHOLDER |
| contact | `address` | `"[PENDIENTE-DIRECCION]"` | PLACEHOLDER |
| contact | `city` | `"[PENDIENTE - ciudad/barrio]"` | PLACEHOLDER |
| contact | `maps_url` | `"[PENDIENTE - link Google Maps]"` | PLACEHOLDER |
| hours | `weekdays` | `"[PENDIENTE-HORARIO]"` | PLACEHOLDER |
| hours | `saturday` | `"[PENDIENTE-HORARIO]"` | PLACEHOLDER |
| hours | `sunday` | `"[PENDIENTE-HORARIO]"` | PLACEHOLDER |
| hours | `holiday_note` | `"[PENDIENTE - feriados/excepciones]"` | PLACEHOLDER |
| payment | `methods` | `["[PENDIENTE-MEDIOS-DE-PAGO]"]` | PLACEHOLDER |
| payment | `installments` | `"[PENDIENTE - cuotas disponibles o sin interés]"` | PLACEHOLDER |
| payment | `wholesale_min_order` | `"[PENDIENTE - monto mínimo compra mayorista]"` | PLACEHOLDER |
| payment | `account_credit` | `"[PENDIENTE - condiciones de cuenta corriente]"` | PLACEHOLDER |
| shipping | `zones` | `"[PENDIENTE - zonas de envío cubiertas]"` | PLACEHOLDER |
| shipping | `lead_time` | `"[PENDIENTE - plazo de entrega habitual]"` | PLACEHOLDER |
| shipping | `free_shipping_threshold` | `"[PENDIENTE - monto mínimo para envío gratis si aplica]"` | PLACEHOLDER |
| communication | `whatsapp_numbers[0]` | `whatsapp:+5493333333333` | SINTÉTICO |
| comparison_features | — | category, proveedor, price_ars, sku | COMPLETO |
| cross_sell_rules | — | 5 reglas de categorías | COMPLETO |
| raíz | `hold_minutes` | `"[PENDIENTE - confirmar con cliente: 45 min vs 24h]"` | PLACEHOLDER |
| features | `enable_upselling` | `true` | COMPLETO |
| features | `enable_crossselling` | `true` | COMPLETO |
| features | `enable_bundles` | `true` | COMPLETO |
| required_reservation_fields | — | nombre, contacto | COMPLETO |
| validation | `placeholder_names` | lista de 7 nombres | COMPLETO |
| validation | `placeholder_phones` | lista de 3 patrones | COMPLETO |
| validation | `placeholder_emails` | lista de 4 patrones | COMPLETO |
| training | `personality` | `""` | VACÍO |
| training | `objective` | `""` | VACÍO |
| paths | `db` | `data/ferreteria.db` | COMPLETO |
| paths | `catalog` | `data/tenants/ferreteria/catalog.csv` | COMPLETO |
| paths | `policies` | `data/tenants/ferreteria/policies.md` | COMPLETO |
| paths | `branding` | `data/tenants/ferreteria/branding.json` | COMPLETO |

**Resumen profile.yaml:** 14 campos PLACEHOLDER, 1 SINTÉTICO, 2 VACÍO, el resto COMPLETO.

---

## 2. knowledge/*.yaml — uno por uno

### acceptance_patterns.yaml
**Estado: COMPLETO.**
Contiene patrones de aceptación (`accept_phrases`), reset (`reset_phrases`), merge (`merge_phrases`) y nuevo presupuesto (`new_quote_phrases`) bien cubiertos. Slang argentino correctamente incluido ("dale", "che", "avancemos", etc.). Sin placeholders ni TODOs. Sin dependencia de datos del cliente.

### blocked_terms.yaml
**Estado: MÍNIMO pero funcional.**
Solo tiene una entrada: `herramienta` bloqueada por "demasiado amplio". Esto es intencional — el archivo es muy escueto. No es un problema para producción, pero el cliente podría ampliar si hay términos problemáticos específicos de su negocio (ej: marcas que no vende, términos que no quiere que el bot responda).

### category_aliases.yaml
**Estado: COMPLETO pero con inconsistencia.**
Mapea aliases comunes a categorías canónicas. Problema: varios aliases mapean a categorías que no coinciden exactamente con las de `profile.yaml.visible_categories`. Por ejemplo:
- `martillo` → `"Martillos"` (no está en visible_categories)
- `destornillador` → `"Destornilladores"` (no está en visible_categories)
- `tornillo` → `"Bulonería"` (no está en visible_categories)
- `silicona`, `sellador`, `teflon`, `cano`, `conexion` → `"Sanitaria"` (no está en visible_categories)

Esto es técnico, no datos del cliente. Sin placeholders.

### clarification_rules.yaml
**Estado: COMPLETO — pero desconectado del código.**
Reglas bien definidas para pedir clarificación (tornillo, mecha, broca, caño, pintura, silicona, cable, rodillo, tarugo, taco, latex). Sin placeholders. **Problema conocido documentado en PENDIENTES.md**: el archivo existe pero ningún interceptor lo lee actualmente. No es falta de datos del cliente — es deuda técnica.

### complementary_rules.yaml
**Estado: COMPLETO.**
Define qué productos complementar cuando el cliente elige uno (silicona → pistola, pintura → rodillo/pincel/bandeja, taladro → mecha/broca, etc.). Sin placeholders ni dependencia de datos del cliente.

### family_rules.yaml
**Estado: COMPLETO con 2 familias sin productos en catálogo.**
20 familias de productos definidas y verificadas. Dos familias con `allowed_categories: []` intencionales:
- `niple`: sin productos en catálogo (0 matches verificados 2026-05-04). **Pregunta pendiente para cliente: ¿lo vende o no?**
- `ramal`: ídem. **Pregunta pendiente para cliente: ¿lo vende o no?**

El knowledge loader filtra silenciosamente estas dos entradas — comportamiento seguro documentado.

### faqs.yaml
**Estado: COMPLETO con datos hardcodeados que necesitan confirmación.**
7 entradas: envíos, pagos, facturación, cambios, garantía, horario.

Datos hardcodeados que PUEDEN SER REALES o NO:
- **Horario**: "lunes a viernes de 8:00 a 18:00 y los sábados de 8:30 a 13:00" — ¿es el horario real del local?
- **Envíos**: "24 a 72 horas hábiles según zona" — ¿es el plazo real?
- **Pagos**: "efectivo, transferencia, MercadoPago y tarjetas" — ¿están todos los medios?
- **Cambios**: "10 días corridos con ticket o factura" — ¿es la política real?

Si el `profile.yaml` sigue con `[PENDIENTE-HORARIO]` pero `faqs.yaml` tiene el horario hardcodeado, hay **inconsistencia potencial** si el cliente da un horario diferente al preguntar.

### item_family_map.yaml
**Estado: COMPLETO con categorías divergentes respecto a family_rules.yaml.**
Este archivo usa categorías escritas con tildes y nombres ligeramente distintos a `family_rules.yaml`:
- `mecha/broca` → `"Mechas y Brocas"` (aquí) vs `"Herramientas Electricas"` (en family_rules.yaml)
- `silicona/sellador/teflon/cano` → `"Plomería"` (aquí) vs categorías reales del catálogo (en family_rules.yaml)
- `guante` → `"Seguridad"` (aquí) vs `"Bocallaves y Dados", "Pinturas", "Varios"` (en family_rules.yaml)
- `cable` → `"Electricidad"` (aquí) vs `"Pinzas y Alicates", "Sujeción", "Varios"` (en family_rules.yaml)

Esta divergencia es deuda técnica, no datos del cliente. Sin placeholders.

### language_patterns.yaml
**Estado: COMPLETO.**
Maneja errores ortográficos (teflón, fischer, látex), términos regionales (caño, brocas, drywall/durlock), marcas genéricas (fisher/fischer → taco fisher), abreviaturas (int, ext, sanit), aliases de superficies y patrones de dimensiones. Sin placeholders ni dependencia de datos del cliente.

### substitute_rules.yaml
**Estado: COMPLETO.**
4 grupos de reglas de sustitución (mechas, brocas, tornillos, tarugos/tacos). Sin placeholders. No depende de datos del cliente.

### synonyms.yaml
**Estado: COMPLETO.**
28 entradas canónicas con aliases. Cubre productos principales del catálogo. Sin placeholders. Una familia referenciada (`electrovalvula`) fue eliminada de `family_rules.yaml` por no tener productos — la entrada en synonyms.yaml permanece inocua.

---

## 3. policies.md — config/ vs data/tenants/ferreteria/

**Son archivos DISTINTOS con roles distintos. No deben "coincidir" — pero hay divergencias problemáticas.**

### `data/tenants/ferreteria/policies.md` (versión tenant — la que usa el bot)
Documento operativo específico para la ferretería. Incluye:
- Horarios hardcodeados: L-V 8:00–18:00, Sáb 8:30–13:00
- **Reservas: 45 minutos** desde confirmación de datos
- Pagos: efectivo, transferencia, MercadoPago y tarjetas
- Envío en moto dentro de zona cercana en el día o 24h hábiles
- Despachos al interior 24–72h hábiles
- Cambios: 10 días corridos con ticket/factura
- No inventar medidas, rendimientos, compatibilidades

### `config/policies.md` (versión genérica / legacy)
Documento más amplio de estilo chatbot. Incluye:
- Identidad: "vendedor especializado en ferretería"
- Marcas mencionadas explícitamente: Knipex, Bondhus, Dewalt, Stanley, BREMEN, WEMBLEY, Fischer, Makita, Bosch
- **Reservas: 24 horas hábiles** (distinto de los 45 min del tenant)
- Tarjeta crédito: "consultar recargo vigente" (más precavido que la versión tenant)
- Secciones de estilo de respuesta y casos de handoff

### Discrepancias críticas

| Punto | `data/tenants/ferreteria/policies.md` | `config/policies.md` |
|---|---|---|
| Duración de reserva | **45 minutos** | **24 horas hábiles** |
| Tarjeta crédito | No mencionado | "consultar recargo vigente" |
| Marcas explícitas | No listadas | Knipex, Dewalt, Stanley, etc. |
| Tono/estilo | No incluido | Incluido |

**Recomendación:** El bot usa `data/tenants/ferreteria/policies.md`. La duración de reserva debe ser confirmada por el cliente (Nacho) y reflejada de forma consistente en `profile.yaml.hold_minutes` y en la policies del tenant. `config/policies.md` parece ser un legacy de configuración global; si el bot lo ignora en producción, puede quedar como referencia desactualizada.

---

## 4. faqs.yaml / faqs.json

### `knowledge/faqs.yaml` (el que usa el bot)
7 entradas con horarios, pagos, facturación, cambios, garantía, horario de atención. **Ver sección 2 arriba.** Datos hardcodeados que necesitan confirmación del cliente.

### `config/faqs.json` (legacy / no usado directamente)
12 entradas. Formato distinto (JSON vs YAML). Contenido divergente:
- **Zonas geográficas específicas**: CABA (moto gratis 24-48h), AMBA (48-72h), Interior (Correo/Andreani 3-5 días) — nunca confirmadas con el cliente. Probablemente genéricas/de plantilla.
- **Cuotas**: 3 cuotas sin interés, 6/12 con interés vía MercadoPago — no confirmadas.
- **Entrega gratis en CABA** — no confirmada.
- **Productos originales / sin usados** — entradas genéricas que no son propias de una ferretería.
- Metadata: `"last_updated": "2026-01-21"` — fecha anterior a toda la sesión de trabajo, indica que es una plantilla sin actualizar.

**Estado:** `config/faqs.json` contiene datos SINTÉTICOS/de plantilla no confirmados. Si el bot llega a leerlo, presentará información incorrecta a los clientes. Necesita revisión antes de producción.

**Duplicación:** Hay solapamiento temático (envíos, garantía, pagos, devoluciones) entre ambos archivos pero con contenido divergente.

---

## 5. branding.json

| Campo | Valor | Estado |
|---|---|---|
| `brand_name` | `"Ferreteria Central"` | NO CONFIRMADO — posiblemente sintético |
| `tagline` | `"Herramientas y materiales para obra y hogar"` | Genérico — no confirmado |
| `hero_title` | `"Ferreteria Central"` | Repite brand_name — no confirmado |
| `hero_subtitle` | `"Bot de ventas por CLI y WhatsApp, sin frontend web"` | Descripción técnica, no comercial — **claramente placeholder** |
| `accent_color` | `"#b45309"` | Color naranja-ámbar genérico — no confirmado |
| `secondary_color` | `"#1f2937"` | Gris oscuro genérico — no confirmado |
| `currency_symbol` | `"$"` | COMPLETO |

**Estado general:** El `hero_subtitle` es directamente un texto técnico de desarrollo, no un tagline comercial. `brand_name` y `tagline` son genéricos. Sin logo definido. Todo lo visual-comercial necesita input del cliente.

---

## 6. data/tenants/ferreteria/PENDIENTES.md — resumen

Archivo de 733 líneas. Última actualización: 2026-05-04. Es el changelog técnico del proyecto.

### Situación general documentada en el archivo:
- **El cliente (cuñado/Nacho) no respondió los cuestionarios** — está documentado explícitamente en múltiples secciones.
- El bot NO está en producción (Railway pendiente).
- Sesión 2026-05-04 fue la más reciente: 22+ commits, 276/277 tests pasando.

### Lo que está RESUELTO (del lado técnico):
- Bug crítico del matcher base (D1–D6)
- Anti-alucinación de precios R1 (precio inventado desde budget eliminado)
- R2 (validación post-LLM, modo log-only)
- R3 (refresh de precios stale en multiturno)
- Performance multi-item (~25s → ~2.6s)
- Safe alternatives fallback
- Anti-alucinación de specs (V1–V9: pesos, diámetros, watts, adjetivos imposibles)

### Lo que está PENDIENTE (del lado técnico):
- **3 bugs críticos** descubiertos en testing manual EOD:
  1. TurnInterpreter clasifica mal intent (quote_modify cuando debería ser quote_build o project_request)
  2. Pérdida de contexto + alucinación de stock en multiturno ("no está disponible" cuando stock=999)
  3. Parser multi-item splittea conectores ("dale" tratado como ítem de producto)
- clarification_rules.yaml desconectado del código
- R2 modo log-only → necesita escalarse a corrección inline o handoff
- Cierre multiturno E41-E43 (sesión reset en turno 5)

### Lo que está PENDIENTE (del lado del cliente):
- Todos los campos `[PENDIENTE-X]` de profile.yaml
- Confirmación de niple y ramal (¿vende o no?)
- Confirmación de caños PP-R (¿vende o no?)
- Confirmación de hold_minutes (45 min vs 24h)
- Confirmación de nombre comercial ("Ferreteria Central" — ¿correcto?)

---

## 7. tenants.yaml + multi-tenant

### tenants.yaml (raíz)
Registra 4 tenants:

| id | name | Número WhatsApp | Notas |
|---|---|---|---|
| `default_tenant` | Default Store | `+14155238886` (Twilio sandbox) | Demo/sandbox |
| `farmacia` | Farmacia Demo | `+5491111111111` | Demo |
| `ropa` | Ropa Demo | `+5492222222222` | Demo |
| `ferreteria` | Ferreteria Central | `+5493333333333` | **NÚMERO SINTÉTICO** |

**Problemas en la entrada `ferreteria`:**
- `phone_numbers[0]`: `whatsapp:+5493333333333` — número de prueba, debe ser reemplazado por el número real de WhatsApp Business del cliente.
- `name`: `"Ferreteria Central"` — sin confirmar con cliente.
- `whatsapp_phone_number_id`: `${FERRETERIA_WHATSAPP_PHONE_NUMBER_ID}` — variable de entorno, correcta (depende del cliente proveer el Phone Number ID real de Meta/WhatsApp Business).
- `admin_phone_number_id`: `${FERRETERIA_ADMIN_PHONE_ID}` — ídem.
- Rutas de archivos apuntan correctamente a `data/tenants/ferreteria/`.
- API keys via `${OPENAI_API_KEY}` y `${GEMINI_API_KEY}` — correctas (variables de entorno).

**Los otros 3 tenants** (default, farmacia, ropa) son demos/plantillas. No representan clientes reales. No tienen impacto en la ferretería.

### tenants/atelier.yaml
Es un archivo de **monitoreo de infraestructura Railway** para un proyecto diferente (Atelier), no un tenant del bot de ferretería. Contiene IDs de proyecto/servicio de Railway, configuración de watchdog, alertas, checks de salud. No tiene relación con los datos del cliente de la ferretería. Se puede ignorar para esta auditoría.

---

## 8. Cuestionario final para Nacho

### Sesión 1 (~15 min): Datos básicos del negocio — BLOQUEANTE

Estos datos hacen que el bot muestre `[PENDIENTE-X]` a clientes reales. Sin ellos, no puede salir a producción.

**1. ¿Cuál es el nombre comercial completo del local?**
_(Hoy dice "Ferreteria Central" como placeholder. ¿Es correcto? ¿Hay razón social diferente?)_
→ BLOQUEANTE

**2. ¿Cuál es el teléfono / WhatsApp real del local?**
_(El número de WhatsApp Business que recibirá los mensajes de los clientes)_
→ BLOQUEANTE

**3. ¿Cuál es la dirección física del local?**
_(Calle, número, barrio/ciudad)_
→ BLOQUEANTE

**4. ¿Tienen link de Google Maps? ¿O lo generamos con la dirección?**
→ BLOQUEANTE

**5. ¿Cuál es el horario de atención?**
- Lunes a viernes: ¿de qué hora a qué hora?
- Sábados: ¿atienden? ¿de qué hora a qué hora?
- Domingos: ¿atienden?
- Feriados: ¿atienden / reducido / cerrado?

_(El bot ya tiene hardcodeado L-V 8:00–18:00 y Sáb 8:30–13:00 — ¿es correcto ese horario?)_
→ BLOQUEANTE

---

### Sesión 2 (~15 min): Pagos, envíos y política de reservas — IMPORTANTE

**6. ¿Qué medios de pago aceptan?**
Marcar los que aplican:
- [ ] Efectivo
- [ ] Transferencia bancaria (¿sin recargo?)
- [ ] MercadoPago (¿link de pago?)
- [ ] Tarjeta débito (¿sin recargo?)
- [ ] Tarjeta crédito (¿con recargo? ¿cuánto?)
- [ ] Naranja X / Naranja
- [ ] Cheque
- [ ] Otro: _______________
→ BLOQUEANTE

**7. ¿Ofrecen cuotas? ¿Con o sin interés? ¿Cuántas cuotas? ¿Con qué tarjetas?**
_(El config/faqs.json dice "3 sin interés, 6/12 con interés vía MercadoPago" — ¿es correcto?)_
→ BLOQUEANTE

**8. ¿Cuánto tiempo dura una reserva?**
Hay una contradicción en el sistema:
- `policies.md` del bot dice: **45 minutos**
- El archivo de configuración general dice: **24 horas hábiles**
¿Cuál es el tiempo real que quieren dar a los clientes?
→ BLOQUEANTE

**9. ¿Hacen envíos? ¿A qué zonas?**
- ¿Solo zona cercana al local? ¿En qué radio o barrios?
- ¿Hacen envíos al interior / correo?
- ¿Cuál es el plazo habitual de entrega?
- ¿Hay envío gratis a partir de cierto monto?
_(El faqs.json genérico dice CABA/AMBA/Interior — ¿aplica eso a su negocio?)_
→ BLOQUEANTE

**10. ¿Tienen condiciones mayoristas? ¿Monto mínimo para precio mayorista?**
→ IMPORTANTE

**11. ¿Otorgan cuenta corriente? ¿Bajo qué condiciones?**
→ IMPORTANTE

---

### Sesión 3 (~15 min): Catálogo, identidad y ajuste fino — NICE_TO_HAVE / IMPORTANTE

**12. ¿Venden niples y ramales? (accesorios de plomería)**
El catálogo no tiene productos con esos nombres. Si los venden, hay que cargarlos.
Si no los venden, se cierra la pregunta y el bot responde correctamente que no los tiene.
→ IMPORTANTE

**13. ¿Venden caños PP-R (termofusión)?**
El catálogo tiene accesorios/boquillas PP-R pero no los caños en sí.
→ IMPORTANTE

**14. ¿Las 7 llaves esféricas que están en la categoría "General" pertenecen a Plomería?**
_(Llave esférica 1/2", 3/4", 20mm, 25mm, llave para gas)_
Si las movemos a Plomería el bot las encuentra mejor cuando el cliente pregunta por plomería.
→ NICE_TO_HAVE

**15. ¿Tienen slogan o frase comercial del local?**
_(El tagline actual "Herramientas y materiales para obra y hogar" es genérico)_
→ NICE_TO_HAVE

**16. ¿Tienen logo o colores del local?**
_(Hoy el bot usa naranja #b45309 genérico)_
→ NICE_TO_HAVE

**17. ¿Hay algo que el bot no debería decir o términos que no usan en el local?**
_(ej: marcas que no venden, términos que no usan)_
→ NICE_TO_HAVE

**18. ¿Cuántos años llevan en el mercado? ¿Tienen alguna especialidad fuerte?**
_(Para que el bot pueda mencionar eso si el cliente pregunta sobre el negocio)_
→ NICE_TO_HAVE

---

## 9. Bloqueantes para producción

Sin los siguientes datos/fixes el bot NO puede salir a clientes reales:

### Del cliente (Nacho):
1. **Nombre comercial real** — aparece como "Ferretería" (placeholder) o "Ferreteria Central" (no confirmado)
2. **Teléfono / WhatsApp real** — hoy es `+5493333333333` (sintético)
3. **Dirección física**
4. **Link Google Maps**
5. **Horario de atención completo** (confirmar o corregir L-V 8–18 / S 8:30–13)
6. **Medios de pago reales** (incluyendo política de cuotas y recargos)
7. **Duración de reserva** — resolver contradicción 45 min vs 24h
8. **Zonas de envío y plazos**

### Del lado técnico (Julian / próxima sesión):
9. **Bug TurnInterpreter** — clasifica mal cotizaciones nuevas como modificaciones → respuestas incorrectas o crash
10. **Bug pérdida de contexto + alucinación de stock en multiturno** — bot dice "no disponible" con stock=999
11. **Bug parser de conectores** — "dale, mostrame los Bosch" se rompe en 2 items vacíos
12. **WhatsApp Phone Number ID real** — variable `FERRETERIA_WHATSAPP_PHONE_NUMBER_ID` debe ser configurada con el ID real de Meta Business

---

## 10. Dudas para Julian

1. **`config/policies.md` vs `data/tenants/ferreteria/policies.md`**: ¿el bot en producción lee `config/policies.md`? Si es así, hay contradicción en duración de reservas (24h vs 45 min). Si no lo lee, ¿se puede descartar o archivar para evitar confusión?

2. **`config/faqs.json`**: ¿el bot en producción carga este archivo? Tiene zonas geográficas (CABA/AMBA/Interior) y cuotas MercadoPago que nunca fueron confirmadas con el cliente. Si el bot lo lee, está mintiendo a los clientes sobre política de envíos y cuotas.

3. **`training.personality` y `training.objective` vacíos en profile.yaml**: ¿el sistema los usa? ¿Hay un fallback, o queda un hueco en el prompt del bot?

4. **`item_family_map.yaml` diverge de `family_rules.yaml`** en las categorías reales (mecha→"Mechas y Brocas" vs "Herramientas Electricas", guante→"Seguridad" vs "Varios", cable→"Electricidad" vs "Sujeción"). ¿Cuál tiene prioridad en el sistema de matching? ¿Hay riesgo de que el mapa viejo pise las correcciones del D1?

5. **`tenants/atelier.yaml`** está en el mismo repo. ¿Es correcto que las credenciales de monitoreo de Railway de Atelier vivan aquí, o deberían estar en otro repo? (Solo una pregunta de higiene de repo.)

6. **Worktrees mergeados (D1–D6)**: PENDIENTES.md documenta 6 worktrees para cleanup. ¿Se hizo? `git worktree list` puede confirmarlo. Si no, el cleanup sigue pendiente.

7. **R2 en modo log-only**: el price_validator detecta alucinaciones pero no modifica la respuesta. ¿Cuándo se sube a modo "correción inline" o "handoff"? Depende de datos de producción que todavía no existen — ¿se decide que log-only es aceptable para la primera semana en producción?

8. **clarification_rules.yaml**: el archivo está completo pero desconectado. ¿Se conecta antes del lanzamiento o se deja como backlog post-MVP?
