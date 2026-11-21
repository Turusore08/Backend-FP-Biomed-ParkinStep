from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.dtos.common import UNSET, PatchField
from src.domain.entities import EmergencyContact, PatientProfile


@dataclass(frozen=True, slots=True)
class EmergencyContactInputDTO:
    contact_id: UUID | None
    name: str
    phone_e164: str
    relation: str
    is_primary: bool


@dataclass(frozen=True, slots=True)
class PatientPatchDTO:
    display_name: PatchField[str] = UNSET
    birth_year: PatchField[int | None] = UNSET
    consent_local: PatchField[bool] = UNSET
    consent_skeleton_sync: PatchField[bool] = UNSET
    consent_cloud_video: PatchField[bool] = UNSET
    emergency_contacts: PatchField[list[EmergencyContactInputDTO]] = UNSET
    client_updated_at_utc: PatchField[datetime] = UNSET


@dataclass(frozen=True, slots=True)
class PatientEraseRequestDTO:
    password: str


@dataclass(frozen=True, slots=True)
class EmergencyContactOutputDTO:
    contact_id: UUID
    name: str
    phone_e164: str
    relation: str
    is_primary: bool
    updated_at_utc: datetime

    @classmethod
    def from_entity(cls, entity: EmergencyContact) -> "EmergencyContactOutputDTO":
        return cls(
            contact_id=entity.contact_id,
            name=entity.name,
            phone_e164=entity.phone_e164,
            relation=entity.relation,
            is_primary=entity.is_primary,
            updated_at_utc=entity.updated_at_utc,
        )


@dataclass(frozen=True, slots=True)
class ConsentFlagsOutputDTO:
    consent_local: bool
    consent_skeleton_sync: bool
    consent_cloud_video: bool
    accepted_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class PatientProfileOutputDTO:
    patient_id: UUID
    user_id: UUID
    display_name: str
    birth_year: int | None
    consent: ConsentFlagsOutputDTO
    emergency_contacts: list[EmergencyContactOutputDTO]
    updated_at_utc: datetime

    @classmethod
    def from_entity(cls, entity: PatientProfile) -> "PatientProfileOutputDTO":
        return cls(
            patient_id=entity.patient_id,
            user_id=entity.user_id,
            display_name=entity.display_name,
            birth_year=entity.birth_year,
            consent=ConsentFlagsOutputDTO(
                consent_local=entity.consent.consent_local,
                consent_skeleton_sync=entity.consent.consent_skeleton_sync,
                consent_cloud_video=entity.consent.consent_cloud_video,
                accepted_at_utc=entity.consent.accepted_at_utc,
            ),
            emergency_contacts=[
                EmergencyContactOutputDTO.from_entity(c) for c in entity.emergency_contacts
            ],
            updated_at_utc=entity.updated_at_utc,
        )
