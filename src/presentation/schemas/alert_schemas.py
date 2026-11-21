from uuid import UUID

from src.application.dtos import EmergencyAlertOutputDTO
from src.domain.enums import EmergencyTrigger
from src.presentation.schemas.common import StrictBaseSchema, UtcDatetime


class EmergencyAlertRequest(StrictBaseSchema):
    alert_id: UUID
    patient_id: UUID
    session_id: UUID
    trigger_type: EmergencyTrigger
    triggered_at_utc: UtcDatetime
    cancelled_by_user: bool


class EmergencyAlertResponse(StrictBaseSchema):
    alert_id: UUID
    patient_id: UUID
    session_id: UUID
    trigger_type: EmergencyTrigger
    triggered_at_utc: UtcDatetime
    cancelled_by_user: bool
    dispatched_at_utc: UtcDatetime | None
    notified_contacts_count: int

    @classmethod
    def from_dto(cls, dto: EmergencyAlertOutputDTO) -> "EmergencyAlertResponse":
        return cls(
            alert_id=dto.alert_id,
            patient_id=dto.patient_id,
            session_id=dto.session_id,
            trigger_type=dto.trigger_type,
            triggered_at_utc=dto.triggered_at_utc,
            cancelled_by_user=dto.cancelled_by_user,
            dispatched_at_utc=dto.dispatched_at_utc,
            notified_contacts_count=dto.notified_contacts_count,
        )
