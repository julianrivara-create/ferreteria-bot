# Mini demo del entrenamiento Ferretería

Este demo está completamente aislado de los datos normales del tenant.

## Qué incluye

- flujo principal completo: hablar con el bot, enseñar y activar
- workspace simple con una respuesta incorrecta seleccionada
- caso con aclaración pendiente
- caso enfocado en cobertura futura
- detalle de un borrador
- pantalla de cambios listos para activar
- vistas secundarias de apoyo: impacto y uso

## Apertura rápida

1. Serví `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_simple_owner/snapshots` con un servidor estático:
   ```bash
   python3 -m http.server 8033 --directory "/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_simple_owner/snapshots"
   ```
2. Abrí `http://127.0.0.1:8033/index.html`.

## Recorrido recomendado para revisar el demo

1. Empezá por `Hablar con el bot` para ver el flujo simple.
2. Mirá cómo se guarda una enseñanza sobre una respuesta puntual.
3. Abrí el caso solo como vista avanzada.
4. Terminá en `Cambios listos` para revisar activación y antes/después.
## Páginas generadas

- `01_workflow_home.html`
  - muestra: Pantalla principal con conversación, panel de enseñanza y acceso directo a cambios listos.
  - ruta original: `/ops/ferreteria/training`
- `02_sandbox_review.html`
  - muestra: La ruta histórica de sandbox ahora reutiliza la misma experiencia simple de conversación y enseñanza.
  - ruta original: `/ops/ferreteria/training/sandbox?session_id=training:615d992f26774cbc94788b94032f3a8d&review_message_id=096c44d12909487e88fb988684dbb4a5`
- `03_case_clarification.html`
  - muestra: Caso guardado con resumen estructurado, estado de cobertura y creación guiada de correcciones.
  - ruta original: `/ops/ferreteria/training/cases/de90b441d3014a5398b0e0269883442c`
- `04_case_regression.html`
  - muestra: Caso que ya tiene un ejemplo futuro y todavía necesita decidir si conviene tocar el conocimiento activo.
  - ruta original: `/ops/ferreteria/training/cases/406a8a5491f04fd2abdc658105293852`
- `05_suggestion_draft.html`
  - muestra: Borrador de corrección con contexto semántico de revisión y vista antes/después.
  - ruta original: `/ops/ferreteria/training/suggestions/4d5dd2baca604bea8620e78e3797ad00`
- `06_suggestion_approved.html`
  - muestra: Corrección aprobada que muestra qué está listo para activarse a continuación.
  - ruta original: `/ops/ferreteria/training/suggestions/f022056efed74ee5b69197ddef388fc7`
- `07_cases_queue.html`
  - muestra: Lista de casos orientada al trabajo, con próximos pasos y señales de cobertura futura.
  - ruta original: `/ops/ferreteria/training/cases`
- `08_suggestions_queue.html`
  - muestra: Pantalla simple para activar cambios aprobados con antes/después y acceso al detalle.
  - ruta original: `/ops/ferreteria/training/suggestions`
- `09_usage.html`
  - muestra: Visibilidad de tokens y costo en un demo con datos cargados.
  - ruta original: `/ops/ferreteria/training/usage`

## Entorno del demo

- perfil: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_simple_owner/workspace/profile.yaml`
- base de datos: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_simple_owner/workspace/ferreteria_training_demo.db`
- token admin usado para renderizar snapshots: `demo-admin-token`
