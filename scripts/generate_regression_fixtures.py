#!/usr/bin/env python3
"""
Genera fixtures de pytest desde regression_case_exports en la DB de training.

Lee los casos exportados desde la interfaz de entrenamiento y genera archivos
de test en tests/regression/ listos para correr con pytest.

Uso:
    python scripts/generate_regression_fixtures.py
    python scripts/generate_regression_fixtures.py --tenant ferreteria --output tests/regression/
    python scripts/generate_regression_fixtures.py --dry-run
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Agregar raíz al path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _find_training_db(tenant_slug: str) -> Path:
    """Localiza la DB del tenant leyendo tenants.yaml."""
    import yaml

    tenants_yaml = ROOT / "tenants.yaml"
    if tenants_yaml.exists():
        with open(tenants_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for t in data.get("tenants", []):
            if t.get("slug") == tenant_slug or t.get("id") == tenant_slug:
                db_file = t.get("db_file", f"data/{tenant_slug}.db")
                path = Path(db_file)
                return path if path.is_absolute() else ROOT / path

    # Fallback convencional
    return ROOT / f"data/{tenant_slug}.db"


def _slugify(text: str) -> str:
    """Convierte un texto a un nombre de función Python válido."""
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower())
    text = text.strip("_")
    return text or "case"


_FILE_HEADER = '''\
"""
Tests de regresión generados automáticamente desde regression_case_exports.
NO editar manualmente — se regeneran con scripts/generate_regression_fixtures.py.

Generado el: {generated_at}
Tenant: {tenant}
Total de casos: {total}
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.fixture(scope="module")
def bot_fixture(tmp_path_factory):
    """Bot en mock mode para regresión (sin API key real)."""
    from bot_sales.core.database import Database
    from bot_sales.bot import SalesBot

    tmp = tmp_path_factory.mktemp("regression_db")
    db_file = tmp / "regression.db"
    catalog_file = tmp / "catalog.csv"
    with open(catalog_file, "w") as f:
        f.write("SKU,Category,Model,StockQty,PriceARS\\n")
    log_file = tmp / "bot.log"

    db = Database(str(db_file), str(catalog_file), str(log_file))
    bot = SalesBot(db=db, api_key="mock_key_regression", sandbox_mode=True)
    yield bot
    bot.close()

'''

_TEST_TEMPLATE = '''\

# ──────────────────────────────────────────────────────────────
# Caso: {fixture_name}
# Review: {review_id}
# Exportado: {created_at}
# Label esperado: {review_label}
# Route esperado: {route_source}
# ──────────────────────────────────────────────────────────────
def test_{safe_name}(bot_fixture):
    """
    Regresión desde caso de training #{review_id_short}.
    Input del cliente: {user_input_preview}
    """
    user_input = {user_input!r}
    response = bot_fixture.process_message("regression_{safe_name}", user_input)

    # El bot siempre debe responder con texto no vacío
    assert response, "El bot devolvió respuesta vacía"
    assert len(response.strip()) > 0

    # Verificar que la respuesta no es un error técnico interno
    assert "traceback" not in response.lower(), "La respuesta contiene un traceback"
    assert "exception" not in response.lower(), "La respuesta contiene una excepción"
{family_assertion}'''


def _build_family_assertion(payload: dict) -> str:
    family = payload.get("suggested_family")
    canonical = payload.get("suggested_canonical_product")
    lines = []
    if family:
        lines.append(
            f"\n    # El bot debería mencionar la familia esperada: {family!r}"
        )
        lines.append(
            f"    # assert {family.lower()!r} in response.lower()  # descomentar si aplica"
        )
    if canonical:
        lines.append(
            f"\n    # Producto canónico esperado: {canonical!r}"
        )
        lines.append(
            f"    # assert {canonical.lower()!r} in response.lower()  # descomentar si aplica"
        )
    return "\n".join(lines)


def generate(tenant_slug: str, output_dir: Path, dry_run: bool = False) -> int:
    db_path = _find_training_db(tenant_slug)
    if not db_path.exists():
        print(f"[ERROR] DB de training no encontrada: {db_path}")
        print("  Asegurate de que el tenant esté configurado y la DB exista.")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM regression_case_exports ORDER BY created_at ASC"
    ).fetchall()
    conn.close()

    if not rows:
        print("[INFO] No hay regression_case_exports en la DB.")
        return 0

    from datetime import datetime

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    test_functions: list[str] = []
    seen_names: set[str] = set()

    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        fixture_name = row["fixture_name"] or f"case_{row['id'][:8]}"
        safe_name = _slugify(fixture_name)

        # Evitar duplicados de nombre
        original = safe_name
        counter = 2
        while safe_name in seen_names:
            safe_name = f"{original}_{counter}"
            counter += 1
        seen_names.add(safe_name)

        user_input = payload.get("user_input") or ""
        test_functions.append(
            _TEST_TEMPLATE.format(
                fixture_name=fixture_name,
                review_id=row["review_id"],
                review_id_short=row["review_id"][:8],
                created_at=row["created_at"],
                review_label=payload.get("review_label", "unknown"),
                route_source=payload.get("route_source", "unknown"),
                safe_name=safe_name,
                user_input=user_input,
                user_input_preview=(user_input[:60] + "...") if len(user_input) > 60 else user_input,
                family_assertion=_build_family_assertion(payload),
            )
        )

    file_content = _FILE_HEADER.format(
        generated_at=generated_at,
        tenant=tenant_slug,
        total=len(rows),
    ) + "\n".join(test_functions) + "\n"

    if dry_run:
        print(f"[DRY RUN] Se generarían {len(rows)} tests en {output_dir}/test_regression_cases.py")
        print(f"[DRY RUN] Primeros 500 chars:\n{file_content[:500]}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "test_regression_cases.py"
    out_file.write_text(file_content, encoding="utf-8")

    # Crear __init__.py si no existe
    init = output_dir / "__init__.py"
    if not init.exists():
        init.write_text("# Regression tests — auto-generados\n")

    print(f"[OK] {len(rows)} tests generados en {out_file}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Genera fixtures de regresión desde training DB")
    parser.add_argument("--tenant", default="ferreteria", help="Slug del tenant (default: ferreteria)")
    parser.add_argument("--output", default="tests/regression", help="Directorio de salida")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar output sin escribir archivos")
    args = parser.parse_args()

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    sys.exit(generate(args.tenant, output_dir, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
