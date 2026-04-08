from __future__ import annotations

import os
from typing import Any
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock

import structlog

try:
    import redis
except Exception:  # pragma: no cover - dependency is available in production image
    redis = None


logger = structlog.get_logger()


class InMemoryRateLimiter:
    def __init__(self):
        self._lock = Lock()
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = datetime.utcnow()
        threshold = now - timedelta(seconds=window_seconds)

        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] < threshold:
                dq.popleft()

            if len(dq) >= limit:
                return False

            dq.append(now)
            return True


class HybridRateLimiter:
    """Use Redis when available for multi-instance limits, fallback to in-memory."""

    _REDIS_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

    def __init__(self):
        self._memory = InMemoryRateLimiter()
        self._redis: Any | None = None
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if not redis_url:
            return

        if redis is None:
            logger.warning("crm_rate_limiter_redis_dependency_missing")
            return

        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self._redis = client
        except Exception as exc:
            logger.warning("crm_rate_limiter_redis_unavailable error=%s", exc)
            self._redis = None

    def _disable_redis(self, exc: Exception) -> None:
        if self._redis is not None:
            logger.warning("crm_rate_limiter_redis_runtime_error error=%s fallback=memory", exc)
        self._redis = None

    def _redis_allow(self, key: str, limit: int, window_seconds: int) -> bool | None:
        if self._redis is None:
            return None

        redis_key = f"crm:ratelimit:{key}"
        ttl = max(1, int(window_seconds))
        try:
            current = int(self._redis.eval(self._REDIS_SCRIPT, 1, redis_key, str(ttl)))
        except Exception as exc:
            self._disable_redis(exc)
            return None
        return current <= limit

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        redis_result = self._redis_allow(key=key, limit=limit, window_seconds=window_seconds)
        if redis_result is not None:
            return redis_result
        return self._memory.allow(key=key, limit=limit, window_seconds=window_seconds)


rate_limiter = HybridRateLimiter()
