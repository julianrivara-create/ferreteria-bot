#!/usr/bin/env python3
"""
Demo End-to-End Test Suite EXTENDED — Ferretería Bot
=====================================================

50+ casos nuevos que complementan demo_test_suite.py (31 casos originales).
No duplica casos existentes. Cubre escenarios mayoristas, conversación
argentina, negociación, stock, anti-fraude, multiturno largo, WhatsApp
fragmentado y mensajes ambiguos.

Cómo correrlo:
    PYTHONPATH=. python3 scripts/demo_test_suite_extended.py

Cuándo correrlo:
    Después de cambios significativos. Tarda ~8-12 minutos (API real).

Total de casos: 53 (E01-E53)
    - pedidos_mayoristas (12): listas largas de obra/instalación
    - conversacion_argentina (8): slang, informalidad, contexto
    - negociacion (6): regateo, descuentos, objeción de precio
    - disponibilidad_stock (6): reservas, entrega, stock
    - anti_fraude (6): specs imposibles, productos absurdos
    - multiturno_largo (5): carritos con 5+ turnos, modificaciones
    - whatsapp_fragmentado (5): mensajes cortos secuenciales
    - ambiguedad (5): una palabra, sin contexto

Criterios:
    PASS  = comportamiento correcto sin defectos
    WARN  = funciona pero subóptimo
    FAIL  = error concreto (alucinó precio, perdió carrito, ignoró spec)
    ERROR = excepción inesperada en runtime

Estado inicial: 2026-05-03 — primera corrida contra main @ b68f12c
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
    prices = []
    for m in re.finditer(r'\$[\d\.]+', text):
        raw = m.group(0).replace('$', '').replace('.', '')
        try:
            prices.append(int(raw))
        except ValueError:
            pass
    return prices


def _has_no_match(text: str) -> bool:
    kws = ("no tenemos", "no contamos", "no disponemos", "no tengo",
           "no lo tenemos", "no hay", "no existe", "no encontré", "no lo encontré")
    return any(k in text.lower() for k in kws)


class DemoTestSuiteExtended:
    def __init__(self):
        from bot_sales.runtime import get_runtime_bot, get_runtime_tenant
        from bot_sales.ferreteria_unresolved_log import suppress_unresolved_logging
        tenant = get_runtime_tenant("ferreteria")
        self.bot = get_runtime_bot(tenant.id)
        self.suppress = suppress_unresolved_logging
        self.run_id = uuid.uuid4().hex[:8]
        self.results: list[TestResult] = []

    def _sid(self, case_id: str) -> str:
        return f"ext_{case_id}_{self.run_id}"

    def _send(self, session_id: str, messages: list[str]) -> list[str]:
        responses = []
        with self.suppress():
            for msg in messages:
                responses.append(self.bot.process_message(session_id, msg))
        return responses

    def _run_case(self, case_id, category, description, inputs,
                  expected_description, checker) -> TestResult:
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

    def _manual_multiturn(self, case_id, category, description, turns,
                          expected_description, checker) -> TestResult:
        """Para casos multiturno donde necesito revisar respuestas intermedias."""
        sid = self._sid(case_id)
        t0 = time.perf_counter()
        try:
            responses = []
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

    # ── CATEGORÍA 1 — Pedidos mayoristas reales ───────────────────────────

    def case_E01_obra_5_items(self):
        msg = 'hola, me podés cotizar para una obra: 100m de caño 1/2", 50 codos, 30 cuplas, 10 llaves de paso, 5 ramales'
        def check(rs):
            r = rs[-1].lower()
            prices = _extract_prices(rs[-1])
            items = sum([
                "caño" in r, "codo" in r, "cupla" in r,
                "llave" in r, "ramal" in r,
            ])
            total = max(prices) if prices else 0
            if items >= 4 and total > 50_000:
                return "PASS", f"detectó {items}/5 ítems, total=${total:,}"
            if items >= 3:
                return "WARN", f"detectó {items}/5 ítems, total=${total:,}"
            return "FAIL", f"detectó {items}/5 ítems — parser falla con lista de obra"
        return self._run_case("E01", "pedidos_mayoristas",
            "lista obra: caño/codos/cuplas/llaves/ramales (5 ítems)", [msg],
            "detectar 4+ ítems con total > $50.000", check)

    def case_E02_tornillos_3_medidas(self):
        msg = "necesito 200 tornillos M6, 200 M8, 100 M10, todos cabeza hexagonal"
        def check(rs):
            r = rs[-1].lower()
            has_m6 = "m6" in r or ("tornillo" in r and "6" in r)
            has_m8 = "m8" in r or ("tornillo" in r and "8" in r)
            has_m10 = "m10" in r or ("tornillo" in r and "10" in r)
            n = sum([has_m6, has_m8, has_m10])
            if n == 3:
                return "PASS", "detectó M6 + M8 + M10 con cantidades"
            if n == 2:
                return "WARN", f"detectó {n}/3 medidas de tornillo"
            return "FAIL", f"detectó {n}/3 medidas — falla con múltiples especificaciones técnicas"
        return self._run_case("E02", "pedidos_mayoristas",
            "200xM6 + 200xM8 + 100xM10 cabeza hexagonal", [msg],
            "detectar 3 medidas de tornillo con cantidades", check)

    def case_E03_electricista_3_items(self):
        msg = "cotización para electricista: 50m de cable 2.5mm, 30 cajas de luz, 100m termocontraíble"
        def check(rs):
            r = rs[-1].lower()
            prices = _extract_prices(rs[-1])
            has_cable = "cable" in r
            has_caja = "caja" in r
            has_termo = "termo" in r or "termocontra" in r
            n = sum([has_cable, has_caja, has_termo])
            if n == 3 and not (prices and all(p > 1_000_000 for p in prices)):
                return "PASS", "detectó cable + caja + termocontraíble sin alucinar"
            if n >= 2:
                return "WARN", f"detectó {n}/3 ítems de electricista"
            return "FAIL", f"detectó {n}/3 ítems"
        return self._run_case("E03", "pedidos_mayoristas",
            "cable 2.5mm + cajas de luz + termocontraíble (electricista)", [msg],
            "detectar 3 ítems sin alucinación de precios", check)

    def case_E04_instalacion_4_items(self):
        msg = 'para instalación: 20 niples 1/2", 15 codos 90 grados, 10 llaves esféricas, sellador siliconado'
        def check(rs):
            r = rs[-1].lower()
            items = sum([
                "niple" in r, "codo" in r,
                "llave" in r or "esférica" in r or "esferica" in r,
                "sellador" in r or "silicona" in r,
            ])
            if items >= 4:
                return "PASS", f"detectó {items}/4 ítems de instalación"
            if items >= 3:
                return "WARN", f"detectó {items}/4 ítems"
            return "FAIL", f"detectó {items}/4 ítems"
        return self._run_case("E04", "pedidos_mayoristas",
            "niples + codos 90° + llaves esféricas + sellador (4 ítems)", [msg],
            "detectar 4 ítems de instalación de plomería", check)

    def case_E05_mechas_3_medidas_bosch(self):
        msg = "presupuesto urgente: 100 mechas 6mm Bosch + 50 mechas 8mm + 30 brocas 10mm"
        def check(rs):
            r = rs[-1].lower()
            prices = _extract_prices(rs[-1])
            has_mecha = "mecha" in r or "broca" in r
            has_bosch = "bosch" in r
            # No debe matchear acoples: precios unitarios de acoples > $50.000
            max_price = max(prices) if prices else 0
            if not has_mecha:
                return "FAIL", "no detectó mechas ni brocas"
            if max_price > 400_000:
                return "FAIL", f"precio inflado ${max_price:,} — matcheó acoples"
            if has_mecha and has_bosch:
                return "PASS", "detectó mechas Bosch sin matchear acoples"
            return "WARN", "encontró mechas pero sin referencia Bosch clara"
        return self._run_case("E05", "pedidos_mayoristas",
            "100xMecha6mm Bosch + 50xMecha8mm + 30xBroca10mm (anti-acople)", [msg],
            "detectar 3 tamaños de mecha sin matchear acoples", check)

    def case_E06_tablero_electrico(self):
        msg = "necesito armar un tablero: 1 contactora trifásica, 3 térmicas, 1 disyuntor, cable 4mm 20m, 10 borneras"
        def check(rs):
            r = rs[-1].lower()
            items = sum([
                "contact" in r, "térmica" in r or "termica" in r,
                "disyuntor" in r, "cable" in r, "bornera" in r,
            ])
            asks_clarif = any(kw in r for kw in ("qué tipo", "qué marca", "especificá", "más info"))
            if items >= 3:
                return "PASS", f"detectó {items}/5 ítems eléctricos"
            if asks_clarif or items >= 2:
                return "WARN", f"pidió clarificación o detectó {items}/5 — ítems eléctricos complejos"
            prices = _extract_prices(rs[-1])
            if prices:
                return "WARN", f"muestra precios pero detectó pocos ítems ({items}/5)"
            return "FAIL", f"detectó {items}/5 ítems de tablero eléctrico"
        return self._run_case("E06", "pedidos_mayoristas",
            "tablero: contactora + térmicas + disyuntor + cable + borneras", [msg],
            "detectar 5 ítems eléctricos o pedir clarificación amigable", check)

    def case_E07_stock_5_herramientas(self):
        msg = "tenes todo lo siguiente con stock?: martillo 500g, destornillador philips, alicate, llave inglesa, sierra de mano"
        def check(rs):
            r = rs[-1].lower()
            items = sum([
                "martillo" in r, "destornillador" in r,
                "alicate" in r or "pinza" in r,
                "llave" in r, "sierra" in r,
            ])
            prices = _extract_prices(rs[-1])
            if items >= 4 and prices:
                return "PASS", f"confirmó stock para {items}/5 herramientas con precios"
            if items >= 3:
                return "WARN", f"encontró {items}/5 herramientas"
            return "FAIL", f"encontró {items}/5 — falla con lista de verificación de stock"
        return self._run_case("E07", "pedidos_mayoristas",
            "verificar stock: martillo + destornillador + alicate + llave + sierra", [msg],
            "confirmar disponibilidad de 4+ herramientas con precios", check)

    def case_E08_lista_cliente_final(self):
        msg = "lista cliente final: 5 sets destornilladores Bahco, 3 taladros percutores, 10 amoladoras 4.5"
        def check(rs):
            r = rs[-1].lower()
            prices = _extract_prices(rs[-1])
            items = sum([
                "destornillador" in r or "bahco" in r,
                "taladro" in r,
                "amoladora" in r or "esmeriladora" in r,
            ])
            if items == 3 and prices:
                return "PASS", f"detectó 3/3 ítems con precios reales"
            if items >= 2:
                return "WARN", f"detectó {items}/3 ítems"
            return "FAIL", f"detectó {items}/3 ítems de herramientas eléctricas"
        return self._run_case("E08", "pedidos_mayoristas",
            "Bahco sets + taladros percutores + amoladoras 4.5 (3 ítems)", [msg],
            "detectar 3 ítems con precios reales", check)

    def case_E09_termofusion_ppr(self):
        msg = "obra completa para baño: termofusión 20mm + accesorios, llaves esféricas, sellador, cinta teflón"
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            has_disclaimer = _has_no_match(r) or "no contamos con" in rl
            mentions_ppr = "pp-r" in rl or "termofusi" in rl
            has_alternatives = any(kw in rl for kw in ("llave", "sellador", "teflón", "teflon"))
            # PASS: menciona PP-R/termofusión + dice que no la tiene + ofrece otros ítems
            # (los precios son de los ítems disponibles, no de PP-R — no es alucinación)
            if has_disclaimer and mentions_ppr and has_alternatives:
                return "PASS", "informó que no tiene PP-R y ofreció lo disponible con precios"
            if has_disclaimer and mentions_ppr:
                return "WARN", "informó que no tiene PP-R pero no ofreció alternativas"
            # FAIL: menciona PP-R con precios sin disclaimear su ausencia
            if prices and mentions_ppr and not has_disclaimer:
                return "FAIL", f"inventó precios para termofusión PP-R sin aclarar ausencia: {prices[:3]}"
            if has_disclaimer and has_alternatives:
                return "PASS", "informó ausencia y ofreció lo disponible"
            if has_alternatives and prices:
                return "WARN", "ofrece ítems alternativos sin aclarar ausencia de PP-R"
            return "WARN", "respuesta ambigua sobre termofusión PP-R"
        return self._run_case("E09", "pedidos_mayoristas",
            "termofusión PP-R + llaves esféricas + sellador + teflón", [msg],
            "aclarar que no tiene PP-R, ofrecer ítems disponibles, no inventar", check)

    def case_E10_canos_galvanizados(self):
        msg = 'buenas, mandame: 3 caños galvanizados 6mts, 5 codos, 10 cuplas, 2 llaves de paso 3/4"'
        def check(rs):
            r = rs[-1].lower()
            items = sum([
                "caño" in r or "galvanizado" in r,
                "codo" in r,
                "cupla" in r,
                "llave" in r or "paso" in r,
            ])
            if items >= 4:
                return "PASS", f"detectó {items}/4 ítems con cantidades"
            if items >= 3:
                return "WARN", f"detectó {items}/4"
            return "FAIL", f"detectó {items}/4 ítems de plomería galvanizada"
        return self._run_case("E10", "pedidos_mayoristas",
            'caños galvanizados + codos + cuplas + llaves 3/4"', [msg],
            "detectar 4 ítems con cantidades", check)

    def case_E11_multiplicador_x50(self):
        msg = "cotizá: 1m caño + 1 codo + 1 cupla x 50 (todos)"
        def check(rs):
            r = rs[-1].lower()
            prices = _extract_prices(rs[-1])
            has_cano = "caño" in r
            has_codo = "codo" in r
            has_cupla = "cupla" in r
            has_50 = "50" in r
            asks_clarif = any(kw in r for kw in ("qué tipo", "clarificá", "aclará", "x 50"))
            if (has_cano or has_codo or has_cupla) and (has_50 or asks_clarif):
                return "PASS", "interpretó multiplicador x50 o pidió clarificación"
            if has_cano or has_codo or has_cupla:
                return "WARN", "encontró ítems pero sin multiplicador x50"
            return "FAIL", "no detectó ítems con el formato x50"
        return self._run_case("E11", "pedidos_mayoristas",
            "formato: 1 caño + 1 codo + 1 cupla x 50 (multiplicador)", [msg],
            "interpretar multiplicador x50 o pedir clarificación", check)

    def case_E12_taller_lubricantes(self):
        msg = "para taller: lubricantes (WD-40 + grasa universal), trapos, guantes 5 pares, gafas 2"
        def check(rs):
            r = rs[-1].lower()
            found = sum([
                "wd" in r or "lubricante" in r or "grasa" in r,
                "trapo" in r,
                "guante" in r,
                "gafa" in r or "lente" in r or "antiparras" in r,
            ])
            no_match = _has_no_match(r)
            if found >= 2 or (found >= 1 and no_match):
                return "PASS", f"detectó {found}/4 ítems de taller, informó sobre los demás"
            if found >= 1:
                return "WARN", f"detectó {found}/4 ítems sin informar sobre los ausentes"
            return "FAIL", "no detectó ningún ítem de taller"
        return self._run_case("E12", "pedidos_mayoristas",
            "WD-40 + grasa + trapos + guantes + gafas (taller)", [msg],
            "detectar ítems disponibles, informar qué no encuentra", check)

    # ── CATEGORÍA 2 — Conversación natural argentina ───────────────────────

    def case_E13_che_taladros(self):
        def check(rs):
            r = rs[-1].lower()
            has_taladro = "taladro" in r
            prices = _extract_prices(rs[-1])
            if has_taladro and prices:
                return "PASS", "respondió con opciones de taladros"
            if has_taladro:
                return "WARN", "mencionó taladros pero sin precios"
            return "FAIL", "no respondió con taladros al slang 'che tenés'"
        return self._run_case("E13", "conversacion_argentina",
            '"che, tenés taladros?" → slang argentino', ["che, tenés taladros?"],
            "mostrar opciones de taladros", check)

    def case_E14_dale_mostrame(self):
        def check(rs):
            r = rs[-1].lower()
            asks = any(kw in r for kw in (
                "qué buscás", "qué necesitás", "qué producto", "qué querés",
                "contame", "especificá", "cuál", "qué rubro"
            ))
            if asks:
                return "PASS", "pidió especificar qué busca (respuesta correcta a ambigüedad)"
            prices = _extract_prices(rs[-1])
            if prices:
                return "WARN", "mostró productos sin pedir qué busca — demasiado asertivo"
            return "WARN", "respuesta vaga ante mensaje muy ambiguo"
        return self._run_case("E14", "conversacion_argentina",
            '"dale, mostrame qué hay" → ambigüedad', ["dale, mostrame qué hay"],
            "pedir especificación (mensaje muy ambiguo)", check)

    def case_E15_buenisimo_voy_con_eso(self):
        def check(rs):
            r = rs[-1].lower()
            # Sin contexto previo: debe manejar con elegancia, no crashear
            prices = _extract_prices(rs[-1])
            if not r:
                return "FAIL", "respuesta vacía"
            if prices and len(prices) > 3:
                return "WARN", "inventó presupuesto sin contexto"
            asks = any(kw in r for kw in ("qué", "cuál", "contame", "especificá", "de qué"))
            if asks:
                return "PASS", "pidió contexto ante respuesta sin antecedente"
            return "WARN", "maneja sin error pero respuesta vaga"
        return self._run_case("E15", "conversacion_argentina",
            '"buenísimo, voy con eso" → sin contexto previo', ["buenísimo, voy con eso"],
            "manejar con elegancia, pedir contexto", check)

    def case_E16_mortal_el_precio(self):
        def check(rs):
            r = rs[-1].lower()
            # "está mortal" = muy caro en arg → objeción de precio
            handles = any(kw in r for kw in (
                "entiendo", "comprendo", "valor", "calidad", "alternativa",
                "descuento", "opción", "precio", "económic"
            ))
            if handles:
                return "PASS", "reconoció 'mortal' como objeción de precio"
            asks_context = any(kw in r for kw in ("qué producto", "cuál", "de qué"))
            if asks_context:
                return "WARN", "pidió contexto — no reconoció slang de objeción"
            return "FAIL", "no manejó 'está mortal el precio' como objeción"
        return self._run_case("E16", "conversacion_argentina",
            '"está mortal el precio" → slang objeción', ["está mortal el precio"],
            "manejar como objeción de precio (slang argentino)", check)

    def case_E17_me_sirve_dale(self):
        def check(rs):
            r = rs[-1].lower()
            if not r:
                return "FAIL", "respuesta vacía"
            # Sin contexto: puede pedir qué confirma o aceptar
            handles = any(kw in r for kw in (
                "qué", "cuál", "confirmar", "pedido", "recibimos", "reserva"
            ))
            if handles:
                return "PASS", "maneja 'me sirve, dale' pidiendo contexto o confirmando"
            return "WARN", "respuesta vaga ante confirmación sin contexto"
        return self._run_case("E17", "conversacion_argentina",
            '"me sirve, dale" → confirmación sin contexto', ["me sirve, dale"],
            "pedir qué confirma o manejar elegantemente", check)

    def case_E18_nahh_caro(self):
        def check(rs):
            r = rs[-1].lower()
            handles = any(kw in r for kw in (
                "entiendo", "comprendo", "alternativa", "opción", "precio",
                "descuento", "calidad", "valor", "económic", "similar"
            ))
            if handles:
                return "PASS", "manejó 'nahh está caro' como objeción"
            return "WARN", "respuesta vaga ante objeción informal"
        return self._run_case("E18", "conversacion_argentina",
            '"nahh está caro" → objeción informal', ["nahh está caro"],
            "manejar como objeción de precio", check)

    def case_E19_no_me_convence(self):
        def check(rs):
            r = rs[-1].lower()
            offers_alt = any(kw in r for kw in (
                "alternativa", "opción", "otra", "diferente", "similar",
                "qué buscás", "qué necesitás", "contame más"
            ))
            if offers_alt:
                return "PASS", "ofreció alternativas o pidió más info"
            return "WARN", "no ofreció alternativas ante 'no me convence'"
        return self._run_case("E19", "conversacion_argentina",
            '"no me convence, mostrame otra cosa"', ["no me convence, mostrame otra cosa"],
            "ofrecer alternativas o pedir más especificación", check)

    def case_E20_tipo_bosch(self):
        def check(rs):
            r = rs[-1].lower()
            asks_product = any(kw in r for kw in (
                "qué producto", "qué tipo", "taladro", "amoladora",
                "sierra", "qué herramienta", "qué necesitás"
            ))
            has_bosch = "bosch" in r
            if asks_product and has_bosch:
                return "PASS", "preguntó qué tipo de producto Bosch"
            if asks_product:
                return "WARN", "preguntó producto pero sin mencionar Bosch"
            prices = _extract_prices(rs[-1])
            if prices and has_bosch:
                return "PASS", "mostró productos Bosch directamente"
            return "WARN", "respuesta vaga ante 'tipo Bosch'"
        return self._run_case("E20", "conversacion_argentina",
            '"tipo Bosch tenés algo?" → marca sin producto', ["tipo Bosch tenés algo?"],
            "preguntar qué tipo de producto Bosch necesita", check)

    # ── CATEGORÍA 3 — Negociación / regateo ──────────────────────────────

    def case_E21_cuanto_el_ultimo(self):
        def check(rs):
            r = rs[-1].lower()
            handles = any(kw in r for kw in (
                "precio", "descuento", "política", "asesor", "mejor precio",
                "volumen", "mayor", "confirmar"
            ))
            invents = _extract_prices(rs[-1]) and "% " in r and "descuento" in r
            if invents:
                return "WARN", "prometió descuento específico sin política clara"
            if handles:
                return "PASS", "manejó negociación sin inventar descuentos"
            return "WARN", "respuesta vaga ante regateo de precio final"
        return self._run_case("E21", "negociacion",
            '"está caro, cuánto el último?" → regateo', ["está caro, ¿cuánto el último?"],
            "manejar sin inventar descuentos, aclarar política", check)

    def case_E22_si_llevo_100(self):
        def check(rs):
            r = rs[-1].lower()
            handles_volume = any(kw in r for kw in (
                "volumen", "mayor", "cantidad", "descuento", "política",
                "asesor", "consultar", "confirmar", "coordinar"
            ))
            if handles_volume:
                return "PASS", "respondió política mayorista o escaló para volumen"
            return "WARN", "no mencionó política de volumen al pedir descuento por 100 unidades"
        return self._run_case("E22", "negociacion",
            '"si llevo 100 me bajás?" → descuento por volumen', ["si llevo 100 me bajás?"],
            "responder política mayorista o escalar a asesor", check)

    def case_E23_en_otro_lado_mas_barato(self):
        def check(rs):
            r = rs[-1].lower()
            professional = any(kw in r for kw in (
                "entiendo", "calidad", "garantía", "stock", "servicio",
                "asesor", "comparar", "precio", "valor"
            ))
            drops_price = any(kw in r for kw in ("te doy", "te hago", "% off", "bajamos"))
            if drops_price:
                return "WARN", "bajó precio sin política — demasiado fácil"
            if professional:
                return "PASS", "manejó objeción de competencia profesionalmente"
            return "WARN", "respuesta vaga ante objeción de precio de competencia"
        return self._run_case("E23", "negociacion",
            '"en otro lado lo conseguí más barato"', ["en otro lado lo conseguí más barato"],
            "manejar objeción profesionalmente sin bajar precio automáticamente", check)

    def case_E24_descuento_por_mayor(self):
        def check(rs):
            r = rs[-1].lower()
            has_policy = any(kw in r for kw in (
                "mayorista", "volumen", "cantidad", "política", "asesor",
                "descuento", "precio especial", "consultar"
            ))
            if has_policy:
                return "PASS", "indicó política de descuento por mayor"
            return "WARN", "no mencionó política mayorista"
        return self._run_case("E24", "negociacion",
            '"hacés descuento por mayor?" → política mayorista', ["hacés descuento por mayor?"],
            "indicar política de descuentos por volumen", check)

    def case_E25_15_off(self):
        def check(rs):
            r = rs[-1].lower()
            auto_accepts = any(kw in r for kw in ("listo", "aplicado", "hecho", "te doy el 15"))
            escalates = any(kw in r for kw in (
                "asesor", "consultar", "confirmar", "política", "equipo", "coordinar"
            ))
            if auto_accepts:
                return "FAIL", "aceptó automáticamente 15% off sin consultar"
            if escalates:
                return "PASS", "no aceptó automáticamente, escaló o explicó política"
            return "WARN", "no rechazó ni escaló el pedido de descuento específico"
        return self._run_case("E25", "negociacion",
            '"15% off?" → no aceptar automáticamente', ["15% off?"],
            "no aceptar automáticamente, escalar o explicar política", check)

    def case_E26_dame_mejor_precio(self):
        def check(rs):
            r = rs[-1].lower()
            auto_drops = any(kw in r for kw in ("te doy", "bajamos", "% off", "te hago precio"))
            handles = any(kw in r for kw in (
                "asesor", "política", "consultar", "volumen", "cantidad",
                "qué producto", "cuánto necesitás"
            ))
            if auto_drops:
                return "WARN", "bajó precio automáticamente sin contexto ni política"
            if handles:
                return "PASS", "manejó negociación sin bajar precio automáticamente"
            return "WARN", "respuesta vaga ante pedido de mejor precio"
        return self._run_case("E26", "negociacion",
            '"dame mejor precio" → negociación general', ["dame mejor precio"],
            "no bajar precio automáticamente, pedir contexto o escalar", check)

    # ── CATEGORÍA 4 — Disponibilidad y stock ─────────────────────────────

    def case_E27_stock_taladros_bosch(self):
        def check(rs):
            r = rs[-1].lower()
            has_taladro = "taladro" in r
            has_bosch = "bosch" in r
            has_stock = any(kw in r for kw in ("stock", "disponible", "tenemos", "hay"))
            asks_spec = any(kw in r for kw in ("qué tipo", "modelo", "voltaje", "percutor"))
            if has_taladro and has_bosch and (has_stock or asks_spec):
                return "PASS", "confirma stock Bosch o pide especificación"
            if has_taladro and (has_stock or asks_spec):
                return "WARN", "responde stock de taladros pero sin Bosch específico"
            return "FAIL", "no respondió sobre stock de taladros Bosch"
        return self._run_case("E27", "disponibilidad_stock",
            '"hay stock de taladros Bosch?"', ["hay stock de taladros Bosch?"],
            "confirmar stock real o pedir especificación de modelo", check)

    def case_E28_cuando_llega_mercaderia(self):
        def check(rs):
            r = rs[-1].lower()
            escalates = any(kw in r for kw in (
                "asesor", "equipo", "consultar", "coordinar", "contactar"
            ))
            asks_product = any(kw in r for kw in (
                "qué producto", "cuál", "qué necesitás", "especificá"
            ))
            if escalates or asks_product:
                return "PASS", "escaló o pidió especificar producto"
            return "WARN", "no escaló ni pidió producto al preguntar por reposición"
        return self._run_case("E28", "disponibilidad_stock",
            '"cuándo te llega más mercadería?" → reposición', ["cuándo te llega más mercadería?"],
            "pedir especificar producto o escalar a equipo", check)

    def case_E29_disponible_mañana(self):
        def check(rs):
            r = rs[-1].lower()
            has_delivery_info = any(kw in r for kw in (
                "entrega", "envío", "despacho", "disponible", "coordinar",
                "mañana", "días", "plazo", "asesor"
            ))
            if has_delivery_info:
                return "PASS", "respondió sobre disponibilidad/entrega"
            return "WARN", "no aclaró política de entrega o disponibilidad"
        return self._run_case("E29", "disponibilidad_stock",
            '"tenés disponible para mañana?"', ["tenés disponible para mañana?"],
            "aclarar política de entrega o escalar", check)

    def case_E30_reservar_tornillos(self):
        def check(rs):
            r = rs[-1].lower()
            asks_type = any(kw in r for kw in (
                "qué tipo", "M6", "M8", "medida", "hexagonal", "philips",
                "especificá", "cuál"
            ))
            has_reserva = any(kw in r for kw in ("reserva", "guardar", "separar", "apartar"))
            if asks_type or has_reserva:
                return "PASS", "preguntó tipo de tornillo o inició reserva"
            return "WARN", "no pidió tipo de tornillo ni mencionó reserva"
        return self._run_case("E30", "disponibilidad_stock",
            '"me reservás 50 tornillos M6?"', ["me reservás 50 tornillos M6?"],
            "preguntar tipo o usar crear_reserva", check)

    def case_E31_hasta_cuando_lo_guardas(self):
        def check(rs):
            r = rs[-1].lower()
            has_time = any(kw in r for kw in (
                "minuto", "hora", "día", "reserva", "tiempo", "plazo",
                "guardar", "hold", "vencimiento"
            ))
            if has_time:
                return "PASS", "indicó tiempo de reserva o hold_minutes"
            return "WARN", "no indicó cuánto tiempo se mantiene la reserva"
        return self._run_case("E31", "disponibilidad_stock",
            '"hasta cuándo me lo guardás?" → tiempo de reserva', ["hasta cuándo me lo guardás?"],
            "indicar tiempo de reserva (hold_minutes)", check)

    def case_E32_disponible_o_hay_que_pedir(self):
        def check(rs):
            r = rs[-1].lower()
            has_stock_info = any(kw in r for kw in (
                "stock", "disponible", "hay", "tenemos", "pedir",
                "solicitar", "proveedor", "consultar"
            ))
            if has_stock_info:
                return "PASS", "informó sobre disponibilidad real o proceso de pedido"
            return "WARN", "respuesta vaga sobre disponibilidad vs pedido"
        return self._run_case("E32", "disponibilidad_stock",
            '"está disponible o lo tienen que pedir?"', ["está disponible o lo tienen que pedir?"],
            "responder sobre stock real o proceso de pedido", check)

    # ── CATEGORÍA 5 — Anti-fraude ─────────────────────────────────────────

    def case_E33_taladro_5000w(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            if prices and "5000" in rl and "taladro" in rl:
                return "FAIL", f"inventó taladro de 5000W con precio: {prices[:2]}"
            no_match = _has_no_match(r)
            asks_clarif = any(kw in rl for kw in ("qué potencia", "cuántos watts", "aclará"))
            if no_match or asks_clarif:
                return "PASS", "bloqueó spec imposible o pidió aclaración de potencia"
            if prices:
                return "WARN", f"dio precio de taladro sin validar spec de 5000W"
            return "WARN", "respuesta ambigua ante spec imposible"
        return self._run_case("E33", "anti_fraude",
            '"taladro de 5000W" → potencia imposible', ["taladro de 5000W"],
            "no inventar taladro 5000W, pedir aclaración o informar que no existe", check)

    def case_E34_martillo_100kg(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            if prices and "100" in rl and "martillo" in rl:
                return "FAIL", f"inventó martillo de 100kg con precios: {prices[:2]}"
            no_match = _has_no_match(r)
            if no_match:
                return "PASS", "rechazó spec de martillo 100kg"
            if prices:
                return "WARN", "dio precios de martillo sin validar peso de 100kg"
            return "WARN", "respuesta ambigua ante martillo de 100kg"
        return self._run_case("E34", "anti_fraude",
            '"martillo Stanley plateado de 100kg" → peso imposible', ["martillo Stanley plateado de 100kg"],
            "rechazar spec imposible (peso > 5kg para martillo)", check)

    def case_E35_destornillador_laser_cuantico(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            if prices and ("láser" in rl or "laser" in rl or "cuántico" in rl):
                return "FAIL", f"inventó destornillador láser cuántico: {prices[:2]}"
            no_match = _has_no_match(r)
            if no_match:
                return "PASS", "indicó que destornillador láser cuántico no existe"
            if prices:
                return "WARN", "dio precios de otro destornillador sin negar el absurdo"
            return "WARN", "respuesta ambigua ante producto absurdo"
        return self._run_case("E35", "anti_fraude",
            '"destornillador láser cuántico" → producto imposible', ["destornillador láser cuántico"],
            "decir que no existe, no inventar precios", check)

    def case_E36_100_metros_de_tornillo(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            asks_clarif = any(kw in rl for kw in (
                "qué tipo", "medida", "longitud", "mm", "aclará", "cuántos"
            ))
            if prices and "100" in rl and ("metro" in rl or "m de" in rl):
                return "FAIL", f"inventó '100 metros de tornillo' con precios: {prices[:2]}"
            if asks_clarif:
                return "PASS", "pidió clarificación sobre medida/longitud"
            no_match = _has_no_match(r)
            if no_match:
                return "PASS", "informó que 100 metros de tornillo no existe"
            if prices:
                return "WARN", "dio precios de tornillos sin validar longitud imposible"
            return "WARN", "respuesta vaga"
        return self._run_case("E36", "anti_fraude",
            '"100 metros de tornillo" → longitud imposible', ["100 metros de tornillo"],
            "pedir clarificación o rechazar longitud imposible (>800mm)", check)

    def case_E37_broca_de_oro(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            if prices and "oro" in rl and "broca" in rl:
                return "FAIL", f"inventó broca de oro: {prices[:2]}"
            no_match = _has_no_match(r)
            asks_clarif = any(kw in rl for kw in ("material", "tipo de broca", "acero", "hss"))
            if no_match or asks_clarif:
                return "PASS", "informó que no hay brocas de oro o pidió material real"
            if prices:
                return "WARN", "dio precios de broca sin negar el color 'oro'"
            return "WARN", "respuesta ambigua ante broca de oro"
        return self._run_case("E37", "anti_fraude",
            '"broca de oro de 8mm" → material imposible', ["broca de oro de 8mm"],
            "no tener brocas de oro — informar o pedir material real", check)

    def case_E38_alicate_inflable(self):
        def check(rs):
            r = rs[-1]
            rl = r.lower()
            prices = _extract_prices(r)
            if prices and "inflabl" in rl:
                return "FAIL", f"inventó alicate inflable: {prices[:2]}"
            no_match = _has_no_match(r)
            if no_match:
                return "PASS", "indicó que alicate inflable no existe"
            if prices:
                return "WARN", "dio precios de alicate sin negar 'inflable'"
            asks_clarif = any(kw in rl for kw in ("qué tipo", "alicate", "pinza"))
            if asks_clarif:
                return "WARN", "preguntó tipo de alicate sin negar el absurdo"
            return "WARN", "respuesta ambigua"
        return self._run_case("E38", "anti_fraude",
            '"alicate inflable" → producto imposible', ["alicate inflable"],
            "decir que no existe, no inventar precios", check)

    # ── CATEGORÍA 6 — Multiturno largo ───────────────────────────────────

    def case_E39_taladro_5_turnos(self):
        turns = [
            "necesito un taladro",
            "Bosch",
            "qué horarios tienen?",
            "agregame 5 brocas 8mm",
            "cuánto el total?",
        ]
        def check(rs):
            r5 = rs[-1].lower()
            has_taladro = "taladro" in r5
            has_broca = "broca" in r5 or "mecha" in r5
            prices = _extract_prices(rs[-1])
            total = max(prices) if prices else 0
            faq_ok = "horario" in rs[2].lower() or any(kw in rs[2].lower() for kw in
                ("lunes", "viernes", "abierto", "horario", "pendiente"))
            if has_taladro and has_broca and total > 0:
                return "PASS", f"carrito final: taladro+brocas, total=${total:,}, FAQ ok={faq_ok}"
            if has_taladro or has_broca:
                return "WARN", f"carrito parcial: taladro={has_taladro} brocas={has_broca}"
            return "FAIL", "turno 5 no muestra taladro ni brocas en el total"
        return self._manual_multiturn("E39", "multiturno_largo",
            "5 turnos: taladro → Bosch → FAQ → agregar brocas → total", turns,
            "total turno 5 incluye taladro + 5 brocas 8mm", check)

    def case_E40_modificacion_cantidad(self):
        turns = [
            "hola",
            "presupuesto: 50 tornillos M6",
            "y 30 M8",
            "no, mejor 50 M8",
            "cerralo así",
        ]
        def check(rs):
            r5 = rs[-1].lower()
            # Turno 5 debe mostrar cierre con 50xM6 y 50xM8 (no 30xM8)
            has_cierre = any(kw in r5 for kw in ("recibimos", "equipo", "revisión", "confirmad"))
            r4 = rs[3].lower()
            has_50_m8 = "50" in r4 and "m8" in r4
            has_30_m8 = "30" in r4 and "m8" in r4 and "50" not in r4
            if has_cierre and not has_30_m8:
                return "PASS", "carrito modificado correctamente (50xM8, no 30xM8)"
            if has_30_m8:
                return "FAIL", "no aplicó modificación — carrito tiene 30xM8 en vez de 50"
            if has_cierre:
                return "WARN", "cerró pedido pero sin confirmar corrección de cantidad"
            return "WARN", "turno 5 no cerró pedido claramente"
        return self._manual_multiturn("E40", "multiturno_largo",
            "5 turnos: inicio → M6 → M8 → MODIFICAR a 50xM8 → cerrar", turns,
            "carrito final: 50xM6 + 50xM8 (la corrección aplica)", check)

    def case_E41_destornillador_martillo(self):
        turns = [
            "destornillador philips",
            "cualquiera está bien",
            "agregame martillo",
            "stanley",
            "presupuesto?",
        ]
        def check(rs):
            r5 = rs[-1].lower()
            has_destornillador = "destornillador" in r5
            has_martillo = "martillo" in r5
            prices = _extract_prices(rs[-1])
            if has_destornillador and has_martillo and prices:
                return "PASS", "turno 5 muestra destornillador + martillo con precios"
            if has_destornillador or has_martillo:
                return "WARN", f"turno 5 parcial: dest={has_destornillador} mart={has_martillo}"
            return "FAIL", "turno 5 no muestra ninguno de los 2 productos"
        return self._manual_multiturn("E41", "multiturno_largo",
            "5 turnos: destornillador → cualquiera → agregar martillo → stanley → presupuesto", turns,
            "presupuesto final con destornillador + martillo Stanley", check)

    def case_E42_mecha_concreto_factura(self):
        turns = [
            "necesito mecha 8mm",
            "para concreto",
            "10 unidades",
            "factura A?",
            "ok dame el total",
        ]
        def check(rs):
            r5 = rs[-1].lower()
            prices = _extract_prices(rs[-1])
            has_mecha = "mecha" in r5 or "broca" in r5
            max_price = max(prices) if prices else 0
            faq_ok = "factura" in rs[3].lower() and " a" in rs[3].lower()
            if has_mecha and 50_000 <= max_price <= 200_000:
                return "PASS", f"10 mechas para concreto, precio OK ${max_price:,}, FAQ={faq_ok}"
            if has_mecha and max_price > 200_000:
                return "WARN", f"mecha encontrada pero precio alto ${max_price:,}"
            if has_mecha:
                return "WARN", "encontró mecha pero sin precio en el total"
            return "FAIL", "turno 5 no muestra mechas para concreto"
        return self._manual_multiturn("E42", "multiturno_largo",
            "5 turnos: mecha 8mm → concreto → 10u → factura A → total", turns,
            "10 mechas para concreto + responde factura A + precio $50k-$200k", check)

    def case_E43_datos_cliente_reserva(self):
        turns = [
            "hola",
            "te paso datos",
            "Juan Pérez, 11-5555-1234, Buenos Aires",
            "necesito 5 sierras de mano",
            "podés reservar?",
        ]
        def check(rs):
            r5 = rs[-1].lower()
            has_reserva = any(kw in r5 for kw in (
                "reserva", "guardar", "separar", "apartar", "equipo",
                "coordinar", "contactar", "juan", "datos"
            ))
            has_sierra = "sierra" in rs[3].lower() or "sierra" in r5
            if has_reserva and has_sierra:
                return "PASS", "manejó datos del cliente + sierras + solicitud de reserva"
            if has_reserva:
                return "WARN", "procesó reserva pero sin referencia a sierras"
            if has_sierra:
                return "WARN", "encontró sierras pero no procesó reserva con datos del cliente"
            return "FAIL", "no procesó datos del cliente ni solicitud de reserva"
        return self._manual_multiturn("E43", "multiturno_largo",
            "5 turnos: saludo → datos → Juan Pérez → sierras → reservar", turns,
            "usar datos del cliente para crear_reserva o pedir más info", check)

    # ── CATEGORÍA 7 — Casos WhatsApp típicos ─────────────────────────────

    def case_E44_mensajes_fragmentados_taladro(self):
        turns = ["hola", "queria saber", "si tenes", "taladros bosch"]
        def check(rs):
            r = rs[-1].lower()
            has_taladro = "taladro" in r
            has_bosch = "bosch" in r
            if has_taladro and has_bosch:
                return "PASS", "mantuvo contexto a través de 4 mensajes fragmentados → taladros Bosch"
            if has_taladro:
                return "WARN", "encontró taladros pero sin Bosch específico"
            return "FAIL", "no entiende query fragmentado 'hola / queria saber / si tenes / taladros bosch'"
        return self._run_case("E44", "whatsapp_fragmentado",
            "4 mensajes cortos → taladros Bosch", turns,
            "entender query fragmentado en 4 turnos", check)

    def case_E45_martillo_mango_fibra(self):
        turns = ["cuanto", "el martillo", "de mango fibra", "5kg"]
        def check(rs):
            r = rs[-1].lower()
            has_martillo = "martillo" in r
            has_fibra = "fibra" in r or "mango" in r
            prices = _extract_prices(rs[-1])
            if has_martillo and (has_fibra or prices):
                return "PASS", "armó query de martillo mango fibra desde mensajes fragmentados"
            if has_martillo:
                return "WARN", "encontró martillo pero sin referencia a mango fibra"
            return "FAIL", "no armó el query de martillo mango fibra"
        return self._run_case("E45", "whatsapp_fragmentado",
            "4 mensajes: cuanto / el martillo / de mango fibra / 5kg", turns,
            "armar query de martillo mango fibra desde fragmentos", check)

    def case_E46_mechas_de_8_10_unidades(self):
        turns = ["pregunta rapida", "tenes mechas", "de 8", "varias", "10"]
        def check(rs):
            r = rs[-1].lower()
            has_mecha = "mecha" in r or "broca" in r
            has_8 = "8" in r
            has_10 = "10" in r
            if has_mecha and (has_8 or has_10):
                return "PASS", "entendió '10 mechas de 8mm' desde mensajes fragmentados"
            if has_mecha:
                return "WARN", "encontró mechas pero sin dimensión 8mm ni cantidad 10"
            return "FAIL", "no entendió '10 mechas de 8mm' fragmentado"
        return self._run_case("E46", "whatsapp_fragmentado",
            "5 mensajes → 10 mechas de 8mm", turns,
            "entender pedido fragmentado: 10 mechas de 8mm", check)

    def case_E47_mostrame_los_caros(self):
        turns = ["si tenes", "mostrame", "los caros"]
        def check(rs):
            r = rs[-1].lower()
            asks_clarif = any(kw in r for kw in (
                "qué producto", "qué buscás", "cuál", "de qué", "especificá"
            ))
            prices = _extract_prices(rs[-1])
            if asks_clarif:
                return "PASS", "pidió aclaración ante 'mostrame los caros' sin contexto"
            if prices:
                return "WARN", "mostró productos caros sin saber qué busca"
            return "WARN", "respuesta vaga ante query fragmentado y ambiguo"
        return self._run_case("E47", "whatsapp_fragmentado",
            '"si tenes / mostrame / los caros" → ambiguo', turns,
            "pedir aclaración o mostrar premium con contexto", check)

    def case_E48_tornillos_por_kilo_o_unidad(self):
        turns = ["dudita", "los tornillos M6", "vienen por kilo", "o por unidad?"]
        def check(rs):
            r = rs[-1].lower()
            has_answer = any(kw in r for kw in (
                "unidad", "kilo", "caja", "pack", "presentación", "bulto",
                "por unidad", "por kilo", "a granel"
            ))
            if has_answer:
                return "PASS", "respondió sobre forma de venta de tornillos M6"
            return "WARN", "no respondió sobre presentación (kilo vs unidad) de tornillos"
        return self._run_case("E48", "whatsapp_fragmentado",
            '"tornillos M6: por kilo o por unidad?" → forma de venta', turns,
            "responder sobre presentación/forma de venta", check)

    # ── CATEGORÍA 8 — Mensajes ambiguos ──────────────────────────────────

    def case_E49_una_sola_palabra_taladro(self):
        def check(rs):
            r = rs[-1].lower()
            has_taladro = "taladro" in r
            prices = _extract_prices(rs[-1])
            asks = any(kw in r for kw in ("percutor", "batería", "voltios", "marca", "tipo"))
            if has_taladro and (prices or asks):
                return "PASS", "mostró opciones o pidió aclaración de tipo de taladro"
            if has_taladro:
                return "WARN", "mencionó taladro pero sin opciones ni clarificación"
            return "FAIL", "no respondió con taladros ante una sola palabra"
        return self._run_case("E49", "ambiguedad",
            '"taladro" (una sola palabra)', ["taladro"],
            "pedir aclaración o mostrar opciones de taladro", check)

    def case_E50_si_sin_contexto(self):
        def check(rs):
            r = rs[-1].lower()
            if not r:
                return "FAIL", "respuesta vacía"
            asks = any(kw in r for kw in (
                "qué", "cuál", "contame", "de qué", "a qué", "podés", "especificá"
            ))
            prices = _extract_prices(rs[-1])
            if asks:
                return "PASS", "pidió contexto ante 'sí' sin antecedente"
            if prices:
                return "WARN", "inventó presupuesto ante 'sí' sin contexto"
            return "WARN", "respuesta sin pedir contexto ni inventar"
        return self._run_case("E50", "ambiguedad",
            '"sí" (sin contexto previo)', ["sí"],
            "pedir más información, no inventar", check)

    def case_E51_todo(self):
        def check(rs):
            r = rs[-1].lower()
            asks = any(kw in r for kw in (
                "qué", "especificá", "contame", "cuál", "de qué", "qué rubro"
            ))
            prices = _extract_prices(rs[-1])
            if asks:
                return "PASS", "pidió especificación ante 'todo' (ambigüedad total)"
            if prices and len(prices) > 10:
                return "FAIL", "mostró catálogo completo ante 'todo'"
            return "WARN", "respuesta vaga ante ambigüedad total"
        return self._run_case("E51", "ambiguedad",
            '"todo" (ambigüedad total)', ["todo"],
            "pedir especificación, no mostrar catálogo completo", check)

    def case_E52_barato(self):
        def check(rs):
            r = rs[-1].lower()
            asks = any(kw in r for kw in (
                "qué buscás", "qué producto", "qué necesitás", "de qué",
                "cuál", "especificá", "contame"
            ))
            if asks:
                return "PASS", "preguntó qué busca antes de mostrar productos baratos"
            prices = _extract_prices(rs[-1])
            if prices:
                return "WARN", "mostró productos sin saber qué buscan"
            return "WARN", "respuesta vaga ante 'barato' sin contexto"
        return self._run_case("E52", "ambiguedad",
            '"barato" (sin contexto)', ["barato"],
            "preguntar qué busca, no mostrar productos random", check)

    def case_E53_el_de_bosch(self):
        def check(rs):
            r = rs[-1].lower()
            asks = any(kw in r for kw in (
                "qué producto", "cuál", "taladro", "amoladora", "sierra",
                "qué herramienta", "qué bosch", "de bosch"
            ))
            has_bosch = "bosch" in r
            if asks and has_bosch:
                return "PASS", "preguntó qué producto Bosch sin contexto"
            if asks:
                return "WARN", "preguntó pero sin mencionar Bosch"
            prices = _extract_prices(rs[-1])
            if prices and has_bosch:
                return "PASS", "mostró productos Bosch directamente"
            return "WARN", "respuesta ambigua ante 'el de Bosch' sin contexto"
        return self._run_case("E53", "ambiguedad",
            '"el de Bosch" (sin saber cuál)', ["el de Bosch"],
            "preguntar qué producto Bosch sin contexto", check)

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
        print("REPORTE — DEMO TEST SUITE EXTENDED — FERRETERÍA BOT")
        print("=" * 80)

        print(f"\n{'ID':<5} {'ST':<5} {'CATEGORÍA':<26} {'DESCRIPCIÓN':<34} NOTAS")
        print("-" * 115)
        for r in self.results:
            icon = icons[r.status]
            desc = r.description[:33]
            notes = r.notes[:46]
            print(f"{r.case_id:<5} {icon} {r.status:<3} {r.category:<26} {desc:<34} {notes}")

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
                    print(f"       respuesta: {r.actual_response[:100]}")
                for r in warns:
                    print(f"    ⚠️  {r.case_id}: {r.description[:60]}")
                    print(f"       → {r.notes}")

        pct = lambda n: f"{n/total*100:.0f}%" if total else "0%"
        print(f"\n{'─'*80}")
        print("RESUMEN EJECUTIVO")
        print(f"  Total casos : {total}")
        print(f"  ✅ PASS     : {totals['PASS']} ({pct(totals['PASS'])})")
        print(f"  ⚠️  WARN     : {totals['WARN']} ({pct(totals['WARN'])})")
        print(f"  ❌ FAIL     : {totals['FAIL']} ({pct(totals['FAIL'])})")
        print(f"  💥 ERROR    : {totals['ERROR']} ({pct(totals['ERROR'])})")
        print(f"  Tiempo total: {total_time:.1f}s")
        print(f"  run_id      : {self.run_id}")
        print("=" * 80)

    def run_all(self) -> int:
        icons = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "ERROR": "💥"}
        cases = sorted(
            [getattr(self, n) for n in dir(self) if n.startswith("case_E")],
            key=lambda f: f.__name__,
        )
        print(f"Corriendo {len(cases)} casos — run_id={self.run_id}\n")
        for fn in cases:
            result = fn()
            icon = icons[result.status]
            print(f"  {icon} [{result.case_id}] {result.description[:58]:<58} ({result.duration_seconds}s)")
        print()
        self._print_report()
        self.bot.close()
        fails = sum(1 for r in self.results if r.status in ("FAIL", "ERROR"))
        return 1 if fails > 0 else 0


if __name__ == "__main__":
    suite = DemoTestSuiteExtended()
    raise SystemExit(suite.run_all())
