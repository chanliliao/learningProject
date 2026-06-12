import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from qdrant_client import QdrantClient
from llama_index.core.embeddings import MockEmbedding
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.main import app
from app.db import get_session
from app.routers.pipeline import get_checkpointer, get_llm_mode
from app.models.schema import TargetSchema

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"
_XML_BYTES = (_SCHEMAS / "acord_life_sample.xml").read_bytes()

_CHECKPOINTERS: dict = {}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_engine():
    return create_async_engine("sqlite+aiosqlite://", echo=False)


def _seed_schema(engine) -> int:
    import json
    async def _inner():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as s:
            schema_def = json.loads((_SCHEMAS / "target_distributor_a.json").read_text())
            ts = TargetSchema(name="distributor_a", version="1.0", definition=schema_def)
            s.add(ts)
            await s.commit()
            await s.refresh(ts)
            return ts.id
    return _run(_inner())


def test_support_endpoint_returns_answer():
    engine = _make_engine()
    schema_id = _seed_schema(engine)
    qdrant_client = QdrantClient(location=":memory:")
    embed_model = MockEmbedding(embed_dim=8)

    async def _get_session():
        async with AsyncSession(engine) as s:
            yield s

    checkpointer = MemorySaver()
    _CHECKPOINTERS["test"] = checkpointer

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer
    app.dependency_overrides[get_llm_mode] = lambda: "test"

    client = TestClient(app)

    # Start a run and get it to completed state
    with open(_SCHEMAS / "acord_life_sample.xml", "rb") as f:
        resp = client.post(
            "/api/runs",
            files={"file": ("acord_life_sample.xml", f, "text/xml")},
            data={"target_schema_id": str(schema_id)},
        )
    assert resp.status_code in (200, 201)
    run_id = resp.json()["run_id"]

    # Step through all 4 gates to reach completed state
    client.post(f"/api/runs/{run_id}/stages/extract/approve")
    client.post(f"/api/runs/{run_id}/stages/interpret/approve")
    client.post(f"/api/runs/{run_id}/stages/map/approve")
    client.post(f"/api/runs/{run_id}/stages/test/approve")

    # Index the run manually (inject in-memory client/embed for test)
    async def _index():
        from app.rag.index import index_run
        await index_run(
            run_id,
            ["FaceAmt maps to faceAmount. Death benefit."],
            client=qdrant_client,
            embed_model=embed_model,
        )
    _run(_index())

    # Inject the qdrant client into support router override
    from app.routers import support as support_router
    app.dependency_overrides[support_router.get_qdrant_client] = lambda: qdrant_client
    app.dependency_overrides[support_router.get_embed_model] = lambda: embed_model

    resp = client.post(
        f"/api/runs/{run_id}/support",
        json={"question": "why is faceAmount mapped?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert isinstance(body["answer"], str)
    assert len(body["answer"]) > 0

    app.dependency_overrides.clear()


def test_support_missing_run_returns_404():
    engine = _make_engine()
    _seed_schema(engine)

    async def _get_session():
        async with AsyncSession(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _get_session

    client = TestClient(app)
    resp = client.post("/runs/99999/support", json={"question": "test?"})
    assert resp.status_code == 404

    app.dependency_overrides.clear()
