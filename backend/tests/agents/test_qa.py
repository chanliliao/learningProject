from app.agents.transform import build_transform
from app.agents.qa import run_qa_checks


def test_qa_validates_against_target_schema():
    spec = {"mappings": [
        {"source_path": "Policy.PolicyNumber", "target_path": "policyNumber", "transform": None}]}
    target_schema = {"type": "object", "required": ["policyNumber"],
                     "properties": {"policyNumber": {"type": "string"}}}
    samples = [{"Policy.PolicyNumber": "A1"}, {"Policy.PolicyNumber": ""}]
    report = run_qa_checks(spec, target_schema, samples)
    assert report.total >= 2
    assert report.passed >= 1
    assert any(not c.ok for c in report.cases)


def test_qa_all_pass():
    spec = build_transform([{"source_path": "s", "target_path": "name", "transform": None}])
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    samples = [{"s": "Alice"}, {"s": "Bob"}, {"s": "Carol"}]
    report = run_qa_checks(spec, schema, samples)
    assert report.passed == report.total


def test_qa_auto_generates_edge_samples_when_few():
    spec = build_transform([{"source_path": "s", "target_path": "name", "transform": None}])
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    report = run_qa_checks(spec, schema, [{"s": "only_one"}])
    assert report.total > 1  # auto-generated edges added
