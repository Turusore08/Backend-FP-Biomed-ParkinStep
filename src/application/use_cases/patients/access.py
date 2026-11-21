from uuid import UUID

from src.application.dtos.common import ActorContext
from src.application.interfaces.repositories import UnitOfWork
from src.domain.entities import PatientProfile
from src.domain.enums import UserRole
from src.domain.exceptions import (
    AuthorizationDeniedError,
    ConsentRevokedError,
    EntityNotFoundError,
)


async def ensure_patient_access(
    uow: UnitOfWork,
    actor: ActorContext,
    patient_id: UUID,
    *,
    require_owner: bool = False,
) -> PatientProfile:
    """Enforce ownership or explicit caregiver/clinician grant (anti-IDOR/BOLA)."""
    patient = await uow.patients.get_by_id(patient_id)
    if patient is None:
        raise EntityNotFoundError(f"Patient {patient_id} was not found.")

    if actor.user_id == patient.user_id:
        return patient

    if require_owner:
        raise AuthorizationDeniedError(
            "Only the patient account owner is permitted to perform this operation."
        )

    if actor.role in (UserRole.CAREGIVER, UserRole.CLINICIAN):
        granted = await uow.patients.has_access_grant(patient_id, actor.user_id)
        if granted:
            return patient

    raise AuthorizationDeniedError("You do not have permission to access this patient record.")


def require_sync_consent(patient: PatientProfile) -> None:
    """Enforce UU PDP Consent A before uploading telemetry or session results."""
    if not patient.consent.consent_skeleton_sync:
        raise ConsentRevokedError(
            "Cloud telemedicine sync consent (consent_skeleton_sync) is disabled.",
            error_code="CONSENT_SYNC_REQUIRED",
        )


def require_cloud_video_consent(patient: PatientProfile) -> None:
    """Enforce UU PDP Consent B before accepting opt-in cloud video fallback."""
    if not patient.consent.consent_cloud_video:
        raise ConsentRevokedError(
            "Cloud fallback video analysis consent (consent_cloud_video) is disabled.",
            error_code="CONSENT_CLOUD_VIDEO_REQUIRED",
        )
