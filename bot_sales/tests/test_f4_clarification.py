"""
F4 Bug fix — regression tests for detect_option_selection and looks_like_additive.

These tests guard the regex changes introduced to make clarification responses
deterministic: extended option-selection phrases and additional additive verb forms.
"""
import pytest
import bot_sales.ferreteria_quote as fq


class TestF4DetectOptionSelection:
    # ── New two-word prefix patterns (D3) ─────────────────────────────────

    def test_la_opcion_A_returns_index_0(self):
        assert fq.detect_option_selection("la opcion A") == 0

    def test_la_opcion_b_lowercase_returns_index_1(self):
        assert fq.detect_option_selection("la opcion b") == 1

    def test_la_opcion_C_returns_index_2(self):
        assert fq.detect_option_selection("la opcion C") == 2

    def test_la_opcion_A_with_tilde_returns_index_0(self):
        assert fq.detect_option_selection("la opción A") == 0

    def test_la_opcion_b_with_tilde_returns_index_1(self):
        assert fq.detect_option_selection("la opción b") == 1

    def test_me_quedo_con_la_A_returns_index_0(self):
        assert fq.detect_option_selection("me quedo con la A") == 0

    def test_me_quedo_con_la_C_returns_index_2(self):
        assert fq.detect_option_selection("me quedo con la C") == 2

    def test_con_la_A_returns_index_0(self):
        assert fq.detect_option_selection("con la A") == 0

    def test_con_la_B_returns_index_1(self):
        assert fq.detect_option_selection("con la B") == 1

    def test_quiero_la_B_returns_index_1(self):
        assert fq.detect_option_selection("quiero la B") == 1

    def test_tomo_la_A_returns_index_0(self):
        assert fq.detect_option_selection("tomo la A") == 0

    def test_dame_la_A_returns_index_0(self):
        assert fq.detect_option_selection("dame la A") == 0

    def test_dame_la_B_returns_index_1(self):
        assert fq.detect_option_selection("dame la B") == 1

    def test_voy_con_la_B_returns_index_1(self):
        assert fq.detect_option_selection("voy con la B") == 1

    def test_elijo_la_C_returns_index_2(self):
        assert fq.detect_option_selection("elijo la C") == 2

    def test_option_in_compound_message_detected(self):
        # "la opcion A. tambien te pido un martillo" — CASO B T2
        assert fq.detect_option_selection("la opcion A. tambien te pido un martillo") == 0

    def test_me_quedo_con_la_B_in_compound_detected(self):
        # "me quedo con la B. cuanto es el total?"
        assert fq.detect_option_selection("me quedo con la B. cuanto es el total?") == 1

    # ── Regressions — existing patterns must still work (D3) ──────────────

    def test_existing_simple_A_still_works(self):
        assert fq.detect_option_selection("A") == 0

    def test_existing_simple_B_still_works(self):
        assert fq.detect_option_selection("B") == 1

    def test_existing_la_A_still_works(self):
        assert fq.detect_option_selection("la A") == 0

    def test_existing_opcion_A_still_works(self):
        assert fq.detect_option_selection("opcion A") == 0

    def test_existing_el_primero_still_works(self):
        assert fq.detect_option_selection("el primero") == 0

    def test_existing_segundo_still_works(self):
        assert fq.detect_option_selection("el segundo") == 1

    def test_existing_cualquiera_still_works(self):
        assert fq.detect_option_selection("cualquiera") == 0

    # ── Negative cases — must NOT match ───────────────────────────────────

    def test_unrelated_phrase_returns_None(self):
        assert fq.detect_option_selection("para madera") is None

    def test_martillo_alone_returns_None(self):
        assert fq.detect_option_selection("un martillo") is None

    def test_letter_f_out_of_range_returns_None(self):
        # F is outside a-e range
        assert fq.detect_option_selection("la opcion F") is None

    def test_additive_phrase_returns_None(self):
        assert fq.detect_option_selection("tambien te pido un martillo") is None

    def test_material_answer_returns_None(self):
        assert fq.detect_option_selection("Para madera, por favor") is None


class TestF4LooksLikeAdditive:
    # ── New additive verb forms (D4) ──────────────────────────────────────

    def test_tambien_te_pido_returns_True(self):
        assert fq.looks_like_additive("tambien te pido un martillo") is True

    def test_tambien_te_pido_with_product_returns_True(self):
        assert fq.looks_like_additive("tambien te pido 2 tornillos") is True

    def test_te_pido_tambien_returns_True(self):
        assert fq.looks_like_additive("te pido también un destornillador") is True

    def test_te_pido_tambien_no_tilde_returns_True(self):
        assert fq.looks_like_additive("te pido tambien una mecha") is True

    def test_tambien_dame_returns_True(self):
        assert fq.looks_like_additive("también dame un martillo") is True

    def test_tambien_dame_no_tilde_returns_True(self):
        assert fq.looks_like_additive("tambien dame brocas") is True

    def test_agregale_tambien_returns_True(self):
        assert fq.looks_like_additive("agregale también una mecha") is True

    def test_sumale_tambien_returns_True(self):
        assert fq.looks_like_additive("sumale también un martillo") is True

    def test_sumale_alone_returns_True(self):
        assert fq.looks_like_additive("sumale un tornillo") is True

    # ── Regressions — existing additive forms must still work (D4) ────────

    def test_existing_tambien_quiero_still_works(self):
        assert fq.looks_like_additive("tambien quiero un martillo") is True

    def test_existing_tambien_necesito_still_works(self):
        assert fq.looks_like_additive("tambien necesito brocas") is True

    def test_existing_agregame_still_works(self):
        assert fq.looks_like_additive("agregame un tornillo") is True

    def test_existing_agregale_still_works(self):
        assert fq.looks_like_additive("agregale una mecha") is True

    def test_existing_suma_still_works(self):
        assert fq.looks_like_additive("suma un martillo") is True

    def test_existing_y_tambien_still_works(self):
        assert fq.looks_like_additive("y tambien quiero tornillos") is True

    # ── Negative cases — must NOT match ───────────────────────────────────

    def test_unrelated_phrase_returns_False(self):
        assert fq.looks_like_additive("para madera") is False

    def test_option_selection_returns_False(self):
        assert fq.looks_like_additive("la opcion A") is False

    def test_plain_product_query_returns_False(self):
        assert fq.looks_like_additive("necesito un martillo") is False

    def test_clarification_answer_returns_False(self):
        assert fq.looks_like_additive("Para madera, por favor") is False
