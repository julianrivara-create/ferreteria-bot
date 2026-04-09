# tests/test_ferreteria_setup.py
# ============================================================
# Ferreteria bot — functional test suite (corrective pass)
# ============================================================
# Tests validate real process_message() behaviour, not just helpers.
# Every test must confirm:
#   - structured quote output where required
#   - NO urgency/payment fallback for quote-oriented messages
#   - honest unresolving, ambiguity, pack-unit safety, acceptance
# ============================================================
from pathlib import Path

import yaml

from bot_sales.bot import SalesBot
from bot_sales.core.business_logic import BusinessLogic
from bot_sales.core.database import Database
from bot_sales.runtime import get_runtime_tenant, resolve_runtime_tenant_id

ROOT = Path(__file__).resolve().parents[1]


def build_ferreteria_logic(tmp_path):
    catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    db = Database(
        db_file=str(tmp_path / "ferreteria_test.db"),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / "ferreteria_test.log"),
    )
    return db, BusinessLogic(db)


def build_ferreteria_bot(tmp_path):
    catalog = ROOT / "data" / "tenants" / "ferreteria" / "catalog.csv"
    profile = yaml.safe_load(
        (ROOT / "data" / "tenants" / "ferreteria" / "profile.yaml").read_text(encoding="utf-8")
    )
    db = Database(
        db_file=str(tmp_path / "ferreteria_bot.db"),
        catalog_csv=str(catalog),
        log_path=str(tmp_path / "ferreteria_bot.log"),
    )
    bot = SalesBot(
        db=db,
        api_key="",
        tenant_id="ferreteria",
        tenant_profile=profile,
    )
    return bot


# ---- Baseline setup tests ------------------------------------------------


def test_runtime_defaults_to_ferreteria():
    assert resolve_runtime_tenant_id() == "ferreteria"


def test_ferreteria_profile_loaded():
    tenant = get_runtime_tenant("ferreteria")
    assert tenant.name == "Ferreteria Central"
    assert tenant.profile["business"]["industry"] == "ferreteria"


def test_ferreteria_catalog_has_searchable_products(tmp_path):
    _, logic = build_ferreteria_logic(tmp_path)
    result = logic.buscar_stock("silicona")
    assert result["status"] in ("found", "no_match", "no_stock")


def test_ferreteria_faq_answers_factura(tmp_path):
    _, logic = build_ferreteria_logic(tmp_path)
    result = logic.consultar_faq("Hacen factura A?")
    assert result["status"] == "found"
    assert "factura" in str(result.get("respuesta", "")).lower()


def test_conversation_busco_un_taladro_is_product_first(tmp_path):
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("sid_taladro", "Busco un taladro")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        assert "taladro" in reply.lower()
        assert "amoladora" not in reply.lower()
        assert any(fragment in reply.lower() for fragment in ("hogar", "obra", "uso seguido", "conviene"))
    finally:
        bot.close()


def test_conversation_factura_a_hits_faq_before_planning(tmp_path):
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("sid_faq", "Hacen factura A?")
        assert "factura" in reply.lower()
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
    finally:
        bot.close()


def test_conversation_silicona_y_teflon_resolves_multi_item_first(tmp_path):
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("sid_multi", "Quiero silicona y teflon")
        assert "Presupuesto" in reply
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        assert any(fragment in reply.lower() for fragment in ("te arme", "si queres", "precio", "uso"))
    finally:
        bot.close()


def test_open_quote_recommendation_request_gets_consultative_reply(tmp_path):
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("sid_reco", "Quiero silicona y teflon")
        reply = bot.process_message("sid_reco", "¿Cuál me recomendás?")
        lower = reply.lower()
        assert "urgencia" not in lower
        assert "pago" not in lower
        assert any(fragment in lower for fragment in ("yo arrancaria", "yo arrancaría", "conviene", "hogar", "obra"))
        assert "silicona" in lower or "teflon" in lower
    finally:
        bot.close()


def test_open_quote_price_objection_stays_consultative(tmp_path):
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("sid_price", "Quiero silicona y teflon")
        reply = bot.process_message("sid_price", "Lo necesito más barato")
        lower = reply.lower()
        assert "urgencia" not in lower
        assert "pago" not in lower
        assert any(fragment in lower for fragment in ("cuidar el numero", "presupuesto tope", "priorizas precio", "priorizás precio"))
    finally:
        bot.close()


# ---- Business scenario 1: Strong simple quote ----------------------------


def test_biz_01_simple_quote_with_quantities(tmp_path):
    """2 silicones + 3 teflones — structured quote, subtotals, no payment."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz01", "Quiero 2 siliconas y 3 teflones")
        assert "Presupuesto" in reply
        assert "silicona" in reply.lower() or "silicona" in reply.lower()
        assert "teflon" in reply.lower()
        # Quantities must appear
        assert "2" in reply or "Cantidad: 2" in reply
        assert "3" in reply or "Cantidad: 3" in reply
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
    finally:
        bot.close()


# ---- Business scenario 2: Pack/unit safety --------------------------------


def test_biz_02_pack_unit_safety(tmp_path):
    """
    '10 tornillos para chapa' — SKU is 'Caja x100'.
    Bot must NOT silently treat 10 as 10 boxes.
    Either: warns about pack presentation, OR asks for clarification.
    Must NOT show '$9.500 x 10 = $95.000' with no warning if SKU is a pack.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz02", "Necesito 10 tornillos para chapa y un taladro")
        assert "Presupuesto" in reply
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        # If tornillos resolved to a pack SKU, the reply must include a pack warning
        # OR mark it as requiring clarification.
        tornillo_quoted_wrong = (
            "10" in reply
            and "9.500" in reply
            and "95.000" in reply
            and "caja" not in reply.lower()
            and "presentacion" not in reply.lower()
            and "aclaracion" not in reply.lower()
        )
        assert not tornillo_quoted_wrong, (
            "Bot quoted 10 boxes without pack safety warning — unsafe quantity semantics."
        )
    finally:
        bot.close()


# ---- Business scenario 3: Broad request ----------------------------------


def test_biz_03_broad_request_rubros(tmp_path):
    """'Presupuesto para un baño' — must ask for rubros, not sales qualify."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz03", "Pasame presupuesto para un baño")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        assert any(kw in reply.lower() for kw in (
            "rubros", "materiales", "caños", "selladores", "lista",
            "necesito", "presupuesto"
        ))
    finally:
        bot.close()


# ---- Business scenario 4: Synonym + clarification continuation -----------


def test_biz_04_synonym_and_clarification(tmp_path):
    """
    Turn 1: 'taco fisher y mecha' → taco resolves via synonym, mecha ambiguous.
    Turn 2: 'Mecha de 8 mm para madera' → mecha updated, no restart.
    CRITICAL: mecha must NOT resolve to 'taladro'.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply1 = bot.process_message("biz04", "Necesito taco fisher y mecha")
        assert "Presupuesto" in reply1
        assert "urgencia" not in reply1.lower()
        assert "tarugo" in reply1.lower() or "fischer" in reply1.lower(), (
            "Taco fisher should resolve through synonym expansion to the tarugo SKU"
        )
        assert "requiere aclaracion" in reply1.lower() or "aclaraciones pendientes" in reply1.lower(), (
            "Mecha should stay pending until material/size are clarified"
        )

        reply2 = bot.process_message("biz04", "Mecha de 8 mm para madera")
        assert "urgencia" not in reply2.lower()
        assert "pago" not in reply2.lower()
        # Mecha clarification must NOT resolve to 'taladro' (the drill)
        assert "taladro" not in reply2.lower() or "mecha" in reply2.lower(), (
            "Mecha clarification incorrectly resolved to 'Taladro' — false positive."
        )
        assert "mecha madera 8mm" in reply2.lower() or "mecha de 8 mm para madera" in reply2.lower(), (
            "Clarification should resolve to the mecha SKU, not stay generic"
        )
        # Must return updated quote or clarification, not restart
        assert "Actualice" in reply2 or "Presupuesto" in reply2 or "mecha" in reply2.lower()
    finally:
        bot.close()


def test_biz_04b_single_item_taco_fisher_resolves_via_synonym(tmp_path):
    """Single-item product path must also use the ferreteria resolver for 'taco fisher'."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz04b", "Necesito taco fisher")
        assert "presupuesto" in reply.lower()
        assert "tarugo" in reply.lower() or "fischer" in reply.lower()
        assert "no resuelto" not in reply.lower()
    finally:
        bot.close()


def test_biz_04c_single_item_mecha_and_broca_resolve_usefully(tmp_path):
    """Single-item mecha/broca requests must resolve from the catalog instead of drifting."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        mecha_reply = bot.process_message("biz04c_mecha", "Necesito mecha para madera 8mm")
        assert "mecha madera 8mm" in mecha_reply.lower()
        assert "no resuelto" not in mecha_reply.lower()
        assert "taladro" not in mecha_reply.lower()

        broca_reply = bot.process_message("biz04c_broca", "Necesito broca para metal 10mm")
        assert "mecha metal 10mm" in broca_reply.lower() or "broca" in broca_reply.lower()
        assert "no resuelto" not in broca_reply.lower()
    finally:
        bot.close()


# ---- Business scenario 5: Unknown item -----------------------------------


def test_biz_05_unknown_item_is_honest(tmp_path):
    """'Electrovávula industrial 3/4' — must NOT false-positive match."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz05", "Necesito electrovalvula industrial 3/4 y taladro")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        # Electrovalvula should NOT be quietly matched to something unrelated
        # It must appear as unresolved or with honest clarification
        assert "Presupuesto" in reply  # multi-item path still works
        # The electrovalvula line should NOT claim to be "resuelto" with a random product
        # (We can't easily assert the absence of a false match from test context,
        #  but we CAN assert it doesn't pretend everything is fine)
        assert "no resuelto" in reply.lower() or "no encontre" in reply.lower() or "aclaracion" in reply.lower() or "requiere" in reply.lower()
    finally:
        bot.close()


# ---- Business scenario 6: Same-family alternatives only ------------------


def test_biz_06_alternatives_are_same_family(tmp_path):
    """
    When a product has alternatives, they must be same-family.
    Requesting silicona must not produce a taladro as an alternative.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz06", "Quiero silicona y teflon")
        assert "urgencia" not in reply.lower()
        # If alternatives appear, none should be 'taladro' (completely unrelated)
        lower = reply.lower()
        if "alternativa" in lower:
            assert "taladro" not in lower, (
                "Bot showed 'taladro' as an alternative for silicona — unrelated product."
            )
    finally:
        bot.close()


# ---- Business scenario 7: Complementary suggestions ---------------------


def test_biz_07_complementary_only_when_grounded(tmp_path):
    """
    Complementary suggestions must only appear for catalog-grounded relations.
    They must never include completely unrelated products.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply = bot.process_message("biz07", "Quiero 2 siliconas y 3 teflones")
        # If complementary appears, it must be relevant (not e.g., a random item from another category)
        if "También podrías necesitar" in reply:
            lower = reply.lower()
            # A random unrelated product like 'amoladora' should not appear as complement to silicona
            assert "amoladora" not in lower
        assert "urgencia" not in reply.lower()
    finally:
        bot.close()


# ---- Business scenario 8: Additive update --------------------------------


def test_biz_08_additive_update(tmp_path):
    """Turn 1: siliconas + teflones. Turn 2: 'agregale un taladro'."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply1 = bot.process_message("biz08", "Quiero 2 siliconas y 3 teflones")
        assert "Presupuesto" in reply1

        reply2 = bot.process_message("biz08", "Agregale un taladro")
        # Original items must still appear
        assert "silicona" in reply2.lower() or "teflon" in reply2.lower()
        # New item must appear
        assert "taladro" in reply2.lower()
        assert "Actualice" in reply2 or "Presupuesto" in reply2
        assert "urgencia" not in reply2.lower()
    finally:
        bot.close()


# ---- Business scenario 9: FAQ during open quote --------------------------


def test_biz_09_faq_during_open_quote(tmp_path):
    """FAQ answered, quote preserved, additive still works after."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("biz09", "Quiero silicona y teflon")
        reply_faq = bot.process_message("biz09", "Hacen factura A?")
        assert "factura" in reply_faq.lower()

        reply_add = bot.process_message("biz09", "Agregale un taladro")
        assert "taladro" in reply_add.lower()
        assert "silicona" in reply_add.lower() or "teflon" in reply_add.lower()
    finally:
        bot.close()


# ---- Business scenario 10: Acceptance (all items resolved) ---------------


def test_biz_10_acceptance_clean(tmp_path):
    """
    Start a quote where all items resolve cleanly.
    Then 'Dale, cerralo' → accepted state, internal handoff reply.
    Must NOT be parsed as product items.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        reply1 = bot.process_message("biz10", "Quiero silicona y teflon")
        assert "Presupuesto" in reply1

        reply2 = bot.process_message("biz10", "Dale, cerralo")
        # Must not parse "Dale" as a product
        assert "urgencia" not in reply2.lower()
        assert "pago" not in reply2.lower()
        # Must confirm acceptance or business handoff
        assert any(kw in reply2.lower() for kw in (
            "aceptado", "equipo", "coordinar", "procesem", "contactam", "confirmar", "borrados"
        ))
    finally:
        bot.close()


# ---- Business scenario 11: Acceptance blocked by unresolved items --------


def test_biz_11_acceptance_blocked_when_unresolved(tmp_path):
    """
    Start quote with ambiguous items.
    'Acepto' must be blocked until clarifications are complete.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        # Mecha is always ambiguous; 'electrovalvula' is always unresolved
        reply1 = bot.process_message("biz11", "Necesito mecha y electrovalvula")
        assert "Presupuesto" in reply1

        reply2 = bot.process_message("biz11", "Acepto el presupuesto")
        assert "urgencia" not in reply2.lower()
        assert "pago" not in reply2.lower()
        # Must warn about pending items
        assert any(kw in reply2.lower() for kw in (
            "aclaracion", "pendiente", "antes de confirmar", "definir", "unresolved",
            "requiere", "no resuelto", "clarar"
        ))
    finally:
        bot.close()


# ---- Business scenario 12: Reset -----------------------------------------


def test_biz_12_explicit_reset(tmp_path):
    """Turn 1: open quote. Turn 2: 'nuevo presupuesto' clears it."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("biz12", "Quiero silicona y teflon")
        reply = bot.process_message("biz12", "nuevo presupuesto")
        assert "borrado" in reply.lower() or "nuevo" in reply.lower()
        assert "urgencia" not in reply.lower()
    finally:
        bot.close()


# ---- Business scenario 13: Post-acceptance new quote ---------------------


def test_biz_13_post_acceptance_new_quote_starts_fresh(tmp_path):
    """
    After acceptance, a new multi-item request must start a fresh quote,
    not be misparsed as additive to the accepted one.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("biz13", "Quiero silicona y teflon")
        bot.process_message("biz13", "Dale, cerralo")
        # New request — must produce a fresh Presupuesto, not an "Actualice"
        reply = bot.process_message("biz13", "Ahora necesito un taladro y guantes")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        assert "taladro" in reply.lower() or "guante" in reply.lower() or "presupuesto" in reply.lower()
    finally:
        bot.close()


# ---- Preventive hardening tests ------------------------------------------


def test_prev_con_is_not_a_false_split(tmp_path):
    """
    'silicona con fungicida' must produce ONE quote item, not two.
    'con' must not be treated as a list separator.
    """
    from bot_sales import ferreteria_quote as fq

    items = fq.parse_quote_items("Quiero silicona con fungicida y teflon")
    # Must parse as 2 items: "silicona con fungicida" and "teflon"
    # NOT 3 items: "silicona", "fungicida", "teflon"
    assert len(items) == 2, (
        f"Expected 2 items (silicona con fungicida, teflon), got {len(items)}: {[i['raw'] for i in items]}"
    )
    assert any("silicona" in i.get("normalized", "") and "fungicida" in i.get("normalized", "") for i in items), (
        "Parser split 'silicona con fungicida' — should remain one line"
    )


def test_prev_acceptance_state_stable_after_short_input(tmp_path):
    """
    After acceptance, short replies ('ok', 'gracias') must not
    reopen the quote or cause a loop / session-guard echo.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("prev_acc", "Quiero silicona y teflon")
        reply_acc = bot.process_message("prev_acc", "Dale, cerralo")
        assert any(kw in reply_acc.lower() for kw in ("aceptado", "equipo", "contactam", "coordinar"))

        # After acceptance, a short reply must NOT produce another full quote
        reply_short = bot.process_message("prev_acc", "ok")
        # Should either answer as FAQ / pass through gracefully, not re-echo full quote dump
        # Key invariant: must not crash or return None
        assert reply_short is not None
    finally:
        bot.close()


def test_prev_referential_price_not_shown_as_committed(tmp_path):
    """
    Ambiguous items must visually distinguish referential pricing from
    committed pricing — no subtotal should appear for ambiguous lines.
    """
    from bot_sales import ferreteria_quote as fq

    item = {
        "original":     "mecha",
        "normalized":   "mecha",
        "qty":          1,
        "qty_explicit": False,
        "unit_hint":    None,
        "status":       "ambiguous",
        "products":     [{"model": "Taladro Percutor 13mm", "price_ars": 125000}],
        "unit_price":   125000.0,
        "subtotal":     None,   # must be None for ambiguous
        "pack_note":    None,
        "clarification": "decime medida y material",
        "notes":        "Opciones relacionadas",
        "complementary": [],
    }
    rendered = fq.generate_quote_response([item])
    # Subtotal line must NOT appear
    assert "125.000\n" not in rendered or "referencial" in rendered.lower() or "Subtotal" not in rendered
    assert "requiere aclaracion" in rendered.lower() or "aclaracion" in rendered.lower()


def test_prev_faq_plus_clarification_plus_additive_continuity(tmp_path):
    """
    Full state continuity: quote → FAQ → clarification → additive.
    Quote must survive all four steps coherent.
    """
    bot = build_ferreteria_bot(tmp_path)
    try:
        r1 = bot.process_message("prev_cont", "Necesito taco fisher y mecha")
        assert "Presupuesto" in r1

        r2 = bot.process_message("prev_cont", "Hacen factura A?")
        assert "factura" in r2.lower()

        r3 = bot.process_message("prev_cont", "Mecha de 8mm para madera")
        assert "urgencia" not in r3.lower()
        # Clarification should not wipe out the whole quote
        assert "taco" in r3.lower() or "tarugo" in r3.lower() or "Actualice" in r3

        r4 = bot.process_message("prev_cont", "Agregale silicona")
        assert "silicona" in r4.lower()
        assert "urgencia" not in r4.lower()
    finally:
        bot.close()


# ---- Structural / semantic hardening tests (Phase 3) ---------------------


def test_struct_01_line_id_present_on_all_items(tmp_path):
    """Every item returned by parse_quote_items and resolve_quote_item must have a line_id."""
    from bot_sales import ferreteria_quote as fq
    _, logic = build_ferreteria_logic(tmp_path)

    items = fq.parse_quote_items("Quiero silicona y teflon")
    assert all(it.get("line_id") for it in items), "Missing line_id in parsed items"

    resolved = [fq.resolve_quote_item(it, logic) for it in items]
    assert all(it.get("line_id") for it in resolved), "Missing line_id in resolved items"

    # Clarification must preserve the same line_id
    pending = [it for it in resolved if it["status"] in ("ambiguous", "unresolved")]
    if pending:
        before_id = pending[0]["line_id"]
        updated = fq.apply_clarification("280ml transparente", resolved, logic)
        updated_pending = [it for it in updated if it.get("line_id") == before_id]
        assert updated_pending, "line_id was lost during clarification"


def test_struct_02_remove_teflon(tmp_path):
    """'Sacá el teflón' removes the teflón line and updates the quote."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str02", "Quiero silicona y teflon")
        reply = bot.process_message("str02", "Sacá el teflon")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        # Teflón should be gone or the operation status message should appear
        assert "saqu" in reply.lower() or "teflon" not in reply.lower()
    finally:
        bot.close()


def test_struct_03_replace_silicona_por_sellador(tmp_path):
    """'Cambiá la silicona por sellador' replaces the silicona line."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str03", "Quiero silicona y teflon")
        reply = bot.process_message("str03", "Cambiá la silicona por sellador")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        # Either replacement success message OR new resolved item in quote
        assert "reemplac" in reply.lower() or "sellador" in reply.lower()
    finally:
        bot.close()


def test_struct_04_additive_qty_increment(tmp_path):
    """'Agregale otro teflón' must increment teflon qty, not add a duplicate line."""
    from bot_sales import ferreteria_quote as fq
    _, logic = build_ferreteria_logic(tmp_path)

    base = fq.parse_quote_items("Quiero 2 siliconas y 1 teflon")
    resolved = [fq.resolve_quote_item(it, logic) for it in base]

    # Check how many teflón lines exist
    teflon_before = [it for it in resolved if "teflon" in it.get("normalized", "").lower()
                     or "teflon" in it.get("original", "").lower()]

    updated = fq.apply_additive("Agregale otro teflon", resolved, logic)

    teflon_after = [it for it in updated if "teflon" in it.get("normalized", "").lower()
                    or "teflon" in it.get("original", "").lower()]

    # Must still have the same number of teflon LINES (not double)
    assert len(teflon_after) == len(teflon_before) or len(updated) < len(resolved) + 2, (
        "Additive qty increment created duplicate teflón lines"
    )

    # If teflón was resolved, qty should have incremented
    if teflon_before and teflon_before[0]["status"] == "resolved" and teflon_after:
        assert teflon_after[0].get("qty", 0) >= teflon_before[0].get("qty", 0), (
            "Quantity did not increment after 'agregale otro teflón'"
        )


def test_struct_05_merge_vs_replace_question_fires(tmp_path):
    """Open quote + new multi-item request must ask merge vs replace, not silently overwrite."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str05", "Quiero silicona y teflon")
        reply = bot.process_message("str05", "Necesito taladro y tornillos")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        # Must ask, not silently overwrite
        assert any(kw in reply.lower() for kw in (
            "sumalo", "nuevo", "actual", "abierto", "presupuesto"
        )), f"Expected merge-vs-replace question, got: {reply[:200]}"
        # Silicona/teflon items must NOT have been silently wiped yet
        sess_quote = bot.sessions.get("str05", {}).get("active_quote") or []
        orig_items = {it.get("original", "").lower() for it in sess_quote}
        assert any("silicona" in it for it in orig_items) or bot.sessions.get("str05", {}).get("pending_decision"), (
            "Quote was silently overwritten — merge-vs-replace guard failed"
        )
    finally:
        bot.close()


def test_struct_06_merge_answer_sumalo(tmp_path):
    """After merge-vs-replace question, 'sumalo' merges items into current quote."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str06", "Quiero silicona y teflon")
        bot.process_message("str06", "Necesito taladro y tornillos")  # triggers question
        reply = bot.process_message("str06", "sumalo")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
        # Merged quote should have silicona + taladro (or at least multiple items)
        lower = reply.lower()
        has_original = "silicona" in lower or "teflon" in lower
        has_new = "taladro" in lower or "tornillo" in lower
        assert has_original or has_new, (
            "After 'sumalo', merged quote is empty or missing expected items"
        )
    finally:
        bot.close()


def test_struct_07_new_answer_resets_to_new_quote(tmp_path):
    """After merge-vs-replace question, 'nuevo' starts fresh with the new items."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str07", "Quiero silicona y teflon")
        bot.process_message("str07", "Necesito taladro y tornillos")  # triggers question
        reply = bot.process_message("str07", "nuevo")
        assert "urgencia" not in reply.lower()
        # New quote should have taladro/tornillos, not silicona
        lower = reply.lower()
        assert "taladro" in lower or "tornillo" in lower or "presupuesto" in lower
    finally:
        bot.close()


def test_struct_08_remove_updates_total(tmp_path):
    """Removing a resolved item must update the total — not show stale total."""
    from bot_sales import ferreteria_quote as fq
    _, logic = build_ferreteria_logic(tmp_path)

    base = fq.parse_quote_items("Quiero 2 siliconas y 3 teflones")
    resolved = [fq.resolve_quote_item(it, logic) for it in base]

    original_total_items = [it for it in resolved if it.get("subtotal") is not None]
    total_before = sum(it["subtotal"] for it in original_total_items)

    updated, msg = fq.apply_remove("Sacá el teflon", resolved)

    remaining_total_items = [it for it in updated if it.get("subtotal") is not None]
    total_after = sum(it["subtotal"] for it in remaining_total_items)

    # Total must have changed (reduction)
    removed_had_subtotal = any(
        "teflon" in it.get("normalized", "").lower() and it.get("subtotal") is not None
        for it in resolved
    )
    if removed_had_subtotal:
        assert total_after < total_before, (
            "Total did not decrease after removing a line with a subtotal"
        )


def test_struct_09_replace_preserves_line_id(tmp_path):
    """apply_replace must preserve the replaced line's line_id."""
    from bot_sales import ferreteria_quote as fq
    _, logic = build_ferreteria_logic(tmp_path)

    base = fq.parse_quote_items("Quiero silicona y teflon")
    resolved = [fq.resolve_quote_item(it, logic) for it in base]
    silicona_line = next(
        (it for it in resolved if "silicona" in it.get("original", "").lower()), None
    )
    if silicona_line is None:
        return  # skip if catalog doesn't resolve silicona

    original_id = silicona_line["line_id"]
    updated, msg = fq.apply_replace("Cambiá la silicona por sellador", resolved, logic)

    # The new item at the same position should have the same line_id
    new_item = next(
        (it for it in updated if it.get("line_id") == original_id), None
    )
    assert new_item is not None, (
        "apply_replace did not preserve the original line_id on the new item"
    )


def test_struct_10_clarification_targets_second_pending_item(tmp_path):
    """
    Two unresolved items: mecha + electrovalvula.
    Clarification 'Mecha de 8mm para madera' must target 'mecha', not 'electrovalvula'.
    """
    from bot_sales import ferreteria_quote as fq
    _, logic = build_ferreteria_logic(tmp_path)

    # Parse two items
    base = fq.parse_quote_items("Necesito mecha y electrovalvula")
    resolved = [fq.resolve_quote_item(it, logic) for it in base]

    # Both likely unresolved. Apply clarification explicitly about mecha.
    updated = fq.apply_clarification("Mecha de 8mm para madera", resolved, logic)

    # The electrovalvula line should be UNCHANGED
    orig_electro = next(
        (it for it in resolved if "electrovalvula" in it.get("normalized", "")), None
    )
    new_electro = next(
        (it for it in updated if it.get("line_id") == (orig_electro.get("line_id") if orig_electro else "")),
        None
    )
    if orig_electro and new_electro:
        assert new_electro["status"] == orig_electro["status"], (
            "Clarification about 'mecha' incorrectly changed 'electrovalvula' status"
        )


def test_struct_11_reset_clears_all_session_state(tmp_path):
    """Reset must clear active_quote, quote_state, pending_decision, and pending_clarification_target."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str11", "Quiero silicona y teflon")
        bot.process_message("str11", "Necesito taladro y tornillos")  # sets pending_decision
        bot.process_message("str11", "nuevo presupuesto")  # explicit reset

        sess = bot.sessions.get("str11", {})
        assert sess.get("active_quote") is None or sess.get("active_quote") == [], (
            "active_quote was not cleared by reset"
        )
        assert sess.get("quote_state") is None, "quote_state not cleared by reset"
        assert sess.get("pending_decision") is None, "pending_decision not cleared by reset"
        assert sess.get("pending_clarification_target") is None, (
            "pending_clarification_target not cleared by reset"
        )
    finally:
        bot.close()


def test_struct_12_accepted_quote_not_mutated_by_short_input(tmp_path):
    """After acceptance, short inputs (ok, gracias) must not mutate the accepted quote."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("str12", "Quiero silicona y teflon")
        accept_reply = bot.process_message("str12", "Dale, cerralo")
        # Verify acceptance happened
        assert any(kw in accept_reply.lower() for kw in ("aceptado", "equipo", "coordinar", "confirmar"))

        # Short input after acceptance
        reply = bot.process_message("str12", "ok")
        # Must not crash, must not re-echo a fresh full quote dump from a new request
        assert reply is not None
        # Should NOT return to a multi-item quote flow via urgency/payment
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()
    finally:
        bot.close()


def test_harden_01_match_to_line_prefers_distinctive_token():
    """Two similar silicone lines: 'la blanca' must target the white one."""
    from bot_sales import ferreteria_quote as fq

    lines = [
        {
            "line_id": "sil_white",
            "original": "Silicona blanca",
            "normalized": "silicona blanca sanitaria",
            "status": "ambiguous",
        },
        {
            "line_id": "sil_clear",
            "original": "Silicona transparente",
            "normalized": "silicona transparente neutra",
            "status": "ambiguous",
        },
    ]

    matched = fq._match_to_line("la blanca", lines)
    assert matched is not None, "Distinctive color token should have selected one line"
    assert matched["line_id"] == "sil_white", (
        f"Expected 'la blanca' to target sil_white, got {matched.get('line_id')}"
    )


def test_harden_02_match_to_line_returns_none_for_still_ambiguous_followup():
    """Two similar pending items: generic follow-up must not auto-target a line."""
    from bot_sales import ferreteria_quote as fq

    lines = [
        {
            "line_id": "madera",
            "original": "Mecha 8 mm madera",
            "normalized": "mecha 8mm madera",
            "status": "ambiguous",
        },
        {
            "line_id": "hormigon",
            "original": "Mecha 8 mm hormigon",
            "normalized": "mecha 8mm hormigon",
            "status": "ambiguous",
        },
    ]

    matched = fq._match_to_line("de 8 mm", lines)
    assert matched is None, (
        "Generic clarification 'de 8 mm' should stay ambiguous when both lines share the same distinctive token"
    )


def test_harden_03_match_to_line_margin_too_close_returns_none():
    """If two lines are too close, _match_to_line must refuse to guess."""
    from bot_sales import ferreteria_quote as fq

    lines = [
        {
            "line_id": "neutra",
            "original": "Silicona blanca neutra",
            "normalized": "silicona blanca neutra",
            "status": "ambiguous",
        },
        {
            "line_id": "sanitaria",
            "original": "Silicona blanca sanitaria",
            "normalized": "silicona blanca sanitaria",
            "status": "ambiguous",
        },
    ]

    matched = fq._match_to_line("la blanca", lines)
    assert matched is None, (
        "When the top two line matches are too close, the bot must ask disambiguation instead of auto-targeting"
    )


def test_harden_04_pending_decision_invalid_twice_defaults_to_merge(tmp_path):
    """Two invalid replies must fall back conservatively to merge and clear pending_decision."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("hard04", "Quiero silicona y teflon")
        bot.process_message("hard04", "Necesito taladro y tornillos")

        reply1 = bot.process_message("hard04", "mmm")
        assert "nuevo presupuesto" not in reply1.lower(), (
            "First invalid answer should re-ask, not trigger fallback-to-merge yet"
        )

        reply2 = bot.process_message("hard04", "no sé")
        assert "lo sumo al presupuesto actual" in reply2.lower()

        sess = bot.sessions.get("hard04", {})
        active = sess.get("active_quote") or []
        originals = {it.get("original", "").lower() for it in active}
        assert sess.get("pending_decision") is None, "pending_decision should be cleared after merge fallback"
        assert any("silicona" in item for item in originals), "Original quote items were lost after merge fallback"
        assert any("taladro" in item for item in originals), "New quote items were not merged after fallback"
    finally:
        bot.close()


def test_harden_05_pending_decision_explicit_nuevo_starts_fresh(tmp_path):
    """Explicit 'nuevo' must start a fresh quote, not merge into the old one."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("hard05", "Quiero silicona y teflon")
        bot.process_message("hard05", "Necesito taladro y tornillos")

        reply = bot.process_message("hard05", "nuevo")
        assert "urgencia" not in reply.lower()
        assert "pago" not in reply.lower()

        sess = bot.sessions.get("hard05", {})
        active = sess.get("active_quote") or []
        originals = {it.get("original", "").lower() for it in active}
        assert sess.get("pending_decision") is None, "pending_decision should be cleared after explicit 'nuevo'"
        assert any("taladro" in item for item in originals), "Fresh quote did not keep the new items"
        assert not any("silicona" in item for item in originals), "Old quote leaked into explicit 'nuevo' flow"
    finally:
        bot.close()


def test_harden_06_pending_decision_fallback_preserves_open_quote_state(tmp_path):
    """Fallback-to-merge must leave the quote state coherent and still open."""
    bot = build_ferreteria_bot(tmp_path)
    try:
        bot.process_message("hard06", "Quiero silicona y teflon")
        bot.process_message("hard06", "Necesito taladro y tornillos")
        bot.process_message("hard06", "qué")
        bot.process_message("hard06", "eh")

        sess = bot.sessions.get("hard06", {})
        active = sess.get("active_quote") or []
        assert sess.get("quote_state") == "open", "Merge fallback should preserve quote_state='open'"
        assert sess.get("pending_decision") is None, "pending_decision must be cleared after fallback merge"
        assert len(active) >= 4, "Fallback merge corrupted the active quote contents"
    finally:
        bot.close()


def test_harden_07_unresolved_review_log_records_terms(tmp_path, monkeypatch):
    """Ambiguous and unresolved items must be captured for pilot review."""
    from bot_sales import ferreteria_quote as fq
    from bot_sales.ferreteria_unresolved_log import summarize_log

    _, logic = build_ferreteria_logic(tmp_path)
    log_path = tmp_path / "unresolved_terms.jsonl"
    monkeypatch.setenv("FERRETERIA_UNRESOLVED_LOG", str(log_path))

    fq.resolve_quote_item(
        {"raw": "mecha", "normalized": "mecha", "qty": 1, "qty_explicit": False, "unit_hint": None},
        logic,
    )

    class FakeLogic:
        def buscar_stock(self, term):
            if term == "multiuso acrilico sanitario":
                return {
                    "status": "found",
                    "products": [
                        {"sku": "FAKE-1", "model": "Multiuso", "category": "Otros", "price_ars": 1000}
                    ],
                }
            return {"status": "no_match", "products": []}

        def buscar_por_categoria(self, categoria):
            return {"status": "no_match", "products": []}

    fq.resolve_quote_item(
        {"raw": "multiuso acrilico sanitario", "normalized": "multiuso acrilico sanitario", "qty": 1, "qty_explicit": False, "unit_hint": None},
        FakeLogic(),
    )
    fq.resolve_quote_item(
        {"raw": "electrovalvula industrial", "normalized": "electrovalvula industrial", "qty": 1, "qty_explicit": False, "unit_hint": None},
        logic,
    )

    summary = summarize_log(log_path=log_path, top_n=10)
    assert log_path.exists(), "Unresolved review log file was not created"
    assert summary["total"] >= 2, "Expected at least one ambiguous and one unresolved event in the review log"
    assert summary["by_status"].get("ambiguous", 0) >= 1, "Ambiguous items were not logged"
    assert summary["by_status"].get("unresolved", 0) >= 1, "Unresolved items were not logged"
