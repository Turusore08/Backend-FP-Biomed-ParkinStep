from uuid import UUID

from src.application.dtos import PatientTrendsOutputDTO, TrendPointOutputDTO
from src.domain.enums import MedicationState
from src.presentation.schemas.common import StrictBaseSchema, UtcDatetime


class TrendPointSchema(StrictBaseSchema):
    session_id: UUID
    started_at_utc: UtcDatetime
    med_state: MedicationState
    fog_percentage: float
    episode_count: int

    @classmethod
    def from_dto(cls, dto: TrendPointOutputDTO) -> "TrendPointSchema":
        return cls(
            session_id=dto.session_id,
            started_at_utc=dto.started_at_utc,
            med_state=dto.med_state,
            fog_percentage=dto.fog_percentage,
            episode_count=dto.episode_count,
        )


class PatientTrendsResponse(StrictBaseSchema):
    patient_id: UUID
    total_sessions: int
    on_med_avg_fog_pct: float | None
    off_med_avg_fog_pct: float | None
    points: list[TrendPointSchema]

    @classmethod
    def from_dto(cls, dto: PatientTrendsOutputDTO) -> "PatientTrendsResponse":
        return cls(
            patient_id=dto.patient_id,
            total_sessions=dto.total_sessions,
            on_med_avg_fog_pct=dto.on_med_avg_fog_pct,
            off_med_avg_fog_pct=dto.off_med_avg_fog_pct,
            points=[TrendPointSchema.from_dto(p) for p in dto.points],
        )
