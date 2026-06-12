import pytest
import json
from pathlib import Path
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
from qdrant_client import QdrantClient
from llama_index.core.embeddings import MockEmbedding
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.models.run import PipelineRun, StageResult
from app.graph.build import start_run, resume_run
from app.rag.index import query_run

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"
_XML = (_SCHEMAS / "acord_life_sample.xml").read_text()


@pytest.mark.asyncio
async def test_completed_run_is_indexed():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    qdrant = QdrantClient(location=":memory:")
    embed = MockEmbedding(embed_dim=8)

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
        await s.flush()  # assigns run.id without expiring
        run_id = run.id
        await s.commit()

        checkpointer = MemorySaver()
        await start_run(run_id, s, checkpointer=checkpointer, mode="test")
        await s.commit()

        # Approve all 4 gates to reach completion
        await resume_run(run_id, "approve", s, checkpointer=checkpointer, stage="extract")
        await s.commit()
        await resume_run(run_id, "approve", s, checkpointer=checkpointer, stage="interpret")
        await s.commit()
        await resume_run(run_id, "approve", s, checkpointer=checkpointer, stage="map")
        await s.commit()
        await resume_run(run_id, "approve", s, checkpointer=checkpointer, stage="test",
                         qdrant_client=qdrant, embed_model=embed)
        await s.commit()

        await s.refresh(run)
        assert run.status == "completed"

        # Collection should exist and return nodes
        nodes = query_run(run_id, "policy number", client=qdrant, embed_model=embed)
        assert len(nodes) > 0
