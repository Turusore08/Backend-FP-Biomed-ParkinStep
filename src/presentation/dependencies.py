import secrets
from typing import Annotated, cast

from fastapi import Depends, Header, Request

from src.application.dtos import ActorContext
from src.application.interfaces import (
    ClinicalReportPdfRendererPort,
    CloudKeypointClassifierPort,
    CloudVideoAnalyzerPort,
    EmergencyNotifierPort,
    PasswordHasherPort,
    RateLimiterPort,
    SkeletonCodecPort,
    TokenProviderPort,
    UnitOfWorkFactory,
    VideoDisposalPort,
)
from src.application.use_cases.alerts import DispatchEmergencyAlertUseCase
from src.application.use_cases.analytics import GetPatientTrendsUseCase
from src.application.use_cases.auth import (
    LoginUseCase,
    LogoutUseCase,
    RefreshTokenUseCase,
    RegisterUseCase,
)
from src.application.use_cases.medications import (
    CreateMedicationLogUseCase,
    ListMedicationLogsUseCase,
)
from src.application.use_cases.models import GetModelManifestUseCase
from src.application.use_cases.patients import (
    ErasePatientDataUseCase,
    GetPatientUseCase,
    UpdatePatientUseCase,
)
from src.application.use_cases.sessions import (
    AnalyzeVideoFallbackUseCase,
    CreateSessionUseCase,
    GetSessionReportUseCase,
    UploadSessionResultsUseCase,
    UploadSkeletonBatchUseCase,
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


def get_skeleton_codec(request: Request) -> SkeletonCodecPort:
    return cast(SkeletonCodecPort, request.app.state.skeleton_codec)


def get_emergency_notifier(request: Request) -> EmergencyNotifierPort:
    return cast(EmergencyNotifierPort, request.app.state.emergency_notifier)


def get_video_disposal(request: Request) -> VideoDisposalPort:
    return cast(VideoDisposalPort, request.app.state.video_disposal)


def get_cloud_video_analyzer(request: Request) -> CloudVideoAnalyzerPort:
    return cast(CloudVideoAnalyzerPort, request.app.state.cloud_video_analyzer)


def get_pdf_renderer(request: Request) -> ClinicalReportPdfRendererPort:
    return cast(ClinicalReportPdfRendererPort, request.app.state.pdf_renderer)


def get_cloud_classifier(request: Request) -> CloudKeypointClassifierPort:
    return cast(CloudKeypointClassifierPort, request.app.state.cloud_classifier)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
UowFactoryDep = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
PasswordHasherDep = Annotated[PasswordHasherPort, Depends(get_password_hasher)]
TokenProviderDep = Annotated[TokenProviderPort, Depends(get_token_provider)]
RateLimiterDep = Annotated[RateLimiterPort, Depends(get_rate_limiter)]
SkeletonCodecDep = Annotated[SkeletonCodecPort, Depends(get_skeleton_codec)]
EmergencyNotifierDep = Annotated[EmergencyNotifierPort, Depends(get_emergency_notifier)]
VideoDisposalDep = Annotated[VideoDisposalPort, Depends(get_video_disposal)]
CloudVideoAnalyzerDep = Annotated[CloudVideoAnalyzerPort, Depends(get_cloud_video_analyzer)]
PdfRendererDep = Annotated[ClinicalReportPdfRendererPort, Depends(get_pdf_renderer)]
CloudClassifierDep = Annotated[CloudKeypointClassifierPort, Depends(get_cloud_classifier)]


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


def verify_jwt_or_app_key(
    token_provider: TokenProviderDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
    x_app_key: Annotated[str | None, Header(alias="X-App-Key")] = None,
) -> None:
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
        if not raw_token:
            raise TokenInvalidError("Bearer token must not be empty.")
        token_provider.decode_access_token(raw_token)
        return
    if settings.ota_app_key and x_app_key:
        if secrets.compare_digest(x_app_key, settings.ota_app_key):
            return
        raise TokenInvalidError("Invalid X-App-Key credential.")
    raise TokenInvalidError("Bearer JWT or valid X-App-Key is required.")


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


def get_create_medication_use_case(uow_factory: UowFactoryDep) -> CreateMedicationLogUseCase:
    return CreateMedicationLogUseCase(uow_factory)


def get_list_medications_use_case(uow_factory: UowFactoryDep) -> ListMedicationLogsUseCase:
    return ListMedicationLogsUseCase(uow_factory)


def get_create_session_use_case(uow_factory: UowFactoryDep) -> CreateSessionUseCase:
    return CreateSessionUseCase(uow_factory)


def get_upload_skeleton_use_case(
    uow_factory: UowFactoryDep,
    skeleton_codec: SkeletonCodecDep,
) -> UploadSkeletonBatchUseCase:
    return UploadSkeletonBatchUseCase(uow_factory, skeleton_codec)


def get_upload_session_results_use_case(
    uow_factory: UowFactoryDep,
) -> UploadSessionResultsUseCase:
    return UploadSessionResultsUseCase(uow_factory)


def get_analyze_video_use_case(
    uow_factory: UowFactoryDep,
    video_disposal: VideoDisposalDep,
    analyzer: CloudVideoAnalyzerDep,
    settings: SettingsDep,
) -> AnalyzeVideoFallbackUseCase:
    return AnalyzeVideoFallbackUseCase(
        uow_factory,
        video_disposal,
        analyzer,
        max_upload_bytes=settings.max_video_upload_bytes,
    )


def get_session_report_use_case(
    uow_factory: UowFactoryDep,
    pdf_renderer: PdfRendererDep,
) -> GetSessionReportUseCase:
    return GetSessionReportUseCase(uow_factory, pdf_renderer)


def get_patient_trends_use_case(uow_factory: UowFactoryDep) -> GetPatientTrendsUseCase:
    return GetPatientTrendsUseCase(uow_factory)


def get_dispatch_alert_use_case(
    uow_factory: UowFactoryDep,
    notifier: EmergencyNotifierDep,
) -> DispatchEmergencyAlertUseCase:
    return DispatchEmergencyAlertUseCase(uow_factory, notifier)


def get_model_manifest_use_case(
    uow_factory: UowFactoryDep,
    settings: SettingsDep,
) -> GetModelManifestUseCase:
    return GetModelManifestUseCase(uow_factory, settings.model_cdn_base_url)
