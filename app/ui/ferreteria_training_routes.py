from __future__ import annotations

import hashlib
import hmac
import json
import os
from functools import wraps
from pathlib import Path
import re

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.api.ferreteria_training_routes import (
    ALLOWED_SUGGESTION_DOMAINS,
    get_training_services,
)
from bot_sales.knowledge.validators import KnowledgeValidationError


ferreteria_training_ui = Blueprint(
    "ferreteria_training_ui",
    __name__,
    template_folder="templates",
)

# ── Session-based auth for browser access ────────────────────────────────────
_TRAINING_SESSION_KEY = "training_logged_in"
_TRAINING_SALT = b"ferreteria-training-ui-v1"
_PBKDF2_ITERATIONS = 260_000


def _training_password_hash() -> bytes:
    raw = os.getenv("ADMIN_PASSWORD", "")
    if not raw:
        raise RuntimeError("ADMIN_PASSWORD env var is required.")
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), _TRAINING_SALT, _PBKDF2_ITERATIONS)


def training_login_required(f):
    """Allow access via Flask session (browser login) OR X-Admin-Token header (API/scripts)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Header-based auth (scripts, curl, API calls) — unchanged behaviour
        from app.core.config import get_settings
        settings = get_settings()
        token = request.headers.get("X-Admin-Token", "")
        if settings.is_secret_configured(settings.ADMIN_TOKEN) and token:
            if hmac.compare_digest(token, settings.ADMIN_TOKEN):
                return f(*args, **kwargs)

        # Session-based auth (browser login)
        if session.get(_TRAINING_SESSION_KEY):
            return f(*args, **kwargs)

        # Neither valid → redirect to login
        return redirect(url_for("ferreteria_training_ui.training_login", next=request.path))
    return wrapper


ROOT_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT_DIR / "docs"
GUIDE_PATH = DOCS_DIR / "guia_operativa_entrenamiento_ferreteria.md"
FAQ_PATH = DOCS_DIR / "faq_entrenamiento_ferreteria.md"
DEMO_BOOTSTRAP_COMMAND = f"cd {ROOT_DIR}\npython3 scripts/bootstrap_training_demo.py"
DEMO_OPEN_COMMAND = (
    f"cd {ROOT_DIR}\n"
    "python3 -m http.server 8033 --directory tmp/training_demo/snapshots\n"
    "open http://127.0.0.1:8033/index.html"
)
DEMO_INDEX_HINT = "tmp/training_demo/snapshots/index.html"


def _read_support_doc(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return fallback


DOMAIN_HELP = {
    "synonym": "Ayuda a que el bot entienda una forma real de pedir un producto y la lleve al término correcto.",
    "unresolved_term_mapping": "Sirve para registrar una forma de pedir algo que se repite y todavía no está bien resuelta.",
    "faq": "Agrega o corrige una respuesta corta para preguntas frecuentes o de política del local.",
    "clarification_rule": "Mejora la primera pregunta que el bot debe hacer antes de avanzar con una familia conocida.",
    "family_rule": "Ajusta cómo el bot detecta o bloquea una familia de productos.",
    "blocked_term": "Evita que un término demasiado amplio se resuelva antes de tiempo.",
    "complementary_rule": "Sugiere complementos útiles solo cuando realmente corresponde.",
    "substitute_rule": "Define cuándo una alternativa es lo bastante segura como para proponerla.",
    "language_pattern": "Normaliza errores comunes, términos regionales o abreviaturas de forma controlada.",
    "test_case_only": "Guarda el caso como cobertura futura sin cambiar el conocimiento activo.",
}

DOMAIN_LABELS = {
    "synonym": "Corrección de término",
    "unresolved_term_mapping": "Corrección de término repetido",
    "faq": "Respuesta frecuente o política",
    "clarification_rule": "Mejorar pregunta de aclaración",
    "family_rule": "Corregir detección de producto o familia",
    "blocked_term": "No responder este término todavía",
    "complementary_rule": "Regla de complementos",
    "substitute_rule": "Regla de alternativas seguras",
    "language_pattern": "Normalización de lenguaje",
    "test_case_only": "Solo guardar como caso futuro",
}

FAILURE_TAG_CONFIG = {
    "did_not_understand_term": {
        "label": "No entendió el término",
        "problem_type": "did_not_understand_term",
    },
    "wrong_family": {
        "label": "Eligió la familia equivocada",
        "problem_type": "wrong_product_or_family",
    },
    "wrong_variant": {
        "label": "Eligió la variante equivocada",
        "problem_type": "should_have_asked_clarification",
    },
    "should_have_asked_clarification": {
        "label": "Tendría que haber pedido una aclaración",
        "problem_type": "should_have_asked_clarification",
    },
    "answered_too_unsafely": {
        "label": "Respondió de forma poco segura",
        "problem_type": "answered_too_unsafely",
    },
    "should_have_escalated": {
        "label": "Tendría que haberlo pasado a una persona",
        "problem_type": "should_not_auto_answer",
    },
    "missed_faq_or_policy": {
        "label": "Faltó una respuesta frecuente o de política",
        "problem_type": "missed_faq_or_policy",
    },
    "other": {
        "label": "Otro",
        "problem_type": "other_or_not_sure",
    },
}

FAILURE_DETAIL_CONFIG = {
    "did_not_understand_term": [
        ("alias_missing", "Falta ese término o alias"),
        ("misspelling_or_regional_term", "Era una forma regional o mal escrita"),
        ("brand_generic_confusion", "Confundió una marca con un término genérico"),
    ],
    "wrong_family": [
        ("matched_too_broadly", "Tomó una coincidencia demasiado amplia"),
        ("neighbor_family_confusion", "Cayó en una familia parecida"),
        ("ignored_context_term", "Ignoró una palabra importante del contexto"),
    ],
    "wrong_variant": [
        ("defaulted_too_early", "Se definió demasiado pronto"),
        ("missed_required_dimension", "Le faltó un dato necesario"),
        ("picked_incompatible_variant", "Eligió una variante incompatible"),
    ],
    "should_have_asked_clarification": [
        ("missing_material", "Primero necesitaba material"),
        ("missing_size", "Primero necesitaba medida"),
        ("missing_surface", "Primero necesitaba uso o superficie"),
        ("missing_presentation", "Primero necesitaba presentación"),
        ("missing_compatibility", "Primero necesitaba compatibilidad"),
    ],
    "answered_too_unsafely": [
        ("resolved_too_early", "Resolvió demasiado pronto"),
        ("substitute_was_risky", "Ofreció una alternativa riesgosa"),
        ("confirmed_without_required_data", "Confirmó sin los datos necesarios"),
    ],
    "should_have_escalated": [
        ("off_catalog_or_operator_only", "Este caso debía quedar para una persona"),
        ("repeated_failed_clarification", "Se trabó después de varias aclaraciones fallidas"),
        ("conflicting_customer_signals", "El cliente dio señales contradictorias"),
    ],
    "missed_faq_or_policy": [
        ("billing_or_invoice", "Faltó una respuesta sobre facturación"),
        ("hours_or_store_policy", "Faltó una respuesta sobre horarios o política del local"),
        ("payment_delivery_policy", "Faltó una respuesta sobre pagos o entrega"),
    ],
    "other": [
        ("other", "Otro"),
    ],
}

EXPECTED_BEHAVIOR_CONFIG = {
    "understand_term": {
        "label": "Entender bien cómo lo pidió el cliente",
        "help": "Usalo cuando la corrección principal sea entender un término o normalizar una forma de escribirlo.",
        "problem_type": "did_not_understand_term",
    },
    "choose_correct_family": {
        "label": "Elegir el producto o la familia correcta",
        "help": "Usalo cuando el bot tendría que haber tomado otra familia.",
        "problem_type": "wrong_product_or_family",
    },
    "choose_correct_variant": {
        "label": "Elegir la variante correcta recién con más detalle",
        "help": "Usalo cuando la familia estaba cerca, pero la variante quedó mal o fue prematura.",
        "problem_type": "should_have_asked_clarification",
    },
    "ask_clarification_first": {
        "label": "Pedir una aclaración antes de resolver",
        "help": "Usalo cuando faltaba una pregunta concreta antes de avanzar.",
        "problem_type": "should_have_asked_clarification",
    },
    "block_until_more_detail": {
        "label": "Frenar la respuesta hasta tener más detalle",
        "help": "Usalo cuando el pedido era demasiado amplio para responder con seguridad.",
        "problem_type": "answered_too_unsafely",
    },
    "escalate_to_operator": {
        "label": "Pasarlo a una persona",
        "help": "Usalo cuando este caso no debería resolverse en automático.",
        "problem_type": "should_not_auto_answer",
    },
    "answer_faq_or_policy": {
        "label": "Responder con una respuesta frecuente o de política",
        "help": "Usalo cuando la salida correcta es una respuesta breve y estable.",
        "problem_type": "missed_faq_or_policy",
    },
    "regression_only": {
        "label": "Guardarlo solo como caso futuro",
        "help": "Usalo cuando conviene registrar el caso sin tocar todavía el conocimiento activo.",
        "problem_type": "other_or_not_sure",
    },
}

CLARIFICATION_DIMENSION_CONFIG = {
    "material": "Material o tipo de superficie",
    "size": "Medida",
    "surface": "Uso o superficie",
    "presentation": "Presentación o pack",
    "compatibility": "Compatibilidad o modelo",
    "brand": "Marca o línea",
    "quantity": "Cantidad o unidad",
    "voltage": "Voltaje o potencia",
    "finish": "Terminación o color",
    "other": "Otro dato",
}

PROBLEM_TYPE_CONFIG = {
    "did_not_understand_term": {
        "label": "No entendió cómo lo pidió el cliente",
        "help": "Usalo cuando la frase del cliente debería llevar a un producto, una familia o una variante de lenguaje ya conocida.",
        "recommended_domain": "synonym",
        "alternatives": ["unresolved_term_mapping", "language_pattern"],
    },
    "wrong_product_or_family": {
        "label": "Eligió el producto o la familia equivocada",
        "help": "Usalo cuando el bot se fue a una familia incorrecta o tomó una coincidencia demasiado amplia.",
        "recommended_domain": "family_rule",
        "alternatives": ["synonym", "blocked_term"],
    },
    "should_have_asked_clarification": {
        "label": "Tendría que haber pedido una aclaración",
        "help": "Usalo cuando el bot estaba cerca, pero primero necesitaba una pregunta más para seguir bien.",
        "recommended_domain": "clarification_rule",
        "alternatives": ["family_rule", "blocked_term"],
    },
    "answered_too_unsafely": {
        "label": "Respondió con demasiado riesgo",
        "help": "Usalo cuando resolvió o sugirió algo antes de tener la información necesaria.",
        "recommended_domain": "blocked_term",
        "alternatives": ["substitute_rule", "family_rule"],
    },
    "missed_faq_or_policy": {
        "label": "Faltó una respuesta frecuente o de política",
        "help": "Usalo cuando lo correcto era una respuesta estándar y no entrar en el flujo de presupuesto.",
        "recommended_domain": "faq",
        "alternatives": ["language_pattern"],
    },
    "should_not_auto_answer": {
        "label": "No debería responder este caso en automático",
        "help": "Usalo cuando lo más seguro sea frenar, redirigir o dejar el caso solo como aprendizaje futuro.",
        "recommended_domain": "blocked_term",
        "alternatives": ["test_case_only", "substitute_rule"],
    },
    "other_or_not_sure": {
        "label": "Otro / no estoy seguro",
        "help": "Usalo cuando podés explicar el problema, pero todavía no estás seguro de qué corrección conviene.",
        "recommended_domain": "test_case_only",
        "alternatives": ["synonym", "family_rule", "clarification_rule"],
    },
}

SIMPLE_TEACHING_CONFIG = {
    "understand_term": {
        "label": "No entendió cómo lo pidió",
        "help": "Usalo cuando el cliente habló de una forma real y el bot no reconoció el producto o término.",
        "review_label": "incorrect",
        "failure_tag": "did_not_understand_term",
        "expected_behavior_tag": "understand_term",
        "problem_type": "did_not_understand_term",
        "domain": "synonym",
    },
    "faq_answer": {
        "label": "Faltó una respuesta estándar",
        "help": "Usalo cuando la salida correcta era una respuesta frecuente o una política del local.",
        "review_label": "incorrect",
        "failure_tag": "missed_faq_or_policy",
        "expected_behavior_tag": "answer_faq_or_policy",
        "problem_type": "missed_faq_or_policy",
        "domain": "faq",
    },
    "clarify_first": {
        "label": "Tendría que haber preguntado algo antes",
        "help": "Usalo cuando el bot estaba cerca, pero primero necesitaba una aclaración concreta.",
        "review_label": "incorrect",
        "failure_tag": "should_have_asked_clarification",
        "expected_behavior_tag": "ask_clarification_first",
        "problem_type": "should_have_asked_clarification",
        "domain": "clarification_rule",
    },
    "block_first": {
        "label": "No debería haber respondido todavía",
        "help": "Usalo cuando el bot respondió con demasiado riesgo y convenía frenar hasta tener más detalle.",
        "review_label": "unsafe",
        "failure_tag": "answered_too_unsafely",
        "expected_behavior_tag": "block_until_more_detail",
        "problem_type": "answered_too_unsafely",
        "domain": "blocked_term",
    },
    "correct_family": {
        "label": "Eligió la familia o producto equivocado",
        "help": "Usalo cuando se fue a otro producto o familia y hay que corregir esa detección.",
        "review_label": "incorrect",
        "failure_tag": "wrong_family",
        "expected_behavior_tag": "choose_correct_family",
        "problem_type": "wrong_product_or_family",
        "domain": "family_rule",
    },
    "not_sure": {
        "label": "No estoy seguro todavía",
        "help": "Usalo cuando querés guardar el aprendizaje sin forzar una corrección técnica equivocada.",
        "review_label": "incorrect",
        "failure_tag": "other",
        "expected_behavior_tag": "regression_only",
        "problem_type": "other_or_not_sure",
        "domain": "test_case_only",
    },
}


def _format_cost(micros: int | None) -> str:
    micros = int(micros or 0)
    return f"US$ {micros / 1_000_000:.4f}"


def _pretty_json(payload: object) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, indent=2, sort_keys=True)


def _domain_label(domain: str | None) -> str:
    return DOMAIN_LABELS.get(str(domain or "").strip(), str(domain or "-").replace("_", " ").strip() or "-")


def _review_label(label: str | None) -> str:
    return {
        "correct": "Correcta",
        "partially_correct": "Parcial",
        "incorrect": "Incorrecta",
        "unsafe": "Riesgosa",
    }.get(str(label or "").strip(), str(label or "-").replace("_", " ").strip() or "-")


def _session_status_label(status: str | None) -> str:
    return {
        "open": "Abierta",
        "closed": "Cerrada",
        "archived": "Archivada",
        "limit_reached": "Límite alcanzado",
    }.get(str(status or "").strip(), str(status or "-").replace("_", " ").strip() or "-")


def _suggestion_status_label(status: str | None) -> str:
    return {
        "draft": "Cambio en preparación",
        "approved": "Lista para activar",
        "rejected": "Rechazada",
        "applied": "Activa",
    }.get(str(status or "").strip(), str(status or "-").replace("_", " ").strip() or "-")


def _mode_profile_label(value: str | None) -> str:
    return {
        "cheap": "Económico",
        "balanced": "Balanceado",
        "rich": "Completo",
    }.get(str(value or "").strip(), str(value or "-").replace("_", " ").strip() or "-")


def _route_source_label(value: str | None) -> str:
    return {
        "deterministic": "Regla fija",
        "model_assisted": "Asistido por modelo",
        "review_handoff": "Derivado para revisión",
    }.get(str(value or "").strip(), str(value or "-").replace("_", " ").strip() or "-")


def _approval_action_label(value: str | None) -> str:
    return {
        "approve": "Aprobó",
        "reject": "Rechazó",
        "apply": "Activó",
    }.get(str(value or "").strip(), str(value or "-").replace("_", " ").strip() or "-")


def _regression_status_label(value: str | None) -> str:
    return {
        "candidate": "Listo para exportar",
        "exported": "Exportado",
    }.get(str(value or "").strip(), str(value or "-").replace("_", " ").strip() or "-")


def _failure_tag_label(tag: str | None) -> str:
    return FAILURE_TAG_CONFIG.get(str(tag or "").strip(), {}).get("label", "-")


def _failure_detail_label(failure_tag: str | None, detail_tag: str | None) -> str:
    tag = str(failure_tag or "").strip()
    detail = str(detail_tag or "").strip()
    for key, label in FAILURE_DETAIL_CONFIG.get(tag, []):
        if key == detail:
            return label
    return "-"


def _normalize_failure_tag(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if value in FAILURE_TAG_CONFIG:
        return value
    return "other"


def _normalize_failure_detail_tag(failure_tag: str | None, value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    choices = {key for key, _ in FAILURE_DETAIL_CONFIG.get(_normalize_failure_tag(failure_tag) or "other", [])}
    if value in choices:
        return value
    return None


def _expected_behavior_label(tag: str | None) -> str:
    return EXPECTED_BEHAVIOR_CONFIG.get(str(tag or "").strip(), {}).get("label", "-")


def _normalize_expected_behavior_tag(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if value in EXPECTED_BEHAVIOR_CONFIG:
        return value
    return None


def _clarification_dimension_label(tag: str | None) -> str:
    return CLARIFICATION_DIMENSION_CONFIG.get(str(tag or "").strip(), "-")


def _normalize_clarification_dimension(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if value in CLARIFICATION_DIMENSION_CONFIG:
        return value
    return "other"


def _failure_tag_choices() -> list[dict]:
    return [{"key": key, "label": config["label"]} for key, config in FAILURE_TAG_CONFIG.items()]


def _failure_detail_choices() -> list[dict]:
    return [
        {
            "failure_tag": tag,
            "options": [{"key": key, "label": label} for key, label in options],
        }
        for tag, options in FAILURE_DETAIL_CONFIG.items()
    ]


def _expected_behavior_choices() -> list[dict]:
    return [
        {
            "key": key,
            "label": config["label"],
            "help": config["help"],
        }
        for key, config in EXPECTED_BEHAVIOR_CONFIG.items()
    ]


def _clarification_dimension_choices() -> list[dict]:
    return [{"key": key, "label": label} for key, label in CLARIFICATION_DIMENSION_CONFIG.items()]


def _normalize_problem_type(value: str | None) -> str:
    value = str(value or "").strip()
    if value in PROBLEM_TYPE_CONFIG:
        return value
    return "other_or_not_sure"


def _guess_problem_type(case: dict | None) -> str:
    case = case or {}
    expected_behavior = _normalize_expected_behavior_tag(case.get("expected_behavior_tag"))
    if expected_behavior:
        mapped = EXPECTED_BEHAVIOR_CONFIG.get(expected_behavior, {}).get("problem_type")
        if mapped:
            return mapped
    failure_tag = _normalize_failure_tag(case.get("failure_tag"))
    if failure_tag:
        mapped = FAILURE_TAG_CONFIG.get(failure_tag, {}).get("problem_type")
        if mapped:
            return mapped
    if str(case.get("review_label") or "") == "unsafe":
        return "answered_too_unsafely"
    if case.get("missing_clarification"):
        return "should_have_asked_clarification"
    if case.get("suggested_family"):
        return "wrong_product_or_family"
    if case.get("suggested_canonical_product"):
        return "did_not_understand_term"
    if "faq" in str(case.get("what_was_wrong") or "").lower():
        return "missed_faq_or_policy"
    return "other_or_not_sure"


def _problem_type_choices() -> list[dict]:
    return [
        {
            "key": key,
            "label": config["label"],
            "help": config["help"],
            "recommended_domain": config["recommended_domain"],
            "recommended_domain_label": _domain_label(config["recommended_domain"]),
            "alternative_labels": [_domain_label(domain) for domain in config.get("alternatives", [])],
        }
        for key, config in PROBLEM_TYPE_CONFIG.items()
    ]


def _recommend_domain(problem_type: str | None) -> str:
    config = PROBLEM_TYPE_CONFIG.get(_normalize_problem_type(problem_type), {})
    return str(config.get("recommended_domain") or "test_case_only")


def _build_problem_type_hint(problem_type: str | None) -> dict:
    config = PROBLEM_TYPE_CONFIG.get(_normalize_problem_type(problem_type), PROBLEM_TYPE_CONFIG["other_or_not_sure"])
    return {
        "label": config["label"],
        "help": config["help"],
        "recommended_domain": config["recommended_domain"],
        "recommended_domain_label": _domain_label(config["recommended_domain"]),
        "alternatives": config.get("alternatives", []),
        "alternative_labels": [_domain_label(domain) for domain in config.get("alternatives", [])],
    }


def _simple_teaching_choices() -> list[dict]:
    return [
        {
            "key": key,
            "label": config["label"],
            "help": config["help"],
        }
        for key, config in SIMPLE_TEACHING_CONFIG.items()
    ]


def _normalize_simple_teaching_choice(value: str | None) -> str:
    value = str(value or "").strip()
    if value in SIMPLE_TEACHING_CONFIG:
        return value
    return "not_sure"


def _simple_choice_from_case(case: dict | None) -> str:
    case = case or {}
    expected_behavior = _normalize_expected_behavior_tag(case.get("expected_behavior_tag"))
    if expected_behavior == "understand_term":
        return "understand_term"
    if expected_behavior == "answer_faq_or_policy":
        return "faq_answer"
    if expected_behavior == "ask_clarification_first":
        return "clarify_first"
    if expected_behavior == "block_until_more_detail":
        return "block_first"
    if expected_behavior == "choose_correct_family":
        return "correct_family"
    if expected_behavior == "regression_only":
        return "not_sure"
    failure_tag = _normalize_failure_tag(case.get("failure_tag"))
    if failure_tag == "did_not_understand_term":
        return "understand_term"
    if failure_tag == "missed_faq_or_policy":
        return "faq_answer"
    if failure_tag == "should_have_asked_clarification":
        return "clarify_first"
    if failure_tag == "answered_too_unsafely":
        return "block_first"
    if failure_tag == "wrong_family":
        return "correct_family"
    return "not_sure"


def _simple_review_defaults(case: dict | None) -> dict:
    case = case or {}
    choice = _simple_choice_from_case(case)
    return {
        "choice": choice,
        "what_was_wrong": str(case.get("what_was_wrong") or "").strip(),
        "first_step": str(case.get("missing_clarification") or "").strip(),
        "expected_answer": str(case.get("expected_answer") or "").strip(),
        "family": str(case.get("suggested_family") or "").strip(),
        "canonical_product": str(case.get("suggested_canonical_product") or "").strip(),
        "future_only": _normalize_expected_behavior_tag(case.get("expected_behavior_tag")) == "regression_only",
    }


def _slugify_text(value: str | None, *, fallback: str = "cambio") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    text = text.strip("-")
    return text or fallback


def _non_empty_unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _keyword_candidates(*values: str | None) -> list[str]:
    tokens: list[str] = []
    for value in values:
        tokens.extend(re.findall(r"[a-záéíóúñ0-9]+", str(value or "").lower()))
    return _non_empty_unique([token for token in tokens if len(token) > 2])[:6]


def _family_rule_for(loader, family: str | None) -> dict:
    family_key = str(family or "").strip()
    families = (loader.get_domain("families") or {}).get("families", {})
    for key, rule in families.items():
        if str(key).strip().lower() == family_key.lower():
            return dict(rule or {})
    return {}


def _clarification_rule_for(loader, family: str | None) -> dict:
    family_key = str(family or "").strip()
    rules = (loader.get_domain("clarifications") or {}).get("rules", {})
    for key, rule in rules.items():
        if str(key).strip().lower() == family_key.lower():
            return dict(rule or {})
    return {}


def _build_simple_review_bundle(form, *, current_case: dict | None = None) -> dict:
    current_case = current_case or {}
    choice = _normalize_simple_teaching_choice(form.get("simple_choice") or _simple_choice_from_case(current_case))
    unsure = form.get("simple_unsure") == "on"
    future_only = form.get("simple_future_only") == "on"
    if unsure:
        choice = "not_sure"
    config = SIMPLE_TEACHING_CONFIG[choice]
    what_was_wrong = str(form.get("simple_what_was_wrong") or current_case.get("what_was_wrong") or "").strip()
    first_step = str(form.get("simple_first_step") or current_case.get("missing_clarification") or "").strip()
    expected_answer = str(form.get("simple_expected_answer") or current_case.get("expected_answer") or "").strip()
    family = str(form.get("simple_family") or current_case.get("suggested_family") or "").strip()
    canonical_product = str(
        form.get("simple_canonical_product") or current_case.get("suggested_canonical_product") or ""
    ).strip()
    operator_notes = []
    existing_notes = str(current_case.get("operator_notes") or "").strip()
    if existing_notes:
        operator_notes.append(existing_notes)
    if future_only:
        operator_notes.append("Guardado solo como ejemplo futuro desde el flujo simple.")
    if unsure:
        operator_notes.append("Marcado como no seguro desde el flujo simple.")
    expected_behavior_tag = "regression_only" if future_only else config["expected_behavior_tag"]
    return {
        "choice": choice,
        "unsure": unsure,
        "future_only": future_only,
        "domain": "test_case_only" if future_only else config["domain"],
        "problem_type": "other_or_not_sure" if future_only else config["problem_type"],
        "review_kwargs": {
            "review_label": config["review_label"],
            "failure_tag": config["failure_tag"],
            "failure_detail_tag": _normalize_failure_detail_tag(config["failure_tag"], current_case.get("failure_detail_tag")),
            "expected_behavior_tag": expected_behavior_tag,
            "clarification_dimension": _normalize_clarification_dimension(current_case.get("clarification_dimension")),
            "expected_answer": expected_answer or first_step,
            "what_was_wrong": what_was_wrong or config["help"],
            "missing_clarification": first_step,
            "suggested_family": family,
            "suggested_canonical_product": canonical_product,
            "operator_notes": "\n".join(operator_notes).strip() or None,
        },
    }


def _build_simple_suggestion_from_case(case: dict | None, bundle: dict, loader) -> dict:
    case = case or {}
    source_message = str(case.get("user_input") or "").strip()
    repeated_term = source_message
    first_step = str(bundle["review_kwargs"].get("missing_clarification") or "").strip()
    expected_answer = str(bundle["review_kwargs"].get("expected_answer") or "").strip() or first_step
    what_was_wrong = str(bundle["review_kwargs"].get("what_was_wrong") or "").strip()
    family = str(bundle["review_kwargs"].get("suggested_family") or "").strip() or source_message
    canonical_product = (
        str(bundle["review_kwargs"].get("suggested_canonical_product") or "").strip() or family or source_message
    )
    clarification_dimension = _normalize_clarification_dimension(case.get("clarification_dimension"))
    domain = str(bundle.get("domain") or "test_case_only").strip()

    if domain == "test_case_only":
        return {
            "domain": domain,
            "summary": "Guardar este ejemplo solo como caso futuro",
            "source_message": source_message,
            "repeated_term": repeated_term,
            "suggested_payload": {
                "user_input": source_message,
                "expected_answer": expected_answer or "Guardar este caso como cobertura futura.",
                "route_source": case.get("route_source"),
            },
        }

    if domain == "synonym":
        aliases = _non_empty_unique([source_message, repeated_term])
        return {
            "domain": domain,
            "summary": f"Enseñar que '{source_message or canonical_product}' se entienda mejor",
            "source_message": source_message,
            "repeated_term": repeated_term,
            "suggested_payload": {
                "canonical": canonical_product,
                "family": family,
                "aliases": aliases or [canonical_product],
                "context_terms": _keyword_candidates(source_message, family),
            },
        }

    if domain == "faq":
        faq_id = f"training_{case.get('id', '')[:8]}_{_slugify_text(source_message, fallback='respuesta')}"
        return {
            "domain": domain,
            "summary": "Agregar una respuesta corta y estable para este caso",
            "source_message": source_message,
            "repeated_term": repeated_term,
            "suggested_payload": {
                "id": faq_id[:64],
                "question": source_message or "Consulta frecuente",
                "answer": expected_answer or first_step or "Completar respuesta esperada antes de aprobar.",
                "keywords": _keyword_candidates(source_message, repeated_term, family) or ["consulta"],
                "active": True,
                "tags": ["entrenamiento"],
            },
        }

    if domain == "clarification_rule":
        existing_rule = _clarification_rule_for(loader, family)
        required_dimensions = existing_rule.get("required_dimensions") or (
            [clarification_dimension] if clarification_dimension else []
        )
        question_order = existing_rule.get("question_order") or required_dimensions
        blocked_if_missing = existing_rule.get("blocked_if_missing") or required_dimensions
        prompt = first_step or expected_answer or _clarification_prompt_for_dimension(clarification_dimension)
        return {
            "domain": domain,
            "summary": f"Pedir una aclaración mejor antes de resolver '{family or source_message}'",
            "source_message": source_message,
            "repeated_term": repeated_term,
            "suggested_payload": {
                "family": family,
                "short_prompt": prompt,
                "prompt": prompt,
                "required_dimensions": required_dimensions,
                "question_order": question_order,
                "blocked_if_missing": blocked_if_missing,
                "examples_by_dimension": (
                    {clarification_dimension: _keyword_candidates(source_message)}
                    if clarification_dimension
                    else {}
                ),
            },
        }

    if domain == "blocked_term":
        redirect_prompt = first_step or _clarification_prompt_for_dimension(clarification_dimension)
        return {
            "domain": domain,
            "summary": f"Frenar '{source_message or family}' hasta tener más detalle",
            "source_message": source_message,
            "repeated_term": repeated_term,
            "suggested_payload": {
                "term": source_message or family,
                "reason": what_was_wrong or "Hace falta más detalle antes de responder con seguridad.",
                "redirect_prompt": redirect_prompt,
                "family_hint": family or None,
            },
        }

    if domain == "family_rule":
        existing_rule = _family_rule_for(loader, family)
        return {
            "domain": domain,
            "summary": f"Corregir cómo se detecta '{family or source_message}'",
            "source_message": source_message,
            "repeated_term": repeated_term,
            "suggested_payload": {
                "family": family,
                "allowed_categories": existing_rule.get("allowed_categories") or ["ferreteria"],
                "match_terms": _non_empty_unique([source_message, family, canonical_product]),
                "required_dimensions": existing_rule.get("required_dimensions")
                or ([clarification_dimension] if clarification_dimension else []),
                "optional_dimensions": existing_rule.get("optional_dimensions") or [],
                "dimension_priority": existing_rule.get("dimension_priority") or [],
                "autopick_min_dimensions": existing_rule.get("autopick_min_dimensions") or [],
                "compatibility_axes": existing_rule.get("compatibility_axes") or [],
                "allowed_substitute_groups": existing_rule.get("allowed_substitute_groups") or [],
                "blocked_substitute_groups": existing_rule.get("blocked_substitute_groups") or [],
                "brand_generic_terms": existing_rule.get("brand_generic_terms") or [],
            },
        }

    return {
        "domain": "test_case_only",
        "summary": "Guardar este ejemplo solo como caso futuro",
        "source_message": source_message,
        "repeated_term": repeated_term,
        "suggested_payload": {
            "user_input": source_message,
            "expected_answer": expected_answer or "Guardar este caso como cobertura futura.",
            "route_source": case.get("route_source"),
        },
    }


def _csv(values: list[str] | None) -> str:
    return ", ".join([str(value).strip() for value in values or [] if str(value).strip()])


def _clarification_prompt_for_dimension(dimension: str | None) -> str:
    dimension = _normalize_clarification_dimension(dimension)
    prompts = {
        "material": "¿Para qué material o superficie la necesitás?",
        "size": "¿Qué medida necesitás?",
        "surface": "¿Para qué uso o superficie la necesitás?",
        "presentation": "¿Qué presentación o formato te sirve?",
        "compatibility": "¿Con qué equipo, modelo o medida tiene que ser compatible?",
        "brand": "¿Tenés alguna marca o línea en mente?",
        "quantity": "¿Qué cantidad o unidad necesitás cotizar?",
        "voltage": "¿Qué voltaje o potencia necesitás?",
        "finish": "¿Qué terminación o color necesitás?",
        "other": "¿Qué detalle te falta para elegirlo bien?",
    }
    return prompts.get(dimension or "", prompts["other"])


def _semantic_review_context(domain: str, payload: dict) -> dict:
    context_map = {
        "synonym": {
            "affected_area": "Comprensión de términos y detección inicial",
            "operator_effect": "La forma en que habla el cliente debería llevar al producto o la familia correctos.",
            "review_focus": "Revisá que el alias sea específico y no agarre términos parecidos por error.",
        },
        "unresolved_term_mapping": {
            "affected_area": "Frases repetidas que el bot todavía no entiende bien",
            "operator_effect": "Una forma frecuente de pedir algo debería dejar de caer en respuestas flojas o genéricas.",
            "review_focus": "Revisá si esto conviene activarlo ya o dejarlo más acotado como caso futuro.",
        },
        "faq": {
            "affected_area": "Respuestas frecuentes y políticas del local",
            "operator_effect": "Estas preguntas deberían tener una respuesta estándar sin pasar por presupuesto.",
            "review_focus": "Revisá que la respuesta sea clara y que las palabras clave alcancen.",
        },
        "clarification_rule": {
            "affected_area": "Primera pregunta de aclaración",
            "operator_effect": "El bot debería hacer antes la pregunta correcta y con más consistencia.",
            "review_focus": "Revisá la primera pregunta, los datos necesarios y el orden seguro para cotizar.",
        },
        "family_rule": {
            "affected_area": "Detección de producto o familia",
            "operator_effect": "El bot debería ubicar mejor el pedido y pedir los datos correctos antes de resolver.",
            "review_focus": "Revisá los términos disparadores, los datos obligatorios y que la familia no quede demasiado amplia.",
        },
        "blocked_term": {
            "affected_area": "Seguridad al responder términos amplios",
            "operator_effect": "Los términos muy generales deberían dejar de resolverse antes de tiempo.",
            "review_focus": "Revisá si de verdad conviene frenarlo y si la pregunta de seguimiento es lo bastante concreta.",
        },
        "complementary_rule": {
            "affected_area": "Sugerencia de complementos",
            "operator_effect": "El bot puede sugerir complementos útiles con más consistencia cuando el producto base ya está claro.",
            "review_focus": "Revisá que los complementos sean razonables y conservadores.",
        },
        "substitute_rule": {
            "affected_area": "Seguridad al ofrecer alternativas",
            "operator_effect": "El bot solo debería ofrecer alternativas cuando la compatibilidad está bien controlada.",
            "review_focus": "Revisá con cuidado los datos que tienen que coincidir y los casos que deben quedar bloqueados.",
        },
        "language_pattern": {
            "affected_area": "Normalización de lenguaje",
            "operator_effect": "Las formas regionales o mal escritas deberían interpretarse mejor.",
            "review_focus": "Revisá que la normalización sea acotada y no demasiado amplia.",
        },
        "test_case_only": {
            "affected_area": "Cobertura futura solamente",
            "operator_effect": "Este caso queda guardado como aprendizaje futuro sin cambiar el comportamiento en vivo.",
            "review_focus": "Revisá que de verdad convenga guardarlo solo como caso futuro.",
        },
    }
    return context_map.get(
        domain,
        {
            "affected_area": "Conocimiento del entrenamiento",
            "operator_effect": "El comportamiento revisado debería quedar más consistente después de revisar y activar el cambio.",
            "review_focus": "Revisá que el cambio sea concreto, seguro y valga la pena activarlo.",
        },
    )


def _authoring_defaults(case: dict | None, problem_type: str | None) -> dict:
    case = case or {}
    repeated_term = str(case.get("repeated_term") or case.get("user_input") or "").strip()
    family = str(case.get("suggested_family") or "").strip()
    canonical = str(case.get("suggested_canonical_product") or "").strip()
    failure_label = _failure_tag_label(case.get("failure_tag"))
    expected_behavior = _normalize_expected_behavior_tag(case.get("expected_behavior_tag"))
    clarification_dimension = _normalize_clarification_dimension(case.get("clarification_dimension"))
    clarification_prompt = case.get("missing_clarification") or _clarification_prompt_for_dimension(clarification_dimension)
    summary_map = {
        "synonym": f"Enseñar al bot a entender '{canonical or repeated_term or 'este término'}'.",
        "unresolved_term_mapping": f"Capturar de forma más segura la frase repetida '{repeated_term or canonical or 'este término'}'.",
        "faq": f"Responder '{case.get('user_input') or 'esta consulta'}' como una respuesta frecuente o de política.",
        "clarification_rule": f"Hacer una mejor primera pregunta para '{family or repeated_term or 'esta familia'}'.",
        "family_rule": f"Ajustar la detección de '{family or repeated_term or 'esta familia'}'.",
        "blocked_term": f"Frenar '{repeated_term or family or 'este término'}' hasta que el cliente dé más detalle.",
        "complementary_rule": f"Mejorar los complementos sugeridos para '{family or repeated_term or 'este origen'}'.",
        "substitute_rule": f"Ajustar la seguridad de las alternativas para '{family or repeated_term or 'este origen'}'.",
        "language_pattern": f"Normalizar mejor '{repeated_term or canonical or 'esta frase'}'.",
        "test_case_only": "Guardar este caso solo como cobertura futura.",
    }
    return {
        "summary_by_domain": summary_map,
        "repeated_term": repeated_term,
        "source_message": str(case.get("user_input") or "").strip(),
        "clarification_prompt": clarification_prompt,
        "clarification_short_prompt": case.get("missing_clarification") or _clarification_prompt_for_dimension(clarification_dimension),
        "clarification_dimension": clarification_dimension or "",
        "clarification_required_dimensions": clarification_dimension or "",
        "blocked_reason": str(case.get("what_was_wrong") or failure_label or "Necesita más detalle antes de resolver.").strip(),
        "expected_behavior_label": _expected_behavior_label(expected_behavior),
        "family": family,
        "canonical": canonical,
        "aliases": repeated_term if repeated_term and repeated_term.lower() != canonical.lower() else "",
        "faq_question": str(case.get("user_input") or "").strip(),
        "faq_answer": str(case.get("expected_answer") or "").strip(),
        "language_key": repeated_term,
        "language_value": canonical or family,
        "match_terms": repeated_term,
        "required_dimensions": clarification_dimension or "",
        "question_order": clarification_dimension or "",
        "blocked_if_missing": clarification_dimension or "",
        "recommended_problem_type": _normalize_problem_type(problem_type),
    }


def _before_after_preview(domain: str, payload: dict, loader) -> dict:
    if loader is None:
        return {
            "before_label": "Antes",
            "before_text": "La foto actual del conocimiento en vivo no está disponible en esta vista.",
            "after_label": "Después",
            "after_text": _human_summary_for_suggestion(domain, payload),
        }

    if domain == "synonym":
        canonical = str(payload.get("canonical") or "").strip()
        aliases = [str(value).strip() for value in payload.get("aliases") or [] if str(value).strip()]
        entries = loader.get_domain("synonyms").get("entries", [])
        existing = next(
            (
                entry
                for entry in entries
                if str(entry.get("canonical") or "").strip().lower() == canonical.lower()
            ),
            None,
        )
        before_text = (
            f"'{canonical}' ya reconoce estos alias: {', '.join(existing.get('aliases') or []) or 'ninguno'}."
            if existing
            else f"'{canonical or 'Este término'}' todavía no tiene un alias para {', '.join(aliases) or 'la frase revisada'}."
        )
        after_text = f"{', '.join(aliases) or 'El término revisado'} pasará a entenderse como '{canonical or '-'}'."
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "clarification_rule":
        family = str(payload.get("family") or "").strip()
        current = loader.get_domain("clarifications").get("rules", {}).get(family)
        before_text = (
            f"'{family}' hoy pregunta: {current.get('short_prompt') or current.get('prompt') or 'una aclaración genérica'}."
            if current
            else f"'{family or 'Esta familia'}' todavía no tiene una primera aclaración específica."
        )
        after_text = f"Primero va a preguntar '{payload.get('short_prompt') or payload.get('prompt') or '-'}'."
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "blocked_term":
        term = str(payload.get("term") or "").strip()
        entries = loader.get_domain("blocked_terms").get("terms", [])
        current = next((entry for entry in entries if str(entry.get("term") or "").strip().lower() == term.lower()), None)
        before_text = (
            f"'{term}' hoy está frenado con '{current.get('redirect_prompt') or current.get('reason') or 'una regla anterior'}'."
            if current
            else f"'{term or 'Este término'}' hoy no está frenado de forma explícita."
        )
        after_text = (
            f"'{term}' va a quedar frenado hasta que el cliente agregue detalle, usando '{payload.get('redirect_prompt') or payload.get('reason') or '-'}'."
        )
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "faq":
        faq_id = str(payload.get("id") or "").strip()
        entries = loader.get_domain("faqs").get("entries", [])
        current = next((entry for entry in entries if str(entry.get("id") or "").strip() == faq_id), None)
        before_text = (
            f"La respuesta frecuente '{faq_id}' hoy dice: {current.get('answer') or 'una versión anterior'}."
            if current
            else f"La respuesta frecuente '{faq_id or payload.get('question') or 'esta consulta'}' todavía no existe."
        )
        after_text = f"Va a responder: {payload.get('answer') or '-'}"
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "family_rule":
        family = str(payload.get("family") or payload.get("family_id") or "").strip()
        current = loader.get_domain("families").get("families", {}).get(family)
        current_required = ", ".join(current.get("required_dimensions") or []) if current else ""
        next_required = ", ".join(payload.get("required_dimensions") or [])
        before_text = (
            f"'{family}' hoy requiere {current_required or 'su regla actual'} antes de resolver con seguridad."
            if current
            else f"'{family or 'Esta familia'}' todavía no tiene una regla específica."
        )
        after_text = f"Va a usar la regla actualizada con estos datos necesarios: {next_required or 'ninguno'}."
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "language_pattern":
        section = str(payload.get("section") or "").strip()
        key = str(payload.get("key") or "").strip()
        current = loader.get_domain("language_patterns").get(section, {}).get(key)
        before_text = (
            f"'{key}' en {section} hoy se normaliza como '{current}'."
            if current is not None
            else f"'{key or 'Esta frase'}' en {section or 'esa sección'} todavía no tiene normalización."
        )
        after_text = f"Se va a normalizar como '{payload.get('value') or '-'}'."
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "substitute_rule":
        group_id = str(payload.get("group_id") or "").strip()
        rules = loader.get_domain("substitute_rules").get("rules", [])
        current = next((entry for entry in rules if str(entry.get("group_id") or "").strip() == group_id), None)
        before_text = (
            f"El grupo de alternativas '{group_id}' ya existe con familias de origen {', '.join(current.get('source_families') or []) or '-'}."
            if current
            else f"El grupo de alternativas '{group_id or 'esta regla'}' todavía no existe."
        )
        after_text = (
            f"Solo va a permitir alternativas desde {', '.join(payload.get('source_families') or []) or '-'} hacia {', '.join(payload.get('allowed_targets') or []) or '-'} bajo las validaciones de esta regla."
        )
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "complementary_rule":
        source = str(payload.get("source") or "").strip()
        current = loader.get_domain("complementary").get("rules", {}).get(source)
        before_text = (
            f"'{source}' hoy sugiere {', '.join(current.get('targets') or []) or 'sus complementos actuales'}."
            if current
            else f"'{source or 'Esta familia de origen'}' todavía no tiene una regla de complementos."
        )
        after_text = f"Va a sugerir {', '.join(payload.get('targets') or []) or '-'} como complementos."
        return {"before_label": "Antes", "before_text": before_text, "after_label": "Después", "after_text": after_text}

    if domain == "unresolved_term_mapping":
        resolution_type = str(payload.get("resolution_type") or "synonym").strip()
        return _before_after_preview("blocked_term" if resolution_type == "blocked_term" else "language_pattern" if resolution_type == "language_pattern" else "synonym", payload, loader)

    if domain == "test_case_only":
        return {
            "before_label": "Antes",
            "before_text": "Este caso todavía no está guardado como cobertura futura.",
            "after_label": "Después",
            "after_text": "La conversación revisada va a quedar disponible como caso futuro sin cambiar el conocimiento activo.",
        }

    return {
        "before_label": "Antes",
        "before_text": "El comportamiento en vivo queda como está hoy.",
        "after_label": "Después",
        "after_text": _human_summary_for_suggestion(domain, payload),
    }


def _decorate_suggestion(suggestion: dict | None, *, loader=None) -> dict | None:
    if not suggestion:
        return suggestion
    item = dict(suggestion)
    payload = item.get("suggested_payload") or {}
    domain = str(item.get("domain") or "").strip()
    status = str(item.get("status") or "").strip()
    item["domain_label"] = _domain_label(domain)
    item["status_label"] = _suggestion_status_label(status)
    item["human_summary"] = _human_summary_for_suggestion(domain, payload)
    item["impact_summary"] = _impact_summary_for_suggestion(domain, payload)
    item["technical_payload_pretty"] = _pretty_json(payload)
    item["before_after_preview"] = _before_after_preview(domain, payload, loader)
    item["semantic_review"] = _semantic_review_context(domain, payload)
    item["case_url"] = f"/ops/ferreteria/training/cases/{item.get('review_id')}" if item.get("review_id") else None
    if item.get("review"):
        item["review"] = _decorate_case(item.get("review"))
    item["approvals"] = [
        {**approval, "action_label": _approval_action_label(approval.get("action"))}
        for approval in (item.get("approvals") or [])
    ]
    if status == "draft":
        item["next_action_label"] = "Revisar y aprobar"
    elif status == "approved":
        item["next_action_label"] = "Activar cambio"
    elif status == "applied":
        item["next_action_label"] = "Verificar en vivo"
    else:
        item["next_action_label"] = "Revisar propuesta"
    return item


def _human_summary_for_suggestion(domain: str, payload: dict) -> str:
    if domain == "synonym":
        aliases = ", ".join(payload.get("aliases") or [])
        return f"Agregar {aliases or '-'} como formas válidas de '{payload.get('canonical') or '-'}' para que el bot lo entienda."
    if domain == "unresolved_term_mapping":
        resolution_type = payload.get("resolution_type") or "synonym"
        if resolution_type == "blocked_term":
            return f"Dejar frenado '{payload.get('term') or payload.get('canonical') or '-'}' hasta que el cliente dé un dato más seguro."
        if resolution_type == "language_pattern":
            return f"Normalizar '{payload.get('key') or '-'}' en {payload.get('section') or '-'} como '{payload.get('value') or '-'}'."
        aliases = ", ".join(payload.get("aliases") or [])
        return f"Enseñar al bot que '{aliases or payload.get('canonical') or '-'}' debe entenderse como '{payload.get('canonical') or '-'}'."
    if domain == "faq":
        return f"Agregar o actualizar la respuesta frecuente '{payload.get('question') or payload.get('id') or '-'}'."
    if domain == "clarification_rule":
        return f"Cambiar la primera pregunta para '{payload.get('family') or '-'}' por '{payload.get('short_prompt') or payload.get('prompt') or '-'}'."
    if domain == "family_rule":
        return f"Ajustar cómo el bot detecta o resuelve la familia '{payload.get('family') or payload.get('family_id') or '-'}'."
    if domain == "blocked_term":
        target = payload.get("term") or "-"
        if payload.get("redirect_prompt"):
            return f"Frenar '{target}' para que no se resuelva solo y redirigir con '{payload.get('redirect_prompt')}'."
        return f"Frenar '{target}' para que no se resuelva solo hasta tener más detalle."
    if domain == "complementary_rule":
        targets = ", ".join(payload.get("targets") or [])
        return f"Sugerir {targets or '-'} como complementos cuando el producto base sea '{payload.get('source') or '-'}'."
    if domain == "substitute_rule":
        sources = ", ".join(payload.get("source_families") or [])
        targets = ", ".join(payload.get("allowed_targets") or [])
        return f"Permitir alternativas más seguras desde {sources or '-'} hacia {targets or '-'} solo bajo las validaciones de esta regla."
    if domain == "language_pattern":
        return f"Normalizar '{payload.get('key') or '-'}' dentro de {payload.get('section') or '-'} como '{payload.get('value') or '-'}'."
    if domain == "test_case_only":
        return "Guardar este caso como cobertura futura sin cambiar el conocimiento activo."
    return "Propuesta de corrección estructurada."


def _impact_summary_for_suggestion(domain: str, payload: dict) -> str:
    if domain == "test_case_only":
        return "No cambia el conocimiento en vivo. Solo guarda el caso como cobertura futura."
    target = {
        "synonym": "Los términos entendidos por el bot",
        "unresolved_term_mapping": "El manejo de frases que hoy quedan sin resolver",
        "faq": "Las respuestas frecuentes activas",
        "clarification_rule": "Las primeras preguntas de aclaración",
        "family_rule": "Las reglas activas para detectar familias",
        "blocked_term": "La seguridad al frenar términos amplios",
        "complementary_rule": "Las sugerencias de complementos activas",
        "substitute_rule": "La seguridad al ofrecer alternativas",
        "language_pattern": "La normalización activa de lenguaje",
    }.get(domain, "El conocimiento activo")
    return f"{target} va a cambiar cuando se active esta corrección."


def _decorate_case(case: dict | None) -> dict | None:
    if not case:
        return case
    item = dict(case)
    suggestion_status = str(item.get("suggestion_status") or "").strip()
    if not suggestion_status and item.get("suggestions"):
        suggestion_status = str((item.get("suggestions") or [{}])[0].get("status") or "").strip()
    if not suggestion_status:
        workflow_key = "needs_suggestion"
        workflow_label = "Necesita una propuesta"
    elif suggestion_status == "draft":
        workflow_key = "draft_suggestion"
        workflow_label = "Propuesta en borrador"
    elif suggestion_status == "approved":
        workflow_key = "approved_waiting_apply"
        workflow_label = "Lista para activar"
    elif suggestion_status == "applied":
        workflow_key = "applied"
        workflow_label = "Cambio ya activo"
    else:
        workflow_key = "other"
        workflow_label = suggestion_status.replace("_", " ").title() or "Otro"
    if int(item.get("regression_candidate_count") or 0) > 0 and workflow_key == "needs_suggestion":
        workflow_label = "Necesita propuesta · ya tiene caso futuro"
    item["workflow_key"] = workflow_key
    item["workflow_label"] = workflow_label
    item["review_label_text"] = _review_label(item.get("review_label"))
    item["suggestion_status_label"] = _suggestion_status_label(item.get("suggestion_status"))
    item["domain_label"] = _domain_label(item.get("suggestion_domain"))
    item["failure_tag_label"] = _failure_tag_label(item.get("failure_tag"))
    item["failure_detail_label"] = _failure_detail_label(item.get("failure_tag"), item.get("failure_detail_tag"))
    item["expected_behavior_label"] = _expected_behavior_label(item.get("expected_behavior_tag"))
    item["clarification_dimension_label"] = _clarification_dimension_label(item.get("clarification_dimension"))
    item["route_source_label"] = _route_source_label(item.get("route_source"))
    candidate_count = int(item.get("regression_candidate_count") or len(item.get("regression_candidates") or []))
    export_count = int(item.get("regression_export_count") or len(item.get("exports") or []))
    item["regression_candidate_count"] = candidate_count
    item["regression_export_count"] = export_count
    item["regression_candidates"] = [
        {**candidate, "status_label": _regression_status_label(candidate.get("status"))}
        for candidate in (item.get("regression_candidates") or [])
    ]
    item["exports"] = [
        {
            **export,
            "export_format_label": "JSON" if str(export.get("export_format") or "").lower() == "json" else str(export.get("export_format") or "-").upper(),
        }
        for export in (item.get("exports") or [])
    ]
    item["source_sandbox_url"] = (
        f"/ops/ferreteria/training/sandbox?session_id={item.get('session_id')}&review_message_id={item.get('bot_message_id')}"
        if item.get("session_id") and item.get("bot_message_id")
        else None
    )
    if export_count > 0:
        item["regression_workflow_key"] = "exported"
        item["regression_workflow_label"] = "Caso futuro ya exportado"
        item["regression_next_action"] = "Solo sumá o terminá una corrección si este caso también debe cambiar el comportamiento en vivo."
    elif candidate_count > 0:
        item["regression_workflow_key"] = "candidate_ready"
        item["regression_workflow_label"] = "Caso futuro listo para exportar"
        item["regression_next_action"] = "Exportalo cuando quieras dejar este caso protegido para más adelante."
    else:
        item["regression_workflow_key"] = "no_regression"
        item["regression_workflow_label"] = "Todavía no tiene caso futuro"
        item["regression_next_action"] = "Creá un caso futuro si querés dejar este ejemplo protegido además del cambio en vivo."
    if workflow_key == "needs_suggestion":
        item["next_action_label"] = "Crear primera propuesta"
    elif workflow_key == "draft_suggestion":
        item["next_action_label"] = "Revisar borrador"
    elif workflow_key == "approved_waiting_apply":
        item["next_action_label"] = "Activar cambio aprobado"
    else:
        item["next_action_label"] = "Revisar caso"
    if export_count > 0 and suggestion_status and suggestion_status != "rejected":
        item["coverage_label"] = "Cubierto con cambio activo y caso futuro"
    elif export_count > 0:
        item["coverage_label"] = "Cubierto solo como caso futuro"
    elif candidate_count > 0 and suggestion_status and suggestion_status != "rejected":
        item["coverage_label"] = "La corrección ya empezó, pero falta exportar el caso futuro"
    elif candidate_count > 0:
        item["coverage_label"] = "Caso futuro pendiente de exportar"
    elif suggestion_status and suggestion_status != "rejected":
        item["coverage_label"] = "Por ahora solo hay corrección en conocimiento"
    else:
        item["coverage_label"] = "Todavía no está cubierto"
    return item


def _decorate_session(session: dict | None) -> dict | None:
    if not session:
        return session
    item = dict(session)
    assistant_turn_count = int(item.get("assistant_turn_count") or 0)
    review_count = int(item.get("review_count") or 0)
    item["assistant_turn_count"] = assistant_turn_count
    item["review_count"] = review_count
    item["needs_review"] = assistant_turn_count > review_count
    item["status_label"] = _session_status_label(item.get("status"))
    item["mode_profile_label"] = _mode_profile_label(item.get("mode_profile"))
    return item


def _workflow_counts(cases: list[dict], suggestions: list[dict], sessions: list[dict] | None = None) -> dict:
    decorated_cases = [_decorate_case(case) for case in cases]
    return {
        "needs_suggestion": sum(1 for case in decorated_cases if case and case.get("workflow_key") == "needs_suggestion"),
        "draft_suggestions": sum(1 for suggestion in suggestions if str(suggestion.get("status") or "") == "draft"),
        "approved_waiting_apply": sum(1 for suggestion in suggestions if str(suggestion.get("status") or "") == "approved"),
        "recently_applied": sum(1 for suggestion in suggestions if str(suggestion.get("status") or "") == "applied"),
        "sessions_needing_review": sum(1 for session in (sessions or []) if session and session.get("needs_review")),
        "open_sessions": sum(1 for session in (sessions or []) if session and session.get("status") == "open"),
        "limit_reached_sessions": sum(1 for session in (sessions or []) if session and session.get("status") == "limit_reached"),
        "regression_candidates": sum(1 for case in decorated_cases if int(case.get("regression_candidate_count") or 0) > 0),
        "regression_attention": sum(
            1
            for case in decorated_cases
            if case and case.get("regression_workflow_key") == "candidate_ready"
        ),
    }


def _workflow_inbox_payload(session_service, review_service, suggestion_service) -> dict:
    sessions = [_decorate_session(item) for item in session_service.list_sessions(limit=100)]
    cases = [_decorate_case(item) for item in review_service.list_cases(limit=200)]
    suggestions = [_decorate_suggestion(item, loader=suggestion_service.loader) for item in suggestion_service.list_suggestions(limit=200)]
    counts = _workflow_counts(cases, suggestions, sessions)
    return {
        "sessions_needing_review": [item for item in sessions if item.get("needs_review")][:6],
        "cases_needing_suggestion": [item for item in cases if item.get("workflow_key") == "needs_suggestion"][:6],
        "draft_suggestions": [item for item in suggestions if item.get("status") == "draft"][:6],
        "approved_waiting_apply": [item for item in suggestions if item.get("status") == "approved"][:6],
        "regression_attention": [
            item for item in cases if item.get("regression_workflow_key") == "candidate_ready"
        ][:6],
        "workflow_counts": counts,
        "next_session_review": next((item for item in sessions if item.get("needs_review")), None),
        "next_case_action": next((item for item in cases if item.get("workflow_key") == "needs_suggestion"), None),
        "next_suggestion_action": next((item for item in suggestions if item.get("status") == "draft"), None),
        "next_apply_action": next((item for item in suggestions if item.get("status") == "approved"), None),
        "next_regression_action": next((item for item in cases if item.get("regression_workflow_key") == "candidate_ready"), None),
    }


def _render_training_sandbox(*, error: str | None = None):
    store, session_service, review_service, suggestion_service = get_training_services()
    try:
        selected_id = request.args.get("session_id")
        selected_review_message_id = request.args.get("review_message_id")
        if request.method == "POST":
            action = request.form.get("action", "").strip()
            operator = request.headers.get("X-Admin-User") or request.form.get("operator") or "operator"
            try:
                if action == "start_session":
                    session = session_service.create_session(
                        operator_id=operator,
                        mode_profile=request.form.get("mode_profile", "cheap"),
                        token_ceiling=int(request.form.get("token_ceiling") or 0) or None,
                    )
                    return redirect(url_for("ferreteria_training_ui.training_home_page", session_id=session["id"]))
                if action == "send_message":
                    selected_id = request.form.get("session_id", "").strip()
                    session_service.send_message(selected_id, request.form.get("message", ""))
                    return redirect(url_for("ferreteria_training_ui.training_home_page", session_id=selected_id))
                if action == "reset_session":
                    selected_id = request.form.get("session_id", "").strip()
                    session = session_service.reset_session(selected_id, operator_id=operator)
                    return redirect(url_for("ferreteria_training_ui.training_home_page", session_id=session["id"]))
                if action == "close_session":
                    selected_id = request.form.get("session_id", "").strip()
                    session_service.close_session(selected_id)
                    return redirect(url_for("ferreteria_training_ui.training_home_page", session_id=selected_id))
                if action == "save_simple_review":
                    selected_id = request.form.get("session_id", "").strip()
                    bot_message_id = request.form.get("bot_message_id", "").strip()
                    current_review = next(
                        (
                            item
                            for item in review_service.list_reviews(session_id=selected_id)
                            if str(item.get("bot_message_id") or "").strip() == bot_message_id
                        ),
                        None,
                    )
                    current_case = review_service.get_case_detail(current_review["id"]) if current_review else None
                    bundle = _build_simple_review_bundle(request.form, current_case=current_case)
                    review = review_service.save_review(
                        session_id=selected_id,
                        bot_message_id=bot_message_id,
                        created_by=operator,
                        **bundle["review_kwargs"],
                    )
                    case = review_service.get_case_detail(review["id"]) or {}
                    existing_draft = next(
                        (
                            item
                            for item in (case.get("suggestions") or [])
                            if str(item.get("status") or "").strip() == "draft"
                        ),
                        None,
                    )
                    suggestion_id = existing_draft["id"] if existing_draft else None
                    if not suggestion_id:
                        inferred = _build_simple_suggestion_from_case(case, bundle, suggestion_service.loader)
                        created = suggestion_service.create_suggestion(
                            review_id=review["id"],
                            domain=inferred["domain"],
                            summary=inferred["summary"],
                            source_message=inferred["source_message"],
                            repeated_term=inferred["repeated_term"],
                            suggested_payload=inferred["suggested_payload"],
                            created_by=operator,
                        )
                        suggestion_id = created["id"]
                    return redirect(
                        url_for(
                            "ferreteria_training_ui.training_home_page",
                            session_id=selected_id,
                            review_message_id=bot_message_id,
                            saved_review_id=review["id"],
                            saved_suggestion_id=suggestion_id,
                        )
                    )
                if action == "save_review":
                    failure_tag = _normalize_failure_tag(request.form.get("failure_tag"))
                    review = review_service.save_review(
                        session_id=request.form.get("session_id", "").strip(),
                        bot_message_id=request.form.get("bot_message_id", "").strip(),
                        review_label=request.form.get("review_label", "").strip(),
                        failure_tag=failure_tag,
                        failure_detail_tag=_normalize_failure_detail_tag(failure_tag, request.form.get("failure_detail_tag")),
                        expected_behavior_tag=_normalize_expected_behavior_tag(request.form.get("expected_behavior_tag")),
                        clarification_dimension=_normalize_clarification_dimension(request.form.get("clarification_dimension")),
                        expected_answer=request.form.get("expected_answer"),
                        what_was_wrong=request.form.get("what_was_wrong"),
                        missing_clarification=request.form.get("missing_clarification"),
                        suggested_family=request.form.get("suggested_family"),
                        suggested_canonical_product=request.form.get("suggested_canonical_product"),
                        operator_notes=request.form.get("operator_notes"),
                        created_by=operator,
                    )
                    return redirect(url_for("ferreteria_training_ui.training_case_detail_page", review_id=review["id"]))
            except (ValueError, KnowledgeValidationError) as exc:
                error = str(exc)

        inbox = _workflow_inbox_payload(session_service, review_service, suggestion_service)
        sessions = [_decorate_session(item) for item in session_service.list_sessions(limit=50)]
        if not selected_id and sessions:
            selected_id = next((item["id"] for item in sessions if item.get("status") == "open"), sessions[0]["id"])
        selected = _decorate_session(session_service.get_session(selected_id)) if selected_id else None
        review_target_message = None
        review_target = None
        assistant_messages = []
        if selected:
            reviews = review_service.list_reviews(session_id=selected["id"])
            review_by_message = {review["bot_message_id"]: review for review in reviews}
            for message in selected.get("messages", []):
                if message.get("role") != "assistant":
                    continue
                message["route_source_label"] = _route_source_label(message.get("route_source"))
                review = review_by_message.get(message["id"])
                message["is_reviewed"] = review is not None
                message["review"] = review
                message["case_id"] = review["id"] if review else None
                message["is_selected_review_target"] = message["id"] == selected_review_message_id
                if review_target_message is None and message["id"] == selected_review_message_id:
                    review_target_message = message
            for message in selected.get("messages", []):
                if message.get("role") != "assistant":
                    continue
                message.setdefault("route_source_label", _route_source_label(message.get("route_source")))
            assistant_messages = [message for message in selected.get("messages", []) if message.get("role") == "assistant"]
            if review_target_message is None and assistant_messages:
                review_target_message = next((msg for msg in assistant_messages if not msg.get("is_reviewed")), assistant_messages[-1])
            if review_target_message:
                review_target = review_by_message.get(review_target_message["id"])
                for message in selected.get("messages", []):
                    if message.get("role") == "assistant":
                        message["is_selected_review_target"] = message["id"] == review_target_message["id"]
        simple_defaults = _simple_review_defaults(review_target)
        workspace_notice = None
        saved_review_id = request.args.get("saved_review_id")
        saved_suggestion_id = request.args.get("saved_suggestion_id")
        if saved_review_id or saved_suggestion_id:
            saved_case = _decorate_case(review_service.get_case_detail(saved_review_id)) if saved_review_id else None
            saved_suggestion = (
                _decorate_suggestion(suggestion_service.get_suggestion(saved_suggestion_id), loader=suggestion_service.loader)
                if saved_suggestion_id
                else None
            )
            workspace_notice = {
                "case": saved_case,
                "suggestion": saved_suggestion,
            }
        return render_template(
            "ferreteria_training/home.html",
            title="Hablar con el bot",
            sessions=sessions,
            session=selected,
            review_target_message=review_target_message,
            review_target=review_target,
            assistant_messages=assistant_messages,
            error=error,
            format_cost=_format_cost,
            simple_teaching_choices=_simple_teaching_choices(),
            simple_defaults=simple_defaults,
            workspace_notice=workspace_notice,
            ready_suggestions=inbox["approved_waiting_apply"][:4],
            draft_suggestions=inbox["draft_suggestions"][:4],
            sessions_needing_review=inbox["sessions_needing_review"][:4],
            workflow_counts=inbox["workflow_counts"],
            next_case_action=inbox["next_case_action"],
            next_regression_action=inbox["next_regression_action"],
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/login", methods=["GET", "POST"])
def training_login():
    next_path = request.args.get("next") or request.form.get("next") or url_for("ferreteria_training_ui.training_home_page")
    if session.get(_TRAINING_SESSION_KEY):
        return redirect(next_path)
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        try:
            expected = _training_password_hash()
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), _TRAINING_SALT, _PBKDF2_ITERATIONS)
            if hmac.compare_digest(candidate, expected):
                session[_TRAINING_SESSION_KEY] = True
                return redirect(next_path)
        except RuntimeError:
            pass
        error = "Contraseña incorrecta."
    return render_template("ferreteria_training/login.html", error=error, next=next_path)


@ferreteria_training_ui.route("/ops/ferreteria/training/logout")
def training_logout():
    session.pop(_TRAINING_SESSION_KEY, None)
    return redirect(url_for("ferreteria_training_ui.training_login"))


@ferreteria_training_ui.route("/ops/ferreteria/training", methods=["GET", "POST"])
@training_login_required
def training_home_page():
    return _render_training_sandbox()


@ferreteria_training_ui.route("/ops/ferreteria/training/help", methods=["GET"])
@training_login_required
def training_help_page():
    return render_template(
        "ferreteria_training/help.html",
        title="Ayuda operativa",
        guide_text=_read_support_doc(
            GUIDE_PATH,
            "La guía operativa no está disponible en este entorno. Revisá docs/guia_operativa_entrenamiento_ferreteria.md.",
        ),
        faq_text=_read_support_doc(
            FAQ_PATH,
            "La FAQ no está disponible en este entorno. Revisá docs/faq_entrenamiento_ferreteria.md.",
        ),
        demo_bootstrap_command=DEMO_BOOTSTRAP_COMMAND,
        demo_open_command=DEMO_OPEN_COMMAND,
        demo_index_hint=DEMO_INDEX_HINT,
    )


@ferreteria_training_ui.route("/ops/ferreteria/training/tools", methods=["GET"])
@training_login_required
def training_more_tools_page():
    store, session_service, review_service, suggestion_service = get_training_services()
    try:
        inbox = _workflow_inbox_payload(session_service, review_service, suggestion_service)
        return render_template(
            "ferreteria_training/more_tools.html",
            title="Más herramientas",
            **inbox,
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/sandbox", methods=["GET", "POST"])
@training_login_required
def training_sandbox_page():
    return _render_training_sandbox()


@ferreteria_training_ui.route("/ops/ferreteria/training/sessions", methods=["GET"])
@training_login_required
def training_session_history_page():
    store, session_service, _, _ = get_training_services()
    try:
        all_sessions = [
            _decorate_session(item)
            for item in session_service.list_sessions(
                status=request.args.get("status"),
                operator_id=request.args.get("operator"),
                mode_profile=request.args.get("mode_profile"),
                model_name=request.args.get("model_name"),
                limit=100,
            )
        ]
        sessions = list(all_sessions)
        queue = request.args.get("queue")
        if queue == "needs_review":
            sessions = [item for item in sessions if item.get("needs_review")]
        elif queue == "open":
            sessions = [item for item in sessions if item.get("status") == "open"]
        elif queue == "limit_reached":
            sessions = [item for item in sessions if item.get("status") == "limit_reached"]
        workflow_counts = _workflow_counts([], [], all_sessions)
        return render_template(
            "ferreteria_training/session_history.html",
            title="Historial de sesiones",
            sessions=sessions,
            workflow_counts=workflow_counts,
            format_cost=_format_cost,
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/cases", methods=["GET"])
@training_login_required
def training_cases_page():
    store, _, review_service, suggestion_service = get_training_services()
    try:
        all_cases = [
            _decorate_case(item)
            for item in review_service.list_cases(
                status=request.args.get("status"),
                review_label=request.args.get("review_label"),
                failure_tag=request.args.get("failure_tag"),
                domain=request.args.get("domain"),
                operator_id=request.args.get("operator"),
                suggested_family=request.args.get("family"),
                repeated_term=request.args.get("repeated_term"),
                limit=200,
            )
        ]
        cases = list(all_cases)
        all_suggestions = suggestion_service.list_suggestions(limit=200)
        queue = request.args.get("queue")
        if queue:
            if queue == "regression_candidates":
                cases = [case for case in cases if case.get("regression_workflow_key") == "candidate_ready"]
            else:
                cases = [case for case in cases if case.get("workflow_key") == queue]
        workflow_counts = _workflow_counts(all_cases, all_suggestions)
        return render_template(
            "ferreteria_training/cases.html",
            title="Casos revisados",
            cases=cases,
            workflow_counts=workflow_counts,
            format_cost=_format_cost,
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/cases/<review_id>", methods=["GET", "POST"])
@training_login_required
def training_case_detail_page(review_id: str):
    store, _, review_service, suggestion_service = get_training_services()
    error = None
    selected_problem_type = _normalize_problem_type(request.args.get("problem_type"))
    try:
        if request.method == "POST":
            operator = request.headers.get("X-Admin-User") or request.form.get("operator") or "operator"
            action = request.form.get("action", "").strip()
            selected_problem_type = _normalize_problem_type(request.form.get("problem_type"))
            try:
                if action == "create_suggestion":
                    domain = request.form.get("domain", "").strip() or _recommend_domain(selected_problem_type)
                    suggestion = suggestion_service.create_suggestion(
                        review_id=review_id,
                        domain=domain,
                        summary=request.form.get("summary"),
                        source_message=request.form.get("source_message"),
                        repeated_term=request.form.get("repeated_term"),
                        suggested_payload=_payload_from_form(domain, request.form),
                        created_by=operator,
                    )
                    return redirect(url_for("ferreteria_training_ui.training_suggestion_detail_page", suggestion_id=suggestion["id"]))
                if action == "create_regression_candidate":
                    suggestion_service.create_regression_candidate(
                        review_id,
                        created_by=operator,
                        payload_override={
                            "user_input": request.form.get("user_input"),
                            "expected_answer": request.form.get("expected_answer"),
                            "route_source": request.form.get("route_source"),
                        },
                    )
                    return redirect(url_for("ferreteria_training_ui.training_case_detail_page", review_id=review_id))
                if action == "export_regression":
                    suggestion_service.export_regression_case(review_id, exported_by=operator)
                    return redirect(url_for("ferreteria_training_ui.training_case_detail_page", review_id=review_id))
            except (ValueError, KnowledgeValidationError) as exc:
                error = str(exc)
        case = review_service.get_case_detail(review_id)
        if case and selected_problem_type == "other_or_not_sure" and not request.values.get("problem_type"):
            selected_problem_type = _guess_problem_type(case)
        if case:
            case = _decorate_case(case)
            case["suggestions"] = [_decorate_suggestion(item, loader=suggestion_service.loader) for item in case.get("suggestions", [])]
        recommended_domain = _recommend_domain(selected_problem_type)
        authoring_defaults = _authoring_defaults(case, selected_problem_type)
        return render_template(
            "ferreteria_training/case_detail.html",
            title="Detalle del caso",
            case=case,
            error=error,
            domains=sorted(ALLOWED_SUGGESTION_DOMAINS),
            domain_help=DOMAIN_HELP,
            domain_labels=DOMAIN_LABELS,
            failure_tag_choices=_failure_tag_choices(),
            format_cost=_format_cost,
            problem_type_choices=_problem_type_choices(),
            selected_problem_type=selected_problem_type,
            problem_type_hint=_build_problem_type_hint(selected_problem_type),
            recommended_domain=recommended_domain,
            authoring_defaults=authoring_defaults,
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/suggestions", methods=["GET", "POST"])
@training_login_required
def training_suggestion_queue_page():
    store, _, review_service, suggestion_service = get_training_services()
    error = None
    try:
        if request.method == "POST":
            operator = request.headers.get("X-Admin-User") or request.form.get("operator") or "operator"
            action = request.form.get("action", "").strip()
            suggestion_id = request.form.get("suggestion_id", "").strip()
            reason = request.form.get("reason")
            try:
                if action == "apply_suggestion" and suggestion_id:
                    suggestion_service.apply(suggestion_id, acted_by=operator, reason=reason)
                    return redirect(url_for("ferreteria_training_ui.training_suggestion_queue_page", queue="approved", applied=suggestion_id))
            except KnowledgeValidationError as exc:
                error = str(exc)

        all_suggestions = [
            _decorate_suggestion(item, loader=suggestion_service.loader)
            for item in suggestion_service.list_suggestions(
                status=request.args.get("status"),
                domain=request.args.get("domain"),
                created_by=request.args.get("operator"),
                repeated_term=request.args.get("repeated_term"),
                limit=200,
            )
        ]
        suggestions = list(all_suggestions)
        queue = request.args.get("queue")
        explicit_filters = any(request.args.get(key) for key in ("status", "domain", "operator", "repeated_term"))
        if not queue and not explicit_filters:
            queue = "approved"
        if queue == "draft":
            suggestions = [item for item in suggestions if item.get("status") == "draft"]
        elif queue == "approved":
            suggestions = [item for item in suggestions if item.get("status") == "approved"]
        elif queue == "applied":
            suggestions = [item for item in suggestions if item.get("status") == "applied"]
        workflow_counts = _workflow_counts(review_service.list_cases(limit=200), all_suggestions)
        return render_template(
            "ferreteria_training/suggestion_queue.html",
            title="Cambios listos" if queue == "approved" else "Historial de cambios",
            suggestions=suggestions,
            workflow_counts=workflow_counts,
            queue=queue,
            error=error,
            applied_suggestion=(
                _decorate_suggestion(suggestion_service.get_suggestion(request.args.get("applied")), loader=suggestion_service.loader)
                if request.args.get("applied")
                else None
            ),
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/suggestions/<suggestion_id>", methods=["GET", "POST"])
@training_login_required
def training_suggestion_detail_page(suggestion_id: str):
    store, _, _, suggestion_service = get_training_services()
    error = None
    try:
        if request.method == "POST":
            operator = request.headers.get("X-Admin-User") or request.form.get("operator") or "operator"
            action = request.form.get("action", "").strip()
            reason = request.form.get("reason")
            try:
                if action == "approve":
                    suggestion_service.approve(suggestion_id, acted_by=operator, reason=reason)
                elif action == "reject":
                    suggestion_service.reject(suggestion_id, acted_by=operator, reason=reason)
                elif action == "apply":
                    suggestion_service.apply(suggestion_id, acted_by=operator, reason=reason)
                return redirect(url_for("ferreteria_training_ui.training_suggestion_detail_page", suggestion_id=suggestion_id))
            except KnowledgeValidationError as exc:
                error = str(exc)
        suggestion = _decorate_suggestion(suggestion_service.get_suggestion(suggestion_id), loader=suggestion_service.loader)
        return render_template("ferreteria_training/suggestion_detail.html", title="Detalle de la corrección", suggestion=suggestion, error=error)
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/usage", methods=["GET"])
@training_login_required
def training_usage_page():
    store = get_training_services()[0]
    try:
        return render_template(
            "ferreteria_training/usage.html",
            title="Uso del entrenamiento",
            session_usage=store.list_usage(metric_scope="session", limit=50),
            daily_usage=store.list_usage(metric_scope="daily", limit=31),
            monthly_usage=store.list_usage(metric_scope="monthly", limit=12),
            model_distribution=store.list_model_usage(limit=20),
            format_cost=_format_cost,
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/unresolved-terms", methods=["GET"])
@training_login_required
def training_unresolved_terms_page():
    import json
    from collections import Counter
    from pathlib import Path
    from bot_sales.core.tenancy import tenant_manager

    tenant = tenant_manager.get_tenant_by_slug("ferreteria") or tenant_manager.get_tenant("ferreteria")
    profile_paths = (getattr(tenant, "profile", {}) or {}).get("paths", {})
    base_dir = Path(getattr(tenant, "profile_path", "")).parent if getattr(tenant, "profile_path", "") else Path("data/tenants/ferreteria")
    if not base_dir.is_absolute():
        base_dir = Path(__file__).resolve().parents[2] / base_dir

    jsonl_path = base_dir / "unresolved_terms.jsonl"
    all_entries: list[dict] = []
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    all_entries.append(json.loads(line))
                except Exception:
                    pass

    freq: Counter = Counter(e.get("normalized", e.get("raw", "")) for e in all_entries)
    latest: dict[str, dict] = {}
    for entry in all_entries:
        key = entry.get("normalized", entry.get("raw", ""))
        latest[key] = entry

    terms = [
        {**latest[term], "count": count}
        for term, count in freq.most_common(300)
        if term
    ]

    return render_template(
        "ferreteria_training/unresolved_terms.html",
        title="Términos sin resolver",
        terms=terms,
        total=len(all_entries),
    )


@ferreteria_training_ui.route("/ops/ferreteria/training/impact", methods=["GET"])
@training_login_required
def training_impact_page():
    store = get_training_services()[0]
    try:
        impact_rows = store.get_impact_rows()
        return render_template(
            "ferreteria_training/impact.html",
            title="Impacto de correcciones",
            impact_rows=impact_rows,
        )
    finally:
        store.close()


@ferreteria_training_ui.route("/ops/ferreteria/training/bot-config", methods=["GET", "POST"])
@training_login_required
def bot_config_page():
    """Edit bot manual (structured instruction fields) + personality."""
    import yaml as _yaml
    import json as _json
    from pathlib import Path as _Path

    PROFILE_PATH = _Path(__file__).resolve().parents[2] / "data" / "tenants" / "ferreteria" / "profile.yaml"

    def _load_profile():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return _yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _save_profile(profile: dict):
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            _yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        try:
            from bot_sales.core.tenant_config import _config_cache
            _config_cache.clear()
        except Exception:
            pass

    def _fields_to_objective(fields: list) -> str:
        """Combine list of {title, content} into a single instruction text."""
        parts = []
        for field in fields:
            title = str(field.get("title") or "").strip()
            content = str(field.get("content") or "").strip()
            if content:
                if title:
                    parts.append(f"## {title}\n{content}")
                else:
                    parts.append(content)
        return "\n\n".join(parts)

    profile = _load_profile()
    training = profile.get("training") or {}

    if request.method == "POST":
        # AJAX JSON save
        if request.is_json:
            data = request.get_json() or {}
            personality = str(data.get("personality") or "").strip()
            manual_fields = data.get("manual_fields") or []
            # Validate fields is a list of dicts
            if not isinstance(manual_fields, list):
                return jsonify({"error": "invalid fields"}), 400
            objective = _fields_to_objective(manual_fields)
            try:
                if not isinstance(profile.get("training"), dict):
                    profile["training"] = {}
                profile["training"]["personality"] = personality
                profile["training"]["objective"] = objective
                profile["training"]["manual_fields"] = manual_fields
                _save_profile(profile)
                return jsonify({"ok": True})
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500
        else:
            # Legacy form POST (fallback)
            personality = request.form.get("personality", "").strip()
            objective   = request.form.get("objective", "").strip()
            try:
                if not isinstance(profile.get("training"), dict):
                    profile["training"] = {}
                profile["training"]["personality"] = personality
                profile["training"]["objective"]   = objective
                _save_profile(profile)
                training = profile["training"]
            except Exception:
                pass
            return redirect(request.url)

    manual_fields = training.get("manual_fields") or []
    return render_template(
        "ferreteria_training/bot_config.html",
        personality=training.get("personality") or "",
        manual_fields=manual_fields,
    )


@ferreteria_training_ui.route("/ops/ferreteria/training/api/chat-test", methods=["POST"])
@training_login_required
def training_chat_test():
    """Process a test message through the live ferreteria bot."""
    data = request.get_json() or {}
    message = str(data.get("message") or "").strip()
    session_id = str(data.get("session_id") or "training_test_ferreteria")
    channel = str(data.get("channel") or "cli").strip()
    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400
    try:
        from bot_sales.core.tenancy import tenant_manager
        bot = tenant_manager.get_bot("ferreteria")
        reply = bot.process_message(
            session_id,
            message,
            channel=channel,
            customer_ref=session_id,
        )
        return jsonify({"reply": reply or "(sin respuesta)"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@ferreteria_training_ui.route("/ops/ferreteria/training/api/chat-reset", methods=["POST"])
@training_login_required
def training_chat_reset():
    """Clear a test chat session."""
    data = request.get_json() or {}
    session_id = str(data.get("session_id") or "training_test_ferreteria")
    try:
        from bot_sales.core.tenancy import tenant_manager
        bot = tenant_manager.get_bot("ferreteria")
        if hasattr(bot, "reset_session"):
            bot.reset_session(session_id)
        else:
            if hasattr(bot, "contexts"):
                bot.contexts.pop(session_id, None)
            if hasattr(bot, "sessions"):
                bot.sessions.pop(session_id, None)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _payload_from_form(domain: str, form) -> dict:
    if domain in {"synonym", "unresolved_term_mapping"}:
        aliases = [value.strip() for value in (form.get("aliases") or "").split(",") if value.strip()]
        payload = {
            "canonical": form.get("canonical"),
            "family": form.get("family"),
            "aliases": aliases,
            "misspellings": [value.strip() for value in (form.get("misspellings") or "").split(",") if value.strip()],
            "brand_generic": form.get("brand_generic") == "on",
        }
        resolution_type = form.get("resolution_type", "").strip()
        if resolution_type:
            payload["resolution_type"] = resolution_type
        return payload
    if domain == "faq":
        return {
            "id": form.get("faq_id"),
            "question": form.get("faq_question"),
            "answer": form.get("faq_answer"),
            "keywords": [value.strip() for value in (form.get("faq_keywords") or "").split(",") if value.strip()],
            "active": True,
            "tags": [value.strip() for value in (form.get("faq_tags") or "").split(",") if value.strip()],
        }
    if domain == "clarification_rule":
        return {
            "family": form.get("family"),
            "prompt": form.get("clarification_prompt"),
            "short_prompt": form.get("clarification_short_prompt"),
            "examples": [value.strip() for value in (form.get("clarification_examples") or "").split("\n") if value.strip()],
            "required_dimensions": [value.strip() for value in (form.get("required_dimensions") or "").split(",") if value.strip()],
            "question_order": [value.strip() for value in (form.get("question_order") or "").split(",") if value.strip()],
            "blocked_if_missing": [value.strip() for value in (form.get("blocked_if_missing") or "").split(",") if value.strip()],
        }
    if domain == "family_rule":
        return {
            "family": form.get("family"),
            "allowed_categories": [value.strip() for value in (form.get("allowed_categories") or "").split(",") if value.strip()],
            "match_terms": [value.strip() for value in (form.get("match_terms") or "").split(",") if value.strip()],
            "required_dimensions": [value.strip() for value in (form.get("required_dimensions") or "").split(",") if value.strip()],
            "optional_dimensions": [value.strip() for value in (form.get("optional_dimensions") or "").split(",") if value.strip()],
            "dimension_priority": [value.strip() for value in (form.get("dimension_priority") or "").split(",") if value.strip()],
            "autopick_min_dimensions": [value.strip() for value in (form.get("autopick_min_dimensions") or "").split(",") if value.strip()],
            "compatibility_axes": [value.strip() for value in (form.get("compatibility_axes") or "").split(",") if value.strip()],
            "allowed_substitute_groups": [value.strip() for value in (form.get("allowed_substitute_groups") or "").split(",") if value.strip()],
            "blocked_substitute_groups": [value.strip() for value in (form.get("blocked_substitute_groups") or "").split(",") if value.strip()],
            "brand_generic_terms": [value.strip() for value in (form.get("brand_generic_terms") or "").split(",") if value.strip()],
        }
    if domain == "blocked_term":
        return {
            "term": form.get("blocked_term"),
            "reason": form.get("blocked_reason"),
            "redirect_prompt": form.get("blocked_redirect_prompt"),
            "family_hint": form.get("family"),
        }
    if domain == "complementary_rule":
        return {
            "source": form.get("source"),
            "targets": [value.strip() for value in (form.get("targets") or "").split(",") if value.strip()],
            "max_suggestions": int(form.get("max_suggestions") or 1),
        }
    if domain == "substitute_rule":
        return {
            "group_id": form.get("group_id"),
            "source_families": [value.strip() for value in (form.get("source_families") or "").split(",") if value.strip()],
            "allowed_targets": [value.strip() for value in (form.get("allowed_targets") or "").split(",") if value.strip()],
            "required_matching_dimensions": [value.strip() for value in (form.get("required_matching_dimensions") or "").split(",") if value.strip()],
            "allowed_dimension_drift": [value.strip() for value in (form.get("allowed_dimension_drift") or "").split(",") if value.strip()],
            "blocked_dimension_mismatches": [value.strip() for value in (form.get("blocked_dimension_mismatches") or "").split(",") if value.strip()],
            "blocked_terms": [value.strip() for value in (form.get("substitute_blocked_terms") or "").split(",") if value.strip()],
            "reason_template": form.get("reason_template"),
        }
    if domain == "language_pattern":
        return {
            "section": form.get("language_section"),
            "key": form.get("language_key"),
            "value": form.get("language_value"),
        }
    return {
        "user_input": form.get("user_input"),
        "expected_answer": form.get("expected_answer"),
        "route_source": form.get("route_source"),
    }
