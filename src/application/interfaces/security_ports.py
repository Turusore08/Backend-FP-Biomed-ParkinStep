from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from src.domain.enums import UserRole


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Verified claims extracted from a JWT access token."""

    user_id: UUID
    role: UserRole
    device_id: str
    jti: str


class PasswordHasherPort(Protocol):
    """Port for password hashing and constant-time verification (Argon2id)."""

    def hash(self, password: str) -> str:
        ...

    def verify(self, password: str, password_hash: str) -> bool:
        ...


class TokenProviderPort(Protocol):
    """Port for JWT access token signing/verification and refresh token generation."""

    @property
    def refresh_token_ttl_days(self) -> int:
        ...

    def create_access_token(
        self,
        user_id: UUID,
        role: UserRole,
        device_id: str,
    ) -> tuple[str, int]:
        """Return (jwt_token, expires_in_sec)."""
        ...

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        ...

    def generate_refresh_token(self) -> tuple[str, str]:
        """Return (raw_opaque_token, sha256_token_hash)."""
        ...

    def hash_refresh_token(self, raw_token: str) -> str:
        ...


class RateLimiterPort(Protocol):
    """Port for sliding-window rate limiting on sensitive endpoints."""

    async def check_and_consume(
        self,
        key: str,
        max_attempts: int,
        window_sec: int,
    ) -> tuple[bool, int]:
        """Return (allowed, retry_after_sec)."""
        ...
