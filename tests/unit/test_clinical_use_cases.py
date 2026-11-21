from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.application.dtos import (
    ActorContext,
    EmergencyAlertCreateDTO,
    FogEpisodeInputDTO,
    MedicationListQueryDTO,
    MedicationLogCreateDTO,
    SessionCreateDTO,
    SessionResultUploadDTO,
    SkeletonBatchUploadDTO,
    WindowPredictionInputDTO,
)
from src.application.interfaces import VideoAnalysisOutcome
from src.application.use_cases.alerts import DispatchEmergencyAlertUseCase
from src.application.use_cases.analytics import GetPatientTrendsUseCase
from src.application.use_cases.medications import (
    CreateMedicationLogUseCase,
    ListMedicationLogsUseCase,
)
from src.application.use_cases.models import GetModelManifestUseCase
from src.application.use_cases.sessions import (
    AnalyzeVideoFallbackUseCase,
    CreateSessionUseCase,
    UploadSessionResultsUseCase,
    UploadSkeletonBatchUseCase,
)
from src.domain.entities import (
    ClinicalSession,
    ConsentPreferences,
    EmergencyAlert,
    EmergencyContact,
    FogEpisode,
    MedicationLog,
    ModelBundleManifest,
    PatientProfile,
    SkeletonChunk,
    WindowPrediction,
)
from src.domain.enums import (
    ClassifierName,
    EmergencyTrigger,
    InferenceMode,
    MedicationState,
    SessionProtocol,
    UserRole,
)
from src.domain.exceptions import (
    ConsentRevokedError,
    EntityNotFoundError,
    UnsupportedMediaTypeError,
)
from src.domain.value_objects import utc_now
from src.infrastructure.persistence.codecs.skeleton_codec import ZlibSkeletonCodec
from src.infrastructure.security.video_disposal import SecureTempVideoDisposer


class _ClinicalMemDb:
    def __init__(self, patient: PatientProfile) -> None:
        self.patients: dict[UUID, PatientProfile] = {patient.patient_id: patient}
        self.meds: dict[UUID, MedicationLog] = {}
        self.sessions: dict[UUID, ClinicalSession] = {}
        self.skeletons: dict[tuple[UUID, int], SkeletonChunk] = {}
        self.alerts: dict[UUID, EmergencyAlert] = {}
        self.active_bundle: ModelBundleManifest | None = None


class _PatientRepoStub:
    def __init__(self, db: _ClinicalMemDb) -> None:
        self._db = db

    async def get_by_id(self, patient_id: UUID) -> PatientProfile | None:
        return self._db.patients.get(patient_id)

    async def has_access_grant(self, patient_id: UUID, grantee_user_id: UUID) -> bool:
        return False


class _MedRepoStub:
    def __init__(self, db: _ClinicalMemDb) -> None:
        self._db = db

    async def create(self, log: MedicationLog) -> None:
        self._db.meds[log.log_id] = log

    async def get_by_id(self, log_id: UUID) -> MedicationLog | None:
        return self._db.meds.get(log_id)

    async def list_by_patient(
        self,
        patient_id: UUID,
        *,
        from_utc: datetime | None,
        to_utc: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[MedicationLog], int]:
        items = [
            m
            for m in self._db.meds.values()
            if m.patient_id == patient_id
            and (from_utc is None or m.taken_at_utc >= from_utc)
            and (to_utc is None or m.taken_at_utc <= to_utc)
        ]
        items.sort(key=lambda m: m.taken_at_utc, reverse=True)
        return items[offset : offset + limit], len(items)


class _SessionRepoStub:
    def __init__(self, db: _ClinicalMemDb) -> None:
        self._db = db

    async def create(self, session: ClinicalSession) -> None:
        self._db.sessions[session.session_id] = session

    async def get_by_id(self, session_id: UUID) -> ClinicalSession | None:
        return self._db.sessions.get(session_id)

    async def add_skeleton_chunk(self, chunk: SkeletonChunk) -> None:
        self._db.skeletons[(chunk.session_id, chunk.chunk_index)] = chunk

    async def has_skeleton_chunk(self, session_id: UUID, chunk_index: int) -> bool:
        return (session_id, chunk_index) in self._db.skeletons

    async def save_results(
        self,
        session: ClinicalSession,
        episodes: list[FogEpisode],
        windows: list[WindowPrediction],
    ) -> None:
        session.episodes = episodes
        session.windows = windows
        self._db.sessions[session.session_id] = session

    async def list_completed_for_trends(
        self,
        patient_id: UUID,
        *,
        from_utc: datetime | None,
        to_utc: datetime | None,
    ) -> list[ClinicalSession]:
        rows = [
            s
            for s in self._db.sessions.values()
            if s.patient_id == patient_id
            and s.ended_at_utc is not None
            and (from_utc is None or s.started_at_utc >= from_utc)
            and (to_utc is None or s.started_at_utc <= to_utc)
        ]
        rows.sort(key=lambda s: s.started_at_utc)
        return rows


class _AlertRepoStub:
    def __init__(self, db: _ClinicalMemDb) -> None:
        self._db = db

    async def create(self, alert: EmergencyAlert) -> None:
        self._db.alerts[alert.alert_id] = alert

    async def get_by_id(self, alert_id: UUID) -> EmergencyAlert | None:
        return self._db.alerts.get(alert_id)


class _ModelRepoStub:
    def __init__(self, db: _ClinicalMemDb) -> None:
        self._db = db

    async def get_active(self) -> ModelBundleManifest | None:
        return self._db.active_bundle


class _MemUoW:
    def __init__(self, db: _ClinicalMemDb) -> None:
        self.patients: Any = _PatientRepoStub(db)
        self.medications: Any = _MedRepoStub(db)
        self.sessions: Any = _SessionRepoStub(db)
        self.alerts: Any = _AlertRepoStub(db)
        self.model_bundles: Any = _ModelRepoStub(db)

    async def __aenter__(self) -> "_MemUoW":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: int = 0

    async def notify_caregivers(
        self,
        alert: EmergencyAlert,
        contacts: list[EmergencyContact],
    ) -> int:
        self.calls += 1
        return len(contacts)


class _FakeAnalyzer:
    async def analyze_video_file(self, video_path: Path, session_id: UUID) -> VideoAnalysisOutcome:
        return VideoAnalysisOutcome(frames_analyzed=90, detail=f"ok:{video_path.name}")


async def test_clinical_use_cases_end_to_end_with_stubs(tmp_path: Path) -> None:
    now = utc_now()
    pid = uuid4()
    patient = PatientProfile(
        patient_id=pid,
        user_id=pid,
        display_name="Pasien Test",
        birth_year=1957,
        consent=ConsentPreferences(
            consent_local=True,
            consent_skeleton_sync=False,
            consent_cloud_video=False,
            accepted_at_utc=now,
        ),
        updated_at_utc=now,
        emergency_contacts=[
            EmergencyContact(
                contact_id=uuid4(),
                patient_id=pid,
                name="Siti",
                phone_e164="+6281234567890",
                relation="Spouse",
                is_primary=True,
                updated_at_utc=now,
            )
        ],
    )
    db = _ClinicalMemDb(patient)
    actor = ActorContext(user_id=pid, role=UserRole.PATIENT, device_id="dev-1")

    def uow_factory() -> Any:
        return _MemUoW(db)

    med_uc = CreateMedicationLogUseCase(uow_factory)
    med_id = uuid4()
    with pytest.raises(ConsentRevokedError):
        await med_uc.execute(
            actor,
            MedicationLogCreateDTO(
                log_id=med_id,
                patient_id=pid,
                drug_name="Levodopa/Carbidopa",
                dosage_mg=100.0,
                taken_at_utc=now,
                med_state=MedicationState.ON,
                notes=None,
            ),
        )

    patient.consent = ConsentPreferences(
        consent_local=True,
        consent_skeleton_sync=True,
        consent_cloud_video=False,
        accepted_at_utc=now,
    )
    med_out = await med_uc.execute(
        actor,
        MedicationLogCreateDTO(
            log_id=med_id,
            patient_id=pid,
            drug_name="Levodopa/Carbidopa",
            dosage_mg=100.0,
            taken_at_utc=now,
            med_state=MedicationState.ON,
            notes=None,
        ),
    )
    assert med_out.notes is None

    list_med_uc = ListMedicationLogsUseCase(uow_factory)
    med_list = await list_med_uc.execute(actor, pid, MedicationListQueryDTO())
    assert med_list.total == 1

    sess_uc = CreateSessionUseCase(uow_factory)
    with pytest.raises(EntityNotFoundError):
        await sess_uc.execute(
            actor,
            SessionCreateDTO(
                session_id=uuid4(),
                patient_id=pid,
                protocol=SessionProtocol.TURNING_360_2MIN,
                inference_mode=InferenceMode.LIVE_CAUSAL,
                med_state=MedicationState.ON,
                last_medication_log_id=uuid4(),
                target_fps=15,
                model_bundle_version="b15hz-v1.0.0",
                started_at_utc=now - timedelta(minutes=10),
                safety_checklist_confirmed=True,
            ),
        )

    s_on = uuid4()
    await sess_uc.execute(
        actor,
        SessionCreateDTO(
            session_id=s_on,
            patient_id=pid,
            protocol=SessionProtocol.TURNING_360_2MIN,
            inference_mode=InferenceMode.LIVE_CAUSAL,
            med_state=MedicationState.ON,
            last_medication_log_id=med_id,
            target_fps=15,
            model_bundle_version="b15hz-v1.0.0",
            started_at_utc=now - timedelta(minutes=10),
            safety_checklist_confirmed=True,
        ),
    )

    skel_uc = UploadSkeletonBatchUseCase(uow_factory, ZlibSkeletonCodec())
    ack = await skel_uc.execute(
        actor,
        SkeletonBatchUploadDTO(
            session_id=s_on,
            chunk_index=0,
            sampling_hz=15.0,
            frame_timestamps_ms=[0, 67],
            lb6_xyc=[
                [[100.0, 200.0, 0.9] for _ in range(6)],
                [[101.0, 201.0, 0.9] for _ in range(6)],
            ],
        ),
    )
    assert ack.frame_count == 2

    res_uc = UploadSessionResultsUseCase(uow_factory)
    await res_uc.execute(
        actor,
        SessionResultUploadDTO(
            session_id=s_on,
            classifier_used=ClassifierName.LIGHTGBM_FFT,
            threshold_used=0.26,
            ended_at_utc=now - timedelta(minutes=8),
            duration_sec=120.0,
            valid_lb6_ratio=0.98,
            fog_percentage=10.0,
            episode_count=1,
            total_fog_duration_sec=12.0,
            median_episode_duration_sec=12.0,
            episodes=[
                FogEpisodeInputDTO(
                    episode_index=1,
                    start_sec=10.0,
                    end_sec=22.0,
                    duration_sec=12.0,
                    peak_calibrated_score=84.5,
                    mean_freeze_index=2.3,
                )
            ],
            windows=[
                WindowPredictionInputDTO(
                    window_idx=0,
                    start_sec=0.0,
                    end_sec=2.0,
                    raw_prob=0.1,
                    calibrated_score=19.2,
                    pred_raw=0,
                    pred_postprocessed=0,
                    freeze_index_ankle=0.4,
                    bilateral_asym_ankle=0.05,
                    low_quality_flag=False,
                )
            ],
        ),
    )

    trends_uc = GetPatientTrendsUseCase(uow_factory)
    trends = await trends_uc.execute(actor, pid)
    assert trends.total_sessions == 1
    assert trends.on_med_avg_fog_pct == 10.0
    assert trends.off_med_avg_fog_pct is None

    disposer = SecureTempVideoDisposer(str(tmp_path / "vid"))
    video_uc = AnalyzeVideoFallbackUseCase(
        uow_factory, disposer, _FakeAnalyzer(), max_upload_bytes=4096
    )

    async def _mp4_stream() -> AsyncIterator[bytes]:
        yield b"ftypmp42"

    with pytest.raises(UnsupportedMediaTypeError):
        await video_uc.execute(
            actor,
            s_on,
            content_type="text/plain",
            data_stream=_mp4_stream(),
        )

    with pytest.raises(ConsentRevokedError):
        await video_uc.execute(
            actor,
            s_on,
            content_type="video/mp4",
            data_stream=_mp4_stream(),
        )

    notifier = _FakeNotifier()
    alert_uc = DispatchEmergencyAlertUseCase(uow_factory, notifier)
    near_miss = await alert_uc.execute(
        actor,
        EmergencyAlertCreateDTO(
            alert_id=uuid4(),
            patient_id=pid,
            session_id=s_on,
            trigger_type=EmergencyTrigger.PROLONGED_FREEZE_15S,
            triggered_at_utc=now,
            cancelled_by_user=True,
        ),
    )
    assert near_miss.dispatched_at_utc is None
    assert notifier.calls == 0

    dispatched = await alert_uc.execute(
        actor,
        EmergencyAlertCreateDTO(
            alert_id=uuid4(),
            patient_id=pid,
            session_id=s_on,
            trigger_type=EmergencyTrigger.SUDDEN_HIP_DROP_IMMOBILITY,
            triggered_at_utc=now,
            cancelled_by_user=False,
        ),
    )
    assert dispatched.dispatched_at_utc is not None
    assert dispatched.notified_contacts_count == 1
    assert notifier.calls == 1

    manifest_uc = GetModelManifestUseCase(uow_factory, "https://cdn.example.org/models")
    manifest = await manifest_uc.execute()
    assert manifest.target_fps == 15
    assert manifest.primary_classifier.requires_scaled_input is False
    assert manifest.primary_classifier.threshold_val == 0.26
