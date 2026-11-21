import json
import logging
import re
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "authorization",
        "access_token",
        "refresh_token",
        "phone",
        "phone_e164",
        "display_name",
        "identifier",
        "lb6_xyc",
        "frame_timestamps_ms",
    }
)

_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", re.I)
_E164_RE = re.compile(r"(?<!\w)\+[1-9]\d{6,14}(?!\w)")


def scrub_text(text: str) -> str:
    """Redact JWT Bearer tokens and E.164 phone numbers from arbitrary log text."""
    scrubbed = _BEARER_RE.sub(r"\1" + REDACTED, text)
    scrubbed = _E164_RE.sub(REDACTED, scrubbed)
    return scrubbed


def scrub_dict(obj: Any) -> Any:
    """Recursively redact sensitive keys and PII patterns from structured log data."""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for key, value in obj.items():
            key_str = str(key)
            if key_str.lower() in SENSITIVE_KEYS:
                cleaned[key_str] = REDACTED
            else:
                cleaned[key_str] = scrub_dict(value)
        return cleaned
    if isinstance(obj, list):
        return [scrub_dict(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(scrub_dict(item) for item in obj)
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj


class PiiScrubbingFilter(logging.Filter):
    """Logging filter preventing PII, credentials, or raw pose leakage to logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_text(record.msg)
        elif isinstance(record.msg, (dict, list, tuple)):
            record.msg = scrub_dict(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = scrub_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(scrub_dict(arg) for arg in record.args)

        extra_payload = getattr(record, "extra_data", None)
        if extra_payload is not None:
            record.extra_data = scrub_dict(extra_payload)
        return True


class JsonLogFormatter(logging.Formatter):
    """Minimal structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_payload = getattr(record, "extra_data", None)
        if isinstance(extra_payload, dict):
            payload["data"] = extra_payload
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with PII scrubbing filter and JSON formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(PiiScrubbingFilter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
