import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.seed import seed_target_schemas


@pytest.mark.asyncio
async def test_seed_creates_two_schemas():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine) as s:
        await seed_target_schemas(s)
        await s.commit()
        rows = (await s.exec(select(TargetSchema))).all()
        names = {r.name for r in rows}
        assert "distributor_a" in names
        assert "distributor_b" in names
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine) as s:
        await seed_target_schemas(s)
        await s.commit()
        await seed_target_schemas(s)
        await s.commit()
        rows = (await s.exec(select(TargetSchema))).all()
        assert len(rows) == 2
