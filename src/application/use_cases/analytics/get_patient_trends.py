from datetime import datetime
from uuid import UUID

from src.application.dtos import (
    ActorContext,
    PatientTrendsOutputDTO,
    TrendPointOutputDTO,
)
from src.application.interfaces import UnitOfWorkFactory
from src.application.use_cases.patients.access import ensure_patient_access
from src.domain.enums import MedicationState
from src.domain.exceptions import DomainValidationError
from src.domain.value_objects import ensure_utc


def _avg_fog(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


class GetPatientTrendsUseCase:
    """Compute longitudinal FoG% trends and ON vs OFF medication comparisons."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: ActorContext,
        patient_id: UUID,
        *,
        from_utc: datetime | None = None,
        to_utc: datetime | None = None,
    ) -> PatientTrendsOutputDTO:
        from_dt = ensure_utc(from_utc) if from_utc is not None else None
        to_dt = ensure_utc(to_utc) if to_utc is not None else None
        if from_dt is not None and to_dt is not None and from_dt > to_dt:
            raise DomainValidationError("from_utc must be earlier than or equal to to_utc.")

        async with self._uow_factory() as uow:
            await ensure_patient_access(uow, actor, patient_id)
            sessions = await uow.sessions.list_completed_for_trends(
                patient_id,
                from_utc=from_dt,
                to_utc=to_dt,
            )

        on_values = [
            s.fog_percentage for s in sessions if s.med_state == MedicationState.ON
        ]
        off_values = [
            s.fog_percentage for s in sessions if s.med_state == MedicationState.OFF
        ]
        points = [
            TrendPointOutputDTO(
                session_id=s.session_id,
                started_at_utc=s.started_at_utc,
                med_state=s.med_state,
                fog_percentage=s.fog_percentage,
                episode_count=s.episode_count,
            )
            for s in sessions
        ]

        return PatientTrendsOutputDTO(
            patient_id=patient_id,
            total_sessions=len(sessions),
            on_med_avg_fog_pct=_avg_fog(on_values),
            off_med_avg_fog_pct=_avg_fog(off_values),
            points=points,
        )
