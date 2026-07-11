import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    from src.core.database import init_db, Base

    engine = await init_db("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn:
        for table_name in ("tasks", "alerts"):
            result = await conn.run_sync(
                lambda sc, tn=table_name: sc.execute(
                    select(func.count()).select_from(Base.metadata.tables[tn])
                )
            )
            assert result.scalar_one() == 0, f"table {table_name} should exist and be empty"


@pytest.mark.asyncio
async def test_task_orm_insert_and_query():
    from src.core.database import init_db, Task

    engine = await init_db("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        task = Task(
            id="t-001",
            camera_id="cam-01",
            path_taken="fast",
            status="queued",
        )
        session.add(task)
        await session.commit()

    async with factory() as session:
        t = await session.get(Task, "t-001")
        assert t is not None
        assert t.camera_id == "cam-01"
        assert t.path_taken == "fast"
        assert t.status == "queued"


@pytest.mark.asyncio
async def test_alert_orm_create():
    from src.core.database import init_db, Alert

    engine = await init_db("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        alert = Alert(
            task_id="t-001",
            alert_type="intrusion",
            label="person",
            confidence=0.95,
        )
        session.add(alert)
        await session.commit()

    async with factory() as session:
        result = await session.execute(select(Alert).where(Alert.task_id == "t-001"))
        alerts = result.scalars().all()
        assert len(alerts) == 1
        assert alerts[0].label == "person"
        assert alerts[0].confidence == 0.95
