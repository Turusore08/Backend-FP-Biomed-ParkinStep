from src.application.dtos import (
    ActorContext,
    EmergencyAlertCreateDTO,
    EmergencyAlertOutputDTO,
)
from src.application.interfaces import EmergencyNotifierPort, UnitOfWorkFactory
from src.application.use_cases.patients.access import ensure_patient_access
from src.domain.entities import EmergencyAlert
from src.domain.exceptions import ConflictError, EntityNotFoundError
from src.domain.value_objects import ensure_utc, utc_now


class DispatchEmergencyAlertUseCase:
    """Persist and escalate fall or prolonged freeze (>15s) alerts to caregivers."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        notifier: EmergencyNotifierPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._notifier = notifier

    async def execute(
        self,
        actor: ActorContext,
        request: EmergencyAlertCreateDTO,
    ) -> EmergencyAlertOutputDTO:
        triggered_at = ensure_utc(request.triggered_at_utc)

        async with self._uow_factory() as uow:
            patient = await ensure_patient_access(uow, actor, request.patient_id)
            session = await uow.sessions.get_by_id(request.session_id)
            if session is None or session.patient_id != request.patient_id:
                raise EntityNotFoundError(
                    f"Clinical session {request.session_id} was not found for patient.",
                    error_code="SESSION_NOT_FOUND",
                )

            existing = await uow.alerts.get_by_id(request.alert_id)
            if existing is not None:
                raise ConflictError(
                    f"Emergency alert {request.alert_id} already exists.",
                    error_code="ALERT_ALREADY_EXISTS",
                )

            alert = EmergencyAlert(
                alert_id=request.alert_id,
                patient_id=request.patient_id,
                session_id=request.session_id,
                trigger_type=request.trigger_type,
                triggered_at_utc=triggered_at,
                cancelled_by_user=request.cancelled_by_user,
                dispatched_at_utc=None,
            )

            notified_count = 0
            if not request.cancelled_by_user:
                notified_count = await self._notifier.notify_caregivers(
                    alert,
                    patient.emergency_contacts,
                )
                alert.dispatched_at_utc = utc_now()

            await uow.alerts.create(alert)
            await uow.commit()
            return EmergencyAlertOutputDTO.from_entity(
                alert,
                notified_contacts_count=notified_count,
            )
