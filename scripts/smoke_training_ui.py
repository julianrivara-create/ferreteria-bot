#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import admin_routes
from app.api.ferreteria_training_routes import ferreteria_training_api
from app.ui.ferreteria_training_routes import ferreteria_training_ui
from bot_sales.training.demo_bootstrap import bootstrap_training_demo


def _print(ok: bool, label: str, details: str = "") -> None:
    prefix = "OK" if ok else "FAIL"
    suffix = f" - {details}" if details else ""
    print(f"[{prefix}] {label}{suffix}")


def _temp_catalog_and_profile(tmp_path: Path) -> dict:
    source_catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    catalog_dir = tmp_path / "tenant"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    catalog = catalog_dir / "catalog.csv"
    catalog.write_text(source_catalog.read_text(encoding="utf-8"), encoding="utf-8")

    knowledge_dir = catalog_dir / "knowledge"
    source_knowledge = ROOT / "data" / "tenants" / "ferreteria" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    for source_file in source_knowledge.glob("*.yaml"):
        (knowledge_dir / source_file.name).write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")

    profile = yaml.safe_load((ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8"))
    profile.setdefault("paths", {})
    profile["paths"]["catalog"] = str(catalog)
    profile["paths"]["db"] = str(tmp_path / "ferreteria_training.db")
    profile["paths"]["policies"] = str(ROOT / "data" / "tenants" / "ferreteria" / "policies.md")
    return profile


def run_smoke() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="ferreteria_training_smoke_") as tmpdir:
        tmp_path = Path(tmpdir)
        profile = _temp_catalog_and_profile(tmp_path)
        db_path = profile["paths"]["db"]

        with patch.object(admin_routes.settings, "ADMIN_TOKEN", "test-admin-token"),              patch("app.api.ferreteria_training_routes._tenant_db_path", lambda: db_path),              patch("app.api.ferreteria_training_routes._tenant_profile", lambda: profile):
            app = Flask(__name__, template_folder=str(ROOT / "app" / "ui" / "templates"))
            app.register_blueprint(ferreteria_training_api, url_prefix="/api/admin/ferreteria")
            app.register_blueprint(ferreteria_training_ui)
            client = app.test_client()
            auth_headers = {"X-Admin-Token": "test-admin-token"}
            json_headers = {**auth_headers, "Content-Type": "application/json"}

            home = client.get("/ops/ferreteria/training", headers=auth_headers)
            ok = home.status_code == 200 and "Hablar con el bot".encode() in home.data and "Esto estuvo mal".encode() in home.data
            failures += 0 if ok else 1
            _print(ok, "GET /ops/ferreteria/training", f"status={home.status_code}")

            help_page = client.get("/ops/ferreteria/training/help", headers=auth_headers)
            ok = help_page.status_code == 200 and "Cómo usar la herramienta".encode() in help_page.data
            failures += 0 if ok else 1
            _print(ok, "GET /ops/ferreteria/training/help", f"status={help_page.status_code}")

            session_resp = client.post(
                "/api/admin/ferreteria/training/sessions",
                headers=json_headers,
                json={"mode_profile": "cheap", "operator": "smoke"},
            )
            ok = session_resp.status_code == 201
            failures += 0 if ok else 1
            _print(ok, "POST /training/sessions", f"status={session_resp.status_code}")
            if not ok:
                print("\nTraining UI smoke failed early.")
                return 1
            session_id = session_resp.get_json()["session"]["id"]

            message_resp = client.post(
                f"/api/admin/ferreteria/training/sessions/{session_id}/messages",
                headers=json_headers,
                json={"message": "Necesito canio pvc"},
            )
            ok = message_resp.status_code == 200
            failures += 0 if ok else 1
            _print(ok, "POST /training/sessions/<id>/messages", f"status={message_resp.status_code}")
            payload = message_resp.get_json() or {}
            bot_message_id = (payload.get("message") or {}).get("id")

            simple_save = client.post(
                "/ops/ferreteria/training",
                headers=auth_headers,
                data={
                    "action": "save_simple_review",
                    "session_id": session_id,
                    "bot_message_id": bot_message_id,
                    "simple_choice": "understand_term",
                    "simple_what_was_wrong": "No reconoció una forma real de pedir el producto.",
                    "simple_first_step": "Primero tendría que haber entendido que hablaba de caño pvc.",
                    "simple_expected_answer": "Debería entenderlo como caño pvc y seguir el flujo normal.",
                    "simple_family": "cano",
                    "simple_canonical_product": "caño pvc",
                },
                follow_redirects=False,
            )
            ok = simple_save.status_code == 302 and "saved_suggestion_id=" in simple_save.headers.get("Location", "")
            failures += 0 if ok else 1
            _print(ok, "POST /ops/ferreteria/training save_simple_review", f"status={simple_save.status_code}")

            saved_home = client.get(simple_save.headers["Location"], headers=auth_headers)
            ok = saved_home.status_code == 200 and "Cambio en preparación".encode() in saved_home.data
            failures += 0 if ok else 1
            _print(ok, "GET saved workspace", f"status={saved_home.status_code}")

            suggestions_json = client.get(
                "/api/admin/ferreteria/training/suggestions",
                headers=auth_headers,
            ).get_json()
            suggestion_id = (suggestions_json.get("suggestions") or [{}])[0].get("id")
            review_id = (suggestions_json.get("suggestions") or [{}])[0].get("review_id")

            case_page = client.get(f"/ops/ferreteria/training/cases/{review_id}", headers=auth_headers)
            ok = case_page.status_code == 200 and "Ajustar la corrección recomendada".encode() in case_page.data
            failures += 0 if ok else 1
            _print(ok, "GET /training/cases/<id>", f"status={case_page.status_code}")

            suggestion_page = client.get(f"/ops/ferreteria/training/suggestions/{suggestion_id}", headers=auth_headers)
            ok = suggestion_page.status_code == 200 and "Qué cambia".encode() in suggestion_page.data
            failures += 0 if ok else 1
            _print(ok, "GET /training/suggestions/<id>", f"status={suggestion_page.status_code}")

            quick_draft = client.post(
                "/api/admin/ferreteria/training/unresolved-terms/suggest",
                headers=json_headers,
                json={
                    "term": "taco fisher",
                    "canonical": "taco fischer",
                    "family": "fijaciones",
                    "aliases": "taco fisher, taco plástico",
                    "summary": "Corregir un término repetido desde el atajo",
                },
            )
            quick_json = quick_draft.get_json() or {}
            ok = quick_draft.status_code == 201 and bool(quick_json.get("case_url")) and bool(quick_json.get("suggestion_url"))
            failures += 0 if ok else 1
            _print(ok, "POST /training/unresolved-terms/suggest", f"status={quick_draft.status_code}")

            manifest = bootstrap_training_demo(tmp_path / "training_demo")
            index_ok = Path(manifest["index_path"]).exists()
            failures += 0 if index_ok else 1
            _print(index_ok, "bootstrap_training_demo")

    if failures:
        print(f"\nTraining UI smoke failed: {failures}")
        return 1
    print("\nTraining UI smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
