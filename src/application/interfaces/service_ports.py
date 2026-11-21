from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from src.domain.entities import EmergencyAlert, EmergencyContact

if TYPE_CHECKING:
    from src.application.dtos import SessionClinicalReportOutputDTO


@dataclass(frozen=True, slots=True)
class VideoAnalysisOutcome:
    """Result returned by cloud fallback analyzer before secure temp video deletion."""

    frames_analyzed: int
    detail: str


class EmergencyNotifierPort(Protocol):
    """Port for dispatching high-priority alerts to caregiver contacts."""

    async def notify_caregivers(
        self,
        alert: EmergencyAlert,
        contacts: list[EmergencyContact],
    ) -> int:
        ...


class CloudVideoAnalyzerPort(Protocol):
    """Pluggable port for opt-in encrypted cloud video fallback inference."""

    async def analyze_video_file(
        self,
        video_path: Path,
        session_id: UUID,
    ) -> VideoAnalysisOutcome:
        ...


class VideoDisposalPort(Protocol):
    """Port guaranteeing zero raw-video retention via scoped secure temp disposal."""

    def secure_temp_video(
        self,
        data_stream: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> AbstractAsyncContextManager[Path]:
        ...


class SkeletonCodecPort(Protocol):
    """Binary ZLIB codec for LB6 [T][6][3] keypoints and millisecond timestamps."""

    def pack(
        self,
        timestamps_ms: list[int],
        lb6_xyc: list[list[list[float]]],
    ) -> bytes:
        ...

    def unpack(
        self,
        payload: bytes,
    ) -> tuple[list[int], list[list[list[float]]]]:
        ...


class ClinicalReportPdfRendererPort(Protocol):
    """Port for rendering clinical FoG session reports to PDF bytes."""

    def render_pdf(self, report: "SessionClinicalReportOutputDTO") -> bytes:
        ...


class CloudKeypointClassifierPort(Protocol):
    """Port for real-time 126-FFT feature FoG classification in CLOUD_FALLBACK mode."""

    @property
    def threshold_val(self) -> float:
        ...

    def predict_window_prob(
        self,
        features_126: list[float],
        freeze_index_ankle: float,
    ) -> float:
        ...
