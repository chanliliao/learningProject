import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # noqa: F401
from app.models.audit import LLMCall
from app.agents.base import ExtractedField, InterpretedField
from app.agents.interpret import interpret_fields


@pytest.mark.asyncio
async def test_interpret_fields_returns_interpreted_and_logs():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    fields = [
        ExtractedField(path="Policy.PolNumber", value="POL-001", inferred_type="str"),
        ExtractedField(path="Policy.FaceAmt", value="500000.00", inferred_type="number"),
        ExtractedField(path="Person.FirstName", value="Jane", inferred_type="str"),
    ]

    async with AsyncSession(engine) as s:
        result = await interpret_fields(fields, run_id=None, session=s, mode="test")
        await s.commit()

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(f, InterpretedField) for f in result)

        rows = (await s.exec(select(LLMCall))).all()
        assert len(rows) == 1
