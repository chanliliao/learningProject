# Implementation Report

**Plan**: `.agents/plans/2026-06-06-pipeline-m3-build-test-eval.plan.md`
**Status**: COMPLETE

## Summary

Added Build + Test stages to the pipeline graph (second review gate), an eval harness with golden datasets, a `GET /eval/latest` API endpoint, and a frontend eval dashboard at `/eval`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Transform applier (deterministic) | `app/agents/transform.py` | ✅ |
| 2 | Build node integration | `app/agents/transform.py` | ✅ |
| 3 | QA test-case validation | `app/agents/qa.py` | ✅ |
| 4 | Wire build+test into graph | `app/graph/build.py` | ✅ |
| 5 | jsonschema dependency | `pyproject.toml` | ✅ |
| 6 | Golden dataset | `eval/golden/*.json` | ✅ |
| 7 | Eval runner | `eval/runner.py`, `__main__.py` | ✅ |
| 8 | Eval report API | `app/routers/eval.py` | ✅ |
| 9 | Eval dashboard | `frontend/src/pages/EvalPage.tsx` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend tests | ✅ 63 passed |
| Frontend tests | ✅ 13 passed |
| TypeScript build | ✅ clean |

## Files Changed

| File | Action |
|------|--------|
| `backend/app/agents/transform.py` | CREATE |
| `backend/app/agents/qa.py` | CREATE |
| `backend/app/graph/build.py` | UPDATE — add build/test nodes, second interrupt, aget_state check |
| `backend/app/routers/review.py` | UPDATE — pass stage to resume_run, stage-level 409 guard |
| `backend/app/routers/eval.py` | CREATE |
| `backend/app/main.py` | UPDATE — include eval router |
| `backend/pyproject.toml` | UPDATE — add jsonschema>=4.23 |
| `backend/eval/__init__.py` | CREATE |
| `backend/eval/runner.py` | CREATE |
| `backend/eval/__main__.py` | CREATE |
| `backend/eval/golden/acord_life_basic.json` | CREATE |
| `backend/eval/golden/acord_life_partial.json` | CREATE |
| `frontend/src/api.ts` | UPDATE — add EvalReport types + getEvalReport |
| `frontend/src/main.tsx` | UPDATE — add /eval route |
| `frontend/src/pages/EvalPage.tsx` | CREATE |
| `frontend/src/pages/RunPage.tsx` | UPDATE — dynamic pending stage for second gate |

## Deviations from Plan

1. **Graph completion detection**: Used `compiled.aget_state(config)` to check `graph_state.next` instead of relying on `NodeInterrupt` propagation. LangGraph 0.2.x doesn't re-raise `NodeInterrupt` for the second interrupt when called via `ainvoke(Command(resume=...))`.

2. **QA empty-value check**: Added a custom empty-string check for required fields on top of `jsonschema.validate`, since JSON Schema considers `""` a valid string.

3. **Stage-level 409 guard**: Extended the double-approve guard in `approve_stage`/`reject_stage` to check `StageResult.status`, not just `run.status`. This prevents re-approving a stage that was already approved (e.g., calling `map/approve` twice when already at the test gate).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/agents/test_transform_apply.py` | 7 |
| `tests/agents/test_qa.py` | 3 |
| `tests/agents/test_build_node.py` | 1 |
| `tests/graph/test_graph_full.py` | 2 |
| `tests/eval/test_runner.py` | 1 |
| `tests/routers/test_eval_api.py` | 2 |
| `frontend/src/pages/EvalPage.test.tsx` | 4 |
