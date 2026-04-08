# Guía de uso del entrenamiento Ferretería

## Qué es esta herramienta

Esta herramienta sirve para mejorar el bot sin entrar en código. Está pensada para personas del negocio que conocen los productos, cómo los piden los clientes y cómo debería responder el bot.

La idea es simple: probás una conversación, le enseñás al bot qué tendría que haber hecho y activás el cambio cuando esté listo. Nada más.

## El flujo principal: A → B → C

Todo el trabajo cotidiano sigue tres pasos en orden:

**A. Hablar con el bot**
Probá una conversación como si fueras un cliente real. Cuando el bot responda mal, marcás esa respuesta.

**B. Esto estuvo mal**
Le explicás al sistema qué salió mal y qué tendría que haber hecho el bot. No hace falta elegir categorías técnicas — alcanza con describirlo en lenguaje simple. El sistema arma un borrador de cambio automáticamente.

**C. Cambios listos**
Revisás el borrador, ves el antes y el después, y lo activás cuando estés de acuerdo.

Eso es todo. Las tres pantallas principales reflejan estos tres pasos.

---

## Cómo entrar

Entrá por: `/ops/ferreteria/training`

La primera vez te va a pedir la contraseña del panel. Una vez adentro, podés navegar libremente hasta que cerrés sesión.

---

## Las tres pantallas que vas a usar todos los días

### Hablar con el bot

Es la pantalla principal. Desde acá:

- Iniciás una sesión de prueba aislada (no toca conversaciones reales ni presupuestos en vivo)
- Escribís como si fueras un cliente del local
- Marcás la primera respuesta del bot que se desvió con **Esto estuvo mal**
- Completás el formulario explicando qué pasó
- El sistema guarda un cambio en preparación automáticamente

También podés volver a sesiones anteriores desde el panel de la derecha.

**Consejo:** revisá la *primera* respuesta que desvió la conversación, no la última. Es casi siempre más útil.

### Cambios listos

Acá aparecen los cambios que ya pasaron revisión y solo falta activarlos. Para cada uno podés:

- Leer el resumen en lenguaje simple
- Ver el **antes** y el **después**
- Activar el cambio cuando estés de acuerdo

Un cambio que está en esta pantalla todavía **no está activo** hasta que lo activás vos.

### Más herramientas

Acá quedan las vistas de apoyo para cuando necesitás algo más fino:

| Herramienta | Para qué sirve |
|---|---|
| **Términos sin resolver** | Detectar palabras repetidas que el bot no entiende y crear un borrador rápido |
| **Impacto** | Ver tendencia después de activar cambios |
| **Uso** | Consumo de tokens y costo del sandbox |
| **Sesiones** | Historial completo de pruebas |
| **Casos y ajustes avanzados** | Vista detallada de casos revisados para trabajo más técnico |
| **Cambios en preparación** | Cola completa incluyendo borradores, rechazados e historial |

Para el día a día, no hace falta entrar a estas vistas. Son de apoyo.

---

## Qué escribir en "Esto estuvo mal"

Cuando marcás una respuesta del bot y abrís el formulario, tenés que completar:

- **¿Qué estuvo mal?** — el tipo de problema (seleccionás de una lista corta)
- **¿Qué tendría que haber hecho primero?** — la primera acción que faltó
- **¿Qué debería responder o preguntar?** — la respuesta o pregunta correcta
- **Explicación corta para el equipo** — qué pasó, en una línea

Hay opciones avanzadas opcionales si ya sabés qué familia o producto era el correcto.

### Tipos de problema

| Opción | Cuándo usarla |
|---|---|
| **No entendió el término** | El cliente lo pidió de una forma que el bot no reconoció |
| **Eligió la familia equivocada** | Se fue a otro tipo de producto |
| **Eligió la variante equivocada** | Estaba cerca pero resolvió demasiado rápido |
| **Tendría que haber preguntado primero** | Faltaba una pregunta antes de responder |
| **Respondió con demasiado riesgo** | Contestó sin la seguridad necesaria |
| **Tendría que haberlo pasado a una persona** | No era un caso para resolver automáticamente |
| **Faltó una respuesta frecuente o de política** | Era una respuesta corta y estable del local |
| **No estoy seguro** | Para casos donde no queda claro; igual guarda el ejemplo |

Si dudás, elegí la opción más cercana. Siempre se puede ajustar después.

---

## Qué significan los estados de un cambio

| Estado | Qué significa |
|---|---|
| **Cambio en preparación** | El sistema armó un borrador; todavía no pasó revisión |
| **Lista para activar** | Fue revisada y aceptada; solo falta activarla |
| **Activa** | El cambio ya quedó aplicado en el conocimiento en uso |
| **Caso futuro** | El ejemplo quedó guardado como cobertura sin tocar el conocimiento activo |

---

## Cuándo conviene guardar solo como caso futuro

Conviene cuando:

- el ejemplo vale la pena protegerlo pero todavía no es momento de activar un cambio
- no estás seguro de qué tipo de corrección conviene
- querés dejar una referencia para más adelante sin tocar el comportamiento en vivo

Activá **Guardar solo como ejemplo futuro** en el formulario.

---

## Buenas prácticas

- Escribí pruebas como habla un cliente real: con abreviaturas, errores de tipeo, formas regionales.
- Revisá la primera respuesta que desvió la conversación, no la última.
- Preferí cambios chicos y claros.
- Si un cambio ya está en **Cambios listos**, revisá el antes/después antes de activar.
- Si no estás seguro, guardá como caso futuro y volvés después.

## Errores comunes a evitar

- Querer corregir demasiado en un solo cambio.
- Activar un cambio sin revisar el antes y el después.
- Escribir notas muy largas cuando el formulario estructurado ya explica el problema.
- Ir directo a **Más herramientas** antes de terminar el flujo simple A → B → C.

---

## Resumen en tres líneas

1. **Hablar con el bot** → marcás la primera respuesta que se desvió
2. **Esto estuvo mal** → explicás qué pasó y el sistema arma el cambio
3. **Cambios listos** → revisás el antes/después y activás cuando esté bien

Todo lo demás es secundario.
