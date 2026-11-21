import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select

from src.domain.value_objects import format_utc_z, utc_now
from src.infrastructure.persistence.codecs.skeleton_codec import ZlibSkeletonCodec
from src.infrastructure.persistence.models import (
    ClinicalSessionORM,
    FogEpisodeORM,
    SkeletonChunkORM,
    WindowPredictionORM,
)

UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


async def test_offline_first_session_sync_pipeline_and_analytics_trends(
    client: AsyncClient,
    app: Any,
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

    # Register second patient to test cross-patient medication reference protection
    other_tokens = (
        await client.post(
            "/api/v1/auth/register",
            json=register_payload_factory(role="PATIENT", consent_skeleton_sync=True),
        )
    ).json()
    other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}
    other_med_id = str(uuid4())
    await client.post(
        f"/api/v1/patients/{other_tokens['user_id']}/medications",
        headers={**other_headers, "Idempotency-Key": str(uuid4())},
        json={
            "log_id": other_med_id,
            "drug_name": "Levodopa",
            "dosage_mg": 100.0,
            "taken_at_utc": format_utc_z(utc_now() - timedelta(hours=1)),
            "med_state": "ON",
            "notes": None,
        },
    )

    bad_med_ref = await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "session_id": str(uuid4()),
            "patient_id": pid,
            "protocol": "TURNING_360_2MIN",
            "inference_mode": "LIVE_CAUSAL",
            "med_state": "ON",
            "last_medication_log_id": other_med_id,
            "target_fps": 15,
            "model_bundle_version": "b15hz-v1.0.0",
            "started_at_utc": format_utc_z(utc_now() - timedelta(minutes=20)),
            "safety_checklist_confirmed": True,
        },
    )
    assert bad_med_ref.status_code == 404
    assert bad_med_ref.json()["error_code"] == "MEDICATION_LOG_NOT_FOUND"

    # 1. Create ON-medication session (idempotent)
    s_on_id = str(uuid4())
    s_on_start = utc_now() - timedelta(minutes=30)
    s_on_payload = {
        "session_id": s_on_id,
        "patient_id": pid,
        "protocol": "TURNING_360_2MIN",
        "inference_mode": "POST_SESSION_EXACT",
        "med_state": "ON",
        "last_medication_log_id": None,
        "target_fps": 15,
        "model_bundle_version": "b15hz-v1.0.0",
        "started_at_utc": format_utc_z(s_on_start),
        "safety_checklist_confirmed": True,
    }
    idem_s = str(uuid4())
    s_resp = await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": idem_s},
        json=s_on_payload,
    )
    assert s_resp.status_code == 201
    s_json = s_resp.json()
    assert "last_medication_log_id" in s_json and s_json["last_medication_log_id"] is None
    assert UTC_Z_RE.match(s_json["created_at_utc"])

    s_replay = await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": idem_s},
        json=s_on_payload,
    )
    assert s_replay.status_code == 201
    assert s_replay.headers.get("X-Idempotency-Replayed") == "true"

    # 2. Upload LB6 skeleton batch [T][6][3]
    lb6_frames = [
        [[512.0 + t, 340.0 + j, 0.9 - j * 0.02] for j in range(6)]
        for t in range(4)
    ]
    skel_payload = {
        "chunk_index": 0,
        "sampling_hz": 15.0,
        "frame_timestamps_ms": [0, 67, 133, 200],
        "lb6_xyc": lb6_frames,
    }
    idem_skel = str(uuid4())
    skel_resp = await client.post(
        f"/api/v1/sessions/{s_on_id}/skeleton-frames",
        headers={**headers, "Idempotency-Key": idem_skel},
        json=skel_payload,
    )
    assert skel_resp.status_code == 202
    assert skel_resp.json()["frame_count"] == 4

    # Verify ZLIB binary storage parity in DB
    async with app.state.session_factory() as session:
        chunk_row = (
            await session.execute(
                select(SkeletonChunkORM).where(SkeletonChunkORM.session_id == UUID(s_on_id))
            )
        ).scalar_one()
        assert chunk_row.compression == "ZLIB"
        ts_out, frames_out = ZlibSkeletonCodec().unpack(chunk_row.payload_blob)
        assert ts_out == [0, 67, 133, 200]
        assert len(frames_out) == 4

    # Invalid skeleton shape [5][3] rejected 422
    bad_skel = await client.post(
        f"/api/v1/sessions/{s_on_id}/skeleton-frames",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "chunk_index": 1,
            "sampling_hz": 15.0,
            "frame_timestamps_ms": [267],
            "lb6_xyc": [[[1.0, 2.0, 0.9] for _ in range(5)]],
        },
    )
    assert bad_skel.status_code == 422

    # 3. Upload session results
    results_payload = {
        "classifier_used": "LIGHTGBM_FFT",
        "threshold_used": 0.26,
        "ended_at_utc": format_utc_z(s_on_start + timedelta(minutes=2)),
        "duration_sec": 120.0,
        "valid_lb6_ratio": 0.96,
        "fog_percentage": 8.0,
        "episode_count": 1,
        "total_fog_duration_sec": 9.6,
        "median_episode_duration_sec": 9.6,
        "episodes": [
            {
                "episode_index": 1,
                "start_sec": 20.0,
                "end_sec": 29.6,
                "duration_sec": 9.6,
                "peak_calibrated_score": 78.4,
                "mean_freeze_index": 2.1,
            }
        ],
        "windows": [
            {
                "window_idx": 0,
                "start_sec": 0.0,
                "end_sec": 2.0,
                "raw_prob": 0.12,
                "calibrated_score": 23.08,
                "pred_raw": 0,
                "pred_postprocessed": 0,
                "freeze_index_ankle": 0.5,
                "bilateral_asym_ankle": 0.04,
                "low_quality_flag": False,
            },
            {
                "window_idx": 1,
                "start_sec": 1.0,
                "end_sec": 3.0,
                "raw_prob": 0.34,
                "calibrated_score": 55.4,
                "pred_raw": 1,
                "pred_postprocessed": 1,
                "freeze_index_ankle": 2.41,
                "bilateral_asym_ankle": 0.29,
                "low_quality_flag": False,
            },
        ],
    }
    idem_res = str(uuid4())
    res_resp = await client.post(
        f"/api/v1/sessions/{s_on_id}/results",
        headers={**headers, "Idempotency-Key": idem_res},
        json=results_payload,
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["episode_count"] == 1
    assert res_resp.json()["window_count"] == 2

    # Replay returns cached 200; new key on already finalized session returns 409
    res_replay = await client.post(
        f"/api/v1/sessions/{s_on_id}/results",
        headers={**headers, "Idempotency-Key": idem_res},
        json=results_payload,
    )
    assert res_replay.status_code == 200
    assert res_replay.headers.get("X-Idempotency-Replayed") == "true"

    dup_finalize = await client.post(
        f"/api/v1/sessions/{s_on_id}/results",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=results_payload,
    )
    assert dup_finalize.status_code == 409
    assert dup_finalize.json()["error_code"] == "SESSION_RESULTS_ALREADY_UPLOADED"

    async with app.state.session_factory() as session:
        sess_row = await session.get(ClinicalSessionORM, UUID(s_on_id))
        assert sess_row is not None and sess_row.classifier_used == "LIGHTGBM_FFT"
        eps = (
            await session.execute(
                select(FogEpisodeORM).where(FogEpisodeORM.session_id == UUID(s_on_id))
            )
        ).scalars().all()
        wins = (
            await session.execute(
                select(WindowPredictionORM).where(WindowPredictionORM.session_id == UUID(s_on_id))
            )
        ).scalars().all()
        assert len(eps) == 1 and len(wins) == 2

    # Check trends when only ON session exists -> off_med_avg_fog_pct is explicit null
    trends_on_only = (
        await client.get(f"/api/v1/patients/{pid}/analytics/trends", headers=headers)
    ).json()
    assert trends_on_only["total_sessions"] == 1
    assert trends_on_only["on_med_avg_fog_pct"] == 8.0
    assert trends_on_only["off_med_avg_fog_pct"] is None

    # Create and finalize an OFF-medication session + UNKNOWN session
    for med_state, fog_pct, offset_min in (("OFF", 22.0, 10), ("UNKNOWN", 14.0, 5)):
        sid = str(uuid4())
        st = utc_now() - timedelta(minutes=offset_min)
        await client.post(
            "/api/v1/sessions",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                **s_on_payload,
                "session_id": sid,
                "med_state": med_state,
                "started_at_utc": format_utc_z(st),
            },
        )
        await client.post(
            f"/api/v1/sessions/{sid}/results",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                **results_payload,
                "ended_at_utc": format_utc_z(st + timedelta(minutes=2)),
                "fog_percentage": fog_pct,
                "episode_count": 0,
                "episodes": [],
            },
        )

    trends_all = (
        await client.get(f"/api/v1/patients/{pid}/analytics/trends", headers=headers)
    ).json()
    assert trends_all["total_sessions"] == 3
    assert trends_all["on_med_avg_fog_pct"] == 8.0
    assert trends_all["off_med_avg_fog_pct"] == 22.0
    assert len(trends_all["points"]) == 3

    # Revoke sync consent -> session upload blocked
    await client.patch(
        f"/api/v1/patients/{pid}",
        headers=headers,
        json={"consent_skeleton_sync": False},
    )
    blocked_session = await client.post(
        "/api/v1/sessions",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={**s_on_payload, "session_id": str(uuid4())},
    )
    assert blocked_session.status_code == 403
    assert blocked_session.json()["error_code"] == "CONSENT_SYNC_REQUIRED"
