from app.agents.base import ExtractedField, FieldMappingProposal, ExtractError


def test_extracted_field():
    f = ExtractedField(path="Policy.PolNumber", value="POL-001", inferred_type="str")
    assert f.path == "Policy.PolNumber"
    assert f.value == "POL-001"
    assert f.inferred_type == "str"


def test_field_mapping_proposal():
    p = FieldMappingProposal(
        source_path="Policy.FaceAmt",
        target_path="faceAmount",
        transform=None,
        llm_confidence=0.9,
    )
    assert p.source_path == "Policy.FaceAmt"
    assert p.llm_confidence == 0.9


def test_extract_error_is_exception():
    assert issubclass(ExtractError, Exception)
    e = ExtractError("bad xml")
    assert str(e) == "bad xml"
