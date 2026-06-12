# Plan: Phase 3 — Transform DSL (CEL / JMESPath)

## Summary

Replace the 5-function `_TRANSFORMS` registry with an expressive, safe, serializable rule language so real carrier logic (conditionals, multi-field combine, code-table lookups, date math, defaults) can be expressed as data. Adopt **CEL** (via `cel-python`) for boolean/conditional logic and **JMESPath** for path selection/reshaping. Rules are stored on `FieldMapping`/`TransformMapping`, evaluated in a sandbox (never Python `eval`), and are LLM-generatable (sets up Phase 4 NL editing).

> **Sequencing**: Do this AFTER Phase 2, not in parallel. Both rewrite `transform.py`; Phase 2's projection reuses the existing engine, then Phase 3 extends it with rules. Running them concurrently causes a merge conflict.

## User Story

As a mapping author
I want to express conditional and multi-field transforms as safe, stored rules
So that real carrier logic works without writing Python and without security risk

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (core engine) |
| Complexity | MEDIUM–HIGH |
| Systems Affected | transform engine, mapping model, map agent, qa, migration, deps |
| Jira Issue | N/A |

---

## Patterns to Follow

### Current registry + apply (the thing being replaced/extended)
```python
# SOURCE: backend/app/agents/transform.py:55-61
_TRANSFORMS: dict[str, object] = {
    "to_number": lambda v: float(v) if "." in str(v) else int(v), ...
}
# SOURCE: backend/app/agents/transform.py:120-129  (apply branch)
```

### TransformMapping model to extend
```python
# SOURCE: backend/app/agents/transform.py:22-36
class TransformMapping(BaseModel):
    source_path: str
    target_path: str
    transform: str | None = None
```

### Validation-at-compile pattern (keep this guarantee)
```python
# SOURCE: backend/app/agents/transform.py:82-91  (build_transform raises early)
```

### Test style
```python
# SOURCE: backend/tests/agents/test_transform_apply.py:46-48
def test_unknown_transform_raises():
    with pytest.raises(TransformError): ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `cel-python`, `jmespath` |
| `backend/app/agents/transform.py` | UPDATE | Add `rule` field + CEL/JMESPath evaluator; keep named transforms |
| `backend/app/pipeline/dsl.py` | CREATE | Safe rule-eval wrapper (CEL + JMESPath), allow-list functions |
| `backend/app/models/mapping.py` | UPDATE | Add `rule: dict \| None` column |
| `backend/app/agents/map.py` | UPDATE | Allow LLM to emit a `rule` (validated downstream) |
| `backend/app/graph/build.py` | UPDATE | Validate `rule` in `map_node` like `transform` |
| `backend/alembic/versions/xxxx_rule_col.py` | CREATE | Migration for `rule` column |
| `backend/tests/pipeline/test_dsl.py` | CREATE | Conditional, combine, lookup, date, sandbox-escape tests |

---

## Tasks

### Task 1: Add deps
- **File**: `backend/pyproject.toml`
- **Action**: UPDATE — add `"cel-python>=0.1"`, `"jmespath>=1.0"` to `dependencies`.
- **Validate**: `cd backend && uv sync`

### Task 2: Safe DSL evaluator
- **File**: `backend/app/pipeline/dsl.py`
- **Action**: CREATE
- **Implement**:
  - `class RuleError(Exception)`.
  - Rule schema (Pydantic): `{ "engine": "cel" | "jmespath", "expr": str, "inputs": list[str] }` where `inputs` are source paths the rule reads.
  - `def eval_rule(rule: dict, source: dict) -> Any`:
    - Build a restricted context dict from `inputs` only (no access to full env).
    - CEL: compile via `cel-python` with an **allow-list** of functions (string ops, `has`, comparisons, date parse). No I/O, no attribute access beyond inputs.
    - JMESPath: `jmespath.search(expr, context)`.
    - Catch + wrap errors in `RuleError`. **Never** call `eval`/`exec` (CLAUDE.md security rule).
  - `def validate_rule(rule: dict) -> None`: compile without executing; raise `RuleError` on bad syntax/disallowed funcs (compile-time guarantee like `build_transform`).
- **Mirror**: `backend/app/agents/transform.py:82-91` (early-validate), `:18-19` (error class)
- **Validate**: `cd backend && uv run pytest tests/pipeline/test_dsl.py`

### Task 3: Extend the transform engine
- **File**: `backend/app/agents/transform.py`
- **Action**: UPDATE
- **Implement**:
  - Add `rule: dict | None = None` to `TransformMapping`.
  - In `build_transform`: if `rule` present, call `validate_rule(rule)`; keep existing named-`transform` validation. A mapping has either `transform` OR `rule` (or neither).
  - In `apply_transform`: if `rule` set, `value = eval_rule(rule, source)` (rules read multiple inputs, so pass the whole `source`); else fall back to named transform / verbatim. Keep dotted-target-path expansion.
- **Mirror**: `backend/app/agents/transform.py:64-136`
- **Validate**: `cd backend && uv run pytest tests/agents/test_transform_apply.py tests/pipeline/test_dsl.py`

### Task 4: Persist rules
- **File**: `backend/app/models/mapping.py` + migration
- **Action**: UPDATE / CREATE
- **Implement**: Add `rule: dict | None = Field(default=None, sa_column=Column(JSON))` with Attributes docstring. Migration adds nullable JSON column. `run_build` includes `rule` in `mappings_data`.
- **Mirror**: `backend/app/models/mapping.py:46` (JSON column via `flags`)
- **Validate**: `cd backend && uv run alembic upgrade head`

### Task 5: Let map agent propose rules + validate in graph
- **File**: `backend/app/agents/map.py`, `backend/app/graph/build.py`
- **Action**: UPDATE
- **Implement**: Extend `FieldMappingProposal` (in `base.py`) with optional `rule`. In `map_node`, validate any proposed `rule` via `validate_rule`; on failure normalize to `None` (mirror the existing transform normalization at `build.py:258`). Update the map system prompt to describe available rule engines + examples.
- **Mirror**: `backend/app/graph/build.py:255-267`
- **Validate**: `cd backend && uv run pytest`

### Task 6: Tests
- **File**: `backend/tests/pipeline/test_dsl.py`
- **Action**: CREATE
- **Implement**:
  - `test_conditional`: CEL `FaceAmt > 250000 ? 'underwrite' : 'auto'`.
  - `test_combine_fields`: CEL `FirstName + ' ' + LastName`.
  - `test_code_table_lookup`: map ACORD `tc` code → label.
  - `test_jmespath_reshape`: select nested value.
  - `test_sandbox_blocks_escape`: a malicious expr (attribute access / import attempt) raises `RuleError`, does not execute. **Security-critical.**
  - `test_invalid_rule_raises_at_build`: `build_transform` rejects bad rule.
- **Mirror**: `backend/tests/agents/test_transform_apply.py`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| Sandbox escape (security) | CEL is non-Turing-complete + allow-listed funcs; explicit escape test. Never `eval`. |
| Two ways to transform (named vs rule) | Keep named transforms for simple cases; rule for complex. `build_transform` enforces one-or-the-other. |
| `cel-python` maturity | JMESPath covers reshape; CEL covers logic. If CEL dep is problematic, fall back to a tiny allow-listed AST evaluator — still no `eval`. |

## Acceptance Criteria

- [ ] Conditionals, multi-field combine, code-table lookup, date handling expressible as stored rules
- [ ] Rules validated at build time; invalid rules rejected with `RuleError`
- [ ] Sandbox-escape test proves no arbitrary code execution
- [ ] Existing 5 named transforms still work (back-compat)
- [ ] `uv run pytest` green
