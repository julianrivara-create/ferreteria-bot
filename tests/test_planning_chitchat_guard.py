"""Tests for compute_missing_fields chit-chat intent guard."""
from __future__ import annotations

import pytest
from bot_sales.planning.pipeline import compute_missing_fields


@pytest.mark.parametrize("intent", [
    "CHIT_CHAT",
    "chit_chat",
    "GREETING_CHAT",
    "GREETING",
    "UNKNOWN",
])
def test_compute_missing_fields_returns_empty_for_conversational_intents(intent):
    """Conversational/greeting intents must not trigger missing-fields questions."""
    context: dict = {}  # no product_family, urgency, or payment_preference
    result = compute_missing_fields(context, intent_name=intent)
    assert result == [], f"Expected [] for intent={intent!r}, got {result}"


def test_compute_missing_fields_returns_fields_for_quotation_intent():
    """Non-conversational intents still require product and closing fields."""
    context: dict = {}
    result = compute_missing_fields(context, intent_name="EXACT_PRICE_REQUEST")
    assert "product_family" in result
    assert "urgency" in result


def test_compute_missing_fields_no_intent_still_works():
    """Calling without intent_name behaves as before."""
    context: dict = {}
    result = compute_missing_fields(context)
    assert "product_family" in result
    assert "urgency" in result


def test_compute_missing_fields_context_satisfied_returns_empty():
    """When context has all fields, no missing fields regardless of intent."""
    context = {
        "product_family": "Mechas",
        "model": "Mecha 8mm",
        "urgency": "hoy",
        "payment_preference": "efectivo",
    }
    result = compute_missing_fields(context, intent_name="EXACT_PRICE_REQUEST")
    assert result == []
