from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_col(name: str) -> str:
    """Validate that a column/table name contains only safe identifier characters."""
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name

from bot_sales.persistence.quote_store import utc_now_iso


class TrainingStore:
    """Persistence for training sessions, reviews, suggestions, and usage."""

    def __init__(self, db_file: str, tenant_id: str = "ferreteria"):
        self.db_file = str(db_file)
        self.tenant_id = tenant_id
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._transaction_depth = 0
        self.ensure_schema()

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

    def ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS training_sessions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                operator_id TEXT,
                status TEXT NOT NULL,
                mode_profile TEXT NOT NULL,
                model_name TEXT,
                token_ceiling INTEGER,
                context_strategy TEXT NOT NULL DEFAULT 'compact',
                session_summary TEXT,
                session_state_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_training_sessions_tenant_status ON training_sessions(tenant_id, status, updated_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS training_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                route_source TEXT,
                model_name TEXT,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_micros INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER,
                raw_metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES training_sessions(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_training_messages_session_turn ON training_messages(session_id, turn_index)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS training_reviews (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                bot_message_id TEXT NOT NULL,
                review_label TEXT NOT NULL,
                failure_tag TEXT,
                failure_detail_tag TEXT,
                expected_behavior_tag TEXT,
                clarification_dimension TEXT,
                expected_answer TEXT,
                what_was_wrong TEXT,
                missing_clarification TEXT,
                suggested_family TEXT,
                suggested_canonical_product TEXT,
                operator_notes TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES training_sessions(id),
                FOREIGN KEY(bot_message_id) REFERENCES training_messages(id)
            )
            """
        )
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_training_reviews_message ON training_reviews(bot_message_id)")
        if not self._column_exists("training_reviews", "failure_tag"):
            cur.execute("ALTER TABLE training_reviews ADD COLUMN failure_tag TEXT")
        if not self._column_exists("training_reviews", "failure_detail_tag"):
            cur.execute("ALTER TABLE training_reviews ADD COLUMN failure_detail_tag TEXT")
        if not self._column_exists("training_reviews", "expected_behavior_tag"):
            cur.execute("ALTER TABLE training_reviews ADD COLUMN expected_behavior_tag TEXT")
        if not self._column_exists("training_reviews", "clarification_dimension"):
            cur.execute("ALTER TABLE training_reviews ADD COLUMN clarification_dimension TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_suggestions (
                id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                source_message TEXT,
                repeated_term TEXT,
                suggested_payload_json TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(review_id) REFERENCES training_reviews(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_training_suggestions_status ON knowledge_suggestions(status, created_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_approvals (
                id TEXT PRIMARY KEY,
                suggestion_id TEXT NOT NULL,
                action TEXT NOT NULL,
                acted_by TEXT,
                reason TEXT,
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(suggestion_id) REFERENCES knowledge_suggestions(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_training_approvals_suggestion ON knowledge_approvals(suggestion_id, created_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS training_usage_metrics (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT '',
                period_key TEXT NOT NULL,
                metric_scope TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_micros INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_training_usage_unique ON training_usage_metrics(metric_scope, period_key, session_id)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS regression_case_exports (
                id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                status TEXT NOT NULL,
                fixture_name TEXT NOT NULL,
                export_format TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                exported_by TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(review_id) REFERENCES training_reviews(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_regression_exports_review ON regression_case_exports(review_id, created_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS regression_case_candidates (
                id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                status TEXT NOT NULL,
                fixture_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(review_id) REFERENCES training_reviews(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_regression_candidates_review ON regression_case_candidates(review_id, updated_at DESC)")
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

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        rows = self.conn.execute(f"PRAGMA table_info({_safe_col(table_name)})").fetchall()
        return any(str(row["name"]) == column_name for row in rows)

    def _row(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        return dict(row) if row is not None else None

    def create_session(
        self,
        *,
        operator_id: Optional[str],
        mode_profile: str,
        model_name: str,
        token_ceiling: Optional[int],
        context_strategy: str = "compact",
    ) -> Dict[str, Any]:
        session_id = f"training:{uuid.uuid4().hex}"
        now = utc_now_iso()
        payload = {
            "id": session_id,
            "tenant_id": self.tenant_id,
            "operator_id": operator_id,
            "status": "open",
            "mode_profile": mode_profile,
            "model_name": model_name,
            "token_ceiling": token_ceiling,
            "context_strategy": context_strategy,
            "session_summary": None,
            "session_state_json": "{}",
            "started_at": now,
            "ended_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.conn.execute(
            """
            INSERT INTO training_sessions (
                id, tenant_id, operator_id, status, mode_profile, model_name, token_ceiling,
                context_strategy, session_summary, session_state_json, started_at, ended_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(payload.values()),
        )
        self._commit_if_needed()
        return self.get_session(session_id) or payload

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM training_sessions WHERE tenant_id = ? AND id = ?",
            (self.tenant_id, session_id),
        ).fetchone()
        return self._row(row)

    def list_sessions(
        self,
        *,
        status: Optional[str] = None,
        operator_id: Optional[str] = None,
        mode_profile: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT
                ts.*,
                (
                    SELECT COUNT(*)
                    FROM training_messages tm
                    WHERE tm.session_id = ts.id AND tm.role = 'assistant'
                ) AS assistant_turn_count,
                (
                    SELECT COUNT(*)
                    FROM training_reviews tr
                    WHERE tr.session_id = ts.id
                ) AS review_count
            FROM training_sessions ts
            WHERE tenant_id = ?
        """
        params: List[Any] = [self.tenant_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if operator_id:
            sql += " AND operator_id = ?"
            params.append(operator_id)
        if mode_profile:
            sql += " AND mode_profile = ?"
            params.append(mode_profile)
        if model_name:
            sql += " AND model_name = ?"
            params.append(model_name)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utc_now_iso()
        cols = ", ".join(f"{_safe_col(key)} = ?" for key in fields.keys())
        values = list(fields.values()) + [session_id]
        self.conn.execute(f"UPDATE training_sessions SET {cols} WHERE id = ?", values)
        self._commit_if_needed()

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        route_source: Optional[str] = None,
        model_name: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost_micros: int = 0,
        latency_ms: Optional[int] = None,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        turn_index = int(
            self.conn.execute("SELECT COALESCE(MAX(turn_index), 0) FROM training_messages WHERE session_id = ?", (session_id,)).fetchone()[0]
        ) + 1
        message_id = uuid.uuid4().hex
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO training_messages (
                id, session_id, turn_index, role, content, route_source, model_name,
                prompt_tokens, completion_tokens, total_tokens, estimated_cost_micros,
                latency_ms, raw_metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                turn_index,
                role,
                content,
                route_source,
                model_name,
                int(prompt_tokens or 0),
                int(completion_tokens or 0),
                int(total_tokens or 0),
                int(estimated_cost_micros or 0),
                latency_ms,
                json.dumps(raw_metadata or {}, ensure_ascii=False),
                now,
            ),
        )
        self.update_session(session_id)
        return self.get_message(message_id) or {}

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM training_messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["raw_metadata"] = json.loads(item.get("raw_metadata_json") or "{}")
        return item

    def list_messages(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM training_messages WHERE session_id = ? ORDER BY turn_index ASC",
            (session_id,),
        ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["raw_metadata"] = json.loads(item.get("raw_metadata_json") or "{}")
            messages.append(item)
        return messages

    def upsert_review(self, session_id: str, bot_message_id: str, **fields: Any) -> Dict[str, Any]:
        existing = self.conn.execute(
            "SELECT id FROM training_reviews WHERE bot_message_id = ?",
            (bot_message_id,),
        ).fetchone()
        now = utc_now_iso()
        normalized = {
            "review_label": fields.get("review_label"),
            "failure_tag": fields.get("failure_tag"),
            "failure_detail_tag": fields.get("failure_detail_tag"),
            "expected_behavior_tag": fields.get("expected_behavior_tag"),
            "clarification_dimension": fields.get("clarification_dimension"),
            "expected_answer": fields.get("expected_answer"),
            "what_was_wrong": fields.get("what_was_wrong"),
            "missing_clarification": fields.get("missing_clarification"),
            "suggested_family": fields.get("suggested_family"),
            "suggested_canonical_product": fields.get("suggested_canonical_product"),
            "operator_notes": fields.get("operator_notes"),
            "status": fields.get("status", "submitted"),
            "created_by": fields.get("created_by"),
        }
        if existing:
            review_id = existing["id"]
            self.conn.execute(
                """
                UPDATE training_reviews
                SET review_label = ?, failure_tag = ?, failure_detail_tag = ?, expected_behavior_tag = ?, clarification_dimension = ?,
                    expected_answer = ?, what_was_wrong = ?, missing_clarification = ?, suggested_family = ?, suggested_canonical_product = ?,
                    operator_notes = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized["review_label"],
                    normalized["failure_tag"],
                    normalized["failure_detail_tag"],
                    normalized["expected_behavior_tag"],
                    normalized["clarification_dimension"],
                    normalized["expected_answer"],
                    normalized["what_was_wrong"],
                    normalized["missing_clarification"],
                    normalized["suggested_family"],
                    normalized["suggested_canonical_product"],
                    normalized["operator_notes"],
                    normalized["status"],
                    now,
                    review_id,
                ),
            )
        else:
            review_id = uuid.uuid4().hex
            self.conn.execute(
                """
                INSERT INTO training_reviews (
                    id, session_id, bot_message_id, review_label, failure_tag, failure_detail_tag, expected_behavior_tag,
                    clarification_dimension, expected_answer, what_was_wrong, missing_clarification,
                    suggested_family, suggested_canonical_product, operator_notes,
                    status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    session_id,
                    bot_message_id,
                    normalized["review_label"],
                    normalized["failure_tag"],
                    normalized["failure_detail_tag"],
                    normalized["expected_behavior_tag"],
                    normalized["clarification_dimension"],
                    normalized["expected_answer"],
                    normalized["what_was_wrong"],
                    normalized["missing_clarification"],
                    normalized["suggested_family"],
                    normalized["suggested_canonical_product"],
                    normalized["operator_notes"],
                    normalized["status"],
                    normalized["created_by"],
                    now,
                    now,
                ),
            )
        self._commit_if_needed()
        self.update_session(session_id)
        return self.get_review(review_id) or {}

    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM training_reviews WHERE id = ?", (review_id,)).fetchone()
        return self._row(row)

    def list_reviews(self, *, session_id: Optional[str] = None, bot_message_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM training_reviews WHERE 1 = 1"
        params: List[Any] = []
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if bot_message_id:
            sql += " AND bot_message_id = ?"
            params.append(bot_message_id)
        sql += " ORDER BY updated_at DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_cases(
        self,
        *,
        status: Optional[str] = None,
        review_label: Optional[str] = None,
        failure_tag: Optional[str] = None,
        domain: Optional[str] = None,
        operator_id: Optional[str] = None,
        suggested_family: Optional[str] = None,
        repeated_term: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT
                r.*,
                m.content AS bot_response,
                prev.content AS user_input,
                (
                    SELECT ks.domain
                    FROM knowledge_suggestions ks
                    WHERE ks.review_id = r.id
                    ORDER BY ks.updated_at DESC
                    LIMIT 1
                ) AS suggestion_domain,
                (
                    SELECT ks.status
                    FROM knowledge_suggestions ks
                    WHERE ks.review_id = r.id
                    ORDER BY ks.updated_at DESC
                    LIMIT 1
                ) AS suggestion_status,
                (
                    SELECT ks.repeated_term
                    FROM knowledge_suggestions ks
                    WHERE ks.review_id = r.id
                    ORDER BY ks.updated_at DESC
                    LIMIT 1
                ) AS repeated_term,
                (
                    SELECT COUNT(*)
                    FROM regression_case_candidates rc
                    WHERE rc.review_id = r.id
                ) AS regression_candidate_count,
                (
                    SELECT COUNT(*)
                    FROM regression_case_exports re
                    WHERE re.review_id = r.id
                ) AS regression_export_count
            FROM training_reviews r
            JOIN training_messages m ON m.id = r.bot_message_id
            LEFT JOIN training_messages prev ON prev.session_id = r.session_id AND prev.turn_index = m.turn_index - 1
            JOIN training_sessions ts ON ts.id = r.session_id
            WHERE ts.tenant_id = ?
        """
        params: List[Any] = [self.tenant_id]
        if status:
            sql += " AND r.status = ?"
            params.append(status)
        if review_label:
            sql += " AND r.review_label = ?"
            params.append(review_label)
        if failure_tag:
            sql += " AND r.failure_tag = ?"
            params.append(failure_tag)
        if domain:
            sql += """
                AND EXISTS (
                    SELECT 1 FROM knowledge_suggestions s
                    WHERE s.review_id = r.id AND s.domain = ?
                )
            """
            params.append(domain)
        if operator_id:
            sql += " AND r.created_by = ?"
            params.append(operator_id)
        if suggested_family:
            sql += " AND r.suggested_family = ?"
            params.append(suggested_family)
        if repeated_term:
            sql += """
                AND EXISTS (
                    SELECT 1 FROM knowledge_suggestions s
                    WHERE s.review_id = r.id AND lower(COALESCE(s.repeated_term, '')) LIKE ?
                )
            """
            params.append(f"%{repeated_term.lower()}%")
        sql += " ORDER BY r.updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_case_detail(self, review_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT r.*, m.content AS bot_response, m.route_source, m.model_name, m.prompt_tokens, m.completion_tokens,
                   m.total_tokens, m.estimated_cost_micros, m.created_at AS bot_created_at,
                   prev.content AS user_input
            FROM training_reviews r
            JOIN training_messages m ON m.id = r.bot_message_id
            LEFT JOIN training_messages prev ON prev.session_id = r.session_id AND prev.turn_index = m.turn_index - 1
            WHERE r.id = ?
            """,
            (review_id,),
        ).fetchone()
        if row is None:
            return None
        detail = dict(row)
        detail["suggestions"] = self.list_suggestions(review_id=review_id, limit=20)
        detail["exports"] = self.list_regression_exports(review_id=review_id)
        detail["regression_candidates"] = self.list_regression_candidates(review_id=review_id)
        return detail

    def create_suggestion(
        self,
        *,
        review_id: str,
        domain: str,
        summary: Optional[str],
        source_message: Optional[str],
        repeated_term: Optional[str],
        suggested_payload: Dict[str, Any],
        created_by: Optional[str],
    ) -> Dict[str, Any]:
        suggestion_id = uuid.uuid4().hex
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO knowledge_suggestions (
                id, review_id, tenant_id, domain, status, summary, source_message, repeated_term,
                suggested_payload_json, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                suggestion_id,
                review_id,
                self.tenant_id,
                domain,
                "draft",
                summary,
                source_message,
                repeated_term,
                json.dumps(suggested_payload, ensure_ascii=False),
                created_by,
                now,
                now,
            ),
        )
        self._commit_if_needed()
        return self.get_suggestion(suggestion_id) or {}

    def update_suggestion(self, suggestion_id: str, **fields: Any) -> None:
        if "suggested_payload" in fields:
            fields["suggested_payload_json"] = json.dumps(fields.pop("suggested_payload"), ensure_ascii=False)
        fields["updated_at"] = utc_now_iso()
        cols = ", ".join(f"{_safe_col(key)} = ?" for key in fields.keys())
        values = list(fields.values()) + [suggestion_id]
        self.conn.execute(f"UPDATE knowledge_suggestions SET {cols} WHERE id = ?", values)
        self._commit_if_needed()

    def get_suggestion(self, suggestion_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM knowledge_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["suggested_payload"] = json.loads(item.get("suggested_payload_json") or "{}")
        item["approvals"] = self.get_approvals(suggestion_id)
        item["review"] = self.get_case_detail(item["review_id"])
        return item

    def list_suggestions(
        self,
        *,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        review_id: Optional[str] = None,
        created_by: Optional[str] = None,
        repeated_term: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM knowledge_suggestions WHERE tenant_id = ?"
        params: List[Any] = [self.tenant_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        if review_id:
            sql += " AND review_id = ?"
            params.append(review_id)
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        if repeated_term:
            sql += " AND lower(COALESCE(repeated_term, '')) LIKE ?"
            params.append(f"%{repeated_term.lower()}%")
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["suggested_payload"] = json.loads(item.get("suggested_payload_json") or "{}")
            items.append(item)
        return items

    def add_approval(
        self,
        suggestion_id: str,
        *,
        action: str,
        acted_by: Optional[str],
        reason: Optional[str],
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        approval_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO knowledge_approvals (id, suggestion_id, action, acted_by, reason, before_json, after_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                suggestion_id,
                action,
                acted_by,
                reason,
                json.dumps(before or {}, ensure_ascii=False),
                json.dumps(after or {}, ensure_ascii=False),
                utc_now_iso(),
            ),
        )
        self._commit_if_needed()
        return self.get_approvals(suggestion_id)[0]

    def get_approvals(self, suggestion_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM knowledge_approvals WHERE suggestion_id = ? ORDER BY created_at DESC",
            (suggestion_id,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["before"] = json.loads(item.get("before_json") or "{}")
            item["after"] = json.loads(item.get("after_json") or "{}")
            items.append(item)
        return items

    def upsert_usage(
        self,
        *,
        metric_scope: str,
        period_key: str,
        session_id: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost_micros: int = 0,
        message_count: int = 0,
    ) -> Dict[str, Any]:
        existing = self.conn.execute(
            "SELECT * FROM training_usage_metrics WHERE metric_scope = ? AND period_key = ? AND session_id = ?",
            (metric_scope, period_key, session_id),
        ).fetchone()
        now = utc_now_iso()
        if existing:
            row = dict(existing)
            values = {
                "prompt_tokens": int(row.get("prompt_tokens", 0)) + int(prompt_tokens or 0),
                "completion_tokens": int(row.get("completion_tokens", 0)) + int(completion_tokens or 0),
                "total_tokens": int(row.get("total_tokens", 0)) + int(total_tokens or 0),
                "estimated_cost_micros": int(row.get("estimated_cost_micros", 0)) + int(estimated_cost_micros or 0),
                "message_count": int(row.get("message_count", 0)) + int(message_count or 0),
                "updated_at": now,
            }
            cols = ", ".join(f"{key} = ?" for key in values.keys())
            self.conn.execute(
                f"UPDATE training_usage_metrics SET {cols} WHERE id = ?",
                (*values.values(), row["id"]),
            )
            self._commit_if_needed()
        else:
            usage_id = uuid.uuid4().hex
            self.conn.execute(
                """
                INSERT INTO training_usage_metrics (
                    id, session_id, period_key, metric_scope, prompt_tokens, completion_tokens,
                    total_tokens, estimated_cost_micros, message_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    session_id,
                    period_key,
                    metric_scope,
                    int(prompt_tokens or 0),
                    int(completion_tokens or 0),
                    int(total_tokens or 0),
                    int(estimated_cost_micros or 0),
                    int(message_count or 0),
                    now,
                    now,
                ),
            )
            self._commit_if_needed()
        return self.get_usage(metric_scope=metric_scope, period_key=period_key, session_id=session_id) or {}

    def get_usage(self, *, metric_scope: str, period_key: str, session_id: str = "") -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM training_usage_metrics WHERE metric_scope = ? AND period_key = ? AND session_id = ?",
            (metric_scope, period_key, session_id),
        ).fetchone()
        return self._row(row)

    def list_usage(self, *, metric_scope: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM training_usage_metrics"
        params: List[Any] = []
        if metric_scope:
            sql += " WHERE metric_scope = ?"
            params.append(metric_scope)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def create_regression_export(
        self,
        *,
        review_id: str,
        fixture_name: str,
        export_format: str,
        payload: Dict[str, Any],
        exported_by: Optional[str],
    ) -> Dict[str, Any]:
        export_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO regression_case_exports (id, review_id, status, fixture_name, export_format, payload_json, exported_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                export_id,
                review_id,
                "exported",
                fixture_name,
                export_format,
                json.dumps(payload, ensure_ascii=False),
                exported_by,
                utc_now_iso(),
            ),
        )
        self._commit_if_needed()
        return self.list_regression_exports(review_id=review_id)[0]

    def list_regression_exports(self, *, review_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM regression_case_exports WHERE review_id = ? ORDER BY created_at DESC",
            (review_id,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.get("payload_json") or "{}")
            items.append(item)
        return items

    def create_regression_candidate(
        self,
        *,
        review_id: str,
        fixture_name: str,
        payload: Dict[str, Any],
        created_by: Optional[str],
        status: str = "draft",
    ) -> Dict[str, Any]:
        candidate_id = uuid.uuid4().hex
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO regression_case_candidates (id, review_id, status, fixture_name, payload_json, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                review_id,
                status,
                fixture_name,
                json.dumps(payload, ensure_ascii=False),
                created_by,
                now,
                now,
            ),
        )
        self._commit_if_needed()
        return self.get_regression_candidate(candidate_id) or {}

    def get_regression_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM regression_case_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["payload"] = json.loads(item.get("payload_json") or "{}")
        return item

    def list_regression_candidates(self, *, review_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM regression_case_candidates WHERE review_id = ? ORDER BY updated_at DESC",
            (review_id,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.get("payload_json") or "{}")
            items.append(item)
        return items

    def list_model_usage(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                COALESCE(model_name, 'deterministic') AS model_name,
                COUNT(*) AS turns,
                SUM(total_tokens) AS total_tokens,
                SUM(estimated_cost_micros) AS estimated_cost_micros
            FROM training_messages
            WHERE role = 'assistant'
            GROUP BY COALESCE(model_name, 'deterministic')
            ORDER BY estimated_cost_micros DESC, total_tokens DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_impact_rows(self, days_window: int = 14) -> List[Dict[str, Any]]:
        """
        Para cada sugerencia aplicada, computa la tasa de respuestas correctas
        en los N días previos y N días posteriores al apply.

        Retorna una lista de dicts con:
            suggestion_id, domain, summary, applied_at,
            correct_before, total_before, correct_after, total_after,
            accuracy_before (0-1 o None), accuracy_after (0-1 o None), delta
        """
        sql = f"""
        SELECT
            ks.id            AS suggestion_id,
            ks.domain        AS domain,
            ks.summary       AS summary,
            ks.updated_at    AS applied_at,
            SUM(CASE WHEN r.review_label = 'correct'
                     AND r.created_at < ks.updated_at
                     AND CAST(julianday(ks.updated_at) - julianday(r.created_at) AS REAL) <= {days_window}
                     THEN 1 ELSE 0 END) AS correct_before,
            SUM(CASE WHEN r.created_at < ks.updated_at
                     AND CAST(julianday(ks.updated_at) - julianday(r.created_at) AS REAL) <= {days_window}
                     THEN 1 ELSE 0 END) AS total_before,
            SUM(CASE WHEN r.review_label = 'correct'
                     AND r.created_at >= ks.updated_at
                     AND CAST(julianday(r.created_at) - julianday(ks.updated_at) AS REAL) <= {days_window}
                     THEN 1 ELSE 0 END) AS correct_after,
            SUM(CASE WHEN r.created_at >= ks.updated_at
                     AND CAST(julianday(r.created_at) - julianday(ks.updated_at) AS REAL) <= {days_window}
                     THEN 1 ELSE 0 END) AS total_after
        FROM knowledge_suggestions ks
        LEFT JOIN training_reviews r
            ON (
                CAST(julianday(ks.updated_at) - julianday(r.created_at) AS REAL) BETWEEN 0 AND {days_window}
                OR CAST(julianday(r.created_at) - julianday(ks.updated_at) AS REAL) BETWEEN 0 AND {days_window}
            )
        WHERE ks.status = 'applied'
        GROUP BY ks.id, ks.domain, ks.summary, ks.updated_at
        ORDER BY ks.updated_at DESC
        """
        rows = self.conn.execute(sql).fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            correct_before = int(d.get("correct_before") or 0)
            total_before = int(d.get("total_before") or 0)
            correct_after = int(d.get("correct_after") or 0)
            total_after = int(d.get("total_after") or 0)
            acc_before = round(correct_before / total_before, 3) if total_before > 0 else None
            acc_after = round(correct_after / total_after, 3) if total_after > 0 else None
            if acc_before is not None and acc_after is not None:
                delta = round(acc_after - acc_before, 3)
            else:
                delta = None
            results.append({
                "suggestion_id": d.get("suggestion_id"),
                "domain": d.get("domain"),
                "summary": d.get("summary"),
                "applied_at": d.get("applied_at"),
                "correct_before": correct_before,
                "total_before": total_before,
                "correct_after": correct_after,
                "total_after": total_after,
                "accuracy_before": acc_before,
                "accuracy_after": acc_after,
                "delta": delta,
            })
        return results

    def get_impact_metrics(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna un dict con métricas de impacto del entrenamiento para el tenant dado.

        Incluye:
            total_sessions, total_reviews, total_suggestions, applied_suggestions,
            pending_suggestions, improvement_rate (porcentaje),
            reviews_by_label (dict label -> count),
            suggestions_by_status (dict status -> count),
            recent_activity (lista de últimas 5 sugerencias aplicadas con fecha)
        """
        tid = tenant_id or self.tenant_id

        total_sessions = int(
            (self.conn.execute(
                "SELECT COUNT(*) FROM training_sessions WHERE tenant_id = ?", (tid,)
            ).fetchone() or [0])[0]
        )
        total_reviews = int(
            (self.conn.execute(
                """
                SELECT COUNT(*) FROM training_reviews r
                JOIN training_sessions ts ON ts.id = r.session_id
                WHERE ts.tenant_id = ?
                """,
                (tid,),
            ).fetchone() or [0])[0]
        )
        total_suggestions = int(
            (self.conn.execute(
                "SELECT COUNT(*) FROM knowledge_suggestions WHERE tenant_id = ?", (tid,)
            ).fetchone() or [0])[0]
        )
        applied_suggestions = int(
            (self.conn.execute(
                "SELECT COUNT(*) FROM knowledge_suggestions WHERE tenant_id = ? AND status = 'applied'",
                (tid,),
            ).fetchone() or [0])[0]
        )
        pending_suggestions = int(
            (self.conn.execute(
                "SELECT COUNT(*) FROM knowledge_suggestions WHERE tenant_id = ? AND status IN ('draft', 'approved')",
                (tid,),
            ).fetchone() or [0])[0]
        )
        improvement_rate = (
            round(applied_suggestions / total_suggestions * 100, 1)
            if total_suggestions > 0
            else 0.0
        )

        label_rows = self.conn.execute(
            """
            SELECT r.review_label, COUNT(*) AS cnt
            FROM training_reviews r
            JOIN training_sessions ts ON ts.id = r.session_id
            WHERE ts.tenant_id = ?
            GROUP BY r.review_label
            """,
            (tid,),
        ).fetchall()
        reviews_by_label: Dict[str, int] = {str(row[0] or "unknown"): int(row[1]) for row in label_rows}

        status_rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM knowledge_suggestions
            WHERE tenant_id = ?
            GROUP BY status
            """,
            (tid,),
        ).fetchall()
        suggestions_by_status: Dict[str, int] = {str(row[0] or "unknown"): int(row[1]) for row in status_rows}

        recent_rows = self.conn.execute(
            """
            SELECT ks.id, ks.domain, ks.summary, ks.updated_at AS applied_at
            FROM knowledge_suggestions ks
            WHERE ks.tenant_id = ? AND ks.status = 'applied'
            ORDER BY ks.updated_at DESC
            LIMIT 5
            """,
            (tid,),
        ).fetchall()
        recent_activity: List[Dict[str, Any]] = [
            {
                "suggestion_id": str(row["id"]),
                "domain": str(row["domain"] or ""),
                "summary": str(row["summary"] or ""),
                "applied_at": str(row["applied_at"] or ""),
            }
            for row in recent_rows
        ]

        return {
            "total_sessions": total_sessions,
            "total_reviews": total_reviews,
            "total_suggestions": total_suggestions,
            "applied_suggestions": applied_suggestions,
            "pending_suggestions": pending_suggestions,
            "improvement_rate": improvement_rate,
            "reviews_by_label": reviews_by_label,
            "suggestions_by_status": suggestions_by_status,
            "recent_activity": recent_activity,
        }

    def create_orphan_review(
        self,
        *,
        term: str,
        context: str = "",
        label: str = "unknown_term",
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Crea una training_review sintética (sin sesión real) para poder
        adjuntarle una sugerencia nacida directamente de un término no resuelto.

        Retorna el review creado como dict (incluyendo 'id').
        """
        # Crear una sesión sintética de tipo "unresolved_term_origin"
        session_id = f"orphan:{uuid.uuid4().hex}"
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO training_sessions
                (id, tenant_id, operator_id, status, mode_profile, model_name,
                 token_ceiling, context_strategy, session_summary, session_state_json,
                 started_at, ended_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                self.tenant_id,
                created_by,
                "closed",
                "cheap",
                None,
                None,
                "compact",
                f"Sesión sintética para término no resuelto: {term!r}",
                "{}",
                now,
                now,
                now,
                now,
            ),
        )
        # Crear un mensaje sintético de usuario como ancla
        message_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO training_messages
                (id, session_id, turn_index, role, content,
                 route_source, model_name,
                 prompt_tokens, completion_tokens, total_tokens,
                 estimated_cost_micros, latency_ms, raw_metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                1,
                "assistant",
                f"[Origen automático desde término no resuelto: {term!r}]",
                "deterministic",
                None,
                0, 0, 0, 0, None, None,
                now,
            ),
        )
        # Crear la review vinculada al mensaje sintético
        review_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO training_reviews
                (id, session_id, bot_message_id, review_label,
                 failure_tag, failure_detail_tag, expected_behavior_tag,
                 clarification_dimension, expected_answer,
                 what_was_wrong, missing_clarification,
                 suggested_family, suggested_canonical_product,
                 operator_notes, status, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                session_id,
                message_id,
                "incorrect",
                "did_not_understand_term",
                "alias_missing",
                "understand_term",
                None,
                None,
                f"Término no resuelto: {term!r}",
                None,
                None,
                term,
                f"Creado automáticamente desde términos no resueltos. Término: {term!r}",
                "draft",
                created_by,
                now,
                now,
            ),
        )
        self._commit_if_needed()
        return self.get_review(review_id) or {"id": review_id}

    def record_knowledge_change(
        self,
        *,
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
