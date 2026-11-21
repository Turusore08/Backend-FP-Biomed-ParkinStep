from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.domain.exceptions import DomainValidationError
from src.domain.value_objects.phone_e164 import validate_phone_e164
from src.domain.value_objects.utc_timestamp import ensure_utc


@dataclass(frozen=True, slots=True)
class ConsentPreferences:
    """Granular UU PDP No. 27/2022 consent toggles."""

    consent_local: bool = True
    consent_skeleton_sync: bool = False
    consent_cloud_video: bool = False
    accepted_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        if self.accepted_at_utc is not None:
            object.__setattr__(self, "accepted_at_utc", ensure_utc(self.accepted_at_utc))


@dataclass(slots=True)
class EmergencyContact:
    """Patient caregiver emergency contact."""

    contact_id: UUID
    patient_id: UUID
    name: str
    phone_e164: str
    relation: str
    is_primary: bool
    updated_at_utc: datetime

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.relation = self.relation.strip()
        if not self.name or len(self.name) > 120:
            raise DomainValidationError("Contact name must be 1..120 characters.")
        if not self.relation or len(self.relation) > 64:
            raise DomainValidationError("Contact relation must be 1..64 characters.")
        self.phone_e164 = validate_phone_e164(self.phone_e164)
        self.updated_at_utc = ensure_utc(self.updated_at_utc)


@dataclass(frozen=True, slots=True)
class ConsentAuditEvent:
    """Non-PII consent change audit event for UU PDP compliance."""

    audit_id: UUID
    patient_id: UUID
    consent_type: str
    old_value: bool | None
    new_value: bool
    changed_at_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_at_utc", ensure_utc(self.changed_at_utc))


@dataclass(slots=True)
class PatientProfile:
    """Minimum patient profile adhering to UU PDP data minimization."""

    patient_id: UUID
    user_id: UUID
    display_name: str
    birth_year: int | None
    consent: ConsentPreferences
    updated_at_utc: datetime
    emergency_contacts: list[EmergencyContact] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.display_name = self.display_name.strip()
        if not self.display_name or len(self.display_name) > 120:
            raise DomainValidationError("display_name must be 1..120 characters.")
        if self.birth_year is not None and (self.birth_year < 1900 or self.birth_year > 2026):
            raise DomainValidationError("birth_year must be within 1900..2026.")
        self.updated_at_utc = ensure_utc(self.updated_at_utc)
        self.validate_contacts(self.emergency_contacts)

    @staticmethod
    def validate_contacts(contacts: list[EmergencyContact]) -> None:
        primary_count = sum(1 for c in contacts if c.is_primary)
        if primary_count > 1:
            raise DomainValidationError("At most one emergency contact can be marked primary.")
