import pytest
from pathlib import Path
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.models.run import PipelineRun, StageResult
from app.models.mapping import FieldMapping
from app.models.audit import AuditEvent
from app.graph.build import start_run, resume_run

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"
_XML = (_SCHEMAS / "acord_life_sample.xml").read_text()


@pytest.mark.asyncio
async def test_graph_extract_gate():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as s:
        import json
        schema_def = json.loads((_SCHEMAS / "target_distributor_a.json").read_text())
        ts = TargetSchema(name="distributor_a", version="1.0", definition=schema_def)
        s.add(ts)
        await s.commit()
        await s.refresh(ts)

        run = PipelineRun(
            source_filename="acord_life_sample.xml",
            source_xml=_XML,
            target_schema_id=ts.id,
        )
        s.add(run)
        await s.commit()
        await s.refresh(run)

        checkpointer = MemorySaver()
        await start_run(run.id, s, checkpointer=checkpointer, mode="test")
        await s.commit()

        await s.refresh(run)
        # After start_run: paused at extract gate
        assert run.status == "awaiting_review"
        assert run.thread_id is not None

        stages = (await s.exec(select(StageResult).where(StageResult.run_id == run.id))).all()
        stage_names = {st.stage: st for st in stages}
        assert "extract" in stage_names
        assert stage_names["extract"].status == "awaiting_review"
        # interpret and map not reached yet
        assert "map" not in stage_names

        # No mappings yet — map_node hasn't run
        mappings = (await s.exec(select(FieldMapping).where(FieldMapping.run_id == run.id))).all()
        assert len(mappings) == 0

        events = (await s.exec(select(AuditEvent).where(AuditEvent.run_id == run.id))).all()
        assert len(events) > 0

    # Approve extract and interpret to reach map gate
    async with AsyncSession(engine) as s:
        await resume_run(run.id, "approve", s, checkpointer=checkpointer, mode="test", stage="extract")
        await s.commit()

    async with AsyncSession(engine) as s:
        await resume_run(run.id, "approve", s, checkpointer=checkpointer, mode="test", stage="interpret")
        await s.commit()

        run = (await s.exec(select(PipelineRun).where(PipelineRun.id == run.id))).first()
        assert run.status == "awaiting_review"

        stages = (await s.exec(select(StageResult).where(StageResult.run_id == run.id))).all()
        stage_names = {st.stage: st for st in stages}
        assert "map" in stage_names
        assert stage_names["map"].status == "awaiting_review"

        mappings = (await s.exec(select(FieldMapping).where(FieldMapping.run_id == run.id))).all()
        assert len(mappings) > 0
        assert all(m.status == "proposed" for m in mappings)
