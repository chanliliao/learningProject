import pytest
from app.agents.transform import build_transform, apply_transform, TransformError


def test_apply_maps_and_coerces():
    mappings = [
        {"source_path": "Policy.PolicyNumber", "target_path": "policyNumber", "transform": None},
        {"source_path": "Policy.FaceAmount", "target_path": "faceAmount", "transform": "to_number"},
    ]
    spec = build_transform(mappings)
    source = {"Policy.PolicyNumber": "A123", "Policy.FaceAmount": "100000"}
    out = apply_transform(spec, source)
    assert out == {"policyNumber": "A123", "faceAmount": 100000}


def test_apply_uppercase():
    spec = build_transform([{"source_path": "src", "target_path": "dst", "transform": "uppercase"}])
    out = apply_transform(spec, {"src": "hello"})
    assert out == {"dst": "HELLO"}


def test_apply_lowercase():
    spec = build_transform([{"source_path": "src", "target_path": "dst", "transform": "lowercase"}])
    out = apply_transform(spec, {"src": "WORLD"})
    assert out == {"dst": "world"}


def test_apply_trim():
    spec = build_transform([{"source_path": "src", "target_path": "dst", "transform": "trim"}])
    out = apply_transform(spec, {"src": "  spaces  "})
    assert out == {"dst": "spaces"}


def test_apply_skips_missing_source():
    spec = build_transform([{"source_path": "missing", "target_path": "dst", "transform": None}])
    out = apply_transform(spec, {"other": "val"})
    assert out == {}


def test_apply_dotted_target_path():
    spec = build_transform([{"source_path": "src", "target_path": "a.b.c", "transform": None}])
    out = apply_transform(spec, {"src": "v"})
    assert out == {"a": {"b": {"c": "v"}}}


def test_unknown_transform_raises():
    with pytest.raises(TransformError):
        build_transform([{"source_path": "s", "target_path": "t", "transform": "kaboom"}])
