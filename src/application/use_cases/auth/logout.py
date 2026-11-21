from src.application.dtos.auth_dtos import LogoutRequestDTO
from src.application.dtos.common import ActorContext
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.interfaces.security_ports import TokenProviderPort
from src.domain.exceptions import AuthorizationDeniedError
from src.domain.value_objects import utc_now


class LogoutUseCase:
    """Revoke refresh tokens for the caller's device session."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        token_provider: TokenProviderPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._token_provider = token_provider

    async def execute(self, actor: ActorContext, request: LogoutRequestDTO) -> None:
        now = utc_now()
        async with self._uow_factory() as uow:
            if request.refresh_token and request.refresh_token.strip():
                token_hash = self._token_provider.hash_refresh_token(request.refresh_token)
                record = await uow.refresh_tokens.get_by_token_hash(token_hash)
                if record is not None:
                    if record.user_id != actor.user_id:
                        raise AuthorizationDeniedError(
                            "Cannot revoke a refresh token owned by another user."
                        )
                    if record.revoked_at_utc is None:
                        await uow.refresh_tokens.revoke_by_id(record.token_id, now)
            else:
                target_device = (request.device_id or actor.device_id).strip()
                await uow.refresh_tokens.revoke_by_user_and_device(
                    actor.user_id,
                    target_device,
                    now,
                )
            await uow.commit()
