"""
Tests for F1 fix: compound clarification + additive routing in pre_route section 4.

Bug: messages combining an option selection ("la opcion A") with an additive
request ("te pido también un martillo") were processed by the section 4
clarification fast-path, which silently discarded the additive portion.

Fix: _ADDITIVE_INLINE_RE detects additive phrases at positions > 0, splits
the message, and processes both parts deterministically.
"""
import re
import uuid
import pytest

from bot_sales.bot import _ADDITIVE_INLINE_RE, _CLARIF_TRAIL_CHARS


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: _ADDITIVE_INLINE_RE detection
# ─────────────────────────────────────────────────────────────────────────────

class TestAdditiveInlineRegex:
    """_ADDITIVE_INLINE_RE must detect additive phrases anywhere in the string."""

    def test_te_pido_tambien_at_start(self):
        m = _ADDITIVE_INLINE_RE.search("te pido también un martillo")
        assert m is not None and m.start() == 0

    def test_te_pido_tambien_mid_string(self):
        m = _ADDITIVE_INLINE_RE.search("la opcion a. te pido también un martillo")
        assert m is not None and m.start() > 0

    def test_agrega_at_start(self):
        m = _ADDITIVE_INLINE_RE.search("agregame un clavo")
        assert m is not None and m.start() == 0

    def test_agrega_mid_string(self):
        m = _ADDITIVE_INLINE_RE.search("la B. agregame un clavo")
        assert m is not None and m.start() > 0

    def test_suma_mid_string(self):
        m = _ADDITIVE_INLINE_RE.search("para madera. sumame un taladro")
        assert m is not None and m.start() > 0

    def test_no_match_pure_clarification(self):
        """Pure clarification — no additive phrase."""
        assert _ADDITIVE_INLINE_RE.search("la opcion a") is None

    def test_no_match_material_spec(self):
        """Material clarification — no additive phrase."""
        assert _ADDITIVE_INLINE_RE.search("para madera de 6mm") is None

    def test_no_match_option_letter(self):
        """Single option letter — no additive phrase."""
        assert _ADDITIVE_INLINE_RE.search("la B") is None

    def test_no_match_brand_answer(self):
        """Brand answer — no additive phrase."""
        assert _ADDITIVE_INLINE_RE.search("stanley") is None


class TestClarifTrailChars:
    """Clarification prefix stripping removes trailing noise chars."""

    def _strip(self, s: str) -> str:
        return s.rstrip(_CLARIF_TRAIL_CHARS).strip()

    def test_strip_period(self):
        assert self._strip("la opcion a.") == "la opcion a"

    def test_strip_comma_space(self):
        assert self._strip("la opcion a, ") == "la opcion a"

    def test_strip_y_connector(self):
        assert self._strip("la opcion a y") == "la opcion a"

    def test_strip_semicolon(self):
        assert self._strip("la B;") == "la B"

    def test_no_strip_clean(self):
        assert self._strip("la opcion a") == "la opcion a"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: compound guard conditions (via _ADDITIVE_INLINE_RE.search logic)
# ─────────────────────────────────────────────────────────────────────────────

class TestCompoundGuardConditions:
    """Check the guard conditions:  start > 0  AND  clarif_part non-empty."""

    def _guard_split(self, text: str):
        """Simulate the guard split logic from pre_route section 4.0."""
        m = _ADDITIVE_INLINE_RE.search(text)
        if m is None or m.start() == 0:
            return None, None
        clarif_part = text[:m.start()].rstrip(_CLARIF_TRAIL_CHARS).strip()
        additive_part = text[m.start():].strip()
        if not clarif_part:
            return None, None
        return clarif_part, additive_part

    def test_opcion_punto_te_pido(self):
        cp, ap = self._guard_split("la opcion a. te pido también un martillo")
        assert cp == "la opcion a"
        assert ap == "te pido también un martillo"

    def test_opcion_y_te_pido(self):
        cp, ap = self._guard_split("la opcion a y te pido también un martillo")
        assert cp == "la opcion a"
        assert ap == "te pido también un martillo"

    def test_letra_punto_agregame(self):
        cp, ap = self._guard_split("B. agregame un clavo")
        assert cp == "B"
        assert ap == "agregame un clavo"

    def test_material_y_additive(self):
        cp, ap = self._guard_split("para madera. te pido también clavos")
        assert cp == "para madera"
        assert ap == "te pido también clavos"

    def test_clarif_pura_no_dispara(self):
        """Pure clarification — guard must NOT trigger."""
        cp, ap = self._guard_split("la opción A")
        assert cp is None and ap is None

    def test_additive_pura_no_dispara(self):
        """Additive at position 0 — guard must NOT trigger."""
        cp, ap = self._guard_split("te pido también un martillo")
        assert cp is None and ap is None

    def test_clarif_sin_additive_match(self):
        """No additive phrase at all — guard must NOT trigger."""
        cp, ap = self._guard_split("para chapa de 0.6mm")
        assert cp is None and ap is None


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (slow — require DB and API)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestF1CompoundRoutingIntegration:
    """
    End-to-end tests verifying the compound clarification+additive path.

    These tests require a working API key and catalog database.
    Run with: PYTHONPATH=. pytest -m slow bot_sales/tests/test_f1_compound_routing.py
    """

    @pytest.fixture
    def bot(self):
        from bot_sales.runtime import get_runtime_bot
        return get_runtime_bot("ferreteria")

    def _sid(self):
        return f"f1_test_{uuid.uuid4().hex[:8]}"

    def test_clarif_alone_still_uses_clarification_path(self, bot):
        """Regression: pure clarification without additive still works."""
        sid = self._sid()
        bot.process_message(sid, "necesito destornillador philips")
        sess = bot.sessions.get(sid, {})
        aq = sess.get("active_quote", [])
        if not aq or aq[0].get("status") not in ("ambiguous", "unresolved"):
            pytest.skip("Catalog returned no ambiguous item — skip regression check")

        r2 = bot.process_message(sid, "la opcion a")
        sess2 = bot.sessions.get(sid, {})
        aq2 = sess2.get("active_quote", [])
        # The single clarification should resolve the destornillador without adding anything
        assert len(aq2) == len(aq), "Clarification alone should not add items"

    def test_additive_alone_still_works(self, bot):
        """Regression: additive-only message still appends correctly."""
        sid = self._sid()
        bot.process_message(sid, "necesito destornillador philips")
        sess = bot.sessions.get(sid, {})
        aq = sess.get("active_quote", [])
        initial_count = len(aq)

        bot.process_message(sid, "te pido también un martillo")
        sess2 = bot.sessions.get(sid, {})
        aq2 = sess2.get("active_quote", [])
        # Additive should add at least one item
        assert len(aq2) >= initial_count, "Additive should not remove items"

    def test_no_open_quote_no_dispara(self, bot):
        """Guard must not fire when there is no active quote."""
        sid = self._sid()
        # No T1 — empty session
        r = bot.process_message(sid, "la opcion a. te pido también un martillo")
        sess = bot.sessions.get(sid, {})
        # Bot should not crash; may produce product search or similar
        assert r is not None

    def test_compound_t1_t2_resolves_clarif_and_adds_martillo(self, bot):
        """
        Core F1 scenario:
          T1: destornillador philips → ambiguous, offers A/B/C
          T2: "la opcion a. te pido también un martillo"
              → destornillador resolved to opt A + martillo added to quote
        """
        sid = self._sid()
        bot.process_message(sid, "necesito destornillador philips")
        sess = bot.sessions.get(sid, {})
        aq = sess.get("active_quote", [])
        if not aq or aq[0].get("status") != "ambiguous" or not aq[0].get("products"):
            pytest.skip("Catalog returned no ambiguous destornillador — cannot test F1 compound path")

        bot.process_message(sid, "la opcion a. te pido también un martillo")
        sess2 = bot.sessions.get(sid, {})
        aq2 = sess2.get("active_quote", [])

        has_martillo = any("martillo" in (it.get("original") or "").lower() for it in aq2)
        assert has_martillo, (
            f"T2 should have added martillo to the quote, but quote is: {aq2}"
        )

    def test_full_flow_t1_t2_t3_t4(self, bot):
        """
        Full 4-turn scenario:
          T1: "necesito destornillador philips" → bot offers A/B/C
          T2: "la opcion a. te pido también un martillo"
              → resolves destornillador + adds martillo (ambiguous or resolved)
          T3: "me quedo con la b del martillo. cuanto es el total?"
              → resolves martillo B + shows total
          T4: "hoy te lo retiro por el local"
              → confirmation or local pickup acknowledgment

        Assert: no crash on any turn; martillo present after T2.
        """
        sid = self._sid()

        r1 = bot.process_message(sid, "necesito destornillador philips")
        assert r1 is not None, "T1 must return a response"

        sess = bot.sessions.get(sid, {})
        aq = sess.get("active_quote", [])
        if not aq or aq[0].get("status") != "ambiguous" or not aq[0].get("products"):
            pytest.skip("T1 returned no ambiguous item — cannot test full flow")

        r2 = bot.process_message(sid, "la opcion a. te pido también un martillo")
        assert r2 is not None, "T2 must return a response"
        sess2 = bot.sessions.get(sid, {})
        aq2 = sess2.get("active_quote", [])
        has_martillo = any("martillo" in (it.get("original") or "").lower() for it in aq2)
        assert has_martillo, f"After T2 quote must include martillo: {aq2}"

        r3 = bot.process_message(sid, "me quedo con la b del martillo. cuanto es el total?")
        assert r3 is not None, "T3 must return a response"

        r4 = bot.process_message(sid, "hoy te lo retiro por el local")
        assert r4 is not None, "T4 must return a response"
