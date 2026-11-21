from uuid import uuid4

from src.application.dtos import (
    ActorContext,
    SessionResultSyncOutputDTO,
    SessionResultUploadDTO,
)
from src.application.interfaces import UnitOfWorkFactory
from src.application.use_cases.patients.access import (
    ensure_patient_access,
    require_sync_consent,
)
from src.domain.entities import FogEpisode, WindowPrediction
from src.domain.exceptions import (
    ConflictError,
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.value_objects import ensure_utc


class UploadSessionResultsUseCase:
    """Persist Edge-AI window predictions and confirmed FoG episodes atomically."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def _validate_payload(self, request: SessionResultUploadDTO) -> None:
        if request.duration_sec < 0.0:
            raise DomainValidationError("duration_sec must be >= 0.")
        if not (0.0 <= request.valid_lb6_ratio <= 1.0):
            raise DomainValidationError("valid_lb6_ratio must be within [0.0, 1.0].")
        if not (0.0 <= request.fog_percentage <= 100.0):
            raise DomainValidationError("fog_percentage must be within [0.0, 100.0].")
        if request.episode_count != len(request.episodes):
            raise DomainValidationError("episode_count must match len(episodes).")
        if request.total_fog_duration_sec < 0.0 or request.median_episode_duration_sec < 0.0:
            raise DomainValidationError("FoG duration metrics must be >= 0.")

        seen_episodes: set[int] = set()
        for ep in request.episodes:
            if ep.episode_index < 1 or ep.episode_index in seen_episodes:
                raise DomainValidationError("episodes must have unique episode_index >= 1.")
            if ep.start_sec < 0.0 or ep.end_sec < ep.start_sec or ep.duration_sec < 0.0:
                raise DomainValidationError("Episode timing bounds are invalid.")
            if not (0.0 <= ep.peak_calibrated_score <= 100.0):
                raise DomainValidationError("peak_calibrated_score must be within [0.0, 100.0].")
            seen_episodes.add(ep.episode_index)

        seen_windows: set[int] = set()
        for win in request.windows:
            if win.window_idx < 0 or win.window_idx in seen_windows:
                raise DomainValidationError("windows must have unique window_idx >= 0.")
            if win.end_sec < win.start_sec:
                raise DomainValidationError("Window end_sec must be >= start_sec.")
            if not (0.0 <= win.raw_prob <= 1.0):
                raise DomainValidationError("Window raw_prob must be within [0.0, 1.0].")
            if not (0.0 <= win.calibrated_score <= 100.0):
                raise DomainValidationError("Window calibrated_score must be within [0.0, 100.0].")
            if win.pred_raw not in (0, 1) or win.pred_postprocessed not in (0, 1):
                raise DomainValidationError("pred_raw and pred_postprocessed must be 0 or 1.")
            seen_windows.add(win.window_idx)

    async def execute(
        self,
        actor: ActorContext,
        request: SessionResultUploadDTO,
    ) -> SessionResultSyncOutputDTO:
        self._validate_payload(request)
        ended_at = ensure_utc(request.ended_at_utc)

        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_id(request.session_id)
            if session is None:
                raise EntityNotFoundError(
                    f"Clinical session {request.session_id} was not found.",
                    error_code="SESSION_NOT_FOUND",
                )

            patient = await ensure_patient_access(uow, actor, session.patient_id)
            require_sync_consent(patient)

            if session.ended_at_utc is not None:
                raise ConflictError(
                    f"Results for session {request.session_id} have already been finalized.",
                    error_code="SESSION_RESULTS_ALREADY_UPLOADED",
                )
            if ended_at < session.started_at_utc:
                raise DomainValidationError("ended_at_utc must not precede started_at_utc.")

            episodes = [
                FogEpisode(
                    episode_id=uuid4(),
                    session_id=session.session_id,
                    episode_index=ep.episode_index,
                    start_sec=ep.start_sec,
                    end_sec=ep.end_sec,
                    duration_sec=ep.duration_sec,
                    peak_calibrated_score=ep.peak_calibrated_score,
                    mean_freeze_index=ep.mean_freeze_index,
                )
                for ep in request.episodes
            ]
            windows = [
                WindowPrediction(
                    session_id=session.session_id,
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
                for win in request.windows
            ]

            session.classifier_used = request.classifier_used
            session.threshold_used = request.threshold_used
            session.ended_at_utc = ended_at
            session.duration_sec = request.duration_sec
            session.valid_lb6_ratio = request.valid_lb6_ratio
            session.fog_percentage = request.fog_percentage
            session.episode_count = request.episode_count
            session.total_fog_duration_sec = request.total_fog_duration_sec
            session.median_episode_duration_sec = request.median_episode_duration_sec

            await uow.sessions.save_results(session, episodes, windows)
            await uow.commit()

        return SessionResultSyncOutputDTO(
            session_id=request.session_id,
            classifier_used=request.classifier_used,
            ended_at_utc=ended_at,
            episode_count=len(episodes),
            window_count=len(windows),
            fog_percentage=request.fog_percentage,
        )
