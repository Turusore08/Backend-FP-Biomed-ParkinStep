import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from src.application.interfaces.security_ports import AccessTokenClaims
from src.domain.enums import UserRole
from src.domain.exceptions import TokenExpiredError, TokenInvalidError


class JwtTokenProvider:
    """JWT access token issuer/verifier and SHA-256 hashed refresh token generator."""

    _ISSUER = "parkinstep-api"

    def __init__(
        self,
        *,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_ttl_sec: int = 900,
        refresh_token_ttl_days: int = 30,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_token_ttl_sec = access_token_ttl_sec
        self._refresh_token_ttl_days = refresh_token_ttl_days

    @property
    def refresh_token_ttl_days(self) -> int:
        return self._refresh_token_ttl_days

    def create_access_token(
        self,
        user_id: UUID,
        role: UserRole,
        device_id: str,
    ) -> tuple[str, int]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._access_token_ttl_sec)
        payload = {
            "iss": self._ISSUER,
            "sub": str(user_id),
            "role": role.value,
            "device_id": device_id,
            "jti": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        encoded = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
        return encoded, self._access_token_ttl_sec

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                issuer=self._ISSUER,
                options={"require": ["iss", "sub", "role", "device_id", "jti", "exp"]},
            )
            return AccessTokenClaims(
                user_id=UUID(str(payload["sub"])),
                role=UserRole(str(payload["role"])),
                device_id=str(payload["device_id"]),
                jti=str(payload["jti"]),
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Access token has expired.") from exc
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise TokenInvalidError("Access token is invalid or malformed.") from exc

    def generate_refresh_token(self) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(48)
        return raw_token, self.hash_refresh_token(raw_token)

    def hash_refresh_token(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
