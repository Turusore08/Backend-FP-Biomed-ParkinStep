import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def seed_default_model_bundle() -> None:
    """Seed the canonical B_15hz OTA manifest into model_bundles using runtime env config."""
    from src.application.use_cases.models import build_default_b15hz_manifest
    from src.domain.value_objects import utc_now
    from src.infrastructure.config import get_settings
    from src.infrastructure.persistence import create_async_engine_from_url, create_session_factory
    from src.infrastructure.persistence.repositories import SqlAlchemyUnitOfWork

    settings = get_settings()
    engine = create_async_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)
    manifest = build_default_b15hz_manifest(settings.model_cdn_base_url)

    try:
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            await uow.model_bundles.upsert(
                manifest,
                is_active=True,
                published_at_utc=utc_now(),
            )
            await uow.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_default_model_bundle())
