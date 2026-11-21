from uuid import UUID

from src.application.dtos import (
    ActorContext,
    FogEpisodeOutputDTO,
    SessionClinicalReportOutputDTO,
    WindowPredictionOutputDTO,
)
from src.application.interfaces import ClinicalReportPdfRendererPort, UnitOfWorkFactory
from src.application.use_cases.patients.access import ensure_patient_access
from src.domain.constants import MEDICAL_DISCLAIMER_ID
from src.domain.exceptions import EntityNotFoundError
from src.domain.value_objects import utc_now


def _asymmetry_level(value: float) -> str:
    if value < 0.12:
        return "Rendah"
    if value < 0.25:
        return "Sedang"
    return "Tinggi"


class GetSessionReportUseCase:
    """Assemble full clinical session reports in JSON and PDF formats."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        pdf_renderer: ClinicalReportPdfRendererPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._pdf_renderer = pdf_renderer

    async def execute_json(
        self,
        actor: ActorContext,
        session_id: UUID,
    ) -> SessionClinicalReportOutputDTO:
        async with self._uow_factory() as uow:
            session = await uow.sessions.get_with_details(session_id)
            if session is None:
                raise EntityNotFoundError(
                    f"Clinical session {session_id} was not found.",
                    error_code="SESSION_NOT_FOUND",
                )
            patient = await ensure_patient_access(uow, actor, session.patient_id)
            false_alarms = await uow.alerts.count_cancelled_by_session(session_id)

        freeze_values = [
            w.freeze_index_ankle
            for w in session.windows
            if w.freeze_index_ankle is not None
        ]
        if not freeze_values:
            freeze_values = [
                ep.mean_freeze_index
                for ep in session.episodes
                if ep.mean_freeze_index is not None
            ]
        mean_freeze = round(sum(freeze_values) / len(freeze_values), 3) if freeze_values else 0.0

        asym_values = [
            w.bilateral_asym_ankle
            for w in session.windows
            if w.bilateral_asym_ankle is not None
        ]
        mean_asym = round(sum(asym_values) / len(asym_values), 3) if asym_values else 0.0

        return SessionClinicalReportOutputDTO(
            session_id=session.session_id,
            patient_id=session.patient_id,
            patient_display_name=patient.display_name,
            protocol=session.protocol,
            inference_mode=session.inference_mode,
            med_state=session.med_state,
            classifier_used=session.classifier_used,
            model_bundle_version=session.model_bundle_version,
            threshold_used=session.threshold_used,
            target_fps=session.target_fps,
            started_at_utc=session.started_at_utc,
            ended_at_utc=session.ended_at_utc,
            duration_sec=session.duration_sec,
            valid_lb6_ratio=session.valid_lb6_ratio,
            fog_percentage=session.fog_percentage,
            episode_count=session.episode_count,
            total_fog_duration_sec=session.total_fog_duration_sec,
            median_episode_duration_sec=session.median_episode_duration_sec,
            mean_freeze_index=mean_freeze,
            mean_bilateral_asymmetry=mean_asym,
            asymmetry_level_id=_asymmetry_level(mean_asym),
            fall_guard_false_alarms=false_alarms,
            video_securely_deleted=True,
            episodes=[
                FogEpisodeOutputDTO(
                    episode_index=ep.episode_index,
                    start_sec=ep.start_sec,
                    end_sec=ep.end_sec,
                    duration_sec=ep.duration_sec,
                    peak_calibrated_score=ep.peak_calibrated_score,
                    mean_freeze_index=ep.mean_freeze_index,
                )
                for ep in session.episodes
            ],
            windows=[
                WindowPredictionOutputDTO(
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
                for win in session.windows
            ],
            medical_disclaimer=MEDICAL_DISCLAIMER_ID,
            generated_at_utc=utc_now(),
        )

    async def execute_pdf(
        self,
        actor: ActorContext,
        session_id: UUID,
    ) -> tuple[bytes, str]:
        report = await self.execute_json(actor, session_id)
        pdf_bytes = self._pdf_renderer.render_pdf(report)
        return pdf_bytes, f"parkinstep-report-{session_id}.pdf"
