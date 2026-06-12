import pytest
import json
from pathlib import Path
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # noqa: F401
from app.models.audit import LLMCall
from app.agents.base import ExtractedField, FieldMappingProposal
from app.agents.map import propose_mappings

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"


@pytest.mark.asyncio
async def test_propose_mappings_returns_proposals_and_logs():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    fields = [
        ExtractedField(path="Policy.PolNumber", value="POL-001", inferred_type="str"),
        ExtractedField(path="Policy.FaceAmt", value="500000.00", inferred_type="number"),
        ExtractedField(path="Person.FirstName", value="Jane", inferred_type="str"),
    ]
    target_schema = json.loads((_SCHEMAS / "target_distributor_a.json").read_text())

    async with AsyncSession(engine) as s:
        proposals = await propose_mappings(
            fields, target_schema, run_id=None, session=s, mode="test"
        )
        await s.commit()
        assert isinstance(proposals, list)
        assert len(proposals) > 0
        assert all(isinstance(p, FieldMappingProposal) for p in proposals)
        rows = (await s.exec(select(LLMCall))).all()
        assert len(rows) == 1
