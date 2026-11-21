import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.domain.exceptions import PROBLEM_BASE_URI, DomainError, RateLimitExceededError
from src.infrastructure.logging import scrub_dict
from src.presentation.schemas.common import ProblemDetailsSchema

logger = logging.getLogger(__name__)


def problem_json_response(
    *,
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    instance: str,
    error_code: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 7807 compliant application/problem+json response."""
    payload = ProblemDetailsSchema(
        type=problem_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        error_code=error_code,
        errors=errors,
    ).model_dump(exclude_none=True)
    return JSONResponse(
        status_code=status_code,
        content=payload,
        media_type="application/problem+json",
        headers=headers,
    )


def _sanitize_validation_errors(raw_errors: list[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for err in raw_errors:
        if not isinstance(err, dict):
            continue
        loc = list(err.get("loc", ()))
        entry: dict[str, Any] = {
            "loc": loc,
            "msg": str(err.get("msg", "Invalid value.")),
            "type": str(err.get("type", "value_error")),
        }
        if "input" in err:
            entry["input"] = scrub_dict(
                {str(loc[-1]) if loc else "input": err["input"]}
            ).get(str(loc[-1]) if loc else "input")
        sanitized.append(entry)
    return sanitized


def register_exception_handlers(app: FastAPI) -> None:
    """Register global RFC 7807 handlers on the FastAPI instance."""

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        headers: dict[str, str] | None = None
        if isinstance(exc, RateLimitExceededError):
            headers = {"Retry-After": str(exc.retry_after_sec)}
        return problem_json_response(
            status_code=exc.status_code,
            problem_type=exc.problem_type,
            title=exc.title,
            detail=exc.detail,
            instance=request.url.path,
            error_code=exc.error_code,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        sanitized_errors = _sanitize_validation_errors(list(exc.errors()))
        detail = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in sanitized_errors
        ) or "Request validation failed."
        return problem_json_response(
            status_code=422,
            problem_type=f"{PROBLEM_BASE_URI}/validation-error",
            title="Validation Error",
            detail=detail,
            instance=request.url.path,
            error_code="VALIDATION_ERROR",
            errors=sanitized_errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return problem_json_response(
            status_code=exc.status_code,
            problem_type=f"{PROBLEM_BASE_URI}/http-{exc.status_code}",
            title=str(exc.detail) if exc.detail else "HTTP Error",
            detail=str(exc.detail) if exc.detail else "HTTP error occurred.",
            instance=request.url.path,
            error_code=f"HTTP_{exc.status_code}",
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return problem_json_response(
            status_code=500,
            problem_type=f"{PROBLEM_BASE_URI}/internal-server-error",
            title="Internal Server Error",
            detail="An unexpected internal server error occurred.",
            instance=request.url.path,
            error_code="INTERNAL_SERVER_ERROR",
        )
