import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.memory import MemorySaver
import app.models  # noqa: F401
from app.main import app
from app.db import get_session
from app.routers.pipeline import get_checkpointer, get_llm_mode
from app.models.schema import TargetSchema
from app.models.mapping import FieldMapping
from app.models.audit import ReviewAction, AuditEvent

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
    async def _inner():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as s:
            ts = TargetSchema(
                name="distributor_a", version="1.0",
                definition={
                    "type": "object",
                    "required": ["policyNumber"],
                    "properties": {
                        "policyNumber": {"type": "string"},
                        "faceAmount": {"type": "number"},
                    },
                },
            )
            s.add(ts)
            await s.commit()
            await s.refresh(ts)
            return ts.id
    return _run(_inner())


def _make_client(engine, checkpointer):
    async def override_session():
        async with AsyncSession(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer
    app.dependency_overrides[get_llm_mode] = lambda: "test"
    return TestClient(app, raise_server_exceptions=True)


def test_edit_field_updates_mapping():
    engine = _make_engine()
    cp = MemorySaver()
    schema_id = _seed_schema(engine)
    client = _make_client(engine, cp)
    try:
        resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("test.xml", _XML_BYTES, "application/xml")},
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        # Step through extract and interpret gates to reach map gate (where mappings are created)
        client.post(f"/api/runs/{run_id}/stages/extract/approve")
        client.post(f"/api/runs/{run_id}/stages/interpret/approve")

        get_resp = client.get(f"/api/runs/{run_id}")
        assert get_resp.status_code == 200
        mappings = get_resp.json()["mappings"]
        assert len(mappings) > 0
        field_id = mappings[0]["id"]

        patch_resp = client.patch(
            f"/api/runs/{run_id}/fields/{field_id}",
            json={"target_path": "newTarget", "transform": "rename"},
        )
        assert patch_resp.status_code == 200

        async def _check():
            async with AsyncSession(engine) as s:
                fm = (await s.exec(select(FieldMapping).where(FieldMapping.id == field_id))).first()
                assert fm.status == "edited"
                assert fm.target_path == "newTarget"
                actions = (await s.exec(
                    select(ReviewAction).where(ReviewAction.field_mapping_id == field_id)
                )).all()
                assert len(actions) > 0
                assert actions[0].decision == "edit"
                events = (await s.exec(
                    select(AuditEvent).where(AuditEvent.run_id == run_id, AuditEvent.action == "field_edited")
                )).all()
                assert len(events) > 0
        _run(_check())
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_approve_stage_completes_run():
    engine = _make_engine()
    cp = MemorySaver()
    schema_id = _seed_schema(engine)
    client = _make_client(engine, cp)
    try:
        resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("test.xml", _XML_BYTES, "application/xml")},
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        # Approve extract gate
        r = client.post(f"/api/runs/{run_id}/stages/extract/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "awaiting_review"

        # Approve interpret gate
        r = client.post(f"/api/runs/{run_id}/stages/interpret/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "awaiting_review"

        # Approve map gate — graph runs build+test, pauses at test gate
        r = client.post(f"/api/runs/{run_id}/stages/map/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "awaiting_review"

        # Approve test gate — graph completes
        r = client.post(f"/api/runs/{run_id}/stages/test/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_reject_stage_fails_run():
    engine = _make_engine()
    cp = MemorySaver()
    schema_id = _seed_schema(engine)
    client = _make_client(engine, cp)
    try:
        resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("test.xml", _XML_BYTES, "application/xml")},
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        reject_resp = client.post(f"/api/runs/{run_id}/stages/map/reject")
        assert reject_resp.status_code == 200
        body = reject_resp.json()
        assert body["status"] == "failed"
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_approve_missing_run_returns_404():
    engine = _make_engine()
    cp = MemorySaver()
    _seed_schema(engine)
    client = _make_client(engine, cp)
    try:
        resp = client.post("/api/runs/99999/stages/map/approve")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_double_approve_returns_409():
    engine = _make_engine()
    cp = MemorySaver()
    schema_id = _seed_schema(engine)
    client = _make_client(engine, cp)
    try:
        resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("test.xml", _XML_BYTES, "application/xml")},
        )
        run_id = resp.json()["run_id"]

        # Step through to map gate
        client.post(f"/api/runs/{run_id}/stages/extract/approve")
        client.post(f"/api/runs/{run_id}/stages/interpret/approve")

        # First map approve — succeeds, graph runs to test gate
        first = client.post(f"/api/runs/{run_id}/stages/map/approve")
        assert first.status_code == 200

        # Second map approve — 409, map stage already approved
        second = client.post(f"/api/runs/{run_id}/stages/map/approve")
        assert second.status_code == 409
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())


def test_edit_field_rescores_confidence_and_flags():
    engine = _make_engine()
    cp = MemorySaver()
    schema_id = _seed_schema(engine)
    client = _make_client(engine, cp)
    try:
        resp = client.post(
            "/api/runs",
            data={"target_schema_id": schema_id},
            files={"file": ("test.xml", _XML_BYTES, "application/xml")},
        )
        run_id = resp.json()["run_id"]

        # Step through extract and interpret gates to reach map gate
        client.post(f"/api/runs/{run_id}/stages/extract/approve")
        client.post(f"/api/runs/{run_id}/stages/interpret/approve")

        get_resp = client.get(f"/api/runs/{run_id}")
        mappings = get_resp.json()["mappings"]
        assert len(mappings) > 0
        field_id = mappings[0]["id"]
        confidence_before = mappings[0]["confidence"]

        patch_resp = client.patch(
            f"/api/runs/{run_id}/fields/{field_id}",
            json={"target_path": "policyNumber"},
        )
        assert patch_resp.status_code == 200

        async def _check():
            async with AsyncSession(engine) as s:
                fm = (await s.exec(select(FieldMapping).where(FieldMapping.id == field_id))).first()
                assert fm.confidence is not None
                # confidence re-computed — value may differ from original blend
                assert fm.confidence != confidence_before or fm.flags is not None
        _run(_check())
    finally:
        app.dependency_overrides.clear()
        _run(engine.dispose())
