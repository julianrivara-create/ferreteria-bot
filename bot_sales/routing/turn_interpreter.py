"""
TurnInterpreter — single LLM call per turn that replaces IntentRouter + AcceptanceDetector.
Returns a rich TurnInterpretation with intent, entities, tone, and quote context.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "product_search",
    "policy_faq",
    "quote_modify",
    "quote_accept",
    "quote_reject",
    "escalate",
    "off_topic",
    "small_talk",
    "customer_info",
    "unknown",
}

VALID_TONES = {"neutral", "frustrated", "urgent"}
VALID_SEARCH_MODES = {"exact", "browse", "by_use", None}
VALID_POLICY_TOPICS = {
    "horario", "envio", "garantia", "factura", "devolucion", "reserva", "pago", None
}
VALID_ESCALATION_REASONS = {"explicit_request", "negotiation", "frustration", None}


@dataclass
class EntityBundle:
    product_terms: List[str] = field(default_factory=list)
    use_case: Optional[str] = None
    material: Optional[str] = None
    dimensions: Dict[str, Any] = field(default_factory=dict)
    qty: Optional[int] = None
    brand: Optional[str] = None
    budget: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "EntityBundle":
        if not isinstance(d, dict):
            return cls()
        return cls(
            product_terms=d.get("product_terms") or [],
            use_case=d.get("use_case"),
            material=d.get("material"),
            dimensions=d.get("dimensions") or {},
            qty=d.get("qty"),
            brand=d.get("brand"),
            budget=d.get("budget"),
        )

    def to_dict(self) -> dict:
        return {
            "product_terms": self.product_terms,
            "use_case": self.use_case,
            "material": self.material,
            "dimensions": self.dimensions,
            "qty": self.qty,
            "brand": self.brand,
            "budget": self.budget,
        }


@dataclass
class QuoteReference:
    references_existing_quote: bool = False
    line_hints: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "QuoteReference":
        if not isinstance(d, dict):
            return cls()
        return cls(
            references_existing_quote=bool(d.get("references_existing_quote", False)),
            line_hints=d.get("line_hints") or [],
        )

    def to_dict(self) -> dict:
        return {
            "references_existing_quote": self.references_existing_quote,
            "line_hints": self.line_hints,
        }


@dataclass
class TurnInterpretation:
    intent: str = "unknown"
    confidence: float = 0.0
    tone: str = "neutral"
    policy_topic: Optional[str] = None
    search_mode: Optional[str] = None
    entities: EntityBundle = field(default_factory=EntityBundle)
    quote_reference: QuoteReference = field(default_factory=QuoteReference)
    reset_signal: bool = False
    # B21 additions
    compound_message: bool = False
    # True when the turn contains 2+ distinct commands (e.g. "dame el primero. agregame martillo").
    # Handler decomposition lives in B22; this flag signals that decomposition is needed.
    escalation_reason: Optional[str] = None
    # Subtype when intent="escalate":
    #   "explicit_request" — client explicitly asks for a human
    #   "negotiation"      — client attempts price negotiation (V8 migration)
    #   "frustration"      — sustained frustrated tone
    #   None               — intent != escalate
    referenced_offer_index: Optional[int] = None
    # 0-indexed position in last_offered_products the client is referring to
    # ("el primero" → 0, "el segundo" → 1). None when no referential or no offered context.
    # B22a addition
    sub_commands: List[str] = field(default_factory=list)
    # When compound_message=true, the individual sub-commands as they appear in the original
    # message, preserving phrasing and order. Max 5 elements (sanity bound).
    # Example: "dame el primero, agregame martillo" →
    #   sub_commands=["dame el primero", "agregame martillo"]
    # Empty list when compound_message=false.
    # L2 addition
    items: Optional[List[str]] = None
    # When the message is a product list (numbered, bulleted, or 4+ items), each item
    # pre-extracted with its quantity. None when message is NOT a product list.
    # Example: "1) 5 mechas 6mm\n2) 1 martillo" → ["5 mechas 6mm", "1 martillo"]

    def is_low_confidence(self) -> bool:
        return self.confidence < 0.55

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "tone": self.tone,
            "policy_topic": self.policy_topic,
            "search_mode": self.search_mode,
            "entities": self.entities.to_dict(),
            "quote_reference": self.quote_reference.to_dict(),
            "reset_signal": self.reset_signal,
            "compound_message": self.compound_message,
            "escalation_reason": self.escalation_reason,
            "referenced_offer_index": self.referenced_offer_index,
            "sub_commands": self.sub_commands,
            "items": self.items,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TurnInterpretation":
        if not isinstance(d, dict):
            return cls()
        intent = d.get("intent", "unknown")
        if intent not in VALID_INTENTS:
            intent = "unknown"
        tone = d.get("tone", "neutral")
        if tone not in VALID_TONES:
            tone = "neutral"
        confidence = float(d.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        policy_topic = d.get("policy_topic")
        if policy_topic not in VALID_POLICY_TOPICS:
            policy_topic = None
        search_mode = d.get("search_mode")
        if search_mode not in VALID_SEARCH_MODES:
            search_mode = None
        escalation_reason = d.get("escalation_reason")
        if escalation_reason not in VALID_ESCALATION_REASONS:
            escalation_reason = None
        raw_ref_idx = d.get("referenced_offer_index")
        if raw_ref_idx is not None:
            try:
                raw_ref_idx = int(raw_ref_idx)
                if raw_ref_idx < 0:
                    raw_ref_idx = None
            except (TypeError, ValueError):
                raw_ref_idx = None
        raw_sub = d.get("sub_commands")
        if not isinstance(raw_sub, list):
            sub_commands: List[str] = []
        else:
            sub_commands = [s for s in raw_sub if isinstance(s, str)][:5]
        raw_items = d.get("items")
        if isinstance(raw_items, list):
            items: Optional[List[str]] = [s for s in raw_items if isinstance(s, str) and s.strip()][:20]
            if not items:
                items = None
        else:
            items = None
        return cls(
            intent=intent,
            confidence=confidence,
            tone=tone,
            policy_topic=policy_topic,
            search_mode=search_mode,
            entities=EntityBundle.from_dict(d.get("entities") or {}),
            quote_reference=QuoteReference.from_dict(d.get("quote_reference") or {}),
            reset_signal=bool(d.get("reset_signal", False)),
            compound_message=bool(d.get("compound_message", False)),
            escalation_reason=escalation_reason,
            referenced_offer_index=raw_ref_idx,
            sub_commands=sub_commands,
            items=items,
        )

    @classmethod
    def unknown(cls) -> "TurnInterpretation":
        return cls(intent="unknown", confidence=0.0)


_SYSTEM_PROMPT = """Sos un clasificador de mensajes para un chatbot de ferretería argentina.
Dado un mensaje del cliente, devolvé SOLO JSON válido con esta estructura exacta. Sin texto adicional.

{
  "intent": "product_search|policy_faq|quote_modify|quote_accept|quote_reject|escalate|off_topic|small_talk|customer_info|unknown",
  "confidence": 0.0,
  "tone": "neutral|frustrated|urgent",
  "policy_topic": "horario|envio|garantia|factura|devolucion|reserva|pago|null",
  "search_mode": "exact|browse|by_use|null",
  "entities": {
    "product_terms": [],
    "use_case": null,
    "material": null,
    "dimensions": {},
    "qty": null,
    "brand": null,
    "budget": null
  },
  "quote_reference": {
    "references_existing_quote": false,
    "line_hints": []
  },
  "reset_signal": false,
  "compound_message": false,
  "sub_commands": [],
  "escalation_reason": "explicit_request|negotiation|frustration|null",
  "referenced_offer_index": null,
  "items": null
}

=== REGLAS GENERALES ===
- confidence < 0.6 si el mensaje es ambiguo
- search_mode="by_use" si el cliente describe un uso en vez de nombrar un producto
- search_mode="browse" si pide ver opciones sin producto específico
- policy_topic solo cuando la pregunta es sobre política operativa de la tienda
- tone="frustrated" si hay señales de enojo o repetición ("ya te dije", "cuántas veces", "no entendés")
- tone="urgent" si hay presión de tiempo ("para hoy", "urgente", "ya")
- quote_accept o quote_reject para CUALQUIER aceptación o rechazo, no solo "ok" o "dale"
- reset_signal=true si el cliente quiere cancelar todo y empezar de cero
- intent="customer_info" si el cliente comparte su nombre, empresa, teléfono u otros datos personales ("me llamo", "soy de", "mi número es", "trabajo en")

=== REGLA NEGOCIACIÓN — ALTA PRIORIDAD (V8) ===
Si el cliente intenta negociar el precio bajo CUALQUIER forma — pide descuento, rebaja, mejor
precio, promoción, hace contraoferta, dice que está caro y propone un número alternativo,
presiona por bajar el monto — la clasificación ES:
  intent: "escalate"
  escalation_reason: "negotiation"
  confidence: >= 0.75

Esta regla es PRIORITARIA. Si el mensaje incluye otro contenido además de la negociación,
igual gana "escalate". El bot NO negocia precios, siempre escala a humano.

Ejemplos que SÍ son negociación → escalate/negotiation:
- "me bajás 15% si llevo 5?"
- "nahh, está caro, hacele algo"
- "en otro lado lo conseguí más barato" (presiona implícitamente)
- "15% off?"
- "dame mejor precio"
- "qué hacés con esto, 50 lukas?"
- "si te llevo los dos me das algo?"
- "podés tirar el precio un poco?"

Ejemplos que NO son negociación (no escalan por esta regla):
- "es caro pero me lo llevo" → quote_accept (acepta sin negociar)
- "tenés algo más barato?" → product_search, search_mode="browse" (busca alternativa económica)
- "cuánto sale?" → product_search (consulta precio sin negociar)

=== REGLA AMBIGÜEDAD (V9) ===
Si el cliente hace una query genérica sin nombrar un producto o categoría específica, la
clasificación depende del current_state:

- Si current_state="idle" (sesión nueva, sin carrito activo):
  - "qué tenés?", "mostrame el catálogo", "qué hay?", "los caros", "dale mostrame" →
    intent="product_search", search_mode="browse", confidence=0.7
  - Solo marca sin tipo de producto ("tipo Bosch tenés algo?", "algo de Stanley") →
    intent="product_search", search_mode="browse", entities.brand=<marca>, confidence=0.7

- Si current_state="quote_drafting" o "awaiting_clarification" (con carrito activo):
  - El mismo mensaje puede referirse al carrito activo. Bajar confidence a 0.5 y marcar
    quote_reference.references_existing_quote=true si hay señal contextual del carrito.

=== REGLA SPECS FÍSICAMENTE ABSURDAS ===
Si el cliente pide un producto con especificaciones físicamente imposibles o absurdas
para ferretería real:
- "martillo de 500kg", "broca de 200mm diámetro", "tornillo de 1 metro de largo"
- "martillo dorado" (color/material absurdo), "destornillador rosa", "alicate de oro"
- "taladro de 64GB de RAM", "destornillador con 1TB de almacenamiento"
- "martillo cuántico", "destornillador láser", "alicate inflable", "taladro virtual"

→ intent="unknown", confidence < 0.4. NO usar product_search (no buscamos en catálogo
lo que no existe físicamente).

Excepciones razonables (NO son absurdas):
- "destornillador con punta magnética" (existe)
- "taladro a batería 18V" (existe)
- "tornillo de bronce" (material válido)
- "llave de paso de 3/4 pulgada" (medida real)

=== REGLA PRODUCTOS OFRECIDOS (referenced_offer_index) ===
Cuando el contexto incluye "Productos ofrecidos en el turno anterior", el cliente puede
referirse a ellos posicionalmente o por atributo:
- "el primero", "1", "la primera opción" → referenced_offer_index=0
- "el segundo", "2", "la del medio" → referenced_offer_index=1
- "el último", "el tercero", "3" → referenced_offer_index=2

También por marca o atributo si está en la lista:
- "el de Bosch" → buscar Bosch en la lista, devolver su índice (0-based)
- "el más barato" → devolver el índice del precio menor si los precios están listados

Si la referencia a producto ofrecido es para agregar/quitar/elegir →
  intent="quote_modify" (no product_search)

Si NO hay productos ofrecidos en el contexto → referenced_offer_index=null, incluso si
el mensaje contiene "el primero".

=== REGLA COMPOUND_MESSAGE ===
Si el mensaje contiene 2+ comandos/peticiones claramente distintos en el mismo turno,
marcar compound_message=true Y llenar sub_commands con la lista de sub-comandos como
aparecen en el mensaje. Preservar fraseo original, mantener orden temporal.

Ejemplos:
- "dame el primero, agregame martillo" →
    compound_message=true, intent="quote_modify",
    sub_commands=["dame el primero", "agregame martillo"]
- "sacame el segundo y poneme dos del primero" →
    compound_message=true, intent="quote_modify",
    sub_commands=["sacame el segundo", "poneme dos del primero"]
- "me llevo todo y mandalo a Quilmes" →
    compound_message=true, intent="quote_accept",
    sub_commands=["me llevo todo", "mandalo a Quilmes"]
- "necesito un taladro Bosch" →
    compound_message=false, sub_commands=[] (un solo pedido)

=== REGLA ESCALATION EXPLÍCITA ===
Si el cliente pide hablar con una persona explícitamente ("quiero hablar con alguien",
"pasame con un humano", "necesito un asesor", "hablá con mi encargado") →
  intent="escalate", escalation_reason="explicit_request", confidence >= 0.8

=== REGLA FRUSTRACIÓN ===
Si el tone="frustrated" Y el intent debería ser escalate →
  escalation_reason="frustration"

=== REGLA QUOTE_ACCEPT / QUOTE_REJECT ===
Mantener cobertura completa:
- quote_accept: "dale", "ok lo hacemos", "perfecto mandalo", "me lo llevo", "sí va",
  "cerralo", "vamos con eso", "le doy", "bueno", "sí hagámoslo", "va", "arrancamos",
  cualquier confirmación clara cuando hay carrito activo.
- quote_reject: "no no me sirve", "paso", "mejor no", "lo dejamos", "no gracias",
  cualquier rechazo claro.

=== REGLA ITEMS — LISTAS DE PRODUCTOS ===
Si el mensaje del cliente es una lista de productos (numerada, con bullets, o con 4+ items
separados por comas o saltos de línea), devolvé el campo "items" como lista de strings,
donde cada string es un item limpio con su cantidad.

Cuándo poblar "items":
- Lista numerada: "1) 5 mechas 6mm\n2) 1 martillo\n3) 2 metros manguera"
- Lista con bullets: "- mecha 6mm\n- mecha 8mm\n- destornillador phillips"
- Prosa con 4+ productos distintos: "necesito mechas 6, 8 y 10mm, un martillo y destornillador"

Formato de cada item: qty + producto limpio. Si no hay cantidad explícita, asumir 1.
Ejemplos correctos: "5 mechas 6mm", "1 martillo", "50 tornillos autoperforantes 3 pulgadas",
"2 metros manguera 1/2 pulgada".

Cuándo NO poblar "items" (dejar null):
- Consultas de 1 solo producto: "necesito un martillo", "taladro Bosch"
- Modificaciones de carrito: "dame el primero", "sacame el segundo"
- Preguntas, saludos, consultas de política

=== REGLA QUOTE_MODIFY SOLO CON CARRITO ===
intent="quote_modify" solo es válido cuando current_state="quote_drafting" o
"awaiting_clarification". Si current_state="idle", no hay carrito que modificar:
- "dame el primero" en idle → product_search (el cliente elige de algo que aún no tiene)
- "dame el primero" en quote_drafting → quote_modify (elige del carrito activo)
"""


class TurnInterpreter:
    """
    Single LLM call per turn that classifies intent and extracts entities.
    Replaces IntentRouter + AcceptanceDetector.
    """

    def __init__(self, llm_client):
        """
        llm_client: an object with a send_message(messages, model=..., max_tokens=...) method
                    compatible with ChatGPTClient.
        """
        self.llm = llm_client

    def interpret(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        current_state: str = "idle",
        last_offered_products: Optional[List[Dict[str, Any]]] = None,
    ) -> TurnInterpretation:
        """
        Classify the user turn into a TurnInterpretation.
        Uses a cheap, fast model call with max 1024 output tokens.
        Falls back to TurnInterpretation.unknown() on any error.

        last_offered_products: list of product dicts offered in the previous turn.
          Each dict should have keys: name, brand, price_formatted, sku.
          Pass [] (empty list) when no products were offered — do NOT pass None.
        """
        try:
            messages = self._build_messages(
                user_message, history or [], current_state, last_offered_products or []
            )
            # Save and override model/max_tokens for this cheap routing call
            orig_model = getattr(self.llm, "model", None)
            orig_max_tokens = getattr(self.llm, "max_tokens", None)
            orig_temperature = getattr(self.llm, "temperature", None)
            try:
                self.llm.model = "gpt-4o-mini"
                # max_tokens=1024 supports multi-item lists up to ~25 items
                # without JSON truncation. Bug history: 200 was truncating
                # JSON for 5+ item lists, causing JSONDecodeError → intent=unknown
                # → fallback chain. See PENDIENTES.md "TurnInterpreter trunca JSON".
                self.llm.max_tokens = 1024
                self.llm.temperature = 0.0
                response = self.llm.send_message(messages=messages)
            finally:
                self.llm.model = orig_model
                self.llm.max_tokens = orig_max_tokens
                self.llm.temperature = orig_temperature
            return self._parse_response(response)
        except Exception as exc:
            logger.warning("TurnInterpreter failed: %s", exc)
            return TurnInterpretation.unknown()

    def _build_messages(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        current_state: str,
        last_offered_products: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        # Last 3 turns of history for context
        recent = history[-6:] if len(history) > 6 else history
        context_lines = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                prefix = "Cliente" if role == "user" else "Bot"
                context_lines.append(f"{prefix}: {content[:120]}")

        context_str = "\n".join(context_lines) if context_lines else "(sin historial)"
        user_content = (
            f"Estado actual de la conversación: {current_state}\n"
            f"Historial reciente:\n{context_str}\n\n"
            f"Mensaje del cliente: {user_message}"
        )

        if last_offered_products:
            offered_lines = []
            for i, p in enumerate(last_offered_products):
                name = p.get("name") or p.get("model") or "?"
                brand = p.get("brand") or p.get("proveedor") or ""
                price = p.get("price_formatted") or "?"
                brand_str = f" ({brand})" if brand else ""
                offered_lines.append(f"{i + 1}. {name}{brand_str} — {price}")
            offered_str = "\n".join(offered_lines)
            user_content += f"\n\nProductos ofrecidos en el turno anterior:\n{offered_str}"

        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, response: Any) -> TurnInterpretation:
        """Extract JSON from LLM response and parse into TurnInterpretation."""
        # Handle different response shapes from ChatGPTClient
        text = ""
        if isinstance(response, str):
            text = response
        elif isinstance(response, dict):
            # OpenAI-style response dict
            choices = response.get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "")
            else:
                text = response.get("content", "") or response.get("text", "")
        elif hasattr(response, "content"):
            text = str(response.content)

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("TurnInterpreter JSON parse failed text=%r error=%s", text[:300], exc)
            return TurnInterpretation.unknown()
        return TurnInterpretation.from_dict(parsed)
