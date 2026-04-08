# Plan de Mejora Integral - Ferretería Sales Bot 2.0

## 🎯 OBJETIVO
Plataforma de comercio AI de nivel empresarial para ferretería, con seguridad robusta, inteligencia artificial avanzada, y capacidades omnicanal completas.

---

## ✅ FASE 1: FUNDAMENTOS Y ARQUITECTURA (COMPLETADO)

### 1.1 Integración de Funciones Avanzadas
- [x] **Comparación de Productos** (`comparar_productos`)
  - Implementación completa en `business_logic.py` y `chatgpt.py`
  - Motor de comparación lado a lado con recomendaciones inteligentes
  - Soporte para todas las categorías del catálogo de ferretería

- [x] **Validación de Datos** (`validar_datos_cliente`)
  - Validación proactiva de email, teléfono, DNI
  - Retorna errores específicos por campo
  - Previene datos basura en la DB

- [x] **Detección de Fraude** (`detectar_fraude`)
  - Sistema de scoring 0-100
  - Bloqueo automático con score > 60
  - Integrado con business logic

### 1.2 Arquitectura de Seguridad
**Módulos Implementados**:

#### Fraud Detector (`security/fraud_detector.py`)
- **Blacklist Management**: Emails/teléfonos/IPs bloqueados
- **Rate Limiting**: 10 req/hora, 50/día por usuario
- **Risk Scoring**:
  - Blacklist: +100 (bloqueo instantáneo)
  - Rate limit: +50
  - Contenido sospechoso: +30
  - Email desechable: +20

#### Validators (`security/validators.py`)
- Validación de emails con regex + DNS check opcional
- Teléfonos argentinos (formatos múltiples)
- DNI (7-8 dígitos, rango 1M-99M)
- SKU, precios, stock

#### Image Fraud Detector (`security/image_fraud_detector.py`)
- Detección de manipulación de imágenes (Photoshop)
- Análisis de metadata EXIF
- Validación de comprobantes de pago

---

## 🔒 FASE 2: SEGURIDAD Y COMPLIANCE (COMPLETADO)

### 2.1 Protección contra Fraude
```python
# Ejemplo de uso
fraud_result = bl.detectar_fraude(
    email="usuario@example.com",
    phone="1122334455",
    message="último mensaje del cliente"
)

if fraud_result['should_block']:
    # Bloquear transacción
    # Alertar equipo de seguridad
```

### 2.2 Sanitización de Payload
- Validación estricta de schemas
- Rechazo de eventos sin `order_id`
- Protección contra injection

### 2.3 Webhooks de MercadoPago
**Implementado en** `integrations/mp_webhooks.py`:
- Verificación de firma HMAC
- Rate limiting de webhooks
- Idempotencia (prevenir duplicados)

---

## 🧠 FASE 3: INTELIGENCIA ARTIFICIAL (COMPLETADO)

### 3.1 Motor de Comparación (`intelligence/comparisons.py`)
**Características**:
- Comparación técnica automática (precio, categoría, atributos)
- Identificación de "ganador" por criterio
- Recomendaciones en lenguaje natural
- Tablas formateadas

**Ejemplo de salida**:
```
📊 COMPARACIÓN
Taladro Percutor 13mm   vs   Taladro Inalámbrico 18V

Potencia:   710W ✓           N/A (batería)
Precio:     $85.000 ✓        $120.000

💡 Recomendación:
✅ Taladro Percutor tiene mejor precio (29% más barato)
🔋 Taladro Inalámbrico es más práctico para obra sin cables
```

### 3.2 Control de Alucinaciones
**Reglas Absolutas**:
> El bot NO puede mencionar productos fuera del catálogo

**Implementación**:
- Negative constraints en system prompt
- Si no existe en DB: "No lo tenemos disponible"
- Nunca inventar

### 3.3 Advisor Mode (Asesor Técnico)
**Base de Conocimiento**: `data/specs.json`
- Herramientas eléctricas: ✅ COMPLETO
- Tornillería y fijaciones: ✅ COMPLETO
- Electricidad y plomería: ✅ COMPLETO

**Flujo Obligatorio**:
1. Explicación técnica (potencia, medidas, compatibilidad)
2. Beneficio real para el usuario
3. Recién después → stock y precio

**Filosofía de Venta**:
> No listar specs. Explicar beneficios.

Ejemplo:
> "Tiene 710W y función percutor, lo que significa que puede perforar hormigón sin problema."

Objetivo:
> Vender a través de confianza, no presión.

### 3.4 Zero-Waste AI (Optimización de Costos)
- Saludo inicial en frontend (gratis)
- LLM solo se usa cuando el usuario responde
- Cachear respuestas frecuentes (`consultar_faq`)
- Evitar prompts largos innecesarios

---

## 🎨 FASE 4: EXPERIENCIA DE USUARIO (PENDIENTE)

### 4.1 Mobile First QA
Checklist:
- [ ] Botones no tapados por dedos
- [ ] Chat no invade CTA
- [ ] Imágenes correctas en vertical
- [ ] LCP < 2.5s en 4G

### 4.2 SEO y Open Graph
Al compartir una PDP:
- Imagen correcta
- Nombre del producto
- Precio real

⚠️ Requiere:
- Server-render o pre-render de metadata
- JS client-side NO es suficiente

### 4.3 Dashboard en Tiempo Real
**Métricas Mínimas**:
- Visitas
- Clicks "Comprar"
- Initiate Checkout
- Paid
- Conversión real (`paid / view_item`)

**Feed Live**:
- "Alguien está viendo Taladro Percutor 13mm"
- "Nueva venta confirmada"

**Fuente de Verdad**:
> Dashboard == DB == Bot

---

## 🔄 FASE 5: POSTVENTA Y LIFECYCLE AUTOMATION (FUTURO)

### Timeline de Mensajes
**Día 0**: Confirmación inmediata + instrucciones de retiro/envío
**Día 1-3**: Tracking + ETA realista
**Entrega**: Confirmación de recepción
**Día 7**: Tips de uso + Upsell suave (accesorios complementarios)
**Día 14**: NPS survey
  - 5⭐ → pedir review
  - 1-3⭐ → alerta humana
**Día 30+**: Mantenimiento + recompra segmentada

### Segmentación
- Categoría de producto
- Valor del ticket
- Zona geográfica

---

## ✅ TESTING Y QA (COMPLETADO)

### Test Suite Completo: `tests/test_security_intelligence.py`

**Resultados**:
```
✅ VALIDATOR TESTS: 8/8 PASSED
✅ FRAUD DETECTION TESTS: 5/5 PASSED
✅ PRODUCT COMPARISON TESTS: PASSED
✅ INTEGRATION TESTS: 3/3 PASSED
```

**Cobertura**:
- Validación de emails, teléfonos, DNI
- Detección de emails desechables
- Rate limiting (10 req/h)
- Contenido sospechoso (URLs, keywords)
- Comparación de productos
- Integración completa business logic

---

## 📊 CRITERIOS DE FINALIZACIÓN

Una feature está terminada SOLO si:
- ✅ Cumple este spec
- ✅ Pasa QA
- ✅ No rompe métricas
- ✅ No introduce alucinaciones
- ✅ Mantiene consistencia DB / Bot / Dashboard

---

## 🎯 ESTADO ACTUAL

### ✅ COMPLETADO
1. **Integración de Funciones** (comparación, validación, fraude)
2. **Arquitectura de Seguridad** (fraud detector, validators)
3. **Motor de Inteligencia** (comparación de productos)
4. **Testing Completo** (suite de tests automatizada)
5. **Multi-tenant** (ferreteria, farmacia, ropa)
6. **WhatsApp Meta Webhook** (phone_number_id routing)

### 🏗️ EN PROGRESO
7. **Image Fraud Detection** (módulo existe, pendiente integración)

### 📋 PENDIENTE
8. **Dashboard en Tiempo Real**
9. **Mobile First QA**
10. **SEO/Open Graph**
11. **Lifecycle Automation (mensajes post-venta)**
12. **Redis para Rate Limiting** (actualmente HybridRateLimiter)

---

## 🚀 PRÓXIMOS PASOS RECOMENDADOS

### Corto Plazo (1-2 semanas)
1. Integrar `image_fraud_detector.py` en flujo de pagos
2. Crear dashboard básico de métricas
3. Expandir `specs.json` con más categorías de ferretería

### Mediano Plazo (1 mes)
4. Implementar Redis dedicado para rate limiting distribuido
5. Server-side rendering para SEO
6. A/B testing de prompts (`experiments/ab_testing.py`)

### Largo Plazo (3 meses)
7. Lifecycle automation completo
8. NPS tracking y feedback loop
9. Retargeting de consultas sin conversión

---

## 📝 NOTA FINAL

Este documento reemplaza:
- Prompts largos
- Chats infinitos
- Decisiones implícitas

**Todo cambio debe reflejarse acá.**

**Última actualización**: 2026-04-01
**Estado**: ✅ PRODUCTION READY (Fases 1-3 completadas)
