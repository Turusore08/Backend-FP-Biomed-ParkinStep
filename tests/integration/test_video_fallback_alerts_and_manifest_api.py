import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from src.domain.constants import SCALER_MEAN_B15HZ, SCALER_STD_B15HZ
from src.domain.entities import ModelArtifactSpec, ModelBundleManifest
from src.domain.enums import ModelFormat
from src.domain.value_objects import format_utc_z, utc_now
from src.infrastructure.persistence.repositories import SqlAlchemyUnitOfWork

UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


async def test_cloud_video_fallback_consent_and_zero_retention(
    client: AsyncClient,
    test_settings: Any,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    tokens = (
        await client.post(
            "/api/v1/auth/register",
            json=register_payload_factory(
                role="PATIENT",
                consent_skeleton_sync=True,
                consent_cloud_video=False,
            ),
        )
    ).json()
    pid = tokens["user_id"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    sid = str(uuid4())
    await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "session_id": sid,
            "patient_id": pid,
            "protocol": "TURNING_360_2MIN",
            "inference_mode": "CLOUD_FALLBACK",
            "med_state": "OFF",
            "last_medication_log_id": None,
            "target_fps": 15,
            "model_bundle_version": "b15hz-v1.0.0",
            "started_at_utc": format_utc_z(utc_now()),
            "safety_checklist_confirmed": True,
        },
    )

    # Consent B is OFF -> 403 CONSENT_CLOUD_VIDEO_REQUIRED
    denied = await client.post(
        f"/api/v1/sessions/{sid}/analyze-video",
        headers=headers,
        files={"file": ("clip.mp4", b"ftypmp42" + b"\x00" * 512, "video/mp4")},
    )
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "CONSENT_CLOUD_VIDEO_REQUIRED"

    # Enable Consent B
    await client.patch(
        f"/api/v1/patients/{pid}",
        headers=headers,
        json={"consent_cloud_video": True},
    )

    # Unsupported media type -> 415
    bad_mime = await client.post(
        f"/api/v1/sessions/{sid}/analyze-video",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_mime.status_code == 415
    assert bad_mime.json()["error_code"] == "UNSUPPORTED_MEDIA_TYPE"

    # Valid MP4 upload -> 200 + guaranteed secure delete (temp dir empty)
    ok = await client.post(
        f"/api/v1/sessions/{sid}/analyze-video",
        headers=headers,
        files={"file": ("clip.mp4", b"ftypmp42" + b"\x01\x02" * 1024, "video/mp4")},
    )
    assert ok.status_code == 200
    ok_json = ok.json()
    assert ok_json["auto_delete_after_inference"] is True
    assert ok_json["video_securely_deleted"] is True
    assert ok_json["frames_analyzed"] >= 1

    video_tmp_dir = Path(test_settings.video_temp_dir)
    assert list(video_tmp_dir.iterdir()) == []

    # Oversize upload (> 64 KiB in test settings) -> 413 & zero leftover files
    oversize = await client.post(
        f"/api/v1/sessions/{sid}/analyze-video",
        headers=headers,
        files={"file": ("huge.mp4", b"\x55" * (70 * 1024), "video/mp4")},
    )
    assert oversize.status_code == 413
    assert oversize.json()["error_code"] == "PAYLOAD_TOO_LARGE"
    assert list(video_tmp_dir.iterdir()) == []


async def test_emergency_alerts_near_miss_dispatch_and_idempotency(
    client: AsyncClient,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    tokens = (
        await client.post(
            "/api/v1/auth/register",
            json=register_payload_factory(role="PATIENT", consent_skeleton_sync=True),
        )
    ).json()
    pid = tokens["user_id"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.patch(
        f"/api/v1/patients/{pid}",
        headers=headers,
        json={
            "emergency_contacts": [
                {
                    "name": "Anak Pertama",
                    "phone_e164": "+6281234567890",
                    "relation": "Child",
                    "is_primary": True,
                }
            ]
        },
    )

    sid = str(uuid4())
    await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "session_id": sid,
            "patient_id": pid,
            "protocol": "FREE_WALK_MONITORING",
            "inference_mode": "LIVE_CAUSAL",
            "med_state": "ON",
            "last_medication_log_id": None,
            "target_fps": 15,
            "model_bundle_version": "b15hz-v1.0.0",
            "started_at_utc": format_utc_z(utc_now()),
            "safety_checklist_confirmed": True,
        },
    )

    # Cancelled near-miss -> 202 without dispatch
    near_miss = await client.post(
        "/api/v1/alerts/emergency",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "alert_id": str(uuid4()),
            "patient_id": pid,
            "session_id": sid,
            "trigger_type": "PROLONGED_FREEZE_15S",
            "triggered_at_utc": format_utc_z(utc_now()),
            "cancelled_by_user": True,
        },
    )
    assert near_miss.status_code == 202
    nm_json = near_miss.json()
    assert nm_json["dispatched_at_utc"] is None
    assert nm_json["notified_contacts_count"] == 0

    # Active fall escalation -> 202 dispatched + idempotent replay
    alert_payload = {
        "alert_id": str(uuid4()),
        "patient_id": pid,
        "session_id": sid,
        "trigger_type": "SUDDEN_HIP_DROP_IMMOBILITY",
        "triggered_at_utc": format_utc_z(utc_now()),
        "cancelled_by_user": False,
    }
    idem_alert = str(uuid4())
    dispatched = await client.post(
        "/api/v1/alerts/emergency",
        headers={**headers, "Idempotency-Key": idem_alert},
        json=alert_payload,
    )
    assert dispatched.status_code == 202
    d_json = dispatched.json()
    assert d_json["notified_contacts_count"] == 1
    assert UTC_Z_RE.match(d_json["dispatched_at_utc"])

    replay = await client.post(
        "/api/v1/alerts/emergency",
        headers={**headers, "Idempotency-Key": idem_alert},
        json=alert_payload,
    )
    assert replay.status_code == 202
    assert replay.headers.get("X-Idempotency-Replayed") == "true"
    assert replay.json() == d_json


async def test_ota_model_manifest_auth_parity_and_db_override(
    client: AsyncClient,
    app: Any,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    # Unauthenticated -> 401
    unauth = await client.get("/api/v1/models/manifest")
    assert unauth.status_code == 401
    assert unauth.json()["error_code"] == "AUTH_TOKEN_INVALID"

    # Wrong X-App-Key -> 401
    bad_key = await client.get(
        "/api/v1/models/manifest",
        headers={"X-App-Key": "wrong-key"},
    )
    assert bad_key.status_code == 401

    # Valid X-App-Key -> 200 canonical B_15hz manifest
    app_key_resp = await client.get(
        "/api/v1/models/manifest",
        headers={"X-App-Key": "test-ota-app-key-secret"},
    )
    assert app_key_resp.status_code == 200
    manifest = app_key_resp.json()
    assert manifest["target_fps"] == 15
    assert manifest["window_sec"] == 2.0
    assert manifest["stride_sec"] == 1.0
    assert manifest["min_run_windows"] == 2
    assert manifest["primary_classifier"]["name"] == "lgbm_b15hz"
    assert manifest["primary_classifier"]["requires_scaled_input"] is False
    assert manifest["primary_classifier"]["threshold_val"] == 0.26
    assert manifest["secondary_classifier"]["requires_scaled_input"] is True
    assert manifest["secondary_classifier"]["threshold_val"] == 0.39
    assert len(manifest["scaler_mean_b15hz"]) == 9
    assert len(manifest["scaler_std_b15hz"]) == 9
    assert manifest["scaler_mean_b15hz"] == list(SCALER_MEAN_B15HZ)
    assert manifest["scaler_std_b15hz"] == list(SCALER_STD_B15HZ)
    assert re.match(r"^[a-f0-9]{64}$", manifest["primary_classifier"]["sha256"])

    # Valid Bearer JWT also succeeds and reflects DB-seeded active bundle override
    tokens = (
        await client.post("/api/v1/auth/register", json=register_payload_factory())
    ).json()
    custom_bundle = ModelBundleManifest(
        bundle_version="b15hz-v2.0.0",
        target_fps=15,
        window_sec=2.0,
        stride_sec=1.0,
        min_run_windows=2,
        pose_estimator=ModelArtifactSpec(
            name="yolo26n-pose",
            format=ModelFormat.ONNX,
            download_url="https://models.parkinstep.example.org/v2/yolo26n-pose.onnx",
            sha256="a" * 64,
            size_bytes=8_000_000,
            requires_scaled_input=False,
            threshold_val=0.25,
        ),
        primary_classifier=ModelArtifactSpec(
            name="lgbm_b15hz",
            format=ModelFormat.ONNX,
            download_url="https://models.parkinstep.example.org/v2/lgbm_b15hz.onnx",
            sha256="b" * 64,
            size_bytes=200_000,
            requires_scaled_input=False,
            threshold_val=0.26,
        ),
        secondary_classifier=None,
        scaler_mean_b15hz=SCALER_MEAN_B15HZ,
        scaler_std_b15hz=SCALER_STD_B15HZ,
    )
    async with SqlAlchemyUnitOfWork(app.state.session_factory) as uow:
        await uow.model_bundles.upsert(
            custom_bundle,
            is_active=True,
            published_at_utc=utc_now(),
        )
        await uow.commit()

    jwt_resp = await client.get(
        "/api/v1/models/manifest",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert jwt_resp.status_code == 200
    assert jwt_resp.json()["bundle_version"] == "b15hz-v2.0.0"
    assert jwt_resp.json()["secondary_classifier"] is None
