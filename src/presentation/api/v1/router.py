from fastapi import APIRouter

from src.presentation.api.v1.auth import router as auth_router
from src.presentation.api.v1.patients import router as patients_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(patients_router)
