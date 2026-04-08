from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import jwt
except Exception:  # pragma: no cover - optional local fallback
    jwt = None
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.config import get_settings
from app.crm.models import CRMUser


class AuthError(Exception):
    pass


class CRMAuthService:
    def __init__(self):
        settings = get_settings()
        self.secret = settings.CRM_JWT_SECRET or settings.SECRET_KEY
        self.ttl_minutes = settings.CRM_JWT_TTL_MINUTES
        self._serializer = URLSafeTimedSerializer(self.secret, salt="crm-access")

    def hash_password(self, password: str) -> str:
        return generate_password_hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return check_password_hash(password_hash, password)

    def issue_token(self, user: CRMUser) -> str:
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=self.ttl_minutes)
        payload: dict[str, Any] = {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "crm_access",
        }
        if jwt is not None:
            return jwt.encode(payload, self.secret, algorithm="HS256")
        # Local fallback token (signed, timestamp enforced in decode).
        return self._serializer.dumps(payload)

    def decode_token(self, token: str) -> dict[str, Any]:
        if jwt is not None:
            try:
                payload = jwt.decode(token, self.secret, algorithms=["HS256"])
                if payload.get("type") != "crm_access":
                    raise AuthError("Invalid token type")
                return payload
            except jwt.ExpiredSignatureError as exc:
                raise AuthError("Token expired") from exc
            except jwt.InvalidTokenError as exc:
                raise AuthError("Invalid token") from exc

        try:
            payload = self._serializer.loads(token, max_age=self.ttl_minutes * 60)
            if payload.get("type") != "crm_access":
                raise AuthError("Invalid token type")
            return payload
        except SignatureExpired as exc:
            raise AuthError("Token expired") from exc
        except BadSignature as exc:
            raise AuthError("Invalid token") from exc
