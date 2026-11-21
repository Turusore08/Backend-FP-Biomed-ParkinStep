from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.application.dtos import (
    LoginRequestDTO,
    LogoutRequestDTO,
    RefreshTokenRequestDTO,
    RegisterRequestDTO,
)
from src.application.use_cases.auth import (
    LoginUseCase,
    LogoutUseCase,
    RefreshTokenUseCase,
    RegisterUseCase,
)
from src.presentation.dependencies import (
    CurrentActorDep,
    get_login_use_case,
    get_logout_use_case,
    get_refresh_use_case,
    get_register_use_case,
)
from src.presentation.schemas import (
    AuthTokenResponse,
    LoginRequest,
    LogoutRequest,
    ProblemDetailsSchema,
    RefreshRequest,
    RegisterRequest,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _extract_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register akun baru (PATIENT | CAREGIVER | CLINICIAN)",
    responses={
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def register(
    payload: RegisterRequest,
    use_case: Annotated[RegisterUseCase, Depends(get_register_use_case)],
) -> AuthTokenResponse:
    dto = await use_case.execute(
        RegisterRequestDTO(
            identifier=payload.identifier,
            password=payload.password,
            role=payload.role,
            device_id=payload.device_id,
            display_name=payload.display_name,
            birth_year=payload.birth_year,
            consent_local=payload.consent_local,
            consent_skeleton_sync=payload.consent_skeleton_sync,
            consent_cloud_video=payload.consent_cloud_video,
        )
    )
    return AuthTokenResponse.from_dto(dto)


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Autentikasi akun pasien, caregiver, atau klinisi",
    responses={
        401: {"model": ProblemDetailsSchema},
        429: {"model": ProblemDetailsSchema},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    use_case: Annotated[LoginUseCase, Depends(get_login_use_case)],
) -> AuthTokenResponse:
    dto = await use_case.execute(
        LoginRequestDTO(
            identifier=payload.identifier,
            password=payload.password,
            device_id=payload.device_id,
            client_ip=_extract_client_ip(request),
        )
    )
    return AuthTokenResponse.from_dto(dto)


@router.post(
    "/refresh",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotasi Refresh Token -> Access JWT baru",
    responses={401: {"model": ProblemDetailsSchema}},
)
async def refresh(
    payload: RefreshRequest,
    use_case: Annotated[RefreshTokenUseCase, Depends(get_refresh_use_case)],
) -> AuthTokenResponse:
    dto = await use_case.execute(
        RefreshTokenRequestDTO(
            refresh_token=payload.refresh_token,
            device_id=payload.device_id,
        )
    )
    return AuthTokenResponse.from_dto(dto)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token sesi perangkat",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
    },
)
async def logout(
    actor: CurrentActorDep,
    use_case: Annotated[LogoutUseCase, Depends(get_logout_use_case)],
    payload: LogoutRequest | None = None,
) -> Response:
    req = payload or LogoutRequest()
    await use_case.execute(
        actor,
        LogoutRequestDTO(
            refresh_token=req.refresh_token,
            device_id=req.device_id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
