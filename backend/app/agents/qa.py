"""
QA / test agent: runs automated quality checks against a compiled transform spec.

Takes a ``TransformSpec`` and a list of source record dicts, applies the transforms
to each record, then validates every output against the target JSON schema.  Also
auto-generates edge-case samples (empty values) so at least a minimum number of test
cases are exercised even when only one sample record is provided.
"""

import jsonschema
from pydantic import BaseModel
from app.agents.transform import TransformSpec, apply_transform, build_transform


class Case(BaseModel):
    """Result of a single test case.

    Attributes:
        ok: ``True`` if the transformed output passed JSON schema validation with no
            errors.
        errors: List of validation error messages.  Empty when ``ok`` is ``True``.
    """

    ok: bool
    errors: list[str]


class TestReport(BaseModel):
    """Aggregate QA report for a pipeline run's test stage.

    Attributes:
        total: Total number of test cases executed (user-supplied samples + auto-generated).
        passed: Number of cases where ``ok`` is ``True``.
        cases: Per-case detail, in the same order as the samples passed to
            ``run_qa_checks``.
    """

    total: int
    passed: int
    cases: list[Case]


def _validate(output: dict, schema: dict) -> list[str]:
    """Validate a transformed output dict against a JSON Schema.

    In addition to standard JSON Schema validation, also checks that every required
    field is non-empty (JSON Schema allows ``""`` but it is semantically meaningless
    for our use case).

    Args:
        output: The dict produced by ``apply_transform`` for one source record.
        schema: Target JSON Schema definition (must be a valid JSON Schema dict).

    Returns:
        List of error message strings.  Empty list means validation passed.
    """
    errors = []
    try:
        jsonschema.validate(instance=output, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(e.message)
    except jsonschema.SchemaError as e:
        errors.append(f"Schema error: {e.message}")
    # Extra check: JSON Schema permits empty strings for ``type: string`` fields,
    # but required fields with empty strings are meaningless in our context.
    for req_field in schema.get("required", []):
        val = output.get(req_field)
        if val is not None and isinstance(val, str) and val.strip() == "":
            errors.append(f"Required field '{req_field}' is empty")
    return errors


def _auto_edge_samples(spec: TransformSpec) -> list[dict]:
    """Generate automatic edge-case samples for a transform spec.

    Currently produces one sample: all source fields set to empty strings.  This
    exercises required-field and type-validation rules without needing real data.

    Args:
        spec: Compiled transform specification to generate samples for.

    Returns:
        List of source record dicts to append to the user-supplied samples.
    """
    samples = []
    # Empty-value sample: exercises required-field and type-check validation paths
    samples.append({m.source_path: "" for m in spec.mappings})
    return samples


def run_qa_checks(
    spec: dict | TransformSpec,
    target_schema: dict,
    samples: list[dict],
) -> TestReport:
    """Run automated QA checks for a pipeline run's test stage.

    Applies the transform spec to every provided sample and validates each output
    against the target schema.  If fewer than 3 samples are provided, auto-generated
    edge-case samples are appended to ensure a minimum level of coverage.

    Args:
        spec: Either a compiled ``TransformSpec`` or a raw dict with a ``"mappings"``
            key (the payload stored in the build ``StageResult``).  A dict is compiled
            via ``build_transform`` before use.
        target_schema: Full JSON Schema definition for the destination data format.
        samples: List of source record dicts to test.  Each dict maps source field
            paths to their string values, as produced by ``extract``.

    Returns:
        A ``TestReport`` containing per-case results and aggregate pass/fail counts.
    """
    if isinstance(spec, dict):
        spec = build_transform(spec.get("mappings", []))

    all_samples = list(samples)
    if len(all_samples) < 3:
        all_samples.extend(_auto_edge_samples(spec))

    cases = []
    for sample in all_samples:
        try:
            output = apply_transform(spec, sample)
            errs = _validate(output, target_schema)
            cases.append(Case(ok=len(errs) == 0, errors=errs))
        except Exception as e:
            cases.append(Case(ok=False, errors=[str(e)]))

    passed = sum(1 for c in cases if c.ok)
    return TestReport(total=len(cases), passed=passed, cases=cases)
