from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.config import Settings
from src.infrastructure.persistence.models import Base
from src.infrastructure.security import Argon2PasswordHasher
from src.presentation.api.app import create_app


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "parkinstep_test.db"
    return Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key="test-secret-key-must-be-at-least-32-chars-long!",
        jwt_access_token_ttl_sec=900,
        jwt_refresh_token_ttl_days=30,
        auth_login_rate_limit_max_attempts=5,
        auth_login_rate_limit_window_sec=60,
        idempotency_ttl_hours=24,
        ota_app_key="test-ota-app-key-secret",
        max_video_upload_bytes=1024 * 64,
        video_temp_dir=str(tmp_path / "video_tmp"),
        log_level="WARNING",
    )


@pytest.fixture
async def app(test_settings: Settings) -> AsyncIterator[FastAPI]:
    fast_hasher = Argon2PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    application = create_app(
        test_settings,
        password_hasher=fast_hasher,
        extra_idempotent_patterns=[r"^/api/v1/test-idempotent$"],
    )
    async with application.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield application
    finally:
        await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def register_payload_factory() -> Callable[..., dict[str, Any]]:
    def _build(
        *,
        identifier: str | None = None,
        password: str = "ParkinStep#2026",
        role: str = "PATIENT",
        device_id: str | None = None,
        display_name: str | None = "Budi Santoso",
        birth_year: int | None = 1958,
        consent_local: bool = True,
        consent_skeleton_sync: bool = True,
        consent_cloud_video: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "identifier": identifier or f"user_{uuid4().hex[:8]}@parkinstep.id",
            "password": password,
            "role": role,
            "device_id": device_id or f"device-{uuid4().hex[:8]}",
            "consent_local": consent_local,
            "consent_skeleton_sync": consent_skeleton_sync,
            "consent_cloud_video": consent_cloud_video,
        }
        if display_name is not None:
            payload["display_name"] = display_name
        if birth_year is not None:
            payload["birth_year"] = birth_year
        return payload

    return _build
