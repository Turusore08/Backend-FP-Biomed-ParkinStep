import json
from pathlib import Path

from fastapi import FastAPI
from httpx import AsyncClient

from scripts.export_openapi import build_openapi_schema


async def test_openapi_310_contract_and_exported_snapshot_parity(client: AsyncClient) -> None:
    live = (await client.get("/openapi.json")).json()
    assert live["openapi"] == "3.1.0"

    expected_paths = {
        "/healthz": {"get"},
        "/readyz": {"get"},
        "/api/v1/auth/register": {"post"},
        "/api/v1/auth/login": {"post"},
        "/api/v1/auth/refresh": {"post"},
        "/api/v1/auth/logout": {"post"},
        "/api/v1/patients/{patient_id}": {"get", "patch", "delete"},
        "/api/v1/patients/{patient_id}/medications": {"post", "get"},
        "/api/v1/sessions": {"post"},
        "/api/v1/sessions/{session_id}/skeleton-frames": {"post"},
        "/api/v1/sessions/{session_id}/results": {"post"},
        "/api/v1/sessions/{session_id}/analyze-video": {"post"},
        "/api/v1/sessions/{session_id}/report": {"get"},
        "/api/v1/patients/{patient_id}/analytics/trends": {"get"},
        "/api/v1/models/manifest": {"get"},
        "/api/v1/alerts/emergency": {"post"},
    }

    for path, methods in expected_paths.items():
        assert path in live["paths"], f"Missing OpenAPI path: {path}"
        assert methods <= set(live["paths"][path].keys()), f"Missing methods on {path}"

    # Verify required Idempotency-Key header parameter on all 5 mutating POST endpoints
    idempotent_paths = (
        "/api/v1/patients/{patient_id}/medications",
        "/api/v1/sessions",
        "/api/v1/sessions/{session_id}/skeleton-frames",
        "/api/v1/sessions/{session_id}/results",
        "/api/v1/alerts/emergency",
    )
    for path in idempotent_paths:
        params = live["paths"][path]["post"].get("parameters", [])
        idem_params = [
            p for p in params if p.get("in") == "header" and p.get("name") == "Idempotency-Key"
        ]
        assert idem_params and idem_params[0].get("required") is True, path

    # Verify StrEnums are serialized as uppercase string enums
    schemas = live["components"]["schemas"]
    assert schemas["UserRole"]["enum"] == ["PATIENT", "CAREGIVER", "CLINICIAN"]
    assert schemas["MedicationState"]["enum"] == ["ON", "OFF", "UNKNOWN"]
    assert schemas["InferenceMode"]["enum"] == [
        "LIVE_CAUSAL",
        "POST_SESSION_EXACT",
        "CLOUD_FALLBACK",
    ]
    assert schemas["SessionProtocol"]["enum"] == ["TURNING_360_2MIN", "FREE_WALK_MONITORING"]
    assert schemas["ClassifierName"]["enum"] == ["LIGHTGBM_FFT", "LIGHT_STGCN", "PURE_BIMAMBA"]
    assert schemas["EmergencyTrigger"]["enum"] == [
        "PROLONGED_FREEZE_15S",
        "SUDDEN_HIP_DROP_IMMOBILITY",
    ]

    # Verify committed contracts/openapi.json matches the app schema (ignoring test-only route)
    repo_root = Path(__file__).resolve().parents[2]
    snapshot_path = repo_root / "contracts" / "openapi.json"
    assert snapshot_path.is_file(), "contracts/openapi.json must be exported"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    exported_live = build_openapi_schema()
    assert snapshot == exported_live
    assert isinstance(client, AsyncClient)
    assert isinstance(FastAPI, type)
