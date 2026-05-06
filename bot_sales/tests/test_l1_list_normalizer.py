"""Tests for L1 — structured list normalizer (SalesBot._is_structured_list + _normalize_list_to_items)."""

import pytest
from unittest.mock import MagicMock, patch

from bot_sales.bot import SalesBot


# ── Unit: _is_structured_list ────────────────────────────────────────────────

class TestIsStructuredList:

    def test_numerals_paren(self):
        text = "Necesito:\n1) mecha 6mm\n2) martillo\n3) destornillador"
        assert SalesBot._is_structured_list(text) is True

    def test_numerals_dot(self):
        text = "Lista:\n1. tornillos\n2. mechas\n3. pintura"
        assert SalesBot._is_structured_list(text) is True

    def test_numerals_dash(self):
        text = "Presupuesto:\n1- amoladora\n2- disco de corte"
        assert SalesBot._is_structured_list(text) is True

    def test_bullets_dash(self):
        text = "necesito comprar:\n- mecha 6mm\n- mecha 8mm\n- destornillador phillips"
        assert SalesBot._is_structured_list(text) is True

    def test_bullets_asterisk(self):
        text = "items:\n* martillo\n* cinta de teflón\n* taladro"
        assert SalesBot._is_structured_list(text) is True

    def test_bullets_dot_unicode(self):
        text = "Lista:\n• mecha 6mm\n• martillo"
        assert SalesBot._is_structured_list(text) is True

    def test_prose_no_newline(self):
        text = "necesito martillo, mecha y destornillador"
        assert SalesBot._is_structured_list(text) is False

    def test_prose_with_newline_no_structure(self):
        text = "hola buen día\nnecesito un destornillador"
        assert SalesBot._is_structured_list(text) is False

    def test_only_one_item_line(self):
        # Only 1 numeral line — needs 2+ to qualify
        text = "Hola\n1) mecha 6mm\nalgo más de texto aquí"
        assert SalesBot._is_structured_list(text) is False

    def test_single_line(self):
        text = "necesito mechas 6mm"
        assert SalesBot._is_structured_list(text) is False

    def test_inline_numbered_no_newlines(self):
        text = "Necesito: 1) 50 tornillos 3 pulgadas 2) 5 mechas 6mm 3) 5 mechas 8mm 4) 1 amoladora"
        assert SalesBot._is_structured_list(text) is True

    def test_inline_numbered_real_whatsapp(self):
        text = "Hola, presupuesto para obra. Necesito: 1) 50 tornillos autoperforantes 3 pulgadas 2) 5 mechas de 6mm 3) 5 mechas de 8mm 4) 2 mechas de 10mm 5) 1 amoladora chica"
        assert SalesBot._is_structured_list(text) is True

    def test_inline_single_numeral_is_false(self):
        # Only 1 numeral marker — not a list
        text = "necesito 1) un martillo y algo más"
        assert SalesBot._is_structured_list(text) is False

    def test_long_list_obra(self):
        text = (
            "Hola, presupuesto para obra. Necesito:\n"
            "1) 50 tornillos autoperforantes 3 pulgadas\n"
            "2) 5 mechas de 6mm\n"
            "3) 5 mechas de 8mm\n"
            "4) 2 mechas de 10mm\n"
            "5) 3 cajas de tornillos drywall\n"
            "6) 1 amoladora chica\n"
            "7) 4 discos de corte 4 1/2\"\n"
            "8) 1 rollo cinta de papel para juntas"
        )
        assert SalesBot._is_structured_list(text) is True

    def test_mixed_bullets_message(self):
        text = (
            "necesito comprar:\n"
            "- mecha 6mm\n"
            "- mecha 8mm\n"
            "- destornillador phillips\n"
            "- martillo\n"
            "- cinta de teflón\n"
            "- 2 metros de manguera"
        )
        assert SalesBot._is_structured_list(text) is True


# ── Unit: _normalize_list_to_items ───────────────────────────────────────────

class TestNormalizeListToItems:

    def _make_chatgpt(self, return_content: str) -> MagicMock:
        client = MagicMock()
        client.send_message.return_value = {"content": return_content}
        return client

    def test_returns_csv_format(self):
        text = "Necesito:\n1) 5 mechas 6mm\n2) 1 martillo\n3) 2 metros manguera"
        mock_client = self._make_chatgpt("5 mechas 6mm, 1 martillo, 2 metros manguera")
        result = SalesBot._normalize_list_to_items(text, mock_client)
        assert "," in result
        assert "martillo" in result
        assert "manguera" in result

    def test_fallback_on_exception(self):
        text = "Necesito:\n1) mecha\n2) martillo"
        client = MagicMock()
        client.send_message.side_effect = Exception("API error")
        result = SalesBot._normalize_list_to_items(text, client)
        assert result == text

    def test_fallback_on_empty_response(self):
        text = "Necesito:\n1) mecha\n2) martillo"
        mock_client = self._make_chatgpt("   ")
        result = SalesBot._normalize_list_to_items(text, mock_client)
        assert result == text

    def test_prompt_contains_original_text(self):
        text = "Necesito:\n- mecha 6mm\n- martillo"
        mock_client = self._make_chatgpt("mecha 6mm, martillo")
        SalesBot._normalize_list_to_items(text, mock_client)
        call_args = mock_client.send_message.call_args
        messages = call_args[0][0]
        assert any(text in m.get("content", "") for m in messages)


# ── Slow E2E: integration via get_runtime_bot ────────────────────────────────

def get_runtime_bot():
    """Return a real SalesBot instance if env is available, else skip."""
    try:
        from bot_sales.bot import SalesBot
        from bot_sales.core.chatgpt import ChatGPTClient
        from bot_sales.core.database import Database
        bot = SalesBot(tenant_id="ferreteria")
        return bot
    except Exception as e:
        pytest.skip(f"Runtime bot unavailable: {e}")


@pytest.mark.slow
class TestL1EndToEnd:

    def test_numbered_list_produces_multiple_items(self):
        """Numbered list of 8 items — bot should resolve at least 4 (not 0 or 1)."""
        bot = get_runtime_bot()
        session_id = "l1_e2e_numbered_list_01"
        message = (
            "Hola, presupuesto para obra. Necesito:\n"
            "1) 50 tornillos autoperforantes 3 pulgadas\n"
            "2) 5 mechas de 6mm\n"
            "3) 5 mechas de 8mm\n"
            "4) 2 mechas de 10mm\n"
            "5) 3 cajas de tornillos drywall\n"
            "6) 1 amoladora chica\n"
            "7) 4 discos de corte 4 1/2\"\n"
            "8) 1 rollo cinta de papel para juntas"
        )
        reply = bot.process_message(session_id, message)
        sess = bot.sessions.get(session_id, {})
        active_quote = sess.get("active_quote", [])
        # Without L1 this produces 0-1 items; with L1 should resolve 4+
        assert len(active_quote) >= 4, (
            f"Expected ≥4 items in quote, got {len(active_quote)}. "
            f"active_quote={active_quote}\nreply={reply}"
        )

    def test_bullet_list_produces_multiple_items(self):
        """Bullet list of 6 items — bot should resolve at least 3."""
        bot = get_runtime_bot()
        session_id = "l1_e2e_bullet_list_01"
        message = (
            "necesito comprar:\n"
            "- mecha 6mm\n"
            "- mecha 8mm\n"
            "- destornillador phillips\n"
            "- martillo\n"
            "- cinta de teflón\n"
            "- 2 metros de manguera"
        )
        reply = bot.process_message(session_id, message)
        sess = bot.sessions.get(session_id, {})
        active_quote = sess.get("active_quote", [])
        assert len(active_quote) >= 3, (
            f"Expected ≥3 items in quote, got {len(active_quote)}. "
            f"active_quote={active_quote}\nreply={reply}"
        )

    def test_prose_unaffected(self):
        """Prose multi-item message should still work (L1 guard skipped)."""
        bot = get_runtime_bot()
        session_id = "l1_e2e_prose_01"
        message = "necesito 3 mechas de 6mm, un martillo y destornillador phillips"
        reply = bot.process_message(session_id, message)
        sess = bot.sessions.get(session_id, {})
        active_quote = sess.get("active_quote", [])
        assert len(active_quote) >= 2, (
            f"Prose path broken — expected ≥2 items, got {len(active_quote)}. reply={reply}"
        )
