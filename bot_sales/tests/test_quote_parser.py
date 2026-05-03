import sys
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).parent.parent.parent))

from bot_sales.ferreteria_quote import parse_quote_items


class TestQuoteParser(unittest.TestCase):

    def test_greeting_plus_colon_list(self):
        """Fix A1+A3+B: 'Hola, necesito presupuesto para una obra: item1, item2, item3'
        must NOT produce 'hola' as an item and must parse cleanly."""
        msg = (
            "Hola, necesito presupuesto para una obra: "
            "5 rollos de cinta aisladora, 3 llaves francesas chicas, "
            "2 sets de destornilladores, y 10 mechas de 8mm"
        )
        items = parse_quote_items(msg)
        raws = [i["raw"] for i in items]
        # No garbage 'hola' item
        self.assertFalse(
            any("hola" in r.lower() for r in raws),
            f"'hola' leaked into items: {raws}",
        )
        # Preamble must not be fused with first real product
        self.assertFalse(
            any("presupuesto" in r.lower() or "obra" in r.lower() for r in raws),
            f"Preamble fused into item: {raws}",
        )
        # Must parse 4 real items
        self.assertEqual(len(items), 4, f"Expected 4 items, got {len(items)}: {raws}")

    def test_plain_list_no_greeting(self):
        """Baseline: plain list without greeting still works."""
        msg = "necesito 5 rollos de cinta, 3 llaves, 10 mechas"
        items = parse_quote_items(msg)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["qty"], 5)
        self.assertEqual(items[1]["qty"], 3)
        self.assertEqual(items[2]["qty"], 10)

    def test_greeting_only_no_list(self):
        """Single-word greeting produces 0 items (not 1)."""
        msg = "Hola!"
        items = parse_quote_items(msg)
        self.assertEqual(len(items), 0, f"Expected 0 items, got: {items}")

    def test_semicolon_separator(self):
        """Fix B: semicolons as separators."""
        msg = "3 caños de 1 pulgada; 2 codos de 90; 1 llave de paso"
        items = parse_quote_items(msg)
        self.assertEqual(len(items), 3, f"Expected 3 items, got: {[i['raw'] for i in items]}")

    def test_buenas_greeting_variant(self):
        """Fix A1: 'Buenas,' greeting also stripped correctly."""
        msg = "Buenas, quiero presupuesto de 4 tubos y 6 llaves"
        items = parse_quote_items(msg)
        raws = [i["raw"] for i in items]
        self.assertFalse(
            any("buenas" in r.lower() for r in raws),
            f"'buenas' leaked into items: {raws}",
        )
        self.assertEqual(len(items), 2, f"Expected 2 items, got {len(items)}: {raws}")


if __name__ == "__main__":
    unittest.main()
