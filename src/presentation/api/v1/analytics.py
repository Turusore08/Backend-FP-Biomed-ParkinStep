from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.application.use_cases.analytics import GetPatientTrendsUseCase
from src.presentation.dependencies import CurrentActorDep, get_patient_trends_use_case
from src.presentation.schemas import (
    PatientTrendsResponse,
    ProblemDetailsSchema,
    UtcDatetime,
)

router = APIRouter(prefix="/patients/{patient_id}/analytics", tags=["Analytics"])


@router.get(
    "/trends",
    response_model=PatientTrendsResponse,
    status_code=status.HTTP_200_OK,
    summary="Ambil tren perkembangan FoG & komparasi ON vs OFF medikasi",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def get_patient_trends(
    patient_id: UUID,
    actor: CurrentActorDep,
    use_case: Annotated[GetPatientTrendsUseCase, Depends(get_patient_trends_use_case)],
    from_utc: UtcDatetime | None = None,
    to_utc: UtcDatetime | None = None,
) -> PatientTrendsResponse:
    dto = await use_case.execute(
        actor,
        patient_id,
        from_utc=from_utc,
        to_utc=to_utc,
    )
    return PatientTrendsResponse.from_dto(dto)
