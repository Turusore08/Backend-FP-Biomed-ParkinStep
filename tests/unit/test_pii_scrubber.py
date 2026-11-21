import logging

from src.infrastructure.logging.pii_scrubber import (
    REDACTED,
    JsonLogFormatter,
    PiiScrubbingFilter,
    scrub_dict,
    scrub_text,
)


def test_scrub_text_redacts_bearer_and_e164_phone() -> None:
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig phone=+6281234567890"
    cleaned = scrub_text(raw)
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "+6281234567890" not in cleaned
    assert cleaned.count(REDACTED) == 2


def test_scrub_dict_redacts_nested_sensitive_keys() -> None:
    payload = {
        "session_id": "abc-123",
        "password": "my-secret-password",
        "nested": {
            "display_name": "Siti Aminah",
            "phone_e164": "+628111222333",
            "lb6_xyc": [[[100.0, 200.0, 0.9]]],
        },
        "items": [{"refresh_token": "tok123", "ok": True}],
    }
    cleaned = scrub_dict(payload)
    assert cleaned["session_id"] == "abc-123"
    assert cleaned["password"] == REDACTED
    assert cleaned["nested"]["display_name"] == REDACTED
    assert cleaned["nested"]["phone_e164"] == REDACTED
    assert cleaned["nested"]["lb6_xyc"] == REDACTED
    assert cleaned["items"][0]["refresh_token"] == REDACTED
    assert cleaned["items"][0]["ok"] is True


def test_pii_filter_and_json_formatter_strip_secrets() -> None:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Failed login for +6281299988877 with Bearer header.payload.sig",
        args=(),
        exc_info=None,
    )
    record.extra_data = {"password": "raw-password", "status": "denied"}

    log_filter = PiiScrubbingFilter()
    assert log_filter.filter(record) is True

    formatted = JsonLogFormatter().format(record)
    assert "+6281299988877" not in formatted
    assert "header.payload.sig" not in formatted
    assert "raw-password" not in formatted
    assert "denied" in formatted
