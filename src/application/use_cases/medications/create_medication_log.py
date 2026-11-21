from src.application.dtos import (
    ActorContext,
    MedicationLogCreateDTO,
    MedicationLogOutputDTO,
)
from src.application.interfaces import UnitOfWorkFactory
from src.application.use_cases.patients.access import (
    ensure_patient_access,
    require_sync_consent,
)
from src.domain.entities import MedicationLog
from src.domain.exceptions import ConflictError, DomainValidationError
from src.domain.value_objects import ensure_utc, utc_now


class CreateMedicationLogUseCase:
    """Persist a client-created Levodopa medication log entry."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: ActorContext,
        request: MedicationLogCreateDTO,
    ) -> MedicationLogOutputDTO:
        drug_name = request.drug_name.strip()
        if not drug_name or len(drug_name) > 120:
            raise DomainValidationError("drug_name must be between 1 and 120 characters.")
        if request.dosage_mg < 0.0:
            raise DomainValidationError("dosage_mg must be >= 0.")

        taken_at = ensure_utc(request.taken_at_utc)
        now = utc_now()

        async with self._uow_factory() as uow:
            patient = await ensure_patient_access(uow, actor, request.patient_id)
            require_sync_consent(patient)

            existing = await uow.medications.get_by_id(request.log_id)
            if existing is not None:
                raise ConflictError(
                    f"Medication log {request.log_id} already exists.",
                    error_code="MEDICATION_LOG_EXISTS",
                )

            log = MedicationLog(
                log_id=request.log_id,
                patient_id=request.patient_id,
                drug_name=drug_name,
                dosage_mg=request.dosage_mg,
                taken_at_utc=taken_at,
                med_state=request.med_state,
                notes=request.notes,
                synced_at_utc=now,
            )
            await uow.medications.create(log)
            await uow.commit()
            return MedicationLogOutputDTO.from_entity(log)
