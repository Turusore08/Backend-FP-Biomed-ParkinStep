from fastapi import APIRouter

from src.presentation.api.v1.alerts import router as alerts_router
from src.presentation.api.v1.analytics import router as analytics_router
from src.presentation.api.v1.auth import router as auth_router
from src.presentation.api.v1.medications import router as medications_router
from src.presentation.api.v1.models import router as models_router
from src.presentation.api.v1.patients import router as patients_router
from src.presentation.api.v1.sessions import router as sessions_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(patients_router)
api_v1_router.include_router(medications_router)
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(alerts_router)
api_v1_router.include_router(models_router)
