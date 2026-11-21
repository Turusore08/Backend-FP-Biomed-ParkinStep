from uuid import UUID

from src.application.dtos import (
    ActorContext,
    MedicationListQueryDTO,
    MedicationLogListOutputDTO,
    MedicationLogOutputDTO,
)
from src.application.interfaces import UnitOfWorkFactory
from src.application.use_cases.patients.access import ensure_patient_access
from src.domain.exceptions import DomainValidationError
from src.domain.value_objects import ensure_utc


class ListMedicationLogsUseCase:
    """List paginated Levodopa medication history for a patient."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: ActorContext,
        patient_id: UUID,
        query: MedicationListQueryDTO,
    ) -> MedicationLogListOutputDTO:
        from_utc = ensure_utc(query.from_utc) if query.from_utc is not None else None
        to_utc = ensure_utc(query.to_utc) if query.to_utc is not None else None
        if from_utc is not None and to_utc is not None and from_utc > to_utc:
            raise DomainValidationError("from_utc must be earlier than or equal to to_utc.")

        async with self._uow_factory() as uow:
            await ensure_patient_access(uow, actor, patient_id)
            items, total = await uow.medications.list_by_patient(
                patient_id,
                from_utc=from_utc,
                to_utc=to_utc,
                limit=query.limit,
                offset=query.offset,
            )
            return MedicationLogListOutputDTO(
                items=[MedicationLogOutputDTO.from_entity(item) for item in items],
                total=total,
                limit=query.limit,
                offset=query.offset,
            )
