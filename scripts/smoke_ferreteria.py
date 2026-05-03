#!/usr/bin/env python3
"""Smoke test del flujo de ferreteria sin web."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_sales.ferreteria_unresolved_log import suppress_unresolved_logging  # noqa: E402
from bot_sales.runtime import get_runtime_bot, get_runtime_tenant  # noqa: E402


def main() -> int:
    tenant = get_runtime_tenant("ferreteria")
    bot = get_runtime_bot(tenant.id)
    checks = []
    run_id = uuid.uuid4().hex[:8]

    def sid(name: str) -> str:
        return f"{name}_{run_id}"

    try:
        with suppress_unresolved_logging():
            greeting = bot.process_message(sid("smoke_saludo"), "hola")
            checks.append(("saludo", bool(greeting), greeting[:120]))

            taladro = bot.process_message(sid("smoke_taladro"), "Busco un taladro")
            checks.append(("routing taladro", "Taladro" in taladro and "Lo necesit" not in taladro, taladro[:180]))

            tornillos = bot.process_message(sid("smoke_tornillos"), "Necesito tornillos para chapa")
            checks.append(("routing tornillos", "tornillo" in tornillos.lower() and "chapa" in tornillos.lower() and "Pag" not in tornillos, tornillos[:180]))

            faq = bot.process_message(sid("smoke_faq"), "Hacen factura A?")
            checks.append(("faq factura", "factura A" in faq and "Lo necesit" not in faq, faq[:180]))

            multi = bot.process_message(sid("smoke_multi"), "Quiero silicona y teflon")
            checks.append(("routing multi-item", "silicona" in multi.lower() and "teflon" in multi.lower() and "Pag" not in multi, multi[:220]))

            quote = bot.process_message(sid("smoke_quote"), "Necesito tornillos para chapa y un taladro")
            checks.append((
                "quote builder structured",
                "Presupuesto preliminar" in quote and "urgencia" not in quote.lower() and "pago" not in quote.lower(),
                quote[:280],
            ))

            project = bot.process_message(sid("smoke_project"), "Pasame presupuesto para un baño")
            checks.append(("routing proyecto", "urgencia" not in project.lower() and "pago" not in project.lower() and "rubros" in project.lower(), project[:220]))

            # Phase 1.5 — quantity + subtotal
            qty_quote = bot.process_message(sid("smoke_qty"), "Quiero 2 siliconas y 3 teflones")
            checks.append((
                "qty + subtotal",
                "Presupuesto preliminar" in qty_quote and ("2" in qty_quote or "3" in qty_quote) and "urgencia" not in qty_quote.lower(),
                qty_quote[:300],
            ))

            # Phase 1.5 — synonym expansion
            synonym = bot.process_message(sid("smoke_synonym"), "Necesito taco fisher y mecha")
            checks.append((
                "synonym expansion",
                "Presupuesto preliminar" in synonym
                and "urgencia" not in synonym.lower()
                and ("tarugo" in synonym.lower() or "fisher" in synonym.lower() or "taco" in synonym.lower())
                and ("medida" in synonym.lower() or "madera" in synonym.lower() or "material" in synonym.lower()),
                synonym[:280],
            ))

            # Phase 1.5 — broad request rubros wording
            rubros = bot.process_message(sid("smoke_rubros"), "Necesito materiales para una instalacion")
            checks.append((
                "broad request rubros",
                "urgencia" not in rubros.lower() and "pago" not in rubros.lower() and any(
                    kw in rubros.lower() for kw in ("rubros", "materiales", "caños", "selladores")
                ),
                rubros[:220],
            ))

            # Multi-turn — clarification continuation
            bot.process_message(sid("smoke_mt_clar"), "Necesito taco fisher y mecha")
            mt_clar = bot.process_message(sid("smoke_mt_clar"), "Mecha de 8 mm para madera")
            checks.append((
                "multiturn clarification",
                ("Actualice" in mt_clar or "Presupuesto" in mt_clar)
                and "urgencia" not in mt_clar.lower()
                and "mecha" in mt_clar.lower()
                and "madera" in mt_clar.lower()
                and "taladro" not in mt_clar.lower(),
                mt_clar[:260],
            ))

            # Multi-turn — additive extension
            bot.process_message(sid("smoke_mt_add"), "Quiero 2 siliconas y 3 teflones")
            mt_add = bot.process_message(sid("smoke_mt_add"), "Agregale un taladro")
            checks.append((
                "multiturn additive",
                "taladro" in mt_add.lower() and ("silicona" in mt_add.lower() or "teflon" in mt_add.lower())
                and "urgencia" not in mt_add.lower(),
                mt_add[:280],
            ))

            # Multi-turn — reset
            bot.process_message(sid("smoke_mt_reset"), "Quiero silicona y teflon")
            mt_reset = bot.process_message(sid("smoke_mt_reset"), "nuevo presupuesto")
            checks.append((
                "multiturn reset",
                "borrado" in mt_reset.lower() or "nuevo" in mt_reset.lower(),
                mt_reset[:120],
            ))

            # Multi-turn — FAQ coexistence with open quote
            bot.process_message(sid("smoke_mt_faq"), "Quiero silicona y teflon")
            mt_faq_ans = bot.process_message(sid("smoke_mt_faq"), "Hacen factura A?")
            mt_faq_add = bot.process_message(sid("smoke_mt_faq"), "Agregale un taladro")
            checks.append((
                "faq + open quote",
                "factura A" in mt_faq_ans
                and "taladro" in mt_faq_add.lower()
                and ("silicona" in mt_faq_add.lower() or "teflon" in mt_faq_add.lower())
                and "urgencia" not in mt_faq_add.lower(),
                f"faq='{mt_faq_ans[:80]}' | add='{mt_faq_add[:120]}'",
            ))

            # Acceptance flow
            bot.process_message(sid("smoke_accept"), "Quiero silicona y teflon")
            accept_reply = bot.process_message(sid("smoke_accept"), "Dale, cerralo")
            checks.append((
                "acceptance handoff",
                any(kw in accept_reply.lower() for kw in ("aceptado", "equipo", "coordinar", "contactam", "confirmar")),
                accept_reply[:200],
            ))

            # Parser — 'con' must not split a single item
            from bot_sales import ferreteria_quote as fq_smoke
            con_items = fq_smoke.parse_quote_items("Quiero silicona con fungicida y teflon")
            checks.append((
                "parser con-no-split",
                len(con_items) == 2,
                f"items={[i['raw'] for i in con_items]}",
            ))

            # Pack/unit safety
            pack_reply = bot.process_message(sid("smoke_pack"), "Necesito 10 tornillos para chapa y un taladro")
            tornillo_unsafe = (
                "10" in pack_reply and "9.500" in pack_reply and "95.000" in pack_reply
                and "caja" not in pack_reply.lower() and "presentacion" not in pack_reply.lower()
                and "aclaracion" not in pack_reply.lower()
            )
            checks.append((
                "pack unit safety",
                not tornillo_unsafe,
                pack_reply[:200],
            ))
        ok = True
        for label, passed, detail in checks:
            print(f"[{'OK' if passed else 'FAIL'}] {label} - {detail}")
            ok = ok and passed
        return 0 if ok else 1
    finally:
        bot.close()


if __name__ == "__main__":
    raise SystemExit(main())
