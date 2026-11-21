from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    WithJsonSchema,
)

from src.domain.exceptions import DomainValidationError
from src.domain.value_objects import format_utc_z, parse_utc_iso


def _validate_utc_datetime(value: Any) -> datetime:
    if isinstance(value, (bool, int, float)):
        raise ValueError("Timestamp must be an ISO-8601 UTC string ending in 'Z'.")
    if isinstance(value, str):
        try:
            return parse_utc_iso(value)
        except DomainValidationError as exc:
            raise ValueError(exc.detail) from exc
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Timestamp must be timezone-aware ISO-8601 UTC (e.g. 2026-11-20T08:45:12Z)."
            )
        return value.astimezone(UTC)
    raise ValueError("Timestamp must be a timezone-aware ISO-8601 UTC datetime.")


def _serialize_utc_datetime(value: datetime) -> str:
    return format_utc_z(value)


UtcDatetime = Annotated[
    datetime,
    BeforeValidator(_validate_utc_datetime),
    PlainSerializer(_serialize_utc_datetime, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


class StrictBaseSchema(BaseModel):
    """Base Pydantic V2 schema forbidding undeclared fields to prevent API drift."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ProblemDetailsSchema(BaseModel):
    """RFC 7807 Problem Details error payload."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    error_code: str
    errors: list[dict[str, Any]] | None = None
