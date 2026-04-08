# Plan de Ejecucion: Salesbot Platform Multirubro (Reusable)

## Restriccion de alcance (obligatoria)
- Solo se modifica `/Users/julian/Desktop/Cerrados/sales-bot-platform`.
- No se modifica `Bot_Final_Production` ni ninguna carpeta externa.

## Objetivo
Convertir `sales-bot-platform` en una plantilla de produccion reusable por rubro, donde crear un nuevo bot requiera solo:
1. crear tenant,
2. cargar catalogo,
3. ajustar branding/politicas.

Sin cambios de codigo para cada nuevo cliente.

## Resultado esperado
- Paridad de calidad de produccion en bot + web + dashboard.
- Arquitectura multi-tenant real por slug/telefono.
- Onboarding en 1 comando.
- Suite de pruebas y smoke checks que definan "deployable".

## Estado actual resumido
- Ya existe base multi-tenant (tenant manager, API `/api/t/<slug>/...`, dashboard por tenant, wizard de tenant).
- Todavia hay arrastre Herramienta/Apple/Atelier en partes del core, web, fixtures y docs.
- Falta endpoint de health en `wsgi.py` para checks estandar de plataforma.

## Avance
- P0.1 completado: endpoint `/health` activo + smoke runtime script + gate de tests estable.
- P1 completado: core sin hardcodes de rubro en rutas criticas (chatgpt/gemini/universal_llm/error_recovery/business_logic).
- P1.5 completado: frontend tenant-aware sin fallback de marca fija + checkout/carrito con contexto tenant.
- P2 completado: wizard con validaciones de datos + `scripts/validate_tenant.py` + runbook `docs/LAUNCH_NEW_BOT.md`.

## Fases (P0/P1/P2)

## Fase P0 - Bloqueantes de produccion
### Objetivo
Cerrar riesgos de runtime y observabilidad antes de cualquier expansion.

### Trabajo
1. Agregar `GET /health` en `/Users/julian/Desktop/Cerrados/sales-bot-platform/wsgi.py`.
2. Definir smoke script local (arranque app + health + APIs tenant + dashboard login).
3. Validar bootstrap de tenant default sin dependencias externas.
4. Eliminar defaults fragiles de path/base de datos en runtime principal.

### Criterio de aceptacion
- `GET /health` responde `200` con payload JSON minimo (`status`, `service`, `version` opcional).
- Smoke check pasa en entorno limpio.
- `pytest -q` en verde.

## Fase P1 - Core agnostico de rubro
### Objetivo
Eliminar hardcodes de dominio Herramienta/Apple en flujo funcional.

### Trabajo
1. Revisar y limpiar respuestas mock/hardcodeadas en:
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/bot_sales/core/chatgpt.py`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/bot_sales/core/gemini.py`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/bot_sales/core/universal_llm.py`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/bot_sales/core/error_recovery.py`
2. Generalizar textos de negocio en:
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/bot_sales/core/business_logic.py`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/bot_sales/core/database.py` (docstrings/mensajes).
3. Mover ejemplos de Apple a fixtures/test-data neutrales cuando no prueben compat legacy.
4. Mantener compatibilidad legacy de catalogo sin romper tests existentes.

### Criterio de aceptacion
- En tenant farmacia/ropa, el bot no sugiere Herramienta/Apple salvo que exista en su catalogo.
- No hay hardcodes de marca en paths criticos de runtime (bot/API/dashboard).

## Fase P1.5 - Frontend verdaderamente multirubro
### Objetivo
Quitar defaults visuales y de imagen dependientes de Herramienta.

### Trabajo
1. Limpiar fallbacks de imagen y placeholders Herramienta en:
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/website/scripts/main.js`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/website/scripts/product.js`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/website/scripts/search.js`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/website/scripts/related-products.js`
2. Reemplazar branding hardcodeado en:
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/website/checkout.html`
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/website/api/faq.json` (si se sigue usando como fallback global).
3. Definir estrategia de imagen por tenant:
   - `branding.json` + placeholder neutro por categoria.

### Criterio de aceptacion
- La web renderiza correctamente con tenants no-tecnologia sin assets Apple.
- Navegacion por slug (`/t/<slug>`) mantiene branding/categorias correctas.

## Fase P2 - Producto plantilla y onboarding rapido
### Objetivo
Dejar un flujo "nuevo bot en minutos".

### Trabajo
1. Fortalecer wizard:
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/scripts/create_tenant.py`
   - validaciones de slug/telefono/moneda/idioma.
   - opcion `--industry` con semillas mas completas.
2. Agregar comando de validacion tenant:
   - `scripts/validate_tenant.py` (nuevo), chequea archivos requeridos y schema.
3. Crear runbook operativo:
   - `/Users/julian/Desktop/Cerrados/sales-bot-platform/docs/LAUNCH_NEW_BOT.md`
4. Actualizar docs legacy orientadas a Herramienta para evitar confusion.

### Criterio de aceptacion
- Nuevo tenant operativo en <= 15 minutos sin editar codigo.
- Checklist de lanzamiento reproducible por terceros.

## Fase QA - Gates de release
### Suite minima obligatoria
1. `pytest -q`
2. tests de tenancy/routing y storefront multitenant.
3. smoke endpoints:
   - `/health`
   - `/api/products` (legacy)
   - `/api/t/farmacia/products`
   - `/api/t/ropa/products`
   - `/dashboard/login`

### Definicion de "deployable"
- Tests verdes.
- Smoke verde.
- Sin hardcodes de marca en runtime multitenant.
- Sin cambios fuera de esta carpeta.

## Backlog inmediato recomendado
1. P0.1: agregar `/health` y smoke script.
2. P1.1: limpiar hardcodes de respuesta en `chatgpt.py` y `gemini.py`.
3. P1.2: limpiar frontend fallbacks Herramienta.
4. P2.1: agregar `validate_tenant.py`.
5. P2.2: escribir `LAUNCH_NEW_BOT.md`.

## Regla de trabajo
- Cada fase cierra con:
1. diff acotado,
2. validacion ejecutada,
3. criterio de aceptacion cumplido,
4. breve nota de cambios.
