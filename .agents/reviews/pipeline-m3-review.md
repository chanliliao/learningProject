# Code Review: Pipeline M3 Build + Test Stages + Eval Harness

**Scope**: feat/pipeline branch — M3 Build/Test Nodes + Eval Harness (vs M3 plan at
`.agents/plans/completed/2026-06-06-pipeline-m3-build-test-eval.plan.md`)
**Recommendation**: NEEDS WORK — test gate approval is broken from the frontend

---

## Summary

M3 delivers the build and test nodes, extends the graph to two gates, eval harness
(`runner.py`, `__main__.py`, golden dataset), `GET /eval/latest`, and the eval dashboard.
All 63 backend tests and 13 frontend tests pass; frontend build is clean. All six M2 issues
were also fixed in this milestone (`GET /schemas`, re-score on edit, bare except in resume_run,
dead schema var, double-approve guard, threshold mismatch, transform setter). One high issue
blocks the second-gate flow at runtime: both Approve and Reject in `RunPage.tsx` are hardcoded
to `stage='map'`, causing a 409 when the run is paused at the test gate.

---

## M2 Issues — Disposition

All six M2 issues were fixed:

| M2 Issue | Fix location |
|----------|-------------|
| `GET /schemas` missing (Critical) | `pipeline.py:52-55` |
| `edit_field` no re-score (High) | `review.py:45-64` |
| `except Exception: pass` in resume_run (High) | `build.py:285-287` → `except NodeInterrupt: pass` |
| Dead `schema` var in resume_run (Medium) | removed |
| No double-approve guard (Medium) | `review.py:96-103` |
| Frontend threshold 0.7 vs backend 0.8 (Medium) | `FieldReviewTable.tsx:30` now `< 0.8` |
| `transform` setter discarded (Medium) | `FieldReviewTable.tsx:19` now uses `setTransform` |

---

## Issues Found

### Critical

None.

### High

1. **`RunPage.tsx:24-30` — Approve/Reject hardcoded to `'map'`; test gate approval silently fails**
   - `approve = useMutation({ mutationFn: () => approveStage(runId, 'map') })` and
     `reject = useMutation({ mutationFn: () => rejectStage(runId, 'map') })` — both hardcoded
   - After M3, the graph has two gates: map (first) and test (second). Both set `run.status =
     'awaiting_review'` and show the same Approve/Reject buttons
   - When the run reaches the test gate, clicking Approve calls
     `POST /runs/{id}/stages/map/approve`. The map stage is already `status="approved"` →
     the backend 409 guard fires (`"Stage 'map' already processed"`)
   - Neither mutation has an `onError` handler → the 409 is swallowed; the UI does nothing
   - Fix: determine the pending stage from `stage_results`:
     ```tsx
     const pendingStage = stage_results.find(s => s.status === 'awaiting_review')?.stage ?? 'map'
     const approve = useMutation({
       mutationFn: () => approveStage(runId, pendingStage),
       ...
     })
     ```
   - Also add `onError` to surface failures to the user

### Medium

2. **`runner.py:78` — calibration uses raw `llm_confidence`, not hybrid score**
   - Eval loop calls `propose_mappings` (returns `FieldMappingProposal` with `llm_confidence`)
     and buckets by `p.llm_confidence if p.llm_confidence is not None else 0.5`
   - The hybrid confidence stored on `FieldMapping` (heuristic + LLM blend) is what the
     review console displays and what M2 confidence gates are based on
   - Calibration headline "is confidence predictive of correctness?" is testing LLM confidence
     only, not the value the user sees
   - Fix: after computing proposals, run `score_mapping(...)` for each to get hybrid confidence,
     or note the discrepancy in a comment so it's not misleading

3. **`build.py:131-133` — `test_node` silently uses empty `TransformSpec` if no build stage**
   - `spec_data = build_stage.payload.get("spec", {}) if build_stage else {}`
   - If `build_stage is None` (e.g. DB flush timing issue), `spec = TransformSpec(mappings=[])`
   - An empty spec produces all-empty output; if target schema has no required fields the QA
     report shows `passed == total` with zero mappings — a false-positive pass
   - Fix: raise `RuntimeError("build stage not found for run_id={run_id}")` if `build_stage`
     is None

4. **Golden dataset has 2 records vs plan's "~10"**
   - `eval/golden/` contains `acord_life_basic.json` and `acord_life_partial.json` (2 records)
   - With 2 records the precision/recall numbers are highly sensitive to single-field errors
     and calibration buckets are statistically meaningless (n=2 in high bucket)
   - Fix: add 8+ more records covering the second distributor schema and edge cases (missing
     required fields, type mismatches, deeply nested paths)

5. **`RunPage.tsx:17-19` — polling continues during `awaiting_review` (M2 carry-over)**
   - `refetchInterval` returns `POLL_INTERVAL` (2 s) for both `running` and `awaiting_review`
   - At both gates the user is expected to make a decision; continuous 2 s polling during
     human review is unnecessary noise
   - Fix: poll only when `status === 'running'`

### Suggestions

- **`transform.py:24` — `to_date_iso` is misleadingly named**: it does `str(v).strip()` — it
  does not parse or reformat to ISO 8601. Given `"15/01/2024"` it returns `"15/01/2024"`.
  Either implement actual parsing (`datetime.fromisoformat`, `dateutil.parse`) or rename it
  `to_string`.

- **`qa.py:35-37` — `_auto_edge_samples` generates only empty-value samples**: plan specified
  "empty values, type-boundary". Only the empty-value case is generated; type-boundary samples
  (e.g., string where number expected) are missing. Add one sample with type-mismatched values.

- **`test_evaluate_returns_valid_report` asserts range but not TP/FP/FN correctness**: the test
  checks `0 <= precision <= 1` but not that TP > 0 or that the in-test golden record produces
  any correct mapping. TestModel returns deterministic proposals; assert at least one TP to
  catch a mapping regression.

---

## Validation Results

| Check | Status |
|-------|--------|
| Backend tests (pytest) | PASS — 63/63 |
| Frontend tests (vitest) | PASS — 13/13 |
| Frontend build (tsc + vite) | PASS |

---

## What's Good

- All M2 issues fixed: `GET /schemas`, re-score on edit, bare except, dead var, double-approve
  guard, threshold alignment, transform setter — clean sweep
- `build_transform` + `apply_transform` are pure sync functions (correct per plan convention);
  `run_build` and `run_qa_checks` are correctly async/sync respectively
- `TransformError` propagates through `build_node` / `test_node` with `run.status = "failed"`
  and an `AuditEvent` — error path handled
- `resume_run` correctly detects second-gate completion via `aget_state`: if `graph_state.next`
  is empty, sets `run.status = "completed"` — the two-gate flow logic is correct in the backend
- `test_graph_full.py::test_full_graph_two_approvals` validates the full
  `start→approve_map→approve_test→completed` path end-to-end
- `eval/runner.py` uses `_REPORT_PATH` as a module-level constant; test monkeypatches it
  cleanly — no file-system side-effects in tests
- `eval_api.py` `GET /eval/latest` returns 404 with actionable message ("Run: uv run python
  -m eval")
- `EvalPage.tsx` handles both the loading state and the no-report (error) state
- Dotted target path support (`a.b.c`) in `apply_transform` is implemented and tested
- `run_build` filter `["proposed", "edited", "approved"]` is pragmatically correct — individual
  mappings are never individually approved in the current flow; "stage approved" is tracked
  on `StageResult`, not `FieldMapping`

---

## Recommendation

Fix issue #1 (stage hardcoding in RunPage) before any manual end-to-end testing — the second
gate approval is dead without it. Issue #4 (golden dataset size) is needed before `uv run
python -m eval` produces meaningful numbers. Issues #2, #3, #5 are low blast-radius and can
be batched at M4 start.
