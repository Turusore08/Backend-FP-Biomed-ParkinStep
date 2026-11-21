from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.exceptions import PROBLEM_BASE_URI
from src.presentation.api.middleware.error_handler import problem_json_response

router = APIRouter(tags=["Health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe verifying database connectivity")
async def readyz(request: Request) -> JSONResponse:
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        request.app.state.session_factory,
    )
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready"})
    except Exception:
        return problem_json_response(
            status_code=503,
            problem_type=f"{PROBLEM_BASE_URI}/service-unavailable",
            title="Service Unavailable",
            detail="Database readiness check failed.",
            instance=request.url.path,
            error_code="DATABASE_UNAVAILABLE",
        )
