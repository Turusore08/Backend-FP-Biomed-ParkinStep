from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.application.dtos import (
    ActorContext,
    EmergencyContactInputDTO,
    LoginRequestDTO,
    LogoutRequestDTO,
    PatientEraseRequestDTO,
    PatientPatchDTO,
    RefreshTokenRequestDTO,
    RegisterRequestDTO,
)
from src.application.interfaces import AccessTokenClaims
from src.application.use_cases.auth import (
    LoginUseCase,
    LogoutUseCase,
    RefreshTokenUseCase,
    RegisterUseCase,
)
from src.application.use_cases.patients import (
    ErasePatientDataUseCase,
    GetPatientUseCase,
    UpdatePatientUseCase,
)
from src.domain.entities import (
    ConsentAuditEvent,
    EmergencyContact,
    IdempotencyRecord,
    PatientProfile,
    RefreshTokenRecord,
    UserAccount,
)
from src.domain.enums import UserRole
from src.domain.exceptions import (
    AuthorizationDeniedError,
    ConflictError,
    DomainValidationError,
    InvalidCredentialsError,
    RateLimitExceededError,
    ReauthRequiredError,
    StaleWriteConflictError,
    TokenReuseDetectedError,
)
from src.domain.value_objects import utc_now


class _FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class _FakeTokenProvider:
    @property
    def refresh_token_ttl_days(self) -> int:
        return 30

    def create_access_token(
        self,
        user_id: UUID,
        role: UserRole,
        device_id: str,
    ) -> tuple[str, int]:
        return f"jwt:{user_id}:{role.value}:{device_id}", 900

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        _, raw_uid, raw_role, dev = token.split(":", 3)
        return AccessTokenClaims(
            user_id=UUID(raw_uid),
            role=UserRole(raw_role),
            device_id=dev,
            jti="jti",
        )

    def generate_refresh_token(self) -> tuple[str, str]:
        raw = f"refresh-{uuid4()}"
        return raw, self.hash_refresh_token(raw)

    def hash_refresh_token(self, raw_token: str) -> str:
        return f"sha:{raw_token}"


class _FakeRateLimiter:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def check_and_consume(
        self,
        key: str,
        max_attempts: int,
        window_sec: int,
    ) -> tuple[bool, int]:
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        if count > max_attempts:
            return False, window_sec
        return True, 0


class _InMemoryDb:
    def __init__(self) -> None:
        self.users: dict[UUID, UserAccount] = {}
        self.refresh_tokens: dict[UUID, RefreshTokenRecord] = {}
        self.patients: dict[UUID, PatientProfile] = {}
        self.grants: set[tuple[UUID, UUID]] = set()
        self.audit_events: list[ConsentAuditEvent] = []
        self.idempotency: dict[tuple[UUID, str, str, UUID], IdempotencyRecord] = {}


class _FakeUserRepo:
    def __init__(self, db: _InMemoryDb) -> None:
        self._db = db

    async def get_by_id(self, user_id: UUID) -> UserAccount | None:
        return self._db.users.get(user_id)

    async def get_by_identifier(self, identifier: str) -> UserAccount | None:
        target = identifier.strip().lower()
        return next((u for u in self._db.users.values() if u.identifier == target), None)

    async def create(self, user: UserAccount) -> None:
        self._db.users[user.user_id] = user

    async def delete_by_id(self, user_id: UUID) -> None:
        self._db.users.pop(user_id, None)


class _FakeRefreshRepo:
    def __init__(self, db: _InMemoryDb) -> None:
        self._db = db

    async def create(self, token: RefreshTokenRecord) -> None:
        self._db.refresh_tokens[token.token_id] = token

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        return next(
            (t for t in self._db.refresh_tokens.values() if t.token_hash == token_hash),
            None,
        )

    async def revoke_by_id(self, token_id: UUID, revoked_at_utc: Any) -> None:
        if token_id in self._db.refresh_tokens:
            self._db.refresh_tokens[token_id].revoked_at_utc = revoked_at_utc

    async def revoke_family(self, family_id: UUID, revoked_at_utc: Any) -> None:
        for t in self._db.refresh_tokens.values():
            if t.family_id == family_id and t.revoked_at_utc is None:
                t.revoked_at_utc = revoked_at_utc

    async def revoke_by_user_and_device(
        self,
        user_id: UUID,
        device_id: str,
        revoked_at_utc: Any,
    ) -> None:
        for t in self._db.refresh_tokens.values():
            if t.user_id == user_id and t.device_id == device_id and t.revoked_at_utc is None:
                t.revoked_at_utc = revoked_at_utc

    async def delete_all_for_user(self, user_id: UUID) -> None:
        to_delete = [k for k, v in self._db.refresh_tokens.items() if v.user_id == user_id]
        for k in to_delete:
            del self._db.refresh_tokens[k]


class _FakePatientRepo:
    def __init__(self, db: _InMemoryDb) -> None:
        self._db = db

    async def get_by_id(self, patient_id: UUID) -> PatientProfile | None:
        return self._db.patients.get(patient_id)

    async def create(self, patient: PatientProfile) -> None:
        self._db.patients[patient.patient_id] = patient

    async def update(self, patient: PatientProfile) -> None:
        self._db.patients[patient.patient_id] = patient

    async def replace_emergency_contacts(
        self,
        patient_id: UUID,
        contacts: list[EmergencyContact],
    ) -> None:
        if patient_id in self._db.patients:
            self._db.patients[patient_id].emergency_contacts = list(contacts)

    async def add_consent_audit_events(self, events: list[ConsentAuditEvent]) -> None:
        self._db.audit_events.extend(events)

    async def has_access_grant(self, patient_id: UUID, grantee_user_id: UUID) -> bool:
        return (patient_id, grantee_user_id) in self._db.grants

    async def hard_delete_patient_and_user(self, patient_id: UUID, user_id: UUID) -> None:
        self._db.patients.pop(patient_id, None)
        self._db.users.pop(user_id, None)
        self._db.audit_events = [e for e in self._db.audit_events if e.patient_id != patient_id]


class _FakeIdemRepo:
    def __init__(self, db: _InMemoryDb) -> None:
        self._db = db

    async def try_acquire(
        self,
        record: IdempotencyRecord,
    ) -> tuple[bool, IdempotencyRecord | None]:
        key = (record.actor_user_id, record.method, record.path, record.idempotency_key)
        if key in self._db.idempotency:
            return False, self._db.idempotency[key]
        self._db.idempotency[key] = record
        return True, None

    async def get(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> IdempotencyRecord | None:
        return self._db.idempotency.get((actor_user_id, method, path, idempotency_key))

    async def mark_completed(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
        status_code: int,
        response_body: dict[str, Any] | list[Any] | None,
    ) -> None:
        rec = self._db.idempotency[(actor_user_id, method, path, idempotency_key)]
        rec.status_code = status_code
        rec.response_body = response_body

    async def delete_in_progress(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> None:
        self._db.idempotency.pop((actor_user_id, method, path, idempotency_key), None)

    async def purge_for_actor(self, actor_user_id: UUID) -> None:
        keys = [k for k in self._db.idempotency if k[0] == actor_user_id]
        for k in keys:
            del self._db.idempotency[k]


class _FakeUoW:
    def __init__(self, db: _InMemoryDb) -> None:
        self.users = _FakeUserRepo(db)
        self.refresh_tokens = _FakeRefreshRepo(db)
        self.patients = _FakePatientRepo(db)
        self.idempotency = _FakeIdemRepo(db)
        self.committed = False

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


async def test_register_login_refresh_reuse_and_logout_unit() -> None:
    db = _InMemoryDb()
    hasher = _FakeHasher()
    tokens = _FakeTokenProvider()
    limiter = _FakeRateLimiter()

    def uow_factory() -> _FakeUoW:
        return _FakeUoW(db)

    reg_uc = RegisterUseCase(uow_factory, hasher, tokens)
    with pytest.raises(DomainValidationError):
        await reg_uc.execute(
            RegisterRequestDTO(
                identifier="p@x.id",
                password="password123",
                role=UserRole.PATIENT,
                device_id="dev1",
                consent_local=False,
            )
        )

    auth_res = await reg_uc.execute(
        RegisterRequestDTO(
            identifier="Patient1@ParkinStep.id",
            password="Password123",
            role=UserRole.PATIENT,
            device_id="dev-1",
            consent_local=True,
            consent_skeleton_sync=True,
        )
    )
    assert auth_res.role == UserRole.PATIENT
    assert len(db.audit_events) == 3

    with pytest.raises(ConflictError):
        await reg_uc.execute(
            RegisterRequestDTO(
                identifier="patient1@parkinstep.id",
                password="Password123",
                role=UserRole.PATIENT,
                device_id="dev-1",
            )
        )

    login_uc = LoginUseCase(uow_factory, hasher, tokens, limiter, max_attempts=2, window_sec=60)
    with pytest.raises(InvalidCredentialsError):
        await login_uc.execute(
            LoginRequestDTO(
                identifier="patient1@parkinstep.id",
                password="wrong",
                device_id="dev-1",
                client_ip="127.0.0.1",
            )
        )
    ok_login = await login_uc.execute(
        LoginRequestDTO(
            identifier="patient1@parkinstep.id",
            password="Password123",
            device_id="dev-1",
            client_ip="127.0.0.1",
        )
    )
    with pytest.raises(RateLimitExceededError):
        await login_uc.execute(
            LoginRequestDTO(
                identifier="patient1@parkinstep.id",
                password="Password123",
                device_id="dev-1",
                client_ip="127.0.0.1",
            )
        )

    refresh_uc = RefreshTokenUseCase(uow_factory, tokens)
    rotated = await refresh_uc.execute(
        RefreshTokenRequestDTO(refresh_token=ok_login.refresh_token, device_id="dev-1")
    )
    assert rotated.refresh_token != ok_login.refresh_token

    with pytest.raises(TokenReuseDetectedError):
        await refresh_uc.execute(
            RefreshTokenRequestDTO(refresh_token=ok_login.refresh_token, device_id="dev-1")
        )

    actor = ActorContext(user_id=auth_res.user_id, role=UserRole.PATIENT, device_id="dev-1")
    logout_uc = LogoutUseCase(uow_factory, tokens)
    await logout_uc.execute(actor, LogoutRequestDTO(device_id="dev-1"))


async def test_patient_access_patch_lww_and_erasure_unit() -> None:
    db = _InMemoryDb()
    hasher = _FakeHasher()
    tokens = _FakeTokenProvider()

    def uow_factory() -> _FakeUoW:
        return _FakeUoW(db)

    reg_uc = RegisterUseCase(uow_factory, hasher, tokens)
    patient_auth = await reg_uc.execute(
        RegisterRequestDTO(
            identifier="pasien@parkinstep.id",
            password="Password123",
            role=UserRole.PATIENT,
            device_id="dev-1",
            birth_year=1955,
            consent_skeleton_sync=True,
        )
    )
    caregiver_auth = await reg_uc.execute(
        RegisterRequestDTO(
            identifier="caregiver@parkinstep.id",
            password="Password123",
            role=UserRole.CAREGIVER,
            device_id="dev-2",
        )
    )

    patient_actor = ActorContext(
        user_id=patient_auth.user_id, role=UserRole.PATIENT, device_id="dev-1"
    )
    caregiver_actor = ActorContext(
        user_id=caregiver_auth.user_id, role=UserRole.CAREGIVER, device_id="dev-2"
    )

    get_uc = GetPatientUseCase(uow_factory)
    with pytest.raises(AuthorizationDeniedError):
        await get_uc.execute(caregiver_actor, patient_auth.user_id)

    db.grants.add((patient_auth.user_id, caregiver_auth.user_id))
    profile = await get_uc.execute(caregiver_actor, patient_auth.user_id)
    assert profile.birth_year == 1955

    update_uc = UpdatePatientUseCase(uow_factory)
    with pytest.raises(AuthorizationDeniedError):
        await update_uc.execute(
            caregiver_actor,
            patient_auth.user_id,
            PatientPatchDTO(consent_skeleton_sync=False),
        )

    with pytest.raises(StaleWriteConflictError):
        await update_uc.execute(
            patient_actor,
            patient_auth.user_id,
            PatientPatchDTO(
                display_name="Old Write",
                client_updated_at_utc=utc_now() - timedelta(minutes=5),
            ),
        )

    updated = await update_uc.execute(
        patient_actor,
        patient_auth.user_id,
        PatientPatchDTO(
            birth_year=None,
            consent_skeleton_sync=False,
            emergency_contacts=[
                EmergencyContactInputDTO(
                    contact_id=None,
                    name="Anak",
                    phone_e164="+6281234567890",
                    relation="Child",
                    is_primary=True,
                )
            ],
        ),
    )
    assert updated.birth_year is None
    assert updated.consent.consent_skeleton_sync is False
    assert len(updated.emergency_contacts) == 1

    erase_uc = ErasePatientDataUseCase(uow_factory, hasher)
    with pytest.raises(AuthorizationDeniedError):
        await erase_uc.execute(
            caregiver_actor,
            patient_auth.user_id,
            PatientEraseRequestDTO(password="Password123"),
        )
    with pytest.raises(ReauthRequiredError):
        await erase_uc.execute(
            patient_actor,
            patient_auth.user_id,
            PatientEraseRequestDTO(password="wrong-password"),
        )

    await erase_uc.execute(
        patient_actor,
        patient_auth.user_id,
        PatientEraseRequestDTO(password="Password123"),
    )
    assert patient_auth.user_id not in db.patients
    assert patient_auth.user_id not in db.users
