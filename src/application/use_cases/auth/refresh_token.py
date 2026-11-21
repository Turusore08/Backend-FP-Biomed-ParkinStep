from src.application.dtos.auth_dtos import AuthTokenResponseDTO, RefreshTokenRequestDTO
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.interfaces.security_ports import TokenProviderPort
from src.application.use_cases.auth.token_helper import issue_token_pair
from src.domain.exceptions import (
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    TokenReuseDetectedError,
)
from src.domain.value_objects import utc_now


class RefreshTokenUseCase:
    """Rotate a refresh token and revoke the entire token family on replay detection."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        token_provider: TokenProviderPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._token_provider = token_provider

    async def execute(self, request: RefreshTokenRequestDTO) -> AuthTokenResponseDTO:
        token_hash = self._token_provider.hash_refresh_token(request.refresh_token)
        now = utc_now()

        async with self._uow_factory() as uow:
            record = await uow.refresh_tokens.get_by_token_hash(token_hash)
            if record is None:
                raise TokenInvalidError("Refresh token is invalid.")

            if record.revoked_at_utc is not None:
                # Replay / token theft detected: revoke the entire rotation family immediately.
                await uow.refresh_tokens.revoke_family(record.family_id, now)
                await uow.commit()
                raise TokenReuseDetectedError(
                    "Refresh token reuse detected. Session family has been revoked."
                )

            if record.expires_at_utc <= now:
                await uow.refresh_tokens.revoke_by_id(record.token_id, now)
                await uow.commit()
                raise TokenExpiredError("Refresh token has expired.")

            if record.device_id != request.device_id.strip():
                await uow.refresh_tokens.revoke_family(record.family_id, now)
                await uow.commit()
                raise TokenInvalidError("Refresh token does not match the requesting device.")

            user = await uow.users.get_by_id(record.user_id)
            if user is None or not user.is_active:
                raise InvalidCredentialsError("Account is inactive or no longer exists.")

            await uow.refresh_tokens.revoke_by_id(record.token_id, now)
            tokens = await issue_token_pair(
                uow,
                self._token_provider,
                user,
                record.device_id,
                family_id=record.family_id,
                now=now,
            )
            await uow.commit()
            return tokens
