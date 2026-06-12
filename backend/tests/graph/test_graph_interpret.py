import pytest
import json
from pathlib import Path
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.models.run import PipelineRun, StageResult
from app.graph.build import start_run, resume_run

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"
_XML = (_SCHEMAS / "acord_life_sample.xml").read_text()


@pytest.mark.asyncio
async def test_graph_has_interpret_stage():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    checkpointer = MemorySaver()

    async with AsyncSession(engine) as s:
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
        await s.refresh(ts)
        await s.refresh(run)
        run_id = run.id

        # start_run pauses at extract gate
        await start_run(run_id, s, checkpointer=checkpointer, mode="test")
        await s.commit()

    # Approve extract — resumes to interpret gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, "approve", s, checkpointer=checkpointer, mode="test", stage="extract")
        await s.commit()

    # Approve interpret — resumes to map gate
    async with AsyncSession(engine) as s:
        await resume_run(run_id, "approve", s, checkpointer=checkpointer, mode="test", stage="interpret")
        await s.commit()

        stages = (await s.exec(select(StageResult).where(StageResult.run_id == run_id))).all()
        stage_names = {st.stage: st for st in stages}

        assert "extract" in stage_names
        assert "interpret" in stage_names
        assert "map" in stage_names

        # Order: extract created before interpret, interpret before map
        extract_id = stage_names["extract"].id
        interpret_id = stage_names["interpret"].id
        map_id = stage_names["map"].id
        assert extract_id < interpret_id < map_id
