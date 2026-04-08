from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from flask import Flask
import yaml

from app.api import admin_routes
import app.api.ferreteria_training_routes as training_api_module
from app.api.ferreteria_training_routes import ferreteria_training_api
from app.ui.ferreteria_training_routes import ferreteria_training_ui
from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales.training.review_service import TrainingReviewService
from bot_sales.training.store import TrainingStore
from bot_sales.training.suggestion_service import TrainingSuggestionService


ROOT = Path(__file__).resolve().parents[2]
TENANT_ROOT = ROOT / "data" / "tenants" / "ferreteria"
DEFAULT_ADMIN_TOKEN = "demo-admin-token"


@dataclass(frozen=True)
class DemoSnapshot:
    filename: str
    route: str
    title: str
    description: str


SNAPSHOT_SPECS = [
    DemoSnapshot(
        filename="01_workflow_home.html",
        route="/ops/ferreteria/training",
        title="Hablar con el bot",
        description="Pantalla principal con conversación, panel de enseñanza y acceso directo a cambios listos.",
    ),
    DemoSnapshot(
        filename="02_sandbox_review.html",
        route="/ops/ferreteria/training/sandbox?session_id={session_id}&review_message_id={review_message_id}",
        title="Misma vista desde la ruta sandbox",
        description="La ruta histórica de sandbox ahora reutiliza la misma experiencia simple de conversación y enseñanza.",
    ),
    DemoSnapshot(
        filename="03_case_clarification.html",
        route="/ops/ferreteria/training/cases/{clarification_case_id}",
        title="Caso con aclaración pendiente",
        description="Caso guardado con resumen estructurado, estado de cobertura y creación guiada de correcciones.",
    ),
    DemoSnapshot(
        filename="04_case_regression.html",
        route="/ops/ferreteria/training/cases/{regression_case_id}",
        title="Caso enfocado en cobertura futura",
        description="Caso que ya tiene un ejemplo futuro y todavía necesita decidir si conviene tocar el conocimiento activo.",
    ),
    DemoSnapshot(
        filename="05_suggestion_draft.html",
        route="/ops/ferreteria/training/suggestions/{draft_suggestion_id}",
        title="Detalle de borrador",
        description="Borrador de corrección con contexto semántico de revisión y vista antes/después.",
    ),
    DemoSnapshot(
        filename="06_suggestion_approved.html",
        route="/ops/ferreteria/training/suggestions/{approved_suggestion_id}",
        title="Corrección aprobada por activar",
        description="Corrección aprobada que muestra qué está listo para activarse a continuación.",
    ),
    DemoSnapshot(
        filename="07_cases_queue.html",
        route="/ops/ferreteria/training/cases",
        title="Cola de casos",
        description="Lista de casos orientada al trabajo, con próximos pasos y señales de cobertura futura.",
    ),
    DemoSnapshot(
        filename="08_suggestions_queue.html",
        route="/ops/ferreteria/training/suggestions",
        title="Cambios listos",
        description="Pantalla simple para activar cambios aprobados con antes/después y acceso al detalle.",
    ),
    DemoSnapshot(
        filename="09_usage.html",
        route="/ops/ferreteria/training/usage",
        title="Uso",
        description="Visibilidad de tokens y costo en un demo con datos cargados.",
    ),
]


def bootstrap_training_demo(
    output_dir: str | Path,
    *,
    admin_token: str = DEFAULT_ADMIN_TOKEN,
) -> dict[str, Any]:
    output_path = Path(output_dir).resolve()
    workspace_dir = output_path / "workspace"
    snapshot_dir = output_path / "snapshots"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    profile, profile_path, db_path = _prepare_demo_workspace(workspace_dir)
    manifest = _seed_demo_training_data(profile=profile, db_path=db_path)
    manifest["output_dir"] = str(output_path)
    manifest["workspace_dir"] = str(workspace_dir)
    manifest["snapshot_dir"] = str(snapshot_dir)
    manifest["profile_path"] = str(profile_path)
    manifest["db_path"] = str(db_path)
    manifest["admin_token"] = admin_token

    snapshots = _render_demo_snapshots(
        profile=profile,
        db_path=db_path,
        admin_token=admin_token,
        snapshot_dir=snapshot_dir,
        routes_context=manifest,
    )
    manifest["snapshots"] = snapshots

    walkthrough_path = snapshot_dir / "README.md"
    walkthrough_path.write_text(_render_demo_readme(manifest), encoding="utf-8")
    index_path = snapshot_dir / "index.html"
    index_path.write_text(_render_demo_index(manifest), encoding="utf-8")
    manifest["walkthrough_path"] = str(walkthrough_path)
    manifest["index_path"] = str(index_path)

    manifest_path = output_path / "demo_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _prepare_demo_workspace(workspace_dir: Path) -> tuple[dict[str, Any], Path, Path]:
    tenant_dir = workspace_dir / "ferreteria_demo"
    knowledge_dir = tenant_dir / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    catalog_src = TENANT_ROOT / "catalog.csv"
    catalog_path = tenant_dir / "catalog.csv"
    shutil.copy2(catalog_src, catalog_path)

    policies_src = TENANT_ROOT / "policies.md"
    policies_path = tenant_dir / "policies.md"
    if policies_src.exists():
        shutil.copy2(policies_src, policies_path)

    for source_file in (TENANT_ROOT / "knowledge").glob("*.yaml"):
        shutil.copy2(source_file, knowledge_dir / source_file.name)

    profile = yaml.safe_load((TENANT_ROOT / "profile.yaml").read_text(encoding="utf-8")) or {}
    profile.setdefault("paths", {})
    profile["paths"]["catalog"] = str(catalog_path)
    profile["paths"]["db"] = str(workspace_dir / "ferreteria_training_demo.db")
    profile["paths"]["policies"] = str(policies_path if policies_path.exists() else TENANT_ROOT / "policies.md")
    profile_path = workspace_dir / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return profile, profile_path, Path(profile["paths"]["db"])


def _seed_demo_training_data(*, profile: dict[str, Any], db_path: Path) -> dict[str, Any]:
    if db_path.exists():
        db_path.unlink()

    store = TrainingStore(str(db_path), tenant_id="ferreteria")
    loader = KnowledgeLoader(tenant_id="ferreteria", tenant_profile=profile)
    review_service = TrainingReviewService(store)
    suggestion_service = TrainingSuggestionService(store, loader)

    try:
        open_session = store.create_session(
            operator_id="andrea",
            mode_profile="balanced",
            model_name="gpt-4o-mini",
            token_ceiling=1800,
            context_strategy="compact",
        )
        store.update_session(
            open_session["id"],
            session_summary="Triage de la mañana con mezcla de entendimiento de términos, aclaraciones y una respuesta todavía pendiente de revisión.",
        )

        draft_message = _append_turn(
            store,
            session_id=open_session["id"],
            user_text="Necesito canio pvc de 20 para el baño",
            assistant_text="No encontré “canio pvc” en el catálogo. Si querés, escribime el nombre exacto del producto.",
            route_source="deterministic",
            model_name=None,
        )
        clarification_message = _append_turn(
            store,
            session_id=open_session["id"],
            user_text="Necesito mecha para pared",
            assistant_text="Te paso una mecha estándar de 8 mm para eso.",
            route_source="model_assisted",
            model_name="gpt-4o-mini",
            prompt_tokens=118,
            completion_tokens=44,
            estimated_cost_micros=17100,
        )
        _append_turn(
            store,
            session_id=open_session["id"],
            user_text="¿Hacen envíos el mismo día?",
            assistant_text="Sí, hacemos envíos. ¿Querés que te pase las zonas disponibles?",
            route_source="model_assisted",
            model_name="gpt-4o-mini",
            prompt_tokens=94,
            completion_tokens=31,
            estimated_cost_micros=12800,
        )

        closed_session = store.create_session(
            operator_id="rocio",
            mode_profile="cheap",
            model_name="gpt-4o-mini",
            token_ceiling=900,
            context_strategy="compact",
        )
        store.update_session(
            closed_session["id"],
            session_summary="Sesión de seguimiento con una corrección de FAQ y un caso pensado solo como cobertura futura.",
            status="closed",
            ended_at=_iso_now(),
        )

        applied_message = _append_turn(
            store,
            session_id=closed_session["id"],
            user_text="¿Hacen factura A?",
            assistant_text="Eso lo tiene que confirmar el local.",
            route_source="model_assisted",
            model_name="gpt-4o-mini",
            prompt_tokens=86,
            completion_tokens=28,
            estimated_cost_micros=11600,
        )
        regression_message = _append_turn(
            store,
            session_id=closed_session["id"],
            user_text="Necesito termofusión para agua caliente",
            assistant_text="No entendí bien el término. ¿Podés mandarme más detalle?",
            route_source="deterministic",
            model_name=None,
        )

        draft_review = review_service.save_review(
            session_id=open_session["id"],
            bot_message_id=draft_message["id"],
            review_label="incorrect",
            failure_tag="did_not_understand_term",
            failure_detail_tag="misspelling_or_regional_term",
            expected_behavior_tag="understand_term",
            clarification_dimension="material",
            expected_answer="Debería entender 'canio pvc' como 'caño pvc' y seguir el flujo de caños.",
            what_was_wrong="No reconoció una variante regional común del término.",
            missing_clarification="No faltaba una aclaración: faltaba entender el término.",
            suggested_family="cano",
            suggested_canonical_product="caño pvc",
            operator_notes="Buen ejemplo de lenguaje regional real.",
            created_by="andrea",
        )
        draft_suggestion = suggestion_service.create_suggestion(
            review_id=draft_review["id"],
            domain="synonym",
            summary="Hacer que el bot entienda “canio pvc” como “caño pvc”",
            source_message="Necesito canio pvc de 20 para el baño",
            repeated_term="canio pvc",
            suggested_payload={
                "canonical": "caño pvc",
                "family": "cano",
                "aliases": ["canio pvc", "caño pvc", "cano pvc"],
                "context_terms": ["baño", "20"],
            },
            created_by="andrea",
        )

        clarification_review = review_service.save_review(
            session_id=open_session["id"],
            bot_message_id=clarification_message["id"],
            review_label="incorrect",
            failure_tag="should_have_asked_clarification",
            failure_detail_tag="missing_surface",
            expected_behavior_tag="ask_clarification_first",
            clarification_dimension="surface",
            expected_answer="Debería preguntar primero si es para pared, hormigón o cerámica antes de resolver.",
            what_was_wrong="Eligió una variante demasiado rápido sin pedir la superficie.",
            missing_clarification="Preguntar superficie y material antes de resolver la mecha.",
            suggested_family="mecha",
            suggested_canonical_product="mecha",
            operator_notes="Caso muy común cuando el cliente solo dice 'pared'.",
            created_by="andrea",
        )
        approved_suggestion = suggestion_service.create_suggestion(
            review_id=clarification_review["id"],
            domain="clarification_rule",
            summary="Pedir primero la superficie cuando consultan por mechas",
            source_message="Necesito mecha para pared",
            repeated_term="mecha",
            suggested_payload={
                "family": "mecha",
                "short_prompt": "¿Para pared, hormigón o cerámica?",
                "prompt": "Antes de pasarte una mecha, ¿la necesitás para pared, hormigón o cerámica?",
                "required_dimensions": ["surface"],
                "question_order": ["surface", "size"],
                "blocked_if_missing": ["surface"],
                "examples_by_dimension": {
                    "surface": ["pared", "hormigón", "cerámica"],
                },
            },
            created_by="andrea",
        )
        approved_suggestion = suggestion_service.approve(
            approved_suggestion["id"],
            acted_by="rocio",
            reason="La aclaración es más segura que resolver antes de tiempo.",
        )

        applied_review = review_service.save_review(
            session_id=closed_session["id"],
            bot_message_id=applied_message["id"],
            review_label="incorrect",
            failure_tag="missed_faq_or_policy",
            failure_detail_tag="billing_or_invoice",
            expected_behavior_tag="answer_faq_or_policy",
            expected_answer="Debería responder de forma breve si hacen factura A y qué dato falta pedir.",
            what_was_wrong="No usó una respuesta operativa estable para una pregunta frecuente.",
            missing_clarification="No hacía falta aclarar producto; solo una respuesta estándar.",
            operator_notes="Sirve para mostrar un FAQ ya aplicado.",
            created_by="rocio",
        )
        applied_suggestion = suggestion_service.create_suggestion(
            review_id=applied_review["id"],
            domain="faq",
            summary="Agregar una respuesta breve sobre factura A",
            source_message="¿Hacen factura A?",
            repeated_term="factura A",
            suggested_payload={
                "id": "factura_a_demo",
                "question": "¿Hacen factura A?",
                "answer": "Sí, hacemos factura A. Si querés avanzar, pasanos CUIT y razón social junto con el pedido.",
                "keywords": ["factura a", "cuit", "razon social"],
                "active": True,
                "tags": ["facturacion", "politica"],
            },
            created_by="rocio",
        )
        applied_suggestion = suggestion_service.approve(
            applied_suggestion["id"],
            acted_by="rocio",
            reason="La respuesta es corta, estable y segura para activar.",
        )
        applied_suggestion = suggestion_service.apply(
            applied_suggestion["id"],
            acted_by="rocio",
            reason="Lista para usarse en vivo dentro del entorno demo.",
        )
        regression_export = suggestion_service.export_regression_case(
            applied_review["id"],
            exported_by="rocio",
        )

        regression_review = review_service.save_review(
            session_id=closed_session["id"],
            bot_message_id=regression_message["id"],
            review_label="incorrect",
            failure_tag="other",
            failure_detail_tag="other",
            expected_behavior_tag="regression_only",
            expected_answer="Conviene dejar este ejemplo protegido como regresión mientras se decide si vale una regla nueva.",
            what_was_wrong="Todavía no está claro si hace falta una regla nueva o solo registrar el caso.",
            missing_clarification="Posible decisión futura entre término, familia o derivación.",
            suggested_family="termofusion",
            operator_notes="Caso útil para cobertura aunque todavía no tenga un cambio de conocimiento aprobado.",
            created_by="rocio",
        )
        regression_candidate = suggestion_service.create_regression_candidate(
            regression_review["id"],
            created_by="rocio",
            payload_override={
                "expected_answer": "El caso queda capturado para revisión y cobertura antes de tocar conocimiento en vivo.",
            },
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        for session in store.list_sessions(limit=20):
            messages = store.list_messages(session["id"])
            session_tokens = sum(int(message.get("total_tokens") or 0) for message in messages if message.get("role") == "assistant")
            session_cost = sum(int(message.get("estimated_cost_micros") or 0) for message in messages if message.get("role") == "assistant")
            session_turns = sum(1 for message in messages if message.get("role") == "assistant")
            store.upsert_usage(
                metric_scope="session",
                period_key=session["id"],
                session_id=session["id"],
                total_tokens=session_tokens,
                estimated_cost_micros=session_cost,
                message_count=session_turns,
            )
            store.upsert_usage(
                metric_scope="daily",
                period_key=today,
                session_id="",
                total_tokens=session_tokens,
                estimated_cost_micros=session_cost,
                message_count=session_turns,
            )
            store.upsert_usage(
                metric_scope="monthly",
                period_key=month,
                session_id="",
                total_tokens=session_tokens,
                estimated_cost_micros=session_cost,
                message_count=session_turns,
            )

        return {
            "session_id": open_session["id"],
            "review_message_id": draft_message["id"],
            "draft_case_id": draft_review["id"],
            "clarification_case_id": clarification_review["id"],
            "regression_case_id": regression_review["id"],
            "draft_suggestion_id": draft_suggestion["id"],
            "approved_suggestion_id": approved_suggestion["id"],
            "applied_suggestion_id": applied_suggestion["id"],
            "regression_export_id": regression_export["id"],
            "regression_candidate_id": regression_candidate["id"],
        }
    finally:
        store.close()


def _append_turn(
    store: TrainingStore,
    *,
    session_id: str,
    user_text: str,
    assistant_text: str,
    route_source: str,
    model_name: str | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_micros: int = 0,
) -> dict[str, Any]:
    store.append_message(session_id, role="user", content=user_text)
    return store.append_message(
        session_id,
        role="assistant",
        content=assistant_text,
        route_source=route_source,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=int(prompt_tokens or 0) + int(completion_tokens or 0),
        estimated_cost_micros=estimated_cost_micros,
    )


@contextmanager
def _patched_training_environment(*, profile: dict[str, Any], db_path: Path, admin_token: str):
    original_profile = training_api_module._tenant_profile
    original_db = training_api_module._tenant_db_path
    original_admin_token = admin_routes.settings.ADMIN_TOKEN
    training_api_module._tenant_profile = lambda: profile
    training_api_module._tenant_db_path = lambda: str(db_path)
    admin_routes.settings.ADMIN_TOKEN = admin_token
    try:
        yield
    finally:
        training_api_module._tenant_profile = original_profile
        training_api_module._tenant_db_path = original_db
        admin_routes.settings.ADMIN_TOKEN = original_admin_token


def _render_demo_snapshots(
    *,
    profile: dict[str, Any],
    db_path: Path,
    admin_token: str,
    snapshot_dir: Path,
    routes_context: dict[str, Any],
) -> list[dict[str, str]]:
    snapshots: list[dict[str, str]] = []
    with _patched_training_environment(profile=profile, db_path=db_path, admin_token=admin_token):
        app = Flask(__name__, template_folder=str(ROOT / "app" / "ui" / "templates"))
        app.register_blueprint(ferreteria_training_api, url_prefix="/api/admin/ferreteria")
        app.register_blueprint(ferreteria_training_ui)
        client = app.test_client()
        headers = {"X-Admin-Token": admin_token}
        for spec in SNAPSHOT_SPECS:
            route = spec.route.format(**routes_context)
            response = client.get(route, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"Could not render demo snapshot for {route}: {response.status_code}")
            file_path = snapshot_dir / spec.filename
            file_path.write_bytes(response.data)
            snapshots.append(
                {
                    "title": spec.title,
                    "description": spec.description,
                    "route": route,
                    "filename": spec.filename,
                    "path": str(file_path),
                }
            )
    return snapshots


def _render_demo_readme(manifest: dict[str, Any]) -> str:
    lines = [
        "# Mini demo del entrenamiento Ferretería",
        "",
        "Este demo está completamente aislado de los datos normales del tenant.",
        "",
        "## Qué incluye",
        "",
        "- flujo principal completo: hablar con el bot, enseñar y activar",
        "- workspace simple con una respuesta incorrecta seleccionada",
        "- caso con aclaración pendiente",
        "- caso enfocado en cobertura futura",
        "- detalle de un borrador",
        "- pantalla de cambios listos para activar",
        "- vistas secundarias de apoyo: impacto y uso",
        "",
        "## Apertura rápida",
        "",
        f"1. Serví `{manifest['snapshot_dir']}` con un servidor estático:",
        "   ```bash",
        f"   python3 -m http.server 8033 --directory \"{manifest['snapshot_dir']}\"",
        "   ```",
        "2. Abrí `http://127.0.0.1:8033/index.html`.",
        "",
        "## Recorrido recomendado para revisar el demo",
        "",
        "1. Empezá por `Hablar con el bot` para ver el flujo simple.",
        "2. Mirá cómo se guarda una enseñanza sobre una respuesta puntual.",
        "3. Abrí el caso solo como vista avanzada.",
        "4. Terminá en `Cambios listos` para revisar activación y antes/después.",

        "## Páginas generadas",
        "",
    ]
    for item in manifest["snapshots"]:
        lines.extend(
            [
                f"- `{item['filename']}`",
                f"  - muestra: {item['description']}",
                f"  - ruta original: `{item['route']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Entorno del demo",
            "",
            f"- perfil: `{manifest['profile_path']}`",
            f"- base de datos: `{manifest['db_path']}`",
            f"- token admin usado para renderizar snapshots: `{manifest['admin_token']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_demo_index(manifest: dict[str, Any]) -> str:
    cards = []
    for item in manifest["snapshots"]:
        cards.append(
            f"""
            <a class="card" href="{item['filename']}">
              <div class="eyebrow">{item['title']}</div>
              <h3>{item['description']}</h3>
              <div class="meta">{item['route']}</div>
            </a>
            """
        )
    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <title>Demo de entrenamiento Ferretería</title>
    <style>
      :root {{
        --bg: #f5f1e8;
        --paper: #fffdf9;
        --ink: #1f2937;
        --muted: #6b7280;
        --line: #d6cfc1;
        --accent: #9a3412;
        --accent-soft: #f97316;
        --shadow: 0 18px 40px rgba(31, 41, 55, 0.08);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        background: radial-gradient(circle at top left, #fff7ed, var(--bg) 45%);
        color: var(--ink);
      }}
      .shell {{ max-width: 1120px; margin: 0 auto; padding: 32px 24px 48px; }}
      .hero {{
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 28px;
        padding: 28px;
        box-shadow: var(--shadow);
        margin-bottom: 24px;
      }}
      .eyebrow {{
        color: var(--accent);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
      }}
      h1 {{ margin: 10px 0 8px; font-size: 40px; }}
      p {{ margin: 0; line-height: 1.55; color: var(--muted); }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 16px;
      }}
      .card {{
        display: grid;
        gap: 10px;
        text-decoration: none;
        color: inherit;
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 18px;
        box-shadow: var(--shadow);
      }}
      .card:hover {{
        border-color: var(--accent-soft);
        transform: translateY(-1px);
      }}
      .card h3 {{ margin: 0; font-size: 18px; line-height: 1.35; }}
      .meta {{
        font-size: 12px;
        color: var(--muted);
        word-break: break-all;
      }}
      .notes {{
        margin-top: 22px;
        background: rgba(154, 52, 18, 0.06);
        border: 1px solid rgba(154, 52, 18, 0.18);
        border-radius: 20px;
        padding: 18px;
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="hero">
        <div class="eyebrow">Mini demo local</div>
        <h1>Interfaz de entrenamiento Ferretería</h1>
        <p>Esta exportación usa las plantillas y rutas reales del entrenamiento, cargadas con datos demo aislados de ferretería para que puedas revisar primero el flujo principal y después las pantallas de apoyo, sin depender de una operación en vivo.</p>
      </div>
      <div class="grid">
        {''.join(cards)}
      </div>
      <div class="notes">
        <div class="eyebrow">Qué conviene mirar</div>
        <p>Empezá por <strong>Hablar con el bot</strong>, seguí con la enseñanza sobre una respuesta puntual, abrí el caso solo como vista avanzada y terminá en <strong>Cambios listos</strong>. Después usá impacto y uso como pantallas secundarias. Todos los datos de esta exportación viven en un entorno demo aislado.</p>
      </div>
    </div>
  </body>
</html>
"""


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
