from src.application.dtos.auth_dtos import AuthTokenResponseDTO, LoginRequestDTO
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.interfaces.security_ports import (
    PasswordHasherPort,
    RateLimiterPort,
    TokenProviderPort,
)
from src.application.use_cases.auth.token_helper import issue_token_pair
from src.domain.exceptions import InvalidCredentialsError, RateLimitExceededError
from src.domain.value_objects import utc_now


class LoginUseCase:
    """Authenticate an existing account with rate limiting and constant-time check."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
        token_provider: TokenProviderPort,
        rate_limiter: RateLimiterPort,
        *,
        max_attempts: int = 10,
        window_sec: int = 60,
        dummy_password_hash: str | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._token_provider = token_provider
        self._rate_limiter = rate_limiter
        self._max_attempts = max_attempts
        self._window_sec = window_sec
        self._dummy_hash = dummy_password_hash or password_hasher.hash("parkinstep-timing-guard")

    async def execute(self, request: LoginRequestDTO) -> AuthTokenResponseDTO:
        normalized_identifier = request.identifier.strip().lower()
        rate_key = f"login:{request.client_ip}:{normalized_identifier}"
        allowed, retry_after_sec = await self._rate_limiter.check_and_consume(
            rate_key,
            self._max_attempts,
            self._window_sec,
        )
        if not allowed:
            raise RateLimitExceededError(retry_after_sec=retry_after_sec)

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_identifier(normalized_identifier)
            target_hash = user.password_hash if user is not None else self._dummy_hash
            verified = self._password_hasher.verify(request.password, target_hash)

            if user is None or not user.is_active or not verified:
                raise InvalidCredentialsError("Invalid account identifier or password.")

            tokens = await issue_token_pair(
                uow,
                self._token_provider,
                user,
                request.device_id.strip(),
                now=utc_now(),
            )
            await uow.commit()
            return tokens
