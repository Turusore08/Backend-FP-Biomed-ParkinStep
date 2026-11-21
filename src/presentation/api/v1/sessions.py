from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status

from src.application.dtos import (
    FogEpisodeInputDTO,
    SessionCreateDTO,
    SessionResultUploadDTO,
    SkeletonBatchUploadDTO,
    WindowPredictionInputDTO,
)
from src.application.use_cases.sessions import (
    AnalyzeVideoFallbackUseCase,
    CreateSessionUseCase,
    GetSessionReportUseCase,
    UploadSessionResultsUseCase,
    UploadSkeletonBatchUseCase,
)
from src.presentation.dependencies import (
    CurrentActorDep,
    get_analyze_video_use_case,
    get_create_session_use_case,
    get_session_report_use_case,
    get_upload_session_results_use_case,
    get_upload_skeleton_use_case,
)
from src.presentation.schemas import (
    ProblemDetailsSchema,
    SessionClinicalReportResponse,
    SessionCreateRequest,
    SessionResultSyncResponse,
    SessionResultUpload,
    SessionSummary,
    SkeletonBatchAckResponse,
    SkeletonBatchUpload,
    VideoFallbackAnalysisResponse,
)

router = APIRouter(prefix="/sessions", tags=["Clinical Sessions"])


@router.post(
    "",
    response_model=SessionSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Registrasi sesi tes 360° Turning-in-Place (offline-first compatible)",
    responses={
        400: {"model": ProblemDetailsSchema},
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def create_session(
    payload: SessionCreateRequest,
    _idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    actor: CurrentActorDep,
    use_case: Annotated[CreateSessionUseCase, Depends(get_create_session_use_case)],
) -> SessionSummary:
    dto = await use_case.execute(
        actor,
        SessionCreateDTO(
            session_id=payload.session_id,
            patient_id=payload.patient_id,
            protocol=payload.protocol,
            inference_mode=payload.inference_mode,
            med_state=payload.med_state,
            last_medication_log_id=payload.last_medication_log_id,
            target_fps=payload.target_fps,
            model_bundle_version=payload.model_bundle_version,
            started_at_utc=payload.started_at_utc,
            safety_checklist_confirmed=payload.safety_checklist_confirmed,
        ),
    )
    return SessionSummary.from_dto(dto)


@router.post(
    "/{session_id}/skeleton-frames",
    response_model=SkeletonBatchAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Unggah batch keypoint LB6 anonim [T][6][3] (tanpa video mentah)",
    responses={
        400: {"model": ProblemDetailsSchema},
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def upload_skeleton_frames(
    session_id: UUID,
    payload: SkeletonBatchUpload,
    _idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    actor: CurrentActorDep,
    use_case: Annotated[UploadSkeletonBatchUseCase, Depends(get_upload_skeleton_use_case)],
) -> SkeletonBatchAckResponse:
    dto = await use_case.execute(
        actor,
        SkeletonBatchUploadDTO(
            session_id=session_id,
            chunk_index=payload.chunk_index,
            sampling_hz=payload.sampling_hz,
            frame_timestamps_ms=payload.frame_timestamps_ms,
            lb6_xyc=payload.lb6_xyc,
        ),
    )
    return SkeletonBatchAckResponse.from_dto(dto)


@router.post(
    "/{session_id}/results",
    response_model=SessionResultSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Unggah ringkasan episode FoG & probabilitas window hasil Edge-AI",
    responses={
        400: {"model": ProblemDetailsSchema},
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def upload_session_results(
    session_id: UUID,
    payload: SessionResultUpload,
    _idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    actor: CurrentActorDep,
    use_case: Annotated[UploadSessionResultsUseCase, Depends(get_upload_session_results_use_case)],
) -> SessionResultSyncResponse:
    dto = await use_case.execute(
        actor,
        SessionResultUploadDTO(
            session_id=session_id,
            classifier_used=payload.classifier_used,
            threshold_used=payload.threshold_used,
            ended_at_utc=payload.ended_at_utc,
            duration_sec=payload.duration_sec,
            valid_lb6_ratio=payload.valid_lb6_ratio,
            fog_percentage=payload.fog_percentage,
            episode_count=payload.episode_count,
            total_fog_duration_sec=payload.total_fog_duration_sec,
            median_episode_duration_sec=payload.median_episode_duration_sec,
            episodes=[
                FogEpisodeInputDTO(
                    episode_index=ep.episode_index,
                    start_sec=ep.start_sec,
                    end_sec=ep.end_sec,
                    duration_sec=ep.duration_sec,
                    peak_calibrated_score=ep.peak_calibrated_score,
                    mean_freeze_index=ep.mean_freeze_index,
                )
                for ep in payload.episodes
            ],
            windows=[
                WindowPredictionInputDTO(
                    window_idx=win.window_idx,
                    start_sec=win.start_sec,
                    end_sec=win.end_sec,
                    raw_prob=win.raw_prob,
                    calibrated_score=win.calibrated_score,
                    pred_raw=win.pred_raw,
                    pred_postprocessed=win.pred_postprocessed,
                    freeze_index_ankle=win.freeze_index_ankle,
                    bilateral_asym_ankle=win.bilateral_asym_ankle,
                    low_quality_flag=win.low_quality_flag,
                )
                for win in payload.windows
            ],
        ),
    )
    return SessionResultSyncResponse.from_dto(dto)


@router.post(
    "/{session_id}/analyze-video",
    response_model=VideoFallbackAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="(Cloud Fallback Opt-In) Analisis video terenkripsi dengan auto-delete wajib",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        413: {"model": ProblemDetailsSchema},
        415: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def analyze_video_fallback(
    session_id: UUID,
    actor: CurrentActorDep,
    use_case: Annotated[AnalyzeVideoFallbackUseCase, Depends(get_analyze_video_use_case)],
    file: Annotated[UploadFile, File(...)],
) -> VideoFallbackAnalysisResponse:
    async def _chunk_stream() -> AsyncIterator[bytes]:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            yield chunk

    try:
        dto = await use_case.execute(
            actor,
            session_id,
            content_type=file.content_type,
            data_stream=_chunk_stream(),
        )
        return VideoFallbackAnalysisResponse.from_dto(dto)
    finally:
        await file.close()


@router.get(
    "/{session_id}/report",
    response_model=SessionClinicalReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Unduh laporan klinis sesi skrining (?format=json|pdf)",
    responses={
        200: {"content": {"application/pdf": {}}},
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def get_session_report(
    session_id: UUID,
    actor: CurrentActorDep,
    use_case: Annotated[GetSessionReportUseCase, Depends(get_session_report_use_case)],
    format: Annotated[Literal["json", "pdf"], Query()] = "json",
) -> SessionClinicalReportResponse | Response:
    if format == "pdf":
        pdf_bytes, filename = await use_case.execute_pdf(actor, session_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    dto = await use_case.execute_json(actor, session_id)
    return SessionClinicalReportResponse.from_dto(dto)
