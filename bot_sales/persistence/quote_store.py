"""SQLite quote persistence for ferreteria runtime."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_col(name: str) -> str:
    """Validate that a column name contains only safe identifier characters."""
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


ACTIVE_QUOTE_STATUSES = (
    "open",
    "waiting_customer_input",
)


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class QuoteStore:
    """Persistent quote store backed by the tenant SQLite database."""

    def __init__(self, db_file: str, tenant_id: str = "ferreteria"):
        self.db_file = str(db_file)
        self.tenant_id = tenant_id
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._transaction_depth = 0
        self.ensure_schema()

    def ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'cli',
                customer_ref TEXT,
                customer_name TEXT,
                customer_phone TEXT,
                customer_email TEXT,
                status TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'ARS',
                resolved_total_amount INTEGER,
                has_blocking_lines INTEGER NOT NULL DEFAULT 0,
                accepted_at TEXT,
                closed_at TEXT,
                automation_state TEXT NOT NULL DEFAULT 'manual_only',
                automation_reason TEXT,
                automation_context_json TEXT,
                automation_updated_at TEXT,
                last_auto_followup_at TEXT,
                auto_followup_count INTEGER NOT NULL DEFAULT 0,
                last_customer_message_at TEXT,
                last_bot_message_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quotes_tenant_session ON quotes(tenant_id, session_id, updated_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quotes_tenant_status ON quotes(tenant_id, status, updated_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quote_lines (
                id TEXT PRIMARY KEY,
                quote_id TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                source_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                requested_qty INTEGER NOT NULL DEFAULT 1,
                unit_hint TEXT,
                line_status TEXT NOT NULL,
                confidence_score REAL,
                selected_sku TEXT,
                selected_name TEXT,
                selected_category TEXT,
                selected_unit_price INTEGER,
                presentation_note TEXT,
                clarification_prompt TEXT,
                resolution_reason TEXT,
                family_id TEXT,
                dimensions_json TEXT,
                missing_dimensions_json TEXT,
                issue_type TEXT,
                clarification_attempts INTEGER NOT NULL DEFAULT 0,
                last_targeted_dimension TEXT,
                selected_via_substitute INTEGER NOT NULL DEFAULT 0,
                alternatives_json TEXT,
                complementary_json TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(quote_id) REFERENCES quotes(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quote_lines_quote ON quote_lines(quote_id, line_number)")
        quote_line_columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(quote_lines)").fetchall()
        }
        if "family_id" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN family_id TEXT")
        if "dimensions_json" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN dimensions_json TEXT")
        if "missing_dimensions_json" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN missing_dimensions_json TEXT")
        if "issue_type" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN issue_type TEXT")
        if "clarification_attempts" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN clarification_attempts INTEGER NOT NULL DEFAULT 0")
        if "last_targeted_dimension" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN last_targeted_dimension TEXT")
        if "selected_via_substitute" not in quote_line_columns:
            cur.execute("ALTER TABLE quote_lines ADD COLUMN selected_via_substitute INTEGER NOT NULL DEFAULT 0")
        quote_columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(quotes)").fetchall()
        }
        if "automation_state" not in quote_columns:
            cur.execute("ALTER TABLE quotes ADD COLUMN automation_state TEXT NOT NULL DEFAULT 'manual_only'")
        if "automation_reason" not in quote_columns:
            cur.execute("ALTER TABLE quotes ADD COLUMN automation_reason TEXT")
        if "automation_context_json" not in quote_columns:
            cur.execute("ALTER TABLE quotes ADD COLUMN automation_context_json TEXT")
        if "automation_updated_at" not in quote_columns:
            cur.execute("ALTER TABLE quotes ADD COLUMN automation_updated_at TEXT")
        if "last_auto_followup_at" not in quote_columns:
            cur.execute("ALTER TABLE quotes ADD COLUMN last_auto_followup_at TEXT")
        if "auto_followup_count" not in quote_columns:
            cur.execute("ALTER TABLE quotes ADD COLUMN auto_followup_count INTEGER NOT NULL DEFAULT 0")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quote_events (
                id TEXT PRIMARY KEY,
                quote_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_ref TEXT,
                line_id TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(quote_id) REFERENCES quotes(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quote_events_quote ON quote_events(quote_id, created_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY,
                quote_id TEXT NOT NULL,
                status TEXT NOT NULL,
                destination_type TEXT NOT NULL,
                destination_ref TEXT,
                claimed_by TEXT,
                claimed_at TEXT,
                contacted_customer_at TEXT,
                resolved_at TEXT,
                outcome_note TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(quote_id) REFERENCES quotes(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_quote ON handoffs(quote_id, updated_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_status ON handoffs(status, updated_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS unresolved_terms (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                quote_id TEXT,
                quote_line_id TEXT,
                raw_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                inferred_family TEXT,
                missing_dimensions_json TEXT,
                issue_type TEXT,
                review_status TEXT NOT NULL DEFAULT 'new',
                resolution_note TEXT,
                linked_knowledge_domain TEXT,
                linked_knowledge_key TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_review ON unresolved_terms(tenant_id, review_status, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_quote_line ON unresolved_terms(quote_line_id, created_at DESC)")
        unresolved_columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(unresolved_terms)").fetchall()
        }
        if "inferred_family" not in unresolved_columns:
            cur.execute("ALTER TABLE unresolved_terms ADD COLUMN inferred_family TEXT")
        if "missing_dimensions_json" not in unresolved_columns:
            cur.execute("ALTER TABLE unresolved_terms ADD COLUMN missing_dimensions_json TEXT")
        if "issue_type" not in unresolved_columns:
            cur.execute("ALTER TABLE unresolved_terms ADD COLUMN issue_type TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_family ON unresolved_terms(tenant_id, inferred_family, created_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_change_audit (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                action TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                changed_by TEXT,
                change_reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._commit_if_needed()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self):
        outermost = self._transaction_depth == 0
        if outermost:
            self.conn.execute("BEGIN IMMEDIATE")
        self._transaction_depth += 1
        try:
            yield self.conn
        except Exception:
            if self._transaction_depth > 0:
                self._transaction_depth = 0
                self.conn.rollback()
            raise
        else:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                self.conn.commit()

    def _commit_if_needed(self) -> None:
        if self._transaction_depth == 0:
            self.conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        return dict(row) if row is not None else None

    @staticmethod
    def _inflate_quote_row(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["automation_context"] = json.loads(item.get("automation_context_json") or "{}")
        return item

    def get_active_quote(self, session_id: str) -> Optional[Dict[str, Any]]:
        placeholders = ",".join("?" for _ in ACTIVE_QUOTE_STATUSES)
        row = self.conn.execute(
            f"""
            SELECT * FROM quotes
            WHERE tenant_id = ? AND session_id = ? AND status IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (self.tenant_id, session_id, *ACTIVE_QUOTE_STATUSES),
        ).fetchone()
        if row is None:
            return None
        quote = self._inflate_quote_row(row) or {}
        quote["lines"] = self.get_quote_lines(quote["id"])
        quote["handoffs"] = self.get_handoffs(quote["id"])
        return quote

    def get_quote(self, quote_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM quotes WHERE tenant_id = ? AND id = ?",
            (self.tenant_id, quote_id),
        ).fetchone()
        if row is None:
            return None
        quote = self._inflate_quote_row(row) or {}
        quote["lines"] = self.get_quote_lines(quote_id)
        quote["events"] = self.get_quote_events(quote_id)
        quote["handoffs"] = self.get_handoffs(quote_id)
        return quote

    def create_quote(
        self,
        session_id: str,
        channel: str = "cli",
        customer_ref: Optional[str] = None,
        status: str = "open",
        currency: str = "ARS",
    ) -> str:
        quote_id = uuid.uuid4().hex
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO quotes (
                id, tenant_id, session_id, channel, customer_ref, status, currency,
                created_at, updated_at, last_customer_message_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (quote_id, self.tenant_id, session_id, channel, customer_ref, status, currency, now, now, now),
        )
        self._commit_if_needed()
        return quote_id

    def update_quote_header(self, quote_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utc_now_iso()
        cols = ", ".join(f"{_safe_col(k)} = ?" for k in fields.keys())
        values = list(fields.values()) + [quote_id]
        self.conn.execute(f"UPDATE quotes SET {cols} WHERE id = ?", values)
        self._commit_if_needed()

    def replace_quote_lines(self, quote_id: str, lines: List[Dict[str, Any]]) -> None:
        now = utc_now_iso()
        self.conn.execute("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
        for index, line in enumerate(lines, start=1):
            self.conn.execute(
                """
                INSERT INTO quote_lines (
                    id, quote_id, line_number, source_text, normalized_text, requested_qty, unit_hint,
                    line_status, confidence_score, selected_sku, selected_name, selected_category,
                    selected_unit_price, presentation_note, clarification_prompt, resolution_reason,
                    family_id, dimensions_json, missing_dimensions_json, issue_type,
                    clarification_attempts, last_targeted_dimension, selected_via_substitute,
                    alternatives_json, complementary_json, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    line["id"],
                    quote_id,
                    index,
                    line["source_text"],
                    line["normalized_text"],
                    line["requested_qty"],
                    line.get("unit_hint"),
                    line["line_status"],
                    line.get("confidence_score"),
                    line.get("selected_sku"),
                    line.get("selected_name"),
                    line.get("selected_category"),
                    line.get("selected_unit_price"),
                    line.get("presentation_note"),
                    line.get("clarification_prompt"),
                    line.get("resolution_reason"),
                    line.get("family_id"),
                    json.dumps(line.get("dimensions") or {}, ensure_ascii=False),
                    json.dumps(line.get("missing_dimensions") or [], ensure_ascii=False),
                    line.get("issue_type"),
                    int(line.get("clarification_attempts") or 0),
                    line.get("last_targeted_dimension"),
                    1 if line.get("selected_via_substitute") else 0,
                    json.dumps(line.get("alternatives") or [], ensure_ascii=False),
                    json.dumps(line.get("complementary") or [], ensure_ascii=False),
                    1,
                    now,
                    now,
                ),
            )
        self._commit_if_needed()

    def get_quote_lines(self, quote_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM quote_lines WHERE quote_id = ? ORDER BY line_number",
            (quote_id,),
        ).fetchall()
        lines = []
        for row in rows:
            item = dict(row)
            item["alternatives"] = json.loads(item.get("alternatives_json") or "[]")
            item["complementary"] = json.loads(item.get("complementary_json") or "[]")
            item["dimensions"] = json.loads(item.get("dimensions_json") or "{}")
            item["missing_dimensions"] = json.loads(item.get("missing_dimensions_json") or "[]")
            item["selected_via_substitute"] = bool(item.get("selected_via_substitute"))
            lines.append(item)
        return lines

    def append_event(
        self,
        quote_id: str,
        event_type: str,
        actor_type: str,
        actor_ref: Optional[str] = None,
        line_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        event_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO quote_events (id, quote_id, event_type, actor_type, actor_ref, line_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                quote_id,
                event_type,
                actor_type,
                actor_ref,
                line_id,
                json.dumps(payload or {}, ensure_ascii=False),
                utc_now_iso(),
            ),
        )
        self._commit_if_needed()
        return event_id

    def get_quote_events(self, quote_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM quote_events WHERE quote_id = ? ORDER BY created_at DESC",
            (quote_id,),
        ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.get("payload_json") or "{}")
            events.append(item)
        return events

    def create_handoff(
        self,
        quote_id: str,
        destination_type: str,
        destination_ref: Optional[str],
        status: str = "queued",
        last_error: Optional[str] = None,
    ) -> str:
        handoff_id = uuid.uuid4().hex
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO handoffs (
                id, quote_id, status, destination_type, destination_ref, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (handoff_id, quote_id, status, destination_type, destination_ref, last_error, now, now),
        )
        self._commit_if_needed()
        return handoff_id

    def update_handoff(self, handoff_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utc_now_iso()
        cols = ", ".join(f"{_safe_col(k)} = ?" for k in fields.keys())
        values = list(fields.values()) + [handoff_id]
        self.conn.execute(f"UPDATE handoffs SET {cols} WHERE id = ?", values)
        self._commit_if_needed()

    def get_handoffs(self, quote_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM handoffs WHERE quote_id = ? ORDER BY created_at DESC",
            (quote_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_quotes(
        self,
        statuses: Optional[List[str]] = None,
        automation_states: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params: List[Any] = [self.tenant_id]
        sql = "SELECT * FROM quotes WHERE tenant_id = ?"
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(statuses)
        if automation_states:
            placeholders = ",".join("?" for _ in automation_states)
            sql += f" AND automation_state IN ({placeholders})"
            params.extend(automation_states)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._inflate_quote_row(row) or {} for row in rows]

    def list_unresolved_terms(self, review_status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        params: List[Any] = [self.tenant_id]
        sql = "SELECT * FROM unresolved_terms WHERE tenant_id = ?"
        if review_status:
            sql += " AND review_status = ?"
            params.append(review_status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["missing_dimensions"] = json.loads(item.get("missing_dimensions_json") or "[]")
            items.append(item)
        return items

    def maybe_add_unresolved_term(
        self,
        quote_id: Optional[str],
        quote_line_id: Optional[str],
        raw_text: str,
        normalized_text: str,
        status: str,
        reason: str,
        inferred_family: Optional[str] = None,
        missing_dimensions: Optional[List[str]] = None,
        issue_type: Optional[str] = None,
    ) -> Optional[str]:
        last = None
        if quote_line_id:
            last = self.conn.execute(
                """
                SELECT * FROM unresolved_terms
                WHERE quote_line_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (quote_line_id,),
            ).fetchone()
        if last is not None:
            last_row = dict(last)
            if (
                last_row.get("raw_text") == raw_text
                and last_row.get("normalized_text") == normalized_text
                and last_row.get("status") == status
                and last_row.get("reason") == reason
                and (last_row.get("inferred_family") or "") == (inferred_family or "")
            ):
                return last_row["id"]
        unresolved_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO unresolved_terms (
                id, tenant_id, quote_id, quote_line_id, raw_text, normalized_text, status, reason,
                inferred_family, missing_dimensions_json, issue_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unresolved_id,
                self.tenant_id,
                quote_id,
                quote_line_id,
                raw_text,
                normalized_text,
                status,
                reason,
                inferred_family,
                json.dumps(missing_dimensions or [], ensure_ascii=False),
                issue_type,
                utc_now_iso(),
            ),
        )
        self._commit_if_needed()
        return unresolved_id

    def review_unresolved_term(
        self,
        unresolved_id: str,
        review_status: str,
        reviewed_by: Optional[str] = None,
        resolution_note: Optional[str] = None,
        linked_knowledge_domain: Optional[str] = None,
        linked_knowledge_key: Optional[str] = None,
        inferred_family: Optional[str] = None,
        missing_dimensions: Optional[List[str]] = None,
        issue_type: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE unresolved_terms
            SET review_status = ?, reviewed_by = ?, reviewed_at = ?, resolution_note = ?, linked_knowledge_domain = ?, linked_knowledge_key = ?,
                inferred_family = COALESCE(?, inferred_family),
                missing_dimensions_json = COALESCE(?, missing_dimensions_json),
                issue_type = COALESCE(?, issue_type)
            WHERE id = ?
            """,
            (
                review_status,
                reviewed_by,
                utc_now_iso(),
                resolution_note,
                linked_knowledge_domain,
                linked_knowledge_key,
                inferred_family,
                json.dumps(missing_dimensions, ensure_ascii=False) if missing_dimensions is not None else None,
                issue_type,
                unresolved_id,
            ),
        )
        self._commit_if_needed()

    def record_knowledge_change(
        self,
        domain: str,
        entity_key: str,
        action: str,
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
        changed_by: Optional[str],
        change_reason: Optional[str],
    ) -> str:
        audit_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO knowledge_change_audit (
                id, tenant_id, domain, entity_key, action, before_json, after_json, changed_by, change_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                self.tenant_id,
                domain,
                entity_key,
                action,
                json.dumps(before or {}, ensure_ascii=False),
                json.dumps(after or {}, ensure_ascii=False),
                changed_by,
                change_reason,
                utc_now_iso(),
            ),
        )
        self._commit_if_needed()
        return audit_id
