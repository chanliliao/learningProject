import pytest
from unittest.mock import patch, AsyncMock
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.models.run import PipelineRun
from app.models.mapping import FieldMapping
from app.agents.base import ExtractedField, FieldMappingProposal
from app.graph.build import start_run, resume_run

_SCHEMA_WITH_NUMBER = {
    "type": "object",
    "required": ["policyNumber", "faceAmount"],
    "properties": {
        "policyNumber": {"type": "string"},
        "faceAmount": {"type": "number"},
    },
}

_TYPED_PROPOSALS = [
    FieldMappingProposal(
        source_path="Policy.PolNumber",
        target_path="policyNumber",
        llm_confidence=0.9,
    ),
    FieldMappingProposal(
        source_path="Policy.StringAmount",
        target_path="faceAmount",
        llm_confidence=0.9,
    ),
]

_EXTRACTED = [
    ExtractedField(path="Policy.PolNumber", value="POL-001", inferred_type="str"),
    ExtractedField(path="Policy.StringAmount", value="not-a-number", inferred_type="str"),
]


@pytest.mark.asyncio
async def test_map_node_sets_confidence_and_flags():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as s:
        ts = TargetSchema(name="test", version="1.0", definition=_SCHEMA_WITH_NUMBER)
        s.add(ts)
        await s.commit()
        await s.refresh(ts)

        run = PipelineRun(
            source_filename="test.xml",
            source_xml="<root/>",
            target_schema_id=ts.id,
        )
        s.add(run)
        await s.commit()
        await s.refresh(run)
        run_id = run.id

        checkpointer = MemorySaver()
        with (
            patch("app.graph.build.extract", return_value=_EXTRACTED),
            patch("app.graph.build.propose_mappings", new=AsyncMock(return_value=_TYPED_PROPOSALS)),
        ):
            await start_run(run_id, s, checkpointer=checkpointer, mode="test")
            await s.commit()
            # step through extract and interpret gates (map_node creates FieldMappings)
            await resume_run(run_id, "approve", s, checkpointer=checkpointer, mode="test", stage="extract")
            await s.commit()
            await resume_run(run_id, "approve", s, checkpointer=checkpointer, mode="test", stage="interpret")
            await s.commit()

        mappings = (await s.exec(select(FieldMapping).where(FieldMapping.run_id == run_id))).all()
        assert len(mappings) > 0
        assert all(m.confidence is not None for m in mappings), "all mappings must have confidence set"

        by_target = {m.target_path: m for m in mappings}
        face = by_target.get("faceAmount")
        assert face is not None, "faceAmount mapping must exist"
        assert "type_mismatch" in face.flags, f"expected type_mismatch, got flags={face.flags}"
        assert face.status == "proposed"

        pol = by_target.get("policyNumber")
        assert pol is not None
        assert "type_mismatch" not in pol.flags
