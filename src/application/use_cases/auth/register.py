from uuid import uuid4

from src.application.dtos.auth_dtos import AuthTokenResponseDTO, RegisterRequestDTO
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.interfaces.security_ports import PasswordHasherPort, TokenProviderPort
from src.application.use_cases.auth.token_helper import issue_token_pair
from src.domain.entities import (
    ConsentAuditEvent,
    ConsentPreferences,
    PatientProfile,
    UserAccount,
)
from src.domain.enums import UserRole
from src.domain.exceptions import ConflictError, DomainValidationError
from src.domain.value_objects import utc_now


class RegisterUseCase:
    """Register a new user account and initialize patient UU PDP consent if role is PATIENT."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
        token_provider: TokenProviderPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._token_provider = token_provider

    async def execute(self, request: RegisterRequestDTO) -> AuthTokenResponseDTO:
        normalized_identifier = request.identifier.strip().lower()
        if not normalized_identifier:
            raise DomainValidationError("identifier must not be empty.")
        if len(request.password) < 8:
            raise DomainValidationError("password must be at least 8 characters long.")
        if not request.device_id.strip():
            raise DomainValidationError("device_id must not be empty.")
        if request.role == UserRole.PATIENT and not request.consent_local:
            raise DomainValidationError(
                "Mandatory local processing consent (consent_local) must be accepted."
            )

        now = utc_now()
        user_id = uuid4()
        password_hash = self._password_hasher.hash(request.password)
        user = UserAccount(
            user_id=user_id,
            identifier=normalized_identifier,
            password_hash=password_hash,
            role=request.role,
            is_active=True,
            created_at_utc=now,
        )

        async with self._uow_factory() as uow:
            existing = await uow.users.get_by_identifier(user.identifier)
            if existing is not None:
                raise ConflictError(
                    "Account identifier is already registered.",
                    error_code="AUTH_IDENTIFIER_EXISTS",
                )

            await uow.users.create(user)

            if request.role == UserRole.PATIENT:
                fallback_name = normalized_identifier.split("@")[0] or "Pengguna"
                display_name = (request.display_name or fallback_name).strip()[:120]
                consent = ConsentPreferences(
                    consent_local=request.consent_local,
                    consent_skeleton_sync=request.consent_skeleton_sync,
                    consent_cloud_video=request.consent_cloud_video,
                    accepted_at_utc=now,
                )
                patient = PatientProfile(
                    patient_id=user_id,
                    user_id=user_id,
                    display_name=display_name,
                    birth_year=request.birth_year,
                    consent=consent,
                    updated_at_utc=now,
                    emergency_contacts=[],
                )
                await uow.patients.create(patient)

                audit_events = [
                    ConsentAuditEvent(
                        audit_id=uuid4(),
                        patient_id=patient.patient_id,
                        consent_type=flag_name,
                        old_value=None,
                        new_value=flag_val,
                        changed_at_utc=now,
                    )
                    for flag_name, flag_val in (
                        ("consent_local", consent.consent_local),
                        ("consent_skeleton_sync", consent.consent_skeleton_sync),
                        ("consent_cloud_video", consent.consent_cloud_video),
                    )
                ]
                await uow.patients.add_consent_audit_events(audit_events)

            tokens = await issue_token_pair(
                uow,
                self._token_provider,
                user,
                request.device_id.strip(),
                now=now,
            )
            await uow.commit()
            return tokens
