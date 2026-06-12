from sqlmodel import SQLModel, Session, create_engine
from app.models.schema import TargetSchema


def test_target_schema_persists():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        ts = TargetSchema(name="acme", version="1.0", definition={"type": "object"})
        s.add(ts)
        s.commit()
        s.refresh(ts)
        assert ts.id is not None
        assert ts.definition["type"] == "object"
