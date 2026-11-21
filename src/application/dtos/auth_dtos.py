from dataclasses import dataclass
from uuid import UUID

from src.domain.enums import UserRole


@dataclass(frozen=True, slots=True)
class RegisterRequestDTO:
    identifier: str
    password: str
    role: UserRole
    device_id: str
    display_name: str | None = None
    birth_year: int | None = None
    consent_local: bool = True
    consent_skeleton_sync: bool = False
    consent_cloud_video: bool = False


@dataclass(frozen=True, slots=True)
class LoginRequestDTO:
    identifier: str
    password: str
    device_id: str
    client_ip: str = "unknown"


@dataclass(frozen=True, slots=True)
class RefreshTokenRequestDTO:
    refresh_token: str
    device_id: str


@dataclass(frozen=True, slots=True)
class LogoutRequestDTO:
    refresh_token: str | None = None
    device_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuthTokenResponseDTO:
    access_token: str
    refresh_token: str
    expires_in_sec: int
    user_id: UUID
    role: UserRole
