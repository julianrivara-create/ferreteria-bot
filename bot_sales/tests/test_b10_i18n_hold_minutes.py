"""
B.10: i18n strings for create_reservation must accept the hold duration
as a placeholder so the bot never promises "30 minutes" while the
configured HOLD_MINUTES is something else.

Before: the locale strings hardcoded "30 minutos" / "30 minutes" while
HOLD_MINUTES in config defaults to 1440 (24h) and the actual hold uses
that value, producing a silent UX/communication mismatch when the
Translator gets wired in.
"""
from __future__ import annotations

from bot_sales.i18n.translator import Translator


def test_create_reservation_es_includes_placeholder():
    t = Translator(default_locale="es")
    rendered = t.get("create_reservation", minutes=1440)
    assert "{minutes}" not in rendered
    assert "1440 minutos" in rendered


def test_create_reservation_en_includes_placeholder():
    t = Translator(default_locale="en")
    t.set_locale("en")
    rendered = t.get("create_reservation", locale="en", minutes=45)
    assert "{minutes}" not in rendered
    assert "45 minutes" in rendered


def test_create_reservation_unformatted_keeps_placeholder():
    """Without kwargs we get the raw template — guards against accidental
    consumers that forget to pass the minutes value."""
    t = Translator(default_locale="es")
    rendered = t.get("create_reservation")
    assert "{minutes}" in rendered
