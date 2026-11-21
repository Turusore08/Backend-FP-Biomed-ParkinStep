import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from src.domain.value_objects import format_utc_z, utc_now

UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


async def test_medication_logs_idempotency_pagination_and_consent_gate(
    client: AsyncClient,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    reg = register_payload_factory(role="PATIENT", consent_skeleton_sync=True)
    tokens = (await client.post("/api/v1/auth/register", json=reg)).json()
    pid = tokens["user_id"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    other = (
        await client.post(
            "/api/v1/auth/register",
            json=register_payload_factory(role="PATIENT"),
        )
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    # Missing Idempotency-Key -> 400 RFC 7807
    t1 = utc_now() - timedelta(hours=2)
    log1_id = str(uuid4())
    log1_payload = {
        "log_id": log1_id,
        "drug_name": "Madopar 125",
        "dosage_mg": 125.0,
        "taken_at_utc": format_utc_z(t1),
        "med_state": "ON",
        "notes": None,
    }
    no_key = await client.post(
        f"/api/v1/patients/{pid}/medications",
        headers=headers,
        json=log1_payload,
    )
    assert no_key.status_code == 400
    assert no_key.json()["error_code"] == "IDEMPOTENCY_KEY_REQUIRED"

    # Create log 1 with Idempotency-Key
    idem_1 = str(uuid4())
    created = await client.post(
        f"/api/v1/patients/{pid}/medications",
        headers={**headers, "Idempotency-Key": idem_1},
        json=log1_payload,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["log_id"] == log1_id
    assert "notes" in body and body["notes"] is None
    assert UTC_Z_RE.match(body["taken_at_utc"])
    assert UTC_Z_RE.match(body["synced_at_utc"])

    # Replay returns cached 201 without duplicate error
    replay = await client.post(
        f"/api/v1/patients/{pid}/medications",
        headers={**headers, "Idempotency-Key": idem_1},
        json=log1_payload,
    )
    assert replay.status_code == 201
    assert replay.headers.get("X-Idempotency-Replayed") == "true"
    assert replay.json() == body

    # Mismatch payload with same Idempotency-Key -> 409
    mismatch = await client.post(
        f"/api/v1/patients/{pid}/medications",
        headers={**headers, "Idempotency-Key": idem_1},
        json={**log1_payload, "dosage_mg": 250.0},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error_code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"

    # IDOR blocked
    idor = await client.get(f"/api/v1/patients/{pid}/medications", headers=other_headers)
    assert idor.status_code == 403

    # Create log 2 and verify paginated list + date filtering
    t2 = utc_now() - timedelta(minutes=30)
    log2_payload = {
        "log_id": str(uuid4()),
        "drug_name": "Sinemet 100",
        "dosage_mg": 100.0,
        "taken_at_utc": format_utc_z(t2),
        "med_state": "OFF",
        "notes": "Sebelum sarapan",
    }
    created_2 = await client.post(
        f"/api/v1/patients/{pid}/medications",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=log2_payload,
    )
    assert created_2.status_code == 201

    page_1 = await client.get(
        f"/api/v1/patients/{pid}/medications",
        headers=headers,
        params={"limit": 1, "offset": 0},
    )
    assert page_1.status_code == 200
    p1_json = page_1.json()
    assert p1_json["total"] == 2
    assert len(p1_json["items"]) == 1
    assert p1_json["items"][0]["drug_name"] == "Sinemet 100"

    filtered = await client.get(
        f"/api/v1/patients/{pid}/medications",
        headers=headers,
        params={"from_utc": format_utc_z(t2 - timedelta(minutes=5))},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1

    # Revoke sync consent -> medication upload blocked 403 CONSENT_SYNC_REQUIRED
    revoke = await client.patch(
        f"/api/v1/patients/{pid}",
        headers=headers,
        json={"consent_skeleton_sync": False},
    )
    assert revoke.status_code == 200

    blocked = await client.post(
        f"/api/v1/patients/{pid}/medications",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={**log2_payload, "log_id": str(uuid4())},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error_code"] == "CONSENT_SYNC_REQUIRED"
