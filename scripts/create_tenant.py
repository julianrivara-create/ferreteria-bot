#!/usr/bin/env python3
"""Create a new tenant profile with starter catalog/policies/branding."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
TENANTS_FILE = ROOT / "tenants.yaml"
TENANTS_DIR = ROOT / "data" / "tenants"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
LANG_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


INDUSTRY_CATALOGS: Dict[str, List[Dict[str, Any]]] = {
    "technology": [
        {"sku": "PHN-001", "category": "Smartphones", "name": "Smartphone X 128GB", "price": 1200000, "stock": 8, "color": "Black", "storage_gb": 128, "brand": "TechNova"},
        {"sku": "LPT-001", "category": "Laptops", "name": "Laptop Pro 14", "price": 2200000, "stock": 5, "color": "Silver", "storage_gb": 512, "brand": "TechNova"},
        {"sku": "EAR-001", "category": "Audio", "name": "Earbuds ANC", "price": 240000, "stock": 20, "color": "White", "brand": "TechNova"},
    ],
    "pharmacy": [
        {"sku": "MED-001", "category": "Analgésicos", "name": "Ibuprofeno 400mg", "price": 450, "stock": 120, "requires_prescription": "No", "active_ingredient": "Ibuprofeno", "dosage": "400mg", "brand": "GenericoPharma"},
        {"sku": "MED-002", "category": "Antibióticos", "name": "Amoxicilina 500mg", "price": 1200, "stock": 40, "requires_prescription": "Si", "active_ingredient": "Amoxicilina", "dosage": "500mg", "brand": "AntibioMax"},
        {"sku": "COS-001", "category": "Cuidado Personal", "name": "Protector Solar FPS50", "price": 1800, "stock": 70, "requires_prescription": "No", "brand": "SunCare"},
    ],
    "clothing": [
        {"sku": "CLO-001", "category": "Remeras", "name": "Remera Basica", "price": 18000, "stock": 40, "size": "M", "color": "Black", "material": "Algodon", "brand": "UrbanFit"},
        {"sku": "CLO-002", "category": "Pantalones", "name": "Jean Slim", "price": 42000, "stock": 25, "size": "32", "color": "Blue", "material": "Denim", "brand": "UrbanFit"},
        {"sku": "CLO-003", "category": "Calzado", "name": "Zapatilla Runner", "price": 56000, "stock": 18, "size": "42", "color": "White", "material": "Mesh", "brand": "RunCo"},
    ],
    "ferreteria": [
        {
            "sku": "FER-001",
            "category": "Herramientas",
            "name": "Taladro Percutor 13mm",
            "price": 125000,
            "stock": 12,
            "brand": "ProTools",
            "power_w": 710,
            "voltage": "220V",
            "use": "hogar-profesional",
        },
        {
            "sku": "FER-002",
            "category": "Tornilleria",
            "name": "Caja Tornillos Autoperforantes x100",
            "price": 9500,
            "stock": 45,
            "brand": "FixPro",
            "material": "Acero zincado",
            "size": "8x1",
            "units_per_pack": 100,
        },
        {
            "sku": "FER-003",
            "category": "Pintureria",
            "name": "Pintura Latex Interior 20L",
            "price": 68000,
            "stock": 16,
            "brand": "ColorPlus",
            "color": "Blanco",
            "finish": "Mate",
            "volume_l": 20,
        },
    ],
    "generic": [
        {"sku": "PRD-001", "category": "General", "name": "Producto Demo 1", "price": 10000, "stock": 10},
        {"sku": "PRD-002", "category": "General", "name": "Producto Demo 2", "price": 15000, "stock": 6},
    ],
}


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "tenant"


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def normalize_phone(raw_phone: str) -> str:
    value = (raw_phone or "").strip()
    if not value:
        return ""
    if value.startswith("whatsapp:+"):
        normalized = "+" + re.sub(r"\D", "", value.split("whatsapp:+", 1)[1])
        return f"whatsapp:{normalized}" if normalized != "+" else ""
    if value.startswith("+"):
        normalized = "+" + re.sub(r"\D", "", value)
        return f"whatsapp:{normalized}" if normalized != "+" else ""
    digits = re.sub(r"\D", "", value)
    return f"whatsapp:+{digits}" if digits else ""


def validate_slug(value: str) -> str:
    if not SLUG_RE.match(value):
        raise SystemExit(
            "Invalid slug. Use lowercase letters, numbers and '-', between 3 and 50 chars."
        )
    return value


def validate_language(value: str) -> str:
    lang = (value or "").strip()
    if not LANG_RE.match(lang):
        raise SystemExit("Invalid language code. Use format 'es' or 'es-AR'.")
    return lang


def validate_currency(value: str) -> str:
    currency = (value or "").strip().upper()
    if not CURRENCY_RE.match(currency):
        raise SystemExit("Invalid currency code. Use ISO-4217 (e.g. ARS, USD, EUR).")
    return currency


def validate_country(value: str) -> str:
    country = (value or "").strip().upper()
    if not COUNTRY_RE.match(country):
        raise SystemExit("Invalid country code. Use ISO-3166-1 alpha-2 (e.g. AR, US, MX).")
    return country


def collect_inputs(args: argparse.Namespace) -> Dict[str, str]:
    if args.non_interactive:
        missing = [k for k in ("name", "industry") if not getattr(args, k)]
        if missing:
            raise SystemExit(f"Missing required arguments in --non-interactive mode: {', '.join(missing)}")

    name = (args.name or ask("Nombre del negocio")).strip()
    if not name:
        raise SystemExit("Business name is required.")

    if args.industry and args.industry not in INDUSTRY_CATALOGS:
        raise SystemExit(
            f"Invalid industry '{args.industry}'. Allowed: {', '.join(sorted(INDUSTRY_CATALOGS.keys()))}"
        )
    industry = args.industry
    if not industry:
        industry = ask("Industria (technology/pharmacy/clothing/ferreteria/generic)", "generic").strip().lower()
        if industry not in INDUSTRY_CATALOGS:
            raise SystemExit(
                f"Invalid industry '{industry}'. Allowed: {', '.join(sorted(INDUSTRY_CATALOGS.keys()))}"
            )

    slug = validate_slug((args.slug or slugify(name)).strip())

    if args.non_interactive:
        language = validate_language((args.language or "es").strip())
        currency = validate_currency((args.currency or "ARS").strip())
        country = validate_country((args.country or "AR").strip())
        tone = (args.tone or "informal").strip() or "informal"
        phone = normalize_phone(args.phone or "")
    else:
        language = validate_language((args.language or ask("Idioma", "es")).strip())
        currency = validate_currency((args.currency or ask("Moneda", "ARS")).strip())
        country = validate_country((args.country or ask("Pais", "AR")).strip())
        tone = (args.tone or ask("Tono", "informal")).strip() or "informal"
        phone = normalize_phone(args.phone or ask("Numero WhatsApp del negocio (opcional)", ""))

    return {
        "name": name,
        "slug": slug,
        "industry": industry,
        "language": language,
        "currency": currency,
        "country": country,
        "tone": tone,
        "phone": phone,
    }


def build_profile(cfg: Dict[str, str]) -> Dict[str, Any]:
    tenant_id = cfg["slug"]
    base_path = f"data/tenants/{cfg['slug']}"

    visible_categories = sorted({item["category"] for item in INDUSTRY_CATALOGS[cfg["industry"]]})

    return {
        "id": tenant_id,
        "slug": cfg["slug"],
        "business": {
            "name": cfg["name"],
            "description": f"Negocio del rubro {cfg['industry']}",
            "industry": cfg["industry"],
            "language": cfg["language"],
            "currency": cfg["currency"],
            "country": cfg["country"],
            "tone": cfg["tone"],
            "visible_categories": visible_categories,
        },
        "personality": {
            "tone": cfg["tone"],
            "emojis": "✅",
        },
        "communication": {
            "whatsapp_numbers": [cfg["phone"]] if cfg["phone"] else [],
        },
        "cross_sell_rules": [],
        "paths": {
            "db": f"data/{cfg['slug']}.db",
            "catalog": f"{base_path}/catalog.csv",
            "policies": f"{base_path}/policies.md",
            "branding": f"{base_path}/branding.json",
        },
    }


def build_branding(cfg: Dict[str, str]) -> Dict[str, Any]:
    return {
        "brand_name": cfg["name"],
        "tagline": f"{cfg['industry'].capitalize()} store",
        "hero_title": cfg["name"],
        "hero_subtitle": "Catalogo y ventas asistidas por IA",
        "accent_color": "#2b6cb0",
        "secondary_color": "#2f855a",
        "currency_symbol": "$",
    }


def build_policies(cfg: Dict[str, str]) -> str:
    return f"""# Politicas de {cfg['name']}

## Envios
- Entregas de 24 a 72 horas segun zona.
- Se confirma fecha exacta al cerrar la compra.

## Pagos
- Transferencia
- Efectivo
- Pasarela de pago

## Cambios y Devoluciones
- Se aceptan dentro de 10 dias con comprobante de compra.

## Atencion
- Horario comercial en dias habiles.
"""


def build_catalog(cfg: Dict[str, str]) -> Tuple[List[str], List[Dict[str, Any]]]:
    rows = []
    for item in INDUSTRY_CATALOGS[cfg["industry"]]:
        row = dict(item)
        row["currency"] = cfg["currency"]
        rows.append(row)

    base_cols = ["sku", "category", "name", "price", "currency", "stock"]
    extra_cols = sorted({k for row in rows for k in row.keys() if k not in base_cols})
    return base_cols + extra_cols, rows


def write_catalog(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def upsert_tenant_index(cfg: Dict[str, str], profile: Dict[str, Any]) -> None:
    if TENANTS_FILE.exists():
        data = yaml.safe_load(TENANTS_FILE.read_text(encoding="utf-8")) or {}
    else:
        data = {}

    tenants = data.get("tenants", [])
    tenant_id = cfg["slug"]

    entry = {
        "id": tenant_id,
        "slug": cfg["slug"],
        "name": cfg["name"],
        "profile_path": f"data/tenants/{cfg['slug']}/profile.yaml",
        "phone_numbers": [cfg["phone"]] if cfg["phone"] else [],
        "db_file": profile["paths"]["db"],
        "catalog_file": profile["paths"]["catalog"],
        "policies_file": profile["paths"]["policies"],
        "branding_file": profile["paths"]["branding"],
        "api_keys": {
            "openai": "${OPENAI_API_KEY}",
            "gemini": "${GEMINI_API_KEY}",
        },
        "features": {
            "fraud_detection": True,
            "sentiment_analysis": True,
        },
    }

    updated = False
    for idx, tenant in enumerate(tenants):
        if tenant.get("id") == tenant_id or tenant.get("slug") == cfg["slug"]:
            tenants[idx] = entry
            updated = True
            break

    if not updated:
        tenants.append(entry)

    data["tenants"] = tenants
    TENANTS_FILE.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create tenant scaffold for Salesbot Platform")
    parser.add_argument("--name", help="Business name")
    parser.add_argument("--slug", help="Tenant slug (URL id)")
    parser.add_argument("--industry", choices=sorted(INDUSTRY_CATALOGS.keys()), help="Business industry")
    parser.add_argument("--language", help="Language code (default: es)")
    parser.add_argument("--currency", help="Currency code (default: ARS)")
    parser.add_argument("--country", help="Country code (default: AR)")
    parser.add_argument("--tone", help="Bot tone (default: informal)")
    parser.add_argument("--phone", help="WhatsApp number associated with this tenant")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt for missing data")
    parser.add_argument(
        "--skip-crm-bootstrap",
        action="store_true",
        help="Skip syncing tenant to Final Production CRM tables",
    )
    args = parser.parse_args()

    cfg = collect_inputs(args)
    tenant_dir = TENANTS_DIR / cfg["slug"]
    tenant_dir.mkdir(parents=True, exist_ok=True)

    profile = build_profile(cfg)
    branding = build_branding(cfg)
    policies = build_policies(cfg)
    fieldnames, catalog_rows = build_catalog(cfg)

    (tenant_dir / "profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (tenant_dir / "branding.json").write_text(
        json.dumps(branding, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tenant_dir / "policies.md").write_text(policies, encoding="utf-8")
    write_catalog(tenant_dir / "catalog.csv", fieldnames, catalog_rows)

    upsert_tenant_index(cfg, profile)

    print("=" * 68)
    print("Tenant created/updated successfully")
    print("=" * 68)
    print(f"ID/Slug: {cfg['slug']}")
    print(f"Name   : {cfg['name']}")
    print(f"Industry: {cfg['industry']}")
    print(f"Profile: {tenant_dir / 'profile.yaml'}")
    print(f"Catalog: {tenant_dir / 'catalog.csv'}")
    print("Updated index:", TENANTS_FILE)

    if not args.skip_crm_bootstrap:
        bootstrap_script = ROOT / "scripts" / "bootstrap_finalprod_crm.py"
        if bootstrap_script.exists():
            proc = subprocess.run(
                [sys.executable, str(bootstrap_script)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                print("CRM bootstrap synced.")
            else:
                print("CRM bootstrap warning (tenant files are still created):")
                if proc.stderr.strip():
                    print(proc.stderr.strip())
        else:
            print("CRM bootstrap script not found, skipping.")


if __name__ == "__main__":
    main()
