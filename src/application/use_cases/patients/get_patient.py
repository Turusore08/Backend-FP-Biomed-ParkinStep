from uuid import UUID

from src.application.dtos.common import ActorContext
from src.application.dtos.patient_dtos import PatientProfileOutputDTO
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.use_cases.patients.access import ensure_patient_access


class GetPatientUseCase:
    """Fetch patient profile, emergency contacts, and UU PDP consent flags."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, actor: ActorContext, patient_id: UUID) -> PatientProfileOutputDTO:
        async with self._uow_factory() as uow:
            patient = await ensure_patient_access(uow, actor, patient_id)
            return PatientProfileOutputDTO.from_entity(patient)
