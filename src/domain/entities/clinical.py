from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.domain.enums.clinical_enums import (
    ClassifierName,
    EmergencyTrigger,
    InferenceMode,
    MedicationState,
    ModelFormat,
    SessionProtocol,
)
from src.domain.value_objects.utc_timestamp import ensure_utc


@dataclass(slots=True)
class MedicationLog:
    """Levodopa medication log entry."""

    log_id: UUID
    patient_id: UUID
    drug_name: str
    dosage_mg: float
    taken_at_utc: datetime
    med_state: MedicationState
    notes: str | None
    synced_at_utc: datetime

    def __post_init__(self) -> None:
        self.taken_at_utc = ensure_utc(self.taken_at_utc)
        self.synced_at_utc = ensure_utc(self.synced_at_utc)


@dataclass(slots=True)
class FogEpisode:
    """Confirmed FoG episode (min_run >= 2 windows)."""

    episode_id: UUID
    session_id: UUID
    episode_index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    peak_calibrated_score: float
    mean_freeze_index: float | None = None


@dataclass(slots=True)
class WindowPrediction:
    """Per-window prediction (2.0s window, 1.0s stride)."""

    session_id: UUID
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


@dataclass(slots=True)
class SkeletonChunk:
    """Compressed LB6 keypoint batch [T][6][3] without raw video."""

    session_id: UUID
    chunk_index: int
    sampling_hz: float
    frame_count: int
    compression: str
    payload_blob: bytes
    byte_size: int
    received_at_utc: datetime

    def __post_init__(self) -> None:
        self.received_at_utc = ensure_utc(self.received_at_utc)


@dataclass(slots=True)
class ClinicalSession:
    """360-degree Turning-in-Place or free-walk screening session."""

    session_id: UUID
    patient_id: UUID
    last_medication_log_id: UUID | None
    protocol: SessionProtocol
    inference_mode: InferenceMode
    med_state: MedicationState
    target_fps: int
    model_bundle_version: str
    started_at_utc: datetime
    safety_checklist_confirmed: bool
    created_at_utc: datetime
    classifier_used: ClassifierName | None = None
    threshold_used: float | None = None
    ended_at_utc: datetime | None = None
    duration_sec: float = 0.0
    valid_lb6_ratio: float = 0.0
    fog_percentage: float = 0.0
    episode_count: int = 0
    total_fog_duration_sec: float = 0.0
    median_episode_duration_sec: float = 0.0
    episodes: list[FogEpisode] = field(default_factory=list)
    windows: list[WindowPrediction] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.started_at_utc = ensure_utc(self.started_at_utc)
        self.created_at_utc = ensure_utc(self.created_at_utc)
        if self.ended_at_utc is not None:
            self.ended_at_utc = ensure_utc(self.ended_at_utc)


@dataclass(slots=True)
class EmergencyAlert:
    """Fall or prolonged freeze (> 15s) escalation alert."""

    alert_id: UUID
    patient_id: UUID
    session_id: UUID
    trigger_type: EmergencyTrigger
    triggered_at_utc: datetime
    cancelled_by_user: bool
    dispatched_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        self.triggered_at_utc = ensure_utc(self.triggered_at_utc)
        if self.dispatched_at_utc is not None:
            self.dispatched_at_utc = ensure_utc(self.dispatched_at_utc)


@dataclass(frozen=True, slots=True)
class ModelArtifactSpec:
    """Single downloadable Edge-AI model artifact metadata."""

    name: str
    format: ModelFormat
    download_url: str
    sha256: str
    size_bytes: int
    requires_scaled_input: bool | None = None
    threshold_val: float | None = None


@dataclass(frozen=True, slots=True)
class ModelBundleManifest:
    """OTA Edge-AI model bundle manifest for B_15hz."""

    bundle_version: str
    target_fps: int
    window_sec: float
    stride_sec: float
    min_run_windows: int
    pose_estimator: ModelArtifactSpec
    primary_classifier: ModelArtifactSpec
    secondary_classifier: ModelArtifactSpec | None
    scaler_mean_b15hz: tuple[float, ...]
    scaler_std_b15hz: tuple[float, ...]
