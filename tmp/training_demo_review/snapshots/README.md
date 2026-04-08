# Mini demo del entrenamiento Ferretería

Este demo está completamente aislado de los datos normales del tenant.

## Qué incluye

- flujo principal completo: bandeja, pruebas, caso y corrección
- transcripción del sandbox con una respuesta incorrecta seleccionada
- caso con aclaración pendiente
- caso enfocado en cobertura futura
- detalle de un borrador
- corrección aprobada por activar
- vistas secundarias de apoyo: impacto y uso

## Apertura rápida

1. Serví `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_review/snapshots` con un servidor estático:
   ```bash
   python3 -m http.server 8033 --directory "/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_review/snapshots"
   ```
2. Abrí `http://127.0.0.1:8033/index.html`.

## Recorrido recomendado para revisar el demo
1. Empezá por la bandeja de trabajo para entender qué hacer ahora.
2. Seguí con el sandbox para ver cómo se revisa una respuesta.
3. Abrí el caso para ver cómo se decide la corrección.
4. Terminá en el detalle de corrección para revisar antes/después y estados.
## Páginas generadas

- `01_workflow_home.html`
  - muestra: Punto de entrada con contadores, próximos pasos y seguimiento de casos futuros.
  - ruta original: `/ops/ferreteria/training`
- `02_sandbox_review.html`
  - muestra: Conversación con revisión sobre cualquier respuesta, guía estructurada y una respuesta incorrecta seleccionada.
  - ruta original: `/ops/ferreteria/training/sandbox?session_id=training:5e27eb867d4a422a86af8e2bb594932c&review_message_id=2bb61c688d654bc4a8110895fff8f44a`
- `03_case_clarification.html`
  - muestra: Caso guardado con resumen estructurado, estado de cobertura y creación guiada de correcciones.
  - ruta original: `/ops/ferreteria/training/cases/af6786ea953c4971942a1db56f25982f`
- `04_case_regression.html`
  - muestra: Caso que ya tiene un ejemplo futuro y todavía necesita decidir si conviene tocar el conocimiento activo.
  - ruta original: `/ops/ferreteria/training/cases/df575253c868454ab34d904c5944009d`
- `05_suggestion_draft.html`
  - muestra: Borrador de corrección con contexto semántico de revisión y vista antes/después.
  - ruta original: `/ops/ferreteria/training/suggestions/7148c0e43fc1485eb9a55c61ee631401`
- `06_suggestion_approved.html`
  - muestra: Corrección aprobada que muestra qué está listo para activarse a continuación.
  - ruta original: `/ops/ferreteria/training/suggestions/9b33a90a37ab45e0917d5b9c86ca5940`
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

- perfil: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_review/workspace/profile.yaml`
- base de datos: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_review/workspace/ferreteria_training_demo.db`
- token admin usado para renderizar snapshots: `demo-admin-token`
