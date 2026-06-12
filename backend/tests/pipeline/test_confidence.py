from app.pipeline.confidence import score_mapping


def test_exact_type_and_name_match_scores_high():
    s = score_mapping(
        source_path="Policy.PolicyNumber", source_type="str",
        target_path="policyNumber", target_type="string",
        target_required=True, target_enum=None, value="A123",
        llm_confidence=0.9,
    )
    assert s.score >= 0.8
    assert s.flags == []


def test_type_mismatch_lowers_and_flags():
    s = score_mapping(
        source_path="Policy.FaceAmount", source_type="str",
        target_path="faceAmount", target_type="number",
        target_required=True, target_enum=None, value="not-a-number",
        llm_confidence=0.9,
    )
    assert s.score < 0.8
    assert "type_mismatch" in s.flags


def test_required_missing_flags():
    s = score_mapping(
        source_path="Policy.Name", source_type="str",
        target_path="name", target_type="string",
        target_required=True, target_enum=None, value="",
        llm_confidence=0.5,
    )
    assert "required_missing" in s.flags


def test_enum_violation_flags():
    s = score_mapping(
        source_path="Policy.Status", source_type="str",
        target_path="status", target_type="string",
        target_required=False, target_enum=["active", "inactive"], value="unknown",
        llm_confidence=0.8,
    )
    assert "enum_violation" in s.flags


def test_enum_valid_no_flag():
    s = score_mapping(
        source_path="Policy.Status", source_type="str",
        target_path="status", target_type="string",
        target_required=False, target_enum=["active", "inactive"], value="active",
        llm_confidence=0.9,
    )
    assert "enum_violation" not in s.flags


def test_numeric_value_coerces_to_number():
    s = score_mapping(
        source_path="Policy.Amount", source_type="str",
        target_path="amount", target_type="number",
        target_required=False, target_enum=None, value="123.45",
        llm_confidence=0.85,
    )
    assert "type_mismatch" not in s.flags
    assert s.score >= 0.7
