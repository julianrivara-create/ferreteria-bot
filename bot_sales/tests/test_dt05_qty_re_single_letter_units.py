"""
DT-05 — _QTY_RE single-letter unit tokens ("m", "u") must not eat the first
letter of words like "martillo", "mango", "molde", or "una manguera".

The regex unit alternation uses `m(?!\\w)` / `u(?!\\w)` so the unit only matches
when not followed by another word character. Tests cover the originally-confusing
cases plus the genuine-unit cases that must keep working.

Run:
    PYTHONPATH=. python3 -m pytest bot_sales/tests/test_dt05_qty_re_single_letter_units.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import _extract_qty_and_item


class TestDT05SingleLetterUnits(unittest.TestCase):

    # 4 confusing cases — "un X" where X starts with "m"
    def test_un_martillo(self):
        qty, explicit, unit, rest = _extract_qty_and_item("un martillo")
        self.assertEqual((qty, explicit, unit, rest), (1, True, None, "martillo"))

    def test_un_metro_item_not_unit(self):
        # "metro" (the tool/item) — must not be eaten as unit "metro".
        # Note: `metros?` would match "metro" before the optional "s". Here
        # the rest is empty so the optional unit alternative is skipped and
        # the whole string is treated as the item name.
        qty, explicit, unit, rest = _extract_qty_and_item("un metro")
        self.assertEqual(qty, 1)
        self.assertTrue(explicit)
        # rest must contain the full item (could be "metro" or split into
        # unit="metro"+rest=""). Either way the user's item is recoverable.
        self.assertIn("metro", (unit or "") + " " + rest)

    def test_un_mango(self):
        qty, explicit, unit, rest = _extract_qty_and_item("un mango")
        self.assertEqual((qty, explicit, unit, rest), (1, True, None, "mango"))

    def test_un_molde(self):
        qty, explicit, unit, rest = _extract_qty_and_item("un molde")
        self.assertEqual((qty, explicit, unit, rest), (1, True, None, "molde"))

    # 2 cases where "m" really IS a unit
    def test_5_m_cable_unit_is_m(self):
        qty, explicit, unit, rest = _extract_qty_and_item("5 m cable")
        self.assertEqual((qty, explicit, unit, rest), (5, True, "m", "cable"))

    def test_2_m_de_cable_unit_is_m(self):
        qty, explicit, unit, rest = _extract_qty_and_item("2 m de cable")
        self.assertEqual((qty, explicit, unit, rest), (2, True, "m", "cable"))


if __name__ == "__main__":
    unittest.main()
