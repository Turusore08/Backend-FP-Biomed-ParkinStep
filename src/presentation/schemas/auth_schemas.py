from uuid import UUID

from pydantic import Field

from src.application.dtos import AuthTokenResponseDTO
from src.domain.enums import UserRole
from src.presentation.schemas.common import StrictBaseSchema


class RegisterRequest(StrictBaseSchema):
    identifier: str = Field(..., min_length=3, max_length=160)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.PATIENT
    device_id: str = Field(..., min_length=1, max_length=160)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    birth_year: int | None = Field(default=None, ge=1900, le=2026)
    consent_local: bool = True
    consent_skeleton_sync: bool = False
    consent_cloud_video: bool = False


class LoginRequest(StrictBaseSchema):
    identifier: str = Field(..., min_length=1, max_length=160)
    password: str = Field(..., min_length=1, max_length=128)
    device_id: str = Field(..., min_length=1, max_length=160)


class RefreshRequest(StrictBaseSchema):
    refresh_token: str = Field(..., min_length=10, max_length=512)
    device_id: str = Field(..., min_length=1, max_length=160)


class LogoutRequest(StrictBaseSchema):
    refresh_token: str | None = Field(default=None, min_length=10, max_length=512)
    device_id: str | None = Field(default=None, min_length=1, max_length=160)


class AuthTokenResponse(StrictBaseSchema):
    access_token: str
    refresh_token: str
    expires_in_sec: int
    user_id: UUID
    role: UserRole

    @classmethod
    def from_dto(cls, dto: AuthTokenResponseDTO) -> "AuthTokenResponse":
        return cls(
            access_token=dto.access_token,
            refresh_token=dto.refresh_token,
            expires_in_sec=dto.expires_in_sec,
            user_id=dto.user_id,
            role=dto.role,
        )
