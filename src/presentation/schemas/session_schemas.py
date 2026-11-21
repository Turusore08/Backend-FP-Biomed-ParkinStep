from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from src.application.dtos import (
    SessionClinicalReportOutputDTO,
    SessionResultSyncOutputDTO,
    SessionSummaryOutputDTO,
    SkeletonBatchAckOutputDTO,
    VideoFallbackResultOutputDTO,
)
from src.domain.enums import (
    AlertTier,
    ClassifierName,
    InferenceMode,
    MedicationState,
    SessionProtocol,
)
from src.presentation.schemas.common import StrictBaseSchema, UtcDatetime

type Lb6JointSchema = Annotated[list[float], Field(min_length=3, max_length=3)]
type Lb6FrameSchema = Annotated[list[Lb6JointSchema], Field(min_length=6, max_length=6)]


class SessionCreateRequest(StrictBaseSchema):
    session_id: UUID
    patient_id: UUID
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    last_medication_log_id: UUID | None = None
    target_fps: Literal[15, 30]
    model_bundle_version: str = Field(..., min_length=1, max_length=64)
    started_at_utc: UtcDatetime
    safety_checklist_confirmed: bool


class SessionSummary(StrictBaseSchema):
    session_id: UUID
    patient_id: UUID
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    last_medication_log_id: UUID | None
    target_fps: Literal[15, 30]
    model_bundle_version: str
    started_at_utc: UtcDatetime
    safety_checklist_confirmed: bool
    created_at_utc: UtcDatetime

    @classmethod
    def from_dto(cls, dto: SessionSummaryOutputDTO) -> "SessionSummary":
        fps_literal: Literal[15, 30] = 30 if dto.target_fps == 30 else 15
        return cls(
            session_id=dto.session_id,
            patient_id=dto.patient_id,
            protocol=dto.protocol,
            inference_mode=dto.inference_mode,
            med_state=dto.med_state,
            last_medication_log_id=dto.last_medication_log_id,
            target_fps=fps_literal,
            model_bundle_version=dto.model_bundle_version,
            started_at_utc=dto.started_at_utc,
            safety_checklist_confirmed=dto.safety_checklist_confirmed,
            created_at_utc=dto.created_at_utc,
        )


class SkeletonBatchUpload(StrictBaseSchema):
    chunk_index: int = Field(..., ge=0)
    sampling_hz: float = Field(..., json_schema_extra={"enum": [15.0, 30.0]})
    frame_timestamps_ms: list[int] = Field(..., min_length=1, max_length=3600)
    lb6_xyc: list[Lb6FrameSchema] = Field(..., min_length=1, max_length=3600)

    @field_validator("sampling_hz")
    @classmethod
    def validate_sampling_hz(cls, value: float) -> float:
        if value not in (15.0, 30.0):
            raise ValueError("sampling_hz must be 15.0 or 30.0.")
        return value


class SkeletonBatchAckResponse(StrictBaseSchema):
    session_id: UUID
    chunk_index: int
    frame_count: int
    compressed_bytes: int
    received_at_utc: UtcDatetime

    @classmethod
    def from_dto(cls, dto: SkeletonBatchAckOutputDTO) -> "SkeletonBatchAckResponse":
        return cls(
            session_id=dto.session_id,
            chunk_index=dto.chunk_index,
            frame_count=dto.frame_count,
            compressed_bytes=dto.compressed_bytes,
            received_at_utc=dto.received_at_utc,
        )


class FogEpisodeItem(StrictBaseSchema):
    episode_index: int = Field(..., ge=1)
    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., ge=0)
    duration_sec: float = Field(..., ge=0)
    peak_calibrated_score: float = Field(..., ge=0, le=100)
    mean_freeze_index: float | None = None


class WindowPredictionItem(StrictBaseSchema):
    window_idx: int = Field(..., ge=0)
    start_sec: float
    end_sec: float
    raw_prob: float = Field(..., ge=0, le=1)
    calibrated_score: float = Field(..., ge=0, le=100)
    pred_raw: Literal[0, 1]
    pred_postprocessed: Literal[0, 1]
    freeze_index_ankle: float | None = None
    bilateral_asym_ankle: float | None = None
    low_quality_flag: bool


class SessionResultUpload(StrictBaseSchema):
    classifier_used: ClassifierName
    threshold_used: float
    ended_at_utc: UtcDatetime
    duration_sec: float = Field(..., ge=0)
    valid_lb6_ratio: float = Field(..., ge=0, le=1)
    fog_percentage: float = Field(..., ge=0, le=100)
    episode_count: int = Field(..., ge=0)
    total_fog_duration_sec: float = Field(..., ge=0)
    median_episode_duration_sec: float = Field(..., ge=0)
    episodes: list[FogEpisodeItem]
    windows: list[WindowPredictionItem]


class SessionResultSyncResponse(StrictBaseSchema):
    session_id: UUID
    classifier_used: ClassifierName
    ended_at_utc: UtcDatetime
    episode_count: int
    window_count: int
    fog_percentage: float

    @classmethod
    def from_dto(cls, dto: SessionResultSyncOutputDTO) -> "SessionResultSyncResponse":
        return cls(
            session_id=dto.session_id,
            classifier_used=dto.classifier_used,
            ended_at_utc=dto.ended_at_utc,
            episode_count=dto.episode_count,
            window_count=dto.window_count,
            fog_percentage=dto.fog_percentage,
        )


class VideoFallbackAnalysisResponse(StrictBaseSchema):
    session_id: UUID
    status: str
    frames_analyzed: int
    auto_delete_after_inference: bool
    video_securely_deleted: bool
    detail: str

    @classmethod
    def from_dto(cls, dto: VideoFallbackResultOutputDTO) -> "VideoFallbackAnalysisResponse":
        return cls(
            session_id=dto.session_id,
            status=dto.status,
            frames_analyzed=dto.frames_analyzed,
            auto_delete_after_inference=dto.auto_delete_after_inference,
            video_securely_deleted=dto.video_securely_deleted,
            detail=dto.detail,
        )


class SessionClinicalReportResponse(StrictBaseSchema):
    session_id: UUID
    patient_id: UUID
    patient_display_name: str
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    classifier_used: ClassifierName | None
    model_bundle_version: str
    threshold_used: float | None
    target_fps: Literal[15, 30]
    started_at_utc: UtcDatetime
    ended_at_utc: UtcDatetime | None
    duration_sec: float
    valid_lb6_ratio: float
    fog_percentage: float
    episode_count: int
    total_fog_duration_sec: float
    median_episode_duration_sec: float
    mean_freeze_index: float
    mean_bilateral_asymmetry: float
    asymmetry_level_id: str
    fall_guard_false_alarms: int
    video_securely_deleted: bool
    episodes: list[FogEpisodeItem]
    windows: list[WindowPredictionItem]
    medical_disclaimer: str
    generated_at_utc: UtcDatetime

    @classmethod
    def from_dto(cls, dto: SessionClinicalReportOutputDTO) -> "SessionClinicalReportResponse":
        fps_literal: Literal[15, 30] = 30 if dto.target_fps == 30 else 15
        return cls(
            session_id=dto.session_id,
            patient_id=dto.patient_id,
            patient_display_name=dto.patient_display_name,
            protocol=dto.protocol,
            inference_mode=dto.inference_mode,
            med_state=dto.med_state,
            classifier_used=dto.classifier_used,
            model_bundle_version=dto.model_bundle_version,
            threshold_used=dto.threshold_used,
            target_fps=fps_literal,
            started_at_utc=dto.started_at_utc,
            ended_at_utc=dto.ended_at_utc,
            duration_sec=dto.duration_sec,
            valid_lb6_ratio=dto.valid_lb6_ratio,
            fog_percentage=dto.fog_percentage,
            episode_count=dto.episode_count,
            total_fog_duration_sec=dto.total_fog_duration_sec,
            median_episode_duration_sec=dto.median_episode_duration_sec,
            mean_freeze_index=dto.mean_freeze_index,
            mean_bilateral_asymmetry=dto.mean_bilateral_asymmetry,
            asymmetry_level_id=dto.asymmetry_level_id,
            fall_guard_false_alarms=dto.fall_guard_false_alarms,
            video_securely_deleted=dto.video_securely_deleted,
            episodes=[
                FogEpisodeItem(
                    episode_index=ep.episode_index,
                    start_sec=ep.start_sec,
                    end_sec=ep.end_sec,
                    duration_sec=ep.duration_sec,
                    peak_calibrated_score=ep.peak_calibrated_score,
                    mean_freeze_index=ep.mean_freeze_index,
                )
                for ep in dto.episodes
            ],
            windows=[
                WindowPredictionItem(
                    window_idx=win.window_idx,
                    start_sec=win.start_sec,
                    end_sec=win.end_sec,
                    raw_prob=win.raw_prob,
                    calibrated_score=win.calibrated_score,
                    pred_raw=1 if win.pred_raw == 1 else 0,
                    pred_postprocessed=1 if win.pred_postprocessed == 1 else 0,
                    freeze_index_ankle=win.freeze_index_ankle,
                    bilateral_asym_ankle=win.bilateral_asym_ankle,
                    low_quality_flag=win.low_quality_flag,
                )
                for win in dto.windows
            ],
            medical_disclaimer=dto.medical_disclaimer,
            generated_at_utc=dto.generated_at_utc,
        )


class WsLb6FrameMessage(StrictBaseSchema):
    type: Literal["LB6_FRAME"]
    seq: int = Field(..., ge=0)
    t_ms: int = Field(..., ge=0)
    lb6_xyc: Lb6FrameSchema


class WsWindowPredictionMessage(StrictBaseSchema):
    type: Literal["WINDOW_PREDICTION"] = "WINDOW_PREDICTION"
    window_idx: int
    raw_prob: float
    calibrated_score: float
    alert_tier: AlertTier
    freeze_index_ankle: float
