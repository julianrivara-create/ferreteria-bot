from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class SalesIntent(str, Enum):
    GENERIC_INFO = "GENERIC_INFO"
    AVAILABILITY = "AVAILABILITY"
    COMPARISON = "COMPARISON"
    OBJECTION_PRICE = "OBJECTION_PRICE"
    OBJECTION_TRUST = "OBJECTION_TRUST"
    OBJECTION_DEPOSIT = "OBJECTION_DEPOSIT"
    OBJECTION_PAYMENT_INSTALLMENTS = "OBJECTION_PAYMENT_INSTALLMENTS"
    OBJECTION_DELIVERY = "OBJECTION_DELIVERY"
    OBJECTION_CURRENCY = "OBJECTION_CURRENCY"
    PAYMENT_METHODS = "PAYMENT_METHODS"
    EXACT_PRICE_REQUEST = "EXACT_PRICE_REQUEST"
    HIGH_INTENT_SIGNAL = "HIGH_INTENT_SIGNAL"
    BUYING_SIGNAL = "BUYING_SIGNAL"
    SUPPORT = "SUPPORT"
    CHIT_CHAT = "CHIT_CHAT"
    LOST_SIGNAL = "LOST_SIGNAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntentResult:
    intent: SalesIntent
    confidence: float
    source: str


class IntentClassifier:
    """
    Hybrid intent classifier:
    1) fast keyword path
    2) low-temperature LLM fallback returning only enum
    """

    def classify(
        self,
        user_message: str,
        history: list[dict] | None = None,
        *,
        llm_classifier: Callable[[str, list[dict]], str] | None = None,
    ) -> IntentResult:
        history = history or []
        msg = _normalize(user_message)

        keyword_result = self._keyword_classify(msg)
        if keyword_result.confidence >= 0.72:
            return keyword_result

        if llm_classifier is not None:
            llm_value = str(llm_classifier(user_message, history)).strip().upper()
            if llm_value in SalesIntent.__members__:
                return IntentResult(intent=SalesIntent[llm_value], confidence=0.62, source="llm_fallback")

        if keyword_result.intent != SalesIntent.UNKNOWN:
            return keyword_result

        return IntentResult(intent=SalesIntent.GENERIC_INFO, confidence=0.40, source="fallback")

    def extract_entities(self, user_message: str) -> dict[str, str | bool | None]:
        msg = _normalize(user_message)

        product_family = _first_match(
            msg,
            {
                "celular": "Smartphones",
                "telefono": "Smartphones",
                "smartphone": "Smartphones",
                "laptop": "Laptops",
                "notebook": "Laptops",
                "tablet": "Tablets",
                "auricular": "Audio",
                "audio": "Audio",
                "ropa": "Indumentaria",
                "remera": "Indumentaria",
                "pantalon": "Indumentaria",
                "zapatilla": "Calzado",
                "calzado": "Calzado",
                "farmacia": "Farmacia",
                "medicamento": "Farmacia",
                "analgesico": "Farmacia",
            },
        )

        model = None
        model_match = re.search(r"\b(modelo|producto|marca)\s*[:\-]?\s*([a-z0-9+\- ]{2,40})", msg, re.IGNORECASE)
        if model_match:
            model = " ".join(model_match.group(2).split())
            model = re.sub(r"\s+", " ", model)

        storage = None
        storage_match = re.search(r"\b(16|32|64|128|256|512|1024|1)\s?(gb|tb|ml|mg|gr|g|kg|l)\b", msg, re.IGNORECASE)
        if storage_match:
            qty = storage_match.group(1)
            unit = storage_match.group(2).upper()
            if qty == "1" and unit == "TB":
                storage = "1TB"
            elif qty == "1024" and unit == "GB":
                storage = "1TB"
            else:
                storage = f"{qty}{unit}"

        condition = _first_match(
            msg,
            {
                "sellado": "new_sealed",
                "nuevo": "new_sealed",
                "new": "new_sealed",
                "open box": "open_box",
                "caja abierta": "open_box",
                "usado": "used",
                "semi nuevo": "used",
            },
        )

        payment_preference = _first_match(
            msg,
            {
                "efectivo": "cash",
                "cash": "cash",
                "transferencia": "transfer",
                "transfer": "transfer",
                "usdt": "usdt",
                "crypto": "usdt",
                "tarjeta": "card",
                "credito": "card",
                "débito": "card",
                "debito": "card",
                "mercadopago": "gateway",
            },
        )

        urgency = _first_match(
            msg,
            {
                "hoy": "today",
                "ahora": "today",
                "esta semana": "this_week",
                "este semana": "this_week",
                "este mes": "this_month",
                "cuando cobro": "this_month",
                "sin apuro": "this_month",
            },
        )

        color_preference = _first_match(
            msg,
            {
                "negro": "black",
                "blanco": "white",
                "azul": "blue",
                "natural": "natural",
                "plateado": "silver",
                "rosa": "pink",
                "verde": "green",
                "violeta": "purple",
                "rojo": "red",
            },
        )

        delivery_method = _first_match(
            msg,
            {
                "envio": "delivery",
                "moto": "delivery",
                "correo": "shipping",
                "andreani": "shipping",
                "entrega": "delivery",
                "retiro": "pickup",
            },
        )

        needs_installments: bool | None = None
        if any(token in msg for token in ("cuotas", "cuota", "sin interes", "con interes", "financiado")):
            needs_installments = True
        elif any(token in msg for token in ("contado", "una sola", "pago completo")):
            needs_installments = False

        budget = None
        budget_match = re.search(r"(?:usd|usdt|ars|\$)\s*([0-9][0-9\.\,]{2,})", msg, re.IGNORECASE)
        if budget_match:
            budget = budget_match.group(0).replace("  ", " ").strip()

        # Fallback: if we still don't have model but user mentions a likely product noun phrase.
        if not model:
            generic_model = re.search(
                r"\b(busco|quiero|necesito|precio de|stock de)\s+([a-z0-9+\- ]{3,40})",
                msg,
                re.IGNORECASE,
            )
            if generic_model:
                model = " ".join(generic_model.group(2).split())

        return {
            "product_family": product_family,
            "model": model,
            "storage": storage,
            "condition": condition,
            "payment_preference": payment_preference,
            "needs_installments": needs_installments,
            "urgency": urgency,
            "color_preference": color_preference,
            "delivery_method": delivery_method,
            "budget": budget,
        }

    def detect_objection_type(self, intent: SalesIntent) -> str | None:
        mapping = {
            SalesIntent.OBJECTION_PRICE: "PRICE_OBJECTION",
            SalesIntent.OBJECTION_TRUST: "TRUST_OBJECTION",
            SalesIntent.OBJECTION_DEPOSIT: "DEPOSIT_OBJECTION",
            SalesIntent.OBJECTION_PAYMENT_INSTALLMENTS: "PAYMENT_METHODS",
            SalesIntent.OBJECTION_DELIVERY: "DELIVERY_OBJECTION",
            SalesIntent.OBJECTION_CURRENCY: "DOLLAR_DOWN_OBJECTION",
        }
        return mapping.get(intent)

    def _keyword_classify(self, msg: str) -> IntentResult:
        score: dict[SalesIntent, float] = {intent: 0.0 for intent in SalesIntent}

        rules: list[tuple[SalesIntent, tuple[str, ...], float]] = [
            (SalesIntent.HIGH_INTENT_SIGNAL, ("pago ahora", "pagar ahora", "te pago", "pasame link", "donde pago"), 1.0),
            (SalesIntent.BUYING_SIGNAL, ("lo quiero", "reservame", "reserva", "me lo llevo", "confirmo"), 0.95),
            (SalesIntent.EXACT_PRICE_REQUEST, ("precio final", "precio exacto", "cuanto queda", "cuanto seria"), 0.90),
            (SalesIntent.OBJECTION_PRICE, ("caro", "mas barato", "descuento", "mejor precio", "bajalo"), 0.90),
            (SalesIntent.OBJECTION_TRUST, ("original", "garantia", "confiable", "seguro", "estafa"), 0.90),
            (SalesIntent.OBJECTION_DEPOSIT, ("seña", "reserva con", "adelanto"), 0.90),
            (SalesIntent.OBJECTION_PAYMENT_INSTALLMENTS, ("cuotas", "sin interes", "financiacion"), 0.90),
            (SalesIntent.OBJECTION_DELIVERY, ("envio", "cuando llega", "entrega", "demora"), 0.85),
            (SalesIntent.OBJECTION_CURRENCY, ("dolar bajo", "bajo el dolar", "tipo de cambio"), 0.90),
            (SalesIntent.PAYMENT_METHODS, ("usdt", "transferencia", "efectivo", "tarjeta"), 0.82),
            (SalesIntent.COMPARISON, ("vs", "comparar", "me conviene", "diferencia"), 0.80),
            (SalesIntent.AVAILABILITY, ("stock", "tenes", "disponible", "queda"), 0.78),
            (SalesIntent.SUPPORT, ("no funciona", "reclamo", "devolucion", "garantia post venta"), 0.92),
            (SalesIntent.LOST_SIGNAL, ("no gracias", "no me interesa", "despues veo", "dejo pasar"), 0.95),
            (SalesIntent.CHIT_CHAT, ("hola", "buenas", "jaja", "gracias"), 0.72),
        ]

        for intent, keywords, weight in rules:
            for keyword in keywords:
                if keyword in msg:
                    score[intent] += weight

        best_intent = max(score, key=score.get)
        best_score = score[best_intent]
        if best_score <= 0:
            return IntentResult(intent=SalesIntent.UNKNOWN, confidence=0.0, source="keyword")

        confidence = min(1.0, 0.5 + (best_score / 2.0))
        return IntentResult(intent=best_intent, confidence=round(confidence, 2), source="keyword")


def _normalize(value: str) -> str:
    clean = (value or "").lower().strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _first_match(msg: str, options: dict[str, str]) -> str | None:
    for token, canonical in options.items():
        if token in msg:
            return canonical
    return None
