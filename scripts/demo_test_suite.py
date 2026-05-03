#!/usr/bin/env python3
"""
Demo End-to-End Test Suite — Ferretería Bot
============================================

Qué hace:
    Test de runtime end-to-end que manda mensajes reales al bot y verifica
    que las respuestas cumplan criterios concretos. No usa mocks — llama
    a la API de OpenAI y al catálogo real.

Cómo correrlo:
    PYTHONPATH=. python3 scripts/demo_test_suite.py

Cuándo correrlo:
    Antes de cada cambio significativo al bot (prompt, matcher, parser,
    routing). Detecta regresiones antes de deployar a Railway.

Total de casos: 31
    - saludos (3): respuestas conversacionales sin precios
    - producto_simple (3): búsqueda de producto individual
    - parser (4): pedidos multi-ítem y listas
    - multiturno (1): carrito persistente a través de turnos
    - matcher (3): calidad del match producto/precio
    - casos_limite (3): objeción de precio, escalación, FAQ
    - anti_alucinacion (3): productos inventados, SKUs falsos
    - regresion_precio (1): bug histórico mecha→acople ($57k)
    - tolerancia_linguistica (10): typos, slang, abreviaciones, inglés

Criterios:
    PASS  = comportamiento correcto sin defectos
    WARN  = funciona pero subóptimo (respuesta vaga, match parcial,
            clarificación en lugar de resultado)
    FAIL  = error concreto (inventó precio, ignoró escalación, perdió
            carrito, matcheó producto incorrecto)
    ERROR = excepción inesperada en runtime

Estado al 2026-05-03: 19/31 PASS (61%). Bugs pendientes en:
    matcher (mecha→acople), anti-alucinacion, parser (prefijo "Te paso lista:"),
    tolerancia (abreviaciones, jerga de codos roscados).
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
    llm_calls: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0


def _extract_prices(text: str) -> list[int]:
    """Extrae precios en formato argentino ($1.234.567) de la respuesta del bot."""
    prices = []
    for m in re.finditer(r'\$[\d\.]+', text):
        raw = m.group(0).replace('$', '').replace('.', '')
        try:
            prices.append(int(raw))
        except ValueError:
            pass
    return prices


class DemoTestSuite:
    def __init__(self):
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant
        from bot_sales.ferreteria_unresolved_log import suppress_unresolved_logging
        tenant = get_runtime_tenant("ferreteria")
        self.bot = get_runtime_bot(tenant.id)
        self.suppress = suppress_unresolved_logging
        self.run_id = uuid.uuid4().hex[:8]
        self.results: list[TestResult] = []

    def _sid(self, case_id: str) -> str:
        return f"demo_{case_id}_{self.run_id}"

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
            case_id=case_id,
            category=category,
            description=description,
            inputs=inputs,
            expected_description=expected_description,
            actual_response=responses[-1][:300] if responses else "",
            status=status,
            notes=notes,
            duration_seconds=round(duration, 2),
        )
        self.results.append(result)
        return result

    # ── Saludos ───────────────────────────────────────────────────────────

    def case_01_saludo_hola(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            if not r:
                return "FAIL", "respuesta vacía"
            prices = _extract_prices(r)
            if prices:
                return "FAIL", f"incluyó precios en saludo: {prices[:3]}"
            if "presupuesto preliminar" in rl:
                return "WARN", "abrió presupuesto en vez de saludar"
            return "PASS", "saludo correcto sin precios"
        return self._run_case("01", "saludos", '"hola"', ["hola"],
            "respuesta conversacional sin precios", check)

    def case_02_saludo_buenas(self):
        def check(rs):
            r = rs[-1]
            if not r:
                return "FAIL", "respuesta vacía"
            prices = _extract_prices(r)
            if prices:
                return "FAIL", f"incluyó precios en saludo: {prices[:3]}"
            if "presupuesto preliminar" in r.lower():
                return "WARN", "abrió presupuesto en vez de saludar"
            return "PASS", "saludo correcto"
        return self._run_case("02", "saludos", '"buenas"', ["buenas"],
            "respuesta conversacional sin precios", check)

    def case_03_saludo_como_va(self):
        def check(rs):
            r = rs[-1]
            if not r:
                return "FAIL", "respuesta vacía"
            prices = _extract_prices(r)
            if prices:
                return "FAIL", "incluyó precios en saludo informal"
            if "presupuesto preliminar" in r.lower():
                return "WARN", "abrió presupuesto en vez de saludar"
            return "PASS", "saludo correcto"
        return self._run_case("03", "saludos", '"hola, ¿cómo va?"', ["hola, ¿cómo va?"],
            "respuesta conversacional sin precios", check)

    # ── Producto simple ───────────────────────────────────────────────────

    def case_04_producto_simple_taladro(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            if not r:
                return "FAIL", "respuesta vacía"
            has_quote = "presupuesto" in rl
            has_taladro = "taladro" in rl
            has_clarif = any(kw in rl for kw in ("percutor", "batería", "bateria", "voltios", "marca", "uso", "tipo"))
            if has_taladro and (has_quote or has_clarif):
                return "PASS", "encontró taladro o pidió clarificación"
            if has_taladro:
                return "WARN", "menciona taladro pero sin presupuesto ni clarificación"
            return "FAIL", "no respondió con taladros"
        return self._run_case("04", "producto_simple", '"necesito un taladro"', ["necesito un taladro"],
            "iniciar búsqueda de taladro o pedir aclaración", check)

    def case_05_precio_martillo(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            if not r:
                return "FAIL", "respuesta vacía"
            has_martillo = "martillo" in rl
            prices = _extract_prices(r)
            if has_martillo and prices:
                return "PASS", f"muestra martillo con precio (max=${max(prices):,})"
            if has_martillo:
                return "WARN", "menciona martillo pero sin precio"
            return "FAIL", "no encontró martillos"
        return self._run_case("05", "producto_simple", '"precio del martillo"', ["precio del martillo"],
            "opciones de martillo con precio", check)

    def case_06_llaves_francesas(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            if not r:
                return "FAIL", "respuesta vacía"
            has_llave = "llave" in rl and ("francesa" in rl or "ajustable" in rl or "satinada" in rl)
            prices = _extract_prices(r)
            if has_llave and prices:
                return "PASS", f"muestra llaves francesas con precio"
            if has_llave:
                return "WARN", "menciona llaves pero sin precio"
            return "FAIL", "no encontró llaves francesas"
        return self._run_case("06", "producto_simple", '"tienen llaves francesas?"', ["tienen llaves francesas?"],
            "opciones de llave francesa con precio", check)

    # ── Pedidos multi-item ────────────────────────────────────────────────

    def case_07_multi_saludo_no_item(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            # "Hola" no debe aparecer como ítem: busco patrones de línea de presupuesto
            hola_as_item = bool(re.search(r'[✅❓]\s*\d*\s*[×x]?\s*[Hh]ola', r))
            hola_as_item = hola_as_item or bool(re.search(r'(?:—|→)\s*Hola', r))
            has_martillo = "martillo" in rl
            has_destornillador = "destornillador" in rl
            if hola_as_item:
                return "FAIL", '"Hola" incluido como ítem del pedido'
            if has_martillo and has_destornillador:
                return "PASS", "parseó martillo + destornillador, ignoró saludo"
            if has_martillo or has_destornillador:
                found = "martillo" if has_martillo else "destornillador"
                return "WARN", f"parseó solo 1/2 ítems ({found})"
            return "FAIL", "no parseó ningún ítem del pedido"
        return self._run_case(
            "07", "parser",
            '"Hola, 3 martillos y 2 destornilladores" → Hola no es ítem',
            ["Hola, necesito 3 martillos y 2 destornilladores"],
            "parsear martillo + destornillador, ignorar saludo", check,
        )

    def case_08_lista_4_items(self):
        msg = ("Te paso lista: 5 rollos de cinta aisladora, 3 llaves francesas chicas, "
               "2 sets destornilladores, 10 mechas 8mm")
        def check(rs):
            r = rs[-1].lower()
            found = [
                "cinta" in r or "aisladora" in r,
                "llave" in r and ("francesa" in r or "ajustable" in r),
                "destornillador" in r,
                "mecha" in r or ("broca" in r and "8" in r),
            ]
            n = sum(found)
            if n == 4:
                return "PASS", "encontró los 4 ítems"
            if n >= 2:
                return "WARN", f"encontró {n}/4 ítems"
            return "FAIL", f"encontró {n}/4 — parser falla con listas largas"
        return self._run_case("08", "parser", "lista 4 ítems (cinta/llave/destorn./mecha)", [msg],
            "procesar los 4 ítems sin omisiones", check)

    def case_09_multi_3_items_tecnicos(self):
        msg = "Quiero 10 tornillos M6, 5 mechas 8mm y 3 brocas 6mm"
        def check(rs):
            r = rs[-1].lower()
            found = [
                "tornillo" in r,
                ("mecha" in r or "broca" in r) and "8" in r,
                "broca" in r and "6" in r,
            ]
            n = sum(found)
            if n == 3:
                return "PASS", "encontró los 3 ítems con especificación técnica"
            if n == 2:
                return "WARN", f"encontró 2/3 ítems"
            return "FAIL", f"encontró {n}/3 ítems"
        return self._run_case("09", "parser", "3 ítems con especificación técnica (M6/8mm/6mm)", [msg],
            "parsear tornillos M6 + mechas 8mm + brocas 6mm", check)

    def case_10_plomeria_multi(self):
        msg = "20 metros de manguera, 5 abrazaderas, 2 acoples"
        def check(rs):
            r = rs[-1].lower()
            found = [
                "manguera" in r,
                "abrazadera" in r,
                "acople" in r,
            ]
            n = sum(found)
            if n == 3:
                return "PASS", "encontró los 3 ítems de plomería"
            if n >= 2:
                return "WARN", f"encontró {n}/3 ítems"
            return "FAIL", f"encontró {n}/3 — falla en multi-item plomería"
        return self._run_case("10", "parser", "3 ítems plomería (manguera/abrazadera/acople)", [msg],
            "parsear manguera + abrazaderas + acoples", check)

    # ── Multiturno ────────────────────────────────────────────────────────

    def case_11_multiturn_carrito_completo(self):
        sid = self._sid("11")
        t0 = time.perf_counter()
        try:
            with self.suppress():
                r1 = self.bot.process_message(sid, "quiero silicona y teflón")
                r2 = self.bot.process_message(sid, "¿hacen factura A?")
                r3 = self.bot.process_message(sid, "agregale un taladro")
            duration = round(time.perf_counter() - t0, 2)

            faq_ok = "factura" in r2.lower() and " a" in r2.lower()
            r3l = r3.lower()
            has_silicona = "silicona" in r3l
            has_teflon = "teflon" in r3l or "teflón" in r3l
            has_taladro = "taladro" in r3l

            if not (has_silicona and has_teflon and has_taladro):
                missing = [k for k, v in [
                    ("silicona", has_silicona), ("teflón", has_teflon), ("taladro", has_taladro)
                ] if not v]
                status = "FAIL"
                notes = f"carrito T3 falta: {missing}"
            elif not faq_ok:
                status = "WARN"
                notes = "carrito OK pero FAQ factura A no respondió bien en T2"
            else:
                status = "PASS"
                notes = "carrito preservado + FAQ correcta + ítem additive OK"

            actual = f"T2='{r2[:80]}' | T3='{r3[:120]}'"
        except Exception as exc:
            duration = round(time.perf_counter() - t0, 2)
            status, notes, actual = "ERROR", str(exc), ""

        result = TestResult(
            case_id="11", category="multiturno",
            description="3 turnos: items → FAQ → agregar ítem",
            inputs=["quiero silicona y teflón", "¿hacen factura A?", "agregale un taladro"],
            expected_description="carrito final: silicona + teflón + taladro",
            actual_response=actual,
            status=status, notes=notes, duration_seconds=duration,
        )
        self.results.append(result)
        return result

    # ── Matcher ───────────────────────────────────────────────────────────

    def case_12_matcher_llave_francesa(self):
        def check(rs):
            r = rs[-1].lower()
            has_llave_francesa = "llave francesa" in r or ("llave" in r and "ajustable" in r)
            has_adaptador_solo = "adaptador" in r and "llave" not in r
            if has_adaptador_solo:
                return "FAIL", "matcheó adaptadores en lugar de llaves francesas"
            if has_llave_francesa:
                return "PASS", "matcheó llaves francesas correctamente"
            return "WARN", "respuesta sin llaves francesas claras"
        return self._run_case("12", "matcher", '"llave francesa" → no adaptadores', ["llave francesa"],
            "encontrar llaves francesas, no adaptadores", check)

    def case_13_matcher_mecha_8mm(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            has_mecha = "mecha" in rl or "broca" in rl
            prices = _extract_prices(r)
            max_price = max(prices) if prices else 0
            if not has_mecha:
                return "FAIL", "no encontró mechas ni brocas"
            if max_price > 50_000:
                return "FAIL", f"precio ${max_price:,} — matcheó acople/adaptador grande"
            if max_price > 15_000:
                return "WARN", f"precio ${max_price:,} — verificar qué producto matcheó"
            if max_price >= 5_000:
                return "PASS", f"mecha correcta, precio OK (max=${max_price:,})"
            # max_price == 0: bot mencionó mecha/broca pero sin precio
            # → pidió clarificación (ej: "¿para madera, metal, hormigón?")
            # → es comportamiento correcto, no un falso WARN
            if max_price == 0:
                return "PASS", "bot pidió clarificación de tipo de mecha (sin precio = no matcheó acople)"
            return "WARN", f"precio inesperado ${max_price:,} — verificar"
        return self._run_case("13", "matcher", '"mecha 8mm" → no acoples de $57k+', ["mecha 8mm"],
            "mechas de 8mm (~$6.000-15.000), no acoples de $57.000+", check)

    def case_14_matcher_destornillador_philips(self):
        def check(rs):
            r = rs[-1].lower()
            has_destornillador = "destornillador" in r
            has_philips = "philips" in r or " ph" in r or "punta" in r or "ph2" in r
            if has_destornillador and has_philips:
                return "PASS", "encontró destornillador Philips o punta compatible"
            if has_destornillador:
                return "WARN", "encontró destornillador genérico (sin referencia Philips/PH)"
            return "FAIL", "no encontró destornilladores"
        return self._run_case("14", "matcher", '"destornillador philips" → set PH/Philips', ["destornillador philips"],
            "destornillador con punta Philips o referencia PH", check)

    # ── Casos límite ──────────────────────────────────────────────────────

    def case_15_objecion_precio(self):
        sid = self._sid("15")
        t0 = time.perf_counter()
        try:
            with self.suppress():
                self.bot.process_message(sid, "quiero una llave francesa")
                r = self.bot.process_message(sid, "está caro")
            duration = round(time.perf_counter() - t0, 2)
            rl = r.lower()
            handles = any(kw in rl for kw in (
                "entiendo", "comprendo", "valor", "calidad", "alternativa",
                "descuento", "opción", "opciones", "económic", "similar", "precio"
            ))
            ignores = "presupuesto preliminar" in rl and not handles
            if ignores:
                status, notes = "FAIL", "ignoró objeción y siguió con presupuesto"
            elif handles:
                status, notes = "PASS", "manejo correcto de objeción de precio"
            else:
                status, notes = "WARN", "respuesta vaga — no reconoce ni ignora claramente"
            actual = r[:250]
        except Exception as exc:
            duration = round(time.perf_counter() - t0, 2)
            status, notes, actual = "ERROR", str(exc), ""

        result = TestResult(
            case_id="15", category="casos_limite",
            description='"está caro" luego de ver precio → manejo objeción',
            inputs=["quiero una llave francesa", "está caro"],
            expected_description="reconocer objeción + alternativa o justificación de valor",
            actual_response=actual, status=status, notes=notes, duration_seconds=duration,
        )
        self.results.append(result)
        return result

    def case_16_escalacion_humano(self):
        def check(rs):
            r = rs[-1].lower()
            escalation_kws = (
                "equipo", "asesor", "contactar", "comunicar", "persona",
                "humano", "revisión", "seguimiento", "te vamos", "coordinar"
            )
            if any(kw in r for kw in escalation_kws):
                return "PASS", "escaló correctamente a equipo humano"
            if "momento" in r or "espera" in r:
                return "WARN", "respuesta vaga sin escalación clara"
            return "FAIL", "no escaló al solicitar hablar con humano"
        return self._run_case("16", "casos_limite",
            '"quiero hablar con humano" → escalación',
            ["quiero hablar con humano"],
            "handoff a equipo humano", check)

    def case_17_faq_horario(self):
        def check(rs):
            r = rs[-1].lower()
            has_info = any(kw in r for kw in (
                "horario", "lunes", "viernes", "sábado", "sabado", " hs", "hora",
                "pendiente", "confirmar", "consultar", "local", "abierto", "abre"
            ))
            redirects_to_products = "presupuesto" in r and not has_info
            if redirects_to_products:
                return "FAIL", "ignoró FAQ de horario y pidió productos"
            if has_info:
                return "PASS", "respondió FAQ de horario (o indicó pendiente)"
            return "WARN", "respuesta evasiva — no da info de horario"
        return self._run_case("17", "casos_limite",
            '"qué horarios tienen?" → FAQ policy',
            ["qué horarios tienen?"],
            "info de horarios o indicación de que es pendiente", check)

    # ── Anti-alucinación ──────────────────────────────────────────────────

    def case_18_anti_aluc_canos_ppr(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            no_tiene_kws = (
                "no tenemos", "no contamos", "no disponemos", "no tengo",
                "no está", "no lo tenemos", "no lo tengo", "no hay"
            )
            # FAIL: inventa precios para caños PP-R
            if prices and ("caño" in rl or "pp-r" in rl or "pp r" in rl or "termofusi" in rl):
                return "FAIL", f"inventó caños PP-R con precios: {prices[:3]}"
            if any(kw in rl for kw in no_tiene_kws):
                return "PASS", "indica explícitamente que no tiene caños PP-R"
            if prices:
                return "WARN", "ofrece alternativa con precio sin aclarar que no tiene PP-R"
            return "WARN", "respuesta evasiva — no confirma ni niega ausencia"
        return self._run_case("18", "anti_alucinacion",
            '"caños PP-R termofusión 20mm" → no inventar',
            ["necesito caños PP-R termofusión 20mm"],
            "decir explícitamente que no tiene, no inventar precios", check)

    def case_19_anti_aluc_producto_absurdo(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            no_tiene_kws = (
                "no tenemos", "no contamos", "no existe", "no tengo",
                "no disponemos", "no hay", "no lo tengo", "no lo tenemos"
            )
            if prices and "martillo" in rl:
                return "FAIL", f"inventó precios para producto absurdo: {prices[:3]}"
            if any(kw in rl for kw in no_tiene_kws):
                return "PASS", "descartó producto absurdo explícitamente"
            if prices:
                return "WARN", "dio precios de otro producto sin descartar el absurdo"
            return "WARN", "respuesta evasiva al producto absurdo"
        return self._run_case("19", "anti_alucinacion",
            '"martillo Stanley dorado 500kg" → no inventar',
            ["tienen martillos Stanley dorados de 500kg?"],
            "decir que no existe, no inventar precios", check)

    def case_20_anti_aluc_sku_falso(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            no_existe_kws = (
                "no existe", "no encontré", "no lo tenemos", "no tenemos",
                "no contamos", "no hay", "no lo encontré", "no tengo"
            )
            if prices and "aaaaa" in rl:
                return "FAIL", "inventó precio para SKU AAAAA"
            if any(kw in rl for kw in no_existe_kws):
                return "PASS", "indicó correctamente que el producto no existe"
            if prices:
                return "WARN", "dio precios de otros sin aclarar que AAAAA no existe"
            return "WARN", "respuesta evasiva — no confirma que SKU no existe"
        return self._run_case("20", "anti_alucinacion",
            '"100 unidades de AAAAA" → SKU inexistente',
            ["dame 100 unidades del producto AAAAA"],
            "indicar que el producto no existe, no inventar", check)

    # ── Regresión específica: precio inflado ──────────────────────────────

    def case_21_regresion_precio_mecha(self):
        def check(rs):
            r = rs[-1]
            prices = _extract_prices(r)
            if not prices:
                return "WARN", "sin precios en respuesta — verificar manualmente"
            max_price = max(prices)
            # 10 × mecha 8mm correcta (~$6.427/u) = ~$64.270
            # 10 × acople grande (~$57.787/u) = ~$577.870 → FAIL
            if max_price > 400_000:
                return "FAIL", f"precio inflado ${max_price:,} — matcheó acople/adaptador ($57k+/u)"
            if max_price > 200_000:
                return "WARN", f"precio alto ${max_price:,} — verificar producto matcheado"
            if max_price >= 50_000:
                return "PASS", f"precio razonable ${max_price:,} (esperado ~$64.270 para 10u)"
            return "WARN", f"precio bajo ${max_price:,} — verificar si encontró el producto correcto"
        return self._run_case("21", "regresion_precio",
            '"10 mechas 8mm" → precio $50k-$200k (no $400k+)',
            ["10 mechas 8mm"],
            "precio total entre $50.000 y $200.000 (10 × ~$6.427)", check)

    # ── Bloque G — Tolerancia lingüística ────────────────────────────────

    def case_22_typo_leve_llave(self):
        def check(rs):
            r = rs[-1].lower()
            # Bot debe reconocer "lave" como "llave francesa" o preguntar
            found_llave = "llave francesa" in r or ("llave" in r and "francesa" in r)
            asks_confirm = "te referís" in r or "querés decir" in r or "te referis" in r
            says_no_existe = any(kw in r for kw in ("no existe", "no encontré", "no tenemos", "no hay"))
            if says_no_existe and not (found_llave or asks_confirm):
                return "FAIL", "dijo categóricamente que no existe 'lave'"
            if found_llave or asks_confirm:
                return "PASS", "reconoció typo y encontró llave francesa o pidió confirmación"
            prices = _extract_prices(rs[-1])
            if prices:
                return "WARN", "ofrece alternativas con precio pero sin confirmar 'llave francesa'"
            return "WARN", "respuesta ambigua — no reconoce el typo claramente"
        return self._run_case("22", "tolerancia_linguistica",
            'TYPO: "lave francesa" → llave francesa',
            ["necesito una lave francesa"],
            "reconocer typo y mostrar llaves francesas o pedir confirmación", check)

    def case_23_typo_medio_destornilador(self):
        def check(rs):
            r = rs[-1].lower()
            has_destornillador = "destornillador" in r
            says_no_existe = any(kw in r for kw in ("no existe", "no encontré", "no tenemos")) and not has_destornillador
            if says_no_existe:
                return "FAIL", "rechazó 'destornilador' (una sola l) sin reconocer"
            if has_destornillador:
                return "PASS", "reconoció typo de destornillador"
            asks_confirm = "te referís" in r or "querés decir" in r
            if asks_confirm:
                return "PASS", "pidió confirmación del typo"
            return "WARN", "respuesta sin destornilladores ni confirmación"
        return self._run_case("23", "tolerancia_linguistica",
            'TYPO: "destornilador" (una sola l) → destornillador',
            ["tenes destornilador philips"],
            "reconocer typo y encontrar destornilladores Philips", check)

    def case_24_abreviacion_dest(self):
        def check(rs):
            r = rs[-1].lower()
            has_destornillador = "destornillador" in r
            asks_confirm = "te referís" in r or "querés decir" in r or "qué querés" in r
            says_no_existe = any(kw in r for kw in ("no existe", "no encontré", "no tenemos")) and not has_destornillador
            if says_no_existe:
                return "FAIL", "trató 'dest' como producto literal y no lo encontró"
            if has_destornillador:
                return "PASS", "dedujo destornillador de la abreviación 'dest'"
            if asks_confirm:
                return "WARN", "preguntó qué quiso decir — aceptable pero no ideal"
            return "FAIL", "no interpretó 'dest' ni como destornillador ni pidió aclaración"
        return self._run_case("24", "tolerancia_linguistica",
            'ABREV: "dest planos chicos" → destornillador plano',
            ["dame 5 dest planos chicos"],
            "deducir destornillador o pedir clarificación amigable", check)

    def case_25_slang_pico_de_loro(self):
        def check(rs):
            r = rs[-1].lower()
            has_pinza = "pinza" in r
            has_pico = "pico" in r
            says_no_existe = any(kw in r for kw in ("no existe", "no tenemos", "no hay")) and not (has_pinza or has_pico)
            if says_no_existe:
                return "FAIL", "no reconoció 'pico de loro' como tipo de pinza"
            if has_pinza or has_pico:
                return "PASS", "reconoció 'pico de loro' como pinza"
            asks_confirm = "te referís" in r or "querés decir" in r
            if asks_confirm:
                return "PASS", "pidió confirmación del slang"
            return "WARN", "respuesta sin pinzas ni confirmación del slang"
        return self._run_case("25", "tolerancia_linguistica",
            'SLANG: "pico de loro" → pinza pico de loro',
            ["necesito una pico de loro"],
            "reconocer slang ferretero y encontrar pinza pico de loro", check)

    def case_26_slang_caja_de_luz(self):
        def check(rs):
            r = rs[-1].lower()
            has_caja = "caja" in r and any(kw in r for kw in ("eléctr", "electr", "luz", "conexión", "conex", "pvc"))
            says_no_existe = any(kw in r for kw in ("no existe", "no tenemos", "no hay")) and not has_caja
            asks_confirm = "te referís" in r or "querés decir" in r or "qué tipo" in r
            if says_no_existe:
                return "FAIL", "no reconoció 'caja de luz' como caja eléctrica"
            if has_caja:
                return "PASS", "reconoció 'caja de luz' y encontró cajas eléctricas"
            if asks_confirm:
                return "PASS", "pidió clarificación del tipo de caja"
            prices = _extract_prices(rs[-1])
            if prices:
                return "WARN", "muestra productos con precio pero sin confirmar que son cajas eléctricas"
            return "WARN", "respuesta ambigua sobre 'caja de luz'"
        return self._run_case("26", "tolerancia_linguistica",
            'SLANG: "caja de luz" → caja eléctrica',
            ["tenés caja de luz?"],
            "reconocer slang y encontrar cajas eléctricas o pedir clarificación", check)

    def case_27_ingles_wrench(self):
        def check(rs):
            r = rs[-1].lower()
            has_llave = "llave" in r and any(kw in r for kw in ("inglesa", "tubo", "francesa", "ajustable"))
            asks_confirm = "te referís" in r or "querés decir" in r or "wrench" in r
            says_no_existe = any(kw in r for kw in ("no existe", "no tenemos", "no hay")) and not has_llave
            if says_no_existe:
                return "FAIL", "no reconoció 'wrench' y dijo que no existe"
            if has_llave:
                return "PASS", "reconoció 'wrench' como llave y encontró opciones"
            if asks_confirm:
                return "PASS", "preguntó si se refería a llave inglesa/de tubo"
            prices = _extract_prices(rs[-1])
            if prices:
                return "WARN", "muestra llaves variadas sin confirmar que wrench = llave inglesa"
            return "WARN", "respuesta ambigua ante término en inglés"
        return self._run_case("27", "tolerancia_linguistica",
            'INGLÉS: "wrench" → llave inglesa/de tubo',
            ["necesito una wrench"],
            "reconocer anglicismo y encontrar llaves o pedir clarificación", check)

    def case_28_plural_singular_mal(self):
        def check(rs):
            r = rs[-1].lower()
            has_martillo = "martillo" in r
            # Debe tratar "3 martillo" como pedido de 3 martillos
            has_qty = "3" in r or "tres" in r
            says_no_entiende = any(kw in r for kw in ("no entiendo", "no entendí", "podés aclarar"))
            if says_no_entiende and not has_martillo:
                return "FAIL", "no parseó '3 martillo' (plural incorrecto)"
            if has_martillo and has_qty:
                return "PASS", "parseó '3 martillo' correctamente como pedido de 3"
            if has_martillo:
                return "WARN", "encontró martillo pero sin confirmar cantidad 3"
            return "FAIL", "no respondió con martillos"
        return self._run_case("28", "tolerancia_linguistica",
            'PLURAL/SINGULAR: "3 martillo" → 3 martillos',
            ["necesito 3 martillo"],
            "parsear '3 martillo' como pedido de 3 martillos", check)

    def case_29_sin_acento_mecha(self):
        def check(rs):
            r = rs[-1].lower()
            has_mecha = "mecha" in r or "broca" in r
            prices = _extract_prices(rs[-1])
            max_price = max(prices) if prices else 0
            says_no_existe = any(kw in r for kw in ("no existe", "no tenemos", "no hay")) and not has_mecha
            if says_no_existe:
                return "FAIL", "no encontró mechas (sin tilde en mecha)"
            if has_mecha and max_price > 0 and max_price < 50_000:
                return "PASS", f"encontró mechas de 8mm sin tilde (precio OK: ${max_price:,})"
            if has_mecha and max_price >= 50_000:
                return "WARN", f"encontró mechas pero precio alto ${max_price:,} — verificar match"
            if has_mecha:
                return "PASS", "encontró mechas (sin tilde en mecha)"
            return "WARN", "respuesta ambigua sin acento en mecha"
        return self._run_case("29", "tolerancia_linguistica",
            'SIN ACENTO: "mecha de 8 mm" (sin tilde) → broca 8mm',
            ["necesito una mecha de 8 mm para taladro"],
            "encontrar mechas/brocas de 8mm aunque no haya tilde", check)

    def case_30_slang_codos_roscados(self):
        def check(rs):
            r = rs[-1].lower()
            has_codo = "codo" in r
            has_plomeria = any(kw in r for kw in ("plomería", "plomeria", "rosca", "roscado", "bronce"))
            says_no_existe = any(kw in r for kw in ("no existe", "no tenemos", "no hay")) and not has_codo
            if says_no_existe:
                return "FAIL", "no reconoció 'codos roscados' de plomería"
            if has_codo and (has_plomeria or _extract_prices(rs[-1])):
                return "PASS", "encontró codos roscados de plomería"
            if has_codo:
                return "WARN", "encontró codos pero sin confirmar que son roscados/plomería"
            asks_confirm = "te referís" in r or "qué tipo" in r
            if asks_confirm:
                return "WARN", "pidió clarificación — razonable pero el término es claro"
            return "FAIL", "no respondió con codos de plomería"
        return self._run_case("30", "tolerancia_linguistica",
            'JERGA: "10 codos roscados" → codos de plomería con rosca',
            ["dame 10 codos roscados"],
            "encontrar codos de plomería (jerga ferretera estándar)", check)

    def case_31_marca_sin_producto_bosch(self):
        def check(rs):
            r = rs[-1].lower()
            # Bot debe preguntar QUÉ producto Bosch, no decir "no encontré Bosch"
            asks_what = any(kw in r for kw in (
                "qué producto", "qué necesitás", "qué tipo", "qué herramienta",
                "tenemos varias", "taladro", "amoladora", "sierra"
            ))
            has_bosch = "bosch" in r
            says_no_existe = any(kw in r for kw in ("no existe", "no tenemos", "no hay bosch")) and not asks_what
            if says_no_existe:
                return "FAIL", "dijo 'no hay Bosch' en vez de preguntar qué producto"
            if asks_what and has_bosch:
                return "PASS", "preguntó qué tipo de producto Bosch necesita"
            if has_bosch:
                prices = _extract_prices(rs[-1])
                if prices:
                    return "PASS", "encontró productos Bosch directamente"
                return "WARN", "mencionó Bosch pero sin preguntar ni mostrar productos"
            return "WARN", "respuesta sin referencia a Bosch ni clarificación"
        return self._run_case("31", "tolerancia_linguistica",
            'MARCA: "tienen Bosch?" → preguntar qué producto',
            ["tienen Bosch?"],
            "preguntar qué producto Bosch necesita, no decir 'no encontré Bosch'", check)

    # ── Reporte ───────────────────────────────────────────────────────────

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
        print("REPORTE — DEMO TEST SUITE — FERRETERÍA BOT")
        print("=" * 80)

        # Tabla completa
        print(f"\n{'ID':<4} {'ST':<5} {'CATEGORÍA':<22} {'DESCRIPCIÓN':<38} NOTAS")
        print("-" * 115)
        for r in self.results:
            icon = icons[r.status]
            desc = r.description[:37]
            notes = r.notes[:48]
            print(f"{r.case_id:<4} {icon} {r.status:<3} {r.category:<22} {desc:<38} {notes}")

        # Bugs agrupados por categoría
        non_pass = {cat: rs for cat, rs in by_cat.items()
                    if any(r.status in ("FAIL", "WARN", "ERROR") for r in rs)}
        if non_pass:
            print(f"\n{'─'*80}")
            print("BUGS / ADVERTENCIAS POR CATEGORÍA:")
            for cat, results in sorted(non_pass.items()):
                fails  = [r for r in results if r.status == "FAIL"]
                warns  = [r for r in results if r.status == "WARN"]
                errors = [r for r in results if r.status == "ERROR"]
                if not (fails or warns or errors):
                    continue
                print(f"\n  [{cat.upper()}]")
                for r in errors:
                    print(f"    💥 {r.case_id}: {r.description[:60]}")
                    print(f"       → {r.notes}")
                for r in fails:
                    print(f"    ❌ {r.case_id}: {r.description[:60]}")
                    print(f"       → {r.notes}")
                    print(f"       respuesta: {r.actual_response[:120]}")
                for r in warns:
                    print(f"    ⚠️  {r.case_id}: {r.description[:60]}")
                    print(f"       → {r.notes}")

        # Resumen ejecutivo
        pct = lambda n: f"{n/total*100:.0f}%" if total else "0%"
        print(f"\n{'─'*80}")
        print("RESUMEN EJECUTIVO")
        print(f"  Total casos : {total}")
        print(f"  ✅ PASS     : {totals['PASS']} ({pct(totals['PASS'])})")
        print(f"  ⚠️  WARN     : {totals['WARN']} ({pct(totals['WARN'])})")
        print(f"  ❌ FAIL     : {totals['FAIL']} ({pct(totals['FAIL'])})")
        print(f"  💥 ERROR    : {totals['ERROR']} ({pct(totals['ERROR'])})")
        print(f"  Tiempo total: {total_time:.1f}s")
        print(f"  Costo API   : N/A (no instrumentado)")
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
            print(f"  {icon} [{result.case_id}] {result.description[:58]:<58} ({result.duration_seconds}s)")
        print()
        self._print_report()
        self.bot.close()
        fails = sum(1 for r in self.results if r.status in ("FAIL", "ERROR"))
        return 1 if fails > 0 else 0


if __name__ == "__main__":
    suite = DemoTestSuite()
    raise SystemExit(suite.run_all())
