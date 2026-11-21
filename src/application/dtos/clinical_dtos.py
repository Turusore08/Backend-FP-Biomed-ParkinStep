from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities import (
    ClinicalSession,
    EmergencyAlert,
    MedicationLog,
    ModelArtifactSpec,
    ModelBundleManifest,
)
from src.domain.enums import (
    ClassifierName,
    EmergencyTrigger,
    InferenceMode,
    MedicationState,
    ModelFormat,
    SessionProtocol,
)


@dataclass(frozen=True, slots=True)
class MedicationLogCreateDTO:
    log_id: UUID
    patient_id: UUID
    drug_name: str
    dosage_mg: float
    taken_at_utc: datetime
    med_state: MedicationState
    notes: str | None


@dataclass(frozen=True, slots=True)
class MedicationLogOutputDTO:
    log_id: UUID
    patient_id: UUID
    drug_name: str
    dosage_mg: float
    taken_at_utc: datetime
    med_state: MedicationState
    notes: str | None
    synced_at_utc: datetime

    @classmethod
    def from_entity(cls, entity: MedicationLog) -> "MedicationLogOutputDTO":
        return cls(
            log_id=entity.log_id,
            patient_id=entity.patient_id,
            drug_name=entity.drug_name,
            dosage_mg=entity.dosage_mg,
            taken_at_utc=entity.taken_at_utc,
            med_state=entity.med_state,
            notes=entity.notes,
            synced_at_utc=entity.synced_at_utc,
        )


@dataclass(frozen=True, slots=True)
class MedicationListQueryDTO:
    from_utc: datetime | None = None
    to_utc: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class MedicationLogListOutputDTO:
    items: list[MedicationLogOutputDTO]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class SessionCreateDTO:
    session_id: UUID
    patient_id: UUID
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    last_medication_log_id: UUID | None
    target_fps: int
    model_bundle_version: str
    started_at_utc: datetime
    safety_checklist_confirmed: bool


@dataclass(frozen=True, slots=True)
class SessionSummaryOutputDTO:
    session_id: UUID
    patient_id: UUID
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    last_medication_log_id: UUID | None
    target_fps: int
    model_bundle_version: str
    started_at_utc: datetime
    safety_checklist_confirmed: bool
    created_at_utc: datetime

    @classmethod
    def from_entity(cls, entity: ClinicalSession) -> "SessionSummaryOutputDTO":
        return cls(
            session_id=entity.session_id,
            patient_id=entity.patient_id,
            protocol=entity.protocol,
            inference_mode=entity.inference_mode,
            med_state=entity.med_state,
            last_medication_log_id=entity.last_medication_log_id,
            target_fps=entity.target_fps,
            model_bundle_version=entity.model_bundle_version,
            started_at_utc=entity.started_at_utc,
            safety_checklist_confirmed=entity.safety_checklist_confirmed,
            created_at_utc=entity.created_at_utc,
        )


@dataclass(frozen=True, slots=True)
class SkeletonBatchUploadDTO:
    session_id: UUID
    chunk_index: int
    sampling_hz: float
    frame_timestamps_ms: list[int]
    lb6_xyc: list[list[list[float]]]


@dataclass(frozen=True, slots=True)
class SkeletonBatchAckOutputDTO:
    session_id: UUID
    chunk_index: int
    frame_count: int
    compressed_bytes: int
    received_at_utc: datetime


@dataclass(frozen=True, slots=True)
class FogEpisodeInputDTO:
    episode_index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    peak_calibrated_score: float
    mean_freeze_index: float | None


@dataclass(frozen=True, slots=True)
class WindowPredictionInputDTO:
    window_idx: int
    start_sec: float
    end_sec: float
    raw_prob: float
    calibrated_score: float
    pred_raw: int
    pred_postprocessed: int
    freeze_index_ankle: float | None
    bilateral_asym_ankle: float | None
    low_quality_flag: bool


@dataclass(frozen=True, slots=True)
class SessionResultUploadDTO:
    session_id: UUID
    classifier_used: ClassifierName
    threshold_used: float
    ended_at_utc: datetime
    duration_sec: float
    valid_lb6_ratio: float
    fog_percentage: float
    episode_count: int
    total_fog_duration_sec: float
    median_episode_duration_sec: float
    episodes: list[FogEpisodeInputDTO]
    windows: list[WindowPredictionInputDTO]


@dataclass(frozen=True, slots=True)
class SessionResultSyncOutputDTO:
    session_id: UUID
    classifier_used: ClassifierName
    ended_at_utc: datetime
    episode_count: int
    window_count: int
    fog_percentage: float


@dataclass(frozen=True, slots=True)
class VideoFallbackResultOutputDTO:
    session_id: UUID
    status: str
    frames_analyzed: int
    auto_delete_after_inference: bool
    video_securely_deleted: bool
    detail: str


@dataclass(frozen=True, slots=True)
class FogEpisodeOutputDTO:
    episode_index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    peak_calibrated_score: float
    mean_freeze_index: float | None


@dataclass(frozen=True, slots=True)
class WindowPredictionOutputDTO:
    window_idx: int
    start_sec: float
    end_sec: float
    raw_prob: float
    calibrated_score: float
    pred_raw: int
    pred_postprocessed: int
    freeze_index_ankle: float | None
    bilateral_asym_ankle: float | None
    low_quality_flag: bool


@dataclass(frozen=True, slots=True)
class SessionClinicalReportOutputDTO:
    session_id: UUID
    patient_id: UUID
    patient_display_name: str
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    classifier_used: ClassifierName | None
    model_bundle_version: str
    threshold_used: float | None
    target_fps: int
    started_at_utc: datetime
    ended_at_utc: datetime | None
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
    episodes: list[FogEpisodeOutputDTO]
    windows: list[WindowPredictionOutputDTO]
    medical_disclaimer: str
    generated_at_utc: datetime


@dataclass(frozen=True, slots=True)
class TrendPointOutputDTO:
    session_id: UUID
    started_at_utc: datetime
    med_state: MedicationState
    fog_percentage: float
    episode_count: int


@dataclass(frozen=True, slots=True)
class PatientTrendsOutputDTO:
    patient_id: UUID
    total_sessions: int
    on_med_avg_fog_pct: float | None
    off_med_avg_fog_pct: float | None
    points: list[TrendPointOutputDTO]


@dataclass(frozen=True, slots=True)
class EmergencyAlertCreateDTO:
    alert_id: UUID
    patient_id: UUID
    session_id: UUID
    trigger_type: EmergencyTrigger
    triggered_at_utc: datetime
    cancelled_by_user: bool


@dataclass(frozen=True, slots=True)
class EmergencyAlertOutputDTO:
    alert_id: UUID
    patient_id: UUID
    session_id: UUID
    trigger_type: EmergencyTrigger
    triggered_at_utc: datetime
    cancelled_by_user: bool
    dispatched_at_utc: datetime | None
    notified_contacts_count: int

    @classmethod
    def from_entity(
        cls,
        entity: EmergencyAlert,
        *,
        notified_contacts_count: int,
    ) -> "EmergencyAlertOutputDTO":
        return cls(
            alert_id=entity.alert_id,
            patient_id=entity.patient_id,
            session_id=entity.session_id,
            trigger_type=entity.trigger_type,
            triggered_at_utc=entity.triggered_at_utc,
            cancelled_by_user=entity.cancelled_by_user,
            dispatched_at_utc=entity.dispatched_at_utc,
            notified_contacts_count=notified_contacts_count,
        )


@dataclass(frozen=True, slots=True)
class ModelArtifactSpecOutputDTO:
    name: str
    format: ModelFormat
    download_url: str
    sha256: str
    size_bytes: int
    requires_scaled_input: bool | None
    threshold_val: float | None

    @classmethod
    def from_entity(cls, spec: ModelArtifactSpec) -> "ModelArtifactSpecOutputDTO":
        return cls(
            name=spec.name,
            format=spec.format,
            download_url=spec.download_url,
            sha256=spec.sha256,
            size_bytes=spec.size_bytes,
            requires_scaled_input=spec.requires_scaled_input,
            threshold_val=spec.threshold_val,
        )


@dataclass(frozen=True, slots=True)
class ModelManifestOutputDTO:
    bundle_version: str
    target_fps: int
    window_sec: float
    stride_sec: float
    min_run_windows: int
    pose_estimator: ModelArtifactSpecOutputDTO
    primary_classifier: ModelArtifactSpecOutputDTO
    secondary_classifier: ModelArtifactSpecOutputDTO | None
    scaler_mean_b15hz: tuple[float, ...]
    scaler_std_b15hz: tuple[float, ...]

    @classmethod
    def from_entity(cls, manifest: ModelBundleManifest) -> "ModelManifestOutputDTO":
        return cls(
            bundle_version=manifest.bundle_version,
            target_fps=manifest.target_fps,
            window_sec=manifest.window_sec,
            stride_sec=manifest.stride_sec,
            min_run_windows=manifest.min_run_windows,
            pose_estimator=ModelArtifactSpecOutputDTO.from_entity(manifest.pose_estimator),
            primary_classifier=ModelArtifactSpecOutputDTO.from_entity(manifest.primary_classifier),
            secondary_classifier=(
                ModelArtifactSpecOutputDTO.from_entity(manifest.secondary_classifier)
                if manifest.secondary_classifier is not None
                else None
            ),
            scaler_mean_b15hz=manifest.scaler_mean_b15hz,
            scaler_std_b15hz=manifest.scaler_std_b15hz,
        )
