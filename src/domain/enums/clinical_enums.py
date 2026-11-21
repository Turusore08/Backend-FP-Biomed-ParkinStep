from enum import StrEnum


class UserRole(StrEnum):
    """Supported user roles defined in API_CONTRACT.md."""

    PATIENT = "PATIENT"
    CAREGIVER = "CAREGIVER"
    CLINICIAN = "CLINICIAN"


class MedicationState(StrEnum):
    """Levodopa medication state at test/log time."""

    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


class InferenceMode(StrEnum):
    """Edge vs Cloud fallback inference mode."""

    LIVE_CAUSAL = "LIVE_CAUSAL"
    POST_SESSION_EXACT = "POST_SESSION_EXACT"
    CLOUD_FALLBACK = "CLOUD_FALLBACK"


class SessionProtocol(StrEnum):
    """Clinical gait screening protocol."""

    TURNING_360_2MIN = "TURNING_360_2MIN"
    FREE_WALK_MONITORING = "FREE_WALK_MONITORING"


class ClassifierName(StrEnum):
    """Supported FoG classifiers in B_15hz production profile."""

    LIGHTGBM_FFT = "LIGHTGBM_FFT"
    LIGHT_STGCN = "LIGHT_STGCN"
    PURE_BIMAMBA = "PURE_BIMAMBA"


class EmergencyTrigger(StrEnum):
    """Fall & prolonged freeze escalation trigger type."""

    PROLONGED_FREEZE_15S = "PROLONGED_FREEZE_15S"
    SUDDEN_HIP_DROP_IMMOBILITY = "SUDDEN_HIP_DROP_IMMOBILITY"


class AlertTier(StrEnum):
    """Two-tier real-time alert status emitted by streaming inference."""

    NORMAL = "NORMAL"
    EARLY_WARNING = "EARLY_WARNING"
    FOG_CONFIRMED = "FOG_CONFIRMED"


class ModelFormat(StrEnum):
    """Model artifact format distributed in OTA manifest."""

    ONNX = "ONNX"
    LGBM_TXT = "LGBM_TXT"


class IdempotencyState(StrEnum):
    """Execution state of an offline-first idempotent request."""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class AccessGrantRole(StrEnum):
    """Delegate roles permitted to access a patient profile when granted."""

    CAREGIVER = "CAREGIVER"
    CLINICIAN = "CLINICIAN"
