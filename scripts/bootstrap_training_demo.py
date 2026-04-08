#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_sales.training.demo_bootstrap import bootstrap_training_demo


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera un mini demo local y aislado para la interfaz de entrenamiento de Ferretería.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "tmp" / "training_demo"),
        help="Directorio donde se van a guardar el entorno demo aislado y los snapshots.",
    )
    parser.add_argument(
        "--admin-token",
        default="demo-admin-token",
        help="Token usado solo para renderizar las páginas protegidas en snapshots estáticos del demo.",
    )
    args = parser.parse_args()

    manifest = bootstrap_training_demo(
        args.output_dir,
        admin_token=args.admin_token,
    )

    print("Mini demo de entrenamiento generado.")
    print(f"Directorio de salida : {manifest['output_dir']}")
    print(f"Índice de snapshots  : {manifest['index_path']}")
    print(f"Guía de recorrido    : {manifest['walkthrough_path']}")
    print(f"Base demo            : {manifest['db_path']}")
    print("")
    print("Vista rápida:")
    print(f"  python3 -m http.server 8033 --directory \"{manifest['snapshot_dir']}\"")
    print("  open http://127.0.0.1:8033/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
