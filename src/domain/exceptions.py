PROBLEM_BASE_URI = "https://parkinstep.example.org/problems"


class DomainError(Exception):
    """Base domain exception mapped cleanly to RFC 7807 Problem Details."""

    default_status_code: int = 400
    default_title: str = "Domain Error"
    default_error_code: str = "DOMAIN_ERROR"
    default_problem_slug: str = "domain-error"

    def __init__(
        self,
        detail: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        title: str | None = None,
        problem_slug: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = error_code or self.default_error_code
        self.status_code = status_code if status_code is not None else self.default_status_code
        self.title = title or self.default_title
        self.problem_slug = problem_slug or self.default_problem_slug

    @property
    def problem_type(self) -> str:
        return f"{PROBLEM_BASE_URI}/{self.problem_slug}"


class DomainValidationError(DomainError):
    default_status_code = 422
    default_title = "Validation Error"
    default_error_code = "VALIDATION_ERROR"
    default_problem_slug = "validation-error"


class InvalidCredentialsError(DomainError):
    default_status_code = 401
    default_title = "Invalid Credentials"
    default_error_code = "AUTH_INVALID_CREDENTIALS"
    default_problem_slug = "invalid-credentials"


class TokenExpiredError(DomainError):
    default_status_code = 401
    default_title = "Token Expired"
    default_error_code = "AUTH_TOKEN_EXPIRED"
    default_problem_slug = "token-expired"


class TokenInvalidError(DomainError):
    default_status_code = 401
    default_title = "Invalid Token"
    default_error_code = "AUTH_TOKEN_INVALID"
    default_problem_slug = "token-invalid"


class TokenReuseDetectedError(DomainError):
    default_status_code = 401
    default_title = "Refresh Token Reuse Detected"
    default_error_code = "AUTH_TOKEN_REUSE_DETECTED"
    default_problem_slug = "token-reuse-detected"


class ReauthRequiredError(DomainError):
    default_status_code = 401
    default_title = "Re-authentication Failed"
    default_error_code = "AUTH_REAUTH_FAILED"
    default_problem_slug = "reauth-failed"


class RateLimitExceededError(DomainError):
    default_status_code = 429
    default_title = "Too Many Requests"
    default_error_code = "RATE_LIMIT_EXCEEDED"
    default_problem_slug = "rate-limit-exceeded"

    def __init__(
        self,
        detail: str = "Too many authentication attempts. Please retry later.",
        *,
        retry_after_sec: int,
    ) -> None:
        super().__init__(detail)
        self.retry_after_sec = max(1, retry_after_sec)


class AuthorizationDeniedError(DomainError):
    default_status_code = 403
    default_title = "Access Denied"
    default_error_code = "ACCESS_DENIED"
    default_problem_slug = "access-denied"


class ConsentRevokedError(DomainError):
    default_status_code = 403
    default_title = "Consent Required"
    default_error_code = "CONSENT_SYNC_REQUIRED"
    default_problem_slug = "consent-required"


class EntityNotFoundError(DomainError):
    default_status_code = 404
    default_title = "Resource Not Found"
    default_error_code = "RESOURCE_NOT_FOUND"
    default_problem_slug = "resource-not-found"


class ConflictError(DomainError):
    default_status_code = 409
    default_title = "Resource Conflict"
    default_error_code = "RESOURCE_CONFLICT"
    default_problem_slug = "resource-conflict"


class StaleWriteConflictError(DomainError):
    default_status_code = 409
    default_title = "Stale Write Conflict"
    default_error_code = "STALE_WRITE_CONFLICT"
    default_problem_slug = "stale-write-conflict"


class IdempotencyKeyMissingError(DomainError):
    default_status_code = 400
    default_title = "Missing Idempotency-Key Header"
    default_error_code = "IDEMPOTENCY_KEY_REQUIRED"
    default_problem_slug = "idempotency-key-required"


class IdempotencyKeyInvalidError(DomainError):
    default_status_code = 400
    default_title = "Invalid Idempotency-Key Header"
    default_error_code = "IDEMPOTENCY_KEY_INVALID"
    default_problem_slug = "idempotency-key-invalid"


class IdempotencyPayloadMismatchError(DomainError):
    default_status_code = 409
    default_title = "Idempotency-Key Payload Mismatch"
    default_error_code = "IDEMPOTENCY_PAYLOAD_MISMATCH"
    default_problem_slug = "idempotency-payload-mismatch"


class IdempotencyInProgressError(DomainError):
    default_status_code = 409
    default_title = "Idempotent Request In Progress"
    default_error_code = "IDEMPOTENCY_IN_PROGRESS"
    default_problem_slug = "idempotency-in-progress"


class PayloadTooLargeError(DomainError):
    default_status_code = 413
    default_title = "Payload Too Large"
    default_error_code = "PAYLOAD_TOO_LARGE"
    default_problem_slug = "payload-too-large"


class UnsupportedMediaTypeError(DomainError):
    default_status_code = 415
    default_title = "Unsupported Media Type"
    default_error_code = "UNSUPPORTED_MEDIA_TYPE"
    default_problem_slug = "unsupported-media-type"
