from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import ModelArtifactSpec, ModelBundleManifest
from src.domain.enums import ModelFormat
from src.infrastructure.persistence.models import ModelBundleORM


def _spec_from_dict(data: dict[str, Any]) -> ModelArtifactSpec:
    return ModelArtifactSpec(
        name=str(data["name"]),
        format=ModelFormat(str(data["format"])),
        download_url=str(data["download_url"]),
        sha256=str(data["sha256"]),
        size_bytes=int(data["size_bytes"]),
        requires_scaled_input=data.get("requires_scaled_input"),
        threshold_val=data.get("threshold_val"),
    )


def _spec_to_dict(spec: ModelArtifactSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "format": spec.format.value,
        "download_url": spec.download_url,
        "sha256": spec.sha256,
        "size_bytes": spec.size_bytes,
        "requires_scaled_input": spec.requires_scaled_input,
        "threshold_val": spec.threshold_val,
    }


def _to_entity(row: ModelBundleORM) -> ModelBundleManifest:
    payload = row.manifest_payload
    sec_raw = payload.get("secondary_classifier")
    return ModelBundleManifest(
        bundle_version=row.bundle_version,
        target_fps=row.target_fps,
        window_sec=row.window_sec,
        stride_sec=row.stride_sec,
        min_run_windows=row.min_run_windows,
        pose_estimator=_spec_from_dict(payload["pose_estimator"]),
        primary_classifier=_spec_from_dict(payload["primary_classifier"]),
        secondary_classifier=_spec_from_dict(sec_raw) if sec_raw is not None else None,
        scaler_mean_b15hz=tuple(float(x) for x in payload["scaler_mean_b15hz"]),
        scaler_std_b15hz=tuple(float(x) for x in payload["scaler_std_b15hz"]),
    )


class SqlModelBundleRepository:
    """SQLAlchemy async repository for OTA Edge-AI model bundle manifests."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> ModelBundleManifest | None:
        stmt = (
            select(ModelBundleORM)
            .where(ModelBundleORM.is_active.is_(True))
            .order_by(ModelBundleORM.published_at_utc.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def upsert(
        self,
        manifest: ModelBundleManifest,
        *,
        is_active: bool,
        published_at_utc: datetime,
    ) -> None:
        if is_active:
            await self._session.execute(
                update(ModelBundleORM).where(ModelBundleORM.is_active.is_(True)).values(
                    is_active=False
                )
            )

        payload: dict[str, Any] = {
            "pose_estimator": _spec_to_dict(manifest.pose_estimator),
            "primary_classifier": _spec_to_dict(manifest.primary_classifier),
            "secondary_classifier": (
                _spec_to_dict(manifest.secondary_classifier)
                if manifest.secondary_classifier is not None
                else None
            ),
            "scaler_mean_b15hz": list(manifest.scaler_mean_b15hz),
            "scaler_std_b15hz": list(manifest.scaler_std_b15hz),
        }

        existing = await self._session.get(ModelBundleORM, manifest.bundle_version)
        if existing is None:
            self._session.add(
                ModelBundleORM(
                    bundle_version=manifest.bundle_version,
                    is_active=is_active,
                    target_fps=manifest.target_fps,
                    window_sec=manifest.window_sec,
                    stride_sec=manifest.stride_sec,
                    min_run_windows=manifest.min_run_windows,
                    manifest_payload=payload,
                    published_at_utc=published_at_utc,
                )
            )
        else:
            existing.is_active = is_active
            existing.target_fps = manifest.target_fps
            existing.window_sec = manifest.window_sec
            existing.stride_sec = manifest.stride_sec
            existing.min_run_windows = manifest.min_run_windows
            existing.manifest_payload = payload
            existing.published_at_utc = published_at_utc
        await self._session.flush()
