from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.domain.constants import (
    DEFAULT_THRESHOLDS_B15HZ,
    LB6_JOINT_NAMES,
    MEDICAL_DISCLAIMER_ID,
    SCALER_MEAN_B15HZ,
    SCALER_STD_B15HZ,
    TARGET_FS_HZ,
)
from src.domain.entities import (
    ConsentPreferences,
    EmergencyContact,
    PatientProfile,
    RefreshTokenRecord,
    UserAccount,
)
from src.domain.enums import (
    AlertTier,
    ClassifierName,
    EmergencyTrigger,
    InferenceMode,
    MedicationState,
    SessionProtocol,
    UserRole,
)
from src.domain.exceptions import DomainValidationError
from src.domain.value_objects import (
    Lb6Frame,
    compute_calibrated_score,
    ensure_utc,
    format_utc_z,
    parse_utc_iso,
    utc_now,
    validate_phone_e164,
)


def test_locked_constants_and_enums_match_contract() -> None:
    assert TARGET_FS_HZ == 15.0
    assert len(LB6_JOINT_NAMES) == 6
    assert len(SCALER_MEAN_B15HZ) == 9
    assert len(SCALER_STD_B15HZ) == 9
    assert DEFAULT_THRESHOLDS_B15HZ[ClassifierName.LIGHTGBM_FFT] == 0.26
    assert DEFAULT_THRESHOLDS_B15HZ[ClassifierName.LIGHT_STGCN] == 0.39
    assert DEFAULT_THRESHOLDS_B15HZ[ClassifierName.PURE_BIMAMBA] == 0.15
    assert "BUKAN merupakan diagnosis medis resmi" in MEDICAL_DISCLAIMER_ID

    assert UserRole.PATIENT == "PATIENT"
    assert MedicationState.ON == "ON"
    assert InferenceMode.CLOUD_FALLBACK == "CLOUD_FALLBACK"
    assert SessionProtocol.TURNING_360_2MIN == "TURNING_360_2MIN"
    assert EmergencyTrigger.PROLONGED_FREEZE_15S == "PROLONGED_FREEZE_15S"
    assert AlertTier.FOG_CONFIRMED == "FOG_CONFIRMED"


def test_utc_timestamp_enforces_timezone_awareness_and_z_suffix() -> None:
    naive = datetime(2026, 11, 20, 8, 45, 12)
    with pytest.raises(DomainValidationError):
        ensure_utc(naive)
    with pytest.raises(DomainValidationError):
        parse_utc_iso("2026-11-20T08:45:12")
    with pytest.raises(DomainValidationError):
        parse_utc_iso("not-a-date")

    wib = timezone(timedelta(hours=7))
    aware_wib = datetime(2026, 11, 20, 15, 45, 12, tzinfo=wib)
    normalized = ensure_utc(aware_wib)
    assert normalized.tzinfo == UTC
    assert format_utc_z(normalized) == "2026-11-20T08:45:12Z"
    assert parse_utc_iso("2026-11-20T08:45:12Z") == normalized


def test_calibrated_score_piecewise_mapping() -> None:
    assert compute_calibrated_score(0.0, 0.26) == 0.0
    assert compute_calibrated_score(0.26, 0.26) == 50.0
    assert compute_calibrated_score(1.0, 0.26) == 100.0
    assert compute_calibrated_score(0.13, 0.26) == 25.0
    assert compute_calibrated_score(0.39, 0.39) == 50.0
    assert compute_calibrated_score(0.15, 0.15) == 50.0

    with pytest.raises(DomainValidationError):
        compute_calibrated_score(-0.01, 0.26)
    with pytest.raises(DomainValidationError):
        compute_calibrated_score(1.1, 0.26)
    with pytest.raises(DomainValidationError):
        compute_calibrated_score(0.5, 0.0)


def test_lb6_frame_and_e164_validation() -> None:
    valid_joints = tuple((100.0 + i, 200.0 + i, 0.9) for i in range(6))
    frame = Lb6Frame(keypoints=valid_joints)
    assert len(frame.keypoints) == 6

    with pytest.raises(DomainValidationError):
        Lb6Frame(keypoints=valid_joints[:5])
    with pytest.raises(DomainValidationError):
        Lb6Frame(keypoints=((1.0, 2.0, 1.2),) + valid_joints[1:])
    with pytest.raises(DomainValidationError):
        Lb6Frame(keypoints=((float("nan"), 2.0, 0.8),) + valid_joints[1:])

    assert validate_phone_e164(" +6281234567890 ") == "+6281234567890"
    with pytest.raises(DomainValidationError):
        validate_phone_e164("081234567890")


def test_patient_and_token_entity_invariants() -> None:
    now = utc_now()
    uid = uuid4()
    user = UserAccount(
        user_id=uid,
        identifier=" Patient@Example.ID ",
        password_hash="hash",
        role=UserRole.PATIENT,
        is_active=True,
        created_at_utc=now,
    )
    assert user.identifier == "patient@example.id"

    token = RefreshTokenRecord(
        token_id=uuid4(),
        user_id=uid,
        device_id="pixel-8",
        token_hash="abc",
        family_id=uuid4(),
        expires_at_utc=now + timedelta(days=1),
        revoked_at_utc=None,
        created_at_utc=now,
    )
    assert token.is_active_at(now)
    assert not token.is_active_at(now + timedelta(days=2))

    c1 = EmergencyContact(
        contact_id=uuid4(),
        patient_id=uid,
        name="Ani",
        phone_e164="+6281234567890",
        relation="Spouse",
        is_primary=True,
        updated_at_utc=now,
    )
    c2 = EmergencyContact(
        contact_id=uuid4(),
        patient_id=uid,
        name="Budi",
        phone_e164="+6281987654321",
        relation="Son",
        is_primary=True,
        updated_at_utc=now,
    )
    with pytest.raises(DomainValidationError):
        PatientProfile(
            patient_id=uid,
            user_id=uid,
            display_name="Pasien",
            birth_year=1955,
            consent=ConsentPreferences(),
            updated_at_utc=now,
            emergency_contacts=[c1, c2],
        )

    with pytest.raises(DomainValidationError):
        PatientProfile(
            patient_id=uid,
            user_id=uid,
            display_name="Pasien",
            birth_year=1850,
            consent=ConsentPreferences(),
            updated_at_utc=now,
        )
