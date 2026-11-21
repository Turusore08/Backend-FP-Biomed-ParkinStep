from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.application.interfaces import (
    CloudVideoAnalyzerPort,
    EmergencyNotifierPort,
    PasswordHasherPort,
    RateLimiterPort,
    SkeletonCodecPort,
    UnitOfWork,
    VideoDisposalPort,
)
from src.infrastructure.config import Settings, get_settings
from src.infrastructure.logging import configure_logging
from src.infrastructure.notifications import LoggingEmergencyNotifier
from src.infrastructure.persistence import create_async_engine_from_url, create_session_factory
from src.infrastructure.persistence.codecs.skeleton_codec import ZlibSkeletonCodec
from src.infrastructure.persistence.repositories import SqlAlchemyUnitOfWork
from src.infrastructure.security import (
    Argon2PasswordHasher,
    InMemorySlidingWindowRateLimiter,
    JwtTokenProvider,
)
from src.infrastructure.security.video_disposal import (
    SecureTempVideoDisposer,
    StubCloudVideoAnalyzer,
)
from src.presentation.api.middleware import IdempotencyMiddleware, register_exception_handlers
from src.presentation.api.v1.health import router as health_router
from src.presentation.api.v1.router import api_v1_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await app.state.engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    password_hasher: PasswordHasherPort | None = None,
    rate_limiter: RateLimiterPort | None = None,
    skeleton_codec: SkeletonCodecPort | None = None,
    emergency_notifier: EmergencyNotifierPort | None = None,
    video_disposal: VideoDisposalPort | None = None,
    cloud_video_analyzer: CloudVideoAnalyzerPort | None = None,
    extra_idempotent_patterns: list[str] | None = None,
) -> FastAPI:
    """Create and wire the FastAPI application following Clean Architecture boundaries."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    engine = create_async_engine_from_url(cfg.database_url)
    session_factory = create_session_factory(engine)

    def make_uow() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    hasher = password_hasher or Argon2PasswordHasher()
    dummy_password_hash = hasher.hash("parkinstep-timing-guard")
    token_provider = JwtTokenProvider(
        secret_key=cfg.jwt_secret_key,
        algorithm=cfg.jwt_algorithm,
        access_token_ttl_sec=cfg.jwt_access_token_ttl_sec,
        refresh_token_ttl_days=cfg.jwt_refresh_token_ttl_days,
    )
    limiter = rate_limiter or InMemorySlidingWindowRateLimiter()

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "API sinkronisasi telemedicine, registry model edge OTA, log medikasi Levodopa, "
            "dan notifikasi darurat untuk aplikasi mobile ParkinStep."
        ),
        lifespan=_lifespan,
    )
    app.openapi_version = "3.1.0"

    app.state.settings = cfg
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.uow_factory = make_uow
    app.state.password_hasher = hasher
    app.state.dummy_password_hash = dummy_password_hash
    app.state.token_provider = token_provider
    app.state.rate_limiter = limiter
    app.state.skeleton_codec = skeleton_codec or ZlibSkeletonCodec()
    app.state.emergency_notifier = emergency_notifier or LoggingEmergencyNotifier()
    app.state.video_disposal = video_disposal or SecureTempVideoDisposer(cfg.video_temp_dir)
    app.state.cloud_video_analyzer = cloud_video_analyzer or StubCloudVideoAnalyzer()

    register_exception_handlers(app)

    app.add_middleware(
        IdempotencyMiddleware,
        uow_factory=make_uow,
        token_provider=token_provider,
        ttl_hours=cfg.idempotency_ttl_hours,
        extra_patterns=extra_idempotent_patterns,
    )

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-App-Key"],
    )

    app.include_router(health_router)
    app.include_router(api_v1_router)

    return app
