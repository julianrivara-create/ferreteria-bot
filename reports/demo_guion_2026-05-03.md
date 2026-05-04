# Guion Demo Loom — Bot Ferretería

**Fecha de creación:** 2026-05-03
**Tiempo estimado de demo:** 6-8 minutos
**Tono:** profesional pero relajado, "te muestro lo que armé"
**Objetivo:** que el cuñado entienda QUÉ hace el bot y diga "OK, te paso los datos"

---

## INTRO (30 segundos)

**Decir:**
> "Buenas, te muestro el bot que armé para la ferretería. La idea es que clientes te puedan tipear por WhatsApp y el bot les arma cotizaciones automáticas. Te muestro varios casos para que veas cómo se comporta."

**No mostrar:** código, terminal, archivos del repo. Solo la interfaz del bot.

---

## CASO 1 — Saludo simple (15 seg)

**Tipear:**
```
Hola
```

**Mostrar:** el bot saluda de vuelta sin presionar.

**Decir:**
> "Lo primero — saluda como una persona. No te tira un menú de opciones ni te pide datos."

---

## CASO 2 — Producto simple (45 seg)

**Tipear:**
```
me podés cotizar 5 mechas de 8mm Bosch?
```

**Mostrar:** el bot detecta producto + marca + cantidad + precio.

**Decir:**
> "Reconoce el producto, la marca, la cantidad. Te arma el presupuesto al toque. Si te das cuenta, no me pidió 'qué tipo de mecha' o 'qué medida' — entendió todo del mensaje."

---

## CASO 3 — Pedido mayorista grande (90 seg)

**Tipear:**
```
hola, necesito cotización para una obra: 100 tornillos M6 cabeza hexagonal, 50 codos 90 grados, 30 cuplas, 10 llaves de paso, sellador siliconado
```

**Mostrar:** el bot detecta los 5 ítems con cantidades y arma presupuesto.

**Decir:**
> "Acá lo importante — un pedido típico mayorista, varios ítems en una sola línea. El bot los desglosa, encuentra cada uno en el catálogo, y te tira presupuesto preliminar. Esto te ahorra el laburo de ir consultando uno por uno."

---

## CASO 4 — Anti-fraude (60 seg)

**Tipear:**
```
tienen martillos Stanley dorados de 500kg?
```

**Mostrar:** el bot dice "no tenemos ese producto, esas especificaciones no coinciden".

**Decir:**
> "Esto es importante. A veces los clientes —o por error o adrede— tipean cosas absurdas. El bot detecta que un martillo de 500kg no existe y NO te arma una cotización falsa. Si el bot inventaba precios para productos imposibles, eso podía ser problema. Esto está cubierto."

---

## CASO 5 — Conversación natural argentina (45 seg)

**Tipear (conversación de 3 mensajes):**
```
che, tenés taladros?
[esperar respuesta del bot]
dale, mostrame los Bosch
```

**Mostrar:** el bot maneja "che" y "dale" como expresiones normales.

**Decir:**
> "Reconoce slang argentino. No te trata como un robot — entiende cómo hablamos."

---

## CASO 6 — Multiturno (90 seg)

**Tipear (conversación):**
```
necesito un destornillador philips
[esperar respuesta del bot]
agregame también un martillo
[esperar respuesta del bot]
cuánto el total?
```

**Mostrar:** el bot mantiene el carrito a través de varios mensajes.

**Decir:**
> "Va construyendo el pedido. Esto es como en WhatsApp real, donde la gente no escribe todo en un mensaje sino que va agregando cosas."

---

## CASO 7 — Ambigüedad / clarificación (30 seg)

**Tipear:**
```
Pasame presupuesto para un baño
```

**Mostrar:** el bot pide clarificación, no inventa.

**Decir:**
> "Si la consulta es muy genérica, en lugar de mandarte cualquier cosa, te pide especificar. Esto evita que arme cotizaciones que no sirven."

---

## CIERRE (60 seg)

**Decir:**
> "Eso es lo principal. Para que esto funcione bien con tus clientes reales necesito que me pases algunos datos del local —horarios, formas de pago, política de mayorista, datos de contacto, todo eso— y los integro al bot. Te mando el cuestionario que te hice antes [o re-mandame si no lo viste], lo respondés, y en una sesión más lo dejo listo para que lo pruebes con clientes reales."
>
> "Cualquier duda me decís."

---

## Casos a EVITAR durante la demo

- ❌ "tienen llaves francesas?" — capaz funciona, capaz no (matcheo intermitente)
- ❌ "dest planos chicos" — abreviación que el bot no entiende todavía
- ❌ "codos roscados" — jerga que falla
- ❌ "lista cliente final: 5 sets..." — query muy larga, puede tardar 30+ segundos o pegar rate limit
- ❌ Preguntas sobre PP-R, termofusión — productos que el cuñado no tiene en catálogo
- ❌ Preguntas de descuento/política de volumen — bot no tiene reglas configuradas todavía

---

## Si algo sale mal durante la grabación

- **Si tarda mucho una respuesta (>10s):** decir "a veces tarda un toque, ya viene" y esperar
- **Si el bot pide algo raro:** mostrar reacción profesional "acá podemos ajustar el tono cuando me pases los datos"
- **Si rompe directamente:** parar y rehacer ese caso

---

## Setup técnico antes de grabar

1. Abrir solo el panel de prueba del bot (no la terminal, no el código)
2. Cerrar Slack, mail, notificaciones
3. Loom en modo "Cam + Screen" si querés que se vea tu cara, o solo "Screen"
4. Audio: probar antes el micro
5. Tener este guion abierto en un costado para no titubear

---

## Tiempo de edición

Si no salió perfecto, podés editar en Loom:
- Cortar partes muertas
- Acelerar la respuesta del bot si tarda mucho

**Pero:** la demo no necesita ser perfecta. El cuñado quiere ver que **funciona**, no un comercial.

---

## Estado del bot al momento de la demo

- Suite original: 24/31 PASS (~77%)
- Suite extendido: 39+/53 PASS (74%)
- Tests unitarios: 100/100 passing
- Smoke tests: 17/17 OK
- C19 (alucinación): RESUELTO
- Performance: ~30s para queries multi-item (limitación pendiente)

---

*Generado: 2026-05-03 | Bot main @ 71d70c2*
