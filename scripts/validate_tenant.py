#!/usr/bin/env python3
"""Validate tenant scaffold and index consistency."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
TENANTS_FILE = ROOT / "tenants.yaml"
PHONE_RE = re.compile(r"^whatsapp:\+\d{8,15}$")


def load_index() -> Dict[str, Any]:
    if not TENANTS_FILE.exists():
        raise SystemExit(f"tenants index not found: {TENANTS_FILE}")
    data = yaml.safe_load(TENANTS_FILE.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or "tenants" not in data:
        raise SystemExit("Invalid tenants.yaml: expected top-level 'tenants' list")
    return data


def validate_catalog(catalog_path: Path) -> Tuple[bool, str]:
    if not catalog_path.exists():
        return False, f"catalog not found: {catalog_path}"

    with catalog_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        headers = next(reader, [])
    norm_headers = {h.strip().lower() for h in headers if h}

    new_required = {"sku", "category", "name", "price", "currency", "stock"}

    # Accept legacy with canonical header names (case-insensitive)
    if {"sku", "category", "model", "stockqty", "pricears"}.issubset(norm_headers):
        return True, "legacy-csv"
    if new_required.issubset(norm_headers):
        return True, "new-csv"
    return False, "catalog headers must match legacy or new format"


def validate_profile(profile_path: Path) -> Tuple[bool, str, Dict[str, Any]]:
    if not profile_path.exists():
        return False, f"profile not found: {profile_path}", {}

    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    required_top = ["id", "slug", "business", "paths"]
    for key in required_top:
        if key not in data:
            return False, f"profile missing key: {key}", {}

    business = data.get("business") or {}
    for key in ["name", "industry", "language", "currency", "country"]:
        if not business.get(key):
            return False, f"profile.business missing key: {key}", {}

    paths = data.get("paths") or {}
    for key in ["db", "catalog", "policies", "branding"]:
        if not paths.get(key):
            return False, f"profile.paths missing key: {key}", {}

    return True, "ok", data


def validate_tenant_entry(entry: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    slug = entry.get("slug") or entry.get("id")
    if not slug:
        return ["index entry missing slug/id"]

    required_index_keys = ["id", "slug", "name", "profile_path", "db_file", "catalog_file", "policies_file", "branding_file"]
    for key in required_index_keys:
        if not entry.get(key):
            errors.append(f"[{slug}] index missing key: {key}")

    for phone in entry.get("phone_numbers") or []:
        if phone and not PHONE_RE.match(phone):
            errors.append(f"[{slug}] invalid phone format '{phone}' (expected whatsapp:+########)")

    profile_path = ROOT / str(entry.get("profile_path", ""))
    ok, msg, profile = validate_profile(profile_path)
    if not ok:
        errors.append(f"[{slug}] {msg}")
        return errors

    if profile.get("slug") != entry.get("slug"):
        errors.append(f"[{slug}] slug mismatch between tenants.yaml and profile.yaml")

    # Validate referenced tenant files from profile and index.
    profile_paths = profile.get("paths") or {}
    for key in ["catalog", "policies", "branding"]:
        path = ROOT / str(profile_paths.get(key, ""))
        if not path.exists():
            errors.append(f"[{slug}] missing file from profile.paths.{key}: {path}")

    index_catalog_path = ROOT / str(entry.get("catalog_file", ""))
    cat_ok, cat_msg = validate_catalog(index_catalog_path)
    if not cat_ok:
        errors.append(f"[{slug}] {cat_msg}")

    if profile_paths.get("catalog") != entry.get("catalog_file"):
        errors.append(f"[{slug}] catalog path mismatch profile vs index")
    if profile_paths.get("policies") != entry.get("policies_file"):
        errors.append(f"[{slug}] policies path mismatch profile vs index")
    if profile_paths.get("branding") != entry.get("branding_file"):
        errors.append(f"[{slug}] branding path mismatch profile vs index")
    if profile_paths.get("db") != entry.get("db_file"):
        errors.append(f"[{slug}] db path mismatch profile vs index")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tenant files and index consistency")
    parser.add_argument("--slug", help="Validate only one tenant slug")
    args = parser.parse_args()

    data = load_index()
    entries = data.get("tenants", [])
    if args.slug:
        entries = [t for t in entries if t.get("slug") == args.slug or t.get("id") == args.slug]
        if not entries:
            raise SystemExit(f"Tenant not found in index: {args.slug}")

    all_errors: List[str] = []
    for entry in entries:
        slug = entry.get("slug") or entry.get("id")
        errors = validate_tenant_entry(entry)
        if errors:
            all_errors.extend(errors)
        else:
            print(f"[OK] {slug}")

    if all_errors:
        print("\nValidation failed:")
        for err in all_errors:
            print(f" - {err}")
        raise SystemExit(1)

    print(f"\nValidation passed for {len(entries)} tenant(s).")


if __name__ == "__main__":
    main()
