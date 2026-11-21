from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel

from src.presentation.api.middleware import IDEMPOTENT_ROUTE_PATTERNS


class _DummyIdemBody(BaseModel):
    item_id: str
    fail: bool = False


async def test_health_security_headers_openapi_and_rfc7807(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    health = await client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["Referrer-Policy"] == "no-referrer"
    assert health.headers["Cache-Control"] == "no-store"

    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    openapi = (await client.get("/openapi.json")).json()
    assert openapi["openapi"] == "3.1.0"
    assert "/api/v1/auth/register" in openapi["paths"]
    assert "/api/v1/auth/login" in openapi["paths"]
    assert "/api/v1/patients/{patient_id}" in openapi["paths"]
    assert openapi["components"]["schemas"]["UserRole"]["enum"] == [
        "PATIENT",
        "CAREGIVER",
        "CLINICIAN",
    ]

    # 404 RFC 7807
    not_found = await client.get("/api/v1/does-not-exist")
    assert not_found.status_code == 404
    assert not_found.headers["content-type"].startswith("application/problem+json")
    assert set(not_found.json().keys()) >= {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "error_code",
    }

    # 500 RFC 7807 without leaking exception internals
    @app.get("/api/v1/test-boom")
    async def _boom() -> dict[str, str]:
        raise RuntimeError("sensitive_db_password=supersecret")

    boom_resp = await client.get("/api/v1/test-boom")
    assert boom_resp.status_code == 500
    assert boom_resp.headers["content-type"].startswith("application/problem+json")
    assert boom_resp.json()["error_code"] == "INTERNAL_SERVER_ERROR"
    assert "supersecret" not in boom_resp.text


async def test_idempotency_middleware_contract_and_replay(
    client: AsyncClient,
    app: FastAPI,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    # Verify production route patterns match all 5 required mutating endpoints
    uid = str(uuid4())
    for path in (
        "/api/v1/sessions",
        f"/api/v1/sessions/{uid}/skeleton-frames",
        f"/api/v1/sessions/{uid}/results",
        f"/api/v1/patients/{uid}/medications",
        "/api/v1/alerts/emergency",
    ):
        assert any(p.match(path) for p in IDEMPOTENT_ROUTE_PATTERNS), path

    execution_count = 0

    @app.post("/api/v1/test-idempotent", status_code=201)
    async def _dummy_endpoint(body: _DummyIdemBody) -> dict[str, Any]:
        nonlocal execution_count
        execution_count += 1
        if body.fail:
            raise RuntimeError("transient failure")
        return {"created": body.item_id, "count": execution_count}

    reg_tokens = (
        await client.post("/api/v1/auth/register", json=register_payload_factory())
    ).json()
    auth_headers = {"Authorization": f"Bearer {reg_tokens['access_token']}"}

    # Missing Idempotency-Key -> 400 RFC 7807
    missing = await client.post(
        "/api/v1/test-idempotent",
        headers=auth_headers,
        json={"item_id": "abc"},
    )
    assert missing.status_code == 400
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert missing.json()["error_code"] == "IDEMPOTENCY_KEY_REQUIRED"

    # Invalid UUID -> 400 RFC 7807
    invalid = await client.post(
        "/api/v1/test-idempotent",
        headers={**auth_headers, "Idempotency-Key": "not-a-uuid"},
        json={"item_id": "abc"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error_code"] == "IDEMPOTENCY_KEY_INVALID"

    # First execution succeeds
    idem_key = str(uuid4())
    first = await client.post(
        "/api/v1/test-idempotent",
        headers={**auth_headers, "Idempotency-Key": idem_key},
        json={"item_id": "session-1"},
    )
    assert first.status_code == 201
    assert first.json() == {"created": "session-1", "count": 1}
    assert execution_count == 1

    # Exact retry returns cached response WITHOUT incrementing execution_count
    replay = await client.post(
        "/api/v1/test-idempotent",
        headers={**auth_headers, "Idempotency-Key": idem_key},
        json={"item_id": "session-1"},
    )
    assert replay.status_code == 201
    assert replay.headers.get("X-Idempotency-Replayed") == "true"
    assert replay.json() == {"created": "session-1", "count": 1}
    assert execution_count == 1

    # Different payload with same key -> 409 IDEMPOTENCY_PAYLOAD_MISMATCH
    mismatch = await client.post(
        "/api/v1/test-idempotent",
        headers={**auth_headers, "Idempotency-Key": idem_key},
        json={"item_id": "session-2"},
    )
    assert mismatch.status_code == 409
    assert mismatch.headers["content-type"].startswith("application/problem+json")
    assert mismatch.json()["error_code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"

    # 5xx error must release IN_PROGRESS lock so retry can succeed
    retry_key = str(uuid4())
    failed = await client.post(
        "/api/v1/test-idempotent",
        headers={**auth_headers, "Idempotency-Key": retry_key},
        json={"item_id": "session-3", "fail": True},
    )
    assert failed.status_code == 500

    recovered = await client.post(
        "/api/v1/test-idempotent",
        headers={**auth_headers, "Idempotency-Key": retry_key},
        json={"item_id": "session-3", "fail": True},
    )
    assert recovered.status_code == 500
    assert execution_count == 3
