from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from src.application.dtos import EmergencyAlertCreateDTO
from src.application.use_cases.alerts import DispatchEmergencyAlertUseCase
from src.presentation.dependencies import CurrentActorDep, get_dispatch_alert_use_case
from src.presentation.schemas import (
    EmergencyAlertRequest,
    EmergencyAlertResponse,
    ProblemDetailsSchema,
)

router = APIRouter(prefix="/alerts", tags=["Emergency Alerts"])


@router.post(
    "/emergency",
    response_model=EmergencyAlertResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Kirim eskalasi darurat jatuh atau prolonged freeze > 15 detik",
    responses={
        400: {"model": ProblemDetailsSchema},
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def dispatch_emergency_alert(
    payload: EmergencyAlertRequest,
    _idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    actor: CurrentActorDep,
    use_case: Annotated[DispatchEmergencyAlertUseCase, Depends(get_dispatch_alert_use_case)],
) -> EmergencyAlertResponse:
    dto = await use_case.execute(
        actor,
        EmergencyAlertCreateDTO(
            alert_id=payload.alert_id,
            patient_id=payload.patient_id,
            session_id=payload.session_id,
            trigger_type=payload.trigger_type,
            triggered_at_utc=payload.triggered_at_utc,
            cancelled_by_user=payload.cancelled_by_user,
        ),
    )
    return EmergencyAlertResponse.from_dto(dto)
