# Mini demo del entrenamiento Ferretería

Este demo está completamente aislado de los datos normales del tenant.

## Qué incluye

- bandeja de trabajo con contadores útiles
- transcripción del sandbox con una respuesta incorrecta seleccionada
- caso con aclaración pendiente
- caso enfocado en cobertura futura
- detalle de un borrador
- corrección aprobada por activar
- colas y pantalla de uso

## Apertura rápida

1. Serví `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_es_check/snapshots` con un servidor estático:
   ```bash
   python3 -m http.server 8033 --directory "/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_es_check/snapshots"
   ```
2. Abrí `http://127.0.0.1:8033/index.html`.

## Páginas generadas

- `01_workflow_home.html`
  - muestra: Punto de entrada con contadores, próximos pasos y seguimiento de casos futuros.
  - ruta original: `/ops/ferreteria/training`
- `02_sandbox_review.html`
  - muestra: Conversación con revisión sobre cualquier respuesta, guía estructurada y una respuesta incorrecta seleccionada.
  - ruta original: `/ops/ferreteria/training/sandbox?session_id=training:f2fae2f9d5fc4891a859c9280450634d&review_message_id=56caa74c986b472cb831be25d76141c2`
- `03_case_clarification.html`
  - muestra: Caso guardado con resumen estructurado, estado de cobertura y creación guiada de correcciones.
  - ruta original: `/ops/ferreteria/training/cases/f1f25f03becd4af69b4b046e1a3f1366`
- `04_case_regression.html`
  - muestra: Caso que ya tiene un ejemplo futuro y todavía necesita decidir si conviene tocar el conocimiento activo.
  - ruta original: `/ops/ferreteria/training/cases/cb4eb5e4f12c44d89f500ec9a0c2af32`
- `05_suggestion_draft.html`
  - muestra: Borrador de corrección con contexto semántico de revisión y vista antes/después.
  - ruta original: `/ops/ferreteria/training/suggestions/6f7c4f4f5a154fd998853519e542ef10`
- `06_suggestion_approved.html`
  - muestra: Corrección aprobada que muestra qué está listo para activarse a continuación.
  - ruta original: `/ops/ferreteria/training/suggestions/e6cc61641f624dc783502822546fd80f`
- `07_cases_queue.html`
  - muestra: Lista de casos orientada al trabajo, con próximos pasos y señales de cobertura futura.
  - ruta original: `/ops/ferreteria/training/cases`
- `08_suggestions_queue.html`
  - muestra: Borradores, aprobadas y activas en una sola cola con resúmenes claros del cambio.
  - ruta original: `/ops/ferreteria/training/suggestions`
- `09_usage.html`
  - muestra: Visibilidad de tokens y costo en un demo con datos cargados.
  - ruta original: `/ops/ferreteria/training/usage`

## Entorno del demo

- perfil: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_es_check/workspace/profile.yaml`
- base de datos: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_es_check/workspace/ferreteria_training_demo.db`
- token admin usado para renderizar snapshots: `demo-admin-token`
