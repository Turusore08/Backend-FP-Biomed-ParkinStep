from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from src.application.dtos import MedicationListQueryDTO, MedicationLogCreateDTO
from src.application.use_cases.medications import (
    CreateMedicationLogUseCase,
    ListMedicationLogsUseCase,
)
from src.presentation.dependencies import (
    CurrentActorDep,
    get_create_medication_use_case,
    get_list_medications_use_case,
)
from src.presentation.schemas import (
    MedicationLogCreate,
    MedicationLogListResponse,
    MedicationLogResponse,
    ProblemDetailsSchema,
    UtcDatetime,
)

router = APIRouter(prefix="/patients/{patient_id}/medications", tags=["Medications"])


@router.post(
    "",
    response_model=MedicationLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Catat jadwal atau konsumsi medikasi Levodopa",
    responses={
        400: {"model": ProblemDetailsSchema},
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def create_medication_log(
    patient_id: UUID,
    payload: MedicationLogCreate,
    _idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    actor: CurrentActorDep,
    use_case: Annotated[CreateMedicationLogUseCase, Depends(get_create_medication_use_case)],
) -> MedicationLogResponse:
    dto = await use_case.execute(
        actor,
        MedicationLogCreateDTO(
            log_id=payload.log_id,
            patient_id=patient_id,
            drug_name=payload.drug_name,
            dosage_mg=payload.dosage_mg,
            taken_at_utc=payload.taken_at_utc,
            med_state=payload.med_state,
            notes=payload.notes,
        ),
    )
    return MedicationLogResponse.from_dto(dto)


@router.get(
    "",
    response_model=MedicationLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Daftar riwayat minum obat Levodopa (paginated)",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def list_medication_logs(
    patient_id: UUID,
    actor: CurrentActorDep,
    use_case: Annotated[ListMedicationLogsUseCase, Depends(get_list_medications_use_case)],
    from_utc: UtcDatetime | None = None,
    to_utc: UtcDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MedicationLogListResponse:
    dto = await use_case.execute(
        actor,
        patient_id,
        MedicationListQueryDTO(
            from_utc=from_utc,
            to_utc=to_utc,
            limit=limit,
            offset=offset,
        ),
    )
    return MedicationLogListResponse.from_dto(dto)
