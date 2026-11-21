from uuid import UUID

from pydantic import Field

from src.application.dtos import MedicationLogListOutputDTO, MedicationLogOutputDTO
from src.domain.enums import MedicationState
from src.presentation.schemas.common import StrictBaseSchema, UtcDatetime


class MedicationLogCreate(StrictBaseSchema):
    log_id: UUID
    drug_name: str = Field(..., min_length=1, max_length=120)
    dosage_mg: float = Field(..., ge=0)
    taken_at_utc: UtcDatetime
    med_state: MedicationState
    notes: str | None = None


class MedicationLogResponse(StrictBaseSchema):
    log_id: UUID
    patient_id: UUID
    drug_name: str
    dosage_mg: float
    taken_at_utc: UtcDatetime
    med_state: MedicationState
    notes: str | None
    synced_at_utc: UtcDatetime

    @classmethod
    def from_dto(cls, dto: MedicationLogOutputDTO) -> "MedicationLogResponse":
        return cls(
            log_id=dto.log_id,
            patient_id=dto.patient_id,
            drug_name=dto.drug_name,
            dosage_mg=dto.dosage_mg,
            taken_at_utc=dto.taken_at_utc,
            med_state=dto.med_state,
            notes=dto.notes,
            synced_at_utc=dto.synced_at_utc,
        )


class MedicationLogListResponse(StrictBaseSchema):
    items: list[MedicationLogResponse]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_dto(cls, dto: MedicationLogListOutputDTO) -> "MedicationLogListResponse":
        return cls(
            items=[MedicationLogResponse.from_dto(item) for item in dto.items],
            total=dto.total,
            limit=dto.limit,
            offset=dto.offset,
        )
