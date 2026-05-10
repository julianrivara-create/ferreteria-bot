# Audit M3 — Smells y rarezas

**HEAD:** 9f7369d2e5601ba85952ac5a3af69c4f3a06e8cb
**Fecha:** 2026-05-09

---

## ⚠️ HALLAZGOS PELIGROSOS

**CLAVE DE API REAL ENCONTRADA EN `.env` LOCAL (NO commiteada, pero existe en disco):**

```
OPENAI_API_KEY=sk-proj-JpSjrNF-k...BlbkFJ... [REDACTED — clave real activa]
ADMIN_TOKEN=ferreteria-token-2024
ADMIN_PASSWORD=Aristoteles
SECRET_KEY=dev-secret-key-ferreteria-juli
```

> `.env` está correctamente en `.gitignore` y NO está commiteado. Sin embargo:
> - La clave de OpenAI es real y larga (formato `sk-proj-...`). Si este repo se sube a GitHub público, o si alguien con acceso a la máquina clona el directorio, queda expuesta.
> - `ADMIN_TOKEN` y `ADMIN_PASSWORD` son credenciales de producción con valores débiles/descriptivos.
> - **Acción recomendada:** Rotar la clave de OpenAI. Revisar si `ADMIN_PASSWORD=Aristoteles` y `ADMIN_TOKEN=ferreteria-token-2024` están en uso real en Railway u otro entorno.

---

## Resumen

- **10 TODOs reales** en código de producción (todos del 2026-04-08), duplicados entre `app/bot/` y `bot_sales/` — incluyendo un TODO crítico de "Actualizar DB según result" en el webhook de MercadoPago que implica que los pagos no actualizan la DB.
- **Clave OpenAI real** en `.env` local (no commiteada pero visible en disco). Admin token y password con valores débiles.
- **Binarios comprometidos en git:** `demo_conversacion_dificil.mp4` (8.1 MB), `docs/CLIENT_PITCH.pdf` (5.6 KB), `state/state.json` — todos rastreados por git sin LFS.
- **Bases de datos masivas NO commiteadas** en `/data/`: `ferreteria.db` 338 MB + WAL 13 MB, `ropa.db` 13 MB + WAL 39 MB, `farmacia.db` 13 MB + WAL 39 MB. Estas están en `.gitignore` pero el pattern `data/*.db` podría no cubrir subdirectorios.
- **`data/tenants/ferreteria/catalog.csv` (5.5 MB) commiteada** — archivo binario/datos grande rastreado en git.
- **`wsgi_legacy.py` commiteado** — archivo legacy activo que importa stack viejo (`bot_sales.*`) y tiene fallback string `'default-dev-key-change-in-prod'`.
- **Alta duplicación estructural** entre `app/bot/` y `bot_sales/` — mismos archivos con TODOs idénticos (`slack_files.py`, `mp_webhooks.py`, `whatsapp.py`).
- **`platform_features.pdf` (0 bytes) commiteado** — archivo vacío en git.

---

## 1. TODOs antiguos (TOP 20)

Solo se encontraron 10 TODOs/FIXMEs reales en código de producción (las demás ocurrencias son `TaskStatus.TODO` del enum ORM, no comentarios de deuda técnica). Todos tienen fecha de último cambio: **2026-04-08**.

| Archivo:Línea | Edad estimada | Texto |
|---|---|---|
| `app/bot/integrations/mp_webhooks.py:182` | 2026-04-08 (~31 días) | `# TODO: Actualizar DB según result` |
| `bot_sales/integrations/mp_webhooks.py:187` | 2026-04-08 (~31 días) | `# TODO: Actualizar DB según result` |
| `app/bot/integrations/slack_files.py:169` | 2026-04-08 (~31 días) | `# TODO: Save image to storage (S3, local, etc.)` |
| `app/bot/integrations/slack_files.py:188` | 2026-04-08 (~31 días) | `# TODO: Extract text from PDF using PyPDF2 or similar` |
| `app/bot/integrations/slack_files.py:206` | 2026-04-08 (~31 días) | `# TODO: Process Excel using pandas or openpyxl` |
| `bot_sales/integrations/slack_files.py:169` | 2026-04-08 (~31 días) | `# TODO: Save image to storage (S3, local, etc.)` |
| `bot_sales/integrations/slack_files.py:188` | 2026-04-08 (~31 días) | `# TODO: Extract text from PDF using PyPDF2 or similar` |
| `bot_sales/integrations/slack_files.py:206` | 2026-04-08 (~31 días) | `# TODO: Process Excel using pandas or openpyxl` |
| `bot_sales/core/universal_llm.py:112` | 2026-04-08 (~31 días) | `# TODO: Function calling support for open source models` |
| `bot_sales/core/performance.py:214` | 2026-04-08 (~31 días) | `# TODO: Implementar registro global de cachés` |

> **Nota crítica:** El TODO de `mp_webhooks.py` (duplicado en ambos stacks) indica que el webhook de MercadoPago recibe confirmaciones de pago pero **no las persiste en la DB**. Es deuda funcional, no cosmética.

---

## 2. Binarios commiteados

| Path | Tamaño | Recomendación |
|---|---|---|
| `demo_conversacion_dificil.mp4` | 8.1 MB | REMOVE — mover a Google Drive/Notion; añadir `*.mp4` a `.gitignore` |
| `data/tenants/ferreteria/catalog.csv` | 5.5 MB | REVIEW — si se actualiza frecuentemente, excluir de git o usar LFS |
| `config/catalog.csv` | 689 KB | REVIEW — archivo de datos grande en git |
| `docs/CLIENT_PITCH.pdf` | 5.6 KB | REVIEW — documento cliente en repo; mover a carpeta interna/Drive |
| `platform_features.pdf` | 0 B | REMOVE_NOW — archivo vacío commiteado, sin utilidad |
| `state/state.json` | 290 B | REMOVE — estado de runtime en git; añadir `state/` a `.gitignore` |
| `data/tenants/default/catalog.csv` | 3.7 KB | LOW — pequeño, aceptable si es fixture |

> Las DBs de `/data/` (338 MB `ferreteria.db`, WALs de 39 MB, etc.) NO están commiteadas — `.gitignore` funciona para ellas. Sin embargo `data/*.db` no cubre `data/tenants/ferreteria/ferreteria.db` (0 bytes, no commiteada tampoco pero el glob pattern es inconsistente).

---

## 3. Archivos vacíos / sufijos raros

**Archivos de 0 bytes:**

```
./platform_features.pdf          ← commiteado, 0 bytes
./reports/logs/maintenance.log   ← log placeholder vacío
./bot_sales/__init__.py          ← normal (módulo Python)
./dashboard/iphone_store.db      ← DB vacía (no commiteada)
./tests_finalprod/crm/__init__.py
./app/bot/__init__.py
./tests/mail/__init__.py
./bot_sales/connectors/__init__.py
./bot_sales/core/__init__.py
./bot_sales/observability/__init__.py
./bot_sales/state/__init__.py
./bot_sales/handlers/__init__.py
./app/bot/connectors/__init__.py
./data/tenants/ferreteria/ferreteria.db  ← DB vacía (no commiteada)
```

> Los `__init__.py` vacíos son normales en Python. Los que importan: `platform_features.pdf` (commiteado, 0 bytes) y `dashboard/iphone_store.db` (artifact de template generator, 0 bytes).

**Sufijos sospechosos:** ninguno encontrado (`*.bak`, `*.old`, `*.tmp`, `*.swp`, `*~`, `*.orig`).

---

## 4. Secrets hardcoded

**No se encontraron secrets hardcoded en archivos Python/YAML/JSON commiteados.** Todos los valores sensibles están correctamente referenciados como variables de entorno (`${OPENAI_API_KEY}`, `os.getenv(...)`, etc.).

**Hallazgos menores en archivos commiteados:**
- `wsgi_legacy.py:29` — fallback string `'default-dev-key-change-in-prod'` para `SECRET_KEY` (baja severidad, es un fallback explícito de dev)
- `experiments/ollama/.env.hybrid` — commiteado, contiene `OPENAI_API_KEY=your-openai-key-here` (placeholder, no real)
- `experiments/ollama/.env.ollama` — commiteado, contiene `#OPENAI_API_KEY=sk-your-key-here` (comentado, no real)
- `tenants.yaml` — número de WhatsApp de demo `+5491111111111`, `+5492222222222`, `+5493333333333` (placeholders de tenants demo)

**Hallazgo LOCAL (no commiteado) — ver sección ⚠️ arriba:**
- `.env` contiene clave OpenAI real `sk-proj-JpSjr...` [REDACTADA] y credenciales admin débiles.

---

## 5. Placeholders productivos

**MOCK mode activo condicionalmente en producción:**

| Archivo | Placeholder / Mock |
|---|---|
| `app/bot/config.py:30` | `EMAIL_MOCK_MODE = not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD])` |
| `app/bot/config.py:35` | `SHEETS_MOCK_MODE = not all([GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEET_ID])` |
| `app/bot/config.py:99` | `MP_MOCK_MODE = not MERCADOPAGO_ACCESS_TOKEN` |
| `app/bot/integrations/mercadopago_client.py:25-36` | MOCK implementation que genera `MOCK-{uuid}` en lugar de cobros reales |
| `app/bot/connectors/whatsapp.py:28,96` | Mock mode si no hay credenciales |
| `bot_sales/core/universal_llm.py:91,171` | MOCK MODE responde sin LLM backend |
| `bot_sales/core/gemini.py:53` | Gemini corre en MOCK si no hay API key |
| `bot_sales/core/chatgpt.py:54,294,409` | ChatGPT MOCK con `HOLD-MOCK-MP-999`, `PRD-MOCK-001` |

**Localhost hardcodeados en código de producción:**
- `app/bot/connectors/webchat.py:206` — `const API_URL = 'http://localhost:8080'` (en JS incrustado en Python)
- `bot_sales/connectors/webchat.py:211` — mismo patrón
- `app/core/config.py:72` — `REDIS_URL` default `redis://localhost:6379/0`

**Emails de ejemplo en código no-test:**
- `app/core/config.py:115` — `EMAIL_FROM: str = Field(default="noreply@example.com")`
- `app/bot/security/auth.py:239` — `os.getenv('ADMIN_EMAIL', 'admin@example.com')`

---

## 6. Imports legacy/deprecated

| Archivo | Import / Referencia |
|---|---|
| `wsgi.py:116` | `from wsgi_legacy import create_app as create_legacy_stack_app` — importa stack viejo en producción |
| `app/services/bot_core.py:5` | `from app.services.fallback_bot import get_fallback_service` — módulo "fallback" activo |
| `app/bot/bot_gemini.py:14` | `from .core.gemini import GeminiClient  # Changed from chatgpt` — comentario de migración |
| `app/bot/connectors/cli_gemini.py:15` | `from app.bot.bot_gemini import SalesBotGemini` — conector Gemini alternativo |
| `bot_sales/bot.py:372` | `# Bootstrap V2 state from any existing legacy keys` — migración inline de formato |
| `bot_sales/bot.py:2780` | `Load ConversationStateV2 ... upgrading from legacy format` — upgrade runtime en código |

> `wsgi_legacy.py` es el smell más grave: es un archivo de entrada alternativo completo que importa el stack viejo (`bot_sales.*`) y está commiteado y activo. El `wsgi.py` principal lo importa condicionalmente.

---

## 7. Auditoría .gitignore

**.gitignore actual cubre correctamente:**
- `.env` — correcto
- `*.db`, `*.sqlite`, `*.sqlite3` — correcto (cubre main data/)
- `__pycache__/`, `*.py[cod]` — correcto
- `logs/`, `*.log` — correcto
- `SESSION_SUMMARY_*.md` — correcto (ignorados, no commiteados)
- `.venv/`, `venv/` — correcto

**Archivos commiteados que deberían estar ignorados:**

| Archivo commiteado | Problema |
|---|---|
| `demo_conversacion_dificil.mp4` | `*.mp4` no está en `.gitignore` |
| `state/state.json` | `state/` o `state/state.json` no está en `.gitignore` |
| `platform_features.pdf` | `*.pdf` no está en `.gitignore` (aunque docs/CLIENT_PITCH.pdf puede ser intencional) |
| `data/tenants/ferreteria/catalog.csv` | CSVs de datos grandes no están excluidos |

**Gaps en el pattern de `.gitignore`:**
- `data/*.db` — no cubre `data/tenants/*/` (aunque esas DBs no están commiteadas actualmente)
- No hay entry para `*.mp4`, `*.avi`, u otros videos
- No hay entry para `state/`

---

## 8. Churn alto (Top 20 archivos)

| Commits | Archivo |
|---|---|
| 44 | `bot_sales/bot.py` |
| 31 | `bot_sales/ferreteria_quote.py` |
| 12 | `data/tenants/ferreteria/PENDIENTES.md` |
| 11 | `bot_sales/data/prompts/template_v2.j2` |
| 10 | `bot_sales/core/database.py` |
| 9 | `scripts/smoke_ferreteria.py` |
| 8 | `Dockerfile` |
| 8 | `data/tenants/ferreteria/knowledge/family_rules.yaml` |
| 8 | `bot_sales/routing/turn_interpreter.py` |
| 8 | `bot_sales/core/business_logic.py` |
| 8 | `app/ui/ferreteria_training_routes.py` |
| 8 | `app/main.py` |
| 7 | `PENDIENTES.md` |
| 7 | `data/tenants/ferreteria/profile.yaml` |
| 7 | `bot_sales/core/chatgpt.py` |
| 7 | `app/ui/templates/ferreteria_training/bot_config.html` |
| 6 | `requirements.txt` |
| 6 | `bot_sales/core/tenant_config.py` |
| 6 | `.gitignore` |

> `bot_sales/bot.py` con 44 commits es el archivo más volátil del repo — archivo monolítico de lógica de negocio. `bot_sales/ferreteria_quote.py` con 31 commits indica iteración intensa en cotizaciones. `data/tenants/ferreteria/PENDIENTES.md` con 12 commits es un archivo de gestión de tareas en git (anti-patrón).

---

## 9. Documentación huérfana en root

| Archivo | Tamaño | Lectura |
|---|---|---|
| `ANALYSIS.md` | 9.8 KB | Análisis técnico — posiblemente útil pero podría ir en `docs/` |
| `CHANGELOG.md` | 3.1 KB | Historial de versiones — legítimo en root |
| `context.md` | 11 KB | Contexto para LLM/Claude — no es doc de usuario, podría ir en `.claude/` |
| `CONTRIBUTING.md` | 2.4 KB | Guía de contribución — legítimo en root |
| `P0_P1_COMPLETION.md` | 7.5 KB | Plan de milestones completado — doc de proyecto, podría archivarse |
| `PENDIENTES.md` | 7.1 KB | Lista de tareas activa — anti-patrón: gestión de tareas en git |
| `PLAN_FASE1_2.md` | 17 KB | Plan de fases — doc de planificación, podría ir en `docs/planning/` |
| `QUICKSTART.md` | 3.3 KB | Guía de inicio — legítimo en root |
| `README.md` | 4.0 KB | README principal — legítimo |
| `SECURITY_AUDIT.md` | 4.9 KB | Audit anterior — podría ir en `reports/` |
| `platform_features.pdf` | 0 B | COMMITTED + VACÍO — eliminar |
| `SESSION_SUMMARY_2026-05-01.md` | 1.4 KB | Notas de sesión local — en `.gitignore` pero presentes en disco (correcto) |
| `SESSION_SUMMARY_2026-05-03.md` | 1.4 KB | Notas de sesión local — ídem |
| `data/tenants/ferreteria/PENDIENTES.md` | 34 KB | Lista de tareas del tenant (¡34 KB!) — commiteada y de alto churn |

---

## 10. Recomendaciones

### REMOVE_NOW (peligro)

1. **Rotar `OPENAI_API_KEY`** del `.env` local — la clave `sk-proj-JpSjr...` es real. Aunque no está commiteada, es buena práctica rotarla y usar variables de entorno del sistema o un gestor de secretos (Railway Variables, 1Password, etc.).
2. **Implementar el TODO de `mp_webhooks.py`** — el webhook de MercadoPago recibe pagos confirmados pero no actualiza la DB. Esto es deuda funcional crítica.
3. **Eliminar `demo_conversacion_dificil.mp4` del historial de git** — usar `git filter-repo` o BFG para purgar el binario de 8.1 MB del historial, luego añadir `*.mp4` al `.gitignore`.
4. **Eliminar `platform_features.pdf`** del repo — 0 bytes, sin valor.
5. **Eliminar `state/state.json`** del tracking de git — añadir `state/` al `.gitignore`.

### CLEAN_UP (cosmético)

6. **Añadir al `.gitignore`:** `*.mp4`, `state/`, `*.pdf` (o `platform_features.pdf` específicamente), `data/tenants/*/*.db`.
7. **Consolidar `app/bot/integrations/slack_files.py` y `bot_sales/integrations/slack_files.py`** — son duplicados exactos con los mismos TODOs.
8. **Mover `SECURITY_AUDIT.md`, `ANALYSIS.md`, `P0_P1_COMPLETION.md`, `PLAN_FASE1_2.md`** a `docs/` o `reports/` — el root acumula 10+ docs.
9. **Mover `context.md`** a `.claude/` — es instrucción para el LLM, no documentación de usuario.
10. **Dejar de commitear `data/tenants/ferreteria/PENDIENTES.md`** — 34 KB de lista de tareas en git con 12 commits es ruido. Usar un issue tracker o Notion.

### REVIEW (a discutir)

11. **`wsgi_legacy.py`** — ¿se sigue necesitando? Si el stack `app/` es el principal, este archivo debería deprecarse formalmente o eliminarse. El `wsgi.py` lo importa condicionalmente (`from wsgi_legacy import ...`).
12. **`data/tenants/ferreteria/catalog.csv` (5.5 MB)** — si se actualiza con frecuencia, considerar excluirlo de git y servirlo desde S3/Railway Volume, o al menos usar LFS.
13. **`ADMIN_TOKEN=ferreteria-token-2024` y `ADMIN_PASSWORD=Aristoteles`** en `.env` local — si son las credenciales de producción en Railway, son débiles. Regenerar con valores aleatorios largos.
14. **`app/bot/connectors/webchat.py:206`** — `const API_URL = 'http://localhost:8080'` hardcodeado en JS incrustado en Python. En producción debería ser configurable vía variable de entorno o template.
15. **Duplicación `app/bot/` vs `bot_sales/`** — múltiples archivos duplicados (whatsapp.py, slack_files.py, mp_webhooks.py, etc.). Si el objetivo es migrar todo a `app/`, marcar `bot_sales/` como deprecated formalmente.
