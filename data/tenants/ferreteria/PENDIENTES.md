# PENDIENTES — Identidad del negocio

Completar estos datos ANTES de mostrar el bot a clientes reales.
Todos los campos marcados `[PENDIENTE...]` en `profile.yaml` quedan bloqueados por
la guardia en `bot_sales/services/pending_guard.py` — el bot responde
"Dejame consultar ese dato y te confirmo" en vez de exponer el placeholder.

---

## Checklist para la entrevista con el cliente

### Contacto
- [ ] **Teléfono / WhatsApp real**
  - Ej: `+54 9 11 1234-5678`
  - Usado en: respuestas del bot cuando el cliente pide contactar directo, FAQs

- [ ] **Dirección física del local**
  - Ej: `Av. Corrientes 1234, CABA`
  - Usado en: respuestas de "dónde están", link Google Maps

- [ ] **Ciudad / Barrio / Zona**
  - Ej: `Palermo, CABA` — para contextualizar envíos y recomendaciones

- [ ] **Link Google Maps**
  - Usado en: respuestas de "cómo llego"

### Horarios
- [ ] **Horario lunes a viernes**
  - Ej: `8:00 a 18:00`

- [ ] **Horario sábado**
  - Ej: `8:30 a 13:00`

- [ ] **¿Abren domingos o feriados?**
  - Si hay excepciones, detallarlas

### Medios de pago
- [ ] **Métodos aceptados**
  - Opciones comunes: efectivo, transferencia bancaria, MercadoPago, Naranja X, tarjetas débito, tarjetas crédito
  - ¿Aceptan cheque? ¿Cripto?

- [ ] **Cuotas**
  - ¿Tienen cuotas sin interés? ¿Qué tarjetas? ¿Cuántas cuotas?

### Condiciones mayoristas
- [ ] **Monto mínimo de compra mayorista**
  - Ej: `$50.000 ARS` para acceder a precio mayorista
  - Usado en: respuestas de precio y cotización

- [ ] **Cuenta corriente**
  - ¿Otorgan cuenta corriente? ¿Qué condiciones (plazo, monto, garantías)?

### Envíos y logística
- [ ] **Zonas de envío cubiertas**
  - Ej: CABA y GBA zona norte, o todo el país vía OCA/Andreani

- [ ] **Plazo de entrega habitual**
  - Ej: 24–48 hs hábiles CABA, 3–5 días interior

- [ ] **¿Envío gratis a partir de cierto monto?**
  - Si aplica: monto mínimo para envío sin cargo

### Identidad del negocio (nice-to-have)
- [ ] **Nombre completo del local / razón social**
  - Hoy figura como "Ferreteria Central" — ¿es correcto?

- [ ] **Años en el mercado / historia breve**
  - Para dar personalidad al bot ("somos una ferretería mayorista con 20 años en el rubro")

- [ ] **Especialidades o rubros fuertes**
  - Ej: "somos fuertes en electricidad y construcción, no tanto en pinturería fina"

---

## Archivo a actualizar

Una vez obtenidos los datos, actualizar:
1. `data/tenants/ferreteria/profile.yaml` — reemplazar todos los `[PENDIENTE...]`
2. `data/tenants/ferreteria/knowledge/faqs.yaml` — actualizar respuestas de horario, envíos, pagos
3. `data/tenants/ferreteria/policies.md` — si hay políticas específicas del local

Luego eliminar este archivo o marcar cada ítem como ✅.

---

## Decisiones técnicas pendientes

### Duración de reservas (hold_minutes)

- [ ] **¿Cuánto tiempo se mantiene un presupuesto reservado antes de expirar?**
  - `policies.md` dice: **45 minutos**
  - Configuración legacy (`tenant_config.yaml`): **1440 minutos (24 horas)**
  - Hoy en `profile.yaml`: `[PENDIENTE - confirmar con cliente: 45 min vs 24h]`
  - **Confirmar con el cliente** cuál es la política real para el local y actualizar `profile.yaml`

---

## Gaps detectados en el catálogo (probando demo)

Detectados al probar el bot con un caso de uso mayorista típico. Necesitan 
decisión del cliente:

### Categorización
- 7 llaves esféricas (1/2", 3/4", 20mm, 25mm, gas) están categorizadas como 
  "General" en vez de "Plomería". Pregunta para el cliente: ¿Es correcto 
  esto, o deberían moverse a Plomería?

### Productos faltantes  
- Caños de termofusión PP-R no están en el catálogo. Solo están las 
  boquillas/accesorios de termofusión (en "Cintas y Adhesivos" y "General"). 
  Pregunta para el cliente: ¿Vende caños PP-R y faltan cargar, o no los vende?

### Decisión técnica para discutir
- El bot hoy busca por categoría primero. Si un producto está mal 
  categorizado, no lo encuentra aunque el nombre matchee. Posibilidades:
  (a) Arreglar la categorización (recomendado si son pocos productos)
  (b) Hacer la búsqueda menos restrictiva sobre categoría
  (c) Combinación de ambos
