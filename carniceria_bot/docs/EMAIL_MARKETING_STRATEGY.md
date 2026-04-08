# 📧 Estrategia de Email Marketing (Fidelización)

No vendas solo una vez. Usá el email para que te compren de nuevo (Retention).

## 1. Automatizaciones (Set & Forget)
Estas funcionan solas. Las configurás una vez y el bot hace el resto.

### 🟢 Welcome Series (Secuencia de Bienvenida)
Se dispara cuando alguien hace su **primera compra**.
*   **Email 1 (Inmediato)**: "¡Gracias por tu iPhone! Acá tenés tu factura y un tutorial de configuración."
*   **Email 2 (A los 3 días)**: "¿Necesitás accesorios? 10% OFF en Fundas y Cargadores." (Cross-Selling).
*   **Email 3 (A los 10 días)**: "¿Qué te pareció el servicio? Dejanos una review ⭐⭐⭐⭐⭐".

### 🟢 Carrito Abandonado / Reserva Caída
Si alguien reserva pero no paga en 30 minutos:
*   **Email (A la hora):** "Guardamos tu producto... ¿tuviste algún problema con el pago? Acá tenés el link de nuevo." (Recupera 10-15% de ventas perdidas).

---

## 2. Estrategias Avanzadas (La Mina de Oro) 🏆

Estas son las que usan las grandes marcas para que el cliente gaste más (LTV).

### 📱 Plan Canje (Trade-In) Inteligente
*   **Lógica:** Si sabemos que Juan compró un **iPhone 13** en el 2024... en el 2026 le mandamos:
*   **Asunto:** *"Juan, tu iPhone 13 vale $400 USD hoy"*
*   **Cuerpo:** *"Entregalo y llevate el iPhone 15 por la diferencia. Oferta exclusiva para clientes."*

### 🎂 Aniversario de Compra
*   **Lógica:** 1 año después de la compra.
*   **Email:** *"¡Feliz cumple a tu iPhone! 🥳 ¿Cómo está la batería? Si necesitás un cable nuevo o un service, tenés 15% OFF esta semana."*

### 🤝 Programa de Referidos
*   **Email:** *"¿Te gustó la atención? Si un amigo compra de tu parte, le damos una funda gratis a él y otra a vos."*

---

## 2. Campañas Mensuales (Broadcast)
Emails que mandás manualmente (o programás) a toda tu base.

### 📅 "El Drop del Mes"
*   Avisar cuando entra stock nuevo: *"¡Llegaron los iPhone 15 Pro Max en Titanio!"*
*   **Segmentación**: Mandalo solo a los que preguntaron por ese modelo (si registramos "leads").

### 🎁 Promos de Fecha Especial
*   CyberMonday, HotSale, Navidad, Día de la Madre.
*   *"Solo por hoy: Envío gratis a todo CABA."*

---

## 🛠️ ¿Qué necesitamos cambiar en el código?

1.  **Base de Datos de Clientes**: Hoy guardamos ventas sueltas. Necesitamos una tabla `customers` que guarde:
    *   Email
    *   Nombre
    *   Historial de compras (LTV: Lifetime Value)
    *   *Marketing Opt-in* (si aceptó recibir correos).

2.  **Módulo de Marketing**: Un script que corra todos los días a las 10 AM, chequee "a quién le toca el Email 2" y lo mande.

### Propuesta de Implementación
Puedo armar ahora mismo el módulo de **"Recupero de Reservas Caídas"**. Es el que más plata te va a hacer recuperar rápido. ¿Te parece?
