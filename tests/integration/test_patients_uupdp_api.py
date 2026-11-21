import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select

from src.domain.value_objects import format_utc_z, utc_now
from src.infrastructure.persistence.models import (
    ConsentAuditLogORM,
    EmergencyContactORM,
    IdempotencyKeyORM,
    PatientAccessGrantORM,
    PatientORM,
    RefreshTokenORM,
    UserORM,
)

UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


async def test_patient_profile_patch_nullable_vs_optional_and_lww(
    client: AsyncClient,
    app: Any,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    p1 = register_payload_factory(role="PATIENT", birth_year=None, consent_skeleton_sync=True)
    r1 = (await client.post("/api/v1/auth/register", json=p1)).json()
    headers1 = {"Authorization": f"Bearer {r1['access_token']}"}
    pid1 = r1["user_id"]

    # Explicit null birth_year must be present in JSON (nullable != optional)
    get_res = await client.get(f"/api/v1/patients/{pid1}", headers=headers1)
    assert get_res.status_code == 200
    profile = get_res.json()
    assert "birth_year" in profile
    assert profile["birth_year"] is None
    assert UTC_Z_RE.match(profile["updated_at_utc"])
    assert UTC_Z_RE.match(profile["consent"]["accepted_at_utc"])

    # Set birth_year and emergency contacts
    patch1 = await client.patch(
        f"/api/v1/patients/{pid1}",
        headers=headers1,
        json={
            "birth_year": 1956,
            "emergency_contacts": [
                {
                    "name": "Ibu Siti",
                    "phone_e164": "+6281234567890",
                    "relation": "Istri",
                    "is_primary": True,
                }
            ],
        },
    )
    assert patch1.status_code == 200
    assert patch1.json()["birth_year"] == 1956
    assert len(patch1.json()["emergency_contacts"]) == 1

    # Omitting birth_year preserves 1956
    patch2 = await client.patch(
        f"/api/v1/patients/{pid1}",
        headers=headers1,
        json={"display_name": "Bapak Budi"},
    )
    assert patch2.status_code == 200
    assert patch2.json()["birth_year"] == 1956
    assert patch2.json()["display_name"] == "Bapak Budi"

    # Explicit birth_year: null clears birth_year
    patch3 = await client.patch(
        f"/api/v1/patients/{pid1}",
        headers=headers1,
        json={"birth_year": None, "consent_skeleton_sync": False},
    )
    assert patch3.status_code == 200
    assert patch3.json()["birth_year"] is None
    assert patch3.json()["consent"]["consent_skeleton_sync"] is False

    # Explicit null on non-nullable field display_name must fail 422 RFC 7807
    bad_null = await client.patch(
        f"/api/v1/patients/{pid1}",
        headers=headers1,
        json={"display_name": None},
    )
    assert bad_null.status_code == 422
    assert bad_null.headers["content-type"].startswith("application/problem+json")
    assert bad_null.json()["error_code"] == "VALIDATION_ERROR"

    # Naive timestamp rejected
    bad_ts = await client.patch(
        f"/api/v1/patients/{pid1}",
        headers=headers1,
        json={"updated_at_utc": "2026-11-20T08:45:12"},
    )
    assert bad_ts.status_code == 422

    # Stale LWW timestamp rejected 409
    stale_ts = format_utc_z(utc_now() - timedelta(hours=1))
    stale_res = await client.patch(
        f"/api/v1/patients/{pid1}",
        headers=headers1,
        json={"display_name": "Stale", "updated_at_utc": stale_ts},
    )
    assert stale_res.status_code == 409
    assert stale_res.json()["error_code"] == "STALE_WRITE_CONFLICT"


async def test_idor_access_grants_and_uu_pdp_right_to_erasure(
    client: AsyncClient,
    app: Any,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    p_payload = register_payload_factory(role="PATIENT", password="ErasePassword#1")
    p_tokens = (await client.post("/api/v1/auth/register", json=p_payload)).json()
    p_headers = {"Authorization": f"Bearer {p_tokens['access_token']}"}
    pid = UUID(p_tokens["user_id"])

    cg_payload = register_payload_factory(role="CAREGIVER", display_name=None, birth_year=None)
    cg_tokens = (await client.post("/api/v1/auth/register", json=cg_payload)).json()
    cg_headers = {"Authorization": f"Bearer {cg_tokens['access_token']}"}
    cg_id = UUID(cg_tokens["user_id"])

    # Ungranted caregiver gets 403 ACCESS_DENIED
    denied = await client.get(f"/api/v1/patients/{pid}", headers=cg_headers)
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "ACCESS_DENIED"

    # Grant caregiver read/contact access
    async with app.state.session_factory() as session:
        session.add(
            PatientAccessGrantORM(
                grant_id=uuid4(),
                patient_id=pid,
                grantee_user_id=cg_id,
                access_role="CAREGIVER",
                granted_at_utc=utc_now(),
            )
        )
        await session.commit()

    allowed = await client.get(f"/api/v1/patients/{pid}", headers=cg_headers)
    assert allowed.status_code == 200

    # Caregiver still cannot alter UU PDP consent or delete patient data
    consent_denied = await client.patch(
        f"/api/v1/patients/{pid}",
        headers=cg_headers,
        json={"consent_skeleton_sync": False},
    )
    assert consent_denied.status_code == 403

    delete_denied = await client.request(
        "DELETE",
        f"/api/v1/patients/{pid}",
        headers=cg_headers,
        json={"password": cg_payload["password"]},
    )
    assert delete_denied.status_code == 403

    # Add an emergency contact and an idempotency record owned by patient to verify full purge
    await client.patch(
        f"/api/v1/patients/{pid}",
        headers=p_headers,
        json={
            "emergency_contacts": [
                {
                    "name": "Dr. Hendra",
                    "phone_e164": "+6281122334455",
                    "relation": "Dokter",
                    "is_primary": True,
                }
            ]
        },
    )
    async with app.state.session_factory() as session:
        session.add(
            IdempotencyKeyORM(
                actor_user_id=pid,
                method="POST",
                path="/api/v1/sessions",
                idempotency_key=uuid4(),
                request_hash="abc" * 21 + "a",
                state="COMPLETED",
                status_code=201,
                response_body={"session_id": str(uuid4())},
                created_at_utc=utc_now(),
                expires_at_utc=utc_now() + timedelta(days=1),
            )
        )
        await session.commit()

    # Wrong re-auth password must fail 401 without deleting data
    bad_erase = await client.request(
        "DELETE",
        f"/api/v1/patients/{pid}",
        headers=p_headers,
        json={"password": "WrongPassword"},
    )
    assert bad_erase.status_code == 401
    assert bad_erase.json()["error_code"] == "AUTH_REAUTH_FAILED"

    # Correct re-auth permanently deletes patient, user, contacts, audit logs, tokens, & idempotency
    ok_erase = await client.request(
        "DELETE",
        f"/api/v1/patients/{pid}",
        headers=p_headers,
        json={"password": "ErasePassword#1"},
    )
    assert ok_erase.status_code == 204

    async with app.state.session_factory() as session:
        assert await session.get(PatientORM, pid) is None
        assert await session.get(UserORM, pid) is None
        assert (
            await session.execute(
                select(EmergencyContactORM).where(EmergencyContactORM.patient_id == pid)
            )
        ).scalars().all() == []
        assert (
            await session.execute(
                select(ConsentAuditLogORM).where(ConsentAuditLogORM.patient_id == pid)
            )
        ).scalars().all() == []
        assert (
            await session.execute(
                select(RefreshTokenORM).where(RefreshTokenORM.user_id == pid)
            )
        ).scalars().all() == []
        assert (
            await session.execute(
                select(IdempotencyKeyORM).where(IdempotencyKeyORM.actor_user_id == pid)
            )
        ).scalars().all() == []
