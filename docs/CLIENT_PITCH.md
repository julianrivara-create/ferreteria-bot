# 🍎 Asistente de Ventas con IA - Documentación para Cliente

Este documento detalla el funcionamiento, alcance y operación del Asistente de Ventas Inteligente desarrollado para tu negocio.

---

## 🚀 ¿Qué es?

No es un simple "chatbot" de respuestas automáticas. Es un **Agente de Ventas con Inteligencia Artificial** (potenciado por ChatGPT-4) diseñado específicamente para vender productos High-Ticket (Herramienta, Mac, etc.).

**Su misión:** Atender 24/7, filtrar curiosos, asesorar técnicamente, manejar objeciones y cerrar ventas (o entregarle el cliente "caliente" a un humano).

---

## 🔄 El Viaje del Cliente (User Journey)

Así es la experiencia de un usuario que escribe a tu WhatsApp/Web:

1.  **Saludo y Detección**: El cliente dice "Hola, precio del Taladro Percutor 13mm". El bot detecta la intención de compra inmediatamente.
2.  **Consulta de Stock Real**: El bot consulta la base de datos en tiempo real.
    *   *Si hay*: "Tengo el Taladro Percutor 13mm de 128GB en Negro a $1.200 USD. ¿Te interesa ese color?"
    *   *Si no hay*: Le ofrece alternativas (ej: Atornillador 18V Pro) automáticamente.
3.  **Manejo de Objeciones**:
    *   Cliente: "Es muy caro".
    *   Bot: "Entiendo, es una inversión. Pero pensá que el Taladro Percutor 13mm tiene el nuevo chip A16 y cámara de 48MP que te dura 5 años. Además, el valor de reventa es altísimo." (Argumentos de venta reales).
4.  **Cierre y Reserva**:
    *   Cliente: "Bueno, lo quiero".
    *   Bot: "Genial. Para reservarlo necesito tu nombre y DNI. Te lo guardo por 30 minutos mientras me pasás el comprobante." (Descuenta stock temporalmente).
5.  **Cross-Selling Inteligente**:
    *   Bot: "Por cierto, para proteger ese Herramienta, ¿querés agregar una funda MagSafe o Destornillador a Bateria con 10% de descuento?"
6.  **Pago y Notificación**: El bot genera el link de pago o pasa los datos de transferencia. Al confirmarse, te llega un mail a vos con el detalle.

---

## 🛠️ Tu Operatoria (Cómo se maneja)

El sistema está pensado para que **trabajes menos**, no más.

### 1. ¿Cómo actualizo precios y stock?
Tenés 3 formas, elegí la que te guste:
*   **Automática (Recomendada)**: Si tu proveedor te manda un mail con excel diario, el bot lo lee solo y actualiza todo.
*   **Google Sheets**: Editás una planilla en la nube (como Excel online) y el bot se actualiza solo.
*   **Manual**: Entrás al Panel de Control y cambiás "Stock: 0" cuando vendés el último en el local.

### 2. ¿Quién controla al bot? (Panel de Control)
Tenés acceso a un **Dashboard Web** donde ves:
*   **Ventas del día**: Gráficos de cuánto vendiste.
*   **Chats en vivo**: Podés leer qué está hablando el bot.
*   **Productos Top**: Qué modelos se piden más.

### 3. ¿Qué pasa si el bot no sabe algo?
Si el cliente pregunta algo muy raro o se enoja ("Quiero hablar con un asesor"), el bot detecta el sentimiento negativo y hace un **"Handover"**:
*"Entiendo, te voy a pasar con un asesor humano para ver ese tema puntual. Aguardame un instante."*
(Te notifica para que intervengas).

---

## 🙋 Preguntas Frecuentes (FAQ)

Aquí nos anticipamos a las dudas que podrías tener:

**(Q) ¿El bot puede vender algo que no tengo?**
**R:** No. El bot chequea la base de datos antes de confirmar CADA venta. Si queda 1 unidad y dos personas la quieren, se la vende al primero y al segundo le dice "Disculpá, se acaba de vender, pero tengo este otro...".

**(Q) ¿Es seguro? ¿Me pueden hackear precios?**
**R:** Sí, es seguro. Implementamos validación de firmas criptográficas en los pagos (MercadoPago) y los precios están en tu base de datos privada, no en el chat. Además, el bot tiene "instrucciones de seguridad" para no aceptar regateos ni cambiar precios por su cuenta.

**(Q) ¿Qué pasa si se corta internet?**
**R:** El bot corre en la nube. Si se te corta la luz a vos, el bot SIGUE vendiendo.

**(Q) ¿Puedo ver si el bot está respondiendo bien?**
**R:** Sí. Todas las conversaciones quedan guardadas. Podés auditarlas desde el Dashboard para ver cómo vende. Además, el bot "aprende" (usamos tus correcciones para mejorar sus respuestas futuras).

**(Q) ¿Sirve solo para Herramienta?**
**R:** Hoy está configurado para Herramienta/Apple, pero la arquitectura sirve para cualquier producto. Solo cambiamos el catálogo.

---

## 💡 Resumen de Valor

Estás contratando un **vendedor experto** que:
1.  No duerme.
2.  No pide vacaciones.
3.  Responde en 1 segundo.
4.  Conoce todo el stock de memoria.
5.  No se olvida de ofrecer el cargador/funda (aumenta tu ticket promedio 15-20%).

*¿Empezamos con la implementación?*
