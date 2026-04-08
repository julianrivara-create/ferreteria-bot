# Ferretería Juli
## Documento de estado actual

Fecha: 2026-03-17  
Proyecto evaluado: `/Users/julian/Desktop/Cerrados/Ferreteria`

Nota de contexto: en la base técnica del proyecto todavía aparecen referencias internas a **"Ferreteria Central"**. Eso responde al origen del desarrollo y no cambia el objetivo actual del bot, que en esta presentación se toma como **Ferretería Juli**.

## 1. Objetivo del bot

El bot fue pensado para ayudar a una ferretería a atender consultas comerciales por canales conversacionales, principalmente:

- terminal interna de prueba,
- WhatsApp,
- y, a futuro, otros canales si hiciera falta.

La meta del sistema es que un cliente pueda escribir qué necesita para una compra puntual, una reparación o una obra, y que el bot pueda:

- entender el pedido,
- ubicar productos del catálogo,
- armar una cotización preliminar,
- pedir aclaraciones cuando falta información,
- y dejar listo el paso siguiente para que el equipo comercial termine de cerrar la operación.

## 2. Estado actual en una frase

Hoy el bot ya funciona como un **asistente comercial de ferretería orientado a cotización preliminar**, con capacidad real para responder consultas, buscar productos del catálogo y armar presupuestos simples. Todavía no está en un punto de operación plena para casos complejos o de alta variedad de materiales.

## 3. Qué hace hoy

Actualmente el bot puede:

- responder preguntas frecuentes sobre pagos, facturación, envíos, cambios y garantía,
- mostrar opciones por rubro o categoría,
- reconocer algunos pedidos concretos de productos,
- armar presupuestos preliminares con uno o más ítems simples,
- pedir aclaraciones cuando un producto es ambiguo,
- agregar productos a una cotización ya iniciada,
- reiniciar una cotización,
- y registrar términos que no pudo resolver para mejorar el sistema en iteraciones futuras.

En términos prácticos, hoy sirve bien para:

- consultas comerciales básicas,
- atención inicial,
- exploración de catálogo,
- y cotizaciones preliminares supervisadas.

## 4. Cómo está construido hoy

El proyecto funciona hoy como un bot separado, dedicado al caso ferretería, dentro de una carpeta independiente:

- `/Users/julian/Desktop/Cerrados/Ferreteria`

Los dos puntos de entrada principales son:

- `bot_cli.py` para pruebas por terminal
- `whatsapp_server.py` para el canal WhatsApp

El sistema trabaja con un tenant específico de ferretería, lo que permite que el bot cargue:

- su catálogo,
- sus políticas,
- sus FAQs,
- y su identidad comercial.

En la práctica, esto significa que el bot no responde como un vendedor genérico, sino que ya fue reorientado al rubro ferretería.

## 5. Cómo genera respuestas

El flujo actual combina dos capas:

### 5.1. Lógica específica de ferretería

Para los casos más importantes, el bot no depende solamente de inteligencia artificial abierta, sino de reglas concretas armadas para este negocio. Esa lógica le permite:

- detectar si el cliente está pidiendo productos,
- separar algunos pedidos con varios ítems,
- buscar coincidencias en catálogo,
- pedir precisiones cuando algo no alcanza,
- y devolver una respuesta estructurada.

### 5.2. Capa conversacional general

Además de esas reglas, el proyecto conserva una capa conversacional más general que puede usar herramientas internas y, si está configurada la API correspondiente, apoyarse en modelos de lenguaje para completar respuestas.

En otras palabras:

- lo más sensible para cotización hoy se apoya en lógica controlada,
- y la capa de IA queda como soporte conversacional, no como único motor.

Eso es positivo porque reduce respuestas inventadas, aunque todavía no elimina del todo los límites propios de un sistema en evolución.

## 6. Dónde vive la información del bot

La información principal del bot hoy está repartida en varias fuentes simples y editables:

- catálogo de productos en CSV,
- preguntas frecuentes en JSON,
- políticas comerciales en Markdown,
- perfil del negocio en YAML,
- branding en JSON,
- y una base SQLite para operación y persistencia local.

Esto permite trabajar rápido y con bajo costo técnico, pero todavía no ofrece una experiencia de edición centralizada para usuarios no técnicos.

## 7. Cómo se prueba hoy

El proyecto ya cuenta con validaciones y pruebas concretas:

- validación de estructura del tenant,
- smoke test del flujo principal,
- suite de tests focalizados del bot de ferretería,
- y pruebas reales por terminal a través del flujo conversacional.

Eso significa que no estamos frente a un prototipo únicamente conceptual: ya existe una base testeada que permite iterar con cierto control.

## 8. Qué funciona bien hoy

Los puntos más sólidos del estado actual son:

- enfoque ferretería ya aplicado,
- atención por producto antes que por preguntas comerciales genéricas,
- FAQs resolviendo rápido,
- cotización preliminar simple funcionando,
- continuidad básica de una conversación de presupuesto,
- y registro de casos no resueltos para mejorar el sistema con datos reales.

También es importante remarcar que el bot hoy ya puede dar respuestas útiles sin depender de una web pública como canal principal.

## 9. Limitaciones actuales

Aunque la base es real y útil, todavía hay límites importantes para una operación comercial más exigente.

Hoy las principales limitaciones son:

- catálogo todavía chico para una ferretería real,
- resolución de productos todavía frágil cuando el pedido es amplio o técnico,
- alternativas todavía mejorables,
- aceptación y cierre de venta todavía no integrados de punta a punta como flujo operativo completo,
- edición del conocimiento todavía dependiente del equipo técnico,
- y ausencia de una interfaz administrativa clara para enseñar o corregir el bot sin tocar código.

En resumen:

- el bot ya sirve para iniciar atención y preparar cotizaciones preliminares,
- pero todavía no conviene presentarlo como un sistema cerrado y autónomo de presupuestación completa.

## 10. Ejemplos reales de comportamiento

### Caso que hoy funciona bien

Pedido del cliente:

`Quiero 2 siliconas y 3 teflones`

Resultado actual:

- el bot reconoce ambos productos,
- arma una cotización preliminar,
- muestra precios unitarios,
- calcula subtotales,
- y devuelve un total estimado.

### Caso que hoy funciona razonablemente bien

Pedido del cliente:

`Necesito taco fisher y mecha`

Resultado actual:

- identifica correctamente el equivalente de `taco fisher`,
- detecta que `mecha` necesita más precisión,
- pide aclaración,
- y puede continuar la cotización cuando el cliente completa la información.

### Caso que hoy resuelve con prudencia

Pedido del cliente:

`Pasame presupuesto para un baño`

Resultado actual:

- no inventa un presupuesto,
- pide rubros o lista de materiales,
- y orienta al cliente para seguir.

### Caso que hoy todavía queda corto

Pedido del cliente:

`Necesito una electroválvula industrial 3/4`

Resultado actual:

- el bot informa que no encontró coincidencia clara,
- y pide más datos.

Esto es mejor que inventar una respuesta, pero también muestra que el catálogo y la cobertura semántica todavía necesitan crecer.

## 11. Decisiones pendientes

Antes de escalar el proyecto, todavía conviene definir algunas cuestiones de negocio y producto:

- nombre final de la solución y alineación de identidad,
- fuente principal de catálogo a futuro,
- cómo se va a gestionar la mejora del conocimiento,
- qué significa exactamente “cotización aceptada” en el proceso operativo,
- cómo se deriva al equipo interno,
- y qué nivel de autonomía real se espera del bot en la primera etapa comercial.

---

# Gap Analysis

## 1. Qué falta para que el bot sea entrenable o editable por usuarios no técnicos

Hoy el bot todavía no está preparado para que una persona de negocio lo mantenga por completo sin ayuda técnica.

Para llegar a ese punto falta:

- una interfaz para editar catálogo,
- una interfaz para editar preguntas frecuentes,
- una capa simple para agregar sinónimos y términos equivalentes,
- una forma de revisar qué consultas no está entendiendo,
- y una consola de prueba para validar cambios antes de llevarlos a producción.

Hoy esos cambios todavía están distribuidos entre archivos y lógica interna del proyecto.

## 2. Qué haría falta para una interfaz de administración o enseñanza

Una interfaz útil para el negocio debería permitir:

- cargar o actualizar productos,
- marcar medidas, materiales, presentaciones y variantes,
- enseñar términos frecuentes del cliente,
- corregir respuestas ambiguas,
- revisar términos no resueltos,
- ver cotizaciones abiertas,
- y derivar casos al equipo comercial.

No hace falta pensar primero en una gran plataforma. Al principio bastaría una capa administrativa clara sobre las piezas que ya existen.

## 3. Qué partes hoy están demasiado acopladas

En este momento hay varias cosas mezcladas entre sí:

- reglas de negocio,
- lógica de cotización,
- manejo conversacional,
- formateo de respuestas,
- y conocimiento del catálogo.

Eso acelera el desarrollo inicial, pero vuelve más delicado cualquier cambio posterior. Si se toca una parte, es fácil impactar otra.

También hay un acoplamiento importante entre la lógica activa del bot y el resto del repositorio heredado, que todavía conserva piezas de la plataforma original.

## 4. Qué conviene mantener como está

Hay decisiones actuales que son buenas y conviene sostener:

- el enfoque producto-primero para ferretería,
- las respuestas FAQ por lógica directa,
- el registro de términos no resueltos,
- el uso de tests focalizados,
- y la separación actual del proyecto en una carpeta propia.

Eso da una base razonable para crecer sin rearmar todo desde cero.

## 5. Hoja de ruta lógica

### V1

Objetivo:

- consolidar una versión segura para piloto controlado.

Prioridades:

- mejorar calidad de resolución de productos,
- hacer más confiable la continuidad de cotizaciones,
- fortalecer el cierre de presupuesto para revisión humana,
- y ampliar el catálogo útil real.

### V2

Objetivo:

- volver el bot mantenible por el equipo de negocio.

Prioridades:

- interfaz de administración,
- edición de catálogo y FAQs,
- gestión de sinónimos y términos frecuentes,
- visibilidad de cotizaciones y casos no resueltos.

### V3

Objetivo:

- convertir esta solución en una base reutilizable para otros rubros o negocios.

Prioridades:

- separar mejor núcleo técnico y configuración de negocio,
- estandarizar la enseñanza del bot,
- y convertir la experiencia en una plataforma replicable.

## 6. Conclusión

El bot de Ferretería Juli hoy ya tiene valor real como base comercial asistida. No es solamente una demo: ya puede atender, responder, orientar y armar cotizaciones preliminares en escenarios acotados.

Al mismo tiempo, todavía está en una etapa donde la mejora del conocimiento, la robustez de la cotización y la operación completa siguen dependiendo de trabajo técnico y supervisión humana.

La lectura correcta del estado actual es esta:

- **sí hay una base sólida para seguir construyendo**,  
- pero **todavía no conviene presentarlo como un sistema completamente autónomo o listo para escalar sin control**.

El paso más lógico ahora es consolidar una V1 de piloto controlado con foco en:

- calidad de resolución,
- crecimiento del catálogo,
- y una capa simple de administración del conocimiento.
