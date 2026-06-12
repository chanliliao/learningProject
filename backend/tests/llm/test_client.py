import pytest
from pydantic import BaseModel
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # noqa: F401
from app.models.audit import LLMCall
from app.llm.client import build_agent, run_structured


class Out(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_run_structured_uses_test_model_and_logs():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    agent = build_agent(Out, system="say hi", mode="test")
    async with AsyncSession(engine) as s:
        result = await run_structured(agent, "hello", stage="map", run_id=None, session=s)
        await s.commit()
        assert isinstance(result, Out)
        rows = (await s.exec(select(LLMCall))).all()
        assert len(rows) == 1
        assert rows[0].stage == "map"
