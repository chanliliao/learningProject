import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.models.run import PipelineRun, StageResult
from app.graph.build import start_run, resume_run

_SCHEMA = {
    "type": "object",
    "required": ["policyNumber"],
    "properties": {"policyNumber": {"type": "string"}},
}
_XML = """<Policy><PolNumber>POL-001</PolNumber></Policy>"""


@pytest.mark.asyncio
async def test_resume_approve_completes_run():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    checkpointer = MemorySaver()

    async with AsyncSession(engine) as s:
        ts = TargetSchema(name="test", version="1.0", definition=_SCHEMA)
        s.add(ts)
        await s.commit()
        await s.refresh(ts)
        ts_id = ts.id

        run = PipelineRun(source_filename="t.xml", source_xml=_XML, target_schema_id=ts_id)
        s.add(run)
        await s.commit()
        await s.refresh(run)
        run_id = run.id

        await start_run(run_id, s, checkpointer=checkpointer, mode="test")
        await s.commit()

        await s.refresh(run)
        assert run.status == "awaiting_review"

    # Approve extract gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="extract")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "awaiting_review"

    # Approve interpret gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="interpret")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "awaiting_review"

    # Approve map gate — graph runs build+test, pauses at test gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="map")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "awaiting_review"

        map_stage = (await s.exec(
            select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "map")
        )).first()
        assert map_stage is not None
        assert map_stage.status == "approved"

    # Approve test gate — graph completes
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="test")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "completed"


@pytest.mark.asyncio
async def test_resume_reject_marks_run_failed():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    checkpointer = MemorySaver()

    async with AsyncSession(engine) as s:
        ts = TargetSchema(name="test2", version="1.0", definition=_SCHEMA)
        s.add(ts)
        await s.commit()
        await s.refresh(ts)
        ts_id = ts.id

        run = PipelineRun(source_filename="t.xml", source_xml=_XML, target_schema_id=ts_id)
        s.add(run)
        await s.commit()
        await s.refresh(run)
        run_id = run.id

        await start_run(run_id, s, checkpointer=checkpointer, mode="test")
        await s.commit()

    # Reject at extract gate (first gate)
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="reject", session=s, checkpointer=checkpointer, stage="extract")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "failed"

        extract_stage = (await s.exec(
            select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "extract")
        )).first()
        assert extract_stage is not None
        assert extract_stage.status == "rejected"
