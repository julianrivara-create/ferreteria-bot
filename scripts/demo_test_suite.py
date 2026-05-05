#!/usr/bin/env python3
"""
Strict Regression Suite — Ferretería Bot
=========================================

10 E2E regression cases with strict product-identity checkers.

Pattern: each checker verifies WHAT product was returned — category-aware
assertions and explicit NO-MATCH guards — NOT merely whether a keyword
appears in the response.  Replaces tolerant keyword checkers that produced
false positives (e.g., 'destornillador' keyword passing when a cerradura
was actually returned).

Reference: bot_sales/tests/test_matcher_base.py (D5 pattern).
Consolidates demo_test_suite.py (31) + demo_test_suite_extended.py (53).
Historical cases documented in reports/suite_consolidation_2026-05-05.md.

Groups:
    anti_alucinacion (3):   S01-S03
    matcher_quirurgico (4): S04-S07
    cierre_venta (3):       S08-S10

Run:
    PYTHONPATH=. python3 scripts/demo_test_suite.py

Criteria:
    PASS  = strict assertions satisfied
    WARN  = works but suboptimal (do NOT tighten; document instead)
    FAIL  = strict assertion violated — do NOT soften the checker
    ERROR = unexpected runtime exception
"""

from __future__ import annotations

import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Status = Literal["PASS", "WARN", "FAIL", "ERROR"]


@dataclass
class TestResult:
    case_id: str
    category: str
    description: str
    inputs: list[str]
    expected_description: str
    actual_response: str
    status: Status
    notes: str
    duration_seconds: float


def _extract_prices(text: str) -> list[int]:
    """Extract Argentine-format prices ($1.234.567) from bot response."""
    prices = []
    for m in re.finditer(r'\$[\d\.]+', text):
        raw = m.group(0).replace('$', '').replace('.', '')
        try:
            v = int(raw)
            if v > 0:
                prices.append(v)
        except ValueError:
            pass
    return prices


def _has_no_match(text: str) -> bool:
    kws = (
        "no tenemos", "no contamos", "no disponemos", "no tengo",
        "no lo tenemos", "no hay", "no existe", "no encontré", "no lo encontré",
    )
    return any(k in text.lower() for k in kws)


# ---------------------------------------------------------------------------
# Product-identity guards — strict NO-MATCH assertions
# Mirrors bot_sales/tests/test_matcher_base.py (D5 pattern) for E2E responses.
# Each function detects a known false positive by examining the bot's free-text
# response rather than the underlying product list.
# ---------------------------------------------------------------------------

def _has_cerradura_false_positive(r: str) -> bool:
    """Detects 'Cerradura Cierre Gabinete Destornillador Para S9000 - Genrod'
    returned for screwdriver queries.

    This lock (Herramientas Manuales) mentions 'destornillador' because it
    requires one to open — it is NOT a screwdriver itself.
    Documented in test_matcher_base.py case 1, PENDIENTES.md Bug 1.
    """
    rl = r.lower()
    return "cerradura" in rl and "destornillador" in rl


def _has_bocallave_false_positive(r: str) -> bool:
    """Detects 'Bocallave Destornillador 5.5 mm Encastre 1/4 - Bahco' returned
    for screwdriver or mecha queries.

    A bocallave is a bit-holder in Mechas y Brocas — NOT a destornillador
    and NOT a drill bit (mecha/broca).
    """
    return "bocallave" in r.lower()


def _has_acople_false_positive(r: str) -> bool:
    """Detects 'Acople para Broca 8" Rosca UNC 1.1/4" - Aliafor' returned for
    mecha/broca queries.

    An acople is a fitting adapter in Mechas y Brocas — NOT a drill bit.
    Bug 1: 'broca' token hits 'Acople para Broca' via OR-any matching.
    """
    return bool(re.search(r'acople\b', r, re.I))


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

class StrictRegressionSuite:
    def __init__(self):
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant
        from bot_sales.ferreteria_unresolved_log import suppress_unresolved_logging
        tenant = get_runtime_tenant("ferreteria")
        self.bot = get_runtime_bot(tenant.id)
        self.suppress = suppress_unresolved_logging
        self.run_id = uuid.uuid4().hex[:8]
        self.results: list[TestResult] = []

    def _sid(self, case_id: str) -> str:
        # Each case gets a unique session: strict_<case_id>_<run_id>.
        # run_id is random per suite instantiation → no state bleed between
        # cases, even for multi-turn sessions (S08, S09, S10).
        # No explicit teardown needed.
        return f"strict_{case_id}_{self.run_id}"

    def _send(self, session_id: str, messages: list[str]) -> list[str]:
        responses = []
        with self.suppress():
            for msg in messages:
                responses.append(self.bot.process_message(session_id, msg))
        return responses

    def _run_case(
        self,
        case_id: str,
        category: str,
        description: str,
        inputs: list[str],
        expected_description: str,
        checker,
    ) -> TestResult:
        t0 = time.perf_counter()
        try:
            responses = self._send(self._sid(case_id), inputs)
            status, notes = checker(responses)
        except Exception as exc:
            responses = [f"EXCEPTION: {exc}"]
            status, notes = "ERROR", str(exc)
        duration = time.perf_counter() - t0
        result = TestResult(
            case_id=case_id, category=category, description=description,
            inputs=inputs, expected_description=expected_description,
            actual_response=responses[-1][:300] if responses else "",
            status=status, notes=notes, duration_seconds=round(duration, 2),
        )
        self.results.append(result)
        return result

    def _manual_multiturn(
        self,
        case_id: str,
        category: str,
        description: str,
        turns: list[str],
        expected_description: str,
        checker,
    ) -> TestResult:
        """Multi-turn variant: checker receives ALL intermediate responses."""
        sid = self._sid(case_id)
        t0 = time.perf_counter()
        try:
            responses: list[str] = []
            with self.suppress():
                for msg in turns:
                    responses.append(self.bot.process_message(sid, msg))
            status, notes = checker(responses)
        except Exception as exc:
            responses = [f"EXCEPTION: {exc}"]
            status, notes = "ERROR", str(exc)
        duration = time.perf_counter() - t0
        result = TestResult(
            case_id=case_id, category=category, description=description,
            inputs=turns, expected_description=expected_description,
            actual_response=responses[-1][:300] if responses else "",
            status=status, notes=notes, duration_seconds=round(duration, 2),
        )
        self.results.append(result)
        return result

    # ── GROUP 1: Anti-alucinación ─────────────────────────────────────────

    def case_S01_spec_blocker_martillo_absurdo(self):
        """C19 regression: '500 kg hammer' must be blocked by V1 spec validator.

        Catalog: Stanley hammers exist (Herramientas Manuales, max real ~1.5 kg).
        V1 rule: hammer weight > 10 kg → impossible spec → no products returned.

        If V1 is working: bot says 'no existe' and returns NO prices.
        If V1 is broken: bot returns Stanley hammers with real prices → FAIL.

        FAIL: any price returned for this query (spec not blocked).
        PASS: no prices returned (spec blocked, with or without explicit message).
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)

            # FAIL: returned products with price — V1 spec blocker not working
            if prices:
                return "FAIL", f"spec imposible no bloqueada — precios retornados: {prices[:3]}"

            # PASS: explicit rejection message (ideal UX — user knows why)
            if any(kw in rl for kw in (
                "no existe", "no tenemos", "no contamos", "no hay",
                "imposible", "500", "irreal", "fuera de rango",
                "especificación", "no lo tenemos", "no fabricamos",
            )):
                return "PASS", "rechazó spec imposible explícitamente, sin precios"

            # WARN: V1 blocked silently (no prices, no explanation) — anti-
            # alucinación cumplida pero UX pobre (vendedor no explica el rechazo)
            return "WARN", "spec bloqueada sin mensaje explícito — V1 funcionó pero sin explicación al usuario"

        return self._run_case(
            "S01", "anti_alucinacion",
            '"martillo Stanley dorado 500kg" → V1 bloquea, sin productos',
            ["tienen martillos Stanley dorados de 500kg?"],
            "spec imposible rechazada — cero precios retornados",
            check,
        )

    def case_S02_sku_falso_aaaaa(self):
        """C20 regression: fake SKU 'AAAAA' must NOT generate invented products.

        AAAAA does not exist in catalog. Bot must acknowledge absence.

        FAIL: prices returned AND 'aaaaa' mentioned (hallucinated product).
        FAIL: prices returned without any denial of AAAAA existence.
        PASS: explicit no-match response.
        WARN: evasive — neither confirms nor denies.
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)

            # FAIL: hallucinated price for the non-existent SKU itself
            if prices and "aaaaa" in rl:
                return "FAIL", f"inventó precio para SKU AAAAA: {prices[:2]}"

            # FAIL: returned products without acknowledging AAAAA doesn't exist
            if prices and not _has_no_match(r):
                return "FAIL", f"retornó productos sin decir que AAAAA no existe: {prices[:2]}"

            # WARN: recognized absence but also offered unrelated products without
            # context — a human vendedor would ask 'qué estabas buscando?' first
            if _has_no_match(r) and prices:
                return "WARN", (
                    "reconoció que AAAAA no existe + ofreció productos sin pedir contexto "
                    "(UX subóptima — sin saber qué busca el cliente, los productos son ruido)"
                )

            # PASS: explicit denial, no unsolicited products
            if _has_no_match(r):
                return "PASS", "indicó correctamente que el producto no existe"

            return "WARN", "respuesta evasiva — no confirma ni niega que AAAAA no existe"

        return self._run_case(
            "S02", "anti_alucinacion",
            '"100 unidades del producto AAAAA" → SKU inexistente, no inventar',
            ["dame 100 unidades del producto AAAAA"],
            "decir que el producto no existe, sin inventar precios",
            check,
        )

    def case_S03_ppr_sin_precio_inventado(self):
        """E09: PP-R termofusión not in catalog — bot must NOT invent a price for it.

        Query co-exists with real catalog items (llaves esféricas, sellador,
        cinta teflón). Prices for those items ARE legitimate — do NOT fail on them.

        FAIL: price directly associated with PP-R/termofusión WITHOUT a prior
              disclaimer (pattern: 'termofusión ... $X' in same context block).
        PASS: bot explicitly disclaims PP-R absence + shows prices for available items.
        WARN: prices present but PP-R status ambiguous.
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)

            mentions_ppr = "pp-r" in rl or "pp r" in rl or "termofusi" in rl

            # PP-R-specific disclaimer — only fires when PP-R or termofusión is
            # explicitly denied. Generic "no tenemos" is intentionally excluded to
            # avoid false-PASS when the bot denies something else in the same turn.
            #
            # Patterns covered:
            #   "no tenemos PP-R"          "no manejamos PP-R"
            #   "no contamos con PP-R"     "PP-R no lo tenemos"
            #   "no tenemos termofusión"   "no manejamos termofusión"
            #   "termofusión no disponible" "no contamos con termofusión"
            _ppr_disclaimer_re = [
                r'no\s+(tenemos|contamos con|hay|manejamos)\s+(ca[ñn]os?\s+)?pp.?r',
                r'pp.?r.{0,40}no\s+(lo\s+)?(tenemos|hay|contamos|manejamos)',
                r'no\s+(tenemos|contamos con|hay|manejamos)\s+(ca[ñn]os?\s+)?termofusi[oó]n',
                r'termofusi[oó]n.{0,40}no\s+(la\s+)?(tenemos|hay|contamos|manejamos)',
                r'no\s+(manejamos|trabajamos con)\s+termofusi[oó]n',
                r'termofusi[oó]n\s*no\s*.{0,30}disponible',
            ]
            has_disclaimer = any(re.search(p, rl) for p in _ppr_disclaimer_re)

            has_alternatives = any(kw in rl for kw in (
                "llave", "sellador", "teflón", "teflon", "cinta",
            ))

            # If disclaimer is present, prices are for OTHER items — not hallucinated PP-R
            if has_disclaimer and mentions_ppr and has_alternatives and prices:
                return "PASS", "informó ausencia de PP-R + precios de ítems disponibles"
            if has_disclaimer and has_alternatives:
                return "PASS", "informó ausencia de PP-R + ofreció ítems disponibles"
            if has_disclaimer and prices:
                return "PASS", "disclaimer de ausencia + precios de ítems disponibles"
            if has_disclaimer:
                return "WARN", "informó ausencia de PP-R pero no ofreció alternativas disponibles"

            # No disclaimer — now check if PP-R itself appears near a price (hallucination)
            # Pattern: 'termofusión ... $X' within ~100 chars (same paragraph/line)
            ppr_priced = bool(re.search(
                r'(termofusi[oó]n|pp.?r).{0,100}\$[\d\.]+',
                r, re.I,
            ))
            if ppr_priced:
                return "FAIL", "bot asoció precio a PP-R/termofusión sin disclaimer de ausencia"

            if prices and mentions_ppr:
                return "WARN", (
                    "precios sin disclaimer de PP-R — "
                    "verificar si corresponden a ítems co-existentes"
                )
            if prices:
                return "WARN", "muestra precios pero no menciona PP-R explícitamente"

            return "WARN", "respuesta ambigua sobre termofusión PP-R"

        return self._run_case(
            "S03", "anti_alucinacion",
            '"obra baño: termofusión PP-R + llaves + sellador + teflón" → no inventar precio PP-R',
            ["obra completa para baño: termofusión 20mm + accesorios, llaves esféricas, sellador, cinta teflón"],
            "aclarar ausencia de PP-R, mostrar precios de ítems disponibles, $0 para PP-R nunca",
            check,
        )

    # ── GROUP 2: Matcher quirúrgico ───────────────────────────────────────

    def case_S04_destornillador_philips_strict(self):
        """Strict matcher: 'destornillador philips' must return ONLY actual screwdrivers.

        Known false positives in catalog:
          - 'Cerradura Cierre Gabinete Destornillador Para S9000 - Genrod'
            (Herramientas Manuales) — lock that needs a screwdriver, NOT a screwdriver
          - 'Bocallave Destornillador 5.5 mm Encastre 1/4 - Bahco'
            (Mechas y Brocas) — bit-holder, NOT a destornillador

        Correct products: 'Destornillador 1000 v Phillips PH1 75 mm - Stanley',
        'Destornillador 1000 v Phillips PH3 100 mm - Stanley', Bahco sets.

        FAIL: any known false positive appears in response.
        PASS: destornillador + Phillips indicator, no false positives.
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()

            # FAIL guard 1: cerradura false positive
            if _has_cerradura_false_positive(r):
                return "FAIL", (
                    "cerradura retornada como destornillador — "
                    "'Cerradura Cierre Gabinete Destornillador Para S9000'"
                )
            # FAIL guard 2: bocallave false positive
            if _has_bocallave_false_positive(r):
                return "FAIL", (
                    "bocallave retornado como destornillador — "
                    "'Bocallave Destornillador 5.5 mm - Bahco' no es un destornillador"
                )
            # FAIL guard 3: adaptador without destornillador
            if "adaptador" in rl and "destornillador" not in rl:
                return "FAIL", "adaptador retornado sin destornillador"

            has_destornillador = "destornillador" in rl
            has_philips = any(kw in rl for kw in (
                "philips", "phillips", "ph1", "ph2", "ph3", "punta",
            ))

            if has_destornillador and has_philips:
                return "PASS", "destornillador Phillips real, sin falsos positivos"
            if has_destornillador:
                return "WARN", "destornillador encontrado sin indicador Philips/PH"
            return "FAIL", "no retornó destornilladores"

        return self._run_case(
            "S04", "matcher_quirurgico",
            '"destornillador philips" → real (Stanley PH1/PH3), NO cerraduras/bocallaves',
            ["destornillador philips"],
            "destornillador Phillips (Stanley/Bahco), cero falsos positivos",
            check,
        )

    def case_S05_mechas_8mm_bosch(self):
        """C13: '5 mechas de 8mm Bosch' — real 8mm drill bit, NOT acoples or bocallaves.

        NOTE: Bosch has NO individual 8mm mechas in catalog (only Broca Anular PRO
        TCT 14-22mm). Correct bot behaviors:
          Option A: return 8mm brocas from other brands (Ezeta, Rubi) → PASS
          Option B: clarify no Bosch 8mm + offer alternatives → PASS
          Option C: ask material clarification (madera/metal/concreto) → PASS

        Known false positives for this query (Mechas y Brocas):
          - 'Acople para Broca 8" Rosca UNC 1.1/4" - Aliafor' (fitting, NOT drill bit)
          - 'Bocallave Destornillador 5.5 mm - Bahco' (bit-holder, NOT drill bit)
          - 'Mecha Centradora' as generic substitute (guide bit, NOT an 8mm drill)

        FAIL: acople, bocallave, or mecha centradora returned as substitute.
        PASS: real 8mm broca/mecha, brand clarification, or material clarification.
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()

            # FAIL guard 1: acople false positive
            if _has_acople_false_positive(r):
                return "FAIL", (
                    "acople retornado como mecha — "
                    "'Acople para Broca 8' no es una broca"
                )
            # FAIL guard 2: bocallave false positive
            if _has_bocallave_false_positive(r):
                return "FAIL", "bocallave retornado — bit-holder no es una mecha de 8mm"
            # FAIL guard 3: mecha centradora as generic substitute
            if "centradora" in rl:
                return "FAIL", (
                    "mecha centradora retornada como sustituto — "
                    "guía de centrado no equivale a broca de 8mm"
                )

            has_mecha_broca = "mecha" in rl or "broca" in rl
            has_8mm = bool(re.search(r'\b8\s*mm\b|\b8mm\b', rl))

            # PASS: real 8mm drill bit from any brand
            if has_mecha_broca and has_8mm:
                return "PASS", "mecha/broca 8mm real retornada, sin falsos positivos"
            # PASS: bot clarifies no Bosch 8mm + offers alternatives
            if has_mecha_broca and _has_no_match(r) and "bosch" in rl:
                return "PASS", "informó ausencia de Bosch 8mm + ofreció alternativas"
            # PASS: material clarification (valid disambiguation)
            if has_mecha_broca and any(kw in rl for kw in (
                "madera", "metal", "concreto", "hormigón", "material", "tipo",
            )):
                return "PASS", "pidió clarificación de material — comportamiento correcto"
            if has_mecha_broca:
                return "WARN", "mecha/broca encontrada sin confirmar 8mm específicamente"
            return "FAIL", "no retornó mechas ni brocas"

        return self._run_case(
            "S05", "matcher_quirurgico",
            '"5 mechas 8mm Bosch" → broca 8mm real (Ezeta/Rubi), NO acoples/bocallaves',
            ["5 mechas de 8mm Bosch"],
            "mecha/broca 8mm real o clarificación, sin acoples ni bocallaves",
            check,
        )

    def case_S06_mecha_8mm_para_taladro(self):
        """C29 Q3 regression: 'mecha 8mm para taladro' must return actual drill bits.

        Q3 added synonym 'dest' and _families_without_para_context(). Regression guard:
        if scoring breaks, 'mecha' can match bocallaves/acoples in Mechas y Brocas.

        Real products: 'Broca Acero Rapido acero rapido 8 mm - Ezeta',
                       'Broca 8 mm para Porcelanico Corte Humedo - Rubi'.

        FAIL: bocallave, acople, or adaptador-only returned (Q3 regression).
        PASS: real 8mm broca/mecha or material clarification.
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()

            # FAIL guard 1: bocallave false positive (Q3 regression indicator)
            if _has_bocallave_false_positive(r):
                return "FAIL", (
                    "Q3 REGRESSION — bocallave retornado: "
                    "'Bocallave Destornillador 5.5mm' no es mecha para taladro"
                )
            # FAIL guard 2: acople false positive (Q3 regression indicator)
            if _has_acople_false_positive(r):
                return "FAIL", (
                    "Q3 REGRESSION — acople retornado: "
                    "'Acople para Broca' no es mecha para taladro"
                )
            # FAIL guard 3: adaptador without any mecha/broca
            if "adaptador" in rl and not ("mecha" in rl or "broca" in rl):
                return "FAIL", "adaptador retornado sin mecha/broca"

            has_mecha_broca = "mecha" in rl or "broca" in rl
            has_8mm = bool(re.search(r'\b8\s*mm\b|\b8mm\b', rl))

            if has_mecha_broca and has_8mm:
                return "PASS", "mecha/broca 8mm real — Q3 regression no presente"
            # PASS: material clarification (valid)
            if has_mecha_broca and any(kw in rl for kw in (
                "madera", "metal", "concreto", "material", "tipo",
            )):
                return "PASS", "pidió clarificación de material — comportamiento correcto"
            if has_mecha_broca:
                return "WARN", "mecha/broca encontrada sin confirmar 8mm"
            return "FAIL", "no retornó mechas ni brocas"

        return self._run_case(
            "S06", "matcher_quirurgico",
            '"mecha 8mm para taladro" → broca real, NO bocallave/acople (Q3 regression)',
            ["necesito una mecha de 8 mm para taladro"],
            "mecha/broca 8mm real (Ezeta/Rubi), sin bocallaves ni acoples",
            check,
        )

    def case_S07_llave_francesa_strict(self):
        """C12 A2/B1 regression: 'llave francesa' must return actual adjustable wrenches.

        Catalog correct products:
          General:             'Llave francesa 10" satinada - Davidson',
                               'Llave Francesa Ajustable 10" - Irimo'
          Herramientas Manuales: 'Llave Ajustable 10" - Milwaukee',
                               'Llave Ajustable 12" - Bahco'

        Known false positive (test_matcher_base case 4):
          'Adaptador 3/8 para Llaves Combinadas Ratchet - Bahco'
          OR-any 'de' token matches almost the entire catalog.

        FAIL: adaptador returned without any actual llave francesa.
        PASS: llave francesa or ajustable found, no false positives.
        """
        def check(rs):
            r = rs[-1]
            rl = r.lower()

            # FAIL guard 1: specific known false positive (test_matcher_base case 4)
            if "adaptador 3/8" in rl:
                return "FAIL", (
                    "falso positivo A2/B1: 'Adaptador 3/8 para Llaves Combinadas' — "
                    "no es llave francesa"
                )
            # FAIL guard 2: adaptador without llave
            if "adaptador" in rl and "llave" not in rl:
                return "FAIL", "adaptador retornado sin llaves francesas"

            has_llave_francesa = "llave francesa" in rl
            has_llave_ajustable = "llave" in rl and any(kw in rl for kw in (
                "ajustable", "satinada",
            ))
            has_known_brand = any(kw in rl for kw in (
                "davidson", "irimo", "milwaukee", "wembley", "bahco",
            ))

            if has_llave_francesa or has_llave_ajustable:
                return "PASS", "llave francesa/ajustable real — A2/B1 regression no presente"
            if has_known_brand and "llave" in rl:
                return "PASS", "llave de marca conocida retornada"
            if "llave" in rl:
                return "WARN", "llave encontrada sin confirmar que es francesa/ajustable"
            return "FAIL", "no retornó llaves francesas"

        return self._run_case(
            "S07", "matcher_quirurgico",
            '"llave francesa" → real (Davidson/Irimo/Bahco), NO adaptadores (A2/B1)',
            ["tienen llave francesa?"],
            "llave francesa o ajustable real, sin adaptadores",
            check,
        )

    # ── GROUP 3: Cierre de venta ──────────────────────────────────────────

    def case_S08_e41_multiturno_5_turnos(self):
        """E41: 5-turn sequence must show both products in final presupuesto.

        Known bug: session reset can occur at turn 5, wiping active_quote.
        If this FAIL is idempotent across runs → document as Bloque 3 bug confirmed.
        If non-deterministic → flag in report; consider Opcion A (skip + marker).

        Turns:
            T1: 'destornillador philips'  → bot offers options
            T2: 'cualquiera está bien'    → selects destornillador
            T3: 'agregame martillo'       → bot offers martillo options
            T4: 'stanley'                 → selects Stanley martillo
            T5: 'presupuesto?'            → bot shows cart summary

        FAIL: T5 missing 'destornillador' or 'martillo' (session reset).
        FAIL: cerradura false positive in any turn.
        PASS: T5 has both products + prices.
        """
        turns = [
            "destornillador philips",
            "cualquiera está bien",
            "agregame martillo",
            "stanley",
            "presupuesto?",
        ]

        def check(rs):
            # Guard: cerradura false positive in any turn
            for i, r in enumerate(rs):
                if _has_cerradura_false_positive(r):
                    return "FAIL", (
                        f"turno {i + 1}: cerradura retornada como destornillador "
                        "(falso positivo — ver S04)"
                    )

            r5 = rs[-1]
            r5l = r5.lower()
            prices = _extract_prices(r5)

            has_destornillador = "destornillador" in r5l
            has_martillo = "martillo" in r5l

            if not has_destornillador and not has_martillo:
                return "FAIL", (
                    "E41 FAIL — turno 5 vacío (session reset bug, Bloque 3): "
                    "carrito perdió ambos ítems"
                )
            if not has_destornillador:
                return "FAIL", "E41 FAIL — turno 5: destornillador perdido del carrito (session reset)"
            if not has_martillo:
                return "FAIL", "E41 FAIL — turno 5: martillo no aparece en presupuesto"

            if prices:
                return "PASS", (
                    f"turno 5: destornillador + martillo + precios (max=${max(prices):,})"
                )
            return "WARN", "turno 5: ambos productos presentes pero sin precios"

        return self._manual_multiturn(
            "S08", "cierre_venta",
            "E41: 5 turnos dest→cualquiera→martillo→stanley→presupuesto (session reset)",
            turns,
            "turno 5 muestra destornillador + martillo + precios, sin session reset",
            check,
        )

    def case_S09_multiturn_stock_consistency(self):
        """Multi-item stock consistency: total must NOT report 'no disponible'.

        Bug documented in EOD 2026-05-04: bot says 'no disponible' or 'sin stock'
        during total calculation even when stock was 999 in the same session.
        Active_quote loses stock state between turns.

        Ordinal language ('el primero') is natural WhatsApp style.
        Checker does NOT depend on which specific product was chosen — it validates
        the final state only: no availability error + valid total price.

        Turns:
            T1: 'necesito un destornillador philips'
            T2: 'dame el primero. agregame también un martillo'
            T3: 'el primero'
            T4: 'cuál es el total?'

        FAIL: T4 contains 'no disponible' or 'sin stock' (stock hallucination bug).
        FAIL: T4 has no prices (failed to compute total).
        PASS: T4 shows prices > 0 + both product types, no availability errors.
        """
        turns = [
            "necesito un destornillador philips",
            "dame el primero. agregame también un martillo",
            "el primero",
            "cuál es el total?",
        ]

        def check(rs):
            # Guard: cerradura false positive in any turn
            for i, r in enumerate(rs):
                if _has_cerradura_false_positive(r):
                    return "FAIL", (
                        f"turno {i + 1}: cerradura retornada como destornillador"
                    )

            # ── T2 compound-message handling check ────────────────────────
            # T2 = "dame el primero. agregame también un martillo"
            # Two commands in one message: (1) select destornillador, (2) add martillo.
            # Check for evidence of parser failure before validating the final total.
            r2l = rs[1].lower()

            # Parser split: 'el primero' or 'primero' appearing as a list item
            # (bullet/emoji/dash/arrow) means the parser treated ordinal as a product.
            parser_split_t2 = bool(re.search(
                r'[•\-\*✅❓►]\s*(?:\d+\s*[×xX]?\s*)?(?:el\s+)?primero\b',
                rs[1], re.I,
            ))
            # Bot confused 'primero' as a product name
            primero_confused_t2 = any(kw in r2l for kw in (
                "no encontré el primero", "no tenemos primero", "el primero no",
                "primero no existe",
            ))
            if parser_split_t2 or primero_confused_t2:
                return "FAIL", (
                    "PARSER BUG — T2: 'el primero' spliteado como ítem del pedido "
                    "(mensaje compuesto no procesado correctamente)"
                )

            # Basic progress check: did the bot at least show martillo options in T2?
            has_martillo_t2 = "martillo" in r2l
            if not has_martillo_t2:
                return "FAIL", (
                    "PARSER BUG — T2: bot no procesó 'agregame también un martillo' "
                    "(mensaje compuesto ignorado — no avanzó a selección de martillo)"
                )

            # ── T4 stock consistency check ─────────────────────────────────
            r4 = rs[-1]
            r4l = r4.lower()
            prices = _extract_prices(r4)

            # FAIL: stock hallucination on previously confirmed items
            # (distinct from parser bug — stock was confirmed in earlier turns)
            if "no disponible" in r4l:
                return "FAIL", (
                    "STOCK BUG — T4: 'no disponible' para ítems previamente en carrito "
                    "(stock=999 alucinado como sin stock — no es bug de parser)"
                )
            if "sin stock" in r4l:
                return "FAIL", (
                    "STOCK BUG — T4: 'sin stock' para ítems previamente confirmados "
                    "(active_quote perdió estado de stock entre turnos)"
                )

            # FAIL: no prices (can't compute total)
            if not prices:
                return "FAIL", "T4: sin precios — no pudo calcular total"
            total = max(prices)
            if total == 0:
                return "FAIL", "T4: total = $0 — alucinación de precio cero"

            has_dest = "destornillador" in r4l
            has_mart = "martillo" in r4l

            if has_dest and has_mart:
                return "PASS", f"T4: destornillador + martillo en total, precio=${total:,}"
            if has_dest or has_mart:
                found = "destornillador" if has_dest else "martillo"
                return "WARN", f"T4: solo {found} en total — ¿se perdió el otro ítem?"
            # Has prices but products not named in summary (compact format)
            return "WARN", f"T4: precios presentes (${total:,}) pero productos no identificados en resumen"

        return self._manual_multiturn(
            "S09", "cierre_venta",
            "multi-item stock: 'total?' NO dice 'no disponible' (stock hallucination bug)",
            turns,
            "turno 4: total real (>$0), sin 'no disponible' ni 'sin stock'",
            check,
        )

    def case_S10_parser_conectores(self):
        """Parser connector: 'dale' must NOT be split as a separate product item.

        Flow:
            T1: 'che, tenés taladros?' → V9 ambiguity clarification or taladro list
            T2: 'dale, mostrame los Bosch' → continuation signal + brand filter

        Bug to detect: multi-item parser treats 'dale' (conversational connector)
        as a product name and adds it to the pending item list.

        FAIL: T2 response shows 'dale' in a list-item position (bullet/emoji/dash/arrow).
        FAIL: bot asks 'qué es dale?' or 'no encontré dale' (confused 'dale' as product).
        PASS: T2 shows Bosch taladros OR asks about Bosch models (understood continuation).
        WARN: T2 shows taladros without Bosch filter (connector understood but brand ignored).
        """
        turns = [
            "che, tenés taladros?",
            "dale, mostrame los Bosch",
        ]

        def check(rs):
            r2 = rs[-1]
            r2l = r2.lower()

            # FAIL guard 1: 'dale' in a list-item position (parser split connector)
            dale_as_item = bool(re.search(
                r'[•\-\*✅❓]\s*(?:\d+\s*[×xX]?\s*)?dale\b', r2, re.I,
            ))
            dale_as_item = dale_as_item or bool(re.search(
                r'(?:—|→|>)\s*dale\b', r2, re.I,
            ))
            dale_as_item = dale_as_item or bool(re.search(
                r'^\s*dale\s*[:$]', r2, re.I | re.MULTILINE,
            ))
            if dale_as_item:
                return "FAIL", "parser spliteó 'dale' como ítem del pedido"

            # FAIL guard 2: bot confused 'dale' as a product name
            if any(kw in r2l for kw in (
                "qué es dale", "no encontré dale", "dale no está",
                "no tenemos dale", "el producto dale",
            )):
                return "FAIL", "bot interpretó 'dale' como nombre de producto"

            has_taladro = "taladro" in r2l
            has_bosch = "bosch" in r2l

            # PASS: shows Bosch taladros (understood connector + brand)
            if has_taladro and has_bosch:
                return "PASS", "mostró taladros Bosch — 'dale' interpretado como conector"
            # PASS: asks about Bosch model (understood context, clarifying)
            if has_bosch:
                return "PASS", "preguntó sobre modelo Bosch — continuación entendida"
            if has_taladro:
                return "WARN", "mostró taladros sin filtro Bosch (conector OK, marca ignorada)"
            # WARN: V9 re-fired clarification (didn't understand continuation)
            if any(kw in r2l for kw in (
                "qué tipo", "qué marca", "percutor", "batería", "aclarar",
            )):
                return "WARN", "T2 repitió clarificación — no entendió 'dale Bosch' como continuación"
            return "WARN", "T2 ambiguo — sin taladros Bosch ni clarificación de continuación"

        return self._manual_multiturn(
            "S10", "cierre_venta",
            '"dale, mostrame los Bosch" → NO splitear "dale" como ítem del pedido',
            turns,
            "turno 2 muestra taladros Bosch o pregunta Bosch, sin 'dale' como ítem",
            check,
        )

    # ── Report ────────────────────────────────────────────────────────────

    def _print_report(self):
        icons = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "ERROR": "💥"}
        totals = {s: 0 for s in icons}
        by_cat: dict[str, list[TestResult]] = {}

        for r in self.results:
            totals[r.status] += 1
            by_cat.setdefault(r.category, []).append(r)

        total = len(self.results)
        total_time = sum(r.duration_seconds for r in self.results)

        print("=" * 80)
        print("STRICT REGRESSION SUITE — FERRETERÍA BOT")
        print("=" * 80)

        print(f"\n{'ID':<4} {'ST':<5} {'CATEGORÍA':<22} {'DESCRIPCIÓN':<38} NOTAS")
        print("-" * 115)
        for r in self.results:
            icon = icons[r.status]
            desc = r.description[:37]
            notes = r.notes[:48]
            print(f"{r.case_id:<4} {icon} {r.status:<3} {r.category:<22} {desc:<38} {notes}")

        non_pass = {
            cat: rs for cat, rs in by_cat.items()
            if any(r.status in ("FAIL", "WARN", "ERROR") for r in rs)
        }
        if non_pass:
            print(f"\n{'─' * 80}")
            print("BUGS / WARNINGS BY CATEGORY:")
            for cat, results in sorted(non_pass.items()):
                fails  = [r for r in results if r.status == "FAIL"]
                warns  = [r for r in results if r.status == "WARN"]
                errors = [r for r in results if r.status == "ERROR"]
                if not (fails or warns or errors):
                    continue
                print(f"\n  [{cat.upper()}]")
                for r in errors:
                    print(f"    💥 {r.case_id}: {r.description[:70]}")
                    print(f"       → {r.notes}")
                for r in fails:
                    print(f"    ❌ {r.case_id}: {r.description[:70]}")
                    print(f"       → {r.notes}")
                    print(f"       last response: {r.actual_response[:150]}")
                for r in warns:
                    print(f"    ⚠️  {r.case_id}: {r.description[:70]}")
                    print(f"       → {r.notes}")

        pct = lambda n: f"{n / total * 100:.0f}%" if total else "0%"
        print(f"\n{'─' * 80}")
        print("SUMMARY")
        print(f"  Total cases : {total}")
        print(f"  ✅ PASS     : {totals['PASS']} ({pct(totals['PASS'])})")
        print(f"  ⚠️  WARN     : {totals['WARN']} ({pct(totals['WARN'])})")
        print(f"  ❌ FAIL     : {totals['FAIL']} ({pct(totals['FAIL'])})")
        print(f"  💥 ERROR    : {totals['ERROR']} ({pct(totals['ERROR'])})")
        print(f"  Total time  : {total_time:.1f}s")
        print("=" * 80)

    def run_all(self) -> int:
        icons = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "ERROR": "💥"}
        cases = sorted(
            [getattr(self, n) for n in dir(self) if n.startswith("case_")],
            key=lambda f: f.__name__,
        )
        print(f"Corriendo {len(cases)} casos — run_id={self.run_id}\n")
        for case_fn in cases:
            result = case_fn()
            icon = icons[result.status]
            print(
                f"  {icon} [{result.case_id}] {result.description[:60]:<60} "
                f"({result.duration_seconds}s)"
            )
        print()
        self._print_report()
        self.bot.close()
        fails = sum(1 for r in self.results if r.status in ("FAIL", "ERROR"))
        return 1 if fails > 0 else 0


if __name__ == "__main__":
    suite = StrictRegressionSuite()
    raise SystemExit(suite.run_all())
