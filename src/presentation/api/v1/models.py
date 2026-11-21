from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.use_cases.models import GetModelManifestUseCase
from src.presentation.dependencies import get_model_manifest_use_case, verify_jwt_or_app_key
from src.presentation.schemas import ModelManifestSchema, ProblemDetailsSchema

router = APIRouter(prefix="/models", tags=["OTA Model Registry"])


@router.get(
    "/manifest",
    response_model=ModelManifestSchema,
    status_code=status.HTTP_200_OK,
    summary="Ambil manifest versi model Edge-AI OTA, scaler_stats & threshold resmi",
    dependencies=[Depends(verify_jwt_or_app_key)],
    responses={
        401: {"model": ProblemDetailsSchema},
    },
)
async def get_model_manifest(
    use_case: Annotated[GetModelManifestUseCase, Depends(get_model_manifest_use_case)],
) -> ModelManifestSchema:
    dto = await use_case.execute()
    return ModelManifestSchema.from_dto(dto)
