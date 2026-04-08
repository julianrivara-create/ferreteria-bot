"""High-level quote persistence service for ferreteria runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..persistence.quote_store import QuoteStore


BLOCKING_LINE_STATUSES = {"ambiguous", "unresolved", "blocked_by_missing_info"}


class QuoteService:
    """Map runtime quote items to durable quote records."""

    def __init__(self, store: QuoteStore, tenant_id: str = "ferreteria"):
        self.store = store
        self.tenant_id = tenant_id

    @staticmethod
    def map_runtime_status(item: Dict[str, Any]) -> str:
        status = item.get("status")
        if status == "resolved":
            if item.get("pack_note"):
                return "resolved_needs_confirmation"
            return "resolved_high_confidence"
        if status in BLOCKING_LINE_STATUSES:
            return status
        return "unresolved"

    @staticmethod
    def map_persisted_status(line_status: str) -> str:
        if line_status in ("resolved_high_confidence", "resolved_needs_confirmation"):
            return "resolved"
        return line_status

    @staticmethod
    def _infer_confidence(item: Dict[str, Any]) -> float:
        if item.get("status") == "resolved":
            return 0.95 if not item.get("pack_note") else 0.75
        if item.get("status") == "ambiguous":
            return 0.45
        if item.get("status") == "blocked_by_missing_info":
            return 0.25
        return 0.1

    def derive_quote_status(self, items: List[Dict[str, Any]], accepted: bool = False) -> str:
        if accepted:
            return "review_requested"
        if any(self.map_runtime_status(item) in BLOCKING_LINE_STATUSES for item in items):
            return "waiting_customer_input"
        return "open"

    def can_accept_quote(self, items: List[Dict[str, Any]]) -> bool:
        return all(self.map_runtime_status(item) not in BLOCKING_LINE_STATUSES for item in items)

    def _to_line_records(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        line_records: List[Dict[str, Any]] = []
        for item in items:
            products = item.get("products") or []
            selected = products[0] if products else {}
            alternatives = []
            for product in products[1:4]:
                alternatives.append({
                    "sku": product.get("sku"),
                    "name": product.get("model") or product.get("name"),
                    "category": product.get("category"),
                    "price": product.get("price_ars") or product.get("price"),
                })
            line_records.append(
                {
                    "id": item.get("line_id"),
                    "source_text": item.get("original", ""),
                    "normalized_text": item.get("normalized", ""),
                    "requested_qty": int(item.get("qty", 1) or 1),
                    "unit_hint": item.get("unit_hint"),
                    "line_status": self.map_runtime_status(item),
                    "confidence_score": self._infer_confidence(item),
                    "selected_sku": selected.get("sku"),
                    "selected_name": selected.get("model") or selected.get("name"),
                    "selected_category": selected.get("category"),
                    "selected_unit_price": int(item.get("unit_price")) if item.get("unit_price") is not None else None,
                    "presentation_note": item.get("pack_note"),
                    "clarification_prompt": item.get("clarification"),
                    "resolution_reason": item.get("notes"),
                    "family_id": item.get("family"),
                    "dimensions": item.get("dimensions") or {},
                    "missing_dimensions": item.get("missing_dimensions") or [],
                    "issue_type": item.get("issue_type"),
                    "clarification_attempts": int(item.get("clarification_attempts") or 0),
                    "last_targeted_dimension": item.get("last_targeted_dimension"),
                    "selected_via_substitute": bool(item.get("selected_via_substitute")),
                    "alternatives": alternatives,
                    "complementary": item.get("complementary") or [],
                }
            )
        return line_records

    def save_quote_snapshot(
        self,
        session_id: str,
        items: List[Dict[str, Any]],
        *,
        channel: str = "cli",
        customer_ref: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        accepted: bool = False,
        status_override: Optional[str] = None,
        event_type: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
        actor_type: str = "bot",
        actor_ref: Optional[str] = None,
        bot_response: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> Optional[str]:
        if not items and not status_override:
            return None

        with self.store.transaction():
            active = self.store.get_active_quote(session_id)
            quote_id = active["id"] if active else self.store.create_quote(session_id=session_id, channel=channel, customer_ref=customer_ref)
            existing_quote = self.store.get_quote(quote_id) or {}

            line_records = self._to_line_records(items)
            derived_status = status_override or self.derive_quote_status(items, accepted=accepted)
            resolved_total = 0
            has_resolved_price = False
            has_blocking = 0
            for item in items:
                if self.map_runtime_status(item) in BLOCKING_LINE_STATUSES:
                    has_blocking = 1
                subtotal = item.get("subtotal")
                if subtotal is not None:
                    resolved_total += int(round(float(subtotal)))
                    has_resolved_price = True

            update_fields = {
                "status": derived_status,
                "resolved_total_amount": resolved_total if has_resolved_price else None,
                "has_blocking_lines": has_blocking,
                "channel": channel,
                "customer_ref": customer_ref,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "customer_email": customer_email,
                "last_customer_message_at": existing_quote.get("last_customer_message_at"),
                "last_bot_message_at": None,
            }
            if accepted:
                update_fields["accepted_at"] = existing_quote.get("accepted_at") or datetime.utcnow().replace(microsecond=0).isoformat()
            if bot_response is not None:
                update_fields["last_bot_message_at"] = datetime.utcnow().replace(microsecond=0).isoformat()
            if user_message is not None:
                update_fields["last_customer_message_at"] = datetime.utcnow().replace(microsecond=0).isoformat()

            self.store.replace_quote_lines(quote_id, line_records)
            self.store.update_quote_header(quote_id, **update_fields)

            if active is None:
                self.store.append_event(quote_id, "quote_created", "system", payload={"session_id": session_id, "channel": channel})
            if user_message is not None:
                self.store.append_event(quote_id, "customer_message_received", "customer", actor_ref=customer_ref or session_id, payload={"message": user_message})
            if event_type:
                self.store.append_event(quote_id, event_type, actor_type, actor_ref=actor_ref, payload=event_payload or {})
            if bot_response is not None:
                self.store.append_event(quote_id, "bot_response_generated", "bot", payload={"message": bot_response})

            for item, line in zip(items, line_records):
                line_status = line["line_status"]
                if line_status in BLOCKING_LINE_STATUSES:
                    self.store.maybe_add_unresolved_term(
                        quote_id=quote_id,
                        quote_line_id=line["id"],
                        raw_text=item.get("original", ""),
                        normalized_text=item.get("normalized", ""),
                        status=line_status,
                        reason=item.get("notes") or item.get("clarification") or "pending_review",
                        inferred_family=item.get("family"),
                        missing_dimensions=item.get("missing_dimensions") or [],
                        issue_type=item.get("issue_type"),
                    )
            return quote_id

    def mark_reset(self, session_id: str, reason: str = "quote_reset") -> Optional[str]:
        with self.store.transaction():
            active = self.store.get_active_quote(session_id)
            if not active:
                return None
            self.store.update_quote_header(active["id"], status="closed_cancelled", closed_at=datetime.utcnow().replace(microsecond=0).isoformat())
            self.store.append_event(active["id"], "quote_reset", "bot", payload={"reason": reason})
            return active["id"]

    def _line_to_runtime_item(self, line: Dict[str, Any]) -> Dict[str, Any]:
        products = []
        if line.get("selected_name") or line.get("selected_sku"):
            products.append({
                "sku": line.get("selected_sku"),
                "model": line.get("selected_name"),
                "name": line.get("selected_name"),
                "category": line.get("selected_category"),
                "price_ars": line.get("selected_unit_price"),
                "price": line.get("selected_unit_price"),
            })
        for alt in line.get("alternatives", []):
            products.append({
                "sku": alt.get("sku"),
                "model": alt.get("name"),
                "name": alt.get("name"),
                "category": alt.get("category"),
                "price_ars": alt.get("price"),
                "price": alt.get("price"),
            })
        unit_price = line.get("selected_unit_price")
        qty = int(line.get("requested_qty") or 1)
        subtotal = unit_price * qty if unit_price is not None and line.get("line_status") == "resolved_high_confidence" else None
        return {
            "line_id": line.get("id"),
            "original": line.get("source_text", ""),
            "normalized": line.get("normalized_text", ""),
            "qty": qty,
            "qty_explicit": qty != 1,
            "unit_hint": line.get("unit_hint"),
            "status": self.map_persisted_status(line.get("line_status", "unresolved")),
            "products": products,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "pack_note": line.get("presentation_note"),
            "clarification": line.get("clarification_prompt"),
            "notes": line.get("resolution_reason"),
            "complementary": line.get("complementary") or [],
            "family": line.get("family_id"),
            "dimensions": line.get("dimensions") or {},
            "missing_dimensions": line.get("missing_dimensions") or [],
            "issue_type": line.get("issue_type"),
            "clarification_attempts": int(line.get("clarification_attempts") or 0),
            "last_targeted_dimension": line.get("last_targeted_dimension"),
            "selected_via_substitute": bool(line.get("selected_via_substitute")),
        }

    def build_runtime_items_from_lines(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        runtime_items = []
        for line in lines:
            runtime_items.append(self._line_to_runtime_item(line))
        return runtime_items

    def load_active_quote(self, session_id: str) -> Optional[Dict[str, Any]]:
        active = self.store.get_active_quote(session_id)
        if not active:
            return None
        runtime_items = self.build_runtime_items_from_lines(active.get("lines", []))
        return {"quote": active, "items": runtime_items}
