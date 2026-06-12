import pytest
import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.main import app
from app.db import get_session
from app.routers.pipeline import get_checkpointer, get_llm_mode
from app.models.schema import TargetSchema

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"
_XML_BYTES = (_SCHEMAS / "acord_life_sample.xml").read_bytes()


def _make_engine():
    return create_async_engine("sqlite+aiosqlite://", echo=False)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _seed_schema(engine) -> int:
    async def _inner():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as s:
            ts = TargetSchema(name="distributor_a", version="1.0", definition={"type": "object", "properties": {}})
            s.add(ts)
            await s.commit()
            await s.refresh(ts)
            return ts.id
    return _run(_inner())


def _make_client(engine):
    async def override_session():
        async with AsyncSession(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_checkpointer] = lambda: MemorySaver()
    app.dependency_overrides[get_llm_mode] = lambda: "test"
    return TestClient(app, raise_server_exceptions=True)


def test_create_run_returns_201_and_awaiting_review():
    engine = _make_engine()
    schema_id = _seed_schema(engine)
    client = _make_client(engine)
    try:
        resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("acord_life_sample.xml", _XML_BYTES, "application/xml")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "run_id" in body
        assert body["status"] == "awaiting_review"
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_get_run_returns_details():
    engine = _make_engine()
    schema_id = _seed_schema(engine)
    client = _make_client(engine)
    try:
        create_resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("acord_life_sample.xml", _XML_BYTES, "application/xml")},
        )
        assert create_resp.status_code == 201, create_resp.text
        run_id = create_resp.json()["run_id"]

        get_resp = client.get(f"/api/runs/{run_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["run"]["id"] == run_id
        assert "stage_results" in body
        assert "mappings" in body
        assert "audit" in body
        for m in body["mappings"]:
            assert "confidence" in m
            assert "flags" in m
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_list_schemas_returns_seeded_schema():
    engine = _make_engine()
    _seed_schema(engine)
    client = _make_client(engine)
    try:
        resp = client.get("/api/schemas")
        assert resp.status_code == 200
        schemas = resp.json()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "distributor_a"
        assert "id" in schemas[0]
        assert "version" in schemas[0]
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_get_run_missing_returns_404():
    engine = _make_engine()

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    _run(setup())

    client = _make_client(engine)
    try:
        resp = client.get("/api/runs/99999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())
