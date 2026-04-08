# Plan: Fase 1 & 2 — De Bueno a Excelente

> Generado el 2026-03-19. Basado en relevamiento real del código.

---

## Hallazgos clave del relevamiento

### Lo que ya funciona (no tocar)
- **`apply()` en `suggestion_service.py`**: Ya modifica los archivos YAML del knowledge base atomicamente con backup. Llama a `_write_yaml_atomically()` que hace `os.fsync()` + atomic replace + backup automático. Completamente funcional y testeado. **Fase 2.1 está DONE.**
- **Retry logic en `chatgpt.py`**: Tiene backoff exponencial con 3 reintentos. Solo falta mejorar el logging del fallback.
- **Tablas de regression**: `regression_case_exports` y `regression_case_candidates` existen en `store.py` con todos sus métodos. Solo falta la generación de fixtures para pytest.

### Lo que realmente falta
| Item | Archivo | Problema concreto |
|---|---|---|
| SQL Injection | `bot_sales/core/database.py:134` | f-string en ALTER TABLE con valor de Config |
| Sesiones en memoria | `bot_sales/bot_gemini.py:102` | `self.contexts = {}` perdido al reiniciar |
| Sin índices | `bot_sales/core/database.py` _init_db() | Queries O(n) en tablas sin índice |
| Holds sin cleanup | `whatsapp_server.py`, `app/main.py` | `cleanup_holds()` existe pero nunca se llama |
| Mock silencioso | `bot_sales/core/gemini.py` | Sin retry, sin alerta cuando falla API real |
| Regression → pytest | `tests/` | Tabla existe, no hay generador de fixtures |
| Dashboard impacto | `app/ui/templates/ferreteria_training/` | No existe |
| Vista unresolved terms | `app/ui/templates/ferreteria_training/` | No existe |

---

## FASE 1 — Estabilidad y Seguridad

### 1.1 Fix SQL Injection

**Archivo:** `bot_sales/core/database.py:134`

**Problema:**
```python
# VULNERABLE — usa f-string con valor externo
self.cursor.execute(f"ALTER TABLE stock ADD COLUMN category TEXT DEFAULT '{default_cat}'")
```

**Fix:** SQLite no soporta parámetros `?` en DDL. La solución correcta es validar el valor antes de interpolarlo.

```python
# En _ensure_stock_schema(), línea ~130
if "category" not in columns:
    from bot_sales.config import Config
    default_cat = Config.DEFAULT_CATEGORY
    # Validar: solo letras, números, espacios y guiones
    import re
    if default_cat and not re.match(r'^[\w\s\-]+$', default_cat):
        raise ValueError(f"DEFAULT_CATEGORY contiene caracteres inválidos: {default_cat!r}")
    if default_cat:
        safe_default = default_cat.replace("'", "''")  # escape SQL básico
        self.cursor.execute(f"ALTER TABLE stock ADD COLUMN category TEXT DEFAULT '{safe_default}'")
    else:
        self.cursor.execute("ALTER TABLE stock ADD COLUMN category TEXT")
```

**Patrón de referencia:** `bot_sales/core/database.py` líneas 54-112 (CREATE TABLE sin f-strings).

**Verificación:** `grep -n "f\"ALTER\|f'ALTER" bot_sales/core/database.py` → debe devolver 0 resultados sin fix.

---

### 1.2 Persistir sesiones de conversación en SQLite

**Archivo principal:** `bot_sales/bot_gemini.py:102`

**Problema:**
```python
self.contexts: Dict[str, List[Dict[str, str]]] = {}  # perdido al reiniciar
self.sessions: Dict[str, Dict] = {}                  # ídem
```

**Nota importante:** El proyecto NO usa Redis para caché — usa SQLite (`bot_sales/core/cache.py`). La persistencia de sesiones también debe ir en SQLite para mantener coherencia.

**Implementación:**

1. **Agregar tabla `conversation_sessions` en `database.py` _init_db():**
```sql
CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id TEXT NOT NULL,
    tenant_id  TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '[]',
    session_state_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL,
    PRIMARY KEY (session_id, tenant_id)
);
```

2. **Agregar métodos en `Database`:**
```python
def load_session(self, session_id: str) -> tuple[list, dict]:
    """Retorna (context, session_state). Vacío si no existe."""

def save_session(self, session_id: str, context: list, session_state: dict) -> None:
    """Upsert del estado de sesión."""

def delete_session(self, session_id: str) -> None:
    """Eliminar sesión (al cerrar o vender)."""
```

3. **Modificar `bot_gemini.py`** — reemplazar acceso a `self.contexts[session_id]` y `self.sessions[session_id]` por calls a `self.db.load_session()` / `self.db.save_session()`.

**Patrón a copiar:** `database.py` método `upsert_customer()` (líneas ~350-380) — usa INSERT OR REPLACE con `?` params.

**Verificación:** Reiniciar el bot mid-conversación y verificar que retoma el contexto.

---

### 1.3 Agregar índices en SQLite

**Archivo:** `bot_sales/core/database.py`, método `_init_db()`, después de cada `CREATE TABLE`.

**Índices a agregar:**
```sql
-- stock
CREATE INDEX IF NOT EXISTS idx_stock_sku      ON stock(sku);
CREATE INDEX IF NOT EXISTS idx_stock_category ON stock(category);

-- holds
CREATE INDEX IF NOT EXISTS idx_holds_customer  ON holds(customer_id);
CREATE INDEX IF NOT EXISTS idx_holds_expires   ON holds(expires_at);
CREATE INDEX IF NOT EXISTS idx_holds_sku       ON holds(sku);

-- sales
CREATE INDEX IF NOT EXISTS idx_sales_customer  ON sales(customer_email);
CREATE INDEX IF NOT EXISTS idx_sales_sku       ON sales(sku);
CREATE INDEX IF NOT EXISTS idx_sales_ts        ON sales(timestamp DESC);

-- customers
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);

-- leads
CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status);
```

**Referencia:** `bot_sales/training/store.py` líneas donde ya se crean índices para training (e.g., `idx_regression_exports_review`).

**Verificación:** `EXPLAIN QUERY PLAN SELECT * FROM stock WHERE category = 'X'` debe mostrar "SEARCH stock USING INDEX".

---

### 1.4 Cleanup automático de holds con APScheduler

**Archivos:**
- Patrón a copiar: `app/services/mep_rate_scheduler.py` (líneas 1-130)
- Donde llamarlo: `app/main.py:109` (junto a `start_mep_rate_scheduler()`) y `whatsapp_server.py`

**Implementación — crear `app/services/holds_scheduler.py`:**
```python
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

_scheduler = None

def _cleanup_expired_holds():
    """Elimina holds vencidos de todas las DBs activas."""
    from bot_sales.core.tenancy import TenantManager
    for tenant_id in TenantManager.list_active_tenant_ids():
        try:
            db = TenantManager.get_db(tenant_id)
            deleted = db.cleanup_holds()
            if deleted:
                logging.info(f"[holds_cleanup] {deleted} holds vencidos eliminados en tenant={tenant_id}")
        except Exception as e:
            logging.error(f"[holds_cleanup] Error en tenant={tenant_id}: {e}")

def start_holds_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _cleanup_expired_holds,
        trigger=IntervalTrigger(minutes=5),
        id="holds_cleanup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    logging.info("[holds_scheduler] Iniciado (cada 5 min)")
```

**Donde llamarlo:**
```python
# app/main.py — después de start_mep_rate_scheduler()
from app.services.holds_scheduler import start_holds_scheduler
start_holds_scheduler()

# whatsapp_server.py — en main()
from app.services.holds_scheduler import start_holds_scheduler
start_holds_scheduler()
```

**Verificación:** Crear un hold con `expires_at = time.time() - 1`, esperar 6 min, verificar que fue eliminado.

---

### 1.5 Fix mock fallback silencioso

#### Gemini (sin retry — problema principal)

**Archivo:** `bot_sales/core/gemini.py:120-126`

**Problema actual:** Un solo `except Exception` retorna respuesta hardcodeada sin reintentar ni alertar.

**Fix — agregar retry con backoff igual que ChatGPT:**
```python
import time

def send_message(self, messages, functions=None, max_retries=3):
    if self.mock_mode:
        return self._mock_response(messages)

    last_error = None
    for attempt in range(max_retries):
        try:
            # ... lógica existente de llamada a Gemini API ...
            return result
        except Exception as e:
            last_error = e
            wait = 2 ** attempt  # 1s, 2s, 4s
            logging.warning(f"[GeminiClient] intento {attempt+1}/{max_retries} falló: {e}. Reintentando en {wait}s...")
            if attempt < max_retries - 1:
                time.sleep(wait)

    # Todos los reintentos fallaron — loguear como ERROR, no silenciosamente
    logging.error(f"[GeminiClient] API falló tras {max_retries} intentos. Último error: {last_error}", exc_info=True)
    # En producción: re-raise para que el conector maneje el error
    # En desarrollo (mock_mode ya chequeado arriba): never reached
    raise RuntimeError(f"Gemini API no disponible tras {max_retries} intentos: {last_error}")
```

#### ChatGPT (mejorar logging del fallback)

**Archivo:** `bot_sales/core/chatgpt.py:162-177`

**Fix:** Cambiar de `logging.info` a `logging.error` en el fallback final y agregar `exc_info=True`:
```python
# Antes (silencioso):
logging.info("Falling back to MOCK response due to API failure")

# Después (visible):
logging.error(f"[ChatGPTClient] API no disponible. Usando mock de emergencia. Error: {last_error}", exc_info=True)
```

**Verificación:** `grep -n "Falling back\|fallback_mock" bot_sales/core/*.py` → todos deben ser `logging.error` o `logging.warning`.

---

## FASE 2 — Completar el Loop de Entrenamiento

### 2.1 ✅ Apply() ya funciona — NADA QUE IMPLEMENTAR

El relevamiento confirmó que `suggestion_service.py` ya implementa `apply()` correctamente:
- Llama a `_apply_to_knowledge()` → handler específico por dominio → `loader.save_domain()` → `_write_yaml_atomically()` con fsync + backup
- Registra audit trail en 3 tablas: `knowledge_suggestions`, `knowledge_approvals`, `knowledge_change_audit`
- Hay tests de integración que verifican que el archivo YAML fue modificado (`test_ferreteria_training.py:193-259`)

**No se necesita ningún cambio en esta área.**

---

### 2.2 Conectar regression_exports con pytest

**Contexto:** La tabla `regression_case_exports` en `store.py` guarda casos de regresión con `payload_json`. Existe el método `create_regression_export()` (línea 835). **Falta** un generador que tome esos exports y cree fixtures de pytest.

**Implementación — crear `scripts/generate_regression_fixtures.py`:**

```python
#!/usr/bin/env python3
"""
Genera fixtures de pytest desde regression_case_exports en la DB de training.

Uso: python scripts/generate_regression_fixtures.py [--tenant ferreteria] [--output tests/regression/]
"""
import argparse
import json
import sqlite3
from pathlib import Path

TEMPLATE = '''
def test_{fixture_name}(bot_fixture):
    """Caso de regresión: {summary}
    Generado desde export {export_id} (review {review_id})
    """
    user_message = {user_message!r}
    response = bot_fixture.process_message("regression_session", user_message)
    # Assert generado desde expected_behavior
    {assertions}
'''

def generate(tenant_id: str, output_dir: Path):
    db_path = Path(f"data/{tenant_id}_training.db")  # ajustar según config
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, review_id, fixture_name, export_format, payload_json FROM regression_case_exports WHERE status='active'"
    ).fetchall()

    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for export_id, review_id, fixture_name, fmt, payload_raw in rows:
        payload = json.loads(payload_raw)
        # Generar assertions desde expected_behavior en el payload
        assertions = _build_assertions(payload)
        code = TEMPLATE.format(
            fixture_name=fixture_name,
            summary=payload.get("summary", "sin descripción"),
            export_id=export_id,
            review_id=review_id,
            user_message=payload.get("user_message", ""),
            assertions=assertions,
        )
        out_file = output_dir / f"test_regression_{fixture_name}.py"
        out_file.write_text(code)
        count += 1
    print(f"Generados {count} fixtures en {output_dir}")
    conn.close()
```

**Integrar en CI:** Agregar al Makefile o pre-test hook:
```bash
python scripts/generate_regression_fixtures.py --tenant ferreteria --output tests/regression/
pytest tests/regression/ -v
```

**Verificación:** Crear un export manual en la DB, correr el script, verificar que aparece `tests/regression/test_regression_*.py`.

---

### 2.3 Dashboard de impacto del training

**Contexto:** No existe. Necesitamos mostrar métricas que respondan "¿Sirvió la corrección?".

**Fuente de datos disponible:** La tabla `training_reviews` tiene `review_label` (correct/partial/incorrect/unsafe) y `updated_at`. La tabla `knowledge_suggestions` tiene `created_at` y `updated_at` del apply. Con esto podemos calcular: tasa de error antes vs después de cada apply.

**Implementación en 2 partes:**

#### A) Endpoint de métricas — `app/api/ferreteria_training_routes.py`

```python
@ferreteria_training_api.route("/training/impact", methods=["GET"])
@admin_required
def training_impact():
    """
    Devuelve: para cada suggestion aplicada, % de reviews correctas
    en la semana previa vs la semana posterior al apply.
    """
    store, *_ = get_training_services()
    # Query: join knowledge_suggestions (status=applied) con training_reviews
    # agrupando por semana relativa al apply
    rows = store.get_impact_metrics()
    return jsonify({"impact": rows})
```

Agregar `get_impact_metrics()` en `store.py`:
```python
def get_impact_metrics(self) -> list[dict]:
    """
    Para cada sugerencia aplicada, computa tasa de respuestas correctas
    en los 7 días previos y 7 días posteriores al apply.
    """
    sql = """
    SELECT
        ks.id as suggestion_id,
        ks.domain,
        ks.summary,
        ks.updated_at as applied_at,
        SUM(CASE WHEN r.review_label='correct' AND r.created_at < ks.updated_at THEN 1 ELSE 0 END) as correct_before,
        SUM(CASE WHEN r.review_label != 'correct' AND r.created_at < ks.updated_at THEN 1 ELSE 0 END) as incorrect_before,
        SUM(CASE WHEN r.review_label='correct' AND r.created_at >= ks.updated_at THEN 1 ELSE 0 END) as correct_after,
        SUM(CASE WHEN r.review_label != 'correct' AND r.created_at >= ks.updated_at THEN 1 ELSE 0 END) as incorrect_after
    FROM knowledge_suggestions ks
    LEFT JOIN training_reviews r
        ON ABS(julianday(r.created_at) - julianday(ks.updated_at)) <= 7
    WHERE ks.status = 'applied'
    GROUP BY ks.id
    """
    ...
```

#### B) Vista en Training UI — nuevo template `impact.html`

- Tabla con columnas: Corrección | Dominio | Fecha Apply | Antes (% correcto) | Después (% correcto) | Delta
- Badge verde si delta > 0, rojo si regresión
- Agregar tab "Impacto" en `base.html`

---

### 2.4 Vista de términos no resueltos en Training UI

**Contexto:** `data/tenants/ferreteria/unresolved_terms.jsonl` crece sin control. Cada línea tiene:
```json
{"ts": "2025-...", "raw": "taco fisher", "normalized": "taco fisher", "status": "unresolved", "reason": "no_match_after_scored_search"}
```

**Implementación en 3 partes:**

#### A) Endpoint de lectura — `app/api/ferreteria_training_routes.py`
```python
@ferreteria_training_api.route("/training/unresolved-terms", methods=["GET"])
@admin_required
def list_unresolved_terms():
    """Lee el JSONL y devuelve términos agrupados por frecuencia."""
    from collections import Counter
    path = Path(f"data/tenants/{tenant_id}/unresolved_terms.jsonl")
    terms = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    # Agrupar por normalized, ordenar por frecuencia desc
    freq = Counter(t["normalized"] for t in terms)
    unique = {t["normalized"]: t for t in reversed(terms)}  # último occurrence
    result = [
        {**unique[term], "count": count}
        for term, count in freq.most_common(200)
    ]
    return jsonify({"terms": result, "total": len(terms)})
```

#### B) Endpoint de acción (crear sugerencia desde término)
```python
@ferreteria_training_api.route("/training/unresolved-terms/<term>/suggest", methods=["POST"])
@admin_required
def suggest_from_unresolved(term: str):
    """Crea una suggestion de tipo synonym desde un término no resuelto."""
    payload = request.get_json()
    # payload: {"canonical": "tornillo fischer", "family": "fijaciones"}
    ...
```

#### C) Template `unresolved_terms.html`
- Tabla: Término | Frecuencia | Última vez visto | Acción
- Botón "Crear corrección" por fila → modal con campo canonical + family
- Botón "Descartar" para marcar como ignorado
- Agregar tab "Términos sin resolver" en `base.html` con badge de contador

---

## Orden de implementación recomendado

```
1.3 Índices        ← 15 min, zero risk, impacto inmediato
1.1 SQL Injection  ← 20 min, seguridad crítica
1.4 Holds cleanup  ← 30 min, copiar patrón de mep_rate_scheduler
1.5 Mock fallback  ← 20 min, logging + retry en Gemini
1.2 Sesiones       ← 1-2h, más complejo (nueva tabla + refactor bot_gemini)
2.2 Regression     ← 1h, script + integración CI
2.4 Unresolved UI  ← 1.5h, endpoint + template
2.3 Impact dash    ← 2h, query SQL + template con visualización
```

**Total estimado: ~8-9h de implementación.**
