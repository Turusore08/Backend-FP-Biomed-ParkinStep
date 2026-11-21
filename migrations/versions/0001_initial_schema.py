"""Initial ParkinStep schema for auth, UU PDP patients, clinical sync, and idempotency.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-21 08:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_users_identifier", "users", ["identifier"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(length=160), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_id"),
    )
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "patients",
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("consent_local", sa.Boolean(), nullable=False),
        sa.Column("consent_skeleton_sync", sa.Boolean(), nullable=False),
        sa.Column("consent_cloud_video", sa.Boolean(), nullable=False),
        sa.Column("consent_updated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("patient_id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "patient_access_grants",
        sa.Column("grant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("grantee_user_id", sa.Uuid(), nullable=False),
        sa.Column("access_role", sa.String(length=32), nullable=False),
        sa.Column("granted_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["grantee_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("grant_id"),
        sa.UniqueConstraint("patient_id", "grantee_user_id", name="uq_patient_access_grant"),
    )
    op.create_index(
        "ix_patient_access_grants_grantee_user_id",
        "patient_access_grants",
        ["grantee_user_id"],
        unique=False,
    )

    op.create_table(
        "emergency_contacts",
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=False),
        sa.Column("relation", sa.String(length=64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("contact_id"),
    )
    op.create_index(
        "ix_emergency_contacts_patient_id",
        "emergency_contacts",
        ["patient_id"],
        unique=False,
    )

    op.create_table(
        "consent_audit_logs",
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Boolean(), nullable=True),
        sa.Column("new_value", sa.Boolean(), nullable=False),
        sa.Column("changed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "ix_consent_audit_logs_patient_id",
        "consent_audit_logs",
        ["patient_id"],
        unique=False,
    )

    op.create_table(
        "medication_logs",
        sa.Column("log_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("drug_name", sa.String(length=120), nullable=False),
        sa.Column("dosage_mg", sa.Float(), nullable=False),
        sa.Column("taken_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("med_state", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("synced_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_index(
        "idx_medication_logs_patient_time",
        "medication_logs",
        ["patient_id", sa.literal_column("taken_at_utc DESC")],
        unique=False,
    )

    op.create_table(
        "clinical_sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("last_medication_log_id", sa.Uuid(), nullable=True),
        sa.Column("protocol", sa.String(length=48), nullable=False),
        sa.Column("inference_mode", sa.String(length=32), nullable=False),
        sa.Column("med_state", sa.String(length=16), nullable=False),
        sa.Column("target_fps", sa.Integer(), nullable=False),
        sa.Column("model_bundle_version", sa.String(length=64), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("safety_checklist_confirmed", sa.Boolean(), nullable=False),
        sa.Column("classifier_used", sa.String(length=32), nullable=True),
        sa.Column("threshold_used", sa.Float(), nullable=True),
        sa.Column("ended_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("valid_lb6_ratio", sa.Float(), nullable=False),
        sa.Column("fog_percentage", sa.Float(), nullable=False),
        sa.Column("episode_count", sa.Integer(), nullable=False),
        sa.Column("total_fog_duration_sec", sa.Float(), nullable=False),
        sa.Column("median_episode_duration_sec", sa.Float(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["last_medication_log_id"],
            ["medication_logs.log_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        "idx_sessions_patient_time",
        "clinical_sessions",
        ["patient_id", sa.literal_column("started_at_utc DESC")],
        unique=False,
    )

    op.create_table(
        "fog_episodes",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("episode_index", sa.Integer(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("peak_calibrated_score", sa.Float(), nullable=False),
        sa.Column("mean_freeze_index", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["clinical_sessions.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("episode_id"),
        sa.UniqueConstraint("session_id", "episode_index", name="uq_fog_episode_index"),
    )

    op.create_table(
        "window_predictions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("window_idx", sa.Integer(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("raw_prob", sa.Float(), nullable=False),
        sa.Column("calibrated_score", sa.Float(), nullable=False),
        sa.Column("pred_raw", sa.Integer(), nullable=False),
        sa.Column("pred_postprocessed", sa.Integer(), nullable=False),
        sa.Column("freeze_index_ankle", sa.Float(), nullable=True),
        sa.Column("bilateral_asym_ankle", sa.Float(), nullable=True),
        sa.Column("low_quality_flag", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["clinical_sessions.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", "window_idx"),
    )

    op.create_table(
        "skeleton_chunks",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("sampling_hz", sa.Float(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False),
        sa.Column("compression", sa.String(length=16), nullable=False),
        sa.Column("payload_blob", sa.LargeBinary(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["clinical_sessions.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", "chunk_index"),
    )

    op.create_table(
        "emergency_alerts",
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_type", sa.String(length=48), nullable=False),
        sa.Column("triggered_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_by_user", sa.Boolean(), nullable=False),
        sa.Column("dispatched_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["clinical_sessions.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_index(
        "ix_emergency_alerts_patient_id",
        "emergency_alerts",
        ["patient_id"],
        unique=False,
    )

    op.create_table(
        "model_bundles",
        sa.Column("bundle_version", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("target_fps", sa.Integer(), nullable=False),
        sa.Column("window_sec", sa.Float(), nullable=False),
        sa.Column("stride_sec", sa.Float(), nullable=False),
        sa.Column("min_run_windows", sa.Integer(), nullable=False),
        sa.Column("manifest_payload", _JSON_VARIANT, nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("bundle_version"),
    )
    op.create_index("ix_model_bundles_is_active", "model_bundles", ["is_active"], unique=False)

    op.create_table(
        "idempotency_keys",
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", _JSON_VARIANT, nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("actor_user_id", "method", "path", "idempotency_key"),
    )
    op.create_index(
        "ix_idempotency_keys_expires_at_utc",
        "idempotency_keys",
        ["expires_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_expires_at_utc", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_model_bundles_is_active", table_name="model_bundles")
    op.drop_table("model_bundles")
    op.drop_index("ix_emergency_alerts_patient_id", table_name="emergency_alerts")
    op.drop_table("emergency_alerts")
    op.drop_table("skeleton_chunks")
    op.drop_table("window_predictions")
    op.drop_table("fog_episodes")
    op.drop_index("idx_sessions_patient_time", table_name="clinical_sessions")
    op.drop_table("clinical_sessions")
    op.drop_index("idx_medication_logs_patient_time", table_name="medication_logs")
    op.drop_table("medication_logs")
    op.drop_index("ix_consent_audit_logs_patient_id", table_name="consent_audit_logs")
    op.drop_table("consent_audit_logs")
    op.drop_index("ix_emergency_contacts_patient_id", table_name="emergency_contacts")
    op.drop_table("emergency_contacts")
    op.drop_index("ix_patient_access_grants_grantee_user_id", table_name="patient_access_grants")
    op.drop_table("patient_access_grants")
    op.drop_table("patients")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_identifier", table_name="users")
    op.drop_table("users")
