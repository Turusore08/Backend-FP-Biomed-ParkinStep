from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from src.application.dtos import PatientEraseRequestDTO
from src.application.use_cases.patients import (
    ErasePatientDataUseCase,
    GetPatientUseCase,
    UpdatePatientUseCase,
)
from src.presentation.dependencies import (
    CurrentActorDep,
    get_erase_patient_use_case,
    get_patient_use_case,
    get_update_patient_use_case,
)
from src.presentation.schemas import (
    PatientEraseRequest,
    PatientPatchRequest,
    PatientProfileResponse,
    ProblemDetailsSchema,
)

router = APIRouter(prefix="/patients", tags=["Patients & UU PDP"])


@router.get(
    "/{patient_id}",
    response_model=PatientProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Ambil profil pasien, kontak darurat, dan consent flags UU PDP",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
    },
)
async def get_patient(
    patient_id: UUID,
    actor: CurrentActorDep,
    use_case: Annotated[GetPatientUseCase, Depends(get_patient_use_case)],
) -> PatientProfileResponse:
    dto = await use_case.execute(actor, patient_id)
    return PatientProfileResponse.from_dto(dto)


@router.patch(
    "/{patient_id}",
    response_model=PatientProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update kontak darurat atau pencabutan consent UU PDP",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
        409: {"model": ProblemDetailsSchema},
        422: {"model": ProblemDetailsSchema},
    },
)
async def update_patient(
    patient_id: UUID,
    payload: PatientPatchRequest,
    actor: CurrentActorDep,
    use_case: Annotated[UpdatePatientUseCase, Depends(get_update_patient_use_case)],
) -> PatientProfileResponse:
    dto = await use_case.execute(actor, patient_id, payload.to_dto())
    return PatientProfileResponse.from_dto(dto)


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hak penghapusan permanen data cloud (UU PDP No. 27/2022) + re-auth",
    responses={
        401: {"model": ProblemDetailsSchema},
        403: {"model": ProblemDetailsSchema},
        404: {"model": ProblemDetailsSchema},
    },
)
async def delete_patient(
    patient_id: UUID,
    payload: PatientEraseRequest,
    actor: CurrentActorDep,
    use_case: Annotated[ErasePatientDataUseCase, Depends(get_erase_patient_use_case)],
) -> Response:
    await use_case.execute(actor, patient_id, PatientEraseRequestDTO(password=payload.password))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
