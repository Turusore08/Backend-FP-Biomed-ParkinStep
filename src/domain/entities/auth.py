from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.enums.clinical_enums import UserRole
from src.domain.exceptions import DomainValidationError
from src.domain.value_objects.utc_timestamp import ensure_utc


@dataclass(slots=True)
class UserAccount:
    """Authenticated user account (patient, caregiver, or clinician)."""

    user_id: UUID
    identifier: str
    password_hash: str
    role: UserRole
    is_active: bool
    created_at_utc: datetime

    def __post_init__(self) -> None:
        normalized = self.identifier.strip().lower()
        if not normalized or len(normalized) > 160:
            raise DomainValidationError("User identifier must be between 1 and 160 characters.")
        self.identifier = normalized
        if not self.password_hash:
            raise DomainValidationError("Password hash must not be empty.")
        self.created_at_utc = ensure_utc(self.created_at_utc)


@dataclass(slots=True)
class RefreshTokenRecord:
    """Hashed refresh token belonging to a rotation family for replay detection."""

    token_id: UUID
    user_id: UUID
    device_id: str
    token_hash: str
    family_id: UUID
    expires_at_utc: datetime
    revoked_at_utc: datetime | None
    created_at_utc: datetime

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise DomainValidationError("device_id must not be empty.")
        self.device_id = self.device_id.strip()
        self.expires_at_utc = ensure_utc(self.expires_at_utc)
        self.created_at_utc = ensure_utc(self.created_at_utc)
        if self.revoked_at_utc is not None:
            self.revoked_at_utc = ensure_utc(self.revoked_at_utc)

    def is_active_at(self, now: datetime) -> bool:
        """Return True iff the token is neither revoked nor expired at `now`."""
        now_utc = ensure_utc(now)
        return self.revoked_at_utc is None and self.expires_at_utc > now_utc
