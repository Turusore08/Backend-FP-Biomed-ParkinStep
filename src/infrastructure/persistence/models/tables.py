from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base, JsonVariant, UtcDateTime


class UserORM(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    identifier: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class RefreshTokenORM(Base):
    __tablename__ = "refresh_tokens"

    token_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(String(160), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    expires_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    revoked_at_utc: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class PatientORM(Base):
    __tablename__ = "patients"

    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consent_local: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    consent_skeleton_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_cloud_video: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_updated_at_utc: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    updated_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class PatientAccessGrantORM(Base):
    __tablename__ = "patient_access_grants"

    grant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    grantee_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_role: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    __table_args__ = (
        UniqueConstraint("patient_id", "grantee_user_id", name="uq_patient_access_grant"),
    )


class EmergencyContactORM(Base):
    __tablename__ = "emergency_contacts"

    contact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class ConsentAuditLogORM(Base):
    __tablename__ = "consent_audit_logs"

    audit_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    new_value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class MedicationLogORM(Base):
    __tablename__ = "medication_logs"

    log_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    drug_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dosage_mg: Mapped[float] = mapped_column(Float, nullable=False)
    taken_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    med_state: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    __table_args__ = (
        Index("idx_medication_logs_patient_time", "patient_id", taken_at_utc.desc()),
    )


class ClinicalSessionORM(Base):
    __tablename__ = "clinical_sessions"

    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    last_medication_log_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("medication_logs.log_id", ondelete="SET NULL"),
        nullable=True,
    )
    protocol: Mapped[str] = mapped_column(String(48), nullable=False)
    inference_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    med_state: Mapped[str] = mapped_column(String(16), nullable=False)
    target_fps: Mapped[int] = mapped_column(Integer, nullable=False)
    model_bundle_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    safety_checklist_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    classifier_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    threshold_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    ended_at_utc: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    valid_lb6_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fog_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    episode_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_fog_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    median_episode_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    __table_args__ = (
        Index("idx_sessions_patient_time", "patient_id", started_at_utc.desc()),
    )


class FogEpisodeORM(Base):
    __tablename__ = "fog_episodes"

    episode_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    episode_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    peak_calibrated_score: Mapped[float] = mapped_column(Float, nullable=False)
    mean_freeze_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "episode_index", name="uq_fog_episode_index"),
    )


class WindowPredictionORM(Base):
    __tablename__ = "window_predictions"

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    window_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    raw_prob: Mapped[float] = mapped_column(Float, nullable=False)
    calibrated_score: Mapped[float] = mapped_column(Float, nullable=False)
    pred_raw: Mapped[int] = mapped_column(Integer, nullable=False)
    pred_postprocessed: Mapped[int] = mapped_column(Integer, nullable=False)
    freeze_index_ankle: Mapped[float | None] = mapped_column(Float, nullable=True)
    bilateral_asym_ankle: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_quality_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SkeletonChunkORM(Base):
    __tablename__ = "skeleton_chunks"

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    sampling_hz: Mapped[float] = mapped_column(Float, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    compression: Mapped[str] = mapped_column(String(16), nullable=False, default="ZLIB")
    payload_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class EmergencyAlertORM(Base):
    __tablename__ = "emergency_alerts"

    alert_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(String(48), nullable=False)
    triggered_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    cancelled_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dispatched_at_utc: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)


class ModelBundleORM(Base):
    __tablename__ = "model_bundles"

    bundle_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    target_fps: Mapped[int] = mapped_column(Integer, nullable=False)
    window_sec: Mapped[float] = mapped_column(Float, nullable=False)
    stride_sec: Mapped[float] = mapped_column(Float, nullable=False)
    min_run_windows: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_payload: Mapped[dict[str, Any]] = mapped_column(JsonVariant, nullable=False)
    published_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class IdempotencyKeyORM(Base):
    __tablename__ = "idempotency_keys"

    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    method: Mapped[str] = mapped_column(String(16), primary_key=True)
    path: Mapped[str] = mapped_column(String(255), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JsonVariant,
        nullable=True,
    )
    created_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
