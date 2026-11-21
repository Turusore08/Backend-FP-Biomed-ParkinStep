from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import IdempotencyRecord
from src.domain.enums import IdempotencyState
from src.domain.value_objects import utc_now
from src.infrastructure.persistence.models import IdempotencyKeyORM


def _to_entity(row: IdempotencyKeyORM) -> IdempotencyRecord:
    return IdempotencyRecord(
        actor_user_id=row.actor_user_id,
        method=row.method,
        path=row.path,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        state=IdempotencyState(row.state),
        status_code=row.status_code,
        response_body=row.response_body,
        created_at_utc=row.created_at_utc,
        expires_at_utc=row.expires_at_utc,
    )


class SqlIdempotencyRepository:
    """SQLAlchemy async repository for idempotent request locks and cached responses."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_acquire(
        self,
        record: IdempotencyRecord,
    ) -> tuple[bool, IdempotencyRecord | None]:
        row = IdempotencyKeyORM(
            actor_user_id=record.actor_user_id,
            method=record.method,
            path=record.path,
            idempotency_key=record.idempotency_key,
            request_hash=record.request_hash,
            state=record.state.value,
            status_code=record.status_code,
            response_body=record.response_body,
            created_at_utc=record.created_at_utc,
            expires_at_utc=record.expires_at_utc,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
            return True, None
        except IntegrityError:
            existing = await self.get(
                record.actor_user_id,
                record.method,
                record.path,
                record.idempotency_key,
            )
            if existing is not None and existing.expires_at_utc <= utc_now():
                await self._session.execute(
                    delete(IdempotencyKeyORM).where(
                        and_(
                            IdempotencyKeyORM.actor_user_id == record.actor_user_id,
                            IdempotencyKeyORM.method == record.method,
                            IdempotencyKeyORM.path == record.path,
                            IdempotencyKeyORM.idempotency_key == record.idempotency_key,
                        )
                    )
                )
                async with self._session.begin_nested():
                    self._session.add(row)
                    await self._session.flush()
                return True, None
            return False, existing

    async def get(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> IdempotencyRecord | None:
        stmt = select(IdempotencyKeyORM).where(
            and_(
                IdempotencyKeyORM.actor_user_id == actor_user_id,
                IdempotencyKeyORM.method == method,
                IdempotencyKeyORM.path == path,
                IdempotencyKeyORM.idempotency_key == idempotency_key,
            )
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def mark_completed(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
        status_code: int,
        response_body: dict[str, Any] | list[Any] | None,
    ) -> None:
        stmt = (
            update(IdempotencyKeyORM)
            .where(
                and_(
                    IdempotencyKeyORM.actor_user_id == actor_user_id,
                    IdempotencyKeyORM.method == method,
                    IdempotencyKeyORM.path == path,
                    IdempotencyKeyORM.idempotency_key == idempotency_key,
                )
            )
            .values(
                state=IdempotencyState.COMPLETED.value,
                status_code=status_code,
                response_body=response_body,
            )
        )
        await self._session.execute(stmt)

    async def delete_in_progress(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> None:
        stmt = delete(IdempotencyKeyORM).where(
            and_(
                IdempotencyKeyORM.actor_user_id == actor_user_id,
                IdempotencyKeyORM.method == method,
                IdempotencyKeyORM.path == path,
                IdempotencyKeyORM.idempotency_key == idempotency_key,
                IdempotencyKeyORM.state == IdempotencyState.IN_PROGRESS.value,
            )
        )
        await self._session.execute(stmt)

    async def purge_for_actor(self, actor_user_id: UUID) -> None:
        await self._session.execute(
            delete(IdempotencyKeyORM).where(IdempotencyKeyORM.actor_user_id == actor_user_id)
        )
