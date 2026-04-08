# Acceptance Tests – Ferretería Sales Bot 2.0

> Regla: No se acepta “Done” hasta que TODOS los checks de esta lista estén OK.
> Si algo no aplica por falta de feature, se marca como “Not Implemented” y se crea task para implementarlo.

---

## A) PDP (product.html)

- [ ] Si `?model=` no existe en DB → se muestra mensaje “No disponible” (no rompe la página).
- [ ] Si el modelo existe → se renderiza nombre, imagen(es), precio base.
- [ ] Cambiar color/storage/condición/edición dispara `select_variant` y actualiza precio visible al instante.
- [ ] Precio visible coincide con backend (no se calcula con `specs.json`).
- [ ] “Comprar Ahora” genera/obtiene `order_id` y abre chat con selección exacta + `order_id`.

---

## B) Home (index.html)

- [ ] Botón “Comprar Ahora” hace scroll suave y posiciona correctamente en productos.
- [ ] Botón “Ver Video” abre modal (no redirige) y se puede cerrar fácil en móvil.
- [ ] Links de categorías navegan/scroll a sección correcta.
- [ ] “Contacto” abre chat con mensaje precargado “Hola, necesito soporte”.
- [ ] “Garantía” abre `legal.html` o modal sin links rotos.
- [ ] Cards uniformes (alto consistente) y layout estable en mobile.

---

## C) Analytics Events & Order ID

- [ ] Eventos canónicos existen: `view_item`, `select_variant`, `click_buy_now`, `purchase_intent`, `payment_pending`, `paid`, `fulfilled`.
- [ ] “Conversión real” en dashboard usa `paid / view_item`.
- [ ] `paid` siempre incluye `order_id`.
- [ ] `click_buy_now` incluye `order_id`.
- [ ] `purchase_intent` incluye `order_id`.
- [ ] No se emite `paid` si el `order_id` no existe en DB (o está cancelado, si aplica).
- [ ] No se emite `paid` antes de `purchase_intent` (si ese es tu flujo definido).
- [ ] El feed “Venta confirmada” se muestra únicamente cuando ocurre `paid`.

---

## D) API `/api/analytics/track`

- [ ] Rate limit activo (no permite spam de eventos).
- [ ] Schema validation: payload inválido devuelve error (no se traga basura).
- [ ] Sanitización: strings con caracteres raros no rompen logs ni dashboard.
- [ ] Rechazo por faltantes: si el evento requiere `order_id` y no viene → 4xx.
- [ ] Rechazo por inconsistencias: eventos fuera de transición permitida → 4xx.

---

## E) Open Graph / Share (WhatsApp)

- [ ] Compartir una PDP muestra imagen + nombre + (precio si corresponde) en preview.
- [ ] OG se genera server-side (SSR o prerender); no depende de JS del browser.

---

## F) Bot: Anti-alucinación

- [ ] Si un producto no existe en DB → el bot responde “No lo tenemos disponible actualmente.” (sin inventar alternativas falsas).
- [ ] El bot nunca ofrece “disponible” un modelo fuera del catálogo.
- [ ] El bot no inventa variantes o precios.

---

## G) Bot: Advisor Mode (Comparaciones)

- [ ] Si detecta intención “vs/comparar/diferencia/mejor” → responde primero comparación técnica con `specs.json`.
- [ ] Luego traduce a beneficios (“qué significa para vos”), y recién después stock/precio.
- [ ] Si no hay stock → igualmente compara y aclara “no disponible para compra”.

---

## H) Bot: Ambigüedad y Contexto

- [ ] Si el bot listó opciones y el usuario dice “el último” → selecciona la última opción listada.
- [ ] Si el usuario dice “ese” / “el más nuevo” sin claridad → pregunta “¿A cuál te referís?”.
- [ ] El bot no pide teléfono ni valida datos hasta confirmar Modelo + Color + Variante.
- [ ] Prohibido “Número inválido” si el usuario no escribió un número.

---

## I) Zero-Waste AI

- [ ] El saludo inicial ocurre en frontend (sin usar LLM).
- [ ] LLM solo se invoca cuando el usuario envía su primer mensaje.
- [ ] Cache solo para FAQs no personalizadas; nunca cachea precio/stock estático.

---

## J) Notificaciones

- [ ] Al ocurrir `paid` se envía email de confirmación al cliente.
- [ ] Al ocurrir `paid` se dispara alerta admin inmediata.
- [ ] Emails y alertas incluyen `order_id`.