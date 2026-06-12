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
async def test_full_graph_four_approvals():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    checkpointer = MemorySaver()

    async with AsyncSession(engine) as s:
        ts = TargetSchema(name="test", version="1.0", definition=_SCHEMA)
        s.add(ts)
        await s.commit()
        await s.refresh(ts)

        run = PipelineRun(source_filename="t.xml", source_xml=_XML, target_schema_id=ts.id)
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
        assert run.status == "awaiting_review", f"Expected awaiting_review after map approve, got {run.status}"

        build_stage = (await s.exec(
            select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "build")
        )).first()
        assert build_stage is not None
        assert build_stage.status == "approved"

        test_stage = (await s.exec(
            select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "test")
        )).first()
        assert test_stage is not None
        assert test_stage.status == "awaiting_review"

    # Approve test gate — run completes
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="test")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "completed"


@pytest.mark.asyncio
async def test_full_graph_reject_at_map():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    checkpointer = MemorySaver()

    async with AsyncSession(engine) as s:
        ts = TargetSchema(name="test_rej", version="1.0", definition=_SCHEMA)
        s.add(ts)
        await s.commit()
        await s.refresh(ts)

        run = PipelineRun(source_filename="t.xml", source_xml=_XML, target_schema_id=ts.id)
        s.add(run)
        await s.commit()
        await s.refresh(run)
        run_id = run.id

        await start_run(run_id, s, checkpointer=checkpointer, mode="test")
        await s.commit()

    # Step through extract and interpret to reach map gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="extract")
        await s.commit()

    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="approve", session=s, checkpointer=checkpointer, stage="interpret")
        await s.commit()

    # Reject at map gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, decision="reject", session=s, checkpointer=checkpointer, stage="map")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
        assert run.status == "failed"

        map_stage = (await s.exec(
            select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "map")
        )).first()
        assert map_stage is not None
        assert map_stage.status == "rejected"
