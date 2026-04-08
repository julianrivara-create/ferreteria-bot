# 🗺️ Roadmap de Producto: Plataforma de Comercio Conversacional

Este documento define la evolución estratégica del Bot de Ventas actual hacia una Plataforma SaaS Multi-tenant.

## 🎯 Objetivo
Transformar el "demo técnico" actual en un producto vendible, escalable y operable con mínimo esfuerzo manual.

## 1. Fortalezas Actuales (Base Sólida)
*   **Arquitectura en Capas:** Cerebro (Lógica) desacoplado de Interfaces (WhatsApp).
*   **Visibilidad:** Dashboard funcional para el dueño del negocio.
*   **Auditoría:** Logging robusto (`events.log`) y persistencia en DB SQL.
*   **Loop de Venta:** Lead -> Conversación -> Cierre -> Reporte.

## 2. Prioridades de Desarrollo

### Prioridad A: Transformación a SaaS (Multi-tenant)
*Objetivo: Entregar un nuevo cliente en horas, no días.*

- [ ] **Arquitectura Multi-tenant:**
    - Migrar de configuración en `.env` (single tenant) a configuración por cliente en DB/JSON.
    - Cargar credenciales, prompts y catálogos dinámicamente según el número de teléfono entrante (o ID de cuenta).
- [ ] **Configuración No-Code:**
    - UI en Dashboard para editar Prompts de sistema ("Tu eres un vendedor de...").
    - Carga de catálogos (CSV/Excel) por interfaz web.
    - Toggle de features (activar/desactivar IA, activar/desactivar stock real).

### Prioridad B: Operaciones y Confiabilidad (SLA)
*Objetivo: Reducir soporte técnico y garantizar estabilidad.*

- [ ] **Circuit Breakers & Fallbacks:**
    - Si LLM falla/tarda -> Responder con reglas fijas o menú predefinido.
    - Detección de bucles en la conversación.
- [ ] **Guardrails de Negocio:**
    - Validación estricta: El bot NUNCA debe inventar un precio que no esté en la DB.
    - "Verificación de Alucinaciones": Consultar DB antes de confirmar disponibilidad.
- [ ] **Observabilidad Proactiva:**
    - Alertas automáticas (Slack/Email) si aumenta la tasa de error o latencia.

### Prioridad C: Empaquetado Comercial
*Objetivo: Vender resultados, no tecnología.*

#### 📦 Pack 1: "Bot + Handoff" (Entrada)
*   Canal: WhatsApp.
*   Funciones: FAQs, Catálogo, Calificación de Leads.
*   Valor: Filtrar curiosos y entregar leads calificados al humano.
*   Entrega: 7-10 días.

#### 📦 Pack 2: "Bot + Seguimiento" (Crecimiento)
*   Incluye Pack 1.
*   Funciones: Re-activación de clientes ("¿Seguís interesado?"), Recuperación de carritos.
*   Valor: Aumentar conversión de leads existentes.
*   Entrega: 10-14 días.

#### 📦 Pack 3: "Sistema de Ventas Completo" (Profesional)
*   Incluye Pack 2.
*   Funciones: Pipeline de ventas (CRM/Sheets), Reportes automáticos semanales, A/B Testing de mensajes.
*   Valor: Visibilidad total y optimización constante.
*   Entrega: 2-3 semanas.
