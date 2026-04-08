# Resumen general

Nuestra estrategia para la construcción del Asistente de Ventas con Inteligencia Artificial se basa en un principio fundamental: la seguridad operativa. En lugar de intentar crear un robot autónomo desde el primer día que intente cerrar ventas sin supervisión (lo cual genera errores, frustración en los clientes y promesas de precios incorrectos), estamos construyendo el sistema en cinco etapas controladas. 

Este enfoque por fases nos permite asegurarnos de que el asistente primero aprenda a hacer bien lo básico —como consultar el stock real, entender qué pide el cliente y armar presupuestos preliminares confiables— antes de darle mayor libertad. De esta manera, el bot se integra de forma segura a la empresa, actuando como una herramienta que prepara el terreno para que el equipo humano cierre la venta, protegiendo así la reputación del negocio y la calidad de la atención.

# Dónde estamos hoy

Basándonos en el trabajo realizado hasta el momento en el proyecto, **la Fase 1 se encuentra operativa y la Fase 2 está en curso con implementaciones sólidas.**

Actualmente, el bot ya no es un simple chat de respuestas automáticas. En términos prácticos para el negocio, el sistema ya es capaz de:
- Recibir mensajes de clientes a través de WhatsApp.
- Consultar el catálogo y el stock en tiempo real para armar presupuestos preliminares seguros.
- Reconocer cuando un cliente acepta un presupuesto y, en lugar de intentar cobrarle automáticamente, enviar el caso a una "cola de revisión" para que un vendedor humano tome el control, valide los datos y cierre la venta.
- Registrar cuándo el bot no entiende un término o un producto, guardándolo en un registro especial para que el equipo pueda revisarlo y "enseñarle" ese nuevo término al sistema de forma sencilla.
- Permitir que el negocio modifique políticas, preguntas frecuentes (FAQs) y sinónimos sin necesidad de tocar el código de programación.

A su vez, ya estamos trabajando activamente en los objetivos de la Fase 2, incorporando validaciones más estrictas para que el bot distinga mejor entre familias de productos (por ejemplo, para que no confunda un tornillo con un taladro si las palabras se parecen) y mejorando su capacidad para manejar la forma coloquial en la que los clientes piden las cosas.

# Las 5 fases del proyecto

### Fase 1: Asistente operativo con revisión humana (Estado: Completada / Operativa)
**Qué significa:** El bot funciona como un asistente que atiende al cliente, consulta el stock, arma un presupuesto borrador y deriva el caso a un empleado de la ferretería cuando el cliente dice "lo quiero".
**Por qué es importante:** Crea una base segura. Permite que el bot filtre consultas y ahorre tiempo, pero asegura que un humano siempre tenga la última palabra antes de comprometer inventario o cobrar.
**Qué esperar:** Un bot que atiende 24/7, genera presupuestos precisos basados en los datos reales del local y organiza los pedidos para que el equipo los revise. Un panel de control simple para ajustar respuestas frecuentes.
**Qué NO esperar:** El bot no va a cerrar la venta por sí solo, ni a procesar pagos de forma autónoma. No reemplaza a un vendedor experto.

### Fase 2: Profundidad de conocimiento ferretero real (Estado: En progreso)
**Qué significa:** El bot se vuelve un experto en los productos de la ferretería. Aprende a distinguir mejor entre herramientas, medidas, marcas y presentaciones (por ejemplo, saber cuándo vender por unidad o por caja cerrada).
**Por qué es importante:** La ferretería tiene un vocabulario complejo y muchas variantes. Esta fase reduce drástically las confusiones y hace que el bot haga las preguntas de aclaración correctas ("¿Buscás el tornillo de 2 pulgadas o de 3?") en lugar de adivinar o frenarse.
**Qué esperar:** Un asistente que entiende mucho mejor cómo hablan los clientes argentinos, ofrece alternativas lógicas si algo no hay en stock y se "traba" con mucha menor frecuencia.
**Qué NO esperar:** Todavía no arma presupuestos complejos para obras completas ni realiza ventas autónomas.

### Fase 3: Sistema operativo entrenable
**Qué significa:** Implementación de herramientas para que el propio equipo de la ferretería pueda ir "entrenando" al bot en el día a día basándose en las conversaciones reales que tuvo con los clientes, validando correcciones antes de que se apliquen.
**Por qué es importante:** Permite que el bot mejore continuamente de forma estructurada y controlada por el negocio, sin depender de programadores para cada ajuste de vocabulario.
**Qué esperar:** Un panel donde el personal revisa dónde falló el bot y le indica cómo debe responder la próxima vez. Un sistema que va absorbiendo el "saber hacer" de la ferretería de forma segura.
**Qué NO esperar:** No existe el aprendizaje "mágico" o automático por sí solo. El sistema requerirá que un humano apruebe los cambios en el conocimiento para evitar que el bot aprenda cosas incorrectas.

### Fase 4: Copiloto de alta calidad con menor dependencia humana
**Qué significa:** El bot alcanza un nivel de madurez donde resuelve la gran mayoría de las consultas operativas habituales de forma correcta y fluida, requiriendo que los humanos intervengan solo en los casos realmente complejos o de alto valor.
**Por qué es importante:** Libera al equipo de ventas de casi todo el trabajo rutinario, permitiéndoles enfocarse en las ventas a empresas, cotizaciones de obras o atención especializada.
**Qué esperar:** Gran confiabilidad en el día a día. Menos casos derivados por dudas del sistema y mayor tasa de presupuestos correctamente elaborados al primer intento.
**Qué NO esperar:** Autonomía total. Siempre habrá escenarios atípicos, quejas o consultas muy específicas que requerirán tacto humano. No se garantiza una cotización perfecta para el 100% de los escenarios imaginables.

### Fase 5: Automatización madura en escenarios seguros
**Qué significa:** Se habilita al bot para que dé pasos más allá en la venta (como el seguimiento automático o la confirmación directa) *únicamente* en aquellos flujos y productos donde ha demostrado, con datos, ser completamente confiable.
**Por qué es importante:** Maximiza la velocidad de venta y la conversión sin sumar riesgo, automatizando solo lo que ya sabemos que el sistema domina a la perfección.
**Qué esperar:** Un bot que, para ciertos productos o tipos de clientes recurrentes, puede llegar a avanzar la venta de forma casi independiente, haciendo seguimientos inteligentes ("Vi que consultaste por pintura ayer, ¿pudiste decidirte?").
**Qué NO esperar:** No se automatizará a ciegas todo el negocio. No se pretenderá que el bot cierre de forma autónoma operaciones críticas o complejas donde el criterio humano siga siendo vital. Tampoco es el momento de adaptar el sistema para vender otros rubros distintos a la ferretería.

# Por qué lo estamos haciendo así

El desarrollo de software con Inteligencia Artificial aplicado a negocios reales conlleva riesgos importantes si se hace de forma apresurada. Si intentáramos construir un bot 100% autónomo desde el día uno, estaríamos exponiendo a la ferretería a presupuestos erróneos, ventas de productos sin stock y mala atención al cliente.

Al avanzar bloque por bloque —asegurando primero que el bot sepa cotizar, luego que entienda profundamente el rubro, luego que pueda ser entrenado y recién al final dándole autonomía— garantizamos que cada paso que da el sistema aporta valor real al negocio de forma predecible y segura. Construimos confianza tanto en el equipo humano que usa la herramienta como en el cliente final que interactúa con ella.

# Qué puede esperar el cliente en términos reales

El crecimiento del bot no será un salto mágico de cero a experto en una semana. La progresión realista que experimentará el negocio será la siguiente:

1. **Primero, una herramienta útil:** Un asistente que quita trabajo manual, responde rápido y organiza los pedidos para que los vendedores los cierren de forma ordenada.
2. **Luego, un asistente experto en el dominio:** Un bot que ya no hace preguntas obvias y domina el catálogo, las medidas y las variantes propias del rubro ferretero casi tan bien como un empleado nuevo.
3. **Después, un sistema entrenable:** Una plataforma que el mismo equipo puede ir puliendo día a día con casos reales, haciendo que el conocimiento de la empresa quede plasmado en el sistema mes a mes.
4. **Finalmente, un asistente con autonomía responsable:** Un copiloto que asume la carga pesada de las ventas rutinarias de inicio a fin de forma confiable, llamando a los humanos solo cuando la situación requiere experiencia comercial avanzada.

# Versión corta para enviar por WhatsApp

Hola. Te comparto un breve resumen del enfoque de trabajo con el bot de ventas. 

El bot ya está operativo en su Fase 1: atiende, consulta el stock real, arma presupuestos y se los deja servidos al equipo para que los revisen y cierren. También estamos avanzando en la Fase 2, haciéndolo mucho más experto en distinguir variantes (medidas, cajas vs. unidades) y entender cómo pide las cosas la gente en el mostrador.

Nuestro plan tiene 5 fases. No buscamos un "robot mágico" que el primer día intente cobrar solo y cometa errores con tu mercadería. Vamos paso a paso:
1️⃣ Asistente operativo que deriva todo a revisión humana (Ya funcionando).
2️⃣ Bot experto en conocimiento ferretero real (En progreso).
3️⃣ Sistema que tu equipo pueda "entrenar" corrigiendo sus errores de a poco.
4️⃣ Un copiloto robusto que resuelva lo habitual y solo te pase los casos difíciles.
5️⃣ Automatización de ventas enteras solo en los productos y casos donde ya haya demostrado 100% de seguridad.

Avanzando de esta manera nos aseguramos de que el software trabaje *para* el equipo de ventas, ahorrándoles tiempo sin poner en riesgo la atención al cliente ni el inventario.
