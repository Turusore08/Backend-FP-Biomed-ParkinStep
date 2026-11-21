from uuid import UUID

from src.application.dtos.common import ActorContext
from src.application.dtos.patient_dtos import PatientEraseRequestDTO
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.interfaces.security_ports import PasswordHasherPort
from src.application.use_cases.patients.access import ensure_patient_access
from src.domain.exceptions import ReauthRequiredError


class ErasePatientDataUseCase:
    """Execute UU PDP Right to Erasure after explicit password re-authentication."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher

    async def execute(
        self,
        actor: ActorContext,
        patient_id: UUID,
        request: PatientEraseRequestDTO,
    ) -> None:
        async with self._uow_factory() as uow:
            patient = await ensure_patient_access(uow, actor, patient_id, require_owner=True)
            user = await uow.users.get_by_id(patient.user_id)
            if user is None or not self._password_hasher.verify(
                request.password,
                user.password_hash,
            ):
                raise ReauthRequiredError(
                    "Password re-authentication failed. Cloud data erasure aborted."
                )

            await uow.idempotency.purge_for_actor(patient.user_id)
            await uow.refresh_tokens.delete_all_for_user(patient.user_id)
            await uow.patients.hard_delete_patient_and_user(patient.patient_id, patient.user_id)
            await uow.commit()
