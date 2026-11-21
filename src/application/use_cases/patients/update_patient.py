from uuid import UUID, uuid4

from src.application.dtos.common import ActorContext, UnsetType
from src.application.dtos.patient_dtos import PatientPatchDTO, PatientProfileOutputDTO
from src.application.interfaces.repositories import UnitOfWorkFactory
from src.application.use_cases.patients.access import ensure_patient_access
from src.domain.entities import (
    ConsentAuditEvent,
    ConsentPreferences,
    EmergencyContact,
    PatientProfile,
)
from src.domain.exceptions import AuthorizationDeniedError, StaleWriteConflictError
from src.domain.value_objects import ensure_utc, utc_now


class UpdatePatientUseCase:
    """Update patient profile, emergency contacts, and UU PDP granular consent flags."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: ActorContext,
        patient_id: UUID,
        patch: PatientPatchDTO,
    ) -> PatientProfileOutputDTO:
        now = utc_now()
        async with self._uow_factory() as uow:
            patient = await ensure_patient_access(uow, actor, patient_id, require_owner=False)

            consent_fields_touched = not (
                isinstance(patch.consent_local, UnsetType)
                and isinstance(patch.consent_skeleton_sync, UnsetType)
                and isinstance(patch.consent_cloud_video, UnsetType)
            )
            if consent_fields_touched and actor.user_id != patient.user_id:
                raise AuthorizationDeniedError(
                    "Only the patient owner may grant or revoke UU PDP consent flags."
                )

            if not isinstance(patch.client_updated_at_utc, UnsetType):
                client_ts = ensure_utc(patch.client_updated_at_utc)
                if client_ts < patient.updated_at_utc:
                    raise StaleWriteConflictError(
                        "Client update timestamp precedes latest server profile update."
                    )

            new_display_name = (
                patient.display_name
                if isinstance(patch.display_name, UnsetType)
                else patch.display_name
            )
            new_birth_year = (
                patient.birth_year
                if isinstance(patch.birth_year, UnsetType)
                else patch.birth_year
            )

            old_consent = patient.consent
            new_local = (
                old_consent.consent_local
                if isinstance(patch.consent_local, UnsetType)
                else patch.consent_local
            )
            new_sync = (
                old_consent.consent_skeleton_sync
                if isinstance(patch.consent_skeleton_sync, UnsetType)
                else patch.consent_skeleton_sync
            )
            new_video = (
                old_consent.consent_cloud_video
                if isinstance(patch.consent_cloud_video, UnsetType)
                else patch.consent_cloud_video
            )

            audit_events: list[ConsentAuditEvent] = []
            for flag_name, old_val, new_val in (
                ("consent_local", old_consent.consent_local, new_local),
                ("consent_skeleton_sync", old_consent.consent_skeleton_sync, new_sync),
                ("consent_cloud_video", old_consent.consent_cloud_video, new_video),
            ):
                if old_val != new_val:
                    audit_events.append(
                        ConsentAuditEvent(
                            audit_id=uuid4(),
                            patient_id=patient.patient_id,
                            consent_type=flag_name,
                            old_value=old_val,
                            new_value=new_val,
                            changed_at_utc=now,
                        )
                    )

            accepted_at = now if audit_events else old_consent.accepted_at_utc
            new_consent = ConsentPreferences(
                consent_local=new_local,
                consent_skeleton_sync=new_sync,
                consent_cloud_video=new_video,
                accepted_at_utc=accepted_at,
            )

            contacts_updated = not isinstance(patch.emergency_contacts, UnsetType)
            if isinstance(patch.emergency_contacts, UnsetType):
                new_contacts = patient.emergency_contacts
            else:
                new_contacts = [
                    EmergencyContact(
                        contact_id=c.contact_id or uuid4(),
                        patient_id=patient.patient_id,
                        name=c.name,
                        phone_e164=c.phone_e164,
                        relation=c.relation,
                        is_primary=c.is_primary,
                        updated_at_utc=now,
                    )
                    for c in patch.emergency_contacts
                ]

            updated_patient = PatientProfile(
                patient_id=patient.patient_id,
                user_id=patient.user_id,
                display_name=new_display_name,
                birth_year=new_birth_year,
                consent=new_consent,
                updated_at_utc=now,
                emergency_contacts=new_contacts,
            )

            await uow.patients.update(updated_patient)
            if contacts_updated:
                await uow.patients.replace_emergency_contacts(
                    updated_patient.patient_id,
                    updated_patient.emergency_contacts,
                )
            if audit_events:
                await uow.patients.add_consent_audit_events(audit_events)

            await uow.commit()
            return PatientProfileOutputDTO.from_entity(updated_patient)
