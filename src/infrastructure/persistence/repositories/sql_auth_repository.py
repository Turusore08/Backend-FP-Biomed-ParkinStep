from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import RefreshTokenRecord, UserAccount
from src.domain.enums import UserRole
from src.infrastructure.persistence.models import RefreshTokenORM, UserORM


def _to_user_entity(row: UserORM) -> UserAccount:
    return UserAccount(
        user_id=row.user_id,
        identifier=row.identifier,
        password_hash=row.password_hash,
        role=UserRole(row.role),
        is_active=row.is_active,
        created_at_utc=row.created_at_utc,
    )


def _to_refresh_entity(row: RefreshTokenORM) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        token_id=row.token_id,
        user_id=row.user_id,
        device_id=row.device_id,
        token_hash=row.token_hash,
        family_id=row.family_id,
        expires_at_utc=row.expires_at_utc,
        revoked_at_utc=row.revoked_at_utc,
        created_at_utc=row.created_at_utc,
    )


class SqlUserRepository:
    """SQLAlchemy async repository for UserAccount entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> UserAccount | None:
        row = await self._session.get(UserORM, user_id)
        return _to_user_entity(row) if row is not None else None

    async def get_by_identifier(self, identifier: str) -> UserAccount | None:
        stmt = select(UserORM).where(UserORM.identifier == identifier.strip().lower())
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_user_entity(row) if row is not None else None

    async def create(self, user: UserAccount) -> None:
        self._session.add(
            UserORM(
                user_id=user.user_id,
                identifier=user.identifier,
                password_hash=user.password_hash,
                role=user.role.value,
                is_active=user.is_active,
                created_at_utc=user.created_at_utc,
            )
        )
        await self._session.flush()

    async def delete_by_id(self, user_id: UUID) -> None:
        await self._session.execute(delete(UserORM).where(UserORM.user_id == user_id))


class SqlRefreshTokenRepository:
    """SQLAlchemy async repository for rotated RefreshTokenRecord entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: RefreshTokenRecord) -> None:
        self._session.add(
            RefreshTokenORM(
                token_id=token.token_id,
                user_id=token.user_id,
                device_id=token.device_id,
                token_hash=token.token_hash,
                family_id=token.family_id,
                expires_at_utc=token.expires_at_utc,
                revoked_at_utc=token.revoked_at_utc,
                created_at_utc=token.created_at_utc,
            )
        )
        await self._session.flush()

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        stmt = select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_hash)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_refresh_entity(row) if row is not None else None

    async def revoke_by_id(self, token_id: UUID, revoked_at_utc: datetime) -> None:
        stmt = (
            update(RefreshTokenORM)
            .where(
                RefreshTokenORM.token_id == token_id,
                RefreshTokenORM.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=revoked_at_utc)
        )
        await self._session.execute(stmt)

    async def revoke_family(self, family_id: UUID, revoked_at_utc: datetime) -> None:
        stmt = (
            update(RefreshTokenORM)
            .where(
                RefreshTokenORM.family_id == family_id,
                RefreshTokenORM.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=revoked_at_utc)
        )
        await self._session.execute(stmt)

    async def revoke_by_user_and_device(
        self,
        user_id: UUID,
        device_id: str,
        revoked_at_utc: datetime,
    ) -> None:
        stmt = (
            update(RefreshTokenORM)
            .where(
                RefreshTokenORM.user_id == user_id,
                RefreshTokenORM.device_id == device_id,
                RefreshTokenORM.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=revoked_at_utc)
        )
        await self._session.execute(stmt)

    async def delete_all_for_user(self, user_id: UUID) -> None:
        await self._session.execute(
            delete(RefreshTokenORM).where(RefreshTokenORM.user_id == user_id)
        )
