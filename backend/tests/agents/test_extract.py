import pytest
from pathlib import Path
from app.agents.extract import extract
from app.agents.base import ExtractedField, ExtractError

_SCHEMAS = Path(__file__).parent.parent.parent / "app" / "schemas"


def test_extract_life_xml_returns_fields():
    xml = (_SCHEMAS / "acord_life_sample.xml").read_text()
    fields = extract(xml)
    assert len(fields) > 0
    assert all(isinstance(f, ExtractedField) for f in fields)
    paths = [f.path for f in fields]
    assert any("PolNumber" in p for p in paths)
    assert any("LastName" in p for p in paths)
    non_empty = [f for f in fields if f.value.strip()]
    assert len(non_empty) > 0


def test_extract_infers_types():
    xml = (_SCHEMAS / "acord_life_sample.xml").read_text()
    fields = extract(xml)
    by_path = {f.path: f for f in fields}
    face_amt = next((f for f in fields if "FaceAmt" in f.path), None)
    assert face_amt is not None
    assert face_amt.inferred_type == "number"
    issue_date = next((f for f in fields if "IssueDate" in f.path), None)
    assert issue_date is not None
    assert issue_date.inferred_type == "date"


def test_extract_raises_on_malformed_xml():
    with pytest.raises(ExtractError):
        extract("<<<not valid xml>>>")


def test_extract_raises_on_empty_document():
    with pytest.raises(ExtractError):
        extract("")
