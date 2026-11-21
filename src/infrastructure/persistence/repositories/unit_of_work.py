from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.interfaces import (
    IdempotencyRepository,
    PatientRepository,
    RefreshTokenRepository,
    UserRepository,
)
from src.infrastructure.persistence.repositories.sql_auth_repository import (
    SqlRefreshTokenRepository,
    SqlUserRepository,
)
from src.infrastructure.persistence.repositories.sql_idempotency_repository import (
    SqlIdempotencyRepository,
)
from src.infrastructure.persistence.repositories.sql_patient_repository import (
    SqlPatientRepository,
)


class SqlAlchemyUnitOfWork:
    """Async SQLAlchemy Unit of Work managing transactional repository boundaries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.users: UserRepository
        self.refresh_tokens: RefreshTokenRepository
        self.patients: PatientRepository
        self.idempotency: IdempotencyRepository

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.users = SqlUserRepository(self._session)
        self.refresh_tokens = SqlRefreshTokenRepository(self._session)
        self.patients = SqlPatientRepository(self._session)
        self.idempotency = SqlIdempotencyRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._session is None:
            return
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()
