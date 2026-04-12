from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from bot_sales.bot import SalesBot
from bot_sales.core.database import Database
from bot_sales.ferreteria_unresolved_log import suppress_unresolved_logging

from .context_builder import TrainingContextBuilder
from .costs import TrainingCostEngine
from .store import TrainingStore


class TrainingSessionService:
    """Execute sandbox sessions without mutating production bot state."""

    def __init__(self, store: TrainingStore, tenant_profile: Dict[str, Any], tenant_id: str = "ferreteria"):
        self.store = store
        self.tenant_id = tenant_id
        self.tenant_profile = tenant_profile
        self.context_builder = TrainingContextBuilder()
        default_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.costs = TrainingCostEngine(default_model=default_model)

    def create_session(
        self,
        *,
        operator_id: Optional[str],
        mode_profile: str = "cheap",
        token_ceiling: Optional[int] = None,
    ) -> Dict[str, Any]:
        model_name = self.costs.resolve_model(mode_profile)
        return self.store.create_session(
            operator_id=operator_id,
            mode_profile=mode_profile,
            model_name=model_name,
            token_ceiling=token_ceiling,
            context_strategy="compact",
        )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.store.get_session(session_id)
        if not session:
            return None
        session["messages"] = self.store.list_messages(session_id)
        session["usage"] = self.store.get_usage(metric_scope="session", period_key=session_id, session_id=session_id) or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_micros": 0,
            "message_count": 0,
        }
        return session

    def list_sessions(self, **filters: Any) -> list[Dict[str, Any]]:
        return self.store.list_sessions(**filters)

    def close_session(self, session_id: str) -> Dict[str, Any]:
        self.store.update_session(session_id, status="closed", ended_at=datetime.utcnow().replace(microsecond=0).isoformat())
        return self.get_session(session_id) or {}

    def reset_session(self, session_id: str, *, operator_id: Optional[str]) -> Dict[str, Any]:
        existing = self.store.get_session(session_id)
        if not existing:
            raise ValueError("Training session not found")
        self.store.update_session(session_id, status="archived", ended_at=datetime.utcnow().replace(microsecond=0).isoformat())
        return self.create_session(
            operator_id=operator_id or existing.get("operator_id"),
            mode_profile=existing.get("mode_profile") or "cheap",
            token_ceiling=existing.get("token_ceiling"),
        )

    def send_message(self, session_id: str, user_message: str) -> Dict[str, Any]:
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError("Training session not found")
        if session.get("status") == "limit_reached":
            raise ValueError("Training session token ceiling reached")
        if str(session.get("status")) not in {"open"}:
            raise ValueError("Training session is not open")

        self._assert_app_limits()

        bot = self._build_sandbox_bot(session)
        try:
            with suppress_unresolved_logging():
                reply = bot.process_message(session_id, user_message)
            turn_meta = bot.get_last_turn_meta(session_id)
            route_source = self._normalize_route_source(turn_meta.get("route_source"))
            model_name = str(turn_meta.get("model_name") or session.get("model_name") or "")
            prompt_tokens = int(turn_meta.get("prompt_tokens") or 0)
            completion_tokens = int(turn_meta.get("completion_tokens") or 0)
            usage = self.costs.estimate(model_name, prompt_tokens, completion_tokens)
            total_after_turn = self._session_total_tokens(session_id) + usage.total_tokens
            token_ceiling = int(session.get("token_ceiling") or 0)
            if token_ceiling and usage.total_tokens > 0 and total_after_turn > token_ceiling:
                self.store.update_session(session_id, status="limit_reached")
                raise ValueError("Training session token ceiling reached")

            self.store.append_message(session_id, role="user", content=user_message)
            message = self.store.append_message(
                session_id,
                role="assistant",
                content=reply,
                route_source=route_source,
                model_name=model_name or None,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                estimated_cost_micros=usage.estimated_cost_micros,
                latency_ms=turn_meta.get("latency_ms"),
                raw_metadata=turn_meta,
            )
            self._record_usage(session_id, usage)
            self.store.update_session(session_id, session_state_json=self._serialize_state(bot.sessions.get(session_id) or {}))
            return {
                "session": self.get_session(session_id),
                "message": message,
            }
        finally:
            bot.close()
            temp_db = getattr(bot, "_training_temp_db_path", None)
            temp_log = getattr(bot, "_training_temp_log_path", None)
            if temp_db:
                try:
                    Path(temp_db).unlink(missing_ok=True)
                except Exception:
                    pass
            if temp_log:
                try:
                    Path(temp_log).unlink(missing_ok=True)
                except Exception:
                    pass

    def _build_sandbox_bot(self, session: Dict[str, Any]) -> SalesBot:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or "sk-" not in api_key:
            raise ValueError(
                "OPENAI_API_KEY no está configurada en el servidor. "
                "El training requiere una API key válida de OpenAI. "
                "Configurá la variable OPENAI_API_KEY en Railway → Variables."
            )
        profile = dict(self.tenant_profile or {})
        paths = dict(profile.get("paths") or {})
        catalog_path = str(paths.get("catalog") or "")
        if not Path(catalog_path).is_absolute():
            catalog_path = str((Path(__file__).resolve().parents[2] / catalog_path).resolve())
        temp_db_handle = tempfile.NamedTemporaryFile(prefix="ferreteria_training_", suffix=".db", delete=False)
        temp_db_handle.close()
        log_path = tempfile.NamedTemporaryFile(prefix="ferreteria_training_", suffix=".log", delete=False)
        log_path.close()
        db = Database(
            db_file=temp_db_handle.name,
            catalog_csv=catalog_path,
            log_path=log_path.name,
        )
        profile.setdefault("paths", {})
        profile["paths"]["db"] = temp_db_handle.name
        bot = SalesBot(
            db=db,
            api_key=api_key,
            model=session.get("model_name") or self.costs.resolve_model(session.get("mode_profile") or "cheap"),
            tenant_id=self.tenant_id,
            tenant_profile=profile,
            sandbox_mode=True,
        )
        messages = self.store.list_messages(session["id"])
        bot.contexts[session["id"]] = self.context_builder.build_context(
            bot.system_prompt,
            messages,
            session_summary=session.get("session_summary"),
        )
        state = self._deserialize_state(session.get("session_state_json"))
        bot.sessions[session["id"]] = state
        bot._training_temp_db_path = temp_db_handle.name
        bot._training_temp_log_path = log_path.name
        return bot

    def _serialize_state(self, payload: Dict[str, Any]) -> str:
        import json

        return json.dumps(payload or {}, ensure_ascii=False)

    def _deserialize_state(self, payload: Any) -> Dict[str, Any]:
        import json

        if not payload:
            return {}
        if isinstance(payload, dict):
            return payload
        try:
            value = json.loads(str(payload))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _record_usage(self, session_id: str, usage) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        month = datetime.utcnow().strftime("%Y-%m")
        self.store.upsert_usage(
            metric_scope="session",
            period_key=session_id,
            session_id=session_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_micros=usage.estimated_cost_micros,
            message_count=1,
        )
        self.store.upsert_usage(
            metric_scope="daily",
            period_key=today,
            session_id="",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_micros=usage.estimated_cost_micros,
            message_count=1,
        )
        self.store.upsert_usage(
            metric_scope="monthly",
            period_key=month,
            session_id="",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_micros=usage.estimated_cost_micros,
            message_count=1,
        )

    def _session_total_tokens(self, session_id: str) -> int:
        usage = self.store.get_usage(metric_scope="session", period_key=session_id, session_id=session_id)
        return int((usage or {}).get("total_tokens") or 0)

    def _assert_app_limits(self) -> None:
        daily_limit = self.costs.daily_token_ceiling()
        monthly_limit = self.costs.monthly_token_ceiling()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        month = datetime.utcnow().strftime("%Y-%m")
        if daily_limit:
            daily = self.store.get_usage(metric_scope="daily", period_key=today, session_id="")
            if int((daily or {}).get("total_tokens") or 0) >= daily_limit:
                raise ValueError("Training daily token limit reached")
        if monthly_limit:
            monthly = self.store.get_usage(metric_scope="monthly", period_key=month, session_id="")
            if int((monthly or {}).get("total_tokens") or 0) >= monthly_limit:
                raise ValueError("Training monthly token limit reached")

    @staticmethod
    def _normalize_route_source(value: Any) -> str:
        route_source = str(value or "unknown").strip().lower()
        if route_source == "llm_assisted":
            return "model_assisted"
        return route_source
