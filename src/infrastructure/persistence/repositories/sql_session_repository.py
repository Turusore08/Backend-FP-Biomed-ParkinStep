from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import (
    ClinicalSession,
    FogEpisode,
    SkeletonChunk,
    WindowPrediction,
)
from src.domain.enums import (
    ClassifierName,
    InferenceMode,
    MedicationState,
    SessionProtocol,
)
from src.infrastructure.persistence.models import (
    ClinicalSessionORM,
    FogEpisodeORM,
    SkeletonChunkORM,
    WindowPredictionORM,
)


def _to_entity(row: ClinicalSessionORM) -> ClinicalSession:
    return ClinicalSession(
        session_id=row.session_id,
        patient_id=row.patient_id,
        last_medication_log_id=row.last_medication_log_id,
        protocol=SessionProtocol(row.protocol),
        inference_mode=InferenceMode(row.inference_mode),
        med_state=MedicationState(row.med_state),
        target_fps=row.target_fps,
        model_bundle_version=row.model_bundle_version,
        started_at_utc=row.started_at_utc,
        safety_checklist_confirmed=row.safety_checklist_confirmed,
        created_at_utc=row.created_at_utc,
        classifier_used=(
            ClassifierName(row.classifier_used)
            if row.classifier_used is not None
            else None
        ),
        threshold_used=row.threshold_used,
        ended_at_utc=row.ended_at_utc,
        duration_sec=row.duration_sec,
        valid_lb6_ratio=row.valid_lb6_ratio,
        fog_percentage=row.fog_percentage,
        episode_count=row.episode_count,
        total_fog_duration_sec=row.total_fog_duration_sec,
        median_episode_duration_sec=row.median_episode_duration_sec,
    )


class SqlSessionRepository:
    """SQLAlchemy async repository for ClinicalSession, SkeletonChunk, Episodes, and Windows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, session: ClinicalSession) -> None:
        self._session.add(
            ClinicalSessionORM(
                session_id=session.session_id,
                patient_id=session.patient_id,
                last_medication_log_id=session.last_medication_log_id,
                protocol=session.protocol.value,
                inference_mode=session.inference_mode.value,
                med_state=session.med_state.value,
                target_fps=session.target_fps,
                model_bundle_version=session.model_bundle_version,
                started_at_utc=session.started_at_utc,
                safety_checklist_confirmed=session.safety_checklist_confirmed,
                classifier_used=(
                    session.classifier_used.value if session.classifier_used else None
                ),
                threshold_used=session.threshold_used,
                ended_at_utc=session.ended_at_utc,
                duration_sec=session.duration_sec,
                valid_lb6_ratio=session.valid_lb6_ratio,
                fog_percentage=session.fog_percentage,
                episode_count=session.episode_count,
                total_fog_duration_sec=session.total_fog_duration_sec,
                median_episode_duration_sec=session.median_episode_duration_sec,
                created_at_utc=session.created_at_utc,
            )
        )
        await self._session.flush()

    async def get_by_id(self, session_id: UUID) -> ClinicalSession | None:
        row = await self._session.get(ClinicalSessionORM, session_id)
        return _to_entity(row) if row is not None else None

    async def add_skeleton_chunk(self, chunk: SkeletonChunk) -> None:
        self._session.add(
            SkeletonChunkORM(
                session_id=chunk.session_id,
                chunk_index=chunk.chunk_index,
                sampling_hz=chunk.sampling_hz,
                frame_count=chunk.frame_count,
                compression=chunk.compression,
                payload_blob=chunk.payload_blob,
                byte_size=chunk.byte_size,
                received_at_utc=chunk.received_at_utc,
            )
        )
        await self._session.flush()

    async def has_skeleton_chunk(self, session_id: UUID, chunk_index: int) -> bool:
        stmt = select(SkeletonChunkORM.chunk_index).where(
            and_(
                SkeletonChunkORM.session_id == session_id,
                SkeletonChunkORM.chunk_index == chunk_index,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def save_results(
        self,
        session: ClinicalSession,
        episodes: list[FogEpisode],
        windows: list[WindowPrediction],
    ) -> None:
        stmt = (
            update(ClinicalSessionORM)
            .where(ClinicalSessionORM.session_id == session.session_id)
            .values(
                classifier_used=(
                    session.classifier_used.value if session.classifier_used else None
                ),
                threshold_used=session.threshold_used,
                ended_at_utc=session.ended_at_utc,
                duration_sec=session.duration_sec,
                valid_lb6_ratio=session.valid_lb6_ratio,
                fog_percentage=session.fog_percentage,
                episode_count=session.episode_count,
                total_fog_duration_sec=session.total_fog_duration_sec,
                median_episode_duration_sec=session.median_episode_duration_sec,
            )
        )
        await self._session.execute(stmt)

        for ep in episodes:
            self._session.add(
                FogEpisodeORM(
                    episode_id=ep.episode_id,
                    session_id=ep.session_id,
                    episode_index=ep.episode_index,
                    start_sec=ep.start_sec,
                    end_sec=ep.end_sec,
                    duration_sec=ep.duration_sec,
                    peak_calibrated_score=ep.peak_calibrated_score,
                    mean_freeze_index=ep.mean_freeze_index,
                )
            )

        for win in windows:
            self._session.add(
                WindowPredictionORM(
                    session_id=win.session_id,
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
            )
        await self._session.flush()

    async def list_completed_for_trends(
        self,
        patient_id: UUID,
        *,
        from_utc: datetime | None,
        to_utc: datetime | None,
    ) -> list[ClinicalSession]:
        filters: list[ColumnElement[bool]] = [
            ClinicalSessionORM.patient_id == patient_id,
            ClinicalSessionORM.ended_at_utc.is_not(None),
        ]
        if from_utc is not None:
            filters.append(ClinicalSessionORM.started_at_utc >= from_utc)
        if to_utc is not None:
            filters.append(ClinicalSessionORM.started_at_utc <= to_utc)

        stmt = (
            select(ClinicalSessionORM)
            .where(*filters)
            .order_by(ClinicalSessionORM.started_at_utc.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows]
