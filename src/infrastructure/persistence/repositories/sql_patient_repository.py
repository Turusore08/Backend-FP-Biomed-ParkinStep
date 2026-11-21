from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import (
    ConsentAuditEvent,
    ConsentPreferences,
    EmergencyContact,
    PatientProfile,
)
from src.infrastructure.persistence.models import (
    ConsentAuditLogORM,
    EmergencyContactORM,
    PatientAccessGrantORM,
    PatientORM,
    UserORM,
)


def _to_contact_entity(row: EmergencyContactORM) -> EmergencyContact:
    return EmergencyContact(
        contact_id=row.contact_id,
        patient_id=row.patient_id,
        name=row.name,
        phone_e164=row.phone_e164,
        relation=row.relation,
        is_primary=row.is_primary,
        updated_at_utc=row.updated_at_utc,
    )


class SqlPatientRepository:
    """SQLAlchemy async repository for PatientProfile, contacts, grants, and consent logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, patient_id: UUID) -> PatientProfile | None:
        row = await self._session.get(PatientORM, patient_id)
        if row is None:
            return None

        contacts_stmt = (
            select(EmergencyContactORM)
            .where(EmergencyContactORM.patient_id == patient_id)
            .order_by(EmergencyContactORM.is_primary.desc(), EmergencyContactORM.updated_at_utc)
        )
        contacts_result = await self._session.execute(contacts_stmt)
        contacts = [_to_contact_entity(c) for c in contacts_result.scalars().all()]

        return PatientProfile(
            patient_id=row.patient_id,
            user_id=row.user_id,
            display_name=row.display_name,
            birth_year=row.birth_year,
            consent=ConsentPreferences(
                consent_local=row.consent_local,
                consent_skeleton_sync=row.consent_skeleton_sync,
                consent_cloud_video=row.consent_cloud_video,
                accepted_at_utc=row.consent_updated_at_utc,
            ),
            updated_at_utc=row.updated_at_utc,
            emergency_contacts=contacts,
        )

    async def create(self, patient: PatientProfile) -> None:
        self._session.add(
            PatientORM(
                patient_id=patient.patient_id,
                user_id=patient.user_id,
                display_name=patient.display_name,
                birth_year=patient.birth_year,
                consent_local=patient.consent.consent_local,
                consent_skeleton_sync=patient.consent.consent_skeleton_sync,
                consent_cloud_video=patient.consent.consent_cloud_video,
                consent_updated_at_utc=patient.consent.accepted_at_utc,
                updated_at_utc=patient.updated_at_utc,
            )
        )
        await self._session.flush()

    async def update(self, patient: PatientProfile) -> None:
        stmt = (
            update(PatientORM)
            .where(PatientORM.patient_id == patient.patient_id)
            .values(
                display_name=patient.display_name,
                birth_year=patient.birth_year,
                consent_local=patient.consent.consent_local,
                consent_skeleton_sync=patient.consent.consent_skeleton_sync,
                consent_cloud_video=patient.consent.consent_cloud_video,
                consent_updated_at_utc=patient.consent.accepted_at_utc,
                updated_at_utc=patient.updated_at_utc,
            )
        )
        await self._session.execute(stmt)

    async def replace_emergency_contacts(
        self,
        patient_id: UUID,
        contacts: list[EmergencyContact],
    ) -> None:
        await self._session.execute(
            delete(EmergencyContactORM).where(EmergencyContactORM.patient_id == patient_id)
        )
        for contact in contacts:
            self._session.add(
                EmergencyContactORM(
                    contact_id=contact.contact_id,
                    patient_id=contact.patient_id,
                    name=contact.name,
                    phone_e164=contact.phone_e164,
                    relation=contact.relation,
                    is_primary=contact.is_primary,
                    updated_at_utc=contact.updated_at_utc,
                )
            )
        await self._session.flush()

    async def add_consent_audit_events(self, events: list[ConsentAuditEvent]) -> None:
        for event in events:
            self._session.add(
                ConsentAuditLogORM(
                    audit_id=event.audit_id,
                    patient_id=event.patient_id,
                    consent_type=event.consent_type,
                    old_value=event.old_value,
                    new_value=event.new_value,
                    changed_at_utc=event.changed_at_utc,
                )
            )
        await self._session.flush()

    async def has_access_grant(self, patient_id: UUID, grantee_user_id: UUID) -> bool:
        stmt = select(PatientAccessGrantORM.grant_id).where(
            PatientAccessGrantORM.patient_id == patient_id,
            PatientAccessGrantORM.grantee_user_id == grantee_user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def hard_delete_patient_and_user(self, patient_id: UUID, user_id: UUID) -> None:
        # Delete patient explicitly first (cascades clinical tables), then remove user account.
        await self._session.execute(
            delete(PatientORM).where(PatientORM.patient_id == patient_id)
        )
        await self._session.execute(delete(UserORM).where(UserORM.user_id == user_id))
