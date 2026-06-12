from sqlmodel import SQLModel, Session, create_engine
from app.models.schema import TargetSchema
from app.models.run import PipelineRun
from app.models.mapping import FieldMapping
from app.models.audit import AuditEvent, ReviewAction, LLMCall


def test_audit_models_persist():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        schema = TargetSchema(name="acme", version="1.0", definition={})
        s.add(schema)
        s.commit()
        s.refresh(schema)

        run = PipelineRun(source_filename="f.xml", source_xml="<x/>", target_schema_id=schema.id)
        s.add(run)
        s.commit()
        s.refresh(run)

        event = AuditEvent(
            run_id=run.id,
            actor="system",
            action="map_proposed",
            before={"status": "running"},
            after={"status": "awaiting_review"},
        )
        s.add(event)
        s.commit()
        s.refresh(event)
        assert event.id is not None
        assert event.before["status"] == "running"
        assert event.after["status"] == "awaiting_review"

        fm = FieldMapping(run_id=run.id, source_path="a", target_path="b")
        s.add(fm)
        s.commit()
        s.refresh(fm)

        review = ReviewAction(
            run_id=run.id,
            stage="map",
            field_mapping_id=fm.id,
            reviewer="user@test.com",
            decision="approve",
        )
        s.add(review)
        s.commit()
        s.refresh(review)
        assert review.id is not None

        call = LLMCall(
            run_id=run.id,
            stage="map",
            model="test-model",
            prompt="hello",
            response="world",
            langfuse_trace_id="trace-abc",
        )
        s.add(call)
        s.commit()
        s.refresh(call)
        assert call.id is not None
        assert call.langfuse_trace_id == "trace-abc"
