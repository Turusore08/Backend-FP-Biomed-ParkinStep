from typing import Literal

from pydantic import Field

from src.application.dtos import ModelArtifactSpecOutputDTO, ModelManifestOutputDTO
from src.domain.enums import ModelFormat
from src.domain.exceptions import DomainValidationError
from src.presentation.schemas.common import StrictBaseSchema


class ModelArtifactSpecSchema(StrictBaseSchema):
    name: str
    format: ModelFormat
    download_url: str
    sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    size_bytes: int
    requires_scaled_input: bool | None
    threshold_val: float | None

    @classmethod
    def from_dto(cls, dto: ModelArtifactSpecOutputDTO) -> "ModelArtifactSpecSchema":
        return cls(
            name=dto.name,
            format=dto.format,
            download_url=dto.download_url,
            sha256=dto.sha256,
            size_bytes=dto.size_bytes,
            requires_scaled_input=dto.requires_scaled_input,
            threshold_val=dto.threshold_val,
        )


class ModelManifestSchema(StrictBaseSchema):
    bundle_version: str
    target_fps: Literal[15]
    window_sec: float
    stride_sec: float
    min_run_windows: int
    pose_estimator: ModelArtifactSpecSchema
    primary_classifier: ModelArtifactSpecSchema
    secondary_classifier: ModelArtifactSpecSchema | None
    scaler_mean_b15hz: list[float] = Field(..., min_length=9, max_length=9)
    scaler_std_b15hz: list[float] = Field(..., min_length=9, max_length=9)

    @classmethod
    def from_dto(cls, dto: ModelManifestOutputDTO) -> "ModelManifestSchema":
        if dto.target_fps != 15:
            raise DomainValidationError("Active B_15hz model manifest must declare target_fps=15.")
        return cls(
            bundle_version=dto.bundle_version,
            target_fps=15,
            window_sec=dto.window_sec,
            stride_sec=dto.stride_sec,
            min_run_windows=dto.min_run_windows,
            pose_estimator=ModelArtifactSpecSchema.from_dto(dto.pose_estimator),
            primary_classifier=ModelArtifactSpecSchema.from_dto(dto.primary_classifier),
            secondary_classifier=(
                ModelArtifactSpecSchema.from_dto(dto.secondary_classifier)
                if dto.secondary_classifier is not None
                else None
            ),
            scaler_mean_b15hz=list(dto.scaler_mean_b15hz),
            scaler_std_b15hz=list(dto.scaler_std_b15hz),
        )
