from uuid import UUID

from src.application.dtos import ActorContext
from src.application.interfaces import UnitOfWorkFactory
from src.application.use_cases.patients.access import (
    ensure_patient_access,
    require_sync_consent,
)
from src.domain.exceptions import EntityNotFoundError


class AuthorizeKeypointStreamUseCase:
    """Verify session ownership/grant and Consent A before opening WebSocket streaming."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, actor: ActorContext, session_id: UUID) -> None:
        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_id(session_id)
            if session is None:
                raise EntityNotFoundError(
                    f"Clinical session {session_id} was not found.",
                    error_code="SESSION_NOT_FOUND",
                )
            patient = await ensure_patient_access(uow, actor, session.patient_id)
            require_sync_consent(patient)
