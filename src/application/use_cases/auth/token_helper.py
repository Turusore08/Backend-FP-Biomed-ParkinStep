from datetime import datetime, timedelta
from uuid import UUID, uuid4

from src.application.dtos.auth_dtos import AuthTokenResponseDTO
from src.application.interfaces.repositories import UnitOfWork
from src.application.interfaces.security_ports import TokenProviderPort
from src.domain.entities import RefreshTokenRecord, UserAccount


async def issue_token_pair(
    uow: UnitOfWork,
    token_provider: TokenProviderPort,
    user: UserAccount,
    device_id: str,
    *,
    family_id: UUID | None = None,
    now: datetime,
) -> AuthTokenResponseDTO:
    """Create and persist a rotated refresh token paired with a fresh JWT access token."""
    access_token, expires_in_sec = token_provider.create_access_token(
        user_id=user.user_id,
        role=user.role,
        device_id=device_id,
    )
    raw_refresh, refresh_hash = token_provider.generate_refresh_token()
    refresh_record = RefreshTokenRecord(
        token_id=uuid4(),
        user_id=user.user_id,
        device_id=device_id,
        token_hash=refresh_hash,
        family_id=family_id or uuid4(),
        expires_at_utc=now + timedelta(days=token_provider.refresh_token_ttl_days),
        revoked_at_utc=None,
        created_at_utc=now,
    )
    await uow.refresh_tokens.create(refresh_record)
    return AuthTokenResponseDTO(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in_sec=expires_in_sec,
        user_id=user.user_id,
        role=user.role,
    )
