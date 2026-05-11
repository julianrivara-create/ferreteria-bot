"""
B.6: consolidate reset detection.

Two paths used to coexist with no coordination: the TurnInterpreter
classified the turn as reset_signal=true while bot.py also called
fq.looks_like_reset() from five different places. Behaviour depended
on whichever path fired first.

After the fix, _reset_signaled is a single entry point for the
deterministic routes that have a cached TurnInterpretation. It
prefers TurnInterpreter.reset_signal when confidence is reliable
(>= _TI_CONFIDENCE_FLOOR) and always also consults fq.looks_like_reset
as a safety net so explicit canonical phrases ("nuevo presupuesto",
"empecemos de nuevo", etc.) still trigger reset when the LLM is
unavailable or has low confidence.
"""
from __future__ import annotations

from bot_sales.bot import _reset_signaled, _TI_CONFIDENCE_FLOOR


def test_ti_high_confidence_reset_wins():
    interp = {"reset_signal": True, "confidence": 0.92}
    # Even with text that the regex would NOT match, the TI signal wins.
    assert _reset_signaled("hagamos otra cosa", None, interp) is True


def test_ti_low_confidence_falls_back_to_regex_match():
    interp = {"reset_signal": True, "confidence": 0.20}
    # Reset_signal is unreliable below the floor; the regex picks up the
    # canonical phrase regardless.
    assert _reset_signaled("empecemos de nuevo", None, interp) is True


def test_ti_low_confidence_no_reset_phrase_returns_false():
    interp = {"reset_signal": True, "confidence": 0.20}
    # Reset_signal unreliable AND text is not a canonical reset phrase.
    assert _reset_signaled("hola buen dia", None, interp) is False


def test_ti_high_confidence_no_reset_canonical_phrase_still_triggers():
    interp = {"reset_signal": False, "confidence": 0.90}
    # The regex is conservative — it only matches a curated phrase set.
    # When the user types one of those canonical phrases we honour reset
    # even if the LLM classified the turn as something else.
    assert _reset_signaled("nuevo presupuesto", None, interp) is True


def test_ti_high_confidence_no_reset_normal_text_does_not_trigger():
    interp = {"reset_signal": False, "confidence": 0.90}
    # Without a canonical phrase the LLM verdict stands.
    assert _reset_signaled("quiero un taladro", None, interp) is False


def test_no_interpretation_falls_back_to_regex():
    assert _reset_signaled("empecemos de nuevo", None, None) is True
    assert _reset_signaled("hola", None, {}) is False


def test_confidence_floor_constant_is_055():
    assert _TI_CONFIDENCE_FLOOR == 0.55
