from collections.abc import Callable
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select

from src.infrastructure.persistence.models import ConsentAuditLogORM, RefreshTokenORM


async def test_register_patient_and_caregiver_lifecycle(
    client: AsyncClient,
    app: Any,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    payload = register_payload_factory(role="PATIENT", birth_year=1957)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "PATIENT"
    assert body["expires_in_sec"] == 900
    assert UUID(body["user_id"])
    assert body["access_token"]
    assert body["refresh_token"]

    async with app.state.session_factory() as session:
        audit_rows = (
            await session.execute(
                select(ConsentAuditLogORM).where(
                    ConsentAuditLogORM.patient_id == UUID(body["user_id"])
                )
            )
        ).scalars().all()
        assert len(audit_rows) == 3

    dup = await client.post("/api/v1/auth/register", json=payload)
    assert dup.status_code == 409
    assert dup.headers["content-type"].startswith("application/problem+json")
    assert dup.json()["error_code"] == "AUTH_IDENTIFIER_EXISTS"

    bad_consent = register_payload_factory(consent_local=False)
    bad_resp = await client.post("/api/v1/auth/register", json=bad_consent)
    assert bad_resp.status_code == 422
    assert bad_resp.headers["content-type"].startswith("application/problem+json")
    assert bad_resp.json()["error_code"] == "VALIDATION_ERROR"

    caregiver_payload = register_payload_factory(
        role="CAREGIVER",
        display_name=None,
        birth_year=None,
    )
    cg_resp = await client.post("/api/v1/auth/register", json=caregiver_payload)
    assert cg_resp.status_code == 201
    assert cg_resp.json()["role"] == "CAREGIVER"


async def test_login_rate_limit_refresh_rotation_reuse_and_logout(
    client: AsyncClient,
    app: Any,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    reg = register_payload_factory(identifier="pak.budi@parkinstep.id", password="StrongPass#123")
    reg_resp = await client.post("/api/v1/auth/register", json=reg)
    assert reg_resp.status_code == 201

    login_ok = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "PAK.BUDI@parkinstep.id",
            "password": "StrongPass#123",
            "device_id": reg["device_id"],
        },
    )
    assert login_ok.status_code == 200
    tokens_v1 = login_ok.json()

    refresh_ok = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens_v1["refresh_token"], "device_id": reg["device_id"]},
    )
    assert refresh_ok.status_code == 200
    tokens_v2 = refresh_ok.json()
    assert tokens_v2["refresh_token"] != tokens_v1["refresh_token"]

    # Replay revoked tokens_v1 -> triggers whole-family revocation
    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens_v1["refresh_token"], "device_id": reg["device_id"]},
    )
    assert reuse.status_code == 401
    assert reuse.headers["content-type"].startswith("application/problem+json")
    assert reuse.json()["error_code"] == "AUTH_TOKEN_REUSE_DETECTED"

    # Subsequent use of tokens_v2 must also fail because the family was revoked
    after_reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens_v2["refresh_token"], "device_id": reg["device_id"]},
    )
    assert after_reuse.status_code == 401

    # Login again and logout cleanly
    login_again = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "pak.budi@parkinstep.id",
            "password": "StrongPass#123",
            "device_id": reg["device_id"],
        },
    )
    assert login_again.status_code == 200
    tokens_v3 = login_again.json()

    logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens_v3['access_token']}"},
        json={"refresh_token": tokens_v3["refresh_token"]},
    )
    assert logout_resp.status_code == 204

    v3_hash = app.state.token_provider.hash_refresh_token(tokens_v3["refresh_token"])
    async with app.state.session_factory() as session:
        v3_row = (
            await session.execute(
                select(RefreshTokenORM).where(RefreshTokenORM.token_hash == v3_hash)
            )
        ).scalar_one()
        assert v3_row.revoked_at_utc is not None

    # Device-wide logout revokes any remaining tokens for (user_id, device_id)
    device_logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens_v3['access_token']}"},
        json={},
    )
    assert device_logout_resp.status_code == 204

    async with app.state.session_factory() as session:
        all_rows = (
            await session.execute(
                select(RefreshTokenORM).where(
                    RefreshTokenORM.user_id == UUID(tokens_v3["user_id"])
                )
            )
        ).scalars().all()
        assert all(row.revoked_at_utc is not None for row in all_rows)

    # Trigger rate limit (max_attempts = 5 in test_settings; 2 logins already used)
    for _ in range(3):
        bad = await client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "pak.budi@parkinstep.id",
                "password": "WrongPassword",
                "device_id": reg["device_id"],
            },
        )
        assert bad.status_code == 401

    limited = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "pak.budi@parkinstep.id",
            "password": "WrongPassword",
            "device_id": reg["device_id"],
        },
    )
    assert limited.status_code == 429
    assert limited.headers["content-type"].startswith("application/problem+json")
    assert int(limited.headers["Retry-After"]) >= 1
    assert limited.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
