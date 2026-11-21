import hashlib

from src.application.dtos import ModelManifestOutputDTO
from src.application.interfaces import UnitOfWorkFactory
from src.domain.constants import (
    DEFAULT_THRESHOLDS_B15HZ,
    MIN_RUN_WINDOWS,
    SCALER_MEAN_B15HZ,
    SCALER_STD_B15HZ,
    STRIDE_SEC,
    TARGET_FS_HZ,
    WINDOW_SEC,
)
from src.domain.entities import ModelArtifactSpec, ModelBundleManifest
from src.domain.enums import ClassifierName, ModelFormat


def _placeholder_sha256(artifact_tag: str) -> str:
    return hashlib.sha256(artifact_tag.encode("utf-8")).hexdigest()


def build_default_b15hz_manifest(cdn_base_url: str) -> ModelBundleManifest:
    """Construct the canonical B_15hz OTA manifest matching EDGE_ML_SPEC.md."""
    base = cdn_base_url.rstrip("/")
    bundle_version = "b15hz-v1.0.0"
    return ModelBundleManifest(
        bundle_version=bundle_version,
        target_fps=int(TARGET_FS_HZ),
        window_sec=WINDOW_SEC,
        stride_sec=STRIDE_SEC,
        min_run_windows=MIN_RUN_WINDOWS,
        pose_estimator=ModelArtifactSpec(
            name="yolo26n-pose",
            format=ModelFormat.ONNX,
            download_url=f"{base}/{bundle_version}/yolo26n-pose.onnx",
            sha256=_placeholder_sha256(f"{bundle_version}/yolo26n-pose.onnx"),
            size_bytes=7_969_177,
            requires_scaled_input=False,
            threshold_val=0.25,
        ),
        primary_classifier=ModelArtifactSpec(
            name="lgbm_b15hz",
            format=ModelFormat.ONNX,
            download_url=f"{base}/{bundle_version}/lgbm_b15hz.onnx",
            sha256=_placeholder_sha256(f"{bundle_version}/lgbm_b15hz.onnx"),
            size_bytes=197_632,
            requires_scaled_input=False,
            threshold_val=DEFAULT_THRESHOLDS_B15HZ[ClassifierName.LIGHTGBM_FFT],
        ),
        secondary_classifier=ModelArtifactSpec(
            name="stgcn_b15hz",
            format=ModelFormat.ONNX,
            download_url=f"{base}/{bundle_version}/stgcn_b15hz.onnx",
            sha256=_placeholder_sha256(f"{bundle_version}/stgcn_b15hz.onnx"),
            size_bytes=186_368,
            requires_scaled_input=True,
            threshold_val=DEFAULT_THRESHOLDS_B15HZ[ClassifierName.LIGHT_STGCN],
        ),
        scaler_mean_b15hz=SCALER_MEAN_B15HZ,
        scaler_std_b15hz=SCALER_STD_B15HZ,
    )


class GetModelManifestUseCase:
    """Return active OTA Edge-AI model manifest, falling back to canonical B_15hz defaults."""

    def __init__(self, uow_factory: UnitOfWorkFactory, cdn_base_url: str) -> None:
        self._uow_factory = uow_factory
        self._cdn_base_url = cdn_base_url

    async def execute(self) -> ModelManifestOutputDTO:
        async with self._uow_factory() as uow:
            active = await uow.model_bundles.get_active()
        manifest = active or build_default_b15hz_manifest(self._cdn_base_url)
        return ModelManifestOutputDTO.from_entity(manifest)
