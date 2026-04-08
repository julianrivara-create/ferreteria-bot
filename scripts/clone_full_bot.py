#!/usr/bin/env python3
"""Clone this full platform base into a new bot folder in one command."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "htmlcov",
    ".coverage",
    "coverage.xml",
)


def slugify(text: str) -> str:
    value = text.strip().lower()
    value = "".join(c if c.isalnum() else "-" for c in value)
    while "--" in value:
        value = value.replace("--", "-")
    return value.strip("-") or "tenant"


def ensure_destination(destination: Path, force: bool) -> None:
    resolved_root = ROOT.resolve()
    resolved_destination = destination.resolve()
    if resolved_destination == resolved_root:
        raise SystemExit("Destination cannot be the current project root.")
    if str(resolved_destination).startswith(str(resolved_root) + "/"):
        raise SystemExit("Destination cannot be inside the source project.")

    if destination.exists():
        if not force:
            raise SystemExit(f"Destination already exists: {destination} (use --force)")
        shutil.rmtree(destination)


def copy_base(destination: Path) -> None:
    shutil.copytree(ROOT, destination, ignore=DEFAULT_IGNORE)


def cleanup_runtime_artifacts(destination: Path) -> None:
    for file_path in destination.rglob("*.pyc"):
        if file_path.is_file():
            file_path.unlink(missing_ok=True)

    for pycache_dir in destination.rglob("__pycache__"):
        if pycache_dir.is_dir():
            shutil.rmtree(pycache_dir, ignore_errors=True)

    for path in destination.glob("data/*.db"):
        if path.is_file():
            path.unlink(missing_ok=True)

    for path in destination.glob("data/*.sqlite"):
        if path.is_file():
            path.unlink(missing_ok=True)

    for path in destination.glob("data/*.sqlite3"):
        if path.is_file():
            path.unlink(missing_ok=True)

    for path in destination.glob("logs/*.log"):
        if path.is_file():
            path.unlink(missing_ok=True)


def run_command(cmd: Sequence[str], cwd: Path) -> Tuple[int, str, str]:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def create_seed_tenant(
    destination: Path,
    tenant_name: str,
    tenant_slug: str,
    industry: str,
    language: str,
    currency: str,
    country: str,
    tone: str,
    phone: str,
) -> None:
    cmd: List[str] = [
        sys.executable,
        "scripts/create_tenant.py",
        "--non-interactive",
        "--name",
        tenant_name,
        "--slug",
        tenant_slug,
        "--industry",
        industry,
        "--language",
        language,
        "--currency",
        currency,
        "--country",
        country,
        "--tone",
        tone,
    ]
    if phone:
        cmd.extend(["--phone", phone])

    code, out, err = run_command(cmd, destination)
    if code != 0:
        raise SystemExit(
            "Tenant creation failed in cloned project.\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}"
        )


def run_post_clone_checks(destination: Path, checks: Iterable[Sequence[str]]) -> None:
    failures: List[str] = []
    for cmd in checks:
        code, out, err = run_command(cmd, destination)
        if code != 0:
            failures.append(
                f"- {' '.join(cmd)}\n"
                f"  exit={code}\n"
                f"  stdout={out.strip()[-400:]}\n"
                f"  stderr={err.strip()[-400:]}"
            )

    if failures:
        raise SystemExit("Post-clone checks failed:\n" + "\n".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clone full sales-bot-platform base and optionally seed a tenant."
    )
    parser.add_argument(
        "--destination",
        required=True,
        help="Absolute or relative path for the new bot folder",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete destination if it already exists",
    )
    parser.add_argument(
        "--with-tenant",
        action="store_true",
        help="Create an initial tenant in the cloned folder",
    )
    parser.add_argument("--tenant-name", default="Nuevo Negocio", help="Initial tenant business name")
    parser.add_argument("--tenant-slug", help="Initial tenant slug (default: slugified tenant-name)")
    parser.add_argument(
        "--industry",
        default="generic",
        choices=["technology", "pharmacy", "clothing", "ferreteria", "generic"],
        help="Industry for initial tenant",
    )
    parser.add_argument("--language", default="es")
    parser.add_argument("--currency", default="ARS")
    parser.add_argument("--country", default="AR")
    parser.add_argument("--tone", default="informal")
    parser.add_argument("--phone", default="")
    parser.add_argument(
        "--run-checks",
        action="store_true",
        help="Run doctor + tenancy checks in cloned folder",
    )
    args = parser.parse_args()

    destination = Path(args.destination).expanduser()
    if not destination.is_absolute():
        destination = (Path.cwd() / destination).resolve()

    ensure_destination(destination, force=args.force)
    copy_base(destination)
    cleanup_runtime_artifacts(destination)

    tenant_slug = args.tenant_slug or slugify(args.tenant_name)
    if args.with_tenant:
        create_seed_tenant(
            destination=destination,
            tenant_name=args.tenant_name,
            tenant_slug=tenant_slug,
            industry=args.industry,
            language=args.language,
            currency=args.currency,
            country=args.country,
            tone=args.tone,
            phone=args.phone,
        )

    if args.run_checks:
        commands = [
            [sys.executable, "scripts/doctor_base.py"],
            [sys.executable, "scripts/validate_tenant.py"],
            [sys.executable, "scripts/smoke_runtime.py"],
        ]
        run_post_clone_checks(destination, commands)

    print("=" * 72)
    print("Base cloned successfully")
    print("=" * 72)
    print(f"Source      : {ROOT}")
    print(f"Destination : {destination}")
    print(f"Tenant seed : {'yes' if args.with_tenant else 'no'}")
    if args.with_tenant:
        print(f"Tenant slug : {tenant_slug}")
    print(f"Checks run  : {'yes' if args.run_checks else 'no'}")
    print()
    print("Next steps:")
    print(f"1) cd {destination}")
    print("2) python3 scripts/doctor_base.py")
    print("3) python3 scripts/validate_tenant.py")


if __name__ == "__main__":
    main()
