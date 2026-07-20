import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.deps import _session_factory, init_session_factory
from src.core.database import Base

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)


@pytest.fixture(scope="session", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
async def _auto_init_db() -> None:
    prev = _session_factory
    if prev is None:
        factory = async_sessionmaker(_engine, expire_on_commit=False)
        init_session_factory(factory)
    yield
    init_session_factory(prev)


@pytest.fixture(autouse=True)
def _reset_redis():
    yield
    import src.core.redis_client as rc
    rc._redis = None
    rc._redis_loop_id = None
    rc._redis_unavailable = False
