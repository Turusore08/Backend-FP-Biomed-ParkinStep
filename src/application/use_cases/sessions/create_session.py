from src.application.dtos import (
    ActorContext,
    SessionCreateDTO,
    SessionSummaryOutputDTO,
)
from src.application.interfaces import UnitOfWorkFactory
from src.application.use_cases.patients.access import (
    ensure_patient_access,
    require_sync_consent,
)
from src.domain.entities import ClinicalSession
from src.domain.exceptions import (
    ConflictError,
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.value_objects import ensure_utc, utc_now


class CreateSessionUseCase:
    """Register a screening session created offline-first on the mobile client."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: ActorContext,
        request: SessionCreateDTO,
    ) -> SessionSummaryOutputDTO:
        if request.target_fps not in (15, 30):
            raise DomainValidationError("target_fps must be 15 or 30.")
        bundle_version = request.model_bundle_version.strip()
        if not bundle_version or len(bundle_version) > 64:
            raise DomainValidationError("model_bundle_version must be 1..64 characters.")

        started_at = ensure_utc(request.started_at_utc)
        now = utc_now()

        async with self._uow_factory() as uow:
            patient = await ensure_patient_access(uow, actor, request.patient_id)
            require_sync_consent(patient)

            existing = await uow.sessions.get_by_id(request.session_id)
            if existing is not None:
                raise ConflictError(
                    f"Clinical session {request.session_id} already exists.",
                    error_code="SESSION_ALREADY_EXISTS",
                )

            if request.last_medication_log_id is not None:
                med_log = await uow.medications.get_by_id(request.last_medication_log_id)
                if med_log is None or med_log.patient_id != request.patient_id:
                    raise EntityNotFoundError(
                        f"Medication log {request.last_medication_log_id} was not found "
                        "for patient.",
                        error_code="MEDICATION_LOG_NOT_FOUND",
                    )

            session = ClinicalSession(
                session_id=request.session_id,
                patient_id=request.patient_id,
                last_medication_log_id=request.last_medication_log_id,
                protocol=request.protocol,
                inference_mode=request.inference_mode,
                med_state=request.med_state,
                target_fps=request.target_fps,
                model_bundle_version=bundle_version,
                started_at_utc=started_at,
                safety_checklist_confirmed=request.safety_checklist_confirmed,
                created_at_utc=now,
            )
            await uow.sessions.create(session)
            await uow.commit()
            return SessionSummaryOutputDTO.from_entity(session)
