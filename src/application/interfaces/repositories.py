from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from src.domain.entities import (
    ClinicalSession,
    ConsentAuditEvent,
    EmergencyAlert,
    EmergencyContact,
    FogEpisode,
    IdempotencyRecord,
    MedicationLog,
    ModelBundleManifest,
    PatientProfile,
    RefreshTokenRecord,
    SkeletonChunk,
    UserAccount,
    WindowPrediction,
)


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> UserAccount | None:
        ...

    async def get_by_identifier(self, identifier: str) -> UserAccount | None:
        ...

    async def create(self, user: UserAccount) -> None:
        ...

    async def delete_by_id(self, user_id: UUID) -> None:
        ...


class RefreshTokenRepository(Protocol):
    async def create(self, token: RefreshTokenRecord) -> None:
        ...

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        ...

    async def revoke_by_id(self, token_id: UUID, revoked_at_utc: datetime) -> None:
        ...

    async def revoke_family(self, family_id: UUID, revoked_at_utc: datetime) -> None:
        ...

    async def revoke_by_user_and_device(
        self,
        user_id: UUID,
        device_id: str,
        revoked_at_utc: datetime,
    ) -> None:
        ...

    async def delete_all_for_user(self, user_id: UUID) -> None:
        ...


class PatientRepository(Protocol):
    async def get_by_id(self, patient_id: UUID) -> PatientProfile | None:
        ...

    async def create(self, patient: PatientProfile) -> None:
        ...

    async def update(self, patient: PatientProfile) -> None:
        ...

    async def replace_emergency_contacts(
        self,
        patient_id: UUID,
        contacts: list[EmergencyContact],
    ) -> None:
        ...

    async def add_consent_audit_events(self, events: list[ConsentAuditEvent]) -> None:
        ...

    async def has_access_grant(self, patient_id: UUID, grantee_user_id: UUID) -> bool:
        ...

    async def hard_delete_patient_and_user(self, patient_id: UUID, user_id: UUID) -> None:
        ...


class IdempotencyRepository(Protocol):
    async def try_acquire(
        self,
        record: IdempotencyRecord,
    ) -> tuple[bool, IdempotencyRecord | None]:
        """Attempt to insert an IN_PROGRESS lock. Returns (acquired, existing_record)."""
        ...

    async def get(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> IdempotencyRecord | None:
        ...

    async def mark_completed(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
        status_code: int,
        response_body: dict[str, Any] | list[Any] | None,
    ) -> None:
        ...

    async def delete_in_progress(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> None:
        ...

    async def purge_for_actor(self, actor_user_id: UUID) -> None:
        ...


class MedicationRepository(Protocol):
    async def create(self, log: MedicationLog) -> None:
        ...

    async def get_by_id(self, log_id: UUID) -> MedicationLog | None:
        ...

    async def list_by_patient(
        self,
        patient_id: UUID,
        *,
        from_utc: datetime | None,
        to_utc: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[MedicationLog], int]:
        ...


class SessionRepository(Protocol):
    async def create(self, session: ClinicalSession) -> None:
        ...

    async def get_by_id(self, session_id: UUID) -> ClinicalSession | None:
        ...

    async def add_skeleton_chunk(self, chunk: SkeletonChunk) -> None:
        ...

    async def has_skeleton_chunk(self, session_id: UUID, chunk_index: int) -> bool:
        ...

    async def save_results(
        self,
        session: ClinicalSession,
        episodes: list[FogEpisode],
        windows: list[WindowPrediction],
    ) -> None:
        ...

    async def list_completed_for_trends(
        self,
        patient_id: UUID,
        *,
        from_utc: datetime | None,
        to_utc: datetime | None,
    ) -> list[ClinicalSession]:
        ...


class AlertRepository(Protocol):
    async def create(self, alert: EmergencyAlert) -> None:
        ...

    async def get_by_id(self, alert_id: UUID) -> EmergencyAlert | None:
        ...


class ModelBundleRepository(Protocol):
    async def get_active(self) -> ModelBundleManifest | None:
        ...

    async def upsert(
        self,
        manifest: ModelBundleManifest,
        *,
        is_active: bool,
        published_at_utc: datetime,
    ) -> None:
        ...


class UnitOfWork(Protocol):
    users: UserRepository
    refresh_tokens: RefreshTokenRepository
    patients: PatientRepository
    idempotency: IdempotencyRepository
    medications: MedicationRepository
    sessions: SessionRepository
    alerts: AlertRepository
    model_bundles: ModelBundleRepository

    async def __aenter__(self) -> "UnitOfWork":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
