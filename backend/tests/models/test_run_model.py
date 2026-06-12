from sqlmodel import SQLModel, Session, create_engine, select
from app.models.schema import TargetSchema
from app.models.run import PipelineRun, StageResult


def test_pipeline_run_and_stage_result_persist():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        schema = TargetSchema(name="acme", version="1.0", definition={})
        s.add(schema)
        s.commit()
        s.refresh(schema)

        run = PipelineRun(
            source_filename="test.xml",
            source_xml="<xml/>",
            target_schema_id=schema.id,
            thread_id="thread-abc",
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        assert run.id is not None
        assert run.status == "running"
        assert run.thread_id == "thread-abc"

        stage = StageResult(run_id=run.id, stage="extract", status="approved", payload={"count": 5})
        s.add(stage)
        s.commit()
        s.refresh(stage)
        assert stage.id is not None
        assert stage.payload["count"] == 5
