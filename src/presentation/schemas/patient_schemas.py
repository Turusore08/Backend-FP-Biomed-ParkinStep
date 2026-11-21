from uuid import UUID

from pydantic import Field

from src.application.dtos import (
    UNSET,
    EmergencyContactInputDTO,
    PatchField,
    PatientPatchDTO,
    PatientProfileOutputDTO,
)
from src.domain.exceptions import DomainValidationError
from src.presentation.schemas.common import StrictBaseSchema, UtcDatetime


class EmergencyContactSchema(StrictBaseSchema):
    contact_id: UUID
    name: str
    phone_e164: str
    relation: str
    is_primary: bool
    updated_at_utc: UtcDatetime


class EmergencyContactUpsertSchema(StrictBaseSchema):
    contact_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=120)
    phone_e164: str = Field(..., min_length=8, max_length=20)
    relation: str = Field(..., min_length=1, max_length=64)
    is_primary: bool = False


class ConsentFlagsSchema(StrictBaseSchema):
    consent_local: bool
    consent_skeleton_sync: bool
    consent_cloud_video: bool
    accepted_at_utc: UtcDatetime | None


class PatientProfileResponse(StrictBaseSchema):
    patient_id: UUID
    user_id: UUID
    display_name: str
    birth_year: int | None
    consent: ConsentFlagsSchema
    emergency_contacts: list[EmergencyContactSchema]
    updated_at_utc: UtcDatetime

    @classmethod
    def from_dto(cls, dto: PatientProfileOutputDTO) -> "PatientProfileResponse":
        return cls(
            patient_id=dto.patient_id,
            user_id=dto.user_id,
            display_name=dto.display_name,
            birth_year=dto.birth_year,
            consent=ConsentFlagsSchema(
                consent_local=dto.consent.consent_local,
                consent_skeleton_sync=dto.consent.consent_skeleton_sync,
                consent_cloud_video=dto.consent.consent_cloud_video,
                accepted_at_utc=dto.consent.accepted_at_utc,
            ),
            emergency_contacts=[
                EmergencyContactSchema(
                    contact_id=c.contact_id,
                    name=c.name,
                    phone_e164=c.phone_e164,
                    relation=c.relation,
                    is_primary=c.is_primary,
                    updated_at_utc=c.updated_at_utc,
                )
                for c in dto.emergency_contacts
            ],
            updated_at_utc=dto.updated_at_utc,
        )


class PatientPatchRequest(StrictBaseSchema):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    birth_year: int | None = Field(default=None, ge=1900, le=2026)
    consent_local: bool | None = None
    consent_skeleton_sync: bool | None = None
    consent_cloud_video: bool | None = None
    emergency_contacts: list[EmergencyContactUpsertSchema] | None = None
    updated_at_utc: UtcDatetime | None = None

    def _non_nullable_patch_field[T](self, field_name: str, value: T | None) -> PatchField[T]:
        if field_name not in self.model_fields_set:
            return UNSET
        if value is None:
            raise DomainValidationError(
                f"Field '{field_name}' is not nullable and cannot be set to null."
            )
        return value

    def to_dto(self) -> PatientPatchDTO:
        birth_year_field: PatchField[int | None] = (
            self.birth_year if "birth_year" in self.model_fields_set else UNSET
        )
        contacts_field: PatchField[list[EmergencyContactInputDTO]]
        if "emergency_contacts" not in self.model_fields_set:
            contacts_field = UNSET
        elif self.emergency_contacts is None:
            raise DomainValidationError(
                "Field 'emergency_contacts' is not nullable and cannot be set to null."
            )
        else:
            contacts_field = [
                EmergencyContactInputDTO(
                    contact_id=item.contact_id,
                    name=item.name,
                    phone_e164=item.phone_e164,
                    relation=item.relation,
                    is_primary=item.is_primary,
                )
                for item in self.emergency_contacts
            ]

        return PatientPatchDTO(
            display_name=self._non_nullable_patch_field("display_name", self.display_name),
            birth_year=birth_year_field,
            consent_local=self._non_nullable_patch_field("consent_local", self.consent_local),
            consent_skeleton_sync=self._non_nullable_patch_field(
                "consent_skeleton_sync",
                self.consent_skeleton_sync,
            ),
            consent_cloud_video=self._non_nullable_patch_field(
                "consent_cloud_video",
                self.consent_cloud_video,
            ),
            emergency_contacts=contacts_field,
            client_updated_at_utc=self._non_nullable_patch_field(
                "updated_at_utc",
                self.updated_at_utc,
            ),
        )


class PatientEraseRequest(StrictBaseSchema):
    password: str = Field(..., min_length=1, max_length=128)
