import base64
import contextlib
import math
import re
import zlib
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from starlette.websockets import WebSocketDisconnect

from src.domain.constants import MEDICAL_DISCLAIMER_ID
from src.domain.value_objects import format_utc_z, utc_now
from src.infrastructure.config import Settings
from src.infrastructure.persistence.models import Base
from src.infrastructure.security import Argon2PasswordHasher
from src.presentation.api.app import create_app

UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Decode ReportLab ASCII85 + FlateDecode PDF streams to inspect rendered report text."""
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        raw_stream = match.group(1).strip()
        decoded_candidates = [raw_stream]
        if raw_stream.endswith(b"~>"):
            with contextlib.suppress(ValueError):
                decoded_candidates.insert(0, base64.a85decode(raw_stream[:-2]))
        for candidate in decoded_candidates:
            try:
                chunks.append(zlib.decompress(candidate).decode("latin-1", errors="ignore"))
                break
            except zlib.error:
                continue
        else:
            chunks.append(raw_stream.decode("latin-1", errors="ignore"))
    return "\n".join(chunks)


async def test_session_clinical_report_json_and_pdf_export(
    client: AsyncClient,
    register_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    reg = register_payload_factory(
        role="PATIENT",
        display_name="Ibu Ratna",
        consent_skeleton_sync=True,
    )
    tokens = (await client.post("/api/v1/auth/register", json=reg)).json()
    pid = tokens["user_id"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    other = (
        await client.post("/api/v1/auth/register", json=register_payload_factory())
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    sid = str(uuid4())
    start_ts = utc_now() - timedelta(minutes=5)
    await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "session_id": sid,
            "patient_id": pid,
            "protocol": "TURNING_360_2MIN",
            "inference_mode": "POST_SESSION_EXACT",
            "med_state": "OFF",
            "last_medication_log_id": None,
            "target_fps": 15,
            "model_bundle_version": "b15hz-v1.0.0",
            "started_at_utc": format_utc_z(start_ts),
            "safety_checklist_confirmed": True,
        },
    )

    await client.post(
        f"/api/v1/sessions/{sid}/results",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "classifier_used": "LIGHTGBM_FFT",
            "threshold_used": 0.26,
            "ended_at_utc": format_utc_z(start_ts + timedelta(minutes=2)),
            "duration_sec": 120.0,
            "valid_lb6_ratio": 0.95,
            "fog_percentage": 15.0,
            "episode_count": 1,
            "total_fog_duration_sec": 18.0,
            "median_episode_duration_sec": 18.0,
            "episodes": [
                {
                    "episode_index": 1,
                    "start_sec": 30.0,
                    "end_sec": 48.0,
                    "duration_sec": 18.0,
                    "peak_calibrated_score": 82.0,
                    "mean_freeze_index": 2.45,
                }
            ],
            "windows": [
                {
                    "window_idx": 0,
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "raw_prob": 0.42,
                    "calibrated_score": 60.8,
                    "pred_raw": 1,
                    "pred_postprocessed": 1,
                    "freeze_index_ankle": 2.45,
                    "bilateral_asym_ankle": 0.28,
                    "low_quality_flag": False,
                }
            ],
        },
    )

    # Record 1 cancelled Fall Guard near-miss alert
    await client.post(
        "/api/v1/alerts/emergency",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "alert_id": str(uuid4()),
            "patient_id": pid,
            "session_id": sid,
            "trigger_type": "PROLONGED_FREEZE_15S",
            "triggered_at_utc": format_utc_z(start_ts + timedelta(minutes=1)),
            "cancelled_by_user": True,
        },
    )

    # IDOR check
    forbidden = await client.get(f"/api/v1/sessions/{sid}/report", headers=other_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == "ACCESS_DENIED"

    # JSON report
    json_resp = await client.get(
        f"/api/v1/sessions/{sid}/report",
        headers=headers,
        params={"format": "json"},
    )
    assert json_resp.status_code == 200
    report = json_resp.json()
    assert report["patient_display_name"] == "Ibu Ratna"
    assert report["mean_freeze_index"] == 2.45
    assert report["mean_bilateral_asymmetry"] == 0.28
    assert report["asymmetry_level_id"] == "Tinggi"
    assert report["fall_guard_false_alarms"] == 1
    assert report["video_securely_deleted"] is True
    assert report["medical_disclaimer"] == MEDICAL_DISCLAIMER_ID
    assert UTC_Z_RE.match(report["generated_at_utc"])
    assert len(report["episodes"]) == 1
    assert len(report["windows"]) == 1

    # PDF report
    pdf_resp = await client.get(
        f"/api/v1/sessions/{sid}/report",
        headers=headers,
        params={"format": "pdf"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert f"parkinstep-report-{sid}.pdf" in pdf_resp.headers["content-disposition"]
    assert pdf_resp.content.startswith(b"%PDF-1.")
    extracted = _extract_pdf_text(pdf_resp.content)
    assert "Ibu Ratna" in extracted
    assert "BUKAN merupakan diagnosis medis resmi" in extracted


def test_websocket_cloud_fallback_auth_consent_and_streaming(tmp_path: Path) -> None:
    import asyncio

    db_path = tmp_path / "ws_test.db"
    ws_settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key="ws-test-secret-key-at-least-32-chars-long!",
        log_level="WARNING",
    )
    app = create_app(
        ws_settings,
        password_hasher=Argon2PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1),
    )

    async def _init_db() -> None:
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_db())

    with TestClient(app) as sync_client:
        reg_resp = sync_client.post(
            "/api/v1/auth/register",
            json={
                "identifier": "ws.patient@parkinstep.id",
                "password": "WsPassword#123",
                "role": "PATIENT",
                "device_id": "ws-dev-1",
                "consent_local": True,
                "consent_skeleton_sync": True,
            },
        )
        assert reg_resp.status_code == 201
        tokens = reg_resp.json()
        pid = tokens["user_id"]
        ws_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        sid = str(uuid4())
        sess_resp = sync_client.post(
            "/api/v1/sessions",
            headers={**ws_headers, "Idempotency-Key": str(uuid4())},
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
        assert sess_resp.status_code == 201

        # Missing auth -> rejected with 4401
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_client.websocket_connect(f"/ws/v1/stream/keypoints/{sid}"),
        ):
            pass
        assert exc_info.value.code == 4401

        # Unknown session -> rejected with 4404
        with (
            pytest.raises(WebSocketDisconnect) as missing_exc,
            sync_client.websocket_connect(
                f"/ws/v1/stream/keypoints/{uuid4()}",
                headers=ws_headers,
            ),
        ):
            pass
        assert missing_exc.value.code == 4404

        # Valid connection: malformed frame emits ERROR; 63 freeze frames emit 3 predictions
        with sync_client.websocket_connect(
            f"/ws/v1/stream/keypoints/{sid}",
            headers=ws_headers,
        ) as ws:
            ws.send_json({"type": "LB6_FRAME", "seq": 0, "t_ms": 0, "lb6_xyc": [[1.0, 2.0, 0.9]]})
            err_msg = ws.receive_json()
            assert err_msg["type"] == "ERROR"
            assert err_msg["error_code"] == "INVALID_FRAME"

            predictions: list[dict[str, Any]] = []
            for seq in range(63):
                sec = seq / 15.0
                osc_l = 16.0 * math.sin(2.0 * math.pi * 5.5 * sec)
                osc_r = 16.0 * math.sin(2.0 * math.pi * 5.5 * sec + math.pi)
                ws.send_json(
                    {
                        "type": "LB6_FRAME",
                        "seq": seq,
                        "t_ms": int(sec * 1000),
                        "lb6_xyc": [
                            [500.0, 300.0, 0.95],
                            [560.0, 300.0, 0.95],
                            [500.0 + 0.3 * osc_l, 420.0, 0.92],
                            [560.0 + 0.3 * osc_r, 420.0, 0.92],
                            [500.0 + osc_l, 540.0, 0.90],
                            [560.0 + osc_r, 540.0, 0.90],
                        ],
                    }
                )
                if seq in (32, 47, 62):
                    predictions.append(ws.receive_json())

            assert len(predictions) == 3
            assert [p["window_idx"] for p in predictions] == [0, 1, 2]
            assert all(p["type"] == "WINDOW_PREDICTION" for p in predictions)
            assert predictions[0]["alert_tier"] == "EARLY_WARNING"
            assert predictions[1]["alert_tier"] == "FOG_CONFIRMED"
            assert predictions[2]["alert_tier"] == "FOG_CONFIRMED"

        # Revoke Consent A -> WebSocket rejected with 4403
        sync_client.patch(
            f"/api/v1/patients/{pid}",
            headers=ws_headers,
            json={"consent_skeleton_sync": False},
        )
        with (
            pytest.raises(WebSocketDisconnect) as consent_exc,
            sync_client.websocket_connect(
                f"/ws/v1/stream/keypoints/{sid}",
                headers=ws_headers,
            ),
        ):
            pass
        assert consent_exc.value.code == 4403
