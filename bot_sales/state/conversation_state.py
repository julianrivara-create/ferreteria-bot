from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json

# Valid states
VALID_STATES = {
    "idle",
    "browsing",
    "quote_drafting",
    "awaiting_clarification",
    "awaiting_customer_confirmation",
    "review_requested",
    "escalated",
    "closed",
}


@dataclass
class CustomerProfile:
    name: Optional[str] = None
    contact: Optional[str] = None
    email: Optional[str] = None
    zone: Optional[str] = None


@dataclass
class ConversationStateV2:
    state: str = "idle"
    active_quote_id: Optional[str] = None
    pending_questions: List[str] = field(default_factory=list)
    last_interpretation: Optional[Dict[str, Any]] = field(default_factory=dict)
    confirmed_constraints: Dict[str, Any] = field(default_factory=dict)
    rejected_options: List[str] = field(default_factory=list)
    last_search_query_struct: Optional[Dict[str, Any]] = None
    last_candidate_skus: List[str] = field(default_factory=list)
    customer_profile: CustomerProfile = field(default_factory=CustomerProfile)
    acceptance_pending: bool = False
    escalation_status: Optional[str] = None
    handoff_id: Optional[str] = None
    # Legacy compat fields (read-only during migration, do not write new code to these)
    _legacy_active_quote: Optional[List[Dict[str, Any]]] = field(default=None, repr=False)
    _legacy_quote_state: Optional[str] = field(default=None, repr=False)

    def validate_state(self) -> None:
        if self.state not in VALID_STATES:
            raise ValueError(f"Invalid state: {self.state!r}. Must be one of {VALID_STATES}")

    def transition(self, new_state: str) -> None:
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid target state: {new_state!r}")
        self.state = new_state

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Remove private fields from serialization
        d.pop("_legacy_active_quote", None)
        d.pop("_legacy_quote_state", None)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConversationStateV2":
        if not isinstance(d, dict):
            return cls()
        d = dict(d)
        # Extract nested CustomerProfile
        cp_data = d.pop("customer_profile", {}) or {}
        if isinstance(cp_data, dict):
            cp = CustomerProfile(**{k: v for k, v in cp_data.items() if k in CustomerProfile.__dataclass_fields__})
        else:
            cp = CustomerProfile()
        # Filter to known fields only
        known = {k for k in cls.__dataclass_fields__ if not k.startswith("_")}
        filtered = {k: v for k, v in d.items() if k in known}
        filtered["customer_profile"] = cp
        return cls(**filtered)

    @classmethod
    def from_json(cls, s: str) -> "ConversationStateV2":
        try:
            return cls.from_dict(json.loads(s))
        except Exception:
            return cls()

    @classmethod
    def from_legacy_session(cls, sess: Dict[str, Any]) -> "ConversationStateV2":
        """Upgrade a legacy session dict to ConversationStateV2."""
        legacy_quote_state = sess.get("quote_state", "idle")
        state_map = {
            "open": "quote_drafting",
            "accepted": "awaiting_customer_confirmation",
            "review_requested": "review_requested",
            "closed": "closed",
        }
        new_state = state_map.get(legacy_quote_state, "idle")
        return cls(
            state=new_state,
            _legacy_active_quote=sess.get("active_quote"),
            _legacy_quote_state=legacy_quote_state,
        )


class StateStore:
    """Thin wrapper to load/save ConversationStateV2 from the existing session dict."""

    @staticmethod
    def load(sess: Dict[str, Any]) -> ConversationStateV2:
        """Load state from session dict, upgrading legacy format if needed."""
        raw = sess.get("_state_v2")
        if isinstance(raw, dict):
            return ConversationStateV2.from_dict(dict(raw))
        elif isinstance(raw, str):
            return ConversationStateV2.from_json(raw)
        # No V2 state yet — check for legacy keys
        if "quote_state" in sess or "active_quote" in sess:
            return ConversationStateV2.from_legacy_session(sess)
        return ConversationStateV2()

    @staticmethod
    def save(sess: Dict[str, Any], state: ConversationStateV2) -> None:
        """Persist state into session dict (in-memory). DB persistence happens via existing session save."""
        sess["_state_v2"] = state.to_dict()
        # Keep legacy keys in sync during migration so old code doesn't break
        legacy_state_map = {
            "idle": "open",
            "browsing": "open",
            "quote_drafting": "open",
            "awaiting_clarification": "open",
            "awaiting_customer_confirmation": "accepted",
            "review_requested": "review_requested",
            "escalated": "open",
            "closed": "closed",
        }
        sess["quote_state"] = legacy_state_map.get(state.state, "open")
        if state._legacy_active_quote is not None:
            sess["active_quote"] = state._legacy_active_quote
