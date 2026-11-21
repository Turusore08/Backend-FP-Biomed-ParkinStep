from typing import Annotated, cast

from fastapi import Depends, Header, Request

from src.application.dtos import ActorContext
from src.application.interfaces import (
    PasswordHasherPort,
    RateLimiterPort,
    TokenProviderPort,
    UnitOfWorkFactory,
)
from src.application.use_cases.auth import (
    LoginUseCase,
    LogoutUseCase,
    RefreshTokenUseCase,
    RegisterUseCase,
)
from src.application.use_cases.patients import (
    ErasePatientDataUseCase,
    GetPatientUseCase,
    UpdatePatientUseCase,
)
from src.domain.exceptions import TokenInvalidError
from src.infrastructure.config import Settings


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    return cast(UnitOfWorkFactory, request.app.state.uow_factory)


def get_password_hasher(request: Request) -> PasswordHasherPort:
    return cast(PasswordHasherPort, request.app.state.password_hasher)


def get_token_provider(request: Request) -> TokenProviderPort:
    return cast(TokenProviderPort, request.app.state.token_provider)


def get_rate_limiter(request: Request) -> RateLimiterPort:
    return cast(RateLimiterPort, request.app.state.rate_limiter)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
UowFactoryDep = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
PasswordHasherDep = Annotated[PasswordHasherPort, Depends(get_password_hasher)]
TokenProviderDep = Annotated[TokenProviderPort, Depends(get_token_provider)]
RateLimiterDep = Annotated[RateLimiterPort, Depends(get_rate_limiter)]


def get_current_actor(
    token_provider: TokenProviderDep,
    authorization: Annotated[str | None, Header()] = None,
) -> ActorContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise TokenInvalidError("Missing or malformed Bearer authorization header.")
    raw_token = authorization[7:].strip()
    if not raw_token:
        raise TokenInvalidError("Bearer token must not be empty.")
    claims = token_provider.decode_access_token(raw_token)
    return ActorContext(
        user_id=claims.user_id,
        role=claims.role,
        device_id=claims.device_id,
    )


CurrentActorDep = Annotated[ActorContext, Depends(get_current_actor)]


def get_register_use_case(
    uow_factory: UowFactoryDep,
    password_hasher: PasswordHasherDep,
    token_provider: TokenProviderDep,
) -> RegisterUseCase:
    return RegisterUseCase(uow_factory, password_hasher, token_provider)


def get_login_use_case(
    request: Request,
    uow_factory: UowFactoryDep,
    password_hasher: PasswordHasherDep,
    token_provider: TokenProviderDep,
    rate_limiter: RateLimiterDep,
    settings: SettingsDep,
) -> LoginUseCase:
    dummy_hash = cast(str, request.app.state.dummy_password_hash)
    return LoginUseCase(
        uow_factory,
        password_hasher,
        token_provider,
        rate_limiter,
        max_attempts=settings.auth_login_rate_limit_max_attempts,
        window_sec=settings.auth_login_rate_limit_window_sec,
        dummy_password_hash=dummy_hash,
    )


def get_refresh_use_case(
    uow_factory: UowFactoryDep,
    token_provider: TokenProviderDep,
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(uow_factory, token_provider)


def get_logout_use_case(
    uow_factory: UowFactoryDep,
    token_provider: TokenProviderDep,
) -> LogoutUseCase:
    return LogoutUseCase(uow_factory, token_provider)


def get_patient_use_case(uow_factory: UowFactoryDep) -> GetPatientUseCase:
    return GetPatientUseCase(uow_factory)


def get_update_patient_use_case(uow_factory: UowFactoryDep) -> UpdatePatientUseCase:
    return UpdatePatientUseCase(uow_factory)


def get_erase_patient_use_case(
    uow_factory: UowFactoryDep,
    password_hasher: PasswordHasherDep,
) -> ErasePatientDataUseCase:
    return ErasePatientDataUseCase(uow_factory, password_hasher)
