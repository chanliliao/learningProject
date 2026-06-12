from sqlmodel import SQLModel, Session, create_engine
from app.models.schema import TargetSchema
from app.models.run import PipelineRun
from app.models.mapping import FieldMapping


def test_field_mapping_persists():
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

        fm = FieldMapping(
            run_id=run.id,
            source_path="Policy.PolicyNumber",
            target_path="policyNumber",
            transform=None,
            confidence=None,
            flags=["missing_transform"],
        )
        s.add(fm)
        s.commit()
        s.refresh(fm)
        assert fm.id is not None
        assert fm.status == "proposed"
        assert fm.flags == ["missing_transform"]
        assert fm.confidence is None
