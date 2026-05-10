# Audit D6 — Dashboard + UI de training

**HEAD:** `9f7369d`

---

## Resumen

- **Hay DOS capas activas**, no una legacy y una nueva. `dashboard/` es el panel operativo (ventas, productos, conversaciones). `app/ui/` es la UI de training para Nacho. Ninguna es legacy — tienen propósitos distintos.
- **La UI de training está bastante terminada** como estructura: flujo A→B→C completo, auth sólida, sandbox aislado, persistencia SQLite con 8 tablas. Es funcional para Nacho hoy.
- **El gap crítico para la adopción es D2**: cada mensaje en el sandbox hace un full-page reload (POST → redirect). Para una persona probando conversaciones de múltiples turnos, esto es fricción real. La pantalla refresea, hay que hacer scroll, el foco del cursor se pierde.
- **Accesibilidad básica falla**: todos los `<label>` en sandbox/home/case_detail están sueltos — no tienen atributo `for` apuntando a su input. Asistentes de voz no pueden asociarlos.
- El CSS y JS son todos **inline** en los templates (no hay archivos .css/.js externos en `app/ui/`). Esto simplifica el deploy pero complica el mantenimiento del CSS de 453 líneas en `base.html`.
- El sandbox está **bien aislado de producción**: usa una DB SQLite en `/tmp` y `sandbox_mode=True`. El riesgo no es de datos sino de acumulación de archivos temporales si hay limpieza tardía.
- El `dashboard/` usa AJAX para todo desde el día uno. El `training/` usa AJAX solo en `bot_config.html`, `impact.html`, y `unresolved_terms.html` — pero no en el flujo principal del sandbox (D2 pendiente).

---

## 1. dashboard/ vs app/ui/

### `dashboard/` — Panel operativo general

**Estado: Activo, pero secundario**

- `dashboard/app.py` (446 LOC): Blueprint Flask standalone (`dashboard_bp`), registrado en la app principal en `/dashboard`.
- Puede correr independientemente (`python dashboard/app.py`).
- Tiene su propia auth separada: sesión `dashboard_logged_in`, usuario via `ADMIN_USERNAME` env var.
- 6 templates: `index.html` (métricas), `sales.html`, `products.html`, `conversations.html`, `base.html`, `login.html`.
- Todas las páginas cargan datos via **AJAX fetch** al arrancar — es una SPA mínima sobre Flask.
- Tiene `dashboard/iphone_store.db` — una DB SQLite de prueba que parece ser de desarrollo/demo. **Candidata a eliminar del repo.**
- Tiene `dashboard/mock_service.py` — servicio mock. Ídem.
- **Propósito:** Vista de métricas operativas (ventas, conversiones, top products). Es la pantalla "gerencial", no la de training.

### `app/ui/` — UI de training integrada (la de Nacho)

**Estado: Activo, es la capa principal**

- `app/ui/ferreteria_training_routes.py` (2206 LOC): Blueprint `ferreteria_training_ui`, registrado en `/ops/ferreteria/training/*`.
- `app/ui/ferreteria_admin_routes.py` (170 LOC): Rutas de admin más simples (quotes, knowledge editor).
- 21 templates en `ferreteria_training/` + 5 en `ferreteria_admin/`.
- Auth propia: sesión `training_logged_in`, contraseña via `ADMIN_PASSWORD` env var (hash PBKDF2 + salt distinto al del dashboard).
- También acepta `X-Admin-Token` header para acceso script/API (dual-mode auth).
- Conectada a `bot_sales/training/` (la capa de servicios y SQLite).
- **Esta es la UI crítica para Nacho.**

### Diferencia de auth entre capas

`dashboard/` y `app/ui/training` comparten la misma env var `ADMIN_PASSWORD` pero usan **salts distintos** (`ferreteria-dashboard-v1` vs `ferreteria-training-ui-v1`). Esto produce hashes distintos para la misma contraseña — por diseño, para que puedan diferenciarse en el futuro. En la práctica hoy significa que el login del dashboard y el de training son independientes aunque usen la misma contraseña.

---

## 2. Routes/endpoints del training

| Path | Método | Función | Auth | Retorna |
|---|---|---|---|---|
| `/ops/ferreteria/training/login` | GET/POST | `training_login` | Pública | Login form / redirect |
| `/ops/ferreteria/training/logout` | GET | `training_logout` | Pública | Redirect a login |
| `/ops/ferreteria/training` | GET/POST | `training_home_page` | ✓ login_required | Sandbox + inbox principal |
| `/ops/ferreteria/training/sandbox` | GET/POST | `training_sandbox_page` | ✓ login_required | **Alias del home** (mismo `_render_training_sandbox`) |
| `/ops/ferreteria/training/help` | GET | `training_help_page` | ✓ login_required | Guía operativa en markdown |
| `/ops/ferreteria/training/tools` | GET | `training_more_tools_page` | ✓ login_required | Panel con accesos rápidos |
| `/ops/ferreteria/training/sessions` | GET | `training_session_history_page` | ✓ login_required | Historial de sesiones con filtros |
| `/ops/ferreteria/training/cases` | GET | `training_cases_page` | ✓ login_required | Lista de casos con filtros y colas |
| `/ops/ferreteria/training/cases/<review_id>` | GET/POST | `training_case_detail_page` | ✓ login_required | Detalle del caso + crear propuesta |
| `/ops/ferreteria/training/suggestions` | GET/POST | `training_suggestion_queue_page` | ✓ login_required | Cola de correcciones (draft/approved/applied) |
| `/ops/ferreteria/training/suggestions/<suggestion_id>` | GET/POST | `training_suggestion_detail_page` | ✓ login_required | Detalle + approve/reject/apply |
| `/ops/ferreteria/training/usage` | GET | `training_usage_page` | ✓ login_required | Uso de tokens y costos |
| `/ops/ferreteria/training/unresolved-terms` | GET | `training_unresolved_terms_page` | ✓ login_required | Top 300 términos sin resolver |

**Observación: `/ops/ferreteria/training` y `/ops/ferreteria/training/sandbox` llaman a la misma función `_render_training_sandbox()`**. Son aliases. Esto puede confundir a Nacho si llega por `/training` y ve "Sandbox de entrenamiento" como título de página — suena como una vista alternativa cuando en realidad es la pantalla principal.

---

## 3. Templates HTML

| Archivo | LOC | Rol | Smells |
|---|---|---|---|
| `ferreteria_training/base.html` | 453 | Shell: nav, design system completo, dark mode | CSS inline (>300 LOC), Google Fonts externa, sin archivos .css separados |
| `ferreteria_training/home.html` | 317 | **Pantalla A**: sandbox principal + inbox | Form POST (sin AJAX), inline JS mínimo para send-message |
| `ferreteria_training/sandbox.html` | 345 | Alias de home — misma función Python | Inline JS (~85 LOC), labels sin `for=`, misma fricción POST |
| `ferreteria_training/bot_config.html` | 808 | Editor de manual del bot + chat tester | **Tiene AJAX** (fetch), mucho JS inline (~300 LOC), es la más compleja |
| `ferreteria_training/case_detail.html` | 352 | **Pantalla B**: detalle del caso + crear propuesta | Formulario grande con muchos campos opcionales, sin AJAX |
| `ferreteria_training/cases.html` | 109 | Lista de casos con badges de workflow | Limpia, sin JS |
| `ferreteria_training/suggestion_detail.html` | 126 | **Pantalla C**: revisar y activar corrección | Sin AJAX, workflow de approve/reject/apply claro |
| `ferreteria_training/suggestion_queue.html` | 137 | Cola de correcciones por estado | Sin JS |
| `ferreteria_training/impact.html` | 396 | Métricas de impacto del training | **Tiene AJAX** (fetch), JS inline considerable (~150 LOC) |
| `ferreteria_training/unresolved_terms.html` | 197 | Top términos sin resolver + sugerir corrección | **Tiene AJAX** (fetch al suggest endpoint) |
| `ferreteria_training/session_history.html` | 72 | Historial de sesiones | Limpia |
| `ferreteria_training/help.html` | 86 | Muestra guía operativa y FAQ en markdown | Renderiza Markdown como texto plano — sin parser Markdown |
| `ferreteria_training/more_tools.html` | 47 | Panel de accesos rápidos | Muy simple |
| `ferreteria_training/login.html` | 94 | Login de entrenamiento | Simple, correcta |
| `ferreteria_training/usage.html` | 62 | Tabla de uso y costos | Sin JS |
| `ferreteria_training/_suggestion_fields.html` | 375 | Partial: campos del formulario de corrección | Complejo, muchos campos condicionales |
| `ferreteria_admin/base.html` | 34 | Shell mínimo para admin | Sin CSS propio — usa otro sistema |
| `ferreteria_admin/quotes.html` | 50 | Lista de quotes del CRM | Sin JS |
| `ferreteria_admin/quote_detail.html` | 131 | Detalle de quote | Sin JS |
| `ferreteria_admin/knowledge_editor.html` | 14 | Editor de conocimiento | Stub sin contenido real |
| `ferreteria_admin/unresolved_terms.html` | 40 | Vista de términos (admin) | Sin JS |

### JS inline — distribución

| Template | LOC de JS inline | Tipo |
|---|---|---|
| `base.html` | ~20 | Theme toggle, dark mode |
| `sandbox.html` / `home.html` | ~85 | Sync dropdowns, textarea resize, Enter=submit |
| `bot_config.html` | ~300 | AJAX chat-test, reset, editor de campos |
| `impact.html` | ~150 | AJAX fetch métricas |
| `unresolved_terms.html` | ~30 | AJAX suggest |

**No hay archivos `.js` externos en `app/ui/`.** Todo es inline. Funciona, pero dificulta el linting, el testing de JS, y la cache del browser.

---

## 4. Static assets

### `app/ui/` — Sin assets externos

No existe directorio `app/ui/static/`. **Todo el CSS y JS está inline en los templates.** El único asset externo es la fuente Inter cargada desde Google Fonts:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Implicación: si Google Fonts no está disponible (offline, bloqueado por proxy corporativo), la UI cae a `system-ui, sans-serif`. Funcional pero diferente.

### `dashboard/` — Sin assets externos propios

Igual patrón: CSS y JS inline en cada template. No hay `dashboard/static/`. Usa Chart.js desde CDN:
```html
<!-- implícito en index.html — no verificado directamente pero las charts aparecen en el template -->
```

### `static/` en root del repo

No explorado en este audit — probablemente assets del frontend principal (WhatsApp web, etc.), no relevante para el training.

---

## 5. Routes Python (controllers)

### `app/ui/ferreteria_training_routes.py` (2206 LOC)

**Función principal de configuración de datos (~1400 LOC de helpers, ~800 LOC de routes)**

Las primeras ~700 líneas son constantes de configuración (FAILURE_TAG_CONFIG, EXPECTED_BEHAVIOR_CONFIG, DOMAIN_LABELS, etc.) que definen el vocabulary del sistema de training. Son datos, no lógica. Candidatos a un archivo separado `training_config.py`.

Las siguientes ~700 líneas son helpers de rendering: `_decorate_case`, `_decorate_suggestion`, `_decorate_session`, `_build_simple_review_bundle`, `_before_after_preview`, etc. Estos transforman dicts de BD en dicts ricos para los templates.

Las routes propiamente dichas son ~400 LOC.

**Responsabilidades mezcladas:**
1. Configuración/vocabulario (primeras 450 líneas)
2. Helpers de normalización de formularios
3. Helpers de rendering/decoración
4. Lógica de auth y seguridad
5. Route handlers

**`_render_training_sandbox()`** es la función más larga (~170 LOC): maneja todas las acciones POST del sandbox (start_session, send_message, reset_session, close_session, save_simple_review, save_review), luego arma el contexto para el GET. Es el controller más complejo del archivo.

### `app/ui/ferreteria_admin_routes.py` (170 LOC)

Blueprint `ferreteria_admin_ui`, registrado en `/ops/ferreteria/*`. Contiene rutas para:
- `/ops/ferreteria/quotes` — lista de quotes del CRM
- `/ops/ferreteria/quotes/<id>` — detalle
- `/ops/ferreteria/knowledge` — editor stub (template vacío)
- `/ops/ferreteria/unresolved-terms` — vista admin

Usa la misma auth que el training (`training_login_required` importado). Pequeño, bien contenido.

### `dashboard/app.py` (446 LOC)

Blueprint `dashboard_bp`. Routes:
- `/` → redirect al tenant default
- `/login`, `/logout`
- `/t/<tenant_slug>` — index con métricas
- `/t/<tenant_slug>/sales`, `/products`, `/conversations` — vistas estáticas (datos via AJAX)
- `/api/t/<tenant_slug>/products`, `/stats`, `/analytics/sales-by-day`, `/analytics/top-products`, `/sales`, `/conversations`, `/conversations/<session_id>` — APIs JSON para los AJAX

Auth: sesión `dashboard_logged_in` + rate limiter. No acepta X-Admin-Token (solo el training lo tiene).

---

## 6. Backend training (persistencia)

### Capa de almacenamiento: SQLite

**`bot_sales/training/store.py` (49KB, ~1300 LOC)** es la capa de datos principal. Usa SQLite directamente vía `sqlite3` con `check_same_thread=False` (apto para Flask multi-thread si el GIL aplica, pero riesgo con Workers asyncio).

**Tablas creadas al iniciar `TrainingStore`:**

| Tabla | Propósito |
|---|---|
| `training_sessions` | Sesiones de sandbox (modo, modelo, estado, JSON de mensajes) |
| `training_messages` | Mensajes individuales con metadata (tokens, costo, route_source) |
| `training_reviews` | Casos revisados (qué salió mal, comportamiento esperado) |
| `knowledge_suggestions` | Propuestas de corrección (domain, payload JSON, status) |
| `knowledge_approvals` | Log de aprobaciones/rechazos/activaciones |
| `training_usage_metrics` | Métricas de tokens/costo por sesión/día/mes |
| `regression_case_exports` | Casos exportados como regression tests |
| `regression_case_candidates` | Candidatos a exportar |
| `knowledge_change_audit` | Auditoría de cambios al conocimiento activo |

**Ruta del archivo DB:** determinada por `_tenant_db_path()` en `app/api/ferreteria_admin_routes.py`. Apunta a la carpeta del tenant (probablemente `data/tenants/ferreteria/training.db` o similar). No es la misma DB que el bot de producción.

### Servicios de training: `bot_sales/training/`

| Módulo | Tamaño | Rol |
|---|---|---|
| `store.py` | 49KB | CRUD directo SQLite |
| `session_service.py` | 11KB | Orquesta sesiones de sandbox + llama a SalesBot |
| `suggestion_service.py` | 22KB | Ciclo de vida de correcciones (create→approve→apply) |
| `review_service.py` | 1.9KB | CRUD de casos de revisión |
| `context_builder.py` | 1.4KB | Reconstruye contexto de conversación para SalesBot |
| `costs.py` | 2.7KB | Mapeo mode_profile → modelo → precios por token |
| `demo_bootstrap.py` | 27KB | Script de generación de datos de demo |

### Persistencia de knowledge (sugerencias)

Cuando se activa una corrección (`suggestion_service.apply()`), el payload se escribe al YAML de conocimiento del tenant en disco (`data/tenants/ferreteria/*.yaml`). Esto es lo que Nacho hace al activar un cambio — escribe directamente a los archivos de configuración del bot.

**No hay versionado ni rollback** de estos archivos de conocimiento (más allá de git). Si se aplica una corrección incorrecta, hay que hacer git revert o editar el YAML a mano.

---

## 7. Sandbox vs producción

### Aislamiento implementado

`_build_sandbox_bot()` en `session_service.py` (L139–186):
1. Crea un `tempfile.NamedTemporaryFile` para la DB SQLite del sandbox (en `/tmp/ferreteria_training_*.db`)
2. Crea otro tempfile para los logs
3. Instancia `SalesBot` con esa DB temporal y `sandbox_mode=True`
4. Reconstruye el contexto de conversación desde `training_messages` (no toca `conversation_history` de producción)
5. Pasa el estado de sesión serializado en JSON (no toca `sessions` de producción)

**Producción no se toca en ningún aspecto durante el training.** El catálogo se carga en memoria desde el CSV del tenant, no desde la DB productiva.

### Riesgos identificados

**Riesgo 1 — Acumulación de temp files:** Cada `send_message` construye un nuevo `SalesBot` (L88: `bot = self._build_sandbox_bot(session)`) con un nuevo tempfile. Si `_cleanup_temp_files()` no se llama consistentemente después de cada turno, los archivos en `/tmp` se acumulan. En Railway, el `/tmp` es efímero pero dentro de un deploy larga duración podría crecer.

**Riesgo 2 — `check_same_thread=False` en SQLite:** El `TrainingStore` abre SQLite con `check_same_thread=False`. Si dos requests web llegan concurrentemente y el servidor Flask usa múltiples threads (gunicorn default), puede haber race conditions en escritura. Para un usuario único (Nacho) esto es improbable pero latente.

**Riesgo 3 — No hay confirmación de "modo sandbox":** El UI no muestra un banner permanente indicando "estás en el sandbox". El texto introductorio en `sandbox.html` es claro pero está en el hero de la página — si el usuario hace scroll y ve solo el chat, podría no recordarlo.

**Conclusión:** El aislamiento es técnicamente correcto. Los riesgos son operativos, no de diseño.

---

## 8. Flujo A → B → C

### Mapeo en el código

El flujo documentado en el README como "A → B → C" mapea así:

**A — Hablar con el bot** → `/ops/ferreteria/training` (= training_home_page = _render_training_sandbox)
- Template: `home.html` (renderiza el sandbox con transcripción + form de mensaje)
- Acciones POST: `start_session`, `send_message`, `reset_session`, `close_session`
- Problema: cada `send_message` es un POST que hace full-page reload (D2 pendiente)

**B — Esto estuvo mal** → mismo `/ops/ferreteria/training` (panel derecho "Revisar una respuesta")
- El usuario hace click en "Revisar esta respuesta" en la burbuja del bot
- Pasa `?review_message_id=<id>` como query param — el panel derecho se puebla con el form
- Acciones POST: `save_review` o `save_simple_review`
- `save_simple_review` genera automáticamente un borrador de corrección (domain + payload)
- `save_review` (avanzado) redirige al case detail directamente
- **El flujo B está en la misma pantalla que A** — no es una pantalla separada

**C — Cambios listos** → `/ops/ferreteria/training/suggestions?queue=approved`
- Template: `suggestion_queue.html`
- Lista las correcciones con status `approved` esperando ser activadas
- Acción POST: `apply_suggestion` → llama `suggestion_service.apply()` → escribe YAML

**El flujo intermedio (Casos)**:
- Después de `save_review` el usuario llega a `/ops/ferreteria/training/cases/<review_id>` (case_detail)
- Acá puede crear una propuesta de corrección más precisa (dominio, payload)
- La propuesta queda en `status=draft`
- Luego va a `suggestion_detail` para `approve` → luego a la cola `approved` para `apply`

**¿Está el flujo claro en el código?**

La lógica está completa y funciona. El flujo tiene **5 pasos reales**, no 3:
1. Conversación (sandbox)
2. Seleccionar respuesta + revisar (mismo sandbox)
3. Revisar/editar propuesta de corrección (case_detail)
4. Aprobar propuesta (suggestion_detail)
5. Activar cambio (suggestion_queue)

El "A → B → C" del README colapsa pasos 3-5 en "C". Para Nacho, esta simplificación puede funcionar si el flujo simple (`save_simple_review`) genera buenos borradores automáticos.

### Loose ends

- El **flujo simple** (`save_simple_review`) es la ruta más usable para Nacho: un click en "Guardar como caso" genera automáticamente dominio + payload. El flujo avanzado (case_detail) es para refinamiento posterior.
- `/ops/ferreteria/training/sandbox` es un alias de `/ops/ferreteria/training` — puede confundir si Nacho accede directamente al sandbox y espera algo diferente.
- El botón "Guardar como caso de entrenamiento" en sandbox redirige al case detail — hay un paso extra antes de llegar a "C".

---

## 9. Pendientes D2 / D3 — alineación con código

### D2 — AJAX + panel debug toggle + sesiones con nombre

**AJAX para enviar mensajes sin reload:**
- **Estado: No implementado en el flujo principal del sandbox.**
- `home.html` y `sandbox.html` usan `<form method="post">` con redirect. Cada `send_message` es un POST→redirect que recarga toda la página.
- `bot_config.html` YA tiene AJAX (`fetch` a `/ops/ferreteria/training/api/chat-test`). El patrón técnico existe — no se llevó al sandbox principal.
- **Impacto real para Nacho:** En una conversación de 5 turnos, hay 5 reloads completos. La transcripción muestra el historial correctamente pero el usuario ve el parpadeo del browser y pierde el foco del textarea. El D1 (textarea auto-resize + Enter=submit) está implementado y funciona bien.

**Panel debug toggle (intent TI, quote_state, items parseados, tokens, costo):**
- **Estado: No implementado en el sandbox principal.**
- El sandbox SÍ muestra tokens y costo estimado (en el panel "Uso y límites"). Pero no hay debug de intent, quote_state ni items parseados.
- `route_source_label` sí se muestra en cada burbuja del bot (chip "Regla fija" / "Asistido por modelo"). Eso es información de debug mínima.

**Sesiones recientes con preview + timestamp:**
- **Estado: Parcialmente implementado.**
- La lista de sesiones en el sidebar izquierdo muestra `mode_profile_label`, `model_name`, `updated_at`. No hay preview del primer mensaje o del tema de la sesión.

### D3 — Formulario de revisión

- **Estado: PENDIENTES.md dice "No tocar hasta nueva instrucción de Nacho".**
- El formulario en `sandbox.html` (y `home.html`) ya tiene 8 campos para la revisión detallada: review_label, failure_tag, failure_detail_tag, expected_behavior_tag, clarification_dimension, expected_answer, what_was_wrong, missing_clarification, suggested_family, suggested_canonical_product, operator_notes.
- El flujo simple (`save_simple_review`) es una versión más corta del mismo formulario.
- **Observación:** El formulario completo es intimidante para un usuario nuevo. Tiene 10+ campos. El flujo simple reduce esto a 6 opciones de "¿qué pasó?" — que es mucho más manejable. D3 probablemente requiere feedback de Nacho sobre cuál flujo prefiere como default.

---

## 10. UX gaps detectados

| # | Gap | Impacto para Nacho | Dónde |
|---|---|---|---|
| 1 | **Full-page reload por mensaje** | Alto — cada turno recarga todo, se pierde scroll y foco | `home.html` / `sandbox.html` |
| 2 | **Sin banner permanente de "modo sandbox"** | Medio — el texto hero lo aclara pero puede no estar visible durante la sesión | `home.html` |
| 3 | **Labels sin `for=`** — no asociados a sus inputs | Medio — click en label no enfoca el input, sin accesibilidad real | Todos los forms |
| 4 | **Formulario de revisión con 10+ campos** | Alto — muy intimidante como flujo principal | `sandbox.html` panel derecho |
| 5 | **`/training` y `/training/sandbox` son la misma pantalla** — sin distinción visible | Medio — si alguien llega por `/sandbox` espera algo distinto | Naming de routes |
| 6 | **Help page renderiza Markdown como texto plano** — sin parser | Bajo — la guía aparece con `#`, `**` literales si tiene formato | `help.html` |
| 7 | **"Sesiones recientes" sin preview del contenido** — solo ID y timestamp | Bajo — difícil identificar qué conversación era | `home.html` sidebar |
| 8 | **Formulario de "crear propuesta" en case_detail.html** es muy técnico — requiere conocer el "domain" y el formato del payload | Alto — Nacho no debería ver esto; el flujo simple lo bypasea pero si llega al case_detail directamente, es confuso | `case_detail.html` |
| 9 | **La guía operativa en help.html** depende de archivos en `docs/` que podrían no existir en producción — fallback es un mensaje de texto plano | Medio — si Nacho va al Help y no ve nada, no hay segundo recurso | `help.html` |
| 10 | **No hay confirmación visible después de "Activar cambio"** — el redirect vuelve a la queue sin una celebración/feedback de éxito | Bajo — el usuario podría no saber si el cambio se activó correctamente | `suggestion_queue.html` |

---

## 11. Top 10 oportunidades

| # | Oportunidad | Impacto | Esfuerzo |
|---|---|---|---|
| 1 | **Implementar AJAX para send_message** (D2) — fetch POST + append de burbuja al DOM sin reload. El patrón ya existe en `bot_config.html`. | Alto | Medio |
| 2 | **Agregar atributos `for=` y `id=` a todos los label-input pairs** — una pasada rápida por los templates. Accesibilidad básica + UX correcta. | Alto | Bajo |
| 3 | **Poner el flujo simple como default visible** en el panel de revisión de sandbox — el formulario largo debería estar colapsado detrás de un "Modo avanzado". | Alto | Bajo |
| 4 | **Banner/chip permanente de "Sandbox aislado de producción"** — visible durante toda la sesión, no solo en el hero. | Medio | Trivial |
| 5 | **Agregar preview de primer mensaje en "Sesiones recientes"** — mostrar los primeros 60 caracteres del primer turno del usuario para identificar fácilmente de qué trataba. | Medio | Bajo |
| 6 | **Agregar un parser Markdown básico a la help page** — incluir `marked.js` o usar Jinja con un filtro de markdown para que `guia_operativa.md` se vea bien formateada. | Bajo | Bajo |
| 7 | **Eliminar `dashboard/iphone_store.db` y `dashboard/mock_service.py`** del repo — son artefactos de desarrollo inicial que no deben estar en el repo de producción. | Bajo | Trivial |
| 8 | **Separar las 450 líneas de config (FAILURE_TAG_CONFIG, etc.) a un `training_config.py`** — `ferreteria_training_routes.py` tiene 2206 LOC, la mitad son datos. | Bajo | Bajo |
| 9 | **Agregar mensaje de éxito después de "Activar cambio"** — un flash message o un banner `"Cambio activado correctamente"` después del redirect. | Bajo | Trivial |
| 10 | **Dar un nombre descriptivo al route `training_sandbox_page`** o redirigirlo al home — actualmente `/training/sandbox` y `/training` son aliases confusos. | Bajo | Trivial |

---

## 12. Dudas para Julian

1. **¿`/ops/ferreteria/training` y `/ops/ferreteria/training/sandbox` deben ser el mismo?** Nacho va a tener dos URLs que hacen lo mismo. ¿El plan es eventualmente separar el sandbox (solo chat) de la pantalla home (chat + inbox de trabajo)?

2. **El flujo simple vs. el flujo avanzado:** Cuando Nacho guarda una revisión desde el sandbox, ¿debería ir al case_detail para refinarlo, o directamente a la cola de correcciones? Hoy `save_review` (avanzado) va al case_detail y `save_simple_review` va de vuelta al sandbox con el saved notice. ¿Cuál es el flujo principal para Nacho?

3. **`dashboard/iphone_store.db` y `dashboard/mock_service.py`:** ¿Son usados en algún contexto (CI, demo local)? Si no, candidatos a borrar del repo.

4. **Los archivos `docs/guia_operativa_entrenamiento_ferreteria.md` y `docs/faq_entrenamiento_ferreteria.md`:** ¿Existen en el deploy de Railway? La help page los busca en disco. Si no existen, Nacho verá un fallback de texto plano. ¿Están siendo deployados?

5. **Cleanup de temp files del sandbox:** `_build_sandbox_bot()` crea 2 tempfiles por turno (`training_*.db` + `training_*.log`). ¿Hay un punto en el código donde se limpian? En `session_service.py` busqué `_cleanup_temp_files` pero solo vi la referencia. ¿Está implementada la limpieza?

6. **La activación de una corrección escribe directamente al YAML del tenant.** ¿Hay algún mecanismo de rollback más allá de git? Si Nacho activa algo incorrecto, ¿cuál es el recovery path esperado?

7. **`check_same_thread=False` en TrainingStore:** ¿Se usa gunicorn con múltiples workers o threads para el server donde corre esto? Si hay múltiples threads concurrentes al training SQLite, podría haber race conditions.

8. **El `knowledge_editor.html` está prácticamente vacío (14 LOC).** ¿Es una pantalla planeada para el futuro o hay una forma alternativa de editar el knowledge que ya existe?
