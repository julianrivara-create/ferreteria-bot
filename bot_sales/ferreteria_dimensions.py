from __future__ import annotations

import re
from typing import Any, Dict, List

from bot_sales.ferreteria_language import normalize_basic


_MATERIAL_TERMS = {
    "madera": "madera",
    "metal": "metal",
    "hormigon": "hormigon",
    "ceramica": "ceramica",
    "pvc": "pvc",
    "hierro": "hierro",
    "flexible": "flexible",
    "nylon": "nylon",
    "inox": "inox",
}

_USE_TERMS = {
    "chapa": "chapa",
    "madera": "madera",
    "durlock": "durlock",
    "sanitaria": "sanitaria",
    "construccion": "construccion",
    "vidrio": "vidrio",
    "obra": "obra",
}

_TYPE_TERMS = {
    "latex": "latex",
    "esmalte": "esmalte",
    "neutra": "neutra",
    "acetica": "acetica",
    "acida": "acetica",
    "autoperforante": "autoperforante",
    "hexagonal": "hexagonal",
    "ajustable": "ajustable",
    "antigota": "antigota",
}

_ENVIRONMENT_TERMS = {
    "interior": "interior",
    "exterior": "exterior",
}

_COLOR_TERMS = {
    "blanco": "blanco",
    "blanca": "blanco",
    "negro": "negro",
    "negra": "negro",
    "transparente": "transparente",
}

_SURFACE_TERMS = {
    "madera": "madera",
    "metal": "metal",
    "hormigon": "hormigon",
    "ceramica": "ceramica",
    "chapa": "chapa",
    "durlock": "durlock",
}


def _find_first(normalized_text: str, mapping: Dict[str, str]) -> str | None:
    for key, value in mapping.items():
        if re.search(rf"\b{re.escape(key)}\b", normalized_text):
            return value
    return None


def extract_dimensions(text: str, family_rule: Dict[str, Any] | None = None) -> Dict[str, str]:
    normalized = normalize_basic(text)
    dims: Dict[str, str] = {}

    size_match = re.search(r"\bn\s?(\d{1,2})\b", normalized)
    if size_match:
        dims["size"] = f"N{size_match.group(1)}"
        dims.setdefault("diameter", f"{size_match.group(1)}mm")

    mm_match = re.search(r"\b(\d+(?:[.,]\d+)?)mm\b", normalized)
    if mm_match:
        value = mm_match.group(1).replace(",", ".")
        dims["diameter"] = f"{value}mm"
        dims.setdefault("size", f"{value}mm")

    fraction_match = re.search(r"\b(\d+/\d+)\b", normalized)
    if fraction_match:
        dims.setdefault("diameter", fraction_match.group(1))
        dims.setdefault("size", fraction_match.group(1))

    combo_match = re.search(r"\b(\d+(?:[.,]\d+)?)x(\d+(?:[.,]\d+)?(?:/\d+)?)\b", normalized)
    if combo_match:
        first = combo_match.group(1).replace(",", ".")
        second = combo_match.group(2).replace(",", ".")
        dims["size"] = f"{first}x{second}"
        dims.setdefault("diameter", f"{first}mm")
        dims["length"] = second

    liters_match = re.search(r"\b(\d+(?:[.,]\d+)?)(l|ml|m)\b", normalized)
    if liters_match:
        qty = liters_match.group(1).replace(",", ".")
        unit = liters_match.group(2)
        dims["presentation"] = f"{qty}{unit}"

    power_match = re.search(r"\b(\d{2,4})w\b", normalized)
    if power_match:
        dims["power"] = f"{power_match.group(1)}w"

    voltage_match = re.search(r"\b(\d{2,3})v\b", normalized)
    if voltage_match:
        dims["voltage"] = f"{voltage_match.group(1)}v"

    pack_match = re.search(r"\bx\s*(\d{2,3})\b", normalized)
    if pack_match:
        dims["pack_quantity"] = pack_match.group(1)
        dims["unit_mode"] = "pack"

    material = _find_first(normalized, _MATERIAL_TERMS)
    if material:
        dims["material"] = material

    use = _find_first(normalized, _USE_TERMS)
    if use:
        dims["use"] = use

    surface = _find_first(normalized, _SURFACE_TERMS)
    if surface:
        dims["surface"] = surface

    dtype = _find_first(normalized, _TYPE_TERMS)
    if dtype:
        dims["type"] = dtype

    environment = _find_first(normalized, _ENVIRONMENT_TERMS)
    if environment:
        dims["environment"] = environment

    color = _find_first(normalized, _COLOR_TERMS)
    if color:
        dims["color"] = color

    if "sanitaria" in normalized:
        dims.setdefault("use", "sanitaria")
    if "widia" in normalized:
        dims.setdefault("material", "hormigon")
        dims.setdefault("surface", "hormigon")
    if "fisher" in normalized or "fischer" in normalized:
        dims.setdefault("material", "nylon")

    if family_rule:
        family = family_rule.get("family_id") or ""
        if family in {"mecha", "broca"} and "surface" in dims and "material" not in dims:
            dims["material"] = dims["surface"]
        if family in {"tornillo"} and "use" not in dims and "surface" in dims:
            dims["use"] = dims["surface"]
        if family in {"pintura", "latex"} and dims.get("type") == "latex":
            dims.setdefault("use", "pintura")

    return dims


def merge_dimensions(base: Dict[str, str] | None, clarification: Dict[str, str] | None) -> Dict[str, str]:
    merged = dict(base or {})
    for key, value in (clarification or {}).items():
        if value:
            merged[key] = value
    return merged


def missing_required_dimensions(family_rule: Dict[str, Any] | None, dims: Dict[str, str]) -> List[str]:
    if not family_rule:
        return []
    missing: List[str] = []
    required = list(family_rule.get("required_dimensions") or [])
    autopick = list(family_rule.get("autopick_min_dimensions") or [])
    for dimension in required + autopick:
        if dimension not in missing and not dims.get(dimension):
            missing.append(dimension)
    return missing
