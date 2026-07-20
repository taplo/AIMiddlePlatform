import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.api.deps import _session_factory, init_session_factory
from src.core.database import init_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def _auto_init_db() -> AsyncIterator[None]:
    prev = _session_factory
    if prev is None:
        engine = await init_db("sqlite+aiosqlite://")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        init_session_factory(factory)
    yield
    if prev is None:
        init_session_factory(None)
    else:
        init_session_factory(prev)
