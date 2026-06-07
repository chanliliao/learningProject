# Plan: Pipeline — Milestone 3 (Build + Test Stages + Eval Harness)

> **For implementers:** Execute in order. TDD: failing test → run (fail) → implement → run (pass) →
> commit. Builds on M0–M2. Reference spec: `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Turn approved mappings into something runnable and prove it works. Add the **Build** node
(`transform.py`): from approved `FieldMapping`s, generate a JSON mapping config plus a deterministic
Python applier that converts a source document into the target JSON. Add the **Test** node
(`qa.py`): auto-generate test cases, run the applier, and validate the output against the target JSON
Schema. Extend the LangGraph graph to `extract→map→(interrupt)→build→test→(interrupt)→END`. Build the
**eval harness** (`backend/eval/`): a golden dataset of labeled mappings, a runner reporting
field-level precision/recall, confidence calibration, and aggregate LLM cost. Add an **eval
dashboard** to the console. Outcome: an end-to-end runnable transform with measured accuracy.

## User Story

As an integration engineer
I want approved mappings compiled into a runnable, validated transform and a report of how accurate
the mapping is
So that I can trust the output and measure the pipeline's quality.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Milestone | M3 of (M0→M4) |
| Systems Affected | backend (build/test nodes, graph, eval), frontend (eval dashboard) |
| Jira Issue | N/A |

---

## Prerequisites (from M0–M2)

- M1: graph, nodes, models, `start_run`; M2: confidence scoring, `resume_run`, review API, console.
- Sample data + two target JSON schemas (M1 Story 4). `FieldMapping.status="approved"` after review.

---

## Patterns to Follow

### Node + graph (existing)
```python
# SOURCE: backend/app/graph/build.py (M1) — node(state)->partial_state; START->extract->map->interrupt
```
### Backend test style — `backend/tests/test_health.py:1-10`; pytest config `pyproject.toml:17-20`.
### Frontend — `src/App.test.tsx:1-7`; `npm test`=`vitest run`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/agents/transform.py` | CREATE | Build node: mapping config + Python applier |
| `backend/app/agents/qa.py` | CREATE | Test node: generate cases + validate output |
| `backend/app/graph/build.py` | UPDATE | Add build + test nodes and second interrupt |
| `backend/app/models/run.py` | UPDATE | (optional) store TransformSpec/TestReport in StageResult payload |
| `backend/eval/__init__.py`, `runner.py`, `__main__.py` | CREATE | Eval harness |
| `backend/eval/golden/*.json` | CREATE | Golden labeled mappings |
| `backend/app/routers/eval.py` | CREATE | Serve latest eval report |
| `backend/app/main.py` | UPDATE | Include eval router |
| `frontend/src/pages/EvalPage.tsx` | CREATE | Eval dashboard |
| `frontend/src/api.ts` | UPDATE | getEvalReport() |
| tests | CREATE | per task |

---

## Story 1 — Build node (transform generation + applier)

### Task 1.1: Transform applier (deterministic)

- **File:** `backend/app/agents/transform.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/agents/test_transform_apply.py`:

```python
from app.agents.transform import build_transform, apply_transform

def test_apply_maps_and_coerces():
    mappings = [
        {"source_path": "Policy.PolicyNumber", "target_path": "policyNumber", "transform": None},
        {"source_path": "Policy.FaceAmount", "target_path": "faceAmount", "transform": "to_number"},
    ]
    spec = build_transform(mappings)
    source = {"Policy.PolicyNumber": "A123", "Policy.FaceAmount": "100000"}
    out = apply_transform(spec, source)
    assert out == {"policyNumber": "A123", "faceAmount": 100000}
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `build_transform(mappings) -> TransformSpec` (pydantic: ordered list of
  `{source_path, target_path, transform}`) and `apply_transform(spec, source_dict) -> dict`.
  Supported transforms (named registry, deterministic): `None` (copy), `to_number`, `to_date_iso`,
  `uppercase`, `lowercase`, `trim`. Unknown transform → raise `TransformError`. Set nested target
  paths if target uses dotted keys.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add deterministic transform builder and applier`

### Task 1.2: Build node integration

- **File:** `backend/app/agents/transform.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/agents/test_build_node.py`: given approved
  `FieldMapping`s in DB for a run, call `run_build(run_id, session)`; assert a
  `StageResult(stage="build", status="approved")` is stored with the `TransformSpec` in its payload
  and an `AuditEvent` recorded.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `run_build(run_id, session)`: load approved mappings, `build_transform`,
  persist `StageResult` payload + `AuditEvent`. Build is deterministic (no LLM).
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add build node persisting transform spec`

---

## Story 2 — Test node (QA)

### Task 2.1: Test-case generation + validation

- **File:** `backend/app/agents/qa.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/agents/test_qa.py`:

```python
from app.agents.qa import run_qa_checks

def test_qa_validates_against_target_schema():
    spec = {"mappings": [
        {"source_path": "Policy.PolicyNumber", "target_path": "policyNumber", "transform": None}]}
    target_schema = {"type": "object", "required": ["policyNumber"],
                     "properties": {"policyNumber": {"type": "string"}}}
    samples = [{"Policy.PolicyNumber": "A1"}, {"Policy.PolicyNumber": ""}]
    report = run_qa_checks(spec, target_schema, samples)
    assert report.total == 2
    assert report.passed >= 1
    assert any(not c.ok for c in report.cases)  # empty required value fails
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `run_qa_checks(spec, target_schema, samples) -> TestReport` (pydantic:
  `total`, `passed`, `cases: list[Case{ok, errors}]`). For each sample: `apply_transform`, validate
  output against `target_schema` using `jsonschema` (add dep). Auto-generate a couple of edge samples
  (empty values, type-boundary) if `samples` is small. Record per-case pass/fail + errors.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add QA test node validating transform output`

### Task 2.2: Wire build + test into the graph

- **File:** `backend/app/graph/build.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/graph/test_graph_full.py`: run a pipeline to the map
  interrupt, `resume_run(approve)`; assert the graph proceeds through `build` then `test`, persists
  `StageResult`s for both, pauses at a second interrupt after `test` (status `awaiting_review`), and
  a final `resume_run(approve)` sets `PipelineRun.status="completed"`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** add `build_node` + `test_node` to the graph:
  `extract→map→(interrupt)→build→test→(interrupt)→END`. `test_node` stores the `TestReport`; final
  approval completes the run.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: extend graph with build and test nodes`

### Task 2.3: jsonschema dependency

- **File:** `backend/pyproject.toml` (UPDATE)
- [ ] **Step 1 — add** `jsonschema>=4.23` to `[project].dependencies`; `uv sync`.
- [ ] **Step 2 — commit:** `chore: add jsonschema dependency`
  > (If Task 2.1 is implemented before this, add the dep first so its test can run.)

---

## Story 3 — Eval harness

### Task 3.1: Golden dataset

- **Files:** `backend/eval/golden/*.json` (CREATE)
- [ ] **Step 1 — author** ~10 golden records: each `{source_doc, target_schema_name,
  expected_mappings:[{source_path, target_path}]}` covering both distributor schemas and a few messy
  docs. Use the M1 sample XML where possible.
- [ ] **Step 2 — commit:** `test: add golden mapping dataset for eval`

### Task 3.2: Eval runner (precision/recall + calibration + cost)

- **Files:** `backend/eval/runner.py`, `backend/eval/__main__.py`, `__init__.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/eval/test_runner.py`: with a tiny in-test golden set
  and `mode="test"` map output, run `evaluate(golden, session, mode="test")`; assert the report has
  `precision`, `recall` in [0,1], a `calibration` section (flagged-vs-correct), and `total_cost`
  (sum of `LLMCall.estimated_cost`).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `evaluate(...)`: for each golden doc, run extract+map, compare proposed
  vs expected mappings → per-field TP/FP/FN → precision/recall; compute calibration (do
  `flags`/low-confidence predict the FNs/FPs?); sum cost from `LLMCall`. `__main__.py` runs against
  the file golden set and prints a summary; `uv run python -m eval`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add eval runner with precision/recall, calibration, cost`

### Task 3.3: Eval report API

- **Files:** `backend/app/routers/eval.py` (CREATE), `main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_eval_api.py`: `GET /eval/latest` returns
  the last computed report (or 404 if none). Use a stored report fixture / cached file.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** persist the latest report (JSON file or `EvalReport` table) when the
  runner runs; `GET /eval/latest` serves it. Include router.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add eval report endpoint`

---

## Story 4 — Eval dashboard (frontend)

### Task 4.1: Eval page

- **Files:** `frontend/src/pages/EvalPage.tsx` (CREATE), `frontend/src/api.ts`,
  `frontend/src/main.tsx` (UPDATE)
- [ ] **Step 1 — failing test** `frontend/src/pages/EvalPage.test.tsx`: mock `getEvalReport`
  returning precision/recall/calibration/cost; render; assert metrics + a calibration summary + total
  cost display.
- [ ] **Step 2 — run** `npm test` → FAIL.
- [ ] **Step 3 — implement** `getEvalReport()` in `api.ts`; `EvalPage` Tailwind cards for
  precision/recall, a calibration table, and total LLM cost; add `/eval` route.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add eval dashboard page`

---

## Validation

```bash
cd backend && uv run pytest -v && uv run python -m eval   # report prints
cd frontend && npm test && npm run build
# Manual: upload -> approve map -> build+test run -> approve -> completed; open /eval
```

## Acceptance Criteria

- [ ] Approved mappings compile to a `TransformSpec`; `apply_transform` produces target JSON
- [ ] Test node validates output against the target JSON Schema and reports pass/fail cases
- [ ] Graph runs `extract→map→(gate)→build→test→(gate)→END`; final approval completes the run
- [ ] `uv run python -m eval` reports precision/recall, calibration, and total cost
- [ ] `GET /eval/latest` serves the report; dashboard renders it
- [ ] All backend + frontend tests pass offline
- [ ] Follows existing patterns

---

## Out of Scope (later)

- M4: Interpret node, LlamaIndex+Qdrant Support RAG, Ragas eval, support chat UI.
