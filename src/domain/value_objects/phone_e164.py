import re

from src.domain.exceptions import DomainValidationError

_E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def validate_phone_e164(phone: str) -> str:
    """Validate and normalize an E.164 phone number string."""
    cleaned = phone.strip()
    if not _E164_PATTERN.match(cleaned):
        raise DomainValidationError(
            "Emergency contact phone must follow E.164 format (e.g. +6281234567890)."
        )
    return cleaned
