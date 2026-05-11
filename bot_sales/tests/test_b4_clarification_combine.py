"""
B.4: _combine_clarification_text must recognize shared tokens.

Bug: `target_norm in norm_clar.split()` only matched when target_norm was a
single word equal to one token of the clarification. For multi-word product
references ("mecha 8mm", "silicona acetica") the check was always False and
the search text fell into the prepend branch, producing duplicated product
context in the catalog query.

Fix: compare token-by-token.  If any token of target_norm appears in the
clarification tokens, use the clarification verbatim.
"""
from __future__ import annotations

from bot_sales.ferreteria_quote import _combine_clarification_text


class TestCombineClarificationText:
    def test_prefix_keeps_clarification_only(self):
        assert _combine_clarification_text("mecha 8mm para madera", "mecha") == "mecha 8mm para madera"

    def test_shared_single_token_uses_clarification(self):
        assert _combine_clarification_text("uso mecha en el taller", "mecha") == "uso mecha en el taller"

    def test_multiword_target_shared_token_uses_clarification(self):
        result = _combine_clarification_text("uso mecha en el taller", "mecha 8mm")
        assert result == "uso mecha en el taller"

    def test_multiword_target_no_overlap_prepends_target(self):
        result = _combine_clarification_text("para colgar cuadros", "mecha 8mm")
        assert result == "mecha 8mm para colgar cuadros"

    def test_empty_target_returns_clarification(self):
        assert _combine_clarification_text("280ml transparente", "") == "280ml transparente"

    def test_empty_clarification_with_target_prepends(self):
        assert _combine_clarification_text("", "mecha 8mm") == "mecha 8mm"
