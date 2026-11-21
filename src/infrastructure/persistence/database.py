from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_async_engine_from_url(database_url: str) -> AsyncEngine:
    """Create SQLAlchemy AsyncEngine with pre-ping and SQLite FK cascade enforcement."""
    is_sqlite = database_url.startswith("sqlite")
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_async_engine(database_url, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory with expire_on_commit disabled."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
