import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # noqa: F401
from app.models.schema import TargetSchema
from app.models.run import PipelineRun, StageResult
from app.models.mapping import FieldMapping
from app.models.audit import AuditEvent
from app.agents.transform import run_build


@pytest.mark.asyncio
async def test_run_build_creates_stage_result():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as s:
        ts = TargetSchema(
            name="test", version="1.0",
            definition={"type": "object", "properties": {"policyNumber": {"type": "string"}}},
        )
        s.add(ts)
        await s.commit()
        await s.refresh(ts)

        run = PipelineRun(
            source_filename="test.xml",
            source_xml="<Policy><Num>123</Num></Policy>",
            target_schema_id=ts.id,
        )
        s.add(run)
        await s.commit()
        await s.refresh(run)
        run_id = run.id

        fm = FieldMapping(
            run_id=run_id,
            source_path="Policy.Num",
            target_path="policyNumber",
            transform=None,
            status="approved",
        )
        s.add(fm)
        await s.flush()

        spec = await run_build(run_id, s)
        await s.commit()

        assert len(spec.mappings) == 1
        assert spec.mappings[0].target_path == "policyNumber"

        stage = (await s.exec(
            select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "build")
        )).first()
        assert stage is not None
        assert stage.status == "approved"
        assert "spec" in stage.payload

        audit = (await s.exec(
            select(AuditEvent).where(AuditEvent.run_id == run_id, AuditEvent.action == "build_completed")
        )).first()
        assert audit is not None
