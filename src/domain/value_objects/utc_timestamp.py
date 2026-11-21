from datetime import UTC, datetime

from src.domain.exceptions import DomainValidationError


def utc_now() -> datetime:
    """Return current UTC timestamp truncated to whole seconds."""
    return datetime.now(UTC).replace(microsecond=0)


def ensure_utc(dt: datetime) -> datetime:
    """Validate that a datetime is timezone-aware and normalize it to UTC."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise DomainValidationError(
            "Timestamp must be timezone-aware ISO-8601 UTC (e.g. 2026-11-20T08:45:12Z)."
        )
    return dt.astimezone(UTC)


def parse_utc_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string and enforce explicit timezone offset or 'Z'."""
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError("Timestamp string must not be empty.")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise DomainValidationError(f"Invalid ISO-8601 timestamp: {value}") from exc
    return ensure_utc(parsed)


def format_utc_z(dt: datetime) -> str:
    """Serialize a timezone-aware datetime as ISO-8601 UTC string ending in 'Z'."""
    normalized = ensure_utc(dt)
    if normalized.microsecond == 0:
        return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")
    return normalized.isoformat().replace("+00:00", "Z")
